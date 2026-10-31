# AWS infrastructure

Reusable modules live in `modules/`; the 18 dev stacks live in `live/dev/`. The backend is separate from runtime infrastructure. Provider locks are versioned; state and caches are ignored.

- [Stack dependencies and configuration](../docs/architecture/infrastructure.md)
- [Phased deployment](../docs/operations/deployment.md)
- [Lab cleanup and residual verification](../docs/operations/lab-cleanup.md)

`operator-policies/` contains reviewed account-specific references; retired IDs must be rebound for a new deployment. The lab is currently offline.
