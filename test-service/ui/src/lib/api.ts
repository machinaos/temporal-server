const BASE = "/api";

async function post<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "POST" });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export const api = {
  info: () => get<{
    grpc: string;
    http_api: string;
    ui: string;
    task_queue: string;
  }>("/info"),

  workflows: () => get<{ executions: any[] }>("/workflows"),

  orderSuccess: () => post<{
    order_id: string;
    status: string;
    steps: string[];
    tracking: string | null;
  }>("/order/success"),

  orderFailure: () => post<{
    order_id: string;
    status: string;
    steps: string[];
    tracking: string | null;
  }>("/order/failure"),

  onboardingStart: () => post<{
    workflow_id: string;
    user: { user_id: string; email: string; plan: string };
  }>("/onboarding/start"),

  onboardingVerify: (workflowId: string) => post<{
    status: string;
    resources: string[];
    timeline: string[];
  }>(`/onboarding/${workflowId}/verify`),

  pipelineRun: () => post<{
    pipeline_id: string;
    records: number;
    sources: string[];
    valid: boolean;
  }>("/pipeline/run"),

  expenseStart: () => post<{
    workflow_id: string;
    report: { report_id: string; submitter: string; amount: number; description: string; category: string };
  }>("/expense/start"),

  expenseApprove: (workflowId: string) => post<{
    status: string;
    approved_by: string;
    timeline: string[];
  }>(`/expense/${workflowId}/approve`),

  expenseReject: (workflowId: string) => post<{
    status: string;
    approved_by: string;
    timeline: string[];
  }>(`/expense/${workflowId}/reject`),

  batchRun: () => post<{
    job_id: string;
    processed: number;
    status: string;
  }>("/batch/run"),
};
