"use client";

import { useState } from "react";
import { executeSimulation, fetchSimResult, type SimState, type SimResult } from "@/lib/api";

interface Props {
  sessionId: string;
  simState: SimState;
  onSimComplete: () => void;
}

export function SimulateStage({ sessionId, simState, onSimComplete }: Props) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SimResult | null>(simState.sim_result);

  const handleExecute = async () => {
    setRunning(true);
    setError(null);
    try {
      await executeSimulation(sessionId);
      // 等待完成后轮询结果
      const poll = setInterval(async () => {
        try {
          const r = await fetchSimResult(sessionId);
          if (r) {
            setResult(r);
            clearInterval(poll);
            setRunning(false);
            onSimComplete();
          }
        } catch {
          // 仍在运行
        }
      }, 5000);
      // 10分钟超时
      setTimeout(() => {
        clearInterval(poll);
        setRunning(false);
        setError("仿真超时（10分钟）");
      }, 600000);
    } catch (e) {
      setRunning(false);
      setError(String(e));
    }
  };

  // 已有结果
  if (result) {
    return <SimResultDisplay result={result} sessionId={sessionId} />;
  }

  return (
    <div>
      <h3 className="text-lg font-bold mb-4">Step 4: 仿真执行</h3>

      <div className="bg-gray-50 border rounded-lg p-4 mb-6">
        <h4 className="font-bold text-sm mb-2">仿真输入汇总</h4>
        <div className="text-xs text-gray-600 space-y-1">
          <div>项目名称: {simState.sim_project_name || "未知"}</div>
          <div>模式: {simState.sim_mode === "old_station" ? "旧站房（基准+优化对比）" : "新站房"}</div>
          <div>冷水主机: {simState.sim_topology?.chillers?.length ?? 0} 种型号</div>
          <div>COP 数据: {Object.keys(simState.sim_cop_data).length} 组</div>
          <div>工况数据: {simState.sim_operating_conditions ? "已就绪" : "缺失"}</div>
        </div>
      </div>

      <button
        onClick={handleExecute}
        disabled={running}
        className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
      >
        {running ? "仿真执行中（可能需要数分钟）..." : "开始仿真"}
      </button>

      {error && <div className="text-red-600 text-sm mt-4">{error}</div>}
      {running && (
        <div className="text-sm text-gray-500 mt-4">
          AI 正在生成仿真脚本并执行，请查看上方日志面板了解进度...
        </div>
      )}
    </div>
  );
}

function SimResultDisplay({ result, sessionId }: { result: SimResult; sessionId: string }) {
  const { summary, report, files, output_dir } = result;

  return (
    <div>
      <h3 className="text-lg font-bold mb-4">仿真结果</h3>

      {/* 核心指标 */}
      {summary && (
        <div className="grid grid-cols-4 gap-4 mb-6">
          <MetricCard label="全年加权COP" value={summary.annual_cop?.toFixed(2) ?? "-"} />
          <MetricCard label="年总耗电量" value={`${(summary.annual_power_mwh ?? 0).toFixed(0)} MWh`} />
          <MetricCard label="年总供冷量" value={`${(summary.annual_cooling_mwh ?? 0).toFixed(0)} MWh`} />
          <MetricCard
            label="节能率"
            value={summary.energy_saving_rate != null ? `${(summary.energy_saving_rate * 100).toFixed(1)}%` : "-"}
          />
        </div>
      )}

      {/* 图表 */}
      {files?.filter((f) => f.endsWith(".png")).length > 0 && (
        <div className="mb-6">
          <h4 className="font-bold mb-2">分析图表</h4>
          <div className="grid grid-cols-2 gap-4">
            {files.filter((f) => f.endsWith(".png")).map((f) => (
              <img
                key={f}
                src={`${process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/api"}/sim/download/${sessionId}/${f}`}
                alt={f}
                className="border rounded max-h-64 object-contain"
              />
            ))}
          </div>
        </div>
      )}

      {/* 报告 */}
      {report && (
        <div className="mb-6">
          <h4 className="font-bold mb-2">仿真分析报告</h4>
          <div className="prose prose-sm max-w-none border rounded-lg p-4 bg-white">
            <div dangerouslySetInnerHTML={{ __html: markdownToHtml(report) }} />
          </div>
        </div>
      )}

      {/* 文件下载 */}
      {files?.length > 0 && (
        <div className="mb-6">
          <h4 className="font-bold mb-2">下载仿真结果</h4>
          <div className="flex flex-wrap gap-2">
            {files
              .filter((f) => [".xlsx", ".csv", ".md", ".json"].some((ext) => f.endsWith(ext)))
              .map((f) => (
                <a
                  key={f}
                  href={`${process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/api"}/sim/download/${sessionId}/${f}`}
                  className="px-3 py-1 border rounded text-sm hover:bg-gray-50"
                  download
                >
                  {f}
                </a>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="border rounded-lg p-4 text-center">
      <div className="text-2xl font-bold text-indigo-600">{value}</div>
      <div className="text-xs text-gray-500 mt-1">{label}</div>
    </div>
  );
}

function markdownToHtml(md: string): string {
  // 简单 markdown → html（仅处理标题和段落）
  return md
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n\n/g, "</p><p>")
    .replace(/^/, "<p>")
    .replace(/$/, "</p>");
}
