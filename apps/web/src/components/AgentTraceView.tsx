"use client";

/**
 * Agent 轨迹回放视图（M2）
 *
 * 输入 session_id，拉取 /agent/{id}/trace 并逐帧回放
 * agent 的"思考 → 行动 → 观察"轨迹与 token 用量。
 * 独立页面 /agent 可直接使用；也可嵌入结果面板。
 */

import { useCallback, useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

interface TraceStep {
  step: number;
  tool: string;
  args?: Record<string, unknown>;
  reason?: string;
  ok?: boolean | null;
  observation?: Record<string, unknown> | null;
  duration_ms?: number | null;
  decision?: { input_tokens?: number; output_tokens?: number; model?: string } | null;
}

interface AgentTrace {
  run_id?: string;
  mode: string;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  llm_usage?: { brain_calls?: number; input_tokens?: number; output_tokens?: number };
  steps: TraceStep[];
  final?: { status: string; summary?: string };
}

const TOOL_LABELS: Record<string, string> = {
  extract_survey: "📋 提取调研表",
  suggest_filling: "🧮 生成填充建议",
  apply_filling: "📝 执行数据填充",
  calculate_saving_rate: "⚙️ 公式引擎计算",
  request_user_input: "🙋 请求用户补充",
  request_approval: "🕓 等待人工审批",
  finish: "🏁 输出结论",
};

const STATUS_STYLE: Record<string, string> = {
  completed: "text-emerald-600",
  needs_input: "text-amber-600",
  pending_approval: "text-sky-600",
  error: "text-rose-600",
  interrupted: "text-orange-600",
  running: "text-slate-500",
};

function StepCard({ step }: { step: TraceStep }) {
  const [open, setOpen] = useState(false);
  const label = TOOL_LABELS[step.tool] ?? step.tool;
  const okBadge =
    step.ok === true ? "✅" : step.ok === false ? "❌" : "•";
  return (
    <li className="border-l-2 border-slate-200 pl-4 py-2">
      <button
        className="w-full text-left"
        onClick={() => setOpen((v) => !v)}
        type="button"
      >
        <div className="flex items-center gap-2">
          <span>{okBadge}</span>
          <span className="font-medium">{label}</span>
          {typeof step.duration_ms === "number" && (
            <span className="text-xs text-slate-400">{step.duration_ms}ms</span>
          )}
          {step.decision?.output_tokens != null && (
            <span className="text-xs text-slate-400">
              {step.decision.output_tokens} tok
            </span>
          )}
        </div>
        {step.reason && (
          <p className="text-sm text-slate-600 mt-1">🧠 {step.reason}</p>
        )}
      </button>
      {open && step.observation != null && (
        <pre className="mt-2 bg-slate-50 rounded p-2 text-xs overflow-x-auto">
          {JSON.stringify(step.observation, null, 2)}
        </pre>
      )}
    </li>
  );
}

export default function AgentTraceView({ sessionId }: { sessionId?: string }) {
  const [sid, setSid] = useState(sessionId ?? "");
  const [trace, setTrace] = useState<AgentTrace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (id: string) => {
    if (!id.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/agent/${encodeURIComponent(id.trim())}/trace`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      setTrace((await res.json()) as AgentTrace);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setTrace(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (sessionId) void load(sessionId);
  }, [sessionId, load]);

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-4">
      <h1 className="text-xl font-semibold">🔬 Agent 轨迹回放</h1>
      <div className="flex gap-2">
        <input
          className="flex-1 border rounded px-3 py-2 text-sm"
          placeholder="输入 session_id，如 session_20260829_…"
          value={sid}
          onChange={(e) => setSid(e.target.value)}
        />
        <button
          className="bg-slate-800 text-white rounded px-4 py-2 text-sm disabled:opacity-50"
          disabled={loading || !sid.trim()}
          onClick={() => void load(sid)}
          type="button"
        >
          {loading ? "加载中…" : "回放"}
        </button>
      </div>

      {error && <p className="text-sm text-rose-600">加载失败：{error}</p>}

      {trace && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-3 text-sm">
            <span className="px-2 py-0.5 rounded bg-slate-100">
              模式：{trace.mode === "llm" || trace.mode === "agent" ? "LLM 决策" : "确定性策略"}
            </span>
            <span className={STATUS_STYLE[trace.status] ?? "text-slate-500"}>
              状态：{trace.status}
            </span>
            {trace.llm_usage && (
              <span className="text-slate-500">
                🪙 brain 调用 {trace.llm_usage.brain_calls ?? 0} 次 ·
                in {trace.llm_usage.input_tokens ?? 0} · out {trace.llm_usage.output_tokens ?? 0} tok
              </span>
            )}
          </div>

          {trace.final?.summary && (
            <div className="bg-slate-50 rounded p-3 text-sm">
              <p className="font-medium mb-1">结论</p>
              {trace.final.summary}
            </div>
          )}

          <ol className="space-y-1">
            {trace.steps.map((s) => (
              <StepCard key={s.step} step={s} />
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
