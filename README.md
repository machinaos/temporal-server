# temporal-server

Temporal workflow server packaged as an npm module. Downloads the official [Temporal CLI](https://github.com/temporalio/cli) binary which includes a development server with SQLite persistence and built-in Web UI. No Docker, no external databases.

## Install

```bash
npm install temporal-server
```

The postinstall script downloads the Temporal CLI binary (~60MB). Skip with `TEMPORAL_SERVER_SKIP_BINARY_DOWNLOAD=1`.

### Supported Platforms

| OS      | Architecture   |
|---------|---------------|
| Linux   | amd64, arm64  |
| macOS   | amd64, arm64  |
| Windows | amd64, arm64  |
| WSL     | amd64, arm64  |

WSL is auto-detected. Set `TEMPORAL_BINARY_PLATFORM=windows` to force the Windows binary.

## Usage

### CLI

```bash
temporal-server start       # Start server in background
temporal-server start -f    # Start in foreground
temporal-server stop        # Stop server
temporal-server restart     # Restart
temporal-server status      # Check if running (all 4 ports)
temporal-server api         # Start server in foreground
temporal-server clean       # Stop + remove bin/, data/, node_modules/
```

### npm scripts

```bash
npm start          # Start server
npm stop           # Stop
npm run restart    # Restart
npm run status     # Check status (gRPC, HTTP, UI, Metrics)
npm run api        # Start in foreground
npm run clean      # Full cleanup
```

## Ports

| Service       | Port | URL                    |
|---------------|------|------------------------|
| gRPC          | 7233 | localhost:7233          |
| HTTP API / UI | 8233 | http://localhost:8233   |
| UI (alt)      | 8080 | http://localhost:8080   |
| Metrics       | 9090 | http://localhost:9090   |

## Configuration

All settings in [`configs/server.json`](configs/server.json):

```json
{
  "ip": "127.0.0.1",
  "port": 7233,
  "httpPort": 8233,
  "uiPort": 8080,
  "metricsPort": 9090,
  "dbPath": "data/temporal.db",
  "namespaces": ["default"],
  "logLevel": "warn"
}
```

Data persists in `data/temporal.db` (SQLite, created automatically).

## Testing

Requires the `temporalio` Python package (`pip install temporalio`).

```bash
npm start
python test_temporal.py
npm stop
```

Tests HTTP API, Web UI, metrics endpoint, and executes a sample workflow.

## How It Works

Under the hood, `npm start` runs:
```
temporal server start-dev --db-filename data/temporal.db --port 7233 --http-port 8233 --ui-port 8080 --metrics-port 9090 --namespace default
```

The official Temporal CLI handles everything in a single process: gRPC frontend, HTTP API, Web UI, and metrics.

## Use as a Dependency

```json
{
  "dependencies": {
    "temporal-server": "^0.0.5"
  },
  "scripts": {
    "temporal:start": "temporal-server start",
    "temporal:stop": "temporal-server stop",
    "temporal:status": "temporal-server status"
  }
}
```

Connect your Temporal client to `localhost:7233`.

## License

MIT
