# Repository guidance

- Treat source as authoritative. Documentation is in English; start with `docs/README.md` only when context is needed.
- Keep changes scoped. Preserve the Terraform/Helm/controller ownership boundaries and immutable image/artifact contracts.
- Use .NET SDK from `global.json`, pinned provider/chart locks and the tool versions in the validation workflow.
- For documentation: check links/anchors, Mermaid, current-tree secrets and `git diff --check`; do not run expensive app builds solely for prose edits.
- For code: run focused validators/tests appropriate to the change. The full local gate is documented in `docs/development.md`; PostgreSQL-dependent skips must remain explicit.
- Local edits, static validation and fake-adapter tests do not authorize AWS operations. Deployment, backend bootstrap, S3 export and mutating teardown require explicit task authorization.
- Keep credentials, secret payloads, state, binary plans, kubeconfig and original private evidence outside Git. Report secret findings by location without values.
- Preserve teardown identity/approval/journal/transit guards. Never bypass them with finalizer removal, force-unlock, forged approvals or edited checkpoint hashes.
- The lab is offline after final teardown. Do not reactivate delivery, change repository visibility or push unless the task explicitly authorizes it.
