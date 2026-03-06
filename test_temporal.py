"""
Test suite for the Temporal server.
Reads config from configs/server.json, checks HTTP API, UI, and runs a workflow.

Usage:
    python test_temporal.py
    python test_temporal.py --server localhost:7233
"""

import argparse
import asyncio
import json
import sys
import urllib.request
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "configs" / "server.json").read_text())


def check(name, fn):
    try:
        result = fn()
        print(f"  [PASS] {name}")
        return True
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        return False


def http_get(url, timeout=5):
    return urllib.request.urlopen(url, timeout=timeout).read()


# --- Workflow definition ---

@dataclass
class AddInput:
    a: int
    b: int


@activity.defn
async def add_activity(inp: AddInput) -> int:
    return inp.a + inp.b


@workflow.defn
class AddWorkflow:
    @workflow.run
    async def run(self, inp: AddInput) -> int:
        return await workflow.execute_activity(
            add_activity, inp, start_to_close_timeout=timedelta(seconds=10),
        )


# --- Tests ---

async def run_tests(server_address: str) -> bool:
    ip = CONFIG["ip"]
    results = []

    print("Health checks:")
    results.append(check("HTTP API", lambda: http_get(f"http://{ip}:{CONFIG['httpPort']}/api/v1/namespaces")))
    results.append(check("Web UI", lambda: http_get(f"http://{ip}:{CONFIG['uiPort']}")))
    results.append(check("Metrics", lambda: http_get(f"http://{ip}:{CONFIG['metricsPort']}/metrics")))

    print("Workflow test:")
    try:
        client = await Client.connect(server_address)
        async with Worker(client, task_queue="test-queue", workflows=[AddWorkflow], activities=[add_activity]):
            result = await client.execute_workflow(
                AddWorkflow.run, AddInput(a=40, b=2), id="test-add", task_queue="test-queue",
            )
            ok = result == 42
            print(f"  [{'PASS' if ok else 'FAIL'}] AddWorkflow: 40 + 2 = {result}")
            results.append(ok)
    except Exception as e:
        print(f"  [FAIL] AddWorkflow: {e}")
        results.append(False)

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} tests passed")
    return all(results)


def main():
    default_addr = f"{CONFIG['ip']}:{CONFIG['port']}"
    parser = argparse.ArgumentParser(description="Test Temporal server")
    parser.add_argument("--server", default=default_addr, help=f"Server address (default: {default_addr})")
    args = parser.parse_args()

    ok = asyncio.run(run_tests(args.server))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
