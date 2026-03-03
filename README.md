# temporal-server

Temporal workflow server with SQLite persistence, packaged as an npm module. No Docker, no external databases -- a single Go binary with an embedded SQLite backend.

## Install

```bash
npm install temporal-server
```

The postinstall script automatically downloads the pre-built binary for your platform. Skip with `TEMPORAL_SERVER_SKIP_BINARY_DOWNLOAD=1`.

### Supported Platforms

| OS      | Architecture |
|---------|-------------|
| Linux   | amd64, arm64 |
| macOS   | amd64, arm64 |
| Windows | amd64        |

## Usage

### CLI

```bash
temporal-server start       # Start server + UI (background)
temporal-server start -f    # Start in foreground
temporal-server stop        # Stop all processes
temporal-server restart     # Restart all
temporal-server status      # Check if running
temporal-server build       # Build from Go source (requires Go 1.26+)
temporal-server clean       # Stop + remove bin/, data/, node_modules/
```

### npm scripts

```bash
npm start          # Start server + UI
npm stop           # Stop all
npm run restart    # Restart
npm run status     # Check status
npm run build      # Build from source
npm run clean      # Full cleanup
```

## Ports

| Service        | Port | Protocol |
|---------------|------|----------|
| gRPC Frontend | 7233 | gRPC     |
| HTTP Frontend | 8233 | HTTP     |
| Web UI        | 8080 | HTTP     |
| Metrics       | 9090 | HTTP     |

## Configuration

All configuration lives in `configs/`:

- **`configs/server.json`** -- Server settings (ports, persistence, namespaces)
- **`configs/ui.yaml`** -- Web UI settings (port, gRPC address)

Data is stored in `data/temporal.db` (SQLite, created automatically).

## Build from Source

Requires Go 1.26+:

```bash
npm run build
```

This compiles the server binary to `bin/` and installs the Temporal UI server.

## Use as a Dependency

Add to your project's `package.json`:

```json
{
  "dependencies": {
    "temporal-server": "^0.0.1"
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
