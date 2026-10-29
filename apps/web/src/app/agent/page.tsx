import AgentTraceView from "@/components/AgentTraceView";
import { AgentRunPanel, BatchPanel } from "@/components/AgentRunPanel";

export const metadata = {
  title: "Agent 控制台 — HVAC Energy Agent",
};

export default function AgentPage() {
  return (
    <div className="max-w-3xl mx-auto p-6 space-y-10">
      <section className="space-y-3">
        <h1 className="text-xl font-semibold">🚀 Agent 模式测算</h1>
        <AgentRunPanel />
      </section>

      <section className="space-y-3 border-t pt-6">
        <h2 className="text-lg font-semibold">📦 批量测算</h2>
        <BatchPanel />
      </section>

      <section className="space-y-3 border-t pt-6">
        <h2 className="text-lg font-semibold">🔬 轨迹回放</h2>
        <AgentTraceView />
      </section>
    </div>
  );
}
