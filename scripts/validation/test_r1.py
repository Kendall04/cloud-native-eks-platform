"""Negative tests mutate real rendered/parsed inputs, never repository files."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import os
import unittest

import hcl2
from validate_r1 import ROOT, render, validate_edge, validate_runtime


class RegressionDetectors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = render(os.environ.get("HELM_BIN", "helm"), ROOT / "k8s/environments/dev/platform-services.values.yaml")
        with (ROOT / "infra/live/dev/apigateway-integration/terragrunt.hcl").open() as file:
            cls.inputs = hcl2.load(file)["inputs"]
        with (ROOT / "infra/modules/apigateway-integration/main.tf").open() as file:
            cls.module = hcl2.load(file)

    def test_original_selector_collision_is_rejected(self):
        for kind in ("Service", "PodDisruptionBudget"):
            with self.subTest(kind=kind):
                documents = deepcopy(self.documents)
                job = next(d for d in documents if d and d["kind"] == "Job")
                name = job["metadata"]["name"].removesuffix("-migrate")
                job["spec"]["template"]["metadata"]["labels"]["app.kubernetes.io/name"] = name
                obj = next(d for d in documents if d and d["kind"] == kind and d["metadata"]["name"].startswith(name))
                selector = obj["spec"]["selector"] if kind == "Service" else obj["spec"]["selector"]["matchLabels"]
                selector.pop("platform.cloud-native.io/workload")
                with redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                    validate_runtime(documents)

    def test_database_liveness_regression_is_rejected(self):
        documents = deepcopy(self.documents)
        deployment = next(d for d in documents if d and d["kind"] == "Deployment")
        deployment["spec"]["template"]["spec"]["containers"][0]["livenessProbe"]["httpGet"]["path"] = "/health/ready"
        with redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            validate_runtime(documents)

    def test_alb_liveness_regression_is_rejected(self):
        documents = deepcopy(self.documents)
        ingress = next(d for d in documents if d and d["kind"] == "Ingress")
        ingress["metadata"]["annotations"]["alb.ingress.kubernetes.io/healthcheck-path"] = "/health/live"
        with redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            validate_runtime(documents)

    def test_unsafe_edge_routes_are_rejected(self):
        for route in ("ANY /tracking/{proxy+}", "GET /swagger", "GET /internal/shipments/{id}"):
            with self.subTest(route=route):
                inputs = deepcopy(self.inputs)
                inputs["protected_route_keys"].append(route)
                with self.assertRaises(ValueError):
                    validate_edge(inputs, self.module)

    def test_public_admin_regression_is_rejected(self):
        inputs = deepcopy(self.inputs)
        inputs["protected_route_keys"].remove("POST /admin/tracking-events")
        inputs["public_route_keys"].append("POST /admin/tracking-events")
        with self.assertRaises(ValueError):
            validate_edge(inputs, self.module)

    def test_missing_authorizer_is_rejected(self):
        module = deepcopy(self.module)
        for resource in module["resource"]:
            if "aws_apigatewayv2_route" in resource:
                resource["aws_apigatewayv2_route"]["this"]["authorization_type"] = "NONE"
        with self.assertRaises(ValueError):
            validate_edge(self.inputs, module)


if __name__ == "__main__":
    unittest.main()
