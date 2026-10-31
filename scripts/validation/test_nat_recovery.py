"""SDK-shaped offline adversarial NAT tests. No clients, credentials or network."""
import base64
import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("nat_recovery", ROOT / "infra/modules/nat-egress/lambda/recovery.py")
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)
NOW = 1800000000
BOOT = b"reviewed bootstrap\n"


def fixture():
    slots = []
    for index, letter in enumerate("abc", 1):
        az = "us-east-1" + letter
        slots.append(dict(asg="platform-dev-" + az + "-nat-asg", az=az,
            subnet=f"subnet-{index:08x}", eip=f"eipalloc-{index:08x}", table=f"rtb-{index:08x}",
            ami="ami-00000001", instance_type="t3.micro", profile="arn:aws:iam::341936017254:instance-profile/nat-" + letter,
            sg=f"sg-{index:08x}", lt=f"lt-{index:08x}", version=1,
            user_data_sha256=n.digest(BOOT), predecessor_enis=[]))
    return dict(schema=1, account="341936017254", region="us-east-1", project="platform", environment="dev", vpc="vpc-00000001", slots=slots)


class Dynamo:
    def __init__(self, config):
        self.items = {"CONTROL": {"data": {"S": n.canonical({"enabled": True, "generation": n.configuration(config)})}}}
        self.writes = []
        self.fault = None
        self.interfere = None

    def get_item(self, **args):
        assert args["ConsistentRead"] is True
        item = self.items.get(args["Key"]["pk"]["S"])
        return {"Item": copy.deepcopy(item)} if item else {}

    def put_item(self, **args):
        key = args["Item"]["pk"]["S"]
        value = json.loads(args["Item"]["data"]["S"])
        if self.interfere:
            callback, self.interfere = self.interfere, None
            callback(self, key, value)
        old = self.items.get(key)
        if args["ConditionExpression"] == "attribute_not_exists(pk)":
            if old:
                raise RuntimeError("CONDITIONAL_CONFLICT")
        elif not old or old["revision"] != args["ExpressionAttributeValues"][":prior"]:
            raise RuntimeError("CONDITIONAL_CONFLICT")
        phase = value.get("pending") or {}
        fault = self.fault and phase == {"step": self.fault[0], "phase": "ACK"}
        if fault and self.fault[1] == "before":
            self.fault = None
            raise OSError("LOST_JOURNAL_ACK")
        self.items[key] = copy.deepcopy(args["Item"])
        self.writes.append(value)
        if fault:
            self.fault = None
            raise OSError("LOST_JOURNAL_RESPONSE")

    def inhibit(self):
        control = json.loads(self.items["CONTROL"]["data"]["S"])
        control["enabled"] = False
        self.items["CONTROL"]["data"]["S"] = n.canonical(control)


class Cloud:
    def __init__(self, config):
        self.config = config
        self.groups, self.instances, self.enis, self.addresses, self.tables, self.templates = {}, {}, {}, {}, {}, {}
        self.calls, self.mutation_fault, self.after_effect = [], None, None
        self.console_mode = "good"
        self.clock = NOW
        self.readiness_calls = 0
        for index, slot in enumerate(config["slots"], 1):
            self.install(slot, index)
            common = [{"Key": "Project", "Value": config["project"]}, {"Key": "Environment", "Value": config["environment"]}]
            self.addresses[slot["eip"]] = dict(AllocationId=slot["eip"], Tags=common)
            self.tables[slot["table"]] = dict(RouteTableId=slot["table"], VpcId=config["vpc"], Tags=common,
                Routes=[{"DestinationCidrBlock": "10.0.0.0/16", "GatewayId": "local"}])

    def install(self, slot, index):
        identity, eni = f"i-{index:08x}", f"eni-{index:08x}"
        tag_map = dict(Project=self.config["project"], Environment=self.config["environment"], Role="nat", NatSlot=slot["az"])
        eni_tags = [{"Key": k, "Value": v} for k, v in tag_map.items()]
        instance_tags = [*eni_tags, {"Key": "aws:autoscaling:groupName", "Value": slot["asg"]}]
        self.groups[slot["asg"]] = dict(AutoScalingGroupName=slot["asg"], MinSize=1, MaxSize=1, DesiredCapacity=1,
            VPCZoneIdentifier=slot["subnet"], SuspendedProcesses=[], Instances=[dict(InstanceId=identity,
                LifecycleState="InService", HealthStatus="Healthy", LaunchTemplate={"LaunchTemplateId": slot["lt"], "LaunchTemplateName": "sdk-extra-name", "Version": "1"})])
        self.instances[identity] = dict(InstanceId=identity, State={"Name": "running"}, VpcId=self.config["vpc"],
            SubnetId=slot["subnet"], Placement={"AvailabilityZone": slot["az"]}, ImageId=slot["ami"], InstanceType=slot["instance_type"],
            IamInstanceProfile={"Arn": slot["profile"]}, MetadataOptions={"HttpTokens": "required"}, Tags=instance_tags,
            SecurityGroups=[{"GroupId": slot["sg"]}], NetworkInterfaces=[{"NetworkInterfaceId": eni}],
            LaunchTime=datetime.fromtimestamp(NOW - 30, timezone.utc), sdc=True)
        self.enis[eni] = dict(NetworkInterfaceId=eni, VpcId=self.config["vpc"], SubnetId=slot["subnet"],
            AvailabilityZone=slot["az"], Attachment={"InstanceId": identity, "DeleteOnTermination": True}, TagSet=eni_tags)
        self.templates[slot["lt"]] = dict(VersionNumber=1, LaunchTemplateData=dict(ImageId=slot["ami"], InstanceType=slot["instance_type"],
            MetadataOptions={"HttpTokens": "required"}, IamInstanceProfile={"Arn": slot["profile"]}, UserData=base64.b64encode(BOOT).decode(),
            NetworkInterfaces=[dict(AssociatePublicIpAddress=True, DeleteOnTermination=True, Groups=[slot["sg"]])]))

    def event(self, index=0, instance=None):
        slot = self.config["slots"][index]
        return dict(id="11111111-1111-4111-8111-111111111111", source="aws.autoscaling",
            **{"detail-type": "EC2 Instance Launch Successful"}, account=self.config["account"], region=self.config["region"],
            time=datetime.fromtimestamp(self.clock, timezone.utc).isoformat(),
            detail=dict(AutoScalingGroupName=slot["asg"], EC2InstanceId=instance or self.groups[slot["asg"]]["Instances"][0]["InstanceId"]))

    def pause(self, seconds):
        self.clock += seconds

    def describe_auto_scaling_groups(self, AutoScalingGroupNames):
        return {"AutoScalingGroups": [copy.deepcopy(self.groups[name]) for name in AutoScalingGroupNames]}

    def describe_instances(self, InstanceIds):
        return {"Reservations": [{"Instances": [copy.deepcopy(self.instances[i]) for i in InstanceIds]}]}

    def describe_network_interfaces(self, NetworkInterfaceIds):
        return {"NetworkInterfaces": [copy.deepcopy(self.enis[i]) for i in NetworkInterfaceIds]}

    def describe_launch_template_versions(self, LaunchTemplateId, Versions):
        return {"LaunchTemplateVersions": [copy.deepcopy(self.templates[LaunchTemplateId])]}

    def describe_instance_status(self, InstanceIds, IncludeAllInstances):
        assert IncludeAllInstances is True
        return {"InstanceStatuses": [{"InstanceId": i, "InstanceStatus": {"Status": "ok"}, "SystemStatus": {"Status": "ok"}} for i in InstanceIds]}

    def get_console_output(self, InstanceId, Latest):
        self.readiness_calls += 1
        marker = f"CNP_NAT_BOOTSTRAP_V1 {InstanceId} {NOW - 2} CONFIGURED\n"
        text = {"good": marker, "missing": "running\n", "foreign": marker.replace(InstanceId, "i-ffffffff"),
            "duplicate": marker + marker, "failed": marker + "CNP_NAT_BOOTSTRAP_FAILED\n", "future": marker.replace(str(NOW - 2), str(NOW + 100))}[self.console_mode]
        return dict(InstanceId=InstanceId, Output=text, Timestamp=datetime.fromtimestamp(NOW - 1, timezone.utc))

    def describe_instance_attribute(self, InstanceId, Attribute):
        if Attribute == "userData":
            return dict(InstanceId=InstanceId, UserData={"Value": base64.b64encode(BOOT).decode()})
        return dict(InstanceId=InstanceId, SourceDestCheck={"Value": self.instances[InstanceId]["sdc"]})

    def describe_addresses(self, AllocationIds):
        return {"Addresses": [copy.deepcopy(self.addresses[i]) for i in AllocationIds]}

    def describe_route_tables(self, RouteTableIds):
        return {"RouteTables": [copy.deepcopy(self.tables[i]) for i in RouteTableIds]}

    def effect(self, step, args, apply):
        self.calls.append((step, args))
        fault = self.mutation_fault and self.mutation_fault[0] == step
        if fault and self.mutation_fault[1] == "before":
            self.mutation_fault = None
            raise OSError("TRANSPORT_UNKNOWN_BEFORE_EFFECT")
        apply()
        if self.after_effect:
            callback, self.after_effect = self.after_effect, None
            callback(self, step)
        if fault:
            self.mutation_fault = None
            raise OSError("TRANSPORT_UNKNOWN_AFTER_EFFECT")
        return {}

    def modify_instance_attribute(self, **args):
        return self.effect("sdc", args, lambda: self.instances[args["InstanceId"]].update(sdc=False))

    def associate_address(self, **args):
        assert args["AllowReassociation"] is True
        return self.effect("eip", args, lambda: self.addresses[args["AllocationId"]].update(NetworkInterfaceId=args["NetworkInterfaceId"]))

    def create_route(self, **args):
        return self.effect("route", args, lambda: self.tables[args["RouteTableId"]]["Routes"].append(dict(DestinationCidrBlock="0.0.0.0/0", NetworkInterfaceId=args["NetworkInterfaceId"], State="active")))

    def replace_route(self, **args):
        def replace():
            routes = self.tables[args["RouteTableId"]]["Routes"]
            routes[:] = [r for r in routes if r.get("DestinationCidrBlock") != "0.0.0.0/0"]
            routes.append(dict(DestinationCidrBlock="0.0.0.0/0", NetworkInterfaceId=args["NetworkInterfaceId"], State="active"))
        return self.effect("route", args, replace)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.config = fixture()
        self.cloud, self.store = Cloud(self.config), Dynamo(self.config)
        self.journal = n.Journal(self.store, "journal")
        self.runtime = n.Recovery(self.config, self.cloud, self.cloud, self.journal, clock=lambda: self.cloud.clock, sleep=self.cloud.pause)

    def run_recovery(self, index=0, event=None):
        return self.runtime.run(event or self.cloud.event(index))

    def test_all_three_slots_and_no_live_proof_claim(self):
        for index in range(3):
            self.assertEqual("UNVERIFIED_LIVE_PROOF_REQUIRED", self.run_recovery(index)["private_subnet_egress"])
        self.assertEqual(["sdc", "eip", "route"] * 3, [step for step, _ in self.cloud.calls])
        self.assertEqual(3, len([k for k in self.store.items if k.startswith("SLOT#")]))

    def test_duplicate_and_different_event_id_are_effect_idempotent(self):
        self.run_recovery()
        writes = len(self.store.writes)
        self.run_recovery()
        event = self.cloud.event(); event["id"] = "22222222-2222-4222-8222-222222222222"
        self.run_recovery(event=event)
        self.assertEqual(3, len(self.cloud.calls))
        self.assertEqual(writes, len(self.store.writes))

    def test_new_member_uses_prior_verified_eni_and_old_event_is_rejected(self):
        old = self.cloud.event()
        self.run_recovery()
        self.cloud.install(self.config["slots"][0], 17)
        with self.assertRaises(n.Rejected): self.run_recovery(event=old)
        self.run_recovery()
        self.assertEqual(6, len(self.cloud.calls))
        self.assertEqual("eni-00000011", self.cloud.addresses["eipalloc-00000001"]["NetworkInterfaceId"])

    def test_old_event_after_new_ready_never_moves_network_back(self):
        old = self.cloud.event(); self.run_recovery()
        self.cloud.install(self.config["slots"][0], 17); self.run_recovery()
        with self.assertRaises(n.Rejected): self.run_recovery(event=old)
        self.assertEqual(6, len(self.cloud.calls))

    def test_unacknowledged_effects_before_and_after_each_step_never_replay(self):
        for step in n.STEPS:
            for timing in ("before", "after"):
                with self.subTest(step=step, timing=timing):
                    self.setUp(); self.cloud.mutation_fault = (step, timing)
                    with self.assertRaises(OSError): self.run_recovery()
                    count = len(self.cloud.calls)
                    with self.assertRaisesRegex(n.Rejected, "UNCERTAIN_EFFECT"): self.run_recovery()
                    self.assertEqual(count, len(self.cloud.calls))

    def test_lost_ack_journal_response_reconciles_without_reissuing_effect(self):
        for step in n.STEPS:
            with self.subTest(step=step):
                self.setUp(); self.store.fault = (step, "after")
                with self.assertRaises(OSError): self.run_recovery()
                self.run_recovery()
                self.assertEqual(3, len(self.cloud.calls))

    def test_missing_ack_record_blocks_even_when_network_readback_matches(self):
        for step in n.STEPS:
            with self.subTest(step=step):
                self.setUp(); self.store.fault = (step, "before")
                with self.assertRaises(OSError): self.run_recovery()
                count = len(self.cloud.calls)
                with self.assertRaisesRegex(n.Rejected, "UNCERTAIN_EFFECT"): self.run_recovery()
                self.assertEqual(count, len(self.cloud.calls))

    def test_pending_old_member_blocks_replacement(self):
        self.cloud.mutation_fault = ("eip", "after")
        with self.assertRaises(OSError): self.run_recovery()
        self.cloud.install(self.config["slots"][0], 17)
        with self.assertRaisesRegex(n.Rejected, "UNSETTLED_PREVIOUS_MEMBER"): self.run_recovery()
        self.assertEqual(2, len(self.cloud.calls))

    def test_new_member_after_ack_blocks_further_old_member_effects(self):
        for selected in n.STEPS:
            with self.subTest(step=selected):
                self.setUp()
                original = self.cloud.effect
                def effect(step, args, apply):
                    value = original(step, args, apply)
                    if step == selected: self.cloud.install(self.config["slots"][0], 17)
                    return value
                self.cloud.effect = effect
                with self.assertRaises(n.Rejected): self.run_recovery()
                self.assertEqual(list(n.STEPS[:n.STEPS.index(selected) + 1]), [v[0] for v in self.cloud.calls])
                with self.assertRaisesRegex(n.Rejected, "UNSETTLED_PREVIOUS_MEMBER"): self.run_recovery()

    def test_ack_without_observed_effect_is_read_only_until_settled(self):
        original = self.cloud.associate_address
        def delayed(**args):
            response = original(**args)
            self.cloud.addresses[args["AllocationId"]].pop("NetworkInterfaceId")
            return response
        self.cloud.associate_address = delayed
        with self.assertRaisesRegex(n.Rejected, "ACK_READBACK_NOT_OBSERVED"): self.run_recovery()
        with self.assertRaisesRegex(n.Rejected, "ACK_READBACK_NOT_OBSERVED"): self.run_recovery()
        self.assertEqual(["sdc", "eip"], [v[0] for v in self.cloud.calls])
        self.cloud.addresses["eipalloc-00000001"]["NetworkInterfaceId"] = "eni-00000001"
        self.run_recovery()
        self.assertEqual(["sdc", "eip", "route"], [v[0] for v in self.cloud.calls])

    def test_inhibition_before_dispatch_has_zero_effects(self):
        self.store.inhibit()
        with self.assertRaisesRegex(n.Rejected, "INHIBITED"): self.run_recovery()
        self.assertEqual([], self.cloud.calls)

    def test_inhibition_between_intent_and_effect_is_fenced(self):
        original = self.store.put_item
        def put(**args):
            result = original(**args)
            if json.loads(args["Item"]["data"]["S"]).get("pending") == {"step": "sdc", "phase": "ATTEMPT"}: self.store.inhibit()
            return result
        self.store.put_item = put
        with self.assertRaisesRegex(n.Rejected, "INHIBITED"): self.run_recovery()
        self.assertEqual([], self.cloud.calls)

    def test_conditional_race_before_admission_has_no_effect(self):
        def conflict(store, key, value):
            store.items[key] = {"revision": {"N": "999"}, "data": {"S": "{}"}}
        self.store.interfere = conflict
        with self.assertRaisesRegex(RuntimeError, "CONDITIONAL_CONFLICT"): self.run_recovery()
        self.assertEqual([], self.cloud.calls)

    def test_bad_or_missing_bootstrap_is_bounded_and_has_zero_effects(self):
        for mode in ("missing", "foreign", "duplicate", "failed", "future"):
            with self.subTest(mode=mode):
                self.setUp(); self.cloud.console_mode = mode
                with self.assertRaises(n.Rejected): self.run_recovery()
                self.assertLessEqual(self.cloud.readiness_calls, 12)
                self.assertEqual([], self.cloud.calls)

    def test_readiness_retry_rechecks_membership(self):
        self.cloud.console_mode = "missing"
        def replace(seconds): self.cloud.install(self.config["slots"][0], 17)
        self.runtime.sleep = replace
        with self.assertRaises(n.Rejected): self.run_recovery()
        self.assertEqual([], self.cloud.calls)

    def test_unready_duplicate_does_not_poison_a_healthy_retry_or_replacement(self):
        for replace in (False, True):
            with self.subTest(replace=replace):
                self.setUp()
                self.run_recovery()
                ready = copy.deepcopy(self.store.items)
                self.cloud.install(self.config["slots"][0], 17)
                event = self.cloud.event()
                self.cloud.console_mode = "missing"
                with self.assertRaises(n.Rejected): self.run_recovery(event=event)
                self.assertEqual(ready, self.store.items)
                if replace:
                    self.cloud.install(self.config["slots"][0], 33)
                    event = self.cloud.event()
                self.cloud.console_mode = "good"
                self.assertEqual("CONFIGURED_NETWORK_READBACK", self.run_recovery(event=event)["status"])
                self.assertEqual(6, len(self.cloud.calls))

    def test_another_slot_is_foreign_despite_matching_project_tags(self):
        for target in ("eip", "route"):
            with self.subTest(target=target):
                self.setUp()
                if target == "eip":
                    self.cloud.addresses["eipalloc-00000001"]["NetworkInterfaceId"] = "eni-00000002"
                else:
                    self.cloud.tables["rtb-00000001"]["Routes"].append(dict(DestinationCidrBlock="0.0.0.0/0", NetworkInterfaceId="eni-00000002", State="active"))
                before = copy.deepcopy((self.cloud.addresses, self.cloud.tables))
                with self.assertRaises(n.Rejected): self.run_recovery()
                self.assertEqual([], self.cloud.calls)
                self.assertEqual(before, (self.cloud.addresses, self.cloud.tables))

    def test_foreign_network_objects_have_zero_effects(self):
        for kind in ("eip", "route", "table_vpc", "tags"):
            with self.subTest(kind=kind):
                self.setUp()
                if kind == "eip": self.cloud.addresses["eipalloc-00000001"]["NetworkInterfaceId"] = "eni-ffffffff"
                if kind == "route": self.cloud.tables["rtb-00000001"]["Routes"].append(dict(DestinationCidrBlock="0.0.0.0/0", GatewayId="igw-ffffffff"))
                if kind == "table_vpc": self.cloud.tables["rtb-00000001"]["VpcId"] = "vpc-ffffffff"
                if kind == "tags": self.cloud.addresses["eipalloc-00000001"]["Tags"] = []
                with self.assertRaises(n.Rejected): self.run_recovery()
                self.assertEqual([], self.cloud.calls)

    def test_foreign_launch_identity_has_zero_effects(self):
        for field in ("ImageId", "InstanceType", "VpcId", "SubnetId", "profile", "sg", "az", "eni_attachment", "userdata"):
            with self.subTest(field=field):
                self.setUp(); i = self.cloud.instances["i-00000001"]
                if field in i: i[field] = "foreign"
                elif field == "profile": i["IamInstanceProfile"]["Arn"] = "foreign"
                elif field == "sg": i["SecurityGroups"] = [{"GroupId": "sg-ffffffff"}]
                elif field == "az": i["Placement"]["AvailabilityZone"] = "us-east-1b"
                elif field == "eni_attachment": self.cloud.enis["eni-00000001"]["Attachment"]["InstanceId"] = "i-ffffffff"
                else: self.cloud.templates["lt-00000001"]["LaunchTemplateData"]["UserData"] = base64.b64encode(b"unreviewed").decode()
                with self.assertRaises(n.Rejected): self.run_recovery()
                self.assertEqual([], self.cloud.calls)

    def test_wrong_stale_and_future_events_never_mutate(self):
        for field in ("source", "account", "region", "id", "past", "future", "asg", "instance"):
            with self.subTest(field=field):
                self.setUp(); event = self.cloud.event()
                if field in event: event[field] = "foreign"
                elif field in ("past", "future"): event["time"] = datetime.fromtimestamp(NOW + (-1801 if field == "past" else 61), timezone.utc).isoformat()
                elif field == "asg": event["detail"]["AutoScalingGroupName"] = "foreign"
                else: event["detail"]["EC2InstanceId"] = "i-ffffffff"
                with self.assertRaises(n.Rejected): self.run_recovery(event=event)
                self.assertEqual([], self.cloud.calls)

    def test_migration_requires_exact_approved_predecessor(self):
        self.cloud.tables["rtb-00000001"]["Routes"].append(dict(DestinationCidrBlock="0.0.0.0/0", NetworkInterfaceId="eni-ffffffff", State="blackhole"))
        with self.assertRaises(n.Rejected): self.run_recovery()
        self.config["slots"][0]["predecessor_enis"] = ["eni-ffffffff"]
        self.store = Dynamo(self.config); self.runtime.journal = n.Journal(self.store, "journal")
        self.runtime.generation = n.configuration(self.config)
        self.run_recovery()
        self.assertEqual(2, len(self.cloud.tables["rtb-00000001"]["Routes"]))

    def test_capacity_and_execution_budget_block_effects(self):
        self.cloud.groups[self.config["slots"][0]["asg"]]["MaxSize"] = 2
        with self.assertRaises(n.Rejected): self.run_recovery()
        self.cloud.groups[self.config["slots"][0]["asg"]]["MaxSize"] = 1
        self.runtime.remaining = lambda: 35000
        with self.assertRaises(n.Rejected): self.run_recovery()
        self.assertEqual([], self.cloud.calls)

    def test_changed_config_cannot_reset_existing_journal(self):
        self.run_recovery()
        self.config["slots"][0]["predecessor_enis"] = ["eni-ffffffff"]
        self.runtime.generation = n.configuration(self.config)
        self.store.items["CONTROL"]["data"]["S"] = n.canonical(dict(enabled=True, generation=self.runtime.generation))
        with self.assertRaisesRegex(n.Rejected, "JOURNAL_GENERATION"): self.run_recovery()
        self.assertEqual(3, len(self.cloud.calls))

    def test_three_slots_are_not_two_or_four_slot_assumptions(self):
        for count in (1, 2, 3): n.configuration({**self.config, "slots": self.config["slots"][:count]})
        with self.assertRaises(n.Rejected): n.configuration({**self.config, "slots": self.config["slots"] * 2})
        bad = copy.deepcopy(self.config); bad["slots"][1]["table"] = bad["slots"][0]["table"]
        with self.assertRaises(n.Rejected): n.configuration(bad)


if __name__ == "__main__": unittest.main()
