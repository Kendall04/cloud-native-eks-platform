# Architecture Explorer maintenance

[Frontend](../../frontend/README.md) · [Validation](../development.md)

## Sources and deliverables

The canonical JSON is in `docs/interactive/source/`; standalone HTML is generated into `docs/interactive/`. The five active diagrams are Platform, Networking, Event Processing, Private CD and Security. Lifecycle remains historical source/HTML, not an active catalog entry; preserve its transition route and provenance.

Use **Archify v3.1.0**, installed outside the repository from the [official release](https://github.com/tt-a1i/archify/releases/tag/v3.1.0). The recorded release source is `1c2b42d660e4a7571813fb43839c79e3e9ca7720`; `archify.zip` SHA256 is `ffedc53390c9da6e859f41e432c5d2d0615a23cf00a503181f07efbba88a7ce8`. Verify the downloaded bytes before execution. Read that installation's `SKILL.md` and schemas; do not silently upgrade or vendor another renderer.

## Regenerate and review

From the repository root, replace the tool path with the verified installation:

```sh
ARCHIFY="/path/to/archify/bin/archify.mjs"
node "$ARCHIFY" finalize architecture docs/interactive/source/platform.json docs/interactive/platform.html --repo-root . --quality showcase --out-dir .validation-results/archify/platform/new-review --json
node "$ARCHIFY" visual-check docs/interactive/platform.html --require-provenance --out-dir .validation-results/archify/platform/new-visual-review --summary
```

Read each source's `diagram_type` before selecting the command: Platform, Networking and Security use `architecture`; Event Processing uses `sequence`; Private CD uses `workflow`. Preserve source evidence revisions unless the corresponding claims were rechecked. Never edit generated SVG/HTML as a substitute for the generator.

Review every changed connection and visible label. Distinguish source declarations, dated observations, demonstrated behavior and unverified claims. Examine real captures at desktop, laptop, tablet and mobile sizes; Fit All is an overview, not proof of reading-size labels. Preserve guided navigation, text alternatives, keyboard focus and Escape behavior. Axe success alone is not complete WCAG conformance.

## Integrate approved bytes

Only after semantic and visual review, update `frontend/architecture-pins.json` from the approved hashes. Keep LF normalization, Archify license/credits, sanitization and immutable presentation URLs. The asset adapter removes source metadata and embeds a network-denying CSP; the iframe remains opaque without `allow-same-origin`.

Run the relevant architecture, browser, accessibility and packaging checks in [frontend validation](frontend-release.md). Inspect screenshots instead of relying only on automated PASS. Receipts, tool paths and private evidence remain in ignored validation output; do not publish the original evidence directory or raw source metadata.
