# CycloneDX schemas

Official CycloneDX 1.7 JSON schemas, copied from the [`1.7` specification tag](https://github.com/CycloneDX/specification/tree/1.7/schema): `bom-1.7.schema.json`, `spdx.schema.json` and `jsf-0.82.schema.json`. Their Apache-2.0 license is retained in `LICENSE`.

These are validation data, not a generated SBOM. `security.py` resolves their references from a local registry without HTTP retrieval. Update the schemas and tests together only when the pinned Trivy output format changes.
