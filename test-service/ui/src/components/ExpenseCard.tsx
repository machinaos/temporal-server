import { useState } from "react";
import { Loader2, CheckCircle2, XCircle, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "../lib/utils";
import { api } from "../lib/api";

type Phase = "idle" | "starting" | "pending" | "acting" | "done" | "error";

export function ExpenseCard() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [report, setReport] = useState<any>(null);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const start = async () => {
    setPhase("starting");
    setError(null);
    setResult(null);
    try {
      const res = await api.expenseStart();
      setWorkflowId(res.workflow_id);
      setReport(res.report);
      setPhase("pending");
    } catch (e: any) {
      setError(e.message);
      setPhase("error");
    }
  };

  const decide = async (action: "approve" | "reject") => {
    if (!workflowId) return;
    setPhase("acting");
    try {
      const fn = action === "approve" ? api.expenseApprove : api.expenseReject;
      const res = await fn(workflowId);
      setResult(res);
      setPhase("done");
    } catch (e: any) {
      setError(e.message);
      setPhase("error");
    }
  };

  return (
    <div className="bg-surface border border-border rounded-lg p-5 hover:border-border-hover transition-colors">
      <div className="flex items-start justify-between mb-3">
        <h3 className="text-white font-semibold text-sm">Expense Approval</h3>
        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wide bg-purple-500/15 text-purple-400">
          Approval Flow
        </span>
      </div>

      <p className="text-muted text-xs leading-relaxed mb-4">
        Submit expense report, wait for manager approval/rejection signal with deadline.
        Escalates to director if no response. Auto-rejects after second timeout.
        Supports update handler to amend amount mid-flight.
      </p>

      {phase === "pending" && report && (
        <div className="bg-[#080810] border border-border rounded-md p-3 mb-3 text-xs">
          <div className="text-warning flex items-center gap-1.5 mb-1">
            <Loader2 className="w-3 h-3 animate-spin" />
            Pending approval...
          </div>
          <div className="text-zinc-400 font-mono text-[11px]">
            {report.report_id} -- ${report.amount} ({report.category})
          </div>
          <div className="text-muted font-mono text-[10px] mt-1">{report.description}</div>
          <div className="text-muted font-mono text-[10px] mt-1 opacity-50">{workflowId}</div>
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-3">
        <button
          onClick={start}
          disabled={phase === "starting" || phase === "acting"}
          className={cn(
            "px-3 py-1.5 rounded-md text-xs font-medium border transition-all",
            "disabled:opacity-40 disabled:cursor-not-allowed",
            "bg-indigo-600 hover:bg-indigo-500 border-indigo-500 text-white"
          )}
        >
          {phase === "starting" && <Loader2 className="inline w-3 h-3 mr-1 animate-spin" />}
          Submit Expense
        </button>

        {phase === "pending" && (
          <>
            <button
              onClick={() => decide("approve")}
              className="px-3 py-1.5 rounded-md text-xs font-medium border transition-all bg-green-600 hover:bg-green-500 border-green-500 text-white"
            >
              Approve
            </button>
            <button
              onClick={() => decide("reject")}
              className="px-3 py-1.5 rounded-md text-xs font-medium border transition-all bg-red-600/80 hover:bg-red-500 border-red-500 text-white"
            >
              Reject
            </button>
          </>
        )}
      </div>

      {(result || error) && (
        <div className="mt-3">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-[10px] text-muted uppercase tracking-wider mb-2 hover:text-zinc-400"
          >
            {phase === "done" && <CheckCircle2 className="w-3 h-3 text-success" />}
            {phase === "error" && <XCircle className="w-3 h-3 text-danger" />}
            Result
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>

          {expanded && (
            <pre className="bg-[#080810] border border-border rounded-md p-3 text-[11px] font-mono max-h-60 overflow-auto text-zinc-400 leading-relaxed">
              {error ? error : JSON.stringify(result, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
