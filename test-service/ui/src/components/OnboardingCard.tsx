import { useState } from "react";
import { Loader2, CheckCircle2, XCircle, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "../lib/utils";
import { api } from "../lib/api";

type Phase = "idle" | "starting" | "awaiting" | "verifying" | "done" | "error";

export function OnboardingCard() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [user, setUser] = useState<any>(null);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const start = async () => {
    setPhase("starting");
    setError(null);
    setResult(null);
    try {
      const res = await api.onboardingStart();
      setWorkflowId(res.workflow_id);
      setUser(res.user);
      setPhase("awaiting");
    } catch (e: any) {
      setError(e.message);
      setPhase("error");
    }
  };

  const verify = async () => {
    if (!workflowId) return;
    setPhase("verifying");
    try {
      const res = await api.onboardingVerify(workflowId);
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
        <h3 className="text-white font-semibold text-sm">User Onboarding</h3>
        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wide bg-blue-500/15 text-blue-400">
          Signal + Timer
        </span>
      </div>

      <p className="text-muted text-xs leading-relaxed mb-4">
        Create account, send verification email, wait for user to verify (signal) with timeout.
        Provisions resources via child workflow on success. Expires and cleans up if not verified.
      </p>

      {phase === "awaiting" && user && (
        <div className="bg-[#080810] border border-border rounded-md p-3 mb-3 text-xs">
          <div className="text-warning flex items-center gap-1.5 mb-1">
            <Loader2 className="w-3 h-3 animate-spin" />
            Awaiting email verification...
          </div>
          <div className="text-muted font-mono text-[11px]">
            {user.email} ({user.plan} plan)
          </div>
          <div className="text-muted font-mono text-[10px] mt-1 opacity-50">{workflowId}</div>
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-3">
        <button
          onClick={start}
          disabled={phase === "starting" || phase === "verifying"}
          className={cn(
            "px-3 py-1.5 rounded-md text-xs font-medium border transition-all",
            "disabled:opacity-40 disabled:cursor-not-allowed",
            "bg-indigo-600 hover:bg-indigo-500 border-indigo-500 text-white"
          )}
        >
          {phase === "starting" && <Loader2 className="inline w-3 h-3 mr-1 animate-spin" />}
          Start Onboarding
        </button>

        {phase === "awaiting" && (
          <button
            onClick={verify}
            className="px-3 py-1.5 rounded-md text-xs font-medium border transition-all bg-green-600 hover:bg-green-500 border-green-500 text-white"
          >
            Verify Email
          </button>
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
