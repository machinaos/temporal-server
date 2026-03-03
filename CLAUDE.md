# Temporal Server

Custom Temporal workflow server with SQLite persistence. No Docker required.

## Structure

```
temporal/
├── package.json               # npm package: temporal-server
├── scripts/cli.js             # CLI (start/stop/status/build/clean)
├── src/go/                    # Go server source
│   ├── main.go
│   ├── go.mod
│   └── go.sum
├── bin/                       # Built binaries (gitignored)
├── configs/
│   ├── server.json            # Server config (ports, persistence, metrics)
│   └── ui.yaml                # UI server config
├── data/                      # SQLite data (gitignored)
└── test_temporal.py           # Test script
```

## Commands

```bash
npm start         # Start server + UI in background
npm stop          # Stop all
npm run status    # Check if running
npm run restart   # Restart all
npm run build     # Build Go binaries (requires Go)
npm run clean     # Full cleanup (stop, remove bin/, data/, node_modules/)
```

## Ports

- **7233** - gRPC (Temporal server)
- **8233** - HTTP API
- **8080** - Web UI (http://localhost:8080)

## Configuration

Ports and settings in `configs/server.json`. UI config in `configs/ui.yaml`.

## MachinaOs Integration

Set in MachinaOs `.env`:
```env
TEMPORAL_ENABLED=true
TEMPORAL_SERVER_ADDRESS=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=machina-tasks
```

Add to MachinaOs `package.json`:
```json
"dependencies": { "temporal-server": "file:../temporal" }
"scripts": { "temporal:start": "temporal-server start" }
```

## Implementation

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
