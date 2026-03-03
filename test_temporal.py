"""
Minimal test for a custom Temporal server binary.
Connects to localhost:7233, runs a simple workflow with an activity, prints the result.

Usage:
    python test_temporal.py
    python test_temporal.py --server localhost:7233
"""

import argparse
import asyncio
from dataclasses import dataclass
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker


@dataclass
class AddInput:
    a: int
    b: int


@activity.defn
async def add_activity(input: AddInput) -> int:
    activity.logger.info("Adding %d + %d", input.a, input.b)
    return input.a + input.b


@workflow.defn
class AddWorkflow:
    @workflow.run
    async def run(self, input: AddInput) -> int:
        workflow.logger.info("Running AddWorkflow with %s", input)
        return await workflow.execute_activity(
            add_activity,
            input,
            start_to_close_timeout=timedelta(seconds=10),
        )


async def run_test(server_address: str, task_queue: str) -> None:
    print(f"Connecting to Temporal server at {server_address}...")
    client = await Client.connect(server_address)
    print("Connected successfully.")

    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[AddWorkflow],
        activities=[add_activity],
    ):
        print("Worker started. Executing workflow...")
        result = await client.execute_workflow(
            AddWorkflow.run,
            AddInput(a=40, b=2),
            id="test-add-workflow",
            task_queue=task_queue,
        )
        print(f"Workflow result: 40 + 2 = {result}")

    print("Test completed successfully.")


def main():
    parser = argparse.ArgumentParser(description="Test a Temporal server with a simple workflow")
    parser.add_argument("--server", default="localhost:7233", help="Temporal server address")
    parser.add_argument("--task-queue", default="test-task-queue", help="Task queue name")
    args = parser.parse_args()

    asyncio.run(run_test(args.server, args.task_queue))


if __name__ == "__main__":
    main()
