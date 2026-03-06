# Temporal Server

Temporal workflow server using the official [Temporal CLI](https://github.com/temporalio/cli) with SQLite persistence. No Docker required. npm is used for packaging and binary management.

## Structure

```
temporal/
├── package.json               # npm package config + CLI binary version/URL
├── scripts/
│   ├── cli.js                 # CLI: start/stop/restart/status/clean
│   └── download-binary.js     # Postinstall: downloads official Temporal CLI binary
├── configs/
│   └── server.json            # Server config (ports, db path, namespaces, log level)
├── bin/                       # Downloaded Temporal CLI binary (gitignored)
├── data/                      # SQLite database (gitignored)
└── test_temporal.py           # Python test: health checks + workflow execution
```

## Commands

```bash
npm start              # Start server (background)
npm stop               # Stop server
npm run status         # Check if running
npm run restart        # Restart
npm run clean          # Stop + remove bin/, data/, node_modules/
python test_temporal.py  # Run tests (requires temporalio pip package)
```

## How It Works

- `npm install` downloads the official Temporal CLI binary (~60MB compressed) via postinstall
- `npm start` runs `temporal server start-dev` with flags from `configs/server.json`
- Single process handles gRPC, HTTP API, Web UI, and metrics
- Data persists in `data/temporal.db` (SQLite)

## Ports

| Service   | Port | Protocol |
|-----------|------|----------|
| gRPC      | 7233 | gRPC     |
| HTTP API  | 8233 | HTTP     |
| Web UI    | 8080 | HTTP     |
| Metrics   | 9090 | HTTP     |

All ports configurable in `configs/server.json`.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `TEMPORAL_SERVER_SKIP_BINARY_DOWNLOAD=1` | Skip binary download during npm install |
| `TEMPORAL_BINARY_PLATFORM=windows` | Force Windows binary download (useful in WSL) |

## MachinaOs Integration

`.env`:
```env
TEMPORAL_ENABLED=true
TEMPORAL_SERVER_ADDRESS=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=machina-tasks
```

`package.json`:
```json
"dependencies": { "temporal-server": "file:../temporal" }
"scripts": { "temporal:start": "temporal-server start" }
```

All Temporal workflow/activity code lives in MachinaOs:
```
MachinaOs/server/services/temporal/
├── workflow.py      # MachinaWorkflow orchestrator
├── activities.py    # Class-based activities with aiohttp pooling
├── worker.py        # TemporalWorkerManager
├── executor.py      # TemporalExecutor interface
├── client.py        # Client wrapper
└── ws_client.py     # WebSocket connection pool
```
