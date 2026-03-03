#!/usr/bin/env node
/**
 * Downloads pre-built binary from GitHub releases.
 * Called automatically during npm postinstall.
 * Skip: TEMPORAL_SERVER_SKIP_BINARY_DOWNLOAD=1 or binary already exists.
 */
import { createWriteStream, existsSync, mkdirSync, chmodSync, readFileSync, unlinkSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import https from 'https';
import http from 'http';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const BIN_DIR = resolve(ROOT, 'bin');
const pkg = JSON.parse(readFileSync(resolve(ROOT, 'package.json'), 'utf-8'));

// All config from package.json
const VERSION = pkg.version;
const BINARY_NAME = pkg.config.binaryName;
const GITHUB_REPO = pkg.repository.url.match(/github\.com\/(.+?)\.git/)?.[1];
const BASE_URL = `https://github.com/${GITHUB_REPO}/releases/download/v${VERSION}`;

function getPlatformInfo() {
  const osMap = { 'win32': 'windows', 'darwin': 'darwin', 'linux': 'linux' };
  const archMap = { 'x64': 'amd64', 'arm64': 'arm64' };
  const os = osMap[process.platform];
  const goarch = archMap[process.arch];
  if (!os || !goarch) return null;
  return { os, goarch, ext: process.platform === 'win32' ? '.exe' : '' };
}

function downloadFile(url, dest) {
  return new Promise((resolvePromise, reject) => {
    if (existsSync(dest)) try { unlinkSync(dest); } catch { /* ignore */ }

    const request = (currentUrl, redirects = 0) => {
      if (redirects > 5) { reject(new Error('Too many redirects')); return; }
      const protocol = currentUrl.startsWith('https') ? https : http;
      protocol.get(currentUrl, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          request(res.headers.location, redirects + 1); return;
        }
        if (res.statusCode === 404) { reject(new Error(`Binary not found: v${VERSION} may not have pre-built binaries`)); return; }
        if (res.statusCode !== 200) { reject(new Error(`HTTP ${res.statusCode}`)); return; }

        const file = createWriteStream(dest);
        const total = parseInt(res.headers['content-length'], 10);
        let downloaded = 0;
        res.on('data', (chunk) => {
          downloaded += chunk.length;
          if (total) process.stdout.write(`\r  Downloading: ${((downloaded / total) * 100).toFixed(1)}%`);
        });
        res.pipe(file);
        file.on('finish', () => { file.close(); console.log(' Done'); resolvePromise(); });
        file.on('error', (err) => { file.close(); try { unlinkSync(dest); } catch {} reject(err); });
      }).on('error', (err) => { try { unlinkSync(dest); } catch {} reject(err); });
    };
    request(url);
  });
}

async function main() {
  if (process.env.TEMPORAL_SERVER_SKIP_BINARY_DOWNLOAD === '1') {
    console.log(`[${pkg.name}] Skipping binary download`);
    return;
  }

  const info = getPlatformInfo();
  if (!info) { console.error(`[${pkg.name}] Unsupported platform: ${process.platform}/${process.arch}`); process.exit(1); }

  const { os, goarch, ext } = info;
  const remoteName = `${BINARY_NAME}-${os}-${goarch}${ext}`;
  const destPath = resolve(BIN_DIR, `${BINARY_NAME}${ext}`);

  if (existsSync(destPath)) { console.log(`[${pkg.name}] Binary already exists`); return; }

  console.log(`[${pkg.name}] Downloading v${VERSION} (${os}/${goarch})...`);
  if (!existsSync(BIN_DIR)) mkdirSync(BIN_DIR, { recursive: true });

  await downloadFile(`${BASE_URL}/${remoteName}`, destPath);
  if (process.platform !== 'win32') try { chmodSync(destPath, 0o755); } catch {}
  console.log(`[${pkg.name}] Binary installed: ${destPath}`);
}

main().catch((err) => {
  console.error(`[${pkg.name}] Binary download failed:`, err.message);
  process.exit(1);
});
