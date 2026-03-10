import { useState, type ReactNode } from "react";
import { Loader2, CheckCircle2, XCircle, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "../lib/utils";

type Status = "idle" | "running" | "success" | "error";

interface Action {
  label: string;
  onClick: () => Promise<any>;
  variant?: "default" | "primary" | "danger" | "signal";
  disabled?: boolean;
}

interface WorkflowCardProps {
  title: string;
  badge: string;
  badgeColor: string;
  description: string;
  actions: Action[];
  children?: ReactNode;
}

export function WorkflowCard({ title, badge, badgeColor, description, actions, children }: WorkflowCardProps) {
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const handleAction = (action: Action) => async () => {
    setStatus("running");
    setError(null);
    try {
      const res = await action.onClick();
      setResult(res);
      setStatus("success");
    } catch (e: any) {
      setError(e.message);
      setStatus("error");
    }
  };

  const variantClasses: Record<string, string> = {
    default: "bg-zinc-800 hover:bg-zinc-700 border-zinc-700 text-zinc-200",
    primary: "bg-indigo-600 hover:bg-indigo-500 border-indigo-500 text-white",
    danger: "bg-red-600/80 hover:bg-red-500 border-red-500 text-white",
    signal: "bg-blue-600 hover:bg-blue-500 border-blue-500 text-white",
  };

  return (
    <div className="bg-surface border border-border rounded-lg p-5 hover:border-border-hover transition-colors">
      <div className="flex items-start justify-between mb-3">
        <h3 className="text-white font-semibold text-sm">{title}</h3>
        <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wide", badgeColor)}>
          {badge}
        </span>
      </div>

      <p className="text-muted text-xs leading-relaxed mb-4">{description}</p>

      {children}

      <div className="flex flex-wrap gap-2 mb-3">
        {actions.map((action) => (
          <button
            key={action.label}
            onClick={handleAction(action)}
            disabled={status === "running" || action.disabled}
            className={cn(
              "px-3 py-1.5 rounded-md text-xs font-medium border transition-all",
              "disabled:opacity-40 disabled:cursor-not-allowed",
              variantClasses[action.variant || "default"]
            )}
          >
            {status === "running" && <Loader2 className="inline w-3 h-3 mr-1 animate-spin" />}
            {action.label}
          </button>
        ))}
      </div>

      {(result || error) && (
        <div className="mt-3">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-[10px] text-muted uppercase tracking-wider mb-2 hover:text-zinc-400"
          >
            {status === "success" && <CheckCircle2 className="w-3 h-3 text-success" />}
            {status === "error" && <XCircle className="w-3 h-3 text-danger" />}
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
