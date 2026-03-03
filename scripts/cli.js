#!/usr/bin/env node
import { program } from 'commander';
import chalk from 'chalk';
import { execa } from 'execa';
import killPort from 'kill-port';
import { Socket } from 'net';
import { execSync, spawn } from 'child_process';
import { existsSync, statSync, mkdirSync, rmSync, unlinkSync, readFileSync, copyFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const pkg = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'));
const BIN_DIR = join(ROOT, 'bin');
const EXT = process.platform === 'win32' ? '.exe' : '';
const SERVER_BIN = join(BIN_DIR, `${pkg.config.binaryName}${EXT}`);
const UI_BIN = join(BIN_DIR, `${pkg.config.uiBinaryName}${EXT}`);

// Read ports from config files
function loadConfig() {
  const serverCfg = JSON.parse(readFileSync(join(ROOT, 'configs', 'server.json'), 'utf8'));
  let uiPort = null;
  const uiPath = join(ROOT, 'configs', 'ui.yaml');
  if (existsSync(uiPath)) {
    const match = readFileSync(uiPath, 'utf8').match(/^port:\s*(\d+)/m);
    if (match) uiPort = parseInt(match[1], 10);
  }
  return {
    grpcPort: serverCfg.services.frontend.grpcPort,
    uiPort,
  };
}

const log = (m, c = 'blue') => console.log(chalk[c](m));
const sleep = ms => new Promise(r => setTimeout(r, ms));

const portUp = port => new Promise(r => {
  const s = new Socket();
  s.setTimeout(2000);
  s.on('connect', () => { s.destroy(); r(true); });
  s.on('timeout', () => { s.destroy(); r(false); });
  s.on('error', () => r(false));
  s.connect(port, '127.0.0.1');
});

const wait = async (port, ms = 30000) => {
  const t = Date.now();
  while (Date.now() - t < ms) { if (await portUp(port)) return true; await sleep(500); }
  return false;
};

const kill = async (port, name) => {
  try { await killPort(port); log(`${name} stopped`, 'green'); }
  catch { log(`${name} not running`, 'yellow'); }
};

async function start(opts = {}) {
  const cfg = loadConfig();
  if (await portUp(cfg.grpcPort)) { log(`Already running on ${cfg.grpcPort}`, 'yellow'); return; }
  if (!existsSync(SERVER_BIN)) { log('Binary not found. Run: npm run build', 'red'); process.exit(1); }

  const configPath = join(ROOT, 'configs', 'server.json');
  const fg = opts.foreground;
  const stdio = fg ? 'inherit' : 'ignore';

  const serverProc = spawn(SERVER_BIN, ['--config', configPath], { cwd: ROOT, detached: !fg, stdio });
  if (!fg) serverProc.unref();

  let uiProc = null;
  if (existsSync(UI_BIN) && cfg.uiPort) {
    uiProc = spawn(UI_BIN, ['--config', join(ROOT, 'configs'), '--env', 'ui', 'start'], { cwd: ROOT, detached: !fg, stdio });
    if (!fg) uiProc.unref();
  }

  if (fg) {
    process.on('SIGINT', () => { serverProc.kill('SIGINT'); uiProc?.kill('SIGINT'); });
    process.on('SIGTERM', () => { serverProc.kill('SIGTERM'); uiProc?.kill('SIGTERM'); });
    serverProc.on('close', code => { uiProc?.kill('SIGINT'); process.exit(code || 0); });
  } else {
    if (await wait(cfg.grpcPort)) log(`Server: localhost:${cfg.grpcPort}`, 'green');
    else { log('Server failed to start', 'red'); return; }
    if (uiProc && cfg.uiPort && await wait(cfg.uiPort, 10000)) log(`UI: http://localhost:${cfg.uiPort}`, 'green');
  }
}

async function stop() {
  const cfg = loadConfig();
  await kill(cfg.grpcPort, 'Server');
  if (cfg.uiPort) await kill(cfg.uiPort, 'UI');
}

async function status() {
  const cfg = loadConfig();
  const s = await portUp(cfg.grpcPort);
  log(`Server (${cfg.grpcPort}): ${s ? 'UP' : 'DOWN'}`, s ? 'green' : 'red');
  if (cfg.uiPort) {
    const u = await portUp(cfg.uiPort);
    log(`UI     (${cfg.uiPort}): ${u ? 'UP' : 'DOWN'}`, u ? 'green' : 'red');
  }
}

async function build() {
  if (!existsSync(BIN_DIR)) mkdirSync(BIN_DIR, { recursive: true });

  if (existsSync(SERVER_BIN)) {
    log(`Server: ${(statSync(SERVER_BIN).size / 1048576).toFixed(1)}MB`, 'green');
  } else {
    log('Building server...', 'blue');
    await execa('go', ['build', '-o', SERVER_BIN, '.'], { cwd: join(ROOT, pkg.config.goSource), stdio: 'inherit' });
    log(`Server: ${(statSync(SERVER_BIN).size / 1048576).toFixed(1)}MB`, 'green');
  }

  if (existsSync(UI_BIN)) {
    log(`UI: ${(statSync(UI_BIN).size / 1048576).toFixed(1)}MB`, 'green');
  } else {
    log('Building UI server...', 'blue');
    try {
      await execa('go', ['install', pkg.config.uiPackage], { stdio: 'inherit' });
      const gobin = join(execSync('go env GOPATH', { encoding: 'utf8' }).trim(), 'bin', `server${EXT}`);
      if (existsSync(gobin)) { copyFileSync(gobin, UI_BIN); log(`UI: ${(statSync(UI_BIN).size / 1048576).toFixed(1)}MB`, 'green'); }
    } catch (e) { log(`UI build failed: ${e.message}`, 'yellow'); }
  }
}

async function clean() {
  await stop();
  for (const d of [BIN_DIR, join(ROOT, 'data'), join(ROOT, 'node_modules')]) {
    if (existsSync(d)) { rmSync(d, { recursive: true }); log(`Removed ${d.replace(ROOT, '').slice(1)}`, 'green'); }
  }
  const lock = join(ROOT, 'package-lock.json');
  if (existsSync(lock)) { unlinkSync(lock); log('Removed package-lock.json', 'green'); }
}

program.name('temporal-server').version(pkg.version);
program.command('start').description('Start server + UI').option('-f, --foreground', 'Run in foreground').action(start);
program.command('stop').description('Stop all').action(stop);
program.command('restart').description('Restart all').action(async () => { await stop(); await sleep(2000); await start(); });
program.command('status').description('Show status').action(status);
program.command('build').description('Build binaries (requires Go)').action(build);
program.command('clean').description('Full cleanup').action(clean);
program.parse();
