"use client";

import { useState } from "react";
import {
  executeSimulation,
  fetchSimResult,
  API_BASE,
  type SimState,
  type SimResult,
  type SimComparison,
  type SimPlanSummary,
} from "@/lib/api";

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
      let timeoutId: ReturnType<typeof setTimeout>;
      const poll = setInterval(async () => {
        try {
          const r = await fetchSimResult(sessionId);
          if (r) {
            setResult(r);
            clearInterval(poll);
            clearTimeout(timeoutId);
            setRunning(false);
            onSimComplete();
          }
        } catch {
          // still running
        }
      }, 5000);
      timeoutId = setTimeout(() => {
        clearInterval(poll);
        setRunning(false);
        setError("仿真超时（15分钟）");
      }, 900000);
    } catch (e) {
      setRunning(false);
      setError(String(e));
    }
  };

  if (result) {
    return <SimResultDisplay result={result} sessionId={sessionId} />;
  }

  const baselineWan =
    simState.sim_baseline_power_kwh != null
      ? (simState.sim_baseline_power_kwh / 10000).toFixed(2)
      : null;
  const schemes = simState.sim_schemes || [];
  const isOldStation = simState.sim_mode === "old_station";

  return (
    <div>
      <h3 className="text-lg font-bold mb-4">Step 4: 仿真执行</h3>

      <div className="bg-gray-50 border rounded-lg p-4 mb-6">
        <h4 className="font-bold text-sm mb-2">仿真输入汇总</h4>
        <div className="text-xs text-gray-600 space-y-1">
          <div>项目名称: {simState.sim_project_name || "未知"}</div>
          <div>模式: {isOldStation ? "旧站房（基准+多方案对比）" : "新站房"}</div>
          <div>冷水主机: {simState.sim_topology?.chillers?.length ?? 0} 种型号</div>
          <div>COP 数据: {Object.keys(simState.sim_cop_data ?? {}).length} 组</div>
          <div>工况数据: {simState.sim_operating_conditions ? "已就绪" : "缺失"}</div>
          {isOldStation && (
            <>
              <div>
                基准耗电量:{" "}
                <span className={baselineWan ? "text-indigo-700 font-medium" : "text-red-500"}>
                  {baselineWan ? `${baselineWan} 万 kWh/年` : "未设置"}
                </span>
              </div>
              <div>
                优化方案:{" "}
                <span className={schemes.length > 0 ? "text-indigo-700 font-medium" : "text-red-500"}>
                  {schemes.length > 0
                    ? `${schemes.length} 个（${schemes
                        .map((s) => `${s.name} ${s.target_saving_rate_pct}%`)
                        .join("、")}）`
                    : "未定义"}
                </span>
              </div>
            </>
          )}
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
        <div className="mt-4 flex items-center gap-3">
          <style>{`
            @keyframes sim-spin {
              0% { transform: rotate(0deg); }
              100% { transform: rotate(360deg); }
            }
            .sim-spinner {
              width: 20px;
              height: 20px;
              border: 3px solid #e0e0e0;
              border-top-color: #4f46e5;
              border-radius: 50%;
              animation: sim-spin 0.8s linear infinite;
              display: inline-block;
            }
          `}</style>
          <span className="sim-spinner" />
          <span className="text-sm text-gray-600">
            AI 正在生成仿真脚本并执行，请查看上方日志面板了解进度...
          </span>
        </div>
      )}
    </div>
  );
}

// ============ 结果展示 ============

function SimResultDisplay({ result, sessionId }: { result: SimResult; sessionId: string }) {
  const { summary, comparison, report, files } = result;

  return (
    <div>
      <h3 className="text-lg font-bold mb-4">仿真结果</h3>

      {/* 多方案对比（优先展示） */}
      {comparison && <MultiSchemeComparison comparison={comparison} />}

      {/* 单方案核心指标（new_station 或 fallback） */}
      {!comparison && summary && (
        <div className="grid grid-cols-4 gap-4 mb-6">
          <MetricCard
            label="全年加权COP"
            value={summary.annual_cop?.toFixed(2) ?? "-"}
          />
          <MetricCard
            label="年总耗电量"
            value={
              summary.optimized_power_kwh_simulated != null
                ? `${(summary.optimized_power_kwh_simulated / 10000).toFixed(1)} 万kWh`
                : summary.annual_power_mwh != null
                ? `${summary.annual_power_mwh.toFixed(0)} MWh`
                : "-"
            }
          />
          <MetricCard
            label="基准年耗电量"
            value={
              summary.baseline_power_kwh_simulated != null
                ? `${(summary.baseline_power_kwh_simulated / 10000).toFixed(1)} 万kWh`
                : "-"
            }
          />
          <MetricCard
            label="节能率"
            value={
              summary.actual_energy_saving_rate != null
                ? `${(summary.actual_energy_saving_rate * 100).toFixed(1)}%`
                : summary.energy_saving_rate != null
                ? `${(summary.energy_saving_rate * 100).toFixed(1)}%`
                : "-"
            }
          />
        </div>
      )}

      {/* 图表 */}
      {files?.filter((f) => f.endsWith(".png")).length > 0 && (
        <div className="mb-6">
          <h4 className="font-bold mb-2">分析图表</h4>
          <div className="grid grid-cols-2 gap-4">
            {files
              .filter((f) => f.endsWith(".png"))
              .map((f) => (
                <img
                  key={f}
                  src={`${API_BASE}/sim/download/${sessionId}/${f}`}
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
                  href={`${API_BASE}/sim/download/${sessionId}/${f}`}
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

// ============ 多方案对比展示 ============

function MultiSchemeComparison({ comparison }: { comparison: SimComparison }) {
  const planKeys = Object.keys(comparison).filter(
    (k) => k.startsWith("plan_") && typeof comparison[k] === "object" && comparison[k] !== null
  );

  const allPlans: { key: string; label: string; data: SimPlanSummary }[] = [
    { key: "baseline", label: comparison.baseline.label || "基线", data: comparison.baseline },
    ...planKeys.map((k) => {
      const d = comparison[k] as SimPlanSummary;
      return { key: k, label: d.label || k, data: d };
    }),
  ];

  const baselinePower = comparison.baseline.annual_total_power_kwh;

  return (
    <div className="mb-6">
      <h4 className="font-bold mb-3 text-indigo-900">多方案对比</h4>

      {/* 年度指标横向卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        {allPlans.map((p) => {
          const saving = baselinePower - p.data.annual_total_power_kwh;
          const savingPct = baselinePower > 0 ? (saving / baselinePower) * 100 : 0;
          const isBaseline = p.key === "baseline";
          return (
            <div
              key={p.key}
              className={`border rounded-lg p-3 ${
                isBaseline ? "bg-gray-50" : "bg-indigo-50 border-indigo-200"
              }`}
            >
              <div className="text-xs text-gray-500 truncate" title={p.label}>
                {p.label}
              </div>
              <div className="text-xl font-bold text-indigo-700 mt-1">
                {(p.data.annual_total_power_kwh / 10000).toFixed(1)}
                <span className="text-xs text-gray-500 ml-1">万kWh</span>
              </div>
              <div className="text-xs text-gray-500 mt-1">
                COP: {p.data.annual_weighted_system_cop?.toFixed(2) ?? "-"}
              </div>
              {!isBaseline && (
                <div className="text-xs font-medium text-green-600 mt-1">
                  节省 {(saving / 10000).toFixed(1)}万 ({savingPct.toFixed(1)}%)
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 分项能耗对比表 */}
      <div className="overflow-x-auto border rounded mb-4">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-100">
            <tr>
              <th className="px-3 py-2 text-left">设备</th>
              {allPlans.map((p) => (
                <th key={p.key} className="px-3 py-2 text-right">
                  {p.label}
                </th>
              ))}
              {allPlans.length > 1 &&
                allPlans
                  .filter((p) => p.key !== "baseline")
                  .map((p) => (
                    <th key={`${p.key}-save`} className="px-3 py-2 text-right text-green-700">
                      {p.label} 节省
                    </th>
                  ))}
            </tr>
          </thead>
          <tbody>
            {(
              [
                ["冷水机组", "annual_chiller_power_kwh"],
                ["冷冻泵", "annual_chw_pump_power_kwh"],
                ["冷却泵", "annual_cw_pump_power_kwh"],
                ["冷却塔", "annual_tower_power_kwh"],
                ["合计", "annual_total_power_kwh"],
              ] as const
            ).map(([label, key]) => {
              const blVal = (comparison.baseline[key] as number | undefined) ?? 0;
              return (
                <tr key={key} className={key === "annual_total_power_kwh" ? "bg-gray-50 font-bold" : ""}>
                  <td className="px-3 py-1">{label}</td>
                  {allPlans.map((p) => {
                    const v = (p.data[key] as number | undefined) ?? 0;
                    return (
                      <td key={p.key} className="px-3 py-1 text-right">
                        {(v / 10000).toFixed(1)}万
                      </td>
                    );
                  })}
                  {allPlans
                    .filter((p) => p.key !== "baseline")
                    .map((p) => {
                      const v = (p.data[key] as number | undefined) ?? 0;
                      const save = blVal - v;
                      return (
                        <td key={`${p.key}-save`} className="px-3 py-1 text-right text-green-700">
                          {save > 0 ? `-${(save / 10000).toFixed(1)}万` : "—"}
                        </td>
                      );
                    })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* 调参日志（如有） */}
      {comparison.tuning_log && Object.keys(comparison.tuning_log).length > 0 && (
        <details className="mb-4">
          <summary className="text-xs text-gray-500 cursor-pointer">查看节能率对齐过程</summary>
          <div className="mt-2 text-xs space-y-2">
            {Object.entries(comparison.tuning_log).map(([planId, logs]) => (
              <div key={planId} className="bg-gray-50 border rounded p-2">
                <div className="font-medium">方案 {planId}</div>
                <ul className="ml-4 list-disc text-gray-600">
                  {(logs as { iter: number; actual_pct: number; delta: number }[]).map((log, i) => (
                    <li key={i}>
                      第 {log.iter} 轮：仿真 {log.actual_pct.toFixed(2)}%，偏差{" "}
                      {(log.delta * 100).toFixed(2)}%
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </details>
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
  return md
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n\n/g, "</p><p>")
    .replace(/^/, "<p>")
    .replace(/$/, "</p>");
}
