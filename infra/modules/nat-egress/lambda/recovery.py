"""Fixed-slot NAT launch recovery. Importing this module creates no AWS clients.

One reserved Lambda execution plus conditional durable records serialize effects.
An unacknowledged mutation is never replayed, even if its readback looks right:
EC2 route/address APIs have no generation fence or idempotency token. Operators
must settle that uncertainty before admitting another member. This is not AZ
failover, continuous forwarding monitoring, or a claim of live packet delivery.
"""
import base64
import hashlib
import json
import os
import re
import time
from datetime import datetime


STEPS = ("sdc", "eip", "route")


class Rejected(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Rejected(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(value).hexdigest()


def one(values):
    require(type(values) is list and len(values) == 1, "EXACT_SINGLE_RESOURCE_REQUIRED")
    return values[0]


def tags(values):
    result = {v["Key"]: v["Value"] for v in values}
    require(len(result) == len(values), "DUPLICATE_TAGS")
    return result


def configuration(config):
    require(set(config) == {"schema", "account", "region", "project", "environment", "vpc", "slots"}, "CONFIG_FIELDS")
    require(config["schema"] == 1 and re.fullmatch(r"[0-9]{12}", config["account"]), "CONFIG_IDENTITY")
    slots = config["slots"]
    require(type(slots) is list and 1 <= len(slots) <= 3, "SLOT_CAPACITY_LIMIT")
    fields = {"asg", "az", "subnet", "eip", "table", "ami", "instance_type", "profile", "sg", "lt", "version", "user_data_sha256", "predecessor_enis"}
    for slot in slots:
        require(set(slot) == fields, "SLOT_FIELDS")
        require(slot["instance_type"] == "t3.micro" and type(slot["version"]) is int and slot["version"] > 0, "REVIEWED_LAUNCH_REQUIRED")
        for field, prefix in (("subnet", "subnet"), ("eip", "eipalloc"), ("table", "rtb"), ("ami", "ami"), ("sg", "sg"), ("lt", "lt")):
            require(re.fullmatch(prefix + r"-(?:[0-9a-f]{8}|[0-9a-f]{17})", slot[field]), "SLOT_ID")
        require(re.fullmatch(r"[0-9a-f]{64}", slot["user_data_sha256"]), "USER_DATA_PIN")
        require(type(slot["predecessor_enis"]) is list and len(slot["predecessor_enis"]) <= 2, "PREDECESSOR_BOUND")
        require(all(re.fullmatch(r"eni-(?:[0-9a-f]{8}|[0-9a-f]{17})", v) for v in slot["predecessor_enis"]), "PREDECESSOR_ID")
    for field in ("asg", "az", "subnet", "eip", "table", "lt"):
        require(len({s[field] for s in slots}) == len(slots), "SLOTS_MUST_BE_DISJOINT")
    predecessors = [v for s in slots for v in s["predecessor_enis"]]
    require(len(predecessors) == len(set(predecessors)), "CROSS_SLOT_PREDECESSOR")
    return digest(canonical(config).encode())


class Journal:
    """No leases, TTL takeover, delete, or uncertainty-clearing operation."""
    def __init__(self, client, table):
        self.client, self.table = client, table

    def read(self, key):
        item = self.client.get_item(TableName=self.table, Key={"pk": {"S": key}}, ConsistentRead=True).get("Item")
        return json.loads(item["data"]["S"]) if item else None

    def write(self, key, value, previous):
        revision = 1 if previous is None else previous["revision"] + 1
        value = {**value, "revision": revision}
        args = dict(TableName=self.table, Item={"pk": {"S": key}, "revision": {"N": str(revision)}, "data": {"S": canonical(value)}})
        if previous is None:
            args["ConditionExpression"] = "attribute_not_exists(pk)"
        else:
            args.update(ConditionExpression="revision = :prior", ExpressionAttributeValues={":prior": {"N": str(previous["revision"])}})
        self.client.put_item(**args)
        return value


class Recovery:
    def __init__(self, config, ec2, autoscaling, journal, *, clock=time.time, sleep=time.sleep, remaining=lambda: 180000):
        self.config, self.ec2, self.asg, self.journal = config, ec2, autoscaling, journal
        self.generation = configuration(config)
        self.clock, self.sleep, self.remaining = clock, sleep, remaining

    def fence(self):
        control = self.journal.read("CONTROL")
        require(control == {"enabled": True, "generation": self.generation}, "RECOVERY_INHIBITED_OR_GENERATION_CHANGED")
        require(self.remaining() > 35000, "INSUFFICIENT_EXECUTION_BUDGET")

    def event(self, event):
        c = self.config
        require(event.get("source") == "aws.autoscaling" and event.get("detail-type") == "EC2 Instance Launch Successful", "EVENT_TYPE")
        require(event.get("account") == c["account"] and event.get("region") == c["region"], "EVENT_SCOPE")
        require(re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", event.get("id", "")), "EVENT_ID")
        emitted = datetime.fromisoformat(event["time"].replace("Z", "+00:00"))
        require(emitted.tzinfo is not None and -60 <= self.clock() - emitted.timestamp() <= 1800, "EVENT_AGE")
        detail = event["detail"]
        slot = one([s for s in c["slots"] if s["asg"] == detail.get("AutoScalingGroupName")])
        require(re.fullmatch(r"i-(?:[0-9a-f]{8}|[0-9a-f]{17})", detail.get("EC2InstanceId", "")), "EVENT_INSTANCE")
        return slot, detail["EC2InstanceId"]

    def member(self, slot, expected):
        self.fence()
        group = one(self.asg.describe_auto_scaling_groups(AutoScalingGroupNames=[slot["asg"]])["AutoScalingGroups"])
        require(group["AutoScalingGroupName"] == slot["asg"] and group["VPCZoneIdentifier"] == slot["subnet"], "GROUP_SCOPE")
        require(all(group[k] == 1 for k in ("MinSize", "MaxSize", "DesiredCapacity")), "GROUP_CAPACITY_OR_INHIBITION")
        require(not any(p["ProcessName"] in ("Launch", "ReplaceUnhealthy") for p in group.get("SuspendedProcesses", [])), "GROUP_SUSPENDED")
        member = one(group["Instances"])
        require(member["InstanceId"] == expected and member["LifecycleState"] == "InService" and member["HealthStatus"] == "Healthy", "STALE_OR_UNHEALTHY_MEMBER")
        launch = member["LaunchTemplate"]
        require(launch.get("LaunchTemplateId") == slot["lt"] and launch.get("Version") == str(slot["version"]), "MEMBER_LAUNCH_PIN")
        i = one(one(self.ec2.describe_instances(InstanceIds=[expected])["Reservations"])["Instances"])
        require(i["InstanceId"] == expected and i["State"]["Name"] == "running", "INSTANCE_STATE")
        require(i["VpcId"] == self.config["vpc"] and i["SubnetId"] == slot["subnet"] and i["Placement"]["AvailabilityZone"] == slot["az"], "INSTANCE_NETWORK")
        require(i["ImageId"] == slot["ami"] and i["InstanceType"] == slot["instance_type"] and i["MetadataOptions"]["HttpTokens"] == "required", "INSTANCE_LAUNCH")
        require(i.get("IamInstanceProfile", {}).get("Arn") == slot["profile"], "INSTANCE_PROFILE")
        required = {"Project": self.config["project"], "Environment": self.config["environment"], "Role": "nat", "NatSlot": slot["az"], "aws:autoscaling:groupName": slot["asg"]}
        require(all(tags(i["Tags"]).get(k) == v for k, v in required.items()), "INSTANCE_TAGS")
        require(sorted(v["GroupId"] for v in i["SecurityGroups"]) == [slot["sg"]], "INSTANCE_SECURITY_GROUP")
        ref = one(i["NetworkInterfaces"])
        eni = one(self.ec2.describe_network_interfaces(NetworkInterfaceIds=[ref["NetworkInterfaceId"]])["NetworkInterfaces"])
        require(eni["NetworkInterfaceId"] == ref["NetworkInterfaceId"] and eni["VpcId"] == self.config["vpc"] and eni["SubnetId"] == slot["subnet"] and eni["AvailabilityZone"] == slot["az"], "ENI_SCOPE")
        require(eni["Attachment"]["InstanceId"] == expected and eni["Attachment"]["DeleteOnTermination"] is True, "ENI_ATTACHMENT")
        require(all(tags(eni["TagSet"]).get(k) == v for k, v in required.items() if k != "aws:autoscaling:groupName"), "ENI_TAGS")
        require(isinstance(i.get("LaunchTime"), datetime) and i["LaunchTime"].tzinfo is not None, "INSTANCE_LAUNCH_TIME")
        return {"instance": expected, "eni": ref["NetworkInterfaceId"], "launched": int(i["LaunchTime"].timestamp())}

    def bootstrap(self, slot, current):
        version = one(self.ec2.describe_launch_template_versions(LaunchTemplateId=slot["lt"], Versions=[str(slot["version"])])["LaunchTemplateVersions"])
        data = version["LaunchTemplateData"]
        require(version["VersionNumber"] == slot["version"] and data["ImageId"] == slot["ami"] and data["InstanceType"] == slot["instance_type"], "TEMPLATE_PIN")
        require(data["MetadataOptions"]["HttpTokens"] == "required" and data.get("IamInstanceProfile", {}).get("Arn") == slot["profile"], "TEMPLATE_PROFILE")
        network = one(data["NetworkInterfaces"])
        require(network["AssociatePublicIpAddress"] is True and network["DeleteOnTermination"] is True and network["Groups"] == [slot["sg"]], "TEMPLATE_NETWORK")
        require(digest(base64.b64decode(data["UserData"], validate=True)) == slot["user_data_sha256"], "TEMPLATE_USER_DATA")
        raw = self.ec2.describe_instance_attribute(InstanceId=current["instance"], Attribute="userData")
        require(raw["InstanceId"] == current["instance"] and digest(base64.b64decode(raw["UserData"]["Value"], validate=True)) == slot["user_data_sha256"], "INSTANCE_USER_DATA")
        status = one(self.ec2.describe_instance_status(InstanceIds=[current["instance"]], IncludeAllInstances=True)["InstanceStatuses"])
        require(status["InstanceId"] == current["instance"] and status["InstanceStatus"]["Status"] == status["SystemStatus"]["Status"] == "ok", "EC2_STATUS_NOT_READY")
        output = self.ec2.get_console_output(InstanceId=current["instance"], Latest=True)
        text = output.get("Output", "")
        require(output.get("InstanceId") == current["instance"] and type(text) is str and len(text) <= 200000 and "\ufffd" not in text, "CONSOLE_OUTPUT")
        require(isinstance(output.get("Timestamp"), datetime) and output["Timestamp"].tzinfo is not None, "CONSOLE_TIMESTAMP")
        stamp = output["Timestamp"].timestamp()
        require(current["launched"] <= stamp <= self.clock(), "CONSOLE_TIME")
        marks = re.findall(r"(?m)^CNP_NAT_BOOTSTRAP_V1 (i-[0-9a-f]{8,17}) ([0-9]{1,12}) CONFIGURED\r?$", text)
        require(len(marks) == 1 and marks[0][0] == current["instance"] and current["launched"] <= int(marks[0][1]) <= stamp and "CNP_NAT_BOOTSTRAP_FAILED" not in text, "BOOTSTRAP_NOT_READY")

    def network(self, slot, current, predecessors):
        address = one(self.ec2.describe_addresses(AllocationIds=[slot["eip"]])["Addresses"])
        require(address["AllocationId"] == slot["eip"], "EIP_IDENTITY")
        table = one(self.ec2.describe_route_tables(RouteTableIds=[slot["table"]])["RouteTables"])
        require(table["RouteTableId"] == slot["table"] and table["VpcId"] == self.config["vpc"], "TABLE_SCOPE")
        required = {"Project": self.config["project"], "Environment": self.config["environment"]}
        require(all(tags(address["Tags"]).get(k) == v and tags(table["Tags"]).get(k) == v for k, v in required.items()), "NETWORK_OWNERSHIP")
        defaults = [r for r in table["Routes"] if r.get("DestinationCidrBlock") == "0.0.0.0/0"]
        require(len(defaults) <= 1, "AMBIGUOUS_DEFAULT")
        allowed = {None, current["eni"], *predecessors}
        require(address.get("NetworkInterfaceId") in allowed, "FOREIGN_EIP_ATTACHMENT")
        if defaults:
            require(defaults[0].get("NetworkInterfaceId") in allowed - {None} and not any(defaults[0].get(k) for k in ("GatewayId", "NatGatewayId", "TransitGatewayId", "VpcPeeringConnectionId")), "FOREIGN_DEFAULT_ROUTE")
        attr = self.ec2.describe_instance_attribute(InstanceId=current["instance"], Attribute="sourceDestCheck")
        require(attr["InstanceId"] == current["instance"] and type(attr["SourceDestCheck"]["Value"]) is bool, "SOURCE_DEST_READBACK")
        return {"sdc": attr["SourceDestCheck"]["Value"] is False, "eip": address.get("NetworkInterfaceId") == current["eni"], "route": bool(defaults) and defaults[0]["NetworkInterfaceId"] == current["eni"] and defaults[0].get("State") == "active", "route_exists": bool(defaults)}

    def run(self, event):
        slot, instance = self.event(event)
        current = self.member(slot, instance)
        deadline = self.clock() + 120
        for attempt in range(12):
            try:
                self.bootstrap(slot, current)
                require(self.clock() < deadline, "READINESS_BUDGET_EXCEEDED")
                break
            except Rejected:
                if attempt == 11 or self.clock() >= deadline:
                    raise
                self.sleep(min(10, max(0, deadline - self.clock())))
                require(self.member(slot, instance) == current, "MEMBER_CHANGED_DURING_READINESS")
        key = "SLOT#" + slot["asg"]
        row = self.journal.read(key)
        operation = digest(canonical({**current, "generation": self.generation}).encode())
        predecessors = list(slot["predecessor_enis"])
        if row:
            require(row["generation"] == self.generation, "JOURNAL_GENERATION_REQUIRES_REVIEW")
            if row["operation"] != operation:
                require(row["status"] == "READY" and row["pending"] is None, "UNSETTLED_PREVIOUS_MEMBER")
                predecessors.append(row["eni"])
            else:
                require(row["instance"] == instance and row["eni"] == current["eni"], "JOURNAL_MEMBERSHIP")
                predecessors = row["predecessors"]
        # Inspect all protected network objects before making even the first mutation.
        self.network(slot, current, predecessors)
        if row is None or row["operation"] != operation:
            row = self.journal.write(key, {**current, "generation": self.generation, "operation": operation, "status": "ACTIVE", "pending": None, "completed": [], "predecessors": predecessors}, row)
        require(row["completed"] == list(STEPS[:len(row["completed"])]), "JOURNAL_STEP_ORDER")
        for step in STEPS:
            self.fence()
            require(self.member(slot, instance) == current, "MEMBER_CHANGED")
            require(self.journal.read(key) == row, "CONCURRENT_JOURNAL_CHANGE")
            observed = self.network(slot, current, predecessors)
            if step in row["completed"]:
                require(observed[step], "PREVIOUS_EFFECT_DRIFT")
                continue
            if row["pending"]:
                require(row["pending"] == {"step": step, "phase": "ACK"}, "UNCERTAIN_EFFECT_NO_AUTOMATIC_REPLAY")
            elif not observed[step]:
                row = self.journal.write(key, {**row, "pending": {"step": step, "phase": "ATTEMPT"}}, row)
                self.fence()
                require(self.member(slot, instance) == current and self.journal.read(key) == row, "FENCE_CHANGED_BEFORE_EFFECT")
                # A single SDK attempt. Any exception leaves ATTEMPT durably unresolved.
                if step == "sdc":
                    self.ec2.modify_instance_attribute(InstanceId=instance, SourceDestCheck={"Value": False})
                elif step == "eip":
                    self.ec2.associate_address(AllocationId=slot["eip"], NetworkInterfaceId=current["eni"], AllowReassociation=True)
                else:
                    mutate = self.ec2.replace_route if observed["route_exists"] else self.ec2.create_route
                    mutate(RouteTableId=slot["table"], DestinationCidrBlock="0.0.0.0/0", NetworkInterfaceId=current["eni"])
                row = self.journal.write(key, {**row, "pending": {"step": step, "phase": "ACK"}}, row)
            for check in range(4):
                require(self.member(slot, instance) == current, "MEMBER_CHANGED_AFTER_EFFECT")
                if self.network(slot, current, predecessors)[step]:
                    break
                require(check < 3, "ACK_READBACK_NOT_OBSERVED")
                self.sleep(1)
            row = self.journal.write(key, {**row, "pending": None, "completed": [*row["completed"], step]}, row)
        require(self.member(slot, instance) == current and self.journal.read(key) == row, "FINAL_FENCE")
        require(all(self.network(slot, current, predecessors)[s] for s in STEPS), "FINAL_NETWORK_READBACK")
        if row["status"] != "READY":
            row = self.journal.write(key, {**row, "status": "READY"}, row)
        return {"status": "CONFIGURED_NETWORK_READBACK", "asg": slot["asg"], "instance": instance, "private_subnet_egress": "UNVERIFIED_LIVE_PROOF_REQUIRED"}


def lambda_handler(event, context):
    try:
        import boto3
        from botocore.config import Config
        config = json.loads(os.environ["NAT_CONFIG"])
        require(configuration(config) == os.environ["NAT_GENERATION"], "ENVIRONMENT_GENERATION")
        sdk = Config(connect_timeout=5, read_timeout=5, retries={"total_max_attempts": 1})
        clients = {s: boto3.client(s, region_name=config["region"], config=sdk) for s in ("ec2", "autoscaling", "dynamodb")}
        runtime = Recovery(config, clients["ec2"], clients["autoscaling"], Journal(clients["dynamodb"], os.environ["NAT_JOURNAL_TABLE"]), remaining=context.get_remaining_time_in_millis)
        return runtime.run(event)
    except Exception:
        # Never log full events, SDK exceptions, console output, IMDS tokens or payloads.
        raise RuntimeError("NAT_RECOVERY_STOPPED_INSPECT_JOURNAL_AND_FAILURE_QUEUE") from None
