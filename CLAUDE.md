# Temporal Server

npm package wrapping the official [Temporal CLI](https://github.com/temporalio/cli) with SQLite persistence. No Docker required. Published as `temporal-server` on npm.

## Structure

```
temporal/
├── package.json               # npm package config + CLI binary version/URL
├── scripts/
│   ├── cli.js                 # CLI: start/stop/restart/status/clean/api
│   └── download-binary.js     # Postinstall: downloads official Temporal CLI binary
├── configs/
│   └── server.json            # Server config (ports, db path, namespaces, log level)
├── test-service/              # Test app: workflow scenarios + React dashboard
│   ├── server.py              # Python worker with test workflows/activities
│   ├── start.js               # Launcher script
│   ├── test.py                # Test runner
│   └── ui/                    # React dashboard
├── bin/                       # Downloaded Temporal CLI binary (gitignored)
├── data/                      # SQLite database (gitignored)
├── test_temporal.py           # Python test: health checks + workflow execution
└── workflow.json              # Sample workflow definition
```

## Commands

```bash
npm start              # Start server (background)
npm stop               # Stop server
npm run status         # Check if running
npm run restart        # Restart
npm run api            # Start API server (foreground)
npm run clean          # Stop + remove bin/, data/, node_modules/
python test_temporal.py  # Run tests (requires temporalio pip package)
```

## How It Works

- `npm install` downloads the official Temporal CLI binary (~60MB compressed) via postinstall
- `npm start` runs `temporal server start-dev` with flags from `configs/server.json`
- Single process handles gRPC, HTTP API, Web UI, and metrics
- Data persists in `data/temporal.db` (SQLite)
- Version: CLI v1.6.1, package v0.0.4 (tag)

## Ports

| Service       | Port | URL                    |
|---------------|------|------------------------|
| gRPC          | 7233 | localhost:7233          |
| HTTP API / UI | 8233 | http://localhost:8233   |
| UI (alt)      | 8080 | http://localhost:8080   |
| Metrics       | 9090 | http://localhost:9090   |

All ports configurable in `configs/server.json`.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `TEMPORAL_SERVER_SKIP_BINARY_DOWNLOAD=1` | Skip binary download during npm install |
| `TEMPORAL_BINARY_PLATFORM=windows` | Force Windows binary download (useful in WSL) |

## MachinaOs Integration

Install as npm dependency (not local file reference):

`package.json`:
```json
"dependencies": { "temporal-server": "^0.0.4" }
"scripts": {
  "temporal:start": "temporal-server start",
  "temporal:stop": "temporal-server stop",
  "temporal:status": "temporal-server status"
}
```

`.env`:
```env
TEMPORAL_ENABLED=true
TEMPORAL_SERVER_ADDRESS=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=machina-tasks
```

### Execution Architecture

MachinaOs uses a 3-tier fallback: Temporal -> Parallel (Redis) -> Sequential.

Temporal workflow/activity code lives in MachinaOs:
```
MachinaOs/server/services/temporal/
├── workflow.py      # MachinaWorkflow - DAG orchestrator (FIRST_COMPLETED pattern)
├── activities.py    # NodeExecutionActivities - class-based with shared aiohttp session
├── worker.py        # TemporalWorkerManager + standalone worker for horizontal scaling
├── executor.py      # TemporalExecutor - drop-in replacement for WorkflowExecutor
├── client.py        # TemporalClientWrapper - connection lifecycle
└── ws_client.py     # WSConnectionPool (legacy, unused but kept)
```

Key patterns:
- Activities execute nodes via WebSocket to MachinaOs `/ws/internal` endpoint
- CONFIG_HANDLES (input-tools, input-memory, input-model, input-skill) are filtered out of workflow execution
- LangGraph handles AI agent tool-calling loops (separate concern, not replaced by Temporal)
