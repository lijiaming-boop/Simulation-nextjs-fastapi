"use client";

/**
 * 待办收件箱（M2 Human-in-the-loop 前端）
 *
 * agent 求助（补充数据）与填充审批两类待办：
 * - 审批：一键批准（agent 从断点恢复）或忽略
 * - 求助：上传补充后的调研表，自动重跑闭环
 */

import { useCallback, useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

interface InboxAction {
  id: number;
  session_id: string;
  action_type: "needs_input" | "approval";
  status: string;
  reason: string | null;
  detail?: { missing_items?: string[] };
  created_at?: string | null;
  original_filename?: string | null;
  module_type?: string | null;
}

const TYPE_LABEL: Record<string, string> = {
  needs_input: "⚠️ 需补充数据",
  approval: "🕓 待审批填充",
};

export default function InboxView() {
  const [actions, setActions] = useState<InboxAction[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/inbox`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = await res.json();
      setActions(body.actions as InboxAction[]);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 10000);
    return () => clearInterval(timer);
  }, [load]);

  const approve = useCallback(async (id: number) => {
    setBusy(id);
    try {
      const res = await fetch(`${API_BASE}/inbox/${id}/approve`, { method: "POST" });
      setMessage(res.ok ? `#${id} 已批准，agent 恢复运行` : `#${id} 处理失败：${(await res.json()).detail}`);
      await load();
    } finally {
      setBusy(null);
    }
  }, [load]);

  const dismiss = useCallback(async (id: number) => {
    setBusy(id);
    try {
      await fetch(`${API_BASE}/inbox/${id}/dismiss`, { method: "POST" });
      await load();
    } finally {
      setBusy(null);
    }
  }, [load]);

  const resolve = useCallback(async (id: number, sessionId: string, file: File) => {
    setBusy(id);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(
        `${API_BASE}/agent/${encodeURIComponent(sessionId)}/resolve?mode=deterministic`,
        { method: "POST", body: form },
      );
      const body = await res.json().catch(() => ({}));
      setMessage(res.ok ? `#${id} 已补充数据，重新测算中` : `#${id} 失败：${body.detail}`);
      await load();
    } finally {
      setBusy(null);
    }
  }, [load]);

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">📥 待办收件箱</h1>
        <button className="text-sm text-slate-500" onClick={() => void load()} type="button">
          刷新
        </button>
      </div>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {message && <p className="text-sm text-emerald-700">{message}</p>}

      {actions.length === 0 && (
        <p className="text-sm text-slate-400">暂无待办——agent 的求助与审批请求会出现在这里。</p>
      )}

      <ul className="space-y-3">
        {actions.map((a) => (
          <li key={a.id} className="border rounded p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-medium">{TYPE_LABEL[a.action_type] ?? a.action_type}</span>
              <span className="text-xs text-slate-400">#{a.id}</span>
            </div>
            <p className="text-sm text-slate-600">
              {a.original_filename ?? a.session_id}
              {a.module_type ? ` · ${a.module_type}` : ""}
            </p>
            {a.reason && <p className="text-sm">{a.reason}</p>}
            {a.detail?.missing_items && a.detail.missing_items.length > 0 && (
              <ul className="text-xs text-slate-500 list-disc pl-5">
                {a.detail.missing_items.map((m, i) => <li key={i}>{m}</li>)}
              </ul>
            )}

            <div className="flex flex-wrap items-center gap-2 text-sm">
              {a.action_type === "approval" ? (
                <>
                  <button
                    className="bg-emerald-600 text-white rounded px-3 py-1 disabled:opacity-50"
                    disabled={busy === a.id}
                    onClick={() => void approve(a.id)}
                    type="button"
                  >
                    批准（断点恢复）
                  </button>
                  <button
                    className="border rounded px-3 py-1 disabled:opacity-50"
                    disabled={busy === a.id}
                    onClick={() => void dismiss(a.id)}
                    type="button"
                  >
                    忽略
                  </button>
                </>
              ) : (
                <label className="border rounded px-3 py-1 cursor-pointer">
                  上传补充调研表并重跑
                  <input
                    type="file"
                    accept=".xlsx,.xls"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void resolve(a.id, a.session_id, f);
                    }}
                  />
                </label>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
