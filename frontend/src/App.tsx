import {
  useState,
  useRef,
  useEffect,
  useCallback,
  useMemo,
  createContext,
  useContext,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Routes,
  Navigate,
  useLocation,
  Route,
  NavLink,
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router";
import { Explorer } from "./architecture/Explorer";
import { apiMessage, ApiError, createHttpApi } from "./api";
import { createDemoApi } from "./demo";
import type { AppMode } from "./config";
import {
  createSchema,
  statuses,
  type PlatformApi,
  type Profile,
  type Shipment,
} from "./contracts";
const modeCopy = {
  demo: {
    label: "DEMO · SYNTHETIC DATA",
    loginLabel: "DEMO · SYNTHETIC DATA",
    about:
      "Synthetic in-memory data. No EventBridge/SQS traffic. Changes reset on reload.",
    login:
      "Try an isolated preview. Changes reset when you reload. No credentials or network requests are used.",
    footer: "Synthetic workspace",
  },
  local: {
    label: "LOCAL API · POSTGRESQL",
    loginLabel: "LOCAL API",
    about: "Real local APIs and PostgreSQL. AWS event workers are disabled.",
    login: "Sign in with an account in your local Auth database.",
    footer: "Local workspace · .NET 10 services",
  },
  aws: {
    label: "AWS API",
    loginLabel: "AWS API",
    about:
      "Uses the connected platform API. Availability depends on the backend session.",
    login: "Sign in with your platform account. The backend must be available.",
    footer: "Connected workspace · .NET 10 services",
  },
} satisfies Record<AppMode, Record<string, string>>;
type Session = {
  api: PlatformApi;
  profile: Profile;
  logout: () => void;
  mode: AppMode;
};
const Context = createContext<Session | null>(null);
function useSession() {
  const value = useContext(Context);
  if (!value) throw new Error("Session required");
  return value;
}
const human = (text: string) => text.toLowerCase().replaceAll("_", " ");
const date = (value: string) =>
  new Date(value).toLocaleString("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }) + " UTC";
function Badge({ status }: { status: string }) {
  return (
    <span className={`badge status-${status.toLowerCase()}`}>
      {human(status)}
    </span>
  );
}
function ErrorBox({ error }: { error: unknown }) {
  return error ? (
    <div role="alert" className="error">
      {apiMessage(error)}
    </div>
  ) : null;
}
function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="empty">
      <span className="empty-mark">◇</span>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function SpaceTabs() {
  const architecture = useLocation().pathname.startsWith("/architecture");
  return (
    <div className="space-header">
      <Link to="/demo" className="space-brand">
        Cloud Native Platform EKS
      </Link>
      <nav aria-label="Choose workspace">
        <NavLink to="/demo" className={!architecture ? "active" : ""}>
          Logistics Demo
        </NavLink>
        <NavLink to="/architecture" className={architecture ? "active" : ""}>
          Architecture Explorer
        </NavLink>
      </nav>
      <span className="space-caption">CLOUD NATIVE PLATFORM EKS</span>
    </div>
  );
}
export function App(props: {
  mode: AppMode;
  base?: string;
  client?: PlatformApi;
}) {
  const location = useLocation();
  const legacy =
    location.pathname === "/" ||
    location.pathname.startsWith("/shipments") ||
    location.pathname === "/tracking";
  if (legacy)
    return (
      <Navigate
        replace
        to={
          "/demo" +
          (location.pathname === "/" ? "" : location.pathname) +
          location.search
        }
      />
    );
  return (
    <>
      <SpaceTabs />
      <ProductApp {...props} />
    </>
  );
}
function Breadcrumbs() {
  const location = useLocation();
  const path = location.pathname;
  return (
    <nav aria-label="Breadcrumb" className="breadcrumbs">
      <Link to="/demo">Workspace</Link>
      <span>/</span>
      {path.includes("/shipments") ? (
        <>
          <Link to="/demo/shipments">Shipments</Link>
          {path.endsWith("/new") && (
            <>
              <span>/</span>
              <span>Create</span>
            </>
          )}
          {/\/shipments\/[a-f0-9-]+$/i.test(path) && (
            <>
              <span>/</span>
              <span>Details</span>
            </>
          )}
        </>
      ) : (
        <span>{path.includes("/tracking") ? "Tracking" : "Overview"}</span>
      )}
    </nav>
  );
}
function ProductApp({
  mode,
  base = "/api",
  client,
}: {
  mode: AppMode;
  base?: string;
  client?: PlatformApi;
}) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [expires, setExpires] = useState(0);
  const [notice, setNotice] = useState("");
  const api = useMemo(
    () =>
      client ??
      (mode === "demo"
        ? createDemoApi()
        : createHttpApi(base, () => {
            setProfile(null);
            setNotice("Your session expired. Please sign in again.");
          })),
    [client, mode, base],
  );
  const logout = () => {
    api.setToken(null);
    setProfile(null);
    setExpires(0);
    setNotice("You have signed out.");
  };
  useEffect(() => {
    if (!profile) return;
    const remaining = expires - Date.now();
    const timer = setTimeout(
      () => {
        api.setToken(null);
        setProfile(null);
        setNotice("Your session expired. Please sign in again.");
      },
      Math.max(0, remaining),
    );
    return () => clearTimeout(timer);
  }, [api, profile, expires]);
  async function login(email: string, password: string) {
    setNotice("");
    const tokens = await api.login(email, password);
    if (Date.parse(tokens.accessTokenExpiresAt) <= Date.now())
      throw new ApiError(401, "The server issued an expired session.");
    api.setToken(tokens.accessToken);
    try {
      const user = await api.me();
      if (!user.isActive) throw new ApiError(403, "This account is disabled.");
      setExpires(Date.parse(tokens.accessTokenExpiresAt));
      setProfile(user);
    } catch (e) {
      api.setToken(null);
      throw e;
    }
  }
  if (useLocation().pathname.startsWith("/architecture"))
    return <Explorer mode={mode} />;
  if (!profile)
    return (
      <Login
        mode={mode}
        login={login}
        register={api.register}
        notice={notice}
      />
    );
  return (
    <Context.Provider value={{ api, profile, logout, mode }}>
      <div className="shell">
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        <aside>
          <Link to="/demo" className="brand">
            <span className="brand-icon" aria-hidden="true">
              ◈
            </span>{" "}
            Logistics Demo
          </Link>
          <div className="workspace">
            CLOUD NATIVE PLATFORM<span>Shipment workspace</span>
          </div>
          <nav aria-label="Main navigation">
            <NavLink to="/demo" end>
              <span>▦</span> Overview
            </NavLink>
            <NavLink to="/demo/shipments">
              <span>▱</span> Shipments
            </NavLink>
            <NavLink to="/demo/tracking">
              <span>⌁</span> Tracking
            </NavLink>
          </nav>
          <div className="sidebar-bottom">
            <span className={`mode ${mode}`}>{modeCopy[mode].label}</span>
            <details className="mode-details">
              <summary>About this mode</summary>
              <p>{modeCopy[mode].about}</p>
            </details>
            <div className="account">
              <span className="avatar">{profile.firstName.slice(0, 1)}</span>
              <div>
                <strong>
                  {profile.firstName} {profile.lastName}
                </strong>
                <small>{profile.roles.join(", ")}</small>
              </div>
            </div>
            <button className="quiet" onClick={logout}>
              Sign out ↗
            </button>
          </div>
        </aside>
        <div className="content">
          <header>
            <Breadcrumbs />
            <span className="environment">Logistics Platform Demo</span>
          </header>
          <main id="main">
            <Routes>
              <Route path="/demo" element={<Overview />} />
              <Route path="/demo/shipments" element={<Shipments />} />
              <Route path="/demo/shipments/new" element={<Create />} />
              <Route path="/demo/shipments/:id" element={<Detail />} />
              <Route path="/demo/tracking" element={<Tracking />} />
              <Route
                path="*"
                element={
                  <Empty title="Page not found">
                    <Link to="/demo">Back to overview</Link>
                  </Empty>
                }
              />
            </Routes>
          </main>
          <footer>
            Cloud Native Platform EKS
            <span>{modeCopy[mode].footer}</span>
          </footer>
        </div>
      </div>
    </Context.Provider>
  );
}
function Login({
  mode,
  login,
  register,
  notice,
}: {
  register: PlatformApi["register"];
  mode: AppMode;
  login: (email: string, password: string) => Promise<void>;
  notice: string;
}) {
  const [signup, setSignup] = useState(false);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      if (signup)
        await register({
          email: String(data.get("email")),
          password: String(data.get("password")),
          firstName: String(data.get("firstName")),
          lastName: String(data.get("lastName")),
        });
      await login(
        String(data.get("email") ?? ""),
        String(data.get("password") ?? ""),
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-layout">
      <section className="login-story">
        <div className="brand">
          <span className="brand-icon" aria-hidden="true">
            ◈
          </span>{" "}
          Engineering demonstration
        </div>
        <span className="eyebrow">CLOUD NATIVE PLATFORM EKS</span>
        <h1>
          Logistics
          <br />
          Platform Demo
        </h1>
        <p>
          Interactive logistics application running on a cloud-native AWS
          platform. Choose a shipment and follow its journey through the
          engineering demonstration.
        </p>
        <div className="login-route">
          <span>Origin</span>
          <i />
          <span>In transit</span>
          <i />
          <span>Destination</span>
        </div>
        <small>Built on Auth, Shipment & Tracking · .NET 10</small>
      </section>
      <section className="login-card">
        <span className={`mode ${mode}`}>{modeCopy[mode].loginLabel}</span>
        <h2>
          {mode === "demo"
            ? "Explore the workspace"
            : signup
              ? "Create your account"
              : "Welcome back"}
        </h2>
        <p>{modeCopy[mode].login}</p>
        {notice && <p role="status">{notice}</p>}
        <ErrorBox error={error} />
        <form onSubmit={submit}>
          {mode !== "demo" && (
            <>
              {signup && (
                <>
                  <label>
                    First name
                    <input name="firstName" required maxLength={100} />
                  </label>
                  <label>
                    Last name
                    <input name="lastName" required maxLength={100} />
                  </label>
                </>
              )}
              <label>
                Email
                <input
                  name="email"
                  type="email"
                  autoComplete="username"
                  required
                  placeholder="you@example.com"
                />
              </label>
              <label>
                Password
                <input
                  name="password"
                  type="password"
                  autoComplete={signup ? "new-password" : "current-password"}
                  required
                  minLength={signup ? 8 : undefined}
                />
              </label>
            </>
          )}
          <button className="primary" disabled={busy}>
            {busy
              ? "Signing in…"
              : mode === "demo"
                ? "Enter demo workspace →"
                : signup
                  ? "Create account →"
                  : "Sign in →"}
          </button>
        </form>
        {mode !== "demo" && (
          <button
            className="quiet"
            onClick={() => {
              setSignup(!signup);
              setError(null);
            }}
          >
            {signup
              ? "Already registered? Sign in"
              : "New here? Create an account"}
          </button>
        )}
        <div className="session-note">
          Session tokens stay in memory. Reloading signs you out.
          {mode !== "demo" &&
            " Passwords require uppercase, lowercase, a number and a symbol (8 characters minimum)."}
        </div>
      </section>
    </div>
  );
}
function Heading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
function ShipmentTable({ items }: { items: Shipment[] }) {
  if (!items.length)
    return (
      <Empty title="No shipments yet">
        Create a shipment to start its journey.
      </Empty>
    );
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Tracking number</th>
            <th>Route</th>
            <th>Status</th>
            <th>Weight</th>
            <th>Created</th>
            <th>
              <span className="sr-only">Details</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.id}>
              <td>
                <Link className="mono" to={"/demo/shipments/" + s.id}>
                  {s.trackingNumber}
                </Link>
                <small>{s.referenceNumber ?? "No reference"}</small>
              </td>
              <td>
                {s.origin}
                <span className="route-arrow">→</span>
                <small>{s.destination}</small>
              </td>
              <td>
                <Badge status={s.status} />
              </td>
              <td>
                {s.weight} <span className="muted">kg</span>
              </td>
              <td className="muted">{date(s.createdAt)}</td>
              <td>
                <Link
                  aria-label={"Open " + s.trackingNumber}
                  to={"/demo/shipments/" + s.id}
                >
                  ↗
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function useResource<T>(
  key: string,
  load: () => Promise<T>,
): { data?: T; error?: unknown } {
  const [result, setResult] = useState<{
    key: string;
    data?: T;
    error?: unknown;
  }>();
  useEffect(() => {
    let alive = true;
    load()
      .then((data) => {
        if (alive) setResult({ key, data });
      })
      .catch((error) => {
        if (alive) setResult({ key, error });
      });
    return () => {
      alive = false;
    };
  }, [key, load]);
  return result?.key === key ? result : {};
}
function useShipments(page = 1, status = "") {
  const { api } = useSession();
  const [reload, setReload] = useState(0);
  const load = useCallback(() => api.list(page, status), [api, page, status]);
  const { data, error } = useResource(`${page}:${status}:${reload}`, load);
  return {
    data,
    error,
    loading: !data && !error,
    refresh: () => setReload((v) => v + 1),
  };
}
function Overview() {
  const { data, error, loading, refresh } = useShipments();
  const items = data?.items ?? [];
  return (
    <>
      <Heading
        eyebrow="YOUR WORKSPACE"
        title="Shipment overview"
        description="A clear view of your latest shipments and their progress."
        action={
          <Link className="primary" to="/demo/shipments/new">
            ＋ Create shipment
          </Link>
        }
      />
      <div className="stat-grid">
        <article className="stat">
          <span>Total shipments</span>
          <strong>{data?.totalCount ?? "—"}</strong>
          <small>All shipments visible to your account</small>
        </article>
        <article className="stat">
          <span>In transit · current page</span>
          <strong>
            {data ? items.filter((s) => s.status === "IN_TRANSIT").length : "—"}
          </strong>
          <small>Derived from the latest {items.length} records</small>
        </article>
        <article className="stat">
          <span>Delivered · current page</span>
          <strong>
            {data ? items.filter((s) => s.status === "DELIVERED").length : "—"}
          </strong>
          <small>Derived from the latest {items.length} records</small>
        </article>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Latest shipments</h2>
            <p>Most recently created, newest first.</p>
          </div>
          <button className="quiet" onClick={refresh}>
            Refresh ↻
          </button>
        </div>
        <ErrorBox error={error} />
        {loading ? (
          <p role="status" className="loading">
            Loading shipments…
          </p>
        ) : (
          data && <ShipmentTable items={items} />
        )}
      </section>
      <div className="info-strip">
        <span>⌁</span>
        <div>
          <strong>Follow the events behind each shipment</strong>
          <p>
            Open tracking to inspect recorded timestamps, locations and sequence
            numbers.
          </p>
        </div>
        <Link to="/demo/tracking">Explore tracking →</Link>
      </div>
    </>
  );
}
function Shipments() {
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get("page")) || 1);
  const status = params.get("status") ?? "";
  const { data, error, loading, refresh } = useShipments(page, status);
  const navigate = useNavigate();
  function search(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const number = String(data.get("number") ?? "").trim();
    if (number) navigate("/demo/tracking?number=" + encodeURIComponent(number));
  }
  return (
    <>
      <Heading
        eyebrow="SHIPMENT SERVICE"
        title="Shipments"
        description="Manage the shipments your account is authorized to access."
        action={
          <Link className="primary" to="/demo/shipments/new">
            ＋ Create shipment
          </Link>
        }
      />
      <form className="tracking-search" onSubmit={search}>
        <label className="sr-only" htmlFor="shipment-search">
          Find by tracking number
        </label>
        <input
          id="shipment-search"
          name="number"
          required
          maxLength={150}
          placeholder="Exact tracking number"
        />
        <button>Find tracking →</button>
      </form>
      <section className="panel">
        <div className="panel-heading">
          <label className="filter">
            Status
            <select
              aria-label="Filter status"
              value={status}
              onChange={(e) => setParams({ status: e.target.value, page: "1" })}
            >
              <option value="">All statuses</option>
              {statuses.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <button className="quiet" onClick={refresh}>
            Refresh ↻
          </button>
        </div>
        <ErrorBox error={error} />
        {loading ? (
          <p role="status" className="loading">
            Loading shipments…
          </p>
        ) : (
          data && (
            <>
              <ShipmentTable items={data.items} />
              <div className="pagination">
                <span>
                  {data.totalCount} shipments · Page {data.pageNumber}
                </span>
                <div>
                  <button
                    disabled={page <= 1}
                    onClick={() =>
                      setParams({ status, page: String(page - 1) })
                    }
                  >
                    Previous
                  </button>
                  <button
                    disabled={page * data.pageSize >= data.totalCount}
                    onClick={() =>
                      setParams({ status, page: String(page + 1) })
                    }
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          )
        )}
      </section>
    </>
  );
}
function Create() {
  const { api, profile } = useSession();
  const submitting = useRef(false);
  const navigate = useNavigate();
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (submitting.current) return;
    setError(null);
    const form = new FormData(e.currentTarget);
    const parsed = createSchema.safeParse({
      customerId: profile.userId,
      origin: String(form.get("origin")).trim(),
      destination: String(form.get("destination")).trim(),
      weight: Number(form.get("weight")),
      referenceNumber: String(form.get("referenceNumber")).trim() || null,
      priority: String(form.get("priority")).trim() || null,
    });
    if (!parsed.success) {
      setError(
        new Error(
          parsed.error.issues
            .map((i) => `${i.path.join(".")}: ${i.message}`)
            .join(" "),
        ),
      );
      return;
    }
    submitting.current = true;
    setBusy(true);
    try {
      const shipment = await api.create(parsed.data);
      navigate("/demo/shipments/" + shipment.id);
    } catch (e) {
      setError(e);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <>
      <Link className="back" to="/demo/shipments">
        ← All shipments
      </Link>
      <Heading
        eyebrow="NEW SHIPMENT"
        title="Start a new journey"
        description="Create a shipment for your own account. Tracking numbers are assigned by Shipment."
      />
      <section className="panel form-panel">
        <form onSubmit={submit}>
          <h2>Shipment details</h2>
          <p className="muted">Fields marked * are required.</p>
          <ErrorBox error={error} />
          <div className="form-grid">
            <label>
              Origin *
              <input
                name="origin"
                required
                maxLength={200}
                placeholder="City or pickup location"
              />
            </label>
            <label>
              Destination *
              <input
                name="destination"
                required
                maxLength={200}
                placeholder="City or delivery location"
              />
            </label>
            <label>
              Weight (kg) *
              <input
                name="weight"
                type="number"
                min="0.01"
                max="100000"
                step="0.01"
                required
                placeholder="0.00"
              />
            </label>
            <label>
              Reference number
              <input
                name="referenceNumber"
                maxLength={100}
                placeholder="Optional customer reference"
              />
            </label>
            <label>
              Priority
              <input
                name="priority"
                maxLength={50}
                placeholder="Optional, e.g. Standard"
              />
            </label>
          </div>
          <div className="form-actions">
            <Link to="/demo/shipments">Cancel</Link>
            <button className="primary" disabled={busy}>
              {busy ? "Creating…" : "Create shipment →"}
            </button>
          </div>
        </form>
      </section>
    </>
  );
}
function Detail() {
  const { id = "" } = useParams();
  const { api } = useSession();
  const load = useCallback(() => api.get(id), [api, id]);
  const { data: shipment, error } = useResource(id, load);
  return (
    <>
      <Link className="back" to="/demo/shipments">
        ← All shipments
      </Link>
      <ErrorBox error={error} />
      {!shipment && !error && <p role="status">Loading shipment…</p>}
      {shipment && (
        <>
          <Heading
            eyebrow="SHIPMENT DETAILS"
            title={shipment.trackingNumber}
            description={"Created " + date(shipment.createdAt)}
            action={<Badge status={shipment.status} />}
          />
          <section className="panel detail-panel">
            <div className="journey">
              <div>
                <span>ORIGIN</span>
                <h2>{shipment.origin}</h2>
              </div>
              <span className="journey-line">────────→</span>
              <div>
                <span>DESTINATION</span>
                <h2>{shipment.destination}</h2>
              </div>
            </div>
            <dl>
              <div>
                <dt>Weight</dt>
                <dd>{shipment.weight} kg</dd>
              </div>
              <div>
                <dt>Reference</dt>
                <dd>{shipment.referenceNumber ?? "Not provided"}</dd>
              </div>
              <div>
                <dt>Priority</dt>
                <dd>{shipment.priority ?? "Not provided"}</dd>
              </div>
              <div>
                <dt>Last tracking event</dt>
                <dd>
                  {shipment.lastTrackingEventAt
                    ? date(shipment.lastTrackingEventAt)
                    : "Awaiting first tracking update"}
                </dd>
              </div>
            </dl>
          </section>
          {shipment.status === "DELIVERED" && (
            <p className="delivery-note">
              ✓ Delivered — the shipment has reached its destination.
            </p>
          )}
          <Timeline number={shipment.trackingNumber} />
        </>
      )}
    </>
  );
}
function Timeline({ number }: { number: string }) {
  const { api, mode } = useSession();
  const [reload, setReload] = useState(0);
  const load = useCallback(() => api.timeline(number), [api, number]);
  const { data: events, error } = useResource(number + ":" + reload, load);
  return (
    <section className="panel timeline-panel">
      <div className="panel-heading">
        <div>
          <h2>Tracking history</h2>
          <p>Recorded events · timestamps displayed in UTC.</p>
        </div>
        <button className="quiet" onClick={() => setReload((v) => v + 1)}>
          Refresh ↻
        </button>
      </div>
      <ErrorBox error={error} />
      {!events && !error && (
        <p className="loading" role="status">
          Loading tracking…
        </p>
      )}
      {events?.length === 0 && (
        <Empty title="Awaiting first tracking update">
          {mode === "demo"
            ? "This synthetic shipment has no recorded events. Create operations do not fabricate tracking updates."
            : mode === "local"
              ? "Shipment creation does not generate a tracking event. AWS event delivery is not running in this local workspace."
              : "No tracking events have been recorded yet. Refresh to check for updates."}
        </Empty>
      )}
      {events && events.length > 0 && (
        <ol className="timeline">
          {events.map((e) => (
            <li key={e.id}>
              <div className="timeline-dot" />
              <div>
                <Badge status={e.status} />
                <h3>{e.location}</h3>
                {e.notes && <p>{e.notes}</p>}
                <small>
                  {date(e.occurredAt)} · Sequence {e.sequenceNumber} ·{" "}
                  {e.sourceType}
                </small>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
function Tracking() {
  const [params, setParams] = useSearchParams();
  const number = params.get("number") ?? "";
  const { mode } = useSession();
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const value = String(form.get("number")).trim();
    if (value) setParams({ number: value });
  }
  return (
    <>
      <Heading
        eyebrow="TRACKING SERVICE"
        title="Follow a shipment"
        description="Look up recorded events using an exact tracking number."
      />
      <form onSubmit={submit} className="tracking-search">
        <label className="sr-only" htmlFor="tracking-number">
          Tracking number
        </label>
        <input
          id="tracking-number"
          name="number"
          key={number}
          defaultValue={number}
          required
          maxLength={150}
          placeholder="Enter tracking number"
        />
        <button className="primary">Find shipment →</button>
      </form>
      {number ? (
        <TrackingResult number={number} />
      ) : (
        <section className="panel">
          <Empty title="Every journey has a timeline">
            Enter a tracking number above or open a shipment from your
            workspace.
          </Empty>
          {mode === "demo" && (
            <div className="tracking-examples">
              <span>Try a synthetic example:</span>
              {["DEMO-2026-001", "DEMO-2026-002"].map((value) => (
                <button
                  key={value}
                  onClick={() => setParams({ number: value })}
                >
                  {value}
                </button>
              ))}
            </div>
          )}
        </section>
      )}
    </>
  );
}

function TrackingResult({ number }: { number: string }) {
  const { api } = useSession();
  const load = useCallback(() => api.lookup(number), [api, number]);
  const { data: shipment, error } = useResource(number, load);
  return (
    <>
      <ErrorBox error={error} />
      {!shipment && !error && <p role="status">Looking up shipment…</p>}
      {shipment && (
        <>
          <div className="tracking-result">
            <div>
              <Link className="mono" to={"/demo/shipments/" + shipment.id}>
                {shipment.trackingNumber} ↗
              </Link>
              <p>
                {shipment.origin} → {shipment.destination}
              </p>
            </div>
            <div>
              <small>Current shipment status</small>
              <Badge status={shipment.status} />
            </div>
          </div>
          <Timeline number={number} />
        </>
      )}
    </>
  );
}
