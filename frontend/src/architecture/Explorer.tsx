import { Link, NavLink, Routes, Route, useLocation } from "react-router";
import { diagrams, technicalPages, liveChecks } from "./catalog";
import { DiagramViewer } from "./DiagramViewer";
import { publicUrls } from "virtual:architecture-integrity";
import type { AppMode } from "../config";
const editionLabel = (mode: AppMode) =>
  mode === "aws"
    ? "AWS API EDITION"
    : mode === "demo"
      ? "DEMO EDITION · SYNTHETIC DATA"
      : "LOCAL API EDITION";
export function Explorer({ mode }: { mode: AppMode }) {
  const path = useLocation().pathname.split("/").at(-1);
  const isDiagram = diagrams.some((d) => d.id === path);
  const name =
    diagrams.find((d) => d.id === path)?.label ??
    technicalPages.find((p) => p.id === path)?.label ??
    "Overview";
  return (
    <div className="shell architecture-shell">
      <aside>
        <div className="workspace">
          ARCHITECTURE EXPLORER<span>Cloud Native Platform EKS</span>
        </div>
        <nav aria-label="Architecture navigation">
          <NavLink end to="/architecture">
            Overview
          </NavLink>
          {diagrams.map((d) => (
            <NavLink key={d.id} to={"/architecture/" + d.id}>
              {d.label}
            </NavLink>
          ))}
          {technicalPages.map((p) => (
            <NavLink key={p.id} to={"/architecture/" + p.id}>
              {p.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="mode">{editionLabel(mode)}</span>
          <p>
            Design and recorded evidence.
            <br />
            No live cloud telemetry.
          </p>
        </div>
      </aside>
      <div className="content">
        <header>
          <span>
            Architecture <span className="slash">/</span> {name}
          </span>
        </header>
        <main
          id="main"
          className={isDiagram ? "diagram-layout" : "reading-layout"}
        >
          <Routes>
            <Route path="/architecture" element={<Overview mode={mode} />} />
            {diagrams.map((d) => (
              <Route
                key={d.id}
                path={"/architecture/" + d.id}
                element={
                  <>
                    <div className="page-heading diagram-heading">
                      <div>
                        <h1>{d.title}</h1>
                        <p>{d.description}</p>
                      </div>
                    </div>
                    <p className="diagram-status">
                      Source-backed design · Evidence dated October 28–29, 2026
                      · Runtime retired October 29 · No live telemetry
                    </p>
                    <DiagramViewer key={d.id} id={d.id} title={d.title} />
                    <p className="diagram-caveat">{d.caveat}</p>
                    <div className="technical-cards">
                      {d.topics.map((text, i) => (
                        <article className="panel" key={text}>
                          <span className="eyebrow">
                            {
                              [
                                "RESPONSIBILITIES",
                                "CONNECTIONS",
                                "DECISIONS & LIMITS",
                              ][i]
                            }
                          </span>
                          <p>{text}</p>
                        </article>
                      ))}
                    </div>
                    {d.id === "security" && <Security />}
                    <References paths={d.sources} />
                    <Link to="/architecture/evidence" className="text-link">
                      Review verification boundaries →
                    </Link>
                  </>
                }
              />
            ))}
            <Route path="/architecture/scaling" element={<Scaling />} />
            <Route
              path="/architecture/lifecycle"
              element={
                <section className="panel editorial">
                  <h1>Infrastructure Lifecycle — historical diagram</h1>
                  <p>
                    This older diagram is preserved in the repository at
                    docs/interactive/lifecycle.html and source/lifecycle.json.
                    Its resource counts and legacy retirement procedure are
                    historical, not the current operating model.
                  </p>
                  <Link to="/architecture/security" className="text-link">
                    Continue to Security &amp; Trust Boundaries →
                  </Link>
                </section>
              }
            />
            <Route path="/architecture/evidence" element={<Evidence />} />
            <Route
              path="*"
              element={
                <section className="panel editorial">
                  <h1>Architecture page not found</h1>
                  <Link to="/architecture">Back to explorer overview →</Link>
                </section>
              }
            />
          </Routes>
        </main>
        <footer>
          Cloud Native Platform EKS ·{" "}
          <a
            href={publicUrls.license}
            target="_blank"
            rel="noopener noreferrer"
          >
            Archify MIT license
          </a>
          <span>Code-backed design · no live AWS status</span>
        </footer>
      </div>
    </div>
  );
}
function References({ paths }: { paths: readonly string[] }) {
  return (
    <details className="source-references">
      <summary>Implementation references in the original repository</summary>
      <p>
        Source paths for an authorized checkout; private repository links and
        raw reports are not published here.
      </p>
      <ul>
        {paths.map((path) => (
          <li key={path}>
            <code>{path}</code>
          </li>
        ))}
      </ul>
      <p>
        The original Archify files remain in docs/interactive. Presentation
        copies remove repository metadata; their original and adapted SHA256 are
        recorded in the exported JSON.
      </p>
    </details>
  );
}
function Overview({ mode }: { mode: AppMode }) {
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">BEHIND THE PRODUCT</span>
          <h1>Architecture Explorer</h1>
          <p>
            Explore the private AWS platform, reliable event processing and
            controlled delivery behind Logistics Platform Demo.
          </p>
        </div>
        <span className="mode">{editionLabel(mode)}</span>
      </div>
      <div className="architecture-intro">
        <h2>Three services. One traceable platform.</h2>
        <p>
          Auth, Shipment and Tracking run on private EKS, with RDS PostgreSQL
          and EventBridge/SQS. This explorer presents implemented design and
          recorded experiments. The edition label identifies the product data
          source; it does not report backend health. The five diagrams
          distinguish declared contracts, dated observations, proven experiments
          and unverified limits. The runtime was retired on October 29; the
          public DEMO remains independent.
        </p>
      </div>
      <div className="diagram-grid">
        {diagrams.map((d) => (
          <Link
            className="panel diagram-card"
            key={d.id}
            to={"/architecture/" + d.id}
          >
            <span className="eyebrow">{d.tag}</span>
            <h2>
              {d.title} <span>↗</span>
            </h2>
            <p>{d.description}</p>
            <small>Open interactive Archify diagram →</small>
          </Link>
        ))}
      </div>
      <section className="panel editorial">
        <h2>Choose a technical tour</h2>
        <div className="tour-links">
          <Link to="/architecture/platform">Request → private services</Link>
          <Link to="/architecture/event-processing">
            Outbox → durable effects
          </Link>
          <Link to="/architecture/private-cd">
            Immutable artifact → private rollout
          </Link>
          <Link to="/architecture/scaling">Pod demand → scaling controls</Link>
        </div>
      </section>
      <div className="verification-grid">
        <article className="panel">
          <span className="mode">ARCHITECTURE DESIGN</span>
          <h3>Source is authoritative</h3>
          <p>
            Terraform/Terragrunt, Helm, service code and protected contracts
            describe intended behavior.
          </p>
        </article>
        <article className="panel">
          <span className="mode">VERIFIED</span>
          <h3>Scoped, recorded checks</h3>
          <p>
            Local/CI results and a historical AWS lifecycle have different
            boundaries. No live health is inferred.
          </p>
        </article>
        <article className="panel">
          <span className="mode">RECORDED AWS CYCLE</span>
          <h3>Private delivery demonstrated</h3>
          <p>
            October 28–29 observations include .NET 10 services, two persisted
            event sequences, manual private delivery and verified automatic
            rollback. These dated results do not promise continuous
            availability.
          </p>
        </article>
      </div>
      <Link className="text-link" to="/architecture/evidence">
        Inspect the evidence and remaining checks →
      </Link>
    </>
  );
}
function Scaling() {
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">KUBERNETES / DESIGN</span>
          <h1>Kubernetes & scaling</h1>
          <p>
            Different controls act on application replicas, queue pressure and
            node capacity.
          </p>
        </div>
      </div>
      <section className="panel editorial">
        <h2>Scaling responsibilities</h2>
        <div
          className="scaling-signals"
          aria-label="Three scaling control loops, architecture design"
        >
          <div>
            <span>CPU utilization</span>
            <b>↓</b>
            <strong>CPU HPA</strong>
            <span>Auth / Tracking replicas</span>
          </div>
          <div>
            <span>SQS queue pressure · IRSA</span>
            <b>↓</b>
            <strong>KEDA → HPA</strong>
            <span>Shipment replicas</span>
          </div>
          <div>
            <span>Unschedulable pods</span>
            <b>↓</b>
            <strong>Cluster Autoscaler</strong>
            <span>Managed node group capacity</span>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Control</th>
              <th>Signal and responsibility</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>CPU HPA</td>
              <td>
                Auth and Tracking replica scaling uses CPU utilization against
                configured requests.
              </td>
            </tr>
            <tr>
              <td>KEDA</td>
              <td>
                Shipment queue demand is read from SQS through IRSA; its
                ScaledObject drives an HPA. Do not add a competing CPU HPA to
                that target.
              </td>
            </tr>
            <tr>
              <td>Cluster Autoscaler</td>
              <td>
                Scales managed node groups within declared bounds when pods
                cannot be scheduled. It does not replace workload autoscalers.
              </td>
            </tr>
            <tr>
              <td>PDB / probes</td>
              <td>
                Disruption budgets and readiness/liveness constrain selected
                rollout and disruption paths; they are not availability
                guarantees.
              </td>
            </tr>
          </tbody>
        </table>
        <p className="architecture-notice">
          The October 24 cycle observed KEDA replicas from two to four, worker
          nodes from one to two and back, with four total nodes maximum. CPU
          cooldown initially timed out; automatic return was observed later.
          These samples are not general capacity or availability guarantees.
        </p>
        <Link to="/architecture/networking">
          Explore node and network placement →
        </Link>
      </section>
      <References
        paths={[
          "k8s/charts/platform-services/templates",
          "k8s/environments/dev/platform-services.values.yaml",
          "k8s/charts/cluster-addons/values.yaml",
          "infra/live/dev/eks/terragrunt.hcl",
        ]}
      />
    </>
  );
}
function Security() {
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            SECURITY / DESIGN & LOCAL VERIFICATION
          </span>
          <h2>Security controls and limits</h2>
          <p>
            Scoped controls, known limits and explicit verification boundaries.
          </p>
        </div>
      </div>
      <div className="technical-cards">
        {[
          [
            "Trust boundaries",
            "Private EKS and ALB, verified gateway identity, per-service ownership checks and separate internal authentication. Internal HTTP hops are not mTLS.",
          ],
          [
            "Workload hardening",
            "Non-root applications, read-only roots, bounded 64 MiB scratch, dropped capabilities and explicit addon contexts. Scoped runtime checks are recorded in the October 24 acceptance matrix.",
          ],
          [
            "Guarded delivery",
            "OIDC roles, immutable digests/bundles, SHA256, exact template/source pins, replay locks, revision checks, rollback and durable receipts. Executor policy is 1.4.0.",
          ],
          [
            "Residual findings",
            "Nine unique IaC/Kubernetes exceptions remain: six HIGH and three CRITICAL, expiring 12 January 2027 UTC. Ten report occurrences are not ten unique exceptions. They are accepted temporarily, not declared safe.",
          ],
          [
            "Reliability boundary",
            "Outbox/inbox and sequence checks protect durable effects over at-least-once delivery. DLQs and recovery preserve event identity; they do not guarantee exactly-once transport.",
          ],
          [
            "Lab limitations",
            "Single-AZ RDS, one management host and EC2 NAT impose failure/capacity limits. Local/CI success is neither an SLA nor a compliance certification.",
          ],
        ].map(([title, text]) => (
          <article className="panel" key={title}>
            <h2>{title}</h2>
            <p>{text}</p>
          </article>
        ))}
      </div>
      <References
        paths={[
          "docs/security.md",
          "docs/evidence/security-remediation.json",
          "scripts/ci/security-baseline.json",
          "infra/modules/management-host/deployer",
        ]}
      />
      <Link to="/architecture/evidence" className="text-link">
        See verified results and pending live checks →
      </Link>
    </>
  );
}
function Evidence() {
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">EVIDENCE / READ THE BOUNDARIES</span>
          <h1>Validation evidence</h1>
          <p>
            Selected sanitized observations. No raw private reports, credentials
            or current cloud telemetry.
          </p>
        </div>
      </div>
      <section className="panel editorial">
        <span className="mode">VERIFIED LOCALLY & IN CI</span>
        <h2>Current .NET 10 baseline</h2>
        <p>
          SDK 10.0.402, runtime/ASP.NET Core/EF Core 10.0.13 and Npgsql 10.0.3.
          Sixteen projects and sixteen lockfiles. PostgreSQL 15.18 compatibility
          was checked against existing .NET 8-created data without new
          migrations.
        </p>
        <p>
          The migration PRs and main push passed hosted Validate. The later
          restored-develop run was blocked by GitHub billing for 13 jobs that
          never started; it is not represented as a green run.
        </p>
        <ul>
          <li>
            162 unique .NET tests; dedicated PostgreSQL reliability gate 49/49.
          </li>
          <li>
            Three amd64 application image builds and validated CycloneDX 1.7
            SBOMs.
          </li>
          <li>
            At the recorded scan: each final image had 1 LOW, 2 MEDIUM and no
            HIGH/CRITICAL. Scanner results are dated observations, not safety
            guarantees.
          </li>
          <li>
            Four HIGH SDK build-image findings were a separate inventory, not
            production runtime-image findings.
          </li>
        </ul>
      </section>
      <section className="panel editorial">
        <span className="mode">HISTORICAL AWS · .NET 8</span>
        <h2>Completed lifecycle demonstration</h2>
        <p>
          Final report completed 14 October 2026 at 17:28:21 UTC. One redeploy
          recreated 18 stacks and 190 Terraform resources; 3/3 nodes were Ready.
          Auth/Shipment/Tracking, event propagation and post-redeploy Private CD
          were exercised before the final teardown.
        </p>
        <p>
          Egress was verified from pods in B/C, not A. One Auth pod replacement
          reached Ready in 26.1 seconds; this single sample is not an RTO or
          SLA. The later hardening and .NET 10 runtime were not part of that
          live demonstration.
        </p>
      </section>
      <section className="panel editorial">
        <span className="mode">RECORDED AWS · .NET 10</span>
        <h2>October 24 acceptance and retirement</h2>
        <p>
          Direct authorization 29, gateway 42, CNI 18, event recovery 53,
          rollback and capacity 23, and real web/API 13 scoped checks. Counts
          overlap and are not a unique summed test total. A compatible Helm
          rollback did not roll back the database.
        </p>
        <p>
          All 39 retirement stages and three separate temporary IAM removals
          were verified. Original secrets, state history and DEMO hosting were
          preserved. One new key remains PendingDeletion; foreign attributes
          denied to discovery remain unverified. This is not a global purge.
        </p>
        <p>
          Hosting selected DEMO A, AWS configuration B, then original A. Two
          distinct authenticated web-source releases and a continuous old
          authenticated tab through the transition were not demonstrated.
        </p>
      </section>
      <section className="panel editorial">
        <span className="mode">RECORDED AWS · OCTOBER 28–29, 2026</span>
        <h2>Private delivery and recovery observations</h2>
        <p>
          Manual Build, Scan, Create Release and Deploy delivered v2.0.8 through
          OIDC, versioned S3, SSM, Management and Helm. A failed smoke triggered
          verified rollback; a later deployment reached revision 4 with six
          Ready pods and ALB Pod Readiness Gates. No database rollback is
          claimed.
        </p>
        <p>
          Two tracking event sequences were published and applied to durable
          shipment state. One NAT instance replacement recovered its EIP and
          route in 2 minutes 58 seconds. Private egress after that replacement
          remains UNVERIFIED; this was not uninterrupted egress or an AZ
          failover. RDS was Single-AZ; the three nodes were observed in A/A/C,
          with both Auth replicas on one node. These placements are a dated
          observation.
        </p>
      </section>
      <section className="panel editorial">
        <span className="mode demo">LIMITS & FOLLOW-UP</span>
        <h2>Remaining verification boundaries</h2>
        <ul>
          {liveChecks.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <p>
          <a
            href={publicUrls.evidence}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open curated evidence summary (JSON) ↗
          </a>
        </p>
        <p>
          No AWS work is performed by this explorer. AWS delivery workflows were
          manually exercised on October 29; this page does not monitor or change
          their current state. Product API availability depends on the selected
          edition and the separately operated backend session.
        </p>
      </section>
      <References
        paths={[
          "docs/evidence/dotnet10-migration.json",
          "docs/evidence/lifecycle-summary.json",
          "docs/evidence/eks-acceptance-20261024.json",
          "docs/evidence/security-remediation.json",
          "docs/results.md",
          "docs/development.md",
        ]}
      />
    </>
  );
}
