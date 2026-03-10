"""
FastAPI backend for the Temporal workflow UI.
Runs a Temporal worker and exposes endpoints to trigger workflow scenarios.
Serves the React build from ui/dist/ if present.

Started by start.js -- not intended to be run directly.
"""

import asyncio
import json
import random
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from temporalio.client import Client
from temporalio.worker import Worker

from test import (
    IP, GRPC_PORT, HTTP_PORT, UI_PORT, TASK_QUEUE,
    ALL_WORKFLOWS, ALL_ACTIVITIES,
    Order, NewUser, PipelineConfig, ExpenseReport, BatchJob,
    OrderFulfillmentWorkflow, UserOnboardingWorkflow,
    DataPipelineWorkflow, ExpenseApprovalWorkflow,
    BatchProcessingWorkflow,
)

client: Client = None
worker_task: asyncio.Task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, worker_task
    client = await Client.connect(f"{IP}:{GRPC_PORT}")
    w = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=ALL_WORKFLOWS,
        activities=ALL_ACTIVITIES,
    )
    worker_task = asyncio.create_task(w.run())
    print(f"Worker started on queue '{TASK_QUEUE}'")
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Temporal Workflow UI", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def wf_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@app.get("/api/info")
async def info():
    return {
        "grpc": f"{IP}:{GRPC_PORT}",
        "http_api": f"http://{IP}:{HTTP_PORT}",
        "ui": f"http://{IP}:{UI_PORT}",
        "task_queue": TASK_QUEUE,
    }


@app.get("/api/workflows")
async def list_workflows():
    import urllib.request
    body = urllib.request.urlopen(
        f"http://{IP}:{HTTP_PORT}/api/v1/namespaces/default/workflows",
        timeout=5,
    ).read().decode()
    return json.loads(body)


@app.post("/api/order/success")
async def order_success():
    order = Order(
        order_id=f"ORD-{uuid.uuid4().hex[:6]}", customer_id="CUST-42",
        items=[{"sku": "WIDGET-1", "qty": 2, "price": 29.99},
               {"sku": "GADGET-3", "qty": 1, "price": 49.99}],
        total=109.97, shipping_address="123 Main St",
    )
    result = await client.execute_workflow(
        OrderFulfillmentWorkflow.run, order,
        id=wf_id("order-ok"), task_queue=TASK_QUEUE,
    )
    return {"order_id": result.order_id, "status": result.status,
            "steps": result.steps, "tracking": result.tracking_number}


@app.post("/api/order/failure")
async def order_failure():
    order = Order(
        order_id=f"ORD-{uuid.uuid4().hex[:6]}", customer_id="CUST-99",
        items=[{"sku": "EXPENSIVE", "qty": 1, "price": 15000.00}],
        total=15000.00, shipping_address="456 Oak Ave",
    )
    result = await client.execute_workflow(
        OrderFulfillmentWorkflow.run, order,
        id=wf_id("order-fail"), task_queue=TASK_QUEUE,
    )
    return {"order_id": result.order_id, "status": result.status,
            "steps": result.steps, "tracking": result.tracking_number}


@app.post("/api/onboarding/start")
async def onboarding_start():
    user = NewUser(
        user_id=f"USR-{uuid.uuid4().hex[:6]}",
        email=f"user-{uuid.uuid4().hex[:4]}@test.com", plan="pro",
    )
    wid = wf_id("onboard")
    await client.start_workflow(
        UserOnboardingWorkflow.run, user,
        id=wid, task_queue=TASK_QUEUE,
    )
    return {"workflow_id": wid, "user": user.__dict__}


@app.post("/api/onboarding/{workflow_id}/verify")
async def onboarding_verify(workflow_id: str):
    handle = client.get_workflow_handle(workflow_id)
    await handle.signal(UserOnboardingWorkflow.verify_email)
    result = await handle.result()
    return {"status": result.status, "resources": result.provisioned_resources,
            "timeline": result.timeline}


@app.post("/api/pipeline/run")
async def pipeline_run():
    config = PipelineConfig(
        pipeline_id=f"PIPE-{uuid.uuid4().hex[:6]}",
        sources=["database", "flaky_api", "csv_export"], batch_size=100,
    )
    result = await client.execute_workflow(
        DataPipelineWorkflow.run, config,
        id=wf_id("pipeline"), task_queue=TASK_QUEUE,
    )
    return {"pipeline_id": result.pipeline_id, "records": result.records_processed,
            "sources": result.sources_completed, "valid": result.validation_passed}


@app.post("/api/expense/start")
async def expense_start():
    report = ExpenseReport(
        report_id=f"EXP-{uuid.uuid4().hex[:6]}", submitter="alice",
        amount=round(random.uniform(50, 500), 2),
        description="conference travel", category="travel",
        approval_timeout_seconds=300,  # 5 minutes for interactive use
    )
    wid = wf_id("expense")
    await client.start_workflow(
        ExpenseApprovalWorkflow.run, report,
        id=wid, task_queue=TASK_QUEUE,
    )
    return {"workflow_id": wid, "report": report.__dict__}


@app.post("/api/expense/{workflow_id}/approve")
async def expense_approve(workflow_id: str):
    handle = client.get_workflow_handle(workflow_id)
    try:
        await handle.signal(ExpenseApprovalWorkflow.approve, "manager_bob")
        result = await handle.result()
        return {"status": result.status, "approved_by": result.approved_by,
                "timeline": result.timeline}
    except Exception as e:
        return {"status": "ERROR", "error": str(e), "timeline": []}


@app.post("/api/expense/{workflow_id}/reject")
async def expense_reject(workflow_id: str):
    handle = client.get_workflow_handle(workflow_id)
    try:
        await handle.signal(ExpenseApprovalWorkflow.reject, "manager_bob")
        result = await handle.result()
        return {"status": result.status, "approved_by": result.approved_by,
                "timeline": result.timeline}
    except Exception as e:
        return {"status": "ERROR", "error": str(e), "timeline": []}


@app.post("/api/batch/run")
async def batch_run():
    items = [f"item-{i}" for i in range(25)]
    job = BatchJob(job_id=f"BATCH-{uuid.uuid4().hex[:6]}", items=items, batch_size=5)
    result = await client.execute_workflow(
        BatchProcessingWorkflow.run, job,
        id=wf_id("batch"), task_queue=TASK_QUEUE,
    )
    return {"job_id": result.job_id, "processed": result.total_processed,
            "status": result.status}


# --- Serve React static build ---

UI_DIR = Path(__file__).parent / "ui" / "dist"

if UI_DIR.exists():
    app.mount("/assets", StaticFiles(directory=UI_DIR / "assets"), name="static")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        file = UI_DIR / path
        if path and file.exists() and file.is_file():
            return FileResponse(file)
        return FileResponse(UI_DIR / "index.html")
