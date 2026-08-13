"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  API_BASE,
  quoteUpload,
  quotePrecheck,
  quoteExtractStart,
  quoteExtractResult,
  quoteCalculateStart,
  quoteCalculateResult,
  quoteAudit,
  quoteGenerateStart,
  quoteGenerateResult,
  quoteDownloadUrl,
  type QuoteProjectData,
  type QuoteBottomSheet,
  type QuoteBottomSheetItem,
} from "@/lib/api";

type Stage = "upload" | "uploaded" | "extracting" | "extracted" | "calculating" | "calculated" | "generating" | "done" | "error";

interface LogEntry {
  timestamp: string;
  message: string;
}

type Candidate = NonNullable<QuoteBottomSheetItem["candidates"]>[number];

function candidateLabel(c: Candidate): string {
  const primary = c.model || c.name || c.type || c.aperture || c.brand || "候选";
  const secondary =
    (c.name && c.name !== primary && c.name) ||
    (c.type && c.type !== primary && c.type) ||
    (c.category && c.category !== primary && c.category) ||
    (c.aperture && c.aperture !== primary && c.aperture) ||
    (c.current != null && `${c.current}A`) ||
    "";
  const label = secondary ? `${primary} · ${secondary}` : primary;
  return label.length > 28 ? label.slice(0, 27) + "…" : label;
}

function candidateTooltip(c: Candidate): string {
  const parts: string[] = [];
  if (c.brand) parts.push(`品牌:${c.brand}`);
  if (c.name) parts.push(`名称:${c.name}`);
  if (c.model) parts.push(`型号:${c.model}`);
  if (c.type) parts.push(`类型:${c.type}`);
  if (c.category) parts.push(`分类:${c.category}`);
  if (c.aperture) parts.push(`孔径:${c.aperture}`);
  if (c.current != null) parts.push(`电流:${c.current}A`);
  parts.push(`标准¥${c.standard_price}`);
  parts.push(`渠道¥${c.channel_price}`);
  return parts.join("  ·  ");
}

export function QuoteWorkflow() {
  const [stage, setStage] = useState<Stage>("upload");
  const [sessionId, setSessionId] = useState("");
  const [error, setError] = useState("");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [projectData, setProjectData] = useState<QuoteProjectData | null>(null);
  const [parseMode, setParseMode] = useState<"ai" | "local">("ai");
  const [bottomSheet, setBottomSheet] = useState<QuoteBottomSheet | null>(null);
  const [generatedFiles, setGeneratedFiles] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [dataWarnings, setDataWarnings] = useState<
    Array<{
      type?: string;
      source?: string;
      item?: string;
      message?: string;
      description?: string;
      detail?: string;
      severity?: string;
    }>
  >([]);
  const [section9Result, setSection9Result] = useState<{
    is_standard: boolean;
    confidence: string;
    nonstandard_items: Array<{ keyword: string; context: string }>;
    explanation: string;
  } | null>(null);
  const [priceInputs, setPriceInputs] = useState<Record<string, { standard: string; channel: string }>>({});
  const [riskSkip, setRiskSkip] = useState(false);
  const [fileName, setFileName] = useState("");
  const [failedStage, setFailedStage] = useState<Stage | null>(null);
  const [precheckLoading, setPrecheckLoading] = useState(false);
  const [precheckIssues, setPrecheckIssues] = useState<Array<{ section?: string; option?: string; description?: string; severity?: string }>>([]);
  const [precheckSummary, setPrecheckSummary] = useState("");
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const appendLog = useCallback((timestamp: string, message: string) => {
    setLogs((prev) => [...prev, { timestamp, message }]);
  }, []);

  const consumeSSE = useCallback(
    (streamUrl: string, onComplete: () => void, onError: (msg: string) => void) => {
      const url = `${API_BASE.replace("/api", "")}${streamUrl}`;
      const es = new EventSource(url);
      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (data.timestamp && data.message) {
            appendLog(data.timestamp, data.message);
          }
          if (data.type === "complete") {
            es.close();
            onComplete();
          } else if (data.type === "error") {
            es.close();
            onError(data.message);
          }
        } catch {
          /* ignore */
        }
      };
      es.onerror = () => {
        es.close();
      };
      return es;
    },
    [appendLog]
  );

  const handleUpload = async (file: File) => {
    setError("");
    setLogs([]);
    setPrecheckIssues([]);
    setPrecheckSummary("");
    setRunning(true);
    setFileName(file.name);
    try {
      appendLog(new Date().toLocaleTimeString(), `上传文件: ${file.name}`);
      const res = await quoteUpload(file);
      setSessionId(res.session_id);
      appendLog(new Date().toLocaleTimeString(), `Session: ${res.session_id}`);

      setPrecheckLoading(true);
      setStage("uploaded");
      try {
        const precheck = await quotePrecheck(res.session_id);
        setPrecheckIssues(precheck.detected_issues || []);
        setPrecheckSummary(precheck.summary || "");
      } catch (e: unknown) {
        setPrecheckSummary(`预检跳过: ${e}`);
      }
      setPrecheckLoading(false);
      setRunning(false);
    } catch (e: unknown) {
      setError(String(e));
      setFailedStage("upload");
      setStage("error");
      setRunning(false);
    }
  };

  const handleStartExtract = async () => {
    if (!sessionId) return;
    setRunning(true);
    setError("");
    setStage("extracting");
    try {
      const extRes = await quoteExtractStart(sessionId);
      consumeSSE(
        extRes.stream_url,
        async () => {
          const result = await quoteExtractResult(sessionId);
          if (result) {
            setProjectData(result.project_data);
            setParseMode(result.parse_mode);
            setDataWarnings(result.data_warnings || []);
            setStage("extracted");
          }
          setRunning(false);
        },
        (msg) => {
          setError(msg);
          setFailedStage("extracting");
          setStage("error");
          setRunning(false);
        }
      );
    } catch (e: unknown) {
      setError(String(e));
      setFailedStage("extracting");
      setStage("error");
      setRunning(false);
    }
  };

  const handleCalculate = async () => {
    if (!sessionId) return;
    setRunning(true);
    setError("");
    setStage("calculating");
    try {
      appendLog(new Date().toLocaleTimeString(), "开始计算报价...");
      const calcRes = await quoteCalculateStart(sessionId);

      consumeSSE(
        calcRes.stream_url,
        async () => {
          const result = await quoteCalculateResult(sessionId);
          if (result) {
            setBottomSheet(result.bottom_sheet);
            setSection9Result(result.section9_result || null);
          }
          setStage("calculated");
          setRunning(false);
        },
        (msg) => {
          setError(msg);
          setFailedStage("calculating");
          setStage("error");
          setRunning(false);
        }
      );
    } catch (e: unknown) {
      setError(String(e));
      setFailedStage("calculating");
      setStage("error");
      setRunning(false);
    }
  };

  const handleAudit = async (
    itemKey: string,
    action: string,
    extra?: { candidate_index?: number; standard_price?: number; channel_price?: number }
  ) => {
    try {
      const res = await quoteAudit(sessionId, itemKey, action, extra);
      setBottomSheet((prev) => {
        if (!prev) return prev;
        const updated = { ...prev, status_summary: res.status_summary };
        const prefix = itemKey.split("_")[0];
        const idx = parseInt(itemKey.split("_")[1]);
        const zoneMap: Record<string, keyof QuoteBottomSheet> = {
          sw: "software_items",
          hw: "hardware_items",
          ct: "construction_items",
        };
        const zone = zoneMap[prefix];
        if (zone && updated[zone]) {
          const items = [...(updated[zone] as QuoteBottomSheetItem[])];
          items[idx] = { ...items[idx], status: res.new_status as QuoteBottomSheetItem["status"], ...(res.updated_fields || {}) };
          (updated as Record<string, unknown>)[zone as string] = items;
        }
        return updated;
      });
    } catch (e: unknown) {
      setError(String(e));
    }
  };

  const handleGenerate = async () => {
    if (!sessionId) return;
    setRunning(true);
    setError("");
    setStage("generating");
    try {
      appendLog(new Date().toLocaleTimeString(), "开始生成报价表和方案...");
      const genRes = await quoteGenerateStart(sessionId);

      consumeSSE(
        genRes.stream_url,
        async () => {
          const result = await quoteGenerateResult(sessionId);
          if (result) {
            setGeneratedFiles(result.files);
          }
          setStage("done");
          setRunning(false);
        },
        (msg) => {
          setError(msg);
          setFailedStage("generating");
          setStage("error");
          setRunning(false);
        }
      );
    } catch (e: unknown) {
      setError(String(e));
      setFailedStage("generating");
      setStage("error");
      setRunning(false);
    }
  };

  const canGenerate = (() => {
    if (!bottomSheet) return false;
    const s = bottomSheet.status_summary;
    const hardBlock = (s.NONSTANDARD || 0) + (s.BLOCKED || 0);
    if (hardBlock > 0) return false;
    const pending = (s.CONFIRM || 0) + (s.INQUIRY || 0);
    if (pending === 0) return true;
    return riskSkip;
  })();

  const hasSoftBlock = bottomSheet
    ? (bottomSheet.status_summary.CONFIRM || 0) + (bottomSheet.status_summary.INQUIRY || 0) > 0
    : false;

  const hardBlock = bottomSheet
    ? (bottomSheet.status_summary.NONSTANDARD || 0) + (bottomSheet.status_summary.BLOCKED || 0) > 0
    : false;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-5xl mx-auto py-8 px-6">
        <h1 className="text-2xl font-bold mb-6">💰 智能生成报价表</h1>

        {/* Progress */}
        <div className="flex gap-2 mb-6 text-sm">
          {(["upload", "uploaded", "extracting", "extracted", "calculating", "calculated", "generating", "done"] as Stage[]).map(
            (s, i) => (
              <div
                key={s}
                className={`px-3 py-1 rounded-full ${
                  stage === s
                    ? "bg-indigo-600 text-white"
                    : (["upload", "uploaded", "extracting", "extracted", "calculating", "calculated", "generating", "done"].indexOf(stage) > i)
                    ? "bg-green-100 text-green-700"
                    : "bg-gray-100 text-gray-400"
                }`}
              >
                {["上传", "预检", "解析", "已解析", "计算", "已计算", "生成", "完成"][i]}
              </div>
            )
          )}
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4">
            <div className="mb-2">{error}</div>
            <div className="flex gap-2 flex-wrap">
              {failedStage === "upload" && (
                <button className="text-sm px-3 py-1 bg-white border rounded hover:bg-gray-50" onClick={() => { setError(""); setFailedStage(null); setStage("upload"); setRunning(false); }}>
                  重新上传
                </button>
              )}
              {failedStage === "extracting" && (
                <>
                  <button className="text-sm px-3 py-1 bg-red-100 rounded hover:bg-red-200" onClick={() => { setError(""); setFailedStage(null); handleStartExtract(); }}>
                    重试解析
                  </button>
                  <button className="text-sm px-3 py-1 bg-white border rounded hover:bg-gray-50" onClick={() => { setError(""); setFailedStage(null); setStage("uploaded"); setRunning(false); }}>
                    返回预检
                  </button>
                </>
              )}
              {failedStage === "calculating" && (
                <>
                  <button className="text-sm px-3 py-1 bg-red-100 rounded hover:bg-red-200" onClick={() => { setError(""); setFailedStage(null); handleCalculate(); }}>
                    重试计算
                  </button>
                  <button className="text-sm px-3 py-1 bg-white border rounded hover:bg-gray-50" onClick={() => { setError(""); setFailedStage(null); setStage("extracted"); setRunning(false); }}>
                    返回已解析
                  </button>
                </>
              )}
              {failedStage === "generating" && (
                <>
                  <button className="text-sm px-3 py-1 bg-red-100 rounded hover:bg-red-200" onClick={() => { setError(""); setFailedStage(null); handleGenerate(); }}>
                    重试生成
                  </button>
                  <button className="text-sm px-3 py-1 bg-white border rounded hover:bg-gray-50" onClick={() => { setError(""); setFailedStage(null); setStage("calculated"); setRunning(false); }}>
                    返回已计算
                  </button>
                </>
              )}
              <button className="text-sm px-3 py-1 bg-white border rounded hover:bg-gray-50" onClick={() => { setError(""); setFailedStage(null); setStage("upload"); setRunning(false); setSessionId(""); }}>
                从头开始
              </button>
            </div>
          </div>
        )}

        {/* Upload */}
        {stage === "upload" && (
          <div className="border-2 border-dashed rounded-xl p-12 text-center bg-white">
            <p className="text-gray-500 mb-4">上传报价调研表 (.xlsx)</p>
            <input
              type="file"
              accept=".xlsx,.xls"
              onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
              className="mx-auto"
              disabled={running}
            />
          </div>
        )}

        {/* Uploaded - Precheck */}
        {stage === "uploaded" && (
          <div className="bg-white rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-bold">已上传: {fileName}</h2>
              <button
                className="ml-4 text-sm text-gray-500 underline"
                onClick={() => { setStage("upload"); setSessionId(""); }}
              >
                重新上传
              </button>
            </div>

            {precheckLoading && (
              <div className="text-gray-500 py-4">AI 正在检测调研表质量问题...</div>
            )}

            {!precheckLoading && precheckIssues.length > 0 && (
              <div className="mb-4">
                <div className="bg-yellow-50 border border-yellow-200 rounded p-3 mb-2">
                  <span className="font-medium">⚠️ {precheckSummary}（{precheckIssues.length} 项问题）</span>
                </div>
                <details open className="text-sm">
                  <summary className="cursor-pointer font-medium mb-1">📋 查看问题详情</summary>
                  <ul className="list-disc pl-5 space-y-1">
                    {precheckIssues.map((issue, i) => (
                      <li key={i}>
                        <span>{issue.severity === "nonstandard" ? "🔴" : "⚠️"}</span>
                        <b>[{issue.section || "未知"}]</b> {issue.description}
                        {issue.option && <span className="text-gray-500">（{issue.option}）</span>}
                      </li>
                    ))}
                  </ul>
                </details>
              </div>
            )}

            {!precheckLoading && precheckIssues.length === 0 && precheckSummary && !precheckSummary.startsWith("预检跳过") && (
              <div className="bg-green-50 border border-green-200 rounded p-3 mb-4">
                ✅ 调研表格式完整，无缺项漏项
              </div>
            )}

            {!precheckLoading && precheckSummary.startsWith("预检跳过") && (
              <div className="bg-gray-50 border border-gray-200 rounded p-3 mb-4 text-gray-500">
                {precheckSummary}
              </div>
            )}

            <button
              onClick={handleStartExtract}
              disabled={running}
              className="w-full py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 font-medium"
            >
              🚀 开始 AI 识别
            </button>
          </div>
        )}

        {/* Extracting */}
        {stage === "extracting" && (
          <div className="bg-white rounded-xl p-6">
            <h2 className="font-bold mb-4">AI 解析中...</h2>
            <div className="h-64 overflow-y-auto bg-gray-50 rounded p-3 text-sm font-mono">
              {logs.map((l, i) => (
                <div key={i}>
                  <span className="text-gray-400">[{l.timestamp}]</span> {l.message}
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          </div>
        )}

        {/* Extracted - Review */}
        {stage === "extracted" && projectData && (
          <div className="bg-white rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-bold">
                解析结果
                <span className={`ml-2 text-xs font-normal px-2 py-0.5 rounded align-middle ${
                  parseMode === "local" ? "bg-orange-100 text-orange-700" : "bg-blue-100 text-blue-700"
                }`}>
                  {parseMode === "local" ? "📐 本地解析" : "🤖 AI 解析"}
                </span>
              </h2>
              <div className="flex gap-2">
                <button
                  onClick={() => { setStage("upload"); setProjectData(null); setDataWarnings([]); setError(""); }}
                  className="px-4 py-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200 text-sm"
                >
                  返回重新上传
                </button>
                <button
                  onClick={handleCalculate}
                  disabled={running}
                  className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
                >
                  {running ? "计算中..." : "开始计算"}
                </button>
              </div>
            </div>

            {dataWarnings.length > 0 && (
              <details open className="mb-4 border border-yellow-200 bg-yellow-50 rounded p-3">
                <summary className="cursor-pointer text-sm font-semibold text-yellow-800">
                  ⚠️ 数据提醒 ({dataWarnings.length} 项)
                </summary>
                <div className="mt-2 space-y-2 text-xs">
                  {dataWarnings.map((w, i) => {
                    const wtype = w.type || "";
                    const icon = wtype === "contradiction" ? "⚠️" : wtype === "logic_gap" ? "🔍" : "ℹ️";
                    const severityLabel = w.severity && w.severity !== wtype ? w.severity : "";
                    return (
                      <div key={i} className="border-l-2 border-yellow-300 pl-2">
                        <div className="flex gap-2">
                          <span className="shrink-0" title={wtype}>{icon}</span>
                          <span>
                            {w.item && <span className="font-semibold">{w.item}</span>}
                            {w.item && " — "}
                            {w.message || w.description}
                          </span>
                        </div>
                        {(w.source || wtype || severityLabel) && (
                          <div className="text-[11px] text-yellow-700/70 mt-0.5">
                            {wtype && <span className="mr-2">[{wtype}]</span>}
                            {w.source && <span>来源: {w.source}</span>}
                          </div>
                        )}
                        {w.detail && (
                          <div className="text-[11px] text-gray-600 mt-0.5 italic">详情: {w.detail}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </details>
            )}

            <div className="grid grid-cols-2 gap-4 text-sm">
              <div><span className="text-gray-500">客户:</span> {projectData.client_name}</div>
              <div><span className="text-gray-500">项目:</span> {projectData.project_name}</div>
              <div><span className="text-gray-500">地点:</span> {projectData.project_location}</div>
              <div><span className="text-gray-500">部署:</span> {projectData.deployment_mode}</div>
            </div>
            {projectData.new_meters?.electric?.length > 0 && (
              <details className="mt-4">
                <summary className="cursor-pointer font-semibold text-sm">新增电表 ({projectData.new_meters.electric.length} 个)</summary>
                <div className="mt-1 max-h-32 overflow-y-auto text-xs bg-gray-50 rounded p-2">
                  {projectData.new_meters.electric.map((m, i) => (
                    <div key={i}>
                      {m.location} × {m.quantity}
                      {(m.ct_current || m.ct_type) && (
                        <span className="text-gray-500"> (CT: {m.ct_current || ""}A {m.ct_type || ""})</span>
                      )}
                    </div>
                  ))}
                </div>
              </details>
            )}
            {projectData.new_meters?.water?.length > 0 && (
              <details className="mt-4">
                <summary className="cursor-pointer font-semibold text-sm">新增水表 ({projectData.new_meters.water.length} 个)</summary>
                <div className="mt-1 max-h-32 overflow-y-auto text-xs bg-gray-50 rounded p-2">
                  {projectData.new_meters.water.map((m, i) => (
                    <div key={i}>{m.location} DN{m.dn} × {m.quantity}</div>
                  ))}
                </div>
              </details>
            )}
            {projectData.new_meters?.flow_meters?.length > 0 && (
              <details className="mt-4">
                <summary className="cursor-pointer font-semibold text-sm">流量计 ({projectData.new_meters.flow_meters.length} 个)</summary>
                <div className="mt-1 max-h-32 overflow-y-auto text-xs bg-gray-50 rounded p-2">
                  {projectData.new_meters.flow_meters.map((m, i) => (
                    <div key={i}>{m.medium || "(未注明介质)"} DN{m.dn} × {m.quantity}</div>
                  ))}
                </div>
              </details>
            )}
            {projectData.third_party_systems?.length > 0 && (
              <details className="mt-4">
                <summary className="cursor-pointer font-semibold text-sm">第三方系统 ({projectData.third_party_systems.length} 个)</summary>
                <div className="mt-1 max-h-40 overflow-y-auto text-xs bg-gray-50 rounded p-2 space-y-1">
                  {projectData.third_party_systems.map((s, i) => (
                    <div key={i}>
                      <div className="font-medium">{s.name} <span className="text-gray-500 font-normal">({s.type})</span></div>
                      {s.direction && (
                        <div className="text-gray-700 pl-2">🔗 接入方向: <span className="font-medium text-orange-700">{s.direction}</span></div>
                      )}
                      {s.description && (
                        <div className="text-gray-600 pl-2">📝 {s.description}</div>
                      )}
                    </div>
                  ))}
                </div>
              </details>
            )}
            {projectData.optional_modules?.selected_modules?.length > 0 && (
              <details className="mt-4">
                <summary className="cursor-pointer font-semibold text-sm">可选模块 ({projectData.optional_modules.selected_modules.length} 个)</summary>
                <div className="mt-1 text-xs bg-gray-50 rounded p-2 space-y-1">
                  {projectData.optional_modules.selected_modules.map((m, i) => (
                    <div key={i}>
                      <div className="font-medium">{m.name}</div>
                      <div className="text-gray-600 pl-2">
                        范围: {m.scope || "-"}
                        {m.quantity_name && (
                          <span className="ml-3">数量: {m.quantity_name}</span>
                        )}
                        {m.customer_request?.trim() && (
                          <div className="mt-0.5">客户要求: {m.customer_request}</div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            )}
            {((projectData.optional_modules as Record<string, unknown>)?.extra_items as Array<Record<string, unknown>> | undefined)?.length ? (
              <details className="mt-4">
                <summary className="cursor-pointer font-semibold text-sm">
                  附加项 ({((projectData.optional_modules as Record<string, unknown>).extra_items as unknown[]).length} 个)
                </summary>
                <div className="mt-1 text-xs bg-gray-50 rounded p-2">
                  {((projectData.optional_modules as Record<string, unknown>).extra_items as Array<Record<string, unknown>>).map((it, i) => (
                    <div key={i}>{String(it.type || "")} × {String(it.quantity || 0)}{it.customer_artwork ? ` (${String(it.customer_artwork)})` : ""}</div>
                  ))}
                </div>
              </details>
            ) : null}
            {logs.length > 0 && (
              <details className="mt-4">
                <summary className="cursor-pointer font-semibold text-sm">📝 识别日志 ({logs.length} 条)</summary>
                <div className="mt-1 max-h-48 overflow-y-auto text-xs bg-gray-900 text-gray-100 rounded p-3 font-mono">
                  {logs.map((l, i) => (
                    <div key={i}>
                      <span className="text-gray-500">[{l.timestamp}]</span> {l.message}
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}

        {/* Calculated - Audit */}
        {stage === "calculated" && bottomSheet && (
          <div className="bg-white rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-bold">报价审核台</h2>
              <div className="flex gap-2 text-xs">
                {Object.entries(bottomSheet.status_summary).map(([k, v]) => (
                  <span key={k} className={`px-2 py-1 rounded ${
                    k === "AUTO" ? "bg-green-100 text-green-700" :
                    k === "CONFIRM" ? "bg-yellow-100 text-yellow-700" :
                    k === "INQUIRY" ? "bg-orange-100 text-orange-700" :
                    k === "NONSTANDARD" ? "bg-red-100 text-red-700" :
                    k === "BLOCKED" ? "bg-gray-400 text-white" :
                    "bg-gray-200 text-gray-600"
                  }`}>
                    {k}: {v as number}
                  </span>
                ))}
              </div>
            </div>

            {section9Result && !section9Result.is_standard && (
              <details className="mb-4 border border-red-200 bg-red-50 rounded p-3">
                <summary className="cursor-pointer text-sm font-semibold text-red-800">
                  ⚠️ 检测到 {section9Result.nonstandard_items?.length || 0} 项非标（置信度: {section9Result.confidence}）
                </summary>
                <div className="mt-2 text-xs space-y-1">
                  <div className="italic text-red-700">{section9Result.explanation}</div>
                  {section9Result.nonstandard_items?.map((it, i) => (
                    <div key={i} className="flex gap-2">
                      <span className="font-medium shrink-0">[{it.keyword}]</span>
                      <span className="text-gray-700">{it.context}</span>
                    </div>
                  ))}
                </div>
              </details>
            )}

            {/* Totals */}
            <div className="grid grid-cols-2 gap-4 mb-6 p-3 bg-gray-50 rounded text-sm">
              <div>标准价合计: <span className="font-bold text-lg">¥{(bottomSheet.totals.grand_total_standard || 0).toLocaleString()}</span></div>
              <div>渠道价合计: <span className="font-bold text-lg">¥{(bottomSheet.totals.grand_total_channel || 0).toLocaleString()}</span></div>
            </div>

            {/* Items by zone */}
            {(["software_items", "hardware_items", "construction_items"] as const).map((zone) => {
              const items = bottomSheet[zone] as QuoteBottomSheetItem[];
              if (!items || items.length === 0) return null;
              const prefix = zone === "software_items" ? "sw" : zone === "hardware_items" ? "hw" : "ct";
              const label = zone === "software_items" ? "软件" : zone === "hardware_items" ? "硬件" : "施工";
              return (
                <div key={zone} className="mb-4">
                  <h3 className="font-semibold text-sm mb-2">{label} ({items.length} 项)</h3>
                  <div className="space-y-1">
                    {items.map((item, idx) => {
                      const itemKey = `${prefix}_${idx}`;
                      const statusColor =
                        item.status === "AUTO" ? "border-green-200 bg-green-50" :
                        item.status === "CONFIRM" ? "border-yellow-200 bg-yellow-50" :
                        item.status === "INQUIRY" ? "border-orange-200 bg-orange-50" :
                        item.status === "NONSTANDARD" ? "border-red-200 bg-red-50" :
                        "border-gray-300 bg-gray-100";
                      return (
                        <div key={idx} className={`border rounded p-2 text-xs ${statusColor}`}>
                          <div className="flex justify-between items-start">
                            <div>
                              <span className="font-medium">{item.device_name || item.module || item.description || itemKey}</span>
                              {item.brand && <span className="ml-2 text-gray-500">{item.brand} {item.model}</span>}
                              <span className="ml-2 text-gray-400">×{item.quantity} {item.unit || "个"}</span>
                            </div>
                            <div className="text-right">
                              <div>标准 ¥{(item.standard_price || 0).toLocaleString()} / 渠道 ¥{(item.channel_price || 0).toLocaleString()}</div>
                            </div>
                          </div>
                          {(item.location || item.description) && item.status !== "AUTO" && (
                            <div className="text-[11px] text-gray-600 mt-1 space-y-0.5">
                              {item.location && (
                                <div>📍 位置: {item.location}</div>
                              )}
                              {item.description && item.description !== item.device_name && item.description !== item.module && (
                                <div>📝 说明: {item.description}</div>
                              )}
                            </div>
                          )}
                          {item.status !== "AUTO" && (
                            <div className="mt-2 space-y-1">
                              {item.status === "CONFIRM" && item.candidates && (
                                <div className="flex gap-1 flex-wrap">
                                  {item.candidates.map((c, ci) => (
                                    <button
                                      key={ci}
                                      onClick={() => handleAudit(itemKey, "select_candidate", { candidate_index: ci })}
                                      className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
                                      title={candidateTooltip(c)}
                                    >
                                      选{candidateLabel(c)}
                                    </button>
                                  ))}
                                  <button
                                    onClick={() => handleAudit(itemKey, "approve")}
                                    className="px-2 py-0.5 bg-green-100 text-green-700 rounded hover:bg-green-200"
                                  >
                                    确认当前
                                  </button>
                                </div>
                              )}
                              {(item.status === "INQUIRY" || item.status === "NONSTANDARD") && (
                                <div className="flex gap-1 items-center flex-wrap">
                                  <input
                                    type="number"
                                    placeholder={`标准价 (${item.standard_price || 0})`}
                                    value={priceInputs[itemKey]?.standard ?? ""}
                                    onChange={(e) =>
                                      setPriceInputs((p) => ({
                                        ...p,
                                        [itemKey]: { ...p[itemKey], standard: e.target.value, channel: p[itemKey]?.channel ?? "" },
                                      }))
                                    }
                                    className="w-28 px-2 py-0.5 border rounded text-xs"
                                  />
                                  <input
                                    type="number"
                                    placeholder={`渠道价 (${item.channel_price || 0})`}
                                    value={priceInputs[itemKey]?.channel ?? ""}
                                    onChange={(e) =>
                                      setPriceInputs((p) => ({
                                        ...p,
                                        [itemKey]: { ...p[itemKey], channel: e.target.value, standard: p[itemKey]?.standard ?? "" },
                                      }))
                                    }
                                    className="w-28 px-2 py-0.5 border rounded text-xs"
                                  />
                                  <button
                                    onClick={() => {
                                      const pi = priceInputs[itemKey];
                                      handleAudit(itemKey, "update_price", {
                                        standard_price: pi?.standard !== "" && pi?.standard != null ? parseFloat(pi.standard) : item.standard_price,
                                        channel_price: pi?.channel !== "" && pi?.channel != null ? parseFloat(pi.channel) : item.channel_price,
                                      });
                                    }}
                                    className="px-2 py-0.5 bg-green-100 text-green-700 rounded hover:bg-green-200"
                                  >
                                    提交价格
                                  </button>
                                  <button
                                    onClick={() => handleAudit(itemKey, "update_price", {
                                      standard_price: item.standard_price,
                                      channel_price: item.channel_price,
                                    })}
                                    className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
                                  >
                                    接受当前
                                  </button>
                                </div>
                              )}
                              <div className="flex gap-1 flex-wrap">
                                {item.status === "BLOCKED" && (
                                  <button
                                    onClick={() => handleAudit(itemKey, "nstd")}
                                    className="px-2 py-0.5 bg-orange-100 text-orange-700 rounded hover:bg-orange-200"
                                  >
                                    转非标
                                  </button>
                                )}
                                <button
                                  onClick={() => handleAudit(itemKey, "approve")}
                                  className="px-2 py-0.5 bg-green-100 text-green-700 rounded hover:bg-green-200"
                                >
                                  已处理
                                </button>
                                <button
                                  onClick={() => handleAudit(itemKey, "reject")}
                                  className="px-2 py-0.5 bg-red-100 text-red-700 rounded hover:bg-red-200"
                                >
                                  驳回
                                </button>
                              </div>
                              {item.confirm_note && (
                                <div className="mt-1 px-2 py-1 bg-blue-50 border border-blue-200 rounded text-blue-800 text-[11px]">
                                  💬 {item.confirm_note}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}

            <div className="mt-6 flex justify-end items-center gap-2">
              <button
                onClick={() => setStage("extracted")}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200 text-sm"
              >
                返回查看数据
              </button>
              {hardBlock && (
                <span className="text-red-600 text-sm">存在未处理的非标/阻断项，请先处理后再生成</span>
              )}
              {!hardBlock && hasSoftBlock && !riskSkip && (
                <button
                  onClick={() => setRiskSkip(true)}
                  className="px-4 py-2 bg-orange-100 text-orange-700 rounded hover:bg-orange-200 text-sm"
                >
                  仍有未确认项，风险自负继续
                </button>
              )}
              {!hardBlock && hasSoftBlock && riskSkip && (
                <span className="text-orange-600 text-sm">⚠️ 已开启"风险自负"模式，未确认项将按当前价格生成</span>
              )}
              <button
                onClick={() => { handleGenerate(); setRiskSkip(false); }}
                disabled={running || !canGenerate}
                className={`px-6 py-2 rounded text-white disabled:opacity-50 ${
                  riskSkip && canGenerate
                    ? "bg-orange-600 hover:bg-orange-700"
                    : "bg-indigo-600 hover:bg-indigo-700"
                }`}
              >
                {running ? "生成中..." : riskSkip ? "生成（风险自负）" : "生成报价表 + 方案"}
              </button>
            </div>
          </div>
        )}

        {/* Generating */}
        {stage === "generating" && (
          <div className="bg-white rounded-xl p-6">
            <h2 className="font-bold mb-4">生成报价表和方案文档...</h2>
            <div className="h-48 overflow-y-auto bg-gray-50 rounded p-3 text-sm font-mono">
              {logs.map((l, i) => (
                <div key={i}>
                  <span className="text-gray-400">[{l.timestamp}]</span> {l.message}
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          </div>
        )}

        {/* Done */}
        {stage === "done" && (
          <div className="bg-white rounded-xl p-6">
            <h2 className="font-bold mb-4 text-lg">✅ 生成完成</h2>
            {bottomSheet && (
              <details className="mb-4 border rounded p-3 bg-gray-50" open>
                <summary className="cursor-pointer font-semibold text-sm">最终报价底稿</summary>
                <div className="mt-2 grid grid-cols-2 gap-3 text-sm">
                  <div>标准价合计: <span className="font-bold text-indigo-700">¥{(bottomSheet.totals.grand_total_standard || 0).toLocaleString()}</span></div>
                  <div>渠道价合计: <span className="font-bold text-indigo-700">¥{(bottomSheet.totals.grand_total_channel || 0).toLocaleString()}</span></div>
                </div>
                {bottomSheet.status_summary && (
                  <div className="mt-2 flex gap-2 text-xs">
                    {Object.entries(bottomSheet.status_summary).map(([k, v]) => (
                      <span key={k} className="px-2 py-0.5 bg-white rounded border">
                        {k}: {v as number}
                      </span>
                    ))}
                  </div>
                )}
              </details>
            )}
            <h3 className="font-semibold text-sm mb-2">下载文件</h3>
            <div className="space-y-2 mb-6">
              {generatedFiles.map((f) => (
                <a
                  key={f}
                  href={quoteDownloadUrl(sessionId, f)}
                  target="_blank"
                  className="block px-4 py-2 bg-gray-50 rounded hover:bg-gray-100 text-sm"
                >
                  📄 {f}
                </a>
              ))}
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setStage("upload");
                  setSessionId("");
                  setProjectData(null);
                  setBottomSheet(null);
                  setSection9Result(null);
                  setDataWarnings([]);
                  setGeneratedFiles([]);
                  setLogs([]);
                  setPriceInputs({});
                  setRiskSkip(false);
                  setError("");
                }}
                className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 text-sm"
              >
                开始新报价
              </button>
              <button
                onClick={() => setStage("calculated")}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200 text-sm"
              >
                返回审核台
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
