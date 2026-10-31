# API Gateway JWT Authorizer

This Lambda closes the platform trust boundary for the HTTP API edge.

It is used by API Gateway as a `REQUEST` authorizer for protected routes and validates the HMAC-signed JWTs issued by `auth-service`.

## Environment Variables

- `JWT_ISSUER`
- `JWT_AUDIENCE`
- `AUTH_SERVICE_JWT_SECRET_ID`
- `PLATFORM_TRUSTED_PROXY_SECRET_ID`
- `SECRET_CACHE_TTL_SECONDS`

## Behavior

- validates `Authorization: Bearer <token>`
- enforces `HS256`, issuer, audience, signature, `nbf`, and `exp`
- returns simple authorizer context for API Gateway request parameter mapping
- injects a shared proxy secret into the authorizer context so backend services can trust only API-Gateway-verified identity headers
- retrieves secret values from AWS Secrets Manager at runtime
- caches resolved secret values in memory for the configured TTL

## Deployment

This Lambda is packaged and deployed through Terragrunt:

- `infra/live/dev/api-gateway-authorizer/terragrunt.hcl`

The Lambda environment contains only Secrets Manager secret IDs or ARNs, not raw secret values. Secret values are populated outside Terraform and resolved by the Lambda execution role with scoped `secretsmanager:GetSecretValue` permissions.
