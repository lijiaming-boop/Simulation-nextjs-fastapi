"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  API_BASE,
  uploadSurvey,
  startExtract,
  subscribeExtractStream,
  startSuggest,
  fetchSuggest,
  startCalculate,
  fetchResult,
  type StreamEvent,
  type ResultResponse,
  type SuggestResult,
} from "@/lib/api";

type Stage =
  | "idle"
  | "uploading"
  | "uploaded"
  | "extracting"
  | "extracted"
  | "suggesting"
  | "suggested"
  | "calculating"
  | "done"
  | "error";

export default function Workflow() {
  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState<string>("");
  const [sessionId, setSessionId] = useState<string>("");
  const [filename, setFilename] = useState<string>("");
  const [logs, setLogs] = useState<Array<{ ts: string; msg: string }>>([]);
  const [result, setResult] = useState<ResultResponse | null>(null);
  const [useLlm, setUseLlm] = useState<boolean>(true);
  const [suggestions, setSuggestions] = useState<SuggestResult | null>(null);
  const [moduleType, setModuleType] = useState<
    "air_conditioner" | "air_compressor"
  >("air_conditioner");

  const logsEndRef = useRef<HTMLDivElement>(null);
  const extractedDataRef = useRef<Record<string, unknown> | null>(null);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // ================== Step 1: 上传 ==================
  const onFileSelected = useCallback(
    async (file: File) => {
      setError("");
      setStage("uploading");
      try {
        const r = await uploadSurvey(file, moduleType);
        setSessionId(r.session_id);
        setFilename(r.original_filename);
        setStage("uploaded");
      } catch (e) {
        setError((e as Error).message);
        setStage("error");
      }
    },
    [moduleType]
  );

  // ================== Step 2: 提取 + SSE ==================
  const doExtract = useCallback(async () => {
    setError("");
    setStage("extracting");
    setLogs([]);
    try {
      await startExtract(sessionId);
      // 连接 SSE
      subscribeExtractStream(sessionId, (ev: StreamEvent) => {
        if (ev.type === "log" && ev.message) {
          setLogs((prev) => [
            ...prev,
            { ts: ev.timestamp ?? "", msg: ev.message! },
          ]);
        } else if (ev.type === "done") {
          setStage("extracted");
        } else if (ev.type === "error") {
          setError(ev.message ?? "提取失败");
          setStage("error");
        }
      });
    } catch (e) {
      setError((e as Error).message);
      setStage("error");
    }
  }, [sessionId]);

  // ================== Step 3: 拉取提取结果（用于计算） ==================
  useEffect(() => {
    if (stage !== "extracted") return;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/session/${sessionId}/extracted`);
        if (res.ok) {
          extractedDataRef.current = await res.json();
        } else {
          extractedDataRef.current = null;
        }
      } catch {
        extractedDataRef.current = null;
      }
    })();
  }, [stage, sessionId]);

  // ================== Step 3.5: 生成填充建议（可选 LLM 增强） ==================
  const doSuggest = useCallback(async () => {
    setError("");
    setStage("suggesting");
    setLogs([]);
    try {
      await startSuggest(sessionId, useLlm);
      // SSE
      subscribeExtractStream(sessionId, (ev: StreamEvent) => {
        if (ev.type === "log" && ev.message) {
          setLogs((prev) => [
            ...prev,
            { ts: ev.timestamp ?? "", msg: ev.message! },
          ]);
        } else if (ev.type === "done") {
          // 拉取结果
          fetchSuggest(sessionId).then((s) => {
            setSuggestions(s);
            setStage("suggested");
          });
        } else if (ev.type === "error") {
          setError(ev.message ?? "生成建议失败");
          setStage("error");
        }
      });
    } catch (e) {
      setError((e as Error).message);
      setStage("error");
    }
  }, [sessionId, useLlm]);

  // ================== Step 4: 计算 + 轮询结果 ==================
  const doCalculate = useCallback(async () => {
    setError("");
    setStage("calculating");
    try {
      await startCalculate(
        sessionId,
        extractedDataRef.current ?? undefined
      );
      // 轮询
      const poll = async (): Promise<ResultResponse | null> => {
        for (let i = 0; i < 60; i++) {
          const r = await fetchResult(sessionId);
          if (r && r.stage === "result") return r;
          await new Promise((res) => setTimeout(res, 1000));
        }
        return null;
      };
      const r = await poll();
      if (!r) {
        setError("计算超时 60s");
        setStage("error");
        return;
      }
      setResult(r);
      setStage("done");
    } catch (e) {
      setError((e as Error).message);
      setStage("error");
    }
  }, [sessionId]);

  // ================== 重置 ==================
  const reset = () => {
    setStage("idle");
    setSessionId("");
    setFilename("");
    setLogs([]);
    setResult(null);
    setSuggestions(null);
    setError("");
    extractedDataRef.current = null;
  };

  // ================== UI ==================
  return (
    <main className="max-w-5xl mx-auto p-6 space-y-6">
      {/* 顶部标题 */}
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">
            空调 / 空压机节能测算
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            FastAPI + Next.js 重构版（P2 MVP）
          </p>
        </div>
        {sessionId && (
          <button
            onClick={reset}
            className="text-sm text-blue-600 hover:underline"
          >
            重新开始
          </button>
        )}
      </header>

      {/* 步骤条 */}
      <Stepper stage={stage} />

      {/* 上传区 */}
      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className="font-medium mb-3">① 上传调研表</h2>
        <div className="flex items-center gap-3">
          <select
            value={moduleType}
            onChange={(e) =>
              setModuleType(
                e.target.value as "air_conditioner" | "air_compressor"
              )
            }
            disabled={stage !== "idle" && stage !== "error"}
            className="border rounded px-3 py-2 text-sm"
          >
            <option value="air_conditioner">中央空调</option>
            <option value="air_compressor">空压机</option>
          </select>
          <label
            className={`cursor-pointer px-4 py-2 rounded text-white text-sm ${
              stage === "idle" || stage === "error"
                ? "bg-blue-600 hover:bg-blue-700"
                : "bg-gray-400 cursor-not-allowed"
            }`}
          >
            选择 .xlsx / .xls 文件
            <input
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              disabled={stage !== "idle" && stage !== "error"}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onFileSelected(f);
              }}
            />
          </label>
          {filename && (
            <span className="text-sm text-gray-600">
              已上传: {filename}
            </span>
          )}
          {stage === "uploading" && (
            <span className="text-sm text-blue-600">上传中...</span>
          )}
        </div>
        {sessionId && (
          <p className="mt-3 text-xs text-gray-500">
            Session: <code>{sessionId}</code>
          </p>
        )}
      </section>

      {/* 提取 */}
      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className="font-medium mb-3">② 提取数据 + AI 质检</h2>
        <button
          onClick={doExtract}
          disabled={stage !== "uploaded" && stage !== "extracted"}
          className="px-4 py-2 rounded text-white text-sm bg-green-600 hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          {stage === "extracting" ? "提取中..." : "开始提取"}
        </button>

        {/* 日志面板 */}
        {(logs.length > 0 || stage === "extracting" || stage === "suggesting") && (
          <div className="mt-4 rounded bg-gray-900 text-green-300 font-mono text-xs p-3 max-h-72 overflow-auto">
            {logs.map((l, i) => (
              <div key={i} className="whitespace-pre-wrap">
                <span className="text-gray-500">[{l.ts}]</span> {l.msg}
              </div>
            ))}
            {(stage === "extracting" || stage === "suggesting") && (
              <div className="text-yellow-300 animate-pulse">▍等待...</div>
            )}
            <div ref={logsEndRef} />
          </div>
        )}
      </section>

      {/* 填充建议（可选，建议 LLM 增强） */}
      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-medium">③ 填充建议（规则 + LLM 增强）</h2>
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={useLlm}
              onChange={(e) => setUseLlm(e.target.checked)}
              disabled={stage === "suggesting"}
              className="accent-blue-600"
            />
            🤖 LLM 智能增强
          </label>
        </div>
        <button
          onClick={doSuggest}
          disabled={
            stage !== "extracted" &&
            stage !== "suggested" &&
            stage !== "done"
          }
          className="px-4 py-2 rounded text-white text-sm bg-orange-600 hover:bg-orange-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          {stage === "suggesting" ? "生成中..." : "生成填充建议"}
        </button>
        <span className="ml-3 text-xs text-gray-500">
          {useLlm
            ? "将用 LLM 对规则建议做智能增强（耗时约 5-15s）"
            : "仅使用规则脚本（区域电价 + 季节默认值）"}
        </span>

        {suggestions && (
          <SuggestPanel suggestions={suggestions} />
        )}
      </section>

      {/* 计算 + 结果 */}
      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className="font-medium mb-3">④ 公式计算 + 结果</h2>
        <button
          onClick={doCalculate}
          disabled={stage !== "extracted" && stage !== "suggested"}
          className="px-4 py-2 rounded text-white text-sm bg-purple-600 hover:bg-purple-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          {stage === "calculating" ? "计算中..." : "开始计算"}
        </button>

        {result?.result && (
          <ResultPanel r={result.result} />
        )}
      </section>

      {/* 错误 */}
      {stage === "error" && error && (
        <section className="rounded-lg border border-red-300 bg-red-50 text-red-800 p-4 text-sm">
          <strong>错误：</strong>
          {error}
        </section>
      )}
    </main>
  );
}

// ==================== 子组件 ====================

function Stepper({ stage }: { stage: Stage }) {
  const steps: { key: Stage[]; label: string }[] = [
    { key: ["idle", "uploading"], label: "上传" },
    { key: ["uploaded", "extracting"], label: "提取" },
    { key: ["extracted", "suggesting"], label: "建议" },
    { key: ["suggested", "calculating"], label: "计算" },
    { key: ["done"], label: "完成" },
  ];
  const order: Stage[] = ["idle", "uploading", "uploaded", "extracting", "extracted", "suggesting", "suggested", "calculating", "done"];
  const idx = order.indexOf(stage);
  return (
    <ol className="flex items-center gap-2 text-xs">
      {steps.map((s, i) => {
        const active = s.key.includes(stage);
        const done = idx >= order.indexOf(s.key[s.key.length - 1]);
        const cls = active
          ? "bg-blue-600 text-white"
          : done
            ? "bg-green-500 text-white"
            : "bg-gray-200 text-gray-500";
        return (
          <li key={i} className="flex items-center gap-2">
            <span className={`px-2 py-1 rounded ${cls}`}>
              {i + 1}. {s.label}
            </span>
            {i < steps.length - 1 && <span className="text-gray-300">›</span>}
          </li>
        );
      })}
    </ol>
  );
}

function SuggestPanel({ suggestions: s }: { suggestions: SuggestResult }) {
  const unfillable = s.unfillable_fields as unknown[] | undefined;
  const fillable = s.fillable_suggestions as unknown[] | undefined;
  const llmTips = s.llm_enhanced_tips;

  return (
    <div className="mt-4 space-y-3">
      {/* 不可填充字段 */}
      {unfillable && unfillable.length > 0 && (
        <div className="rounded border border-red-200 bg-red-50 p-3">
          <h4 className="text-sm font-medium text-red-800 mb-1">
            ⚠️ 无法自动填充的字段（{unfillable.length}）
          </h4>
          <ul className="text-xs text-red-700 list-disc pl-4 space-y-0.5">
            {unfillable.map((f, i) => (
              <li key={i}>{String(f)}</li>
            ))}
          </ul>
        </div>
      )}

      {/* 可填充建议 */}
      {fillable && fillable.length > 0 && (
        <div className="rounded border border-blue-200 bg-blue-50 p-3">
          <h4 className="text-sm font-medium text-blue-800 mb-1">
            💡 填充建议（{fillable.length} 条）
          </h4>
          <ul className="text-xs text-blue-700 list-disc pl-4 space-y-0.5">
            {fillable.map((item, i) => {
              const rec = item as Record<string, unknown>;
              const field = rec?.field ? String(rec.field) : "";
              const suggestion = rec?.suggestion ? String(rec.suggestion) : String(item);
              return (
                <li key={i}>
                  {field ? <strong>{field}：</strong> : null}
                  {suggestion}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* LLM 增强建议 */}
      {llmTips && (
        <div className="rounded border border-purple-200 bg-purple-50 p-3">
          <h4 className="text-sm font-medium text-purple-800 mb-1">
            🤖 LLM 智能建议
          </h4>
          <pre className="text-xs text-purple-700 whitespace-pre-wrap font-sans">
            {llmTips}
          </pre>
        </div>
      )}
    </div>
  );
}

function ResultPanel({
  r,
}: {
  r: NonNullable<ResultResponse["result"]>;
}) {
  const rows: Array<[string, string, string | number | undefined]> = [
    ["节能率范围", "", r.energy_saving_rate_range],
    ["综合节能率", "%", r.energy_saving_rate != null ? (r.energy_saving_rate * 100).toFixed(2) : undefined],
    ["节能率下限", "%", r.energy_saving_rate_min != null ? (r.energy_saving_rate_min * 100).toFixed(2) : undefined],
    ["节能率上限", "%", r.energy_saving_rate_max != null ? (r.energy_saving_rate_max * 100).toFixed(2) : undefined],
    ["总节电量", "万kW·h", r.total_saving?.toFixed(2)],
    ["冷机节电", "万kW·h", r.chiller_saving?.toFixed(2)],
    ["泵节电", "万kW·h", r.pump_saving?.toFixed(2)],
    ["塔节电", "万kW·h", r.tower_saving?.toFixed(2)],
    ["数据完整率", "", r.completeness != null ? `${(r.completeness * 100).toFixed(1)}%` : undefined],
  ];
  return (
    <div className="mt-4 rounded border border-green-200 bg-green-50 p-4">
      <h3 className="font-medium text-green-900 mb-2">
        📊 节能测算结果
      </h3>
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
        {rows.map(([label, unit, value], i) => (
          <div key={i} className="flex justify-between py-1 border-b border-green-100">
            <dt className="text-gray-600">{label}</dt>
            <dd className="font-semibold text-gray-900">
              {value ?? "-"} {unit}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
