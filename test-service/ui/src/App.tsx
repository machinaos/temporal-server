import { useEffect, useState } from "react";
import {
  ShoppingCart, Package, Database, FileText, Layers,
  ExternalLink, Activity
} from "lucide-react";
import { api } from "./lib/api";
import { WorkflowCard } from "./components/WorkflowCard";
import { OnboardingCard } from "./components/OnboardingCard";
import { ExpenseCard } from "./components/ExpenseCard";

function App() {
  const [info, setInfo] = useState<any>(null);
  const [workflowCount, setWorkflowCount] = useState<number | null>(null);

  useEffect(() => {
    api.info().then(setInfo).catch(() => {});
    const poll = setInterval(() => {
      api.workflows()
        .then((d) => setWorkflowCount(d.executions?.length ?? 0))
        .catch(() => {});
    }, 3000);
    api.workflows()
      .then((d) => setWorkflowCount(d.executions?.length ?? 0))
      .catch(() => {});
    return () => clearInterval(poll);
  }, []);

  return (
    <div className="min-h-screen bg-background text-zinc-200">
      <div className="max-w-6xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-10 pb-5 border-b border-border">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2.5">
              <Activity className="w-6 h-6 text-accent" />
              Temporal Workflow Dashboard
            </h1>
            <p className="text-muted text-sm mt-1">
              Run and monitor workflow scenarios against temporal-server
            </p>
          </div>
          <div className="flex items-center gap-4 text-xs">
            {workflowCount !== null && (
              <span className="text-muted">
                {workflowCount} workflow{workflowCount !== 1 ? "s" : ""} executed
              </span>
            )}
            {info && (
              <a
                href={info.ui}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 text-accent hover:text-accent-hover transition-colors"
              >
                Temporal UI <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
        </div>

        {/* Scenario Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Order Fulfillment - Success */}
          <WorkflowCard
            title="Order Fulfillment (Happy Path)"
            badge="Saga"
            badgeColor="bg-orange-500/15 text-orange-400"
            description="Place order with 2 items ($109.97). Validates inventory, charges payment, reserves shipping, sends confirmation. All steps succeed."
            actions={[
              { label: "Place Order", onClick: api.orderSuccess, variant: "primary" },
            ]}
          />

          {/* Order Fulfillment - Saga Compensation */}
          <WorkflowCard
            title="Order Fulfillment (Saga Compensation)"
            badge="Saga"
            badgeColor="bg-orange-500/15 text-orange-400"
            description="Place order over $10k limit. Payment gets declined after inventory is reserved. Triggers saga compensation: inventory released, no charge."
            actions={[
              { label: "Place Failing Order", onClick: api.orderFailure, variant: "danger" },
            ]}
          />

          {/* User Onboarding */}
          <OnboardingCard />

          {/* Expense Approval */}
          <ExpenseCard />

          {/* Data Pipeline */}
          <WorkflowCard
            title="Data Pipeline (ETL)"
            badge="Pipeline"
            badgeColor="bg-emerald-500/15 text-emerald-400"
            description="Parallel fetch from 3 sources (one flaky with retries). Transform each dataset, merge, validate, persist. Activities heartbeat during processing."
            actions={[
              { label: "Run Pipeline", onClick: api.pipelineRun, variant: "primary" },
            ]}
          />

          {/* Batch Processing */}
          <WorkflowCard
            title="Batch Processing"
            badge="Continue-as-new"
            badgeColor="bg-teal-500/15 text-teal-400"
            description="Process 25 items in batches of 5. Each batch uses continue-as-new to keep workflow history bounded. Activities heartbeat progress per item."
            actions={[
              { label: "Run Batch Job", onClick: api.batchRun, variant: "primary" },
            ]}
          />
        </div>

        {/* Footer */}
        <div className="mt-10 pt-5 border-t border-border text-center text-muted text-xs">
          {info && (
            <span>
              gRPC {info.grpc} / HTTP API{" "}
              <a href={info.http_api} target="_blank" rel="noreferrer" className="text-accent hover:text-accent-hover">
                {info.http_api}
              </a>{" "}
              / Queue: {info.task_queue}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
