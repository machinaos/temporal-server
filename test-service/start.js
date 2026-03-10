#!/usr/bin/env node
/**
 * Launch script for the Temporal Workflow Dashboard.
 *
 * 1. Builds the React UI (if not already built)
 * 2. Starts the Temporal server (if not already running)
 * 3. Starts the FastAPI server (uvicorn) on a free port
 * 4. Opens the browser
 *
 * Usage: node start.js   |   npm start
 */

import { execSync, spawn } from "child_process";
import { existsSync, readFileSync } from "fs";
import { createServer } from "net";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const ROOT = dirname(fileURLToPath(import.meta.url));
const TEMPORAL_PKG = join(ROOT, "node_modules", "temporal-server");
const UI_DIR = join(ROOT, "ui");
const UI_DIST = join(UI_DIR, "dist", "index.html");
const CFG = JSON.parse(readFileSync(join(TEMPORAL_PKG, "configs", "server.json"), "utf8"));

function log(msg) {
  console.log(`[start] ${msg}`);
}

// --- 1. Build UI if needed ---

if (!existsSync(UI_DIST)) {
  log("Building React UI...");
  execSync("npm run build", { cwd: UI_DIR, stdio: "inherit", shell: true });
} else {
  log("UI already built");
}

// --- 2. Start Temporal if needed ---

function portUp(port) {
  return new Promise((resolve) => {
    const s = createServer();
    s.once("error", () => resolve(true)); // port in use = server running
    s.once("listening", () => { s.close(); resolve(false); });
    s.listen(port, "127.0.0.1");
  });
}

const temporalRunning = await portUp(CFG.port);
if (temporalRunning) {
  log(`Temporal already running on ${CFG.port}`);
} else {
  log("Starting Temporal server...");
  execSync(`node ${join(TEMPORAL_PKG, "scripts", "cli.js")} start`, {
    cwd: ROOT,
    stdio: "inherit",
  });
}

// --- 3. Find a free port ---

function freePort() {
  return new Promise((resolve, reject) => {
    const s = createServer();
    s.listen(0, "127.0.0.1", () => {
      const port = s.address().port;
      s.close(() => resolve(port));
    });
    s.on("error", reject);
  });
}

const port = await freePort();

// --- 4. Start uvicorn ---

log(`Starting API server on http://127.0.0.1:${port}`);

const server = spawn(
  "python",
  ["-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", String(port)],
  { cwd: ROOT, stdio: "inherit" }
);

// --- 5. Wait for server, then open browser ---

async function waitForServer(port, timeout = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (await portUp(port)) return true;
    await new Promise((r) => setTimeout(r, 300));
  }
  return false;
}

if (await waitForServer(port)) {
  const url = `http://127.0.0.1:${port}`;
  log(`Dashboard ready: ${url}`);
  log(`Temporal UI:     http://${CFG.ip}:${CFG.uiPort}`);

  // open browser (cross-platform)
  const cmd = process.platform === "win32" ? "start" : process.platform === "darwin" ? "open" : "xdg-open";
  execSync(`${cmd} ${url}`, { shell: true, stdio: "ignore" });
} else {
  log("WARNING: Server did not start within 15s");
}

// forward signals to child
process.on("SIGINT", () => server.kill("SIGINT"));
process.on("SIGTERM", () => server.kill("SIGTERM"));
server.on("close", (code) => process.exit(code || 0));
