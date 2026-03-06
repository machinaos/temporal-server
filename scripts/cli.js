#!/usr/bin/env node
import { program } from 'commander';
import chalk from 'chalk';
import killPort from 'kill-port';
import { Socket } from 'net';
import { spawn } from 'child_process';
import { existsSync, rmSync, unlinkSync, readFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const pkg = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'));
const cfg = JSON.parse(readFileSync(join(ROOT, 'configs', 'server.json'), 'utf8'));
const EXT = process.platform === 'win32' ? '.exe' : '';
const BIN = join(ROOT, 'bin', `${pkg.config.binaryName}${EXT}`);

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

function buildArgs() {
  return [
    'server', 'start-dev',
    '--db-filename', join(ROOT, cfg.dbPath),
    '--ip', cfg.ip,
    '--port', String(cfg.port),
    '--http-port', String(cfg.httpPort),
    '--ui-port', String(cfg.uiPort),
    '--metrics-port', String(cfg.metricsPort),
    '--log-level', cfg.logLevel,
    ...cfg.namespaces.flatMap(ns => ['--namespace', ns]),
  ];
}

async function start(opts = {}) {
  if (await portUp(cfg.port)) { log(`Already running on ${cfg.port}`, 'yellow'); return; }
  if (!existsSync(BIN)) { log('Binary not found. Run: npm install', 'red'); process.exit(1); }

  const fg = opts.foreground;
  const proc = spawn(BIN, buildArgs(), { cwd: ROOT, detached: !fg, stdio: fg ? 'inherit' : 'ignore' });

  if (fg) {
    process.on('SIGINT', () => proc.kill('SIGINT'));
    process.on('SIGTERM', () => proc.kill('SIGTERM'));
    proc.on('close', code => process.exit(code || 0));
  } else {
    proc.unref();
    if (await wait(cfg.port)) log(`Server: localhost:${cfg.port}`, 'green');
    else { log('Server failed to start', 'red'); return; }
    if (await wait(cfg.uiPort, 10000)) log(`UI: http://localhost:${cfg.uiPort}`, 'green');
  }
}

async function stop() {
  for (const [port, name] of [[cfg.port, 'Server'], [cfg.uiPort, 'UI']]) {
    try { await killPort(port); log(`${name} stopped`, 'green'); }
    catch { log(`${name} not running`, 'yellow'); }
  }
}

async function status() {
  for (const [port, name] of [[cfg.port, 'Server'], [cfg.uiPort, 'UI']]) {
    const up = await portUp(port);
    log(`${name} (${port}): ${up ? 'UP' : 'DOWN'}`, up ? 'green' : 'red');
  }
}

async function clean() {
  await stop();
  for (const d of [join(ROOT, 'bin'), join(ROOT, 'data'), join(ROOT, 'node_modules')]) {
    if (existsSync(d)) { rmSync(d, { recursive: true }); log(`Removed ${d.replace(ROOT, '').slice(1)}`, 'green'); }
  }
  const lock = join(ROOT, 'package-lock.json');
  if (existsSync(lock)) { unlinkSync(lock); log('Removed package-lock.json', 'green'); }
}

program.name('temporal-server').version(pkg.version);
program.command('start').description('Start server').option('-f, --foreground', 'Run in foreground').action(start);
program.command('stop').description('Stop server').action(stop);
program.command('restart').description('Restart server').action(async () => { await stop(); await sleep(2000); await start(); });
program.command('status').description('Show status').action(status);
program.command('clean').description('Full cleanup').action(clean);
program.parse();
