// Local-only launcher. Never reads AWS credentials or sends AWS requests.
import { spawn, spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { localConfigDirectory } from "./local-config.mjs";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const ci = process.env.CNP_LOCAL_UI_CI === "1";
const output = localConfigDirectory();
mkdirSync(output, { recursive: true });
const configPath = resolve(output, "backend.json");
const fresh = () => randomBytes(32).toString("hex");
const config = existsSync(configPath)
  ? JSON.parse(readFileSync(configPath, "utf8"))
  : {
      password: fresh(),
      jwtSecret: fresh(),
      proxySecret: fresh(),
      internalSecret: fresh(),
    };
for (const key of ["password", "jwtSecret", "proxySecret", "internalSecret"])
  if (typeof config[key] !== "string" || config[key].length < 32)
    throw new Error("Invalid local secrets file");
writeFileSync(configPath, JSON.stringify(config) + "\n", { mode: 0o600 });
function run(command, args, env = process.env) {
  const r = spawnSync(command, args, {
    cwd: root,
    env,
    stdio: ["ignore", "pipe", "pipe"],
    encoding: "utf8",
  });
  if (r.status !== 0) {
    writeFileSync(
      resolve(output, "launcher-error.log"),
      String(r.stdout ?? "") + String(r.stderr ?? ""),
      { mode: 0o600 },
    );
    throw new Error(
      `${command} failed. Inspect ignored .validation-results/local-ui/launcher-error.log locally; it may contain private configuration.`,
    );
  }
  return r.stdout.trim();
}
const pg = "cnp-local-ui-postgres";
const volume = "cnp-local-ui-postgres-data";
if (!ci) {
  const inspect = spawnSync("docker", ["inspect", pg], { encoding: "utf8" });
  if (inspect.status === 0) {
    const info = JSON.parse(inspect.stdout)[0];
    if (info.Config.Labels?.["cnp.purpose"] !== "offline-ui")
      throw new Error("Existing container has unexpected ownership.");
    run("docker", ["start", pg]);
  } else {
    const check = spawnSync("docker", ["volume", "inspect", volume], {
      encoding: "utf8",
    });
    if (check.status === 0) {
      const info = JSON.parse(check.stdout)[0];
      if (info.Labels?.["cnp.purpose"] !== "offline-ui")
        throw new Error("Existing volume has unexpected ownership.");
    } else
      run("docker", [
        "volume",
        "create",
        "--label",
        "cnp.purpose=offline-ui",
        volume,
      ]);
    run(
      "docker",
      [
        "run",
        "-d",
        "--name",
        pg,
        "--label",
        "cnp.purpose=offline-ui",
        "-p",
        "127.0.0.1:55435:5432",
        "-e",
        "POSTGRES_PASSWORD",
        "-e",
        "POSTGRES_DB=platform",
        "-v",
        volume + ":/var/lib/postgresql/data",
        "postgres:15.18",
      ],
      { ...process.env, POSTGRES_PASSWORD: config.password },
    );
  }
  for (let i = 0; i < 45; i++) {
    const r = spawnSync(
      "docker",
      ["exec", pg, "pg_isready", "-U", "postgres"],
      {
        stdio: "ignore",
      },
    );
    if (r.status === 0) break;
    if (i === 44) throw new Error("PostgreSQL not ready");
    await new Promise((r) => setTimeout(r, 1000));
  }
}
const images = process.argv.includes("--images");
if (ci && images) throw new Error("CI API mode runs local assemblies only");
if (images) {
  const network = "cnp-local-ui-network";
  const check = spawnSync("docker", ["network", "inspect", network], {
    encoding: "utf8",
  });
  if (check.status === 0) {
    if (JSON.parse(check.stdout)[0].Labels?.["cnp.purpose"] !== "offline-ui")
      throw new Error("Network ownership mismatch");
  } else
    run("docker", [
      "network",
      "create",
      "--label",
      "cnp.purpose=offline-ui",
      network,
    ]);
  const info = JSON.parse(run("docker", ["inspect", pg]))[0];
  if (!info.NetworkSettings.Networks[network])
    run("docker", ["network", "connect", network, pg]);
}

const children = [];
const owned = [];
const envBase = {
  ...process.env,
  ASPNETCORE_ENVIRONMENT: "Development",
  DOTNET_ENVIRONMENT: "Development",
  Jwt__Secret: config.jwtSecret,
  PlatformAuth__TrustedProxySecret: config.proxySecret,
  PlatformAuth__InternalServiceSecret: config.internalSecret,
  PlatformAuth__AllowDevelopmentJwtPassthrough: "false",
  ShipmentConsumer__Enabled: "false",
  Outbox__Enabled: "false",
  AWS_EC2_METADATA_DISABLED: "true",
  Logging__LogLevel__Default: "Warning",
  Logging__LogLevel__Microsoft: "Warning",
};
// Do not pass host cloud credentials to local processes.
for (const key of Object.keys(envBase))
  if (key.startsWith("AWS_") && key !== "AWS_EC2_METADATA_DISABLED")
    delete envBase[key];
let stopping = false;
function stop() {
  if (stopping) return;
  stopping = true;
  for (const c of children) c.kill();
  for (const name of owned)
    spawnSync("docker", ["stop", "-t", "5", name], { stdio: "ignore" });
  console.log(
    "Local APIs stopped. PostgreSQL and its named volume were preserved.",
  );
}
process.on("SIGINT", () => {
  stop();
  process.exit(0);
});
process.on("SIGTERM", () => {
  stop();
  process.exit(0);
});
try {
  for (const [index, service] of ["auth", "shipment", "tracking"].entries()) {
    const title = service[0].toUpperCase() + service.slice(1) + "Service";
    const project = `microservices/${service}-service/src/${title}.Api/${title}.Api.csproj`;
    const dll = resolve(
      root,
      `microservices/${service}-service/src/${title}.Api/bin/Release/net10.0/${title}.Api.dll`,
    );
    const env = {
      ...envBase,
      ASPNETCORE_CONTENTROOT: images ? "/app" : resolve(root, dirname(project)),
      ConnectionStrings__Postgres: `Host=${images ? pg : "127.0.0.1"};Port=${ci ? Number(process.env.CNP_UI_POSTGRES_PORT ?? 5432) : images ? 5432 : 55435};Database=${ci ? "platform_ui_ci" : "platform"};Username=postgres;Password=${config.password}`,
      Database__Schema: service,
      ASPNETCORE_URLS: `http://${images ? "+" : "127.0.0.1"}:${8080 + index}`,
      ShipmentService__BaseUrl: images
        ? "http://cnp-local-ui-shipment:8081"
        : "http://127.0.0.1:8081",
    };
    let command, args;
    if (images) {
      const name = "cnp-local-ui-" + service;
      if (
        spawnSync("docker", ["inspect", name], { stdio: "ignore" }).status === 0
      )
        throw new Error(
          name + " already exists. Stop the previous launcher first.",
        );
      command = "docker";
      args = [
        "run",
        "--rm",
        "--name",
        name,
        "--label",
        "cnp.purpose=offline-ui",
        "--network",
        "cnp-local-ui-network",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777",
        "-p",
        `127.0.0.1:${8080 + index}:${8080 + index}`,
      ];
      for (const k of Object.keys(env).filter(
        (k) =>
          k.includes("__") ||
          [
            "ASPNETCORE_ENVIRONMENT",
            "DOTNET_ENVIRONMENT",
            "ASPNETCORE_URLS",
            "AWS_EC2_METADATA_DISABLED",
          ].includes(k),
      ))
        args.push("-e", k);
      args.push("cnp-ci/" + service + ":dotnet10");
      run(command, [...args, "--migrate"], env);
      owned.push(name);
    } else {
      command = process.env.CNP_DOTNET ?? "dotnet";
      run(command, ["restore", project, "--locked-mode"]);
      run(command, ["build", project, "-c", "Release", "--no-restore"]);
      run(command, [dll, "--migrate"], env);
      args = [dll];
    }
    const child = spawn(command, args, {
      env,
      cwd: root,
      stdio: ["ignore", "ignore", "ignore"],
    });
    children.push(child);
    child.once("error", () => {
      console.error("A local API process could not start.");
      stop();
      process.exitCode = 1;
    });
    let ready = false;
    for (let i = 0; i < 50; i++) {
      try {
        const response = await fetch(
          `http://127.0.0.1:${8080 + index}/health/ready`,
          { signal: AbortSignal.timeout(1000) },
        );
        if (response.ok) {
          ready = true;
          break;
        }
      } catch {
        /* bounded readiness polling */
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    if (!ready)
      throw new Error(
        service +
          " readiness failed. Check ports, database credentials and SDK prerequisites.",
      );
    console.log(`${service}: ready at localhost:${8080 + index}`);
  }
  console.log(
    "Local API ready. Start npm run dev:local in another terminal. AWS workers are disabled. Ctrl+C stops APIs, preserving PostgreSQL.",
  );
} catch (e) {
  stop();
  throw e;
}
