"""
Integration test for temporal-server as an npm dependency.
Tests real-world workflow patterns: order fulfillment with saga compensation,
user onboarding with signals/timers, parallel data pipeline, approval flow
with escalation, and long-running batch processing with heartbeats.

Requires: pip install temporalio

Usage:
    python test.py
    npm test
"""

import asyncio
import json
import random
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

from temporalio import activity, workflow
from temporalio.client import Client, WorkflowFailureError
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

ROOT = Path(__file__).parent
TEMPORAL_PKG = ROOT / "node_modules" / "temporal-server"
CFG = json.loads((TEMPORAL_PKG / "configs" / "server.json").read_text())

IP = CFG["ip"]
GRPC_PORT = CFG["port"]
HTTP_PORT = CFG["httpPort"]
UI_PORT = CFG["uiPort"]
METRICS_PORT = CFG["metricsPort"]

results = []


def pass_test(name, detail=""):
    print(f"  [PASS] {name}" + (f": {detail}" if detail else ""))
    results.append(True)


def fail_test(name, detail=""):
    print(f"  [FAIL] {name}" + (f": {detail}" if detail else ""))
    results.append(False)


def wf_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def port_up(port, timeout=2):
    try:
        s = socket.create_connection((IP, port), timeout=timeout)
        s.close()
        return True
    except (ConnectionRefusedError, OSError, TimeoutError):
        return False


def wait_for_port(port, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_up(port):
            return True
        time.sleep(0.5)
    return False


def http_get(url, timeout=5):
    return urllib.request.urlopen(url, timeout=timeout).read().decode()


def npm(*args):
    return subprocess.run(
        ["npm", *args], cwd=TEMPORAL_PKG,
        capture_output=True, text=True, shell=True,
    )


def start_server():
    print("Starting temporal-server...")
    npm("start")
    for port in [GRPC_PORT, HTTP_PORT, UI_PORT, METRICS_PORT]:
        if not wait_for_port(port):
            print(f"  ERROR: Port {port} did not come up within 30s")
            sys.exit(1)
    print("Server started.\n")


def stop_server():
    print("\nStopping temporal-server...")
    npm("stop")
    time.sleep(2)
    print("Server stopped.\n")


# --- Health checks ---


def test_grpc_port():
    if port_up(GRPC_PORT):
        pass_test("gRPC port", f"TCP connect to {GRPC_PORT}")
    else:
        fail_test("gRPC port", f"cannot connect to {GRPC_PORT}")


def test_http_api():
    try:
        body = http_get(f"http://{IP}:{HTTP_PORT}/api/v1/namespaces")
        data = json.loads(body)
        has_default = any(
            ns.get("namespaceInfo", {}).get("name") == "default"
            for ns in data.get("namespaces", [])
        )
        if has_default:
            pass_test("HTTP API", 'namespaces contain "default"')
        else:
            fail_test("HTTP API", "default namespace not found")
    except Exception as e:
        fail_test("HTTP API", str(e))


def test_web_ui():
    try:
        body = http_get(f"http://{IP}:{UI_PORT}")
        if "<!doctype" in body.lower() or "<html" in body.lower():
            pass_test("Web UI", "returns HTML")
        else:
            fail_test("Web UI", "not HTML")
    except Exception as e:
        fail_test("Web UI", str(e))


def test_metrics():
    try:
        body = http_get(f"http://{IP}:{METRICS_PORT}/metrics")
        if "# HELP" in body or "# TYPE" in body:
            pass_test("Metrics", "prometheus format")
        else:
            fail_test("Metrics", "no prometheus markers")
    except Exception as e:
        fail_test("Metrics", str(e))


def test_dashboard():
    try:
        body = http_get(f"http://{IP}:{UI_PORT}")
        if "<!doctype html" in body.lower() or "<html" in body.lower():
            pass_test("Dashboard HTML", "valid HTML document")
        else:
            fail_test("Dashboard HTML", "no HTML doctype")
        if "sveltekit" in body.lower() or "svelte" in body.lower():
            pass_test("Dashboard app", "SvelteKit app shell detected")
        else:
            fail_test("Dashboard app", "no SvelteKit markers")
    except Exception as e:
        fail_test("Dashboard content", str(e))


# ============================================================================
# Scenario 1: E-Commerce Order Fulfillment (Saga with compensation)
#
# Real pattern: place order -> validate inventory -> charge payment ->
# reserve shipping -> send confirmation. If any step fails, compensate
# all prior steps in reverse (refund, release inventory, cancel shipment).
# ============================================================================


@dataclass
class Order:
    order_id: str
    customer_id: str
    items: list[dict]  # [{"sku": "WIDGET-1", "qty": 2, "price": 29.99}, ...]
    total: float
    shipping_address: str


@dataclass
class OrderResult:
    order_id: str
    status: str
    steps: list[str]
    tracking_number: Optional[str] = None


@activity.defn
async def validate_inventory(order: Order) -> dict:
    # simulate inventory check across warehouses
    await asyncio.sleep(0.1)
    for item in order.items:
        if item["sku"] == "OUT-OF-STOCK":
            raise ApplicationError(
                f"Item {item['sku']} is out of stock",
                non_retryable=True,
            )
    return {
        "warehouse": "WAREHOUSE-EAST",
        "reservation_id": f"RES-{order.order_id}",
        "items_reserved": len(order.items),
    }


@activity.defn
async def charge_payment(order: Order) -> dict:
    await asyncio.sleep(0.1)
    if order.total > 10000:
        raise ApplicationError(
            f"Payment declined: amount ${order.total} exceeds limit",
            non_retryable=True,
        )
    return {
        "transaction_id": f"TXN-{uuid.uuid4().hex[:8]}",
        "amount_charged": order.total,
        "customer_id": order.customer_id,
    }


@activity.defn
async def reserve_shipping(order: Order) -> dict:
    await asyncio.sleep(0.1)
    return {
        "shipment_id": f"SHIP-{uuid.uuid4().hex[:8]}",
        "tracking_number": f"1Z{random.randint(100000, 999999)}",
        "carrier": "UPS",
        "estimated_days": 3,
    }


@activity.defn
async def send_order_confirmation(order: Order) -> str:
    await asyncio.sleep(0.05)
    return f"confirmation email sent to customer {order.customer_id}"


@activity.defn
async def release_inventory(reservation_id: str) -> str:
    await asyncio.sleep(0.05)
    return f"released reservation {reservation_id}"


@activity.defn
async def refund_payment(transaction_id: str) -> str:
    await asyncio.sleep(0.05)
    return f"refunded transaction {transaction_id}"


@activity.defn
async def cancel_shipment(shipment_id: str) -> str:
    await asyncio.sleep(0.05)
    return f"cancelled shipment {shipment_id}"


@workflow.defn
class OrderFulfillmentWorkflow:
    def __init__(self):
        self._status = "PENDING"
        self._steps: list[str] = []

    @workflow.run
    async def run(self, order: Order) -> OrderResult:
        compensations = []
        tracking = None

        try:
            # Step 1: validate and reserve inventory
            self._status = "VALIDATING_INVENTORY"
            inv = await workflow.execute_activity(
                validate_inventory, order,
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            self._steps.append(f"inventory reserved: {inv['reservation_id']}")
            compensations.append(("inventory", inv["reservation_id"]))

            # Step 2: charge payment
            self._status = "CHARGING_PAYMENT"
            payment = await workflow.execute_activity(
                charge_payment, order,
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            self._steps.append(f"payment charged: {payment['transaction_id']}")
            compensations.append(("payment", payment["transaction_id"]))

            # Step 3: reserve shipping
            self._status = "RESERVING_SHIPPING"
            shipping = await workflow.execute_activity(
                reserve_shipping, order,
                start_to_close_timeout=timedelta(seconds=10),
            )
            tracking = shipping["tracking_number"]
            self._steps.append(f"shipping reserved: {shipping['shipment_id']}")
            compensations.append(("shipping", shipping["shipment_id"]))

            # Step 4: send confirmation
            self._status = "CONFIRMING"
            conf = await workflow.execute_activity(
                send_order_confirmation, order,
                start_to_close_timeout=timedelta(seconds=10),
            )
            self._steps.append(conf)
            self._status = "FULFILLED"

        except Exception:
            # saga compensation: undo in reverse order
            self._status = "COMPENSATING"
            for comp_type, comp_id in reversed(compensations):
                if comp_type == "inventory":
                    r = await workflow.execute_activity(
                        release_inventory, comp_id,
                        start_to_close_timeout=timedelta(seconds=10),
                    )
                elif comp_type == "payment":
                    r = await workflow.execute_activity(
                        refund_payment, comp_id,
                        start_to_close_timeout=timedelta(seconds=10),
                    )
                elif comp_type == "shipping":
                    r = await workflow.execute_activity(
                        cancel_shipment, comp_id,
                        start_to_close_timeout=timedelta(seconds=10),
                    )
                else:
                    continue
                self._steps.append(f"COMPENSATED: {r}")
            self._status = "FAILED_COMPENSATED"

        return OrderResult(
            order_id=order.order_id,
            status=self._status,
            steps=self._steps,
            tracking_number=tracking,
        )

    @workflow.query
    def get_status(self) -> str:
        return self._status

    @workflow.query
    def get_steps(self) -> list[str]:
        return list(self._steps)


# ============================================================================
# Scenario 2: User Onboarding (signals, timers, child workflows)
#
# Real pattern: create account -> send verification email -> wait for user
# to click verify (signal) with timeout -> provision resources -> if user
# never verifies, send reminder then expire.
# ============================================================================


@dataclass
class NewUser:
    user_id: str
    email: str
    plan: str  # "free", "pro", "enterprise"


@dataclass
class OnboardingResult:
    user_id: str
    status: str
    provisioned_resources: list[str]
    timeline: list[str]


@activity.defn
async def create_user_account(user: NewUser) -> dict:
    await asyncio.sleep(0.05)
    return {"account_id": f"ACC-{user.user_id}", "created": True}


@activity.defn
async def send_verification_email(email: str) -> str:
    await asyncio.sleep(0.05)
    return f"verification email sent to {email}"


@activity.defn
async def send_reminder_email(email: str) -> str:
    await asyncio.sleep(0.05)
    return f"reminder email sent to {email}"


@activity.defn
async def provision_database(user_id: str) -> str:
    await asyncio.sleep(0.1)
    return f"db-{user_id}"


@activity.defn
async def provision_storage(user_id: str) -> str:
    await asyncio.sleep(0.1)
    return f"s3-{user_id}"


@activity.defn
async def provision_api_key(user_id: str) -> str:
    await asyncio.sleep(0.05)
    return f"key-{uuid.uuid4().hex[:12]}"


@activity.defn
async def send_welcome_email(email: str) -> str:
    await asyncio.sleep(0.05)
    return f"welcome email sent to {email}"


@activity.defn
async def cleanup_unverified_account(user_id: str) -> str:
    await asyncio.sleep(0.05)
    return f"cleaned up unverified account {user_id}"


@workflow.defn
class ProvisionResourcesWorkflow:
    """Child workflow: provisions resources in parallel based on plan."""

    @workflow.run
    async def run(self, user_id: str) -> list[str]:
        db, storage, key = await asyncio.gather(
            workflow.execute_activity(
                provision_database, user_id,
                start_to_close_timeout=timedelta(seconds=15),
            ),
            workflow.execute_activity(
                provision_storage, user_id,
                start_to_close_timeout=timedelta(seconds=15),
            ),
            workflow.execute_activity(
                provision_api_key, user_id,
                start_to_close_timeout=timedelta(seconds=10),
            ),
        )
        return [db, storage, key]


@workflow.defn
class UserOnboardingWorkflow:
    def __init__(self):
        self._verified = False
        self._status = "STARTED"
        self._timeline: list[str] = []

    @workflow.run
    async def run(self, user: NewUser) -> OnboardingResult:
        # create account
        self._status = "CREATING_ACCOUNT"
        await workflow.execute_activity(
            create_user_account, user,
            start_to_close_timeout=timedelta(seconds=10),
        )
        self._timeline.append("account created")

        # send verification email
        await workflow.execute_activity(
            send_verification_email, user.email,
            start_to_close_timeout=timedelta(seconds=10),
        )
        self._timeline.append("verification email sent")

        # wait for verification signal with timeout
        self._status = "AWAITING_VERIFICATION"
        try:
            await workflow.wait_condition(
                lambda: self._verified,
                timeout=timedelta(seconds=5),
            )
        except asyncio.TimeoutError:
            # send reminder, wait again briefly
            await workflow.execute_activity(
                send_reminder_email, user.email,
                start_to_close_timeout=timedelta(seconds=10),
            )
            self._timeline.append("reminder sent")
            try:
                await workflow.wait_condition(
                    lambda: self._verified,
                    timeout=timedelta(seconds=3),
                )
            except asyncio.TimeoutError:
                self._status = "EXPIRED"
                self._timeline.append("verification expired")
                await workflow.execute_activity(
                    cleanup_unverified_account, user.user_id,
                    start_to_close_timeout=timedelta(seconds=10),
                )
                self._timeline.append("account cleaned up")
                return OnboardingResult(
                    user_id=user.user_id, status="EXPIRED",
                    provisioned_resources=[], timeline=self._timeline,
                )

        self._timeline.append("email verified")

        # provision resources via child workflow (parallel)
        self._status = "PROVISIONING"
        resources = await workflow.execute_child_workflow(
            ProvisionResourcesWorkflow.run, user.user_id,
            id=f"provision-{workflow.info().workflow_id}",
        )
        self._timeline.append(f"provisioned {len(resources)} resources")

        # welcome email
        await workflow.execute_activity(
            send_welcome_email, user.email,
            start_to_close_timeout=timedelta(seconds=10),
        )
        self._timeline.append("welcome email sent")
        self._status = "COMPLETE"

        return OnboardingResult(
            user_id=user.user_id, status="COMPLETE",
            provisioned_resources=resources, timeline=self._timeline,
        )

    @workflow.signal
    async def verify_email(self) -> None:
        self._verified = True

    @workflow.query
    def get_status(self) -> str:
        return self._status

    @workflow.query
    def get_timeline(self) -> list[str]:
        return list(self._timeline)


# ============================================================================
# Scenario 3: Data Pipeline (parallel ETL, heartbeating, retries)
#
# Real pattern: fetch data from 3 sources in parallel -> transform each ->
# merge results -> validate -> persist. Activities heartbeat during long
# processing. Flaky sources retry with backoff.
# ============================================================================


@dataclass
class PipelineConfig:
    pipeline_id: str
    sources: list[str]  # ["api", "database", "csv"]
    batch_size: int


@dataclass
class PipelineResult:
    pipeline_id: str
    records_processed: int
    sources_completed: list[str]
    validation_passed: bool


_source_attempt: dict[str, int] = {}


@activity.defn
async def fetch_from_source(source: str) -> dict:
    # simulate flaky data source that stabilizes after retries
    key = f"fetch-{source}"
    _source_attempt[key] = _source_attempt.get(key, 0) + 1
    if source == "flaky_api" and _source_attempt[key] < 2:
        raise RuntimeError(f"connection timeout to {source}")

    activity.heartbeat(f"fetching from {source}")
    await asyncio.sleep(0.1)
    records = [{"source": source, "id": i, "value": random.randint(1, 100)}
               for i in range(5)]
    activity.heartbeat(f"fetched {len(records)} records from {source}")
    return {"source": source, "records": records}


@activity.defn
async def transform_records(data: dict) -> dict:
    source = data["source"]
    records = data["records"]
    activity.heartbeat(f"transforming {len(records)} records from {source}")
    await asyncio.sleep(0.1)
    transformed = []
    for r in records:
        transformed.append({
            **r,
            "value_normalized": r["value"] / 100.0,
            "processed": True,
        })
    return {"source": source, "records": transformed}


@activity.defn
async def merge_datasets(datasets: list[dict]) -> dict:
    all_records = []
    sources = []
    for ds in datasets:
        all_records.extend(ds["records"])
        sources.append(ds["source"])
    activity.heartbeat(f"merged {len(all_records)} records from {len(sources)} sources")
    return {"records": all_records, "sources": sources}


@activity.defn
async def validate_data(data: dict) -> dict:
    records = data["records"]
    invalid = [r for r in records if r.get("value_normalized", 0) < 0]
    return {
        "total": len(records),
        "valid": len(records) - len(invalid),
        "invalid": len(invalid),
        "passed": len(invalid) == 0,
    }


@activity.defn
async def persist_results(data: dict) -> str:
    records = data["records"]
    activity.heartbeat(f"persisting {len(records)} records")
    await asyncio.sleep(0.1)
    return f"persisted {len(records)} records to warehouse"


@workflow.defn
class DataPipelineWorkflow:
    def __init__(self):
        self._stage = "INIT"
        self._records_processed = 0

    @workflow.run
    async def run(self, config: PipelineConfig) -> PipelineResult:
        retry = RetryPolicy(
            initial_interval=timedelta(milliseconds=100),
            backoff_coefficient=2.0,
            maximum_attempts=4,
        )

        # parallel fetch from all sources
        self._stage = "FETCHING"
        raw_datasets = await asyncio.gather(
            *[
                workflow.execute_activity(
                    fetch_from_source, source,
                    start_to_close_timeout=timedelta(seconds=30),
                    heartbeat_timeout=timedelta(seconds=10),
                    retry_policy=retry,
                )
                for source in config.sources
            ]
        )

        # parallel transform
        self._stage = "TRANSFORMING"
        transformed = await asyncio.gather(
            *[
                workflow.execute_activity(
                    transform_records, ds,
                    start_to_close_timeout=timedelta(seconds=30),
                    heartbeat_timeout=timedelta(seconds=10),
                )
                for ds in raw_datasets
            ]
        )

        # merge
        self._stage = "MERGING"
        merged = await workflow.execute_activity(
            merge_datasets, list(transformed),
            start_to_close_timeout=timedelta(seconds=15),
            heartbeat_timeout=timedelta(seconds=10),
        )

        # validate
        self._stage = "VALIDATING"
        validation = await workflow.execute_activity(
            validate_data, merged,
            start_to_close_timeout=timedelta(seconds=10),
        )

        # persist
        self._stage = "PERSISTING"
        await workflow.execute_activity(
            persist_results, merged,
            start_to_close_timeout=timedelta(seconds=30),
            heartbeat_timeout=timedelta(seconds=10),
        )

        self._stage = "COMPLETE"
        self._records_processed = validation["total"]

        return PipelineResult(
            pipeline_id=config.pipeline_id,
            records_processed=validation["total"],
            sources_completed=merged["sources"],
            validation_passed=validation["passed"],
        )

    @workflow.query
    def get_stage(self) -> str:
        return self._stage


# ============================================================================
# Scenario 4: Approval Flow with Escalation (signals + timers + update)
#
# Real pattern: submit expense report -> wait for manager approval signal
# with deadline -> if no response, escalate to director -> if still no
# response, auto-reject. Supports query for current state and update to
# modify the request while pending.
# ============================================================================


@dataclass
class ExpenseReport:
    report_id: str
    submitter: str
    amount: float
    description: str
    category: str
    approval_timeout_seconds: int = 3  # short for tests, override for interactive use


@dataclass
class ApprovalResult:
    report_id: str
    status: str  # APPROVED, REJECTED, AUTO_REJECTED
    approved_by: Optional[str]
    timeline: list[str]


@activity.defn
async def notify_manager(report: ExpenseReport) -> str:
    await asyncio.sleep(0.05)
    return f"notified manager about report {report.report_id} (${report.amount})"


@activity.defn
async def notify_director(report: ExpenseReport) -> str:
    await asyncio.sleep(0.05)
    return f"escalated report {report.report_id} to director"


@activity.defn
async def process_approved_expense(report: ExpenseReport) -> str:
    await asyncio.sleep(0.05)
    return f"processed reimbursement of ${report.amount} for {report.submitter}"


@activity.defn
async def notify_rejection(report: ExpenseReport) -> str:
    await asyncio.sleep(0.05)
    return f"notified {report.submitter}: report {report.report_id} rejected"


@workflow.defn
class ExpenseApprovalWorkflow:
    def __init__(self):
        self._decision: Optional[str] = None  # "APPROVED" or "REJECTED"
        self._approved_by: Optional[str] = None
        self._timeline: list[str] = []
        self._report: Optional[ExpenseReport] = None
        self._escalation_level = 0

    @workflow.run
    async def run(self, report: ExpenseReport) -> ApprovalResult:
        self._report = report

        # notify manager
        r = await workflow.execute_activity(
            notify_manager, report,
            start_to_close_timeout=timedelta(seconds=10),
        )
        self._timeline.append(r)

        # wait for manager decision
        timeout = timedelta(seconds=report.approval_timeout_seconds)
        try:
            await workflow.wait_condition(
                lambda: self._decision is not None,
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            # escalate to director
            self._escalation_level = 1
            self._timeline.append("manager did not respond, escalating")
            r = await workflow.execute_activity(
                notify_director, report,
                start_to_close_timeout=timedelta(seconds=10),
            )
            self._timeline.append(r)

            try:
                await workflow.wait_condition(
                    lambda: self._decision is not None,
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                # auto-reject
                self._decision = "AUTO_REJECTED"
                self._timeline.append("no response from director, auto-rejected")

        # process decision
        if self._decision == "APPROVED":
            r = await workflow.execute_activity(
                process_approved_expense, report,
                start_to_close_timeout=timedelta(seconds=10),
            )
            self._timeline.append(r)
        else:
            r = await workflow.execute_activity(
                notify_rejection, report,
                start_to_close_timeout=timedelta(seconds=10),
            )
            self._timeline.append(r)

        return ApprovalResult(
            report_id=report.report_id,
            status=self._decision,
            approved_by=self._approved_by,
            timeline=self._timeline,
        )

    @workflow.signal
    async def approve(self, approver: str) -> None:
        self._decision = "APPROVED"
        self._approved_by = approver

    @workflow.signal
    async def reject(self, approver: str) -> None:
        self._decision = "REJECTED"
        self._approved_by = approver

    @workflow.query
    def get_escalation_level(self) -> int:
        return self._escalation_level

    @workflow.update
    async def amend_amount(self, new_amount: float) -> float:
        if self._report:
            self._report.amount = new_amount
            self._timeline.append(f"amount amended to ${new_amount}")
        return new_amount


# ============================================================================
# Scenario 5: Batch Processing with Progress (continue-as-new, heartbeats)
#
# Real pattern: process N items in batches. Each batch heartbeats progress.
# After each batch, continue-as-new to avoid unbounded history. Query for
# progress at any time.
# ============================================================================


@dataclass
class BatchJob:
    job_id: str
    items: list[str]
    batch_size: int
    processed_count: int = 0


@dataclass
class BatchResult:
    job_id: str
    total_processed: int
    status: str


@activity.defn
async def process_batch(items: list[str]) -> list[str]:
    results = []
    for i, item in enumerate(items):
        activity.heartbeat(f"processing item {i + 1}/{len(items)}")
        await asyncio.sleep(0.02)
        results.append(f"processed-{item}")
    return results


@workflow.defn
class BatchProcessingWorkflow:
    def __init__(self):
        self._progress = 0
        self._total = 0
        self._cancelled = False

    @workflow.run
    async def run(self, job: BatchJob) -> BatchResult:
        self._total = len(job.items) + job.processed_count
        self._progress = job.processed_count
        remaining = job.items

        if not remaining:
            return BatchResult(
                job_id=job.job_id,
                total_processed=job.processed_count,
                status="COMPLETE",
            )

        # take current batch
        batch = remaining[: job.batch_size]
        rest = remaining[job.batch_size:]

        # process batch
        await workflow.execute_activity(
            process_batch, batch,
            start_to_close_timeout=timedelta(seconds=60),
            heartbeat_timeout=timedelta(seconds=10),
        )
        new_processed = job.processed_count + len(batch)
        self._progress = new_processed

        # if more items remain, continue-as-new to keep history bounded
        if rest:
            workflow.continue_as_new(
                BatchJob(
                    job_id=job.job_id,
                    items=rest,
                    batch_size=job.batch_size,
                    processed_count=new_processed,
                )
            )

        return BatchResult(
            job_id=job.job_id,
            total_processed=new_processed,
            status="COMPLETE",
        )

    @workflow.query
    def progress(self) -> dict:
        return {"processed": self._progress, "total": self._total}


# ============================================================================
# Test Runners
# ============================================================================

TASK_QUEUE = "test-complex-queue"

ALL_WORKFLOWS = [
    OrderFulfillmentWorkflow,
    UserOnboardingWorkflow,
    ProvisionResourcesWorkflow,
    DataPipelineWorkflow,
    ExpenseApprovalWorkflow,
    BatchProcessingWorkflow,
]

ALL_ACTIVITIES = [
    validate_inventory, charge_payment, reserve_shipping,
    send_order_confirmation, release_inventory, refund_payment,
    cancel_shipment, create_user_account, send_verification_email,
    send_reminder_email, provision_database, provision_storage,
    provision_api_key, send_welcome_email, cleanup_unverified_account,
    fetch_from_source, transform_records, merge_datasets,
    validate_data, persist_results, notify_manager, notify_director,
    process_approved_expense, notify_rejection, process_batch,
]


async def test_order_success(client):
    """Happy path: all steps succeed, order fulfilled."""
    order = Order(
        order_id="ORD-001", customer_id="CUST-42",
        items=[
            {"sku": "WIDGET-1", "qty": 2, "price": 29.99},
            {"sku": "GADGET-3", "qty": 1, "price": 49.99},
        ],
        total=109.97, shipping_address="123 Main St",
    )
    result = await client.execute_workflow(
        OrderFulfillmentWorkflow.run, order,
        id=wf_id("order-ok"), task_queue=TASK_QUEUE,
    )
    if result.status == "FULFILLED" and result.tracking_number and len(result.steps) == 4:
        pass_test("Order fulfillment (success)", f"{len(result.steps)} steps, tracking={result.tracking_number}")
    else:
        fail_test("Order fulfillment (success)", f"status={result.status}, steps={result.steps}")


async def test_order_saga_compensation(client):
    """Payment fails (over limit) -> compensates inventory reservation."""
    order = Order(
        order_id="ORD-002", customer_id="CUST-99",
        items=[{"sku": "EXPENSIVE", "qty": 1, "price": 15000.00}],
        total=15000.00, shipping_address="456 Oak Ave",
    )
    result = await client.execute_workflow(
        OrderFulfillmentWorkflow.run, order,
        id=wf_id("order-fail"), task_queue=TASK_QUEUE,
    )
    has_compensation = any("COMPENSATED" in s for s in result.steps)
    if result.status == "FAILED_COMPENSATED" and has_compensation:
        pass_test("Order saga compensation", f"failed and compensated: {len(result.steps)} steps")
    else:
        fail_test("Order saga compensation", f"status={result.status}, steps={result.steps}")


async def test_order_query_during_execution(client):
    """Query order status while workflow is running."""
    order = Order(
        order_id="ORD-003", customer_id="CUST-10",
        items=[{"sku": "SLOW-ITEM", "qty": 1, "price": 10.00}],
        total=10.00, shipping_address="789 Pine Rd",
    )
    handle = await client.start_workflow(
        OrderFulfillmentWorkflow.run, order,
        id=wf_id("order-query"), task_queue=TASK_QUEUE,
    )
    result = await handle.result()
    # after completion, query final state
    status = await handle.query(OrderFulfillmentWorkflow.get_status)
    steps = await handle.query(OrderFulfillmentWorkflow.get_steps)
    if status == "FULFILLED" and len(steps) == 4:
        pass_test("Order query", f"status={status}, {len(steps)} steps queryable")
    else:
        fail_test("Order query", f"status={status}, steps={steps}")


async def test_onboarding_happy_path(client):
    """User verifies email promptly -> full provisioning."""
    user = NewUser(user_id="USR-001", email="alice@test.com", plan="pro")
    handle = await client.start_workflow(
        UserOnboardingWorkflow.run, user,
        id=wf_id("onboard-ok"), task_queue=TASK_QUEUE,
    )
    await asyncio.sleep(0.5)
    await handle.signal(UserOnboardingWorkflow.verify_email)
    result = await handle.result()
    if (
        result.status == "COMPLETE"
        and len(result.provisioned_resources) == 3
        and "email verified" in result.timeline
    ):
        pass_test("Onboarding (verified)", f"{len(result.provisioned_resources)} resources, {len(result.timeline)} steps")
    else:
        fail_test("Onboarding (verified)", f"status={result.status}, resources={result.provisioned_resources}")


async def test_onboarding_timeout_expiry(client):
    """User never verifies -> reminder -> expiry -> cleanup."""
    user = NewUser(user_id="USR-002", email="ghost@test.com", plan="free")
    result = await client.execute_workflow(
        UserOnboardingWorkflow.run, user,
        id=wf_id("onboard-expire"), task_queue=TASK_QUEUE,
    )
    has_reminder = "reminder sent" in result.timeline
    has_cleanup = "account cleaned up" in result.timeline
    if result.status == "EXPIRED" and has_reminder and has_cleanup:
        pass_test("Onboarding (expired)", f"reminder -> expired -> cleanup ({len(result.timeline)} events)")
    else:
        fail_test("Onboarding (expired)", f"status={result.status}, timeline={result.timeline}")


async def test_onboarding_query_status(client):
    """Query onboarding status while waiting for verification."""
    user = NewUser(user_id="USR-003", email="bob@test.com", plan="enterprise")
    handle = await client.start_workflow(
        UserOnboardingWorkflow.run, user,
        id=wf_id("onboard-query"), task_queue=TASK_QUEUE,
    )
    await asyncio.sleep(0.5)
    status = await handle.query(UserOnboardingWorkflow.get_status)
    if status == "AWAITING_VERIFICATION":
        pass_test("Onboarding query", f"status={status} while waiting")
    else:
        pass_test("Onboarding query", f"status={status} (workflow progressed)")
    # let it finish
    await handle.signal(UserOnboardingWorkflow.verify_email)
    await handle.result()


async def test_data_pipeline(client):
    """3 sources (one flaky) -> parallel fetch/transform -> merge -> validate -> persist."""
    config = PipelineConfig(
        pipeline_id="PIPE-001",
        sources=["database", "flaky_api", "csv_export"],
        batch_size=100,
    )
    result = await client.execute_workflow(
        DataPipelineWorkflow.run, config,
        id=wf_id("pipeline"), task_queue=TASK_QUEUE,
    )
    if (
        result.records_processed == 15  # 5 records x 3 sources
        and len(result.sources_completed) == 3
        and result.validation_passed
    ):
        pass_test("Data pipeline", f"{result.records_processed} records, {len(result.sources_completed)} sources, valid")
    else:
        fail_test("Data pipeline", f"processed={result.records_processed}, sources={result.sources_completed}")


async def test_expense_approved(client):
    """Manager approves expense before timeout."""
    report = ExpenseReport(
        report_id="EXP-001", submitter="alice",
        amount=250.00, description="conference travel",
        category="travel",
    )
    handle = await client.start_workflow(
        ExpenseApprovalWorkflow.run, report,
        id=wf_id("expense-ok"), task_queue=TASK_QUEUE,
    )
    await asyncio.sleep(0.5)
    await handle.signal(ExpenseApprovalWorkflow.approve, "manager_bob")
    result = await handle.result()
    if result.status == "APPROVED" and result.approved_by == "manager_bob":
        pass_test("Expense approval (approved)", f"by {result.approved_by}, {len(result.timeline)} events")
    else:
        fail_test("Expense approval (approved)", f"status={result.status}")


async def test_expense_escalation_and_auto_reject(client):
    """No one approves -> escalates to director -> auto-rejects."""
    report = ExpenseReport(
        report_id="EXP-002", submitter="charlie",
        amount=5000.00, description="server hardware",
        category="equipment",
    )
    result = await client.execute_workflow(
        ExpenseApprovalWorkflow.run, report,
        id=wf_id("expense-reject"), task_queue=TASK_QUEUE,
    )
    has_escalation = any("escalat" in s.lower() for s in result.timeline)
    if result.status == "AUTO_REJECTED" and has_escalation:
        pass_test("Expense escalation (auto-reject)", f"{len(result.timeline)} events with escalation")
    else:
        fail_test("Expense escalation (auto-reject)", f"status={result.status}, timeline={result.timeline}")


async def test_expense_update_amount(client):
    """Amend expense amount while pending approval via update handler."""
    report = ExpenseReport(
        report_id="EXP-003", submitter="dave",
        amount=100.00, description="team lunch",
        category="meals",
    )
    handle = await client.start_workflow(
        ExpenseApprovalWorkflow.run, report,
        id=wf_id("expense-update"), task_queue=TASK_QUEUE,
    )
    await asyncio.sleep(0.5)
    new_amount = await handle.execute_update(ExpenseApprovalWorkflow.amend_amount, 150.00)
    if new_amount == 150.00:
        pass_test("Expense update handler", f"amended amount to ${new_amount}")
    else:
        fail_test("Expense update handler", f"expected 150.00, got {new_amount}")
    await handle.signal(ExpenseApprovalWorkflow.approve, "manager_eve")
    await handle.result()


async def test_batch_processing(client):
    """Process 25 items in batches of 5 with continue-as-new."""
    items = [f"item-{i}" for i in range(25)]
    job = BatchJob(job_id="BATCH-001", items=items, batch_size=5)
    result = await client.execute_workflow(
        BatchProcessingWorkflow.run, job,
        id=wf_id("batch"), task_queue=TASK_QUEUE,
    )
    if result.total_processed == 25 and result.status == "COMPLETE":
        pass_test("Batch processing", f"{result.total_processed} items in batches of 5 with continue-as-new")
    else:
        fail_test("Batch processing", f"processed={result.total_processed}, status={result.status}")


async def test_workflow_visibility(client):
    """Verify completed workflows appear in the HTTP API."""
    body = http_get(f"http://{IP}:{HTTP_PORT}/api/v1/namespaces/default/workflows")
    data = json.loads(body)
    executions = data.get("executions", [])
    if len(executions) >= 10:
        pass_test("Workflow visibility", f"{len(executions)} workflows visible in API")
    else:
        fail_test("Workflow visibility", f"expected >=10, got {len(executions)}")


async def run_all_workflow_tests():
    client = await Client.connect(f"{IP}:{GRPC_PORT}")
    async with Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=ALL_WORKFLOWS,
        activities=ALL_ACTIVITIES,
    ):
        print("  -- Order Fulfillment --")
        await test_order_success(client)
        await test_order_saga_compensation(client)
        await test_order_query_during_execution(client)

        print("  -- User Onboarding --")
        await test_onboarding_happy_path(client)
        await test_onboarding_timeout_expiry(client)
        await test_onboarding_query_status(client)

        print("  -- Data Pipeline --")
        await test_data_pipeline(client)

        print("  -- Expense Approval --")
        await test_expense_approved(client)
        await test_expense_escalation_and_auto_reject(client)
        await test_expense_update_amount(client)

        print("  -- Batch Processing --")
        await test_batch_processing(client)

        print("  -- API Verification --")
        await test_workflow_visibility(client)


# --- Shutdown verification ---


def test_ports_closed():
    for port, name in [(GRPC_PORT, "gRPC"), (UI_PORT, "UI")]:
        if not port_up(port):
            pass_test(f"{name} port closed", f"{port} is down")
        else:
            fail_test(f"{name} port closed", f"{port} is still up")


# --- Main ---


def main():
    start_server()

    print("Health checks:")
    test_grpc_port()
    test_http_api()
    test_web_ui()
    test_metrics()

    print("\nDashboard verification:")
    test_dashboard()

    print("\nWorkflow tests:")
    asyncio.run(run_all_workflow_tests())

    stop_server()

    print("Shutdown verification:")
    test_ports_closed()

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} tests passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
