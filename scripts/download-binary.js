#!/usr/bin/env node
import { chmodSync, existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import Downloader from 'nodejs-file-downloader';
import decompress from 'decompress';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const BIN = resolve(ROOT, 'bin');
const pkg = JSON.parse(readFileSync(resolve(ROOT, 'package.json'), 'utf-8'));
const { binaryName, cliVersion, downloadUrl } = pkg.config;

const OS = { win32: 'windows', darwin: 'darwin', linux: 'linux' };
const ARCH = { x64: 'amd64', arm64: 'arm64' };

function isWSL() {
  try { return readFileSync('/proc/version', 'utf8').toLowerCase().includes('microsoft'); }
  catch { return false; }
}

function getPlatform() {
  let os = OS[process.platform], arch = ARCH[process.arch];
  if (!os || !arch) return null;
  // WSL: Node reports linux but user may want windows binary via env override
  if (isWSL() && process.env.TEMPORAL_BINARY_PLATFORM === 'windows') {
    os = 'windows';
  }
  const ext = os === 'windows' ? 'zip' : 'tar.gz';
  const binExt = os === 'windows' ? '.exe' : '';
  return { os, arch, ext, binExt };
}

if (process.env.TEMPORAL_SERVER_SKIP_BINARY_DOWNLOAD === '1') process.exit(0);

const p = getPlatform();
if (!p) { console.error(`Unsupported platform: ${process.platform}/${process.arch}`); process.exit(1); }

const dest = resolve(BIN, `${binaryName}${p.binExt}`);
const versionFile = resolve(BIN, '.version');

if (existsSync(dest)) {
  try {
    const installed = readFileSync(versionFile, 'utf8').trim();
    if (installed === cliVersion) { console.log(`${binaryName} v${cliVersion}: already installed`); process.exit(0); }
    console.log(`Upgrading ${binaryName} v${installed} -> v${cliVersion}`);
    unlinkSync(dest);
  } catch {
    console.log(`${binaryName}: already exists`); process.exit(0);
  }
}

const url = downloadUrl.replace(/\{version\}/g, cliVersion).replace('{os}', p.os).replace('{arch}', p.arch).replace('{ext}', p.ext);
mkdirSync(BIN, { recursive: true });

console.log(`Downloading Temporal CLI v${cliVersion} (${p.os}/${p.arch})${isWSL() ? ' [WSL]' : ''}...`);
const { filePath } = await new Downloader({
  url, directory: BIN, cloneFiles: false, maxAttempts: 3,
  onProgress: (pct) => process.stdout.write(`\rDownloading: ${pct}%`),
}).download();
console.log('');

await decompress(filePath, BIN, { filter: f => f.path.startsWith(binaryName) });
try { unlinkSync(filePath); } catch {}

if (process.platform !== 'win32') {
  try { chmodSync(dest, 0o755); } catch {}
}

writeFileSync(versionFile, cliVersion, 'utf8');
console.log('Done');
