"""Local deployment-boundary checks; parsed HCL and deterministic package only."""
import ast
import copy
import io
from pathlib import Path
import re
import unittest
import zipfile
import hcl2
from package_nat_recovery import package

ROOT = Path(__file__).resolve().parents[2]


def source():
    modules = {}
    for name in ("nat", "nat-egress"):
        resources, variables = {}, {}
        for path in (ROOT / "infra/modules" / name).glob("*.tf"):
            value = hcl2.loads(path.read_text(encoding="utf-8"))
            for block in value.get("resource", []):
                for kind, named in block.items():
                    for key, definition in named.items():
                        resources[kind, key] = definition
            for block in value.get("variable", []): variables.update(block)
        modules[name] = (resources, variables)
    return modules


def validate(modules):
    child, _ = modules["nat"]
    root, variables = modules["nat-egress"]
    assert not any(kind in ("aws_instance", "aws_eip_association", "aws_route") for kind, _ in child), "competing static writer"
    assert child["aws_launch_template", "nat"]["credit_specification"][0]["cpu_credits"] == "standard", "no unbounded CPU-credit charge"
    assert variables["recovery_enabled"]["default"] is False, "admission must default off"
    group = root["aws_autoscaling_group", "nat"]
    assert group["for_each"] == "${local.nat_instances}"
    for key in ("min_size", "max_size", "desired_capacity"):
        assert group[key] == "${var.recovery_enabled ? 1 : 0}", "one instance or inhibited zero only"
    assert group["health_check_type"] == "EC2"
    assert group["instance_maintenance_policy"][0] == {"min_healthy_percentage": 0, "max_healthy_percentage": 100}, "no deliberate surge"
    assert "$Latest" not in str(group) and "$Default" not in str(group), "numeric launch pin required"
    assert "aws_cloudwatch_event_target.recovery" in str(group["depends_on"]), "first event must have a target"
    assert "aws_dynamodb_table_item.control" in str(group["depends_on"]), "first launch must have durable admission"
    assert root["aws_route", "default"]["for_each"] == '${var.nat_mode == "gateway" ? local.route_targets : {}}', "instance routes are controller-owned"
    function = root["aws_lambda_function", "recovery"]
    assert function["handler"] == "recovery.lambda_handler"
    assert function["filename"] == "${local.package_path}"
    assert function["source_code_hash"] == "${filebase64sha256(local.package_path)}"
    assert function["reserved_concurrent_executions"] == "${var.recovery_enabled ? 1 : 0}", "single controller writer"
    assert function["timeout"] == 180
    rule = root["aws_cloudwatch_event_rule", "launch"]
    assert rule["state"] == '${var.recovery_enabled ? "ENABLED" : "DISABLED"}'
    assert "AutoScalingGroupName" in rule["event_pattern"] and "slot.asg" in rule["event_pattern"]
    assert "aws.autoscaling" in rule["event_pattern"] and "EC2 Instance Launch Successful" in rule["event_pattern"]
    assert root["aws_cloudwatch_event_target", "recovery"]["arn"] == "${aws_lambda_function.recovery[0].arn}"
    assert root["aws_lambda_permission", "events"]["source_arn"] == "${aws_cloudwatch_event_rule.launch[0].arn}"
    assert root["aws_lambda_permission", "events"]["function_name"] == "${aws_lambda_function.recovery[0].function_name}"
    assert "aws_lambda_event_source_mapping" not in {kind for kind, _ in root}, "failure evidence has no automatic replay consumer"
    for key in (("aws_dynamodb_table", "recovery"), ("aws_sqs_queue", "failures")):
        assert root[key]["lifecycle"][0]["prevent_destroy"] is True, "retain unresolved evidence"
    policy = root["aws_iam_role_policy", "recovery"]["policy"]
    assert re.search(r'"ec2:Attribute"\s*[:=]\s*"SourceDestCheck"', policy), "only source/destination check may change"
    slot_write = policy.split('"WriteSlotsNeverControl"', 1)[1].split('"OwnLogStreams"', 1)[0]
    assert '"dynamodb:LeadingKeys"' in slot_write and 'SLOT#${slot.asg}' in slot_write and 'CONTROL' not in slot_write, "slot-scoped writes"
    assert '"ec2:Subnet"' in policy and "slot.subnet" in policy, "ENI subnet scope"
    assert "elastic-ip/${slot.eip}" in policy and "route-table/${slot.table}" in policy, "exact network resources"
    for forbidden in ("ssm:SendCommand", "ec2:TerminateInstances", "ec2:RunInstances", "ec2:DeleteRoute", "iam:PassRole", "dynamodb:DeleteItem", "dynamodb:UpdateItem", "sqs:ReceiveMessage", "sqs:DeleteMessage"):
        assert forbidden not in policy, forbidden


class ConfigurationTests(unittest.TestCase):
    def test_deployment_boundaries(self): validate(source())

    def test_iam_actions_cover_exact_implemented_sdk_calls_and_service_destinations(self):
        tree = ast.parse((ROOT / "infra/modules/nat-egress/lambda/recovery.py").read_text())
        implemented = set()
        services = {"self.ec2": "ec2", "self.asg": "autoscaling", "self.client": "dynamodb"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and ast.unparse(node.value) in services:
                action = "".join(word.capitalize() for word in node.attr.split("_"))
                implemented.add(services[ast.unparse(node.value)] + ":" + action)
        policy = source()["nat-egress"][0]["aws_iam_role_policy", "recovery"]["policy"]
        declared = set(re.findall(r'"((?:ec2|autoscaling|dynamodb|logs|sqs):[A-Z][A-Za-z]+)"', policy))
        declared -= {"ec2:Attribute", "ec2:Subnet", "dynamodb:LeadingKeys"}
        self.assertEqual(implemented | {"logs:CreateLogStream", "logs:PutLogEvents", "sqs:SendMessage"}, declared)
        describe = policy.split('"DescribeMembership"', 1)[1].split('"BootstrapReadback"', 1)[0]
        self.assertNotIn("ec2:Modify", describe)
        self.assertNotIn("ec2:Associate", describe)
        self.assertNotIn("ec2:CreateRoute", describe)

    def test_capacity_surge_and_default_activation_regressions_rejected(self):
        for mutation in ("capacity", "surge", "activation", "concurrency"):
            with self.subTest(mutation=mutation):
                modules = source(); resources, variables = modules["nat-egress"]
                if mutation == "capacity": resources["aws_autoscaling_group", "nat"]["max_size"] = 2
                elif mutation == "surge": resources["aws_autoscaling_group", "nat"]["instance_maintenance_policy"][0]["max_healthy_percentage"] = 200
                elif mutation == "activation": variables["recovery_enabled"]["default"] = True
                else: resources["aws_lambda_function", "recovery"]["reserved_concurrent_executions"] = 3
                with self.assertRaises(AssertionError): validate(modules)

    def test_iam_expansion_and_network_writer_regressions_rejected(self):
        for mutation in ("ssm:SendCommand", "ec2:TerminateInstances", "dynamodb:DeleteItem", "attribute", "route_writer"):
            with self.subTest(mutation=mutation):
                modules = source(); resources, _ = modules["nat-egress"]
                if mutation == "route_writer": resources["aws_route", "default"]["for_each"] = "${local.route_targets}"
                else:
                    key = ("aws_iam_role_policy", "recovery")
                    resources[key]["policy"] = resources[key]["policy"].replace("SourceDestCheck", "*") if mutation == "attribute" else resources[key]["policy"] + mutation
                with self.assertRaises(AssertionError): validate(modules)

    def test_package_is_exact_deterministic_source_and_not_legacy_handlers(self):
        directory = ROOT / "infra/modules/nat-egress/lambda"
        data = (directory / "recovery.py").read_bytes()
        expected = package(data)
        lf_data = data.replace(b"\r\n", b"\n")
        self.assertEqual(expected, package(lf_data))
        self.assertEqual(expected, package(lf_data.replace(b"\n", b"\r\n")))
        self.assertEqual(expected, (directory / "recovery.zip").read_bytes())
        with zipfile.ZipFile(io.BytesIO(expected)) as archive:
            self.assertEqual(["recovery.py"], archive.namelist())
            self.assertEqual(data.replace(b"\r\n", b"\n"), archive.read("recovery.py"))
        self.assertNotEqual(expected, package(data + b"\n# changed\n"))

    def test_bootstrap_markers_after_readbacks_and_without_token_tracing(self):
        text = (ROOT / "infra/modules/nat/user_data.sh.tftpl").read_text()
        marker = text.index("printf 'CNP_NAT_BOOTSTRAP_V1")
        self.assertNotIn("set -x", text)
        self.assertNotIn("-eux", text)
        for guard in ("timeout 180 dnf", "sysctl -n net.ipv4.ip_forward", "systemctl is-active --quiet iptables", "iptables -t nat -C", "unset TOKEN"):
            self.assertLess(text.index(guard), marker)
        self.assertIn("CNP_NAT_BOOTSTRAP_FAILED", text)


if __name__ == "__main__": unittest.main()
