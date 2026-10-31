// Curated exports from reviewed, pinned Archify artifacts. No arbitrary HTML ingestion.
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  adaptViewport,
  viewportStyle,
  viewportScript,
} from "./architecture-viewport.mjs";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
export const diagramNames = [
  "platform",
  "networking",
  "event-processing",
  "private-cd",
  "security",
];
export const sha256 = (value) =>
  createHash("sha256").update(value).digest("hex");
export const policy =
  "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'";
function readingGuide(name) {
  const source = JSON.parse(
    readFileSync(
      resolve(root, "docs/interactive/source", name + ".json"),
      "utf8",
    ),
  );
  const nodes = source.components ?? source.nodes ?? source.participants;
  const connections = source.connections ?? source.edges ?? source.messages;
  return {
    chapters: source.meta.views,
    nodes: nodes.map(({ id, label, sublabel, sources }) => ({
      id,
      label,
      description: sublabel,
      sources: sources.map(({ path }) => path),
    })),
    connections: connections.map(({ id, from, to, label, note }) => ({
      id,
      from,
      to,
      label,
      note: note ?? "",
      classification: "DECLARED",
    })),
    evidence: source.cards,
  };
}
export function presentationExport(name) {
  if (!diagramNames.includes(name)) throw new Error("Unknown diagram");
  const original = readFileSync(
    resolve(root, "docs/interactive", name + ".html"),
  );
  const manifest = JSON.parse(
    readFileSync(resolve(root, "frontend/architecture-pins.json"), "utf8"),
  );
  if (sha256(original) !== manifest[name])
    throw new Error("Unreviewed Archify artifact: " + name);
  let html = original.toString("utf8");
  if (
    /<script[^>]+src=|<link[^>]+(?:href=)|<iframe|<object|<embed|<base\b|<form\b|\bon[a-z]+=|\b(?:fetch|eval)\s*\(|XMLHttpRequest|WebSocket|sendBeacon|serviceWorker/i.test(
      html,
    )
  )
    throw new Error("Unexpected active resource in " + name);
  html = html.replace('<html lang="en"', '<html lang="en" data-present="true"');
  html = html.replaceAll(
    "window.matchMedia('(prefers-color-scheme: light)').matches",
    "false",
  );
  // Strip private-repository identity/source metadata from the presentation copy.
  html = html.replace(
    /(<script id="archify-source-evidence-data"[^>]*>)[\s\S]*?(<\/script>)/,
    "$1" +
      JSON.stringify({
        schemaVersion: 1,
        verified: false,
        repository: null,
        referenceCount: 0,
        nodes: {},
      }) +
      "$2",
  );
  // Original author credit stays as text; all links are inert inside the offline viewer.
  html = html.replace(
    /(<a\b[^>]*?)\s+href="[^"]*"/g,
    '$1 aria-disabled="true"',
  );
  html = html.replace(
    /<head>/,
    '<head><meta http-equiv="Content-Security-Policy" content="' +
      policy +
      '"><meta name="referrer" content="no-referrer">',
  );
  html = html.replace(
    "</body>",
    `<script>${viewportScript}\nwindow.addEventListener('keydown',function(e){if(e.key==='Escape')window.parent.postMessage({type:'archify-viewer-escape'},'*');});</script></body>`,
  );
  html = html.replace(
    "</head>",
    "<style>html{color-scheme:dark}a[aria-disabled=true]{cursor:default} .source-evidence{display:none!important}" +
      viewportStyle +
      "</style></head>",
  );
  html = adaptViewport(html);
  if (
    /Kendall04|cloud-native-platform-eks\.git|arn:aws:|\b\d{12}\b|-----BEGIN (?:RSA |EC )?PRIVATE KEY/.test(
      html,
    )
  )
    throw new Error("Unexpected publication context in " + name);
  return {
    schemaVersion: 1,
    name,
    originalSha256: sha256(original),
    presentationSha256: sha256(html),
    generator: "Archify 3.1.0",
    adaptation:
      "Metadata removed; links inert; dark initial theme; labelled interactive SVG group; native focus/width camera; guided reading; single host expansion owner; validated focus-only messages; network denied by CSP; opaque-origin sandbox required.",
    guide: readingGuide(name),
    html,
  };
}
export function publicEvidence() {
  const read = (name) => JSON.parse(readFileSync(resolve(root, name), "utf8"));
  const migration = read("docs/evidence/dotnet10-migration.json");
  const lifecycle = read("docs/evidence/lifecycle-summary.json");
  const latest = read("docs/evidence/eks-acceptance-20261024.json");
  const observations = read(
    "docs/evidence/eks-portfolio-observations-20261029.json",
  );
  const baseline = read("scripts/ci/security-baseline.json");
  const paths = [
    "docs/evidence/dotnet10-migration.json",
    "docs/evidence/lifecycle-summary.json",
    "docs/evidence/eks-acceptance-20261024.json",
    "docs/evidence/eks-portfolio-observations-20261029.json",
    "docs/evidence/security-remediation.json",
    "scripts/ci/security-baseline.json",
  ];
  return {
    classification: "CURATED_PORTFOLIO_SUMMARY",
    scope:
      "Recorded local/CI and historical AWS evidence, not current cloud health.",
    runtime: {
      recordedOn: migration.verifiedOn,
      versions: Object.fromEntries(
        [
          "sdk",
          "runtime",
          "aspNetCore",
          "efCore",
          "npgsqlProvider",
          "npgsqlDriver",
          "postgresql",
          "trivy",
        ].map((key) => [key, migration.versions[key]]),
      ),
    },
    security: {
      uniqueExceptions: baseline.exceptions.length,
      severity: baseline.exceptions.reduce(
        (counts, item) => ({
          ...counts,
          [item.severity]: (counts[item.severity] ?? 0) + 1,
        }),
        {},
      ),
      expiry: [...new Set(baseline.exceptions.map((item) => item.expires))],
      policy: baseline.policy,
    },
    historicalAws: {
      runtime: ".NET 8",
      finishedUtc: lifecycle.finishedUtc,
      redeploy: Object.fromEntries(
        [
          "stacks",
          "recreatedTerraformResources",
          "readyNodes",
          "totalNodes",
          "eksVersion",
          "encryptedRootVolumes",
          "rootVolumeGiB",
          "rootVolumeType",
        ].map((key) => [key, lifecycle.redeploy[key]]),
      ),
      podEgress: Object.fromEntries(
        ["us-east-1a", "us-east-1b", "us-east-1c"].map((key) => [
          key,
          lifecycle.podEgress[key],
        ]),
      ),
      authPodReplacementSeconds: lifecycle.authPodReplacementSeconds,
      runtimeAbsentAtObservation:
        lifecycle.finalTeardown.runtimeAbsentAtObservation,
    },
    october24Aws: {
      closedUtc: latest.closedUtc,
      applicationSourceCommit: latest.applicationSourceCommit,
      checks: Object.fromEntries(
        [
          "C2DirectChecks",
          "C2GatewayChecks",
          "CniChecks",
          "C3Checks",
          "C4Checks",
          "liveWebChecks",
        ].map((key) => [key, latest.checks[key]]),
      ),
      retirement: Object.fromEntries(
        [
          "completedStages",
          "totalStages",
          "terraformObjectsRetired",
          "externalIamObjectsAbsent",
          "emptyStates",
          "retainedStates",
          "newKeyPendingDeletion",
          "globalInventoryComplete",
        ].map((key) => [key, latest.retirement[key]]),
      ),
    },
    latestAws: observations,
    pending: [
      "At the October 29 architecture audit, continuous authenticated old-tab transition and two different authenticated web-source releases had not been demonstrated. Later publication checks require their own dated evidence.",
      "Manual private delivery was demonstrated on October 29; authentic Dependabot security-update operation remains a separate repository task.",
      "Four HIGH build-SDK tooling findings remain a separate inventory; image findings remain advisory, not zero vulnerabilities.",
    ],
    sources: paths.map((path) => ({
      path,
      sha256: sha256(readFileSync(resolve(root, path))),
    })),
  };
}
export function versionedAssetPath(name, bytes) {
  return "architecture-assets/" + sha256(bytes) + "/" + name;
}
export function presentationFiles() {
  return new Map(
    [
      ...diagramNames.map((name) => [
        name + ".json",
        JSON.stringify(presentationExport(name)),
      ]),
      ["evidence.json", JSON.stringify(publicEvidence())],
      [
        "ARCHIFY-LICENSE.txt",
        readFileSync(resolve(root, "docs/interactive/ARCHIFY-LICENSE.txt")),
      ],
    ].map(([name, bytes]) => [versionedAssetPath(name, bytes), bytes]),
  );
}
export function architectureAssetPaths() {
  return Object.fromEntries(
    [...presentationFiles().keys()].map((path) => [
      path.split("/").at(-1),
      "/" + path,
    ]),
  );
}
export function architectureAssets() {
  const files = presentationFiles();
  const paths = Object.fromEntries(
    [...files.keys()].map((path) => [path.split("/").at(-1), "/" + path]),
  );
  const hashes = Object.fromEntries(
    diagramNames.map((name) => [
      name,
      presentationExport(name).presentationSha256,
    ]),
  );
  return {
    name: "reviewed-archify-data",
    resolveId(id) {
      if (id === "virtual:architecture-integrity")
        return "\0architecture-integrity";
    },
    load(id) {
      if (id === "\0architecture-integrity")
        return (
          "export default " +
          JSON.stringify(hashes) +
          ";export const assetUrls=" +
          JSON.stringify(
            Object.fromEntries(
              diagramNames.map((name) => [name, paths[name + ".json"]]),
            ),
          ) +
          ";export const publicUrls=" +
          JSON.stringify({
            evidence: paths["evidence.json"],
            license: paths["ARCHIFY-LICENSE.txt"],
          }) +
          ";"
        );
    },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const path = (req.url ?? "").split("?")[0];
        if (!path.startsWith("/architecture-assets/")) return next();
        const bytes = files.get(path.slice(1));
        if (bytes === undefined) {
          res.statusCode = 404;
          res.end();
          return;
        }
        res.setHeader(
          "Content-Type",
          path.endsWith(".json") ? "application/json" : "text/plain",
        );
        res.setHeader("X-Content-Type-Options", "nosniff");
        res.end(bytes);
      });
    },
    generateBundle() {
      for (const [fileName, source] of files)
        this.emitFile({ type: "asset", fileName, source });
    },
  };
}
