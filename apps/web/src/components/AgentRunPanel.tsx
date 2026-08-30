"use client";

/**
 * Agent 运行面板（M2 前端补全）
 *
 * 上传调研表 → 发起 agent 运行 → SSE 实时事件流 → 自动加载轨迹回放。
 * 另含批量测算入口（多文件顺序执行 + 进度轮询）。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";
import AgentTraceView from "@/components/AgentTraceView";

interface LiveEvent {
  type: string;
  timestamp?: string;
  message?: string;
  tool?: string;
  ok?: boolean;
  status?: string;
}

/** fetch 版 SSE 解析（EventSource 无法带身份头） */
async function consumeSSE(
  url: string,
  onEvent: (e: Record<string, unknown>) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(url, { signal });
  if (!res.ok || !res.body) throw new Error(`SSE HTTP ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const dataLine = block
        .split("\n")
        .find((l) => l.startsWith("data:"));
      if (!dataLine) continue;
      try {
        onEvent(JSON.parse(dataLine.slice(5).trim()));
      } catch {
        /* 忽略非 JSON 行（如 ping） */
      }
    }
  }
}

const EVENT_ICON: Record<string, string> = {
  run_start: "🚀",
  thinking: "🧠",
  tool_start: "🔧",
  tool_end: "🔧",
  final: "🏁",
  done: "🏁",
  error: "❌",
};

function LiveEventList({ events }: { events: LiveEvent[] }) {
  return (
    <ul className="space-y-1 text-sm max-h-72 overflow-y-auto bg-slate-50 rounded p-3">
      {events.map((e, i) => (
        <li key={i}>
          <span className="mr-1">{EVENT_ICON[e.type] ?? "•"}</span>
          <span className="text-slate-600">{e.timestamp}</span>{" "}
          <span
            className={
              e.type === "tool_end" && e.ok === false ? "text-rose-600" : ""
            }
          >
            {e.message ?? e.status ?? ""}
          </span>
        </li>
      ))}
      {events.length === 0 && <li className="text-slate-400">等待事件…</li>}
    </ul>
  );
}

export function AgentRunPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState("deterministic");
  const [requireApproval, setRequireApproval] = useState(false);
  const [sid, setSid] = useState<string | null>(null);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [status, setStatus] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback(async () => {
    if (!file) return;
    setError(null);
    setEvents([]);
    setStatus("上传中…");
    try {
      const form = new FormData();
      form.append("file", file);
      const up = await fetch(
        `${API_BASE}/upload?module_type=air_conditioner`,
        { method: "POST", body: form },
      );
      if (!up.ok) throw new Error((await up.json()).detail ?? `上传 ${up.status}`);
      const { session_id } = await up.json();
      setSid(session_id);

      setStatus("运行中…");
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      await consumeSSE(
        `${API_BASE}/agent/run/${session_id}?mode=${mode}&require_approval=${requireApproval}`
          .replace("/agent/run/", "/agent/run/")
          .replace("/api/agent/", "/api/agent/"),
        (e) => {
          const ev = e as unknown as LiveEvent;
          setEvents((prev) => [...prev, ev]);
          if (ev.type === "final" || ev.type === "done" || ev.type === "error") {
            setStatus(`结束：${ev.status ?? ev.message ?? ""}`);
          }
        },
        ctrl.signal,
      );
      // SSE 结束后加载完整轨迹
      setStatus((s) => s || "完成");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("失败");
    }
  }, [file, mode, requireApproval]);

  useEffect(() => () => abortRef.current?.abort(), []);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <input
          type="file"
          accept=".xlsx,.xls"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="border rounded px-3 py-2"
        />
        <select
          className="border rounded px-2 py-2"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          <option value="deterministic">确定性策略（零成本）</option>
          <option value="auto">LLM 决策</option>
        </select>
        <label className="flex items-center gap-1">
          <input
            type="checkbox"
            checked={requireApproval}
            onChange={(e) => setRequireApproval(e.target.checked)}
          />
          填充需审批
        </label>
        <button
          className="bg-slate-800 text-white rounded px-4 py-2 disabled:opacity-50"
          disabled={!file || status.startsWith("运行")}
          onClick={() => void run()}
          type="button"
        >
          发起测算
        </button>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}
      {status && (
        <p className={`text-sm ${status.includes("失败") ? "text-rose-600" : "text-emerald-700"}`}>
          {status}
        </p>
      )}
      {events.length > 0 && <LiveEventList events={events} />}
      {sid && (
        <div className="border-t pt-4">
          <p className="text-xs text-slate-400 mb-2">session: {sid}</p>
          <AgentTraceView sessionId={sid} />
        </div>
      )}
    </div>
  );
}

export function BatchPanel() {
  const [files, setFiles] = useState<FileList | null>(null);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(async () => {
    if (!files?.length) return;
    setError(null);
    try {
      const form = new FormData();
      Array.from(files).forEach((f) => form.append("files", f));
      const res = await fetch(
        `${API_BASE}/agent/batch?module_type=air_conditioner&mode=deterministic`,
        { method: "POST", body: form },
      );
      if (!res.ok) throw new Error((await res.json()).detail ?? `HTTP ${res.status}`);
      const { batch_id, status_url } = await res.json();
      setBatchId(batch_id);
      // 轮询进度
      const timer = setInterval(async () => {
        const s = await fetch(`${API_BASE}${status_url.replace("/api", "")}`);
        if (!s.ok) return;
        const body = await s.json();
        setStatus(body);
        if (body.status === "done") clearInterval(timer);
      }, 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [files]);

  const results = (status?.detail as { results?: Array<Record<string, unknown>> } | undefined)?.results;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <input
          type="file"
          multiple
          accept=".xlsx,.xls"
          onChange={(e) => setFiles(e.target.files)}
          className="border rounded px-3 py-2"
        />
        <button
          className="bg-slate-800 text-white rounded px-4 py-2 disabled:opacity-50"
          disabled={!files?.length || batchId !== null}
          onClick={() => void submit()}
          type="button"
        >
          批量测算
        </button>
      </div>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {status && (
        <div className="text-sm">
          <p>
            状态 {String(status.status)} · 完成 {String(status.completed)}/
            {String(status.total)} · 失败 {String(status.failed)}
          </p>
          <ul className="mt-2 space-y-1">
            {(results ?? []).map((r, i) => (
              <li key={i} className="bg-slate-50 rounded px-3 py-1">
                {String(r.filename)} — {String(r.status)}：{String(r.summary ?? "").slice(0, 80)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
