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
  resultDownloadUrl,
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

export default function Workflow({ moduleType, title }: { moduleType: "air_conditioner" | "air_compressor"; title: string }) {
  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState<string>("");
  const [sessionId, setSessionId] = useState<string>("");
  const [filename, setFilename] = useState<string>("");
  const [logs, setLogs] = useState<Array<{ ts: string; msg: string }>>([]);
  const [result, setResult] = useState<ResultResponse | null>(null);
  const [useLlm, setUseLlm] = useState<boolean>(true);
  const [suggestions, setSuggestions] = useState<SuggestResult | null>(null);

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
            {title}
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
          <ResultPanel r={result.result} sessionId={sessionId} moduleType={moduleType} />
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
  sessionId,
  moduleType,
}: {
  r: NonNullable<ResultResponse["result"]>;
  sessionId: string;
  moduleType: "air_conditioner" | "air_compressor";
}) {
  if (moduleType === "air_compressor") {
    return <CompressorResultPanel r={r} sessionId={sessionId} />;
  }
  return <AcResultPanel r={r} sessionId={sessionId} />;
}

/** 空调节能结果：指标 + 冷机/水泵/冷却塔分项明细 + 下载 */
function AcResultPanel({
  r,
  sessionId,
}: {
  r: NonNullable<ResultResponse["result"]>;
  sessionId: string;
}) {
  const isRange = r.chiller_saving_min != null;

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
    <div className="mt-4 rounded border border-green-200 bg-green-50 p-4 space-y-5">
      <h3 className="font-medium text-green-900">📊 节能测算结果</h3>

      {/* 核心指标 */}
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

      {/* 分项节能明细表 + 柱状图 */}
      <SavingsBreakdown r={r} isRange={isRange} />

      {/* 置信度说明 */}
      <ConfidenceNote r={r} />

      {/* 下载区 */}
      <DownloadSection sessionId={sessionId} />
    </div>
  );
}

/** 空压机节能结果：能耗对比指标 + 设备分析 + 报价单下载 */
function CompressorResultPanel({
  r,
  sessionId,
}: {
  r: NonNullable<ResultResponse["result"]>;
  sessionId: string;
}) {
  const wan = (v: unknown) => (typeof v === "number" ? (v / 10000).toFixed(2) : undefined);
  const rows: Array<[string, string, string | number | undefined]> = [
    ["节能率范围", "", r.energy_saving_rate_range],
    ["综合节能率", "%", r.energy_saving_rate != null ? (r.energy_saving_rate * 100).toFixed(2) : undefined],
    ["当前年总能耗", "万kW·h/年", wan(r.current_total_energy)],
    ["优化后年总能耗", "万kW·h/年", wan(r.optimized_total_energy)],
    ["预计年节能量", "万kW·h/年", wan(r.energy_saving)],
    ["数据完整率", "", r.completeness != null ? `${(r.completeness * 100).toFixed(1)}%` : undefined],
  ];

  const ea = r.equipment_analysis;

  return (
    <div className="mt-4 rounded border border-green-200 bg-green-50 p-4 space-y-5">
      <h3 className="font-medium text-green-900">📊 空压节能测算结果</h3>

      {/* 核心指标 */}
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

      {/* 设备分析 */}
      {ea && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-green-900">🔧 设备分析</h4>
          <table className="w-full text-xs border-collapse">
            <tbody>
              <tr>
                <td className="border border-green-200 px-2 py-1 text-gray-600">空压机台数</td>
                <td className="border border-green-200 px-2 py-1 text-right">{ea.total_air_compressors ?? "-"}</td>
              </tr>
              <tr>
                <td className="border border-green-200 px-2 py-1 text-gray-600">总装机功率 (kW)</td>
                <td className="border border-green-200 px-2 py-1 text-right">{ea.total_power != null ? ea.total_power.toFixed(1) : "-"}</td>
              </tr>
              {ea.equipment_types && Object.keys(ea.equipment_types).length > 0 && (
                <tr>
                  <td className="border border-green-200 px-2 py-1 text-gray-600">设备类型分布</td>
                  <td className="border border-green-200 px-2 py-1 text-right">
                    {Object.entries(ea.equipment_types).map(([k, v]) => `${k} × ${v}`).join("，")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* 置信度说明 */}
      <ConfidenceNote r={r} />

      {/* 下载区：报价单 + 方案文档（直接下载，无密码） */}
      <div className="space-y-3 border-t border-green-200 pt-4">
        <h4 className="text-sm font-medium text-green-900">📥 下载文件</h4>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <a
            href={resultDownloadUrl(sessionId, "air_compressor_quotation.xlsx")}
            className="px-3 py-2 rounded bg-green-600 text-white hover:bg-green-700"
            download
          >
            下载空压报价单 Excel
          </a>
          <a
            href={resultDownloadUrl(sessionId, "air_compressor_scheme.docx")}
            className="px-3 py-2 rounded bg-blue-600 text-white hover:bg-blue-700"
            download
          >
            下载数智化升级方案 Word
          </a>
        </div>
        <p className="text-xs text-gray-500">报价单含项目节能测算汇总 + 云智控产品价目表；方案文档含项目现状分析与节能效益预估</p>
      </div>
    </div>
  );
}

/** 分项节能明细：表格 + 手写 SVG 柱状图（无第三方依赖） */
function SavingsBreakdown({
  r,
  isRange,
}: {
  r: NonNullable<ResultResponse["result"]>;
  isRange: boolean;
}) {
  const devices = [
    { key: "chiller", label: "冷机" },
    { key: "pump", label: "水泵" },
    { key: "tower", label: "冷却塔" },
  ] as const;

  const num = (v: unknown) => (typeof v === "number" ? v : 0);

  if (isRange) {
    const bars = devices.map((d) => ({
      label: d.label,
      min: num(r[`${d.key}_saving_min`]),
      max: num(r[`${d.key}_saving_max`]),
    }));
    const total = {
      min: num(r.total_saving_min),
      max: num(r.total_saving_max),
    };
    const peak = Math.max(1, ...bars.map((b) => b.max));

    return (
      <div className="space-y-3">
        <h4 className="text-sm font-medium text-green-900">📊 分项节能明细（范围）</h4>
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-green-100 text-gray-700">
              <th className="border border-green-200 px-2 py-1 text-left">设备类型</th>
              <th className="border border-green-200 px-2 py-1 text-right">节能量范围 (万kW·h)</th>
              <th className="border border-green-200 px-2 py-1 text-right">下限</th>
              <th className="border border-green-200 px-2 py-1 text-right">上限</th>
            </tr>
          </thead>
          <tbody>
            {bars.map((b) => (
              <tr key={b.label}>
                <td className="border border-green-200 px-2 py-1">{b.label}</td>
                <td className="border border-green-200 px-2 py-1 text-right">{b.min.toFixed(1)} - {b.max.toFixed(1)}</td>
                <td className="border border-green-200 px-2 py-1 text-right">{b.min.toFixed(1)}</td>
                <td className="border border-green-200 px-2 py-1 text-right">{b.max.toFixed(1)}</td>
              </tr>
            ))}
            <tr className="font-semibold bg-green-50">
              <td className="border border-green-200 px-2 py-1">合计</td>
              <td className="border border-green-200 px-2 py-1 text-right">{total.min.toFixed(1)} - {total.max.toFixed(1)}</td>
              <td className="border border-green-200 px-2 py-1 text-right">{total.min.toFixed(1)}</td>
              <td className="border border-green-200 px-2 py-1 text-right">{total.max.toFixed(1)}</td>
            </tr>
          </tbody>
        </table>
        <BarChart
          title="分项节能量范围分布"
          groups={bars.map((b) => ({ label: b.label, values: [b.min, b.max] }))}
          seriesLabels={["下限（保守）", "上限（理想）"]}
          seriesColors={["#86efac", "#16a34a"]}
          peak={peak}
        />
      </div>
    );
  }

  // 单值版
  const total = num(r.total_saving);
  const bars = devices.map((d) => ({ label: d.label, value: num(r[`${d.key}_saving`]) }));
  const peak = Math.max(1, ...bars.map((b) => b.value));

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium text-green-900">📊 分项节能明细</h4>
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="bg-green-100 text-gray-700">
            <th className="border border-green-200 px-2 py-1 text-left">设备类型</th>
            <th className="border border-green-200 px-2 py-1 text-right">节能量 (万kW·h)</th>
            <th className="border border-green-200 px-2 py-1 text-right">占比</th>
          </tr>
        </thead>
        <tbody>
          {bars.map((b) => (
            <tr key={b.label}>
              <td className="border border-green-200 px-2 py-1">{b.label}</td>
              <td className="border border-green-200 px-2 py-1 text-right">{b.value.toFixed(2)}</td>
              <td className="border border-green-200 px-2 py-1 text-right">{total > 0 ? `${((b.value / total) * 100).toFixed(1)}%` : "-"}</td>
            </tr>
          ))}
          <tr className="font-semibold bg-green-50">
            <td className="border border-green-200 px-2 py-1">合计</td>
            <td className="border border-green-200 px-2 py-1 text-right">{total.toFixed(2)}</td>
            <td className="border border-green-200 px-2 py-1 text-right">100%</td>
          </tr>
        </tbody>
      </table>
      <BarChart
        title="分项节能量分布"
        groups={bars.map((b) => ({ label: b.label, values: [b.value] }))}
        seriesLabels={["节能量"]}
        seriesColors={["#16a34a"]}
        peak={peak}
      />
    </div>
  );
}

/** 纯 SVG/HTML 分组柱状图（无外部依赖） */
function BarChart({
  title,
  groups,
  seriesLabels,
  seriesColors,
  peak,
}: {
  title: string;
  groups: Array<{ label: string; values: number[] }>;
  seriesLabels: string[];
  seriesColors: string[];
  peak: number;
}) {
  const chartHeight = 140;
  return (
    <div className="rounded border border-green-100 bg-white p-3">
      <div className="text-xs font-medium text-gray-700 mb-2">{title}</div>
      <div className="flex items-end justify-around gap-4" style={{ height: chartHeight + 24 }}>
        {groups.map((g) => (
          <div key={g.label} className="flex flex-col items-center gap-1 flex-1">
            <div className="flex items-end justify-center gap-1" style={{ height: chartHeight }}>
              {g.values.map((v, i) => (
                <div key={i} className="flex flex-col items-center justify-end">
                  <span className="text-[10px] text-gray-500">{v.toFixed(1)}</span>
                  <div
                    className="w-6 rounded-t"
                    style={{
                      height: Math.max(2, (v / peak) * chartHeight),
                      backgroundColor: seriesColors[i] ?? "#16a34a",
                    }}
                  />
                </div>
              ))}
            </div>
            <span className="text-[11px] text-gray-600">{g.label}</span>
          </div>
        ))}
      </div>
      <div className="flex justify-center gap-4 mt-2">
        {seriesLabels.map((l, i) => (
          <span key={i} className="flex items-center gap-1 text-[11px] text-gray-600">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: seriesColors[i] ?? "#16a34a" }} />
            {l}
          </span>
        ))}
      </div>
    </div>
  );
}

/** 置信度提示 */
function ConfidenceNote({ r }: { r: NonNullable<ResultResponse["result"]> }) {
  const c = r.completeness ?? 0;
  let msg: string;
  let cls: string;
  if (c >= 0.9) {
    msg = "🟢 高置信度 - 数据完整，结果可靠";
    cls = "border-green-200 bg-green-50 text-green-800";
  } else if (c >= 0.7) {
    msg = "🟡 中等置信度 - 部分数据通过智能填充，建议谨慎使用";
    cls = "border-yellow-200 bg-yellow-50 text-yellow-800";
  } else {
    msg = "🔴 低置信度 - 较多数据缺失，结果仅供参考";
    cls = "border-red-200 bg-red-50 text-red-800";
  }
  return (
    <div className="space-y-2">
      {r.mock && (
        <div className="rounded border border-yellow-200 bg-yellow-50 text-yellow-800 p-2 text-xs">
          ⚠️ 注意：此结果为模拟数据（formulas 库不可用）
        </div>
      )}
      <div className={`rounded border p-2 text-xs ${cls}`}>{msg}</div>
    </div>
  );
}

/** 下载区：简化版直接下载 + 完整版密码门槛 */
function DownloadSection({ sessionId }: { sessionId: string }) {
  const [password, setPassword] = useState<string>("");
  const [pwError, setPwError] = useState<string>("");
  const [verified, setVerified] = useState<boolean>(false);

  const verify = useCallback(async () => {
    setPwError("");
    try {
      // 用 HEAD 校验密码：命中 200 视为通过
      const res = await fetch(resultDownloadUrl(sessionId, "calculation_result.xlsx", password), {
        method: "HEAD",
      });
      if (res.ok) {
        setVerified(true);
      } else if (res.status === 403) {
        setPwError("密码错误，请联系管理员");
      } else {
        setPwError(`校验失败：${res.status}`);
      }
    } catch (e) {
      setPwError((e as Error).message);
    }
  }, [sessionId, password]);

  return (
    <div className="space-y-3 border-t border-green-200 pt-4">
      <h4 className="text-sm font-medium text-green-900">📥 下载计算结果</h4>

      {/* 简化版：直接下载 */}
      <div className="flex items-center gap-3 text-sm">
        <a
          href={resultDownloadUrl(sessionId, "simplified_result.xlsx")}
          className="px-3 py-2 rounded bg-green-600 text-white hover:bg-green-700"
          download
        >
          下载简化版 Excel
        </a>
        <span className="text-xs text-gray-500">只含原始电量和节能量核心结果</span>
      </div>

      {/* 完整版：密码门槛 */}
      <div className="rounded border border-green-100 bg-white p-3 space-y-2">
        <div className="text-xs text-gray-600">
          完整计算表格包含详细计算过程和中间数据，需管理员密码下载
        </div>
        {verified ? (
          <a
            href={resultDownloadUrl(sessionId, "calculation_result.xlsx", password)}
            className="inline-block px-3 py-2 rounded bg-purple-600 text-white text-sm hover:bg-purple-700"
            download
          >
            下载完整计算表格
          </a>
        ) : (
          <div className="flex items-center gap-2">
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入管理员密码"
              className="px-2 py-1 border border-gray-300 rounded text-sm"
            />
            <button
              onClick={verify}
              disabled={!password}
              className="px-3 py-1 rounded bg-gray-700 text-white text-sm hover:bg-gray-800 disabled:bg-gray-300"
            >
              验证
            </button>
          </div>
        )}
        {pwError && <div className="text-xs text-red-600">❌ {pwError}</div>}
      </div>
    </div>
  );
}
