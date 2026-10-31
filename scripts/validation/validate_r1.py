"""Local R1 contracts: real Helm rendering and parsed HCL; no AWS access."""
import argparse
from pathlib import Path
import re
import subprocess

import hcl2
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "k8s/charts/platform-services"
PUBLIC = {"POST /auth/login", "POST /auth/register", "POST /auth/refresh"}
PROTECTED = {
    "GET /auth/me", "GET /auth/validate", "POST /shipments", "GET /shipments",
    "GET /shipments/by-id/{id}", "GET /shipments/by-tracking/{trackingNumber}",
    "GET /tracking/by-shipment/{shipmentId}",
    "GET /tracking/by-tracking-number/{trackingNumber}", "POST /admin/tracking-events",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def selects(selector, labels):
    return all(labels.get(key) == value for key, value in selector.items())


def validate_runtime(documents):
    objects = {(d["kind"], d["metadata"]["name"]): d for d in documents if d}
    jobs = [d["spec"]["template"]["metadata"]["labels"] for d in documents if d and d["kind"] == "Job"]
    for name in ("auth-service", "shipment-service", "tracking-service"):
        deployment = objects["Deployment", name]
        pod = deployment["spec"]["template"]
        labels = pod["metadata"]["labels"]
        service = objects["Service", name]
        selectors = {
            "Service": service["spec"]["selector"],
            "PDB": objects["PodDisruptionBudget", name + "-pdb"]["spec"]["selector"]["matchLabels"],
            "Deployment": deployment["spec"]["selector"]["matchLabels"],
        }
        migration = objects["Job", name + "-migrate"]["spec"]["template"]["metadata"]["labels"]
        require(labels.get("platform.cloud-native.io/workload") == "runtime", name + " runtime label missing")
        require(migration.get("platform.cloud-native.io/workload") == "migration", name + " migration label missing")
        for kind, selector in selectors.items():
            require(bool(selector) and selects(selector, labels), f"{name}: {kind} must select runtime")
            require(not any(selects(selector, job) for job in jobs), f"{name}: {kind} selects a migration Job")
        container = pod["spec"]["containers"][0]
        for probe, path in (("startupProbe", "/health/live"), ("livenessProbe", "/health/live"), ("readinessProbe", "/health/ready")):
            require(container[probe]["httpGet"] == {"path": path, "port": "http"}, f"{name}: invalid {probe}")
        require(service["spec"]["ports"][0]["targetPort"] == "http", name + " targetPort mismatch")
        require(container["ports"][0]["name"] == "http", name + " container port mismatch")
        checksum = pod["metadata"]["annotations"]["checksum/config"]
        require(re.fullmatch(r"[0-9a-f]{64}", checksum) is not None, name + " config checksum missing")
        print(f"{name}: selectors={selectors}; runtime={labels}; migration={migration}; probes/config PASS")
    ingress = objects["Ingress", "platform-services"]
    annotations = ingress["metadata"]["annotations"]
    for key, value in {"healthcheck-path": "/health/ready", "healthcheck-port": "traffic-port", "healthcheck-protocol": "HTTP", "backend-protocol": "HTTP", "success-codes": "200", "target-type": "ip"}.items():
        require(str(annotations.get("alb.ingress.kubernetes.io/" + key)) == value, "ALB " + key + " mismatch")
    for rule in ingress["spec"]["rules"]:
        for path in rule["http"]["paths"]:
            backend = path["backend"]["service"]
            require(backend["port"]["number"] == objects["Service", backend["name"]]["spec"]["ports"][0]["port"], "Ingress Service port mismatch")


def validate_edge(inputs, module):
    require(set(inputs["public_route_keys"]) == PUBLIC, "Unexpected public routes")
    require(set(inputs["protected_route_keys"]) == PROTECTED, "Unexpected protected/admin routes")
    resources = {(kind, name): value for block in module["resource"] for kind, named in block.items() for name, value in named.items()}
    route = resources["aws_apigatewayv2_route", "this"]
    require(route["authorization_type"] == '${each.value == "protected" ? "CUSTOM" : "NONE"}', "Protected routes lost CUSTOM authorization")
    require(route["authorizer_id"] == '${each.value == "protected" ? var.authorizer_id : null}', "Protected routes lost authorizer")
    require(route["for_each"] == '${var.enabled ? local.routes : {}}', "Unexpected route source")
    locals_ = module["locals"][0]
    require('var.public_route_keys' in locals_["public_routes"] and '=> "public"' in locals_["public_routes"], "Public route classification changed")
    require('var.protected_route_keys' in locals_["protected_routes"] and '=> "protected"' in locals_["protected_routes"], "Protected route classification changed")
    require(locals_["routes"] == '${merge(local.public_routes, local.protected_routes)}', "Route merge changed")
    for header, claim in (("User-Id", "userId"), ("Email", "email"), ("Roles", "roles"), ("Proxy-Secret", "proxySecret")):
        require(locals_["protected_request_parameters"].get("overwrite:header.X-Platform-" + header) == "$context.authorizer." + claim, "Trusted header mapping changed: " + header)
    require(resources["aws_apigatewayv2_integration", "protected"]["request_parameters"] == "${local.protected_request_parameters}", "Protected integration lost identity context")
    # Real route matching (single path parameter), including authenticated Swagger paths.
    for path in ("/swagger", "/swagger/index.html", "/auth/swagger", "/shipments/swagger", "/tracking/swagger", "/tracking/swagger/v1/swagger.json", "/internal/shipments/123", "/health/ready"):
        for route_key in PUBLIC | PROTECTED:
            pattern = re.sub(r"\{[^}]+\}", "[^/]+", route_key.split(" ", 1)[1])
            require(re.fullmatch(pattern, path) is None, "Edge exposes " + path)
    print("Edge routes, authorization and trusted header overwrite: PASS")


def render(helm, overlay, extra=()):
    args = [helm, "template", "platform-services", str(CHART)]
    if overlay:
        args += ["-f", str(overlay)]
    # R2: identifiers now come from generated overlays. Tests use a named fixture.
    args += ["-f", str(ROOT / "scripts/validation/fixtures/helm-infra.values.yaml")]
    result = subprocess.run(args + list(extra), check=True, capture_output=True, text=True)
    return list(yaml.safe_load_all(result.stdout))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--helm", default="helm")
    args = parser.parse_args()
    for overlay in (None, ROOT / "k8s/environments/dev/platform-services.values.yaml", ROOT / "k8s/environments/prod/platform-services.values.yaml"):
        print("Validating:", overlay or "chart defaults with test images")
        documents = render(args.helm, overlay)
        validate_runtime(documents)
        changed = render(args.helm, overlay, ["--set-string", "services.auth.env.R1_ROLLOUT_TEST=changed"])
        def checksum(items):
            return next(d for d in items if d and d["kind"] == "Deployment" and d["metadata"]["name"] == "auth-service")["spec"]["template"]["metadata"]["annotations"]["checksum/config"]
        require(checksum(documents) != checksum(changed), "Config change did not change pod template")
    with (ROOT / "infra/live/dev/apigateway-integration/terragrunt.hcl").open() as file:
        inputs = hcl2.load(file)["inputs"]
    with (ROOT / "infra/modules/apigateway-integration/main.tf").open() as file:
        module = hcl2.load(file)
    validate_edge(inputs, module)
    # Reject extra route resources bypassing the reviewed integration contract.
    for directory in ("infra/modules/apigateway-core", "infra/modules/apigateway-integration"):
        for file in (ROOT / directory).glob("*.tf"):
            with file.open() as stream:
                for block in hcl2.load(stream).get("resource", []):
                    for name in block.get("aws_apigatewayv2_route", {}):
                        require(directory.endswith("apigateway-integration") and name == "this", "Unreviewed edge route: " + name)
    print("R1 validation PASS")


if __name__ == "__main__":
    main()
