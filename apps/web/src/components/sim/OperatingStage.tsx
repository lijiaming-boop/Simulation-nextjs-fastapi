"use client";

import { useEffect, useState } from "react";
import {
  generateOperating,
  saveOperating,
  saveBaseline,
  saveSchemes,
  type SimState,
  type SimScheme,
} from "@/lib/api";

interface Props {
  sessionId: string;
  simState: SimState;
  onOperatingUpdated: () => void;
}

const OPERATING_EXAMPLE = `过渡季节(3-5月,10-11月)工作日开2台约克3000RT中温变频，75%负载
过渡季节休息日开1台约克1800RT低温变频，75%负载
冬季(12-2月)不开机
夏季(6-9月)工作日开3台3000RT中温变频，80%负载
夏季休息日开1台3000RT中温变频和1台1800RT低温变频，70%负载`;

const DEFAULT_SCHEMES: SimScheme[] = [
  {
    id: "A",
    name: "方案A",
    description: "不改造冷却泵（仅软件策略：冷冻泵温差控制+夏季减泵+冷却塔液位控制）",
    target_saving_rate_pct: 5.0,
    intervention_tags: ["chw_pump_delta_t", "summer_less_pump", "tower_level_cap"],
  },
  {
    id: "B",
    name: "方案B",
    description: "冷却泵全变频改造",
    target_saving_rate_pct: 7.0,
    intervention_tags: [
      "chw_pump_delta_t",
      "summer_less_pump",
      "tower_level_cap",
      "cw_pump_all_vfd",
    ],
  },
];

function nextSchemeId(schemes: SimScheme[]): string {
  const used = new Set(schemes.map((s) => s.id));
  for (let i = 0; i < 26; i++) {
    const c = String.fromCharCode(65 + i);
    if (!used.has(c)) return c;
  }
  return `S${schemes.length + 1}`;
}

export function OperatingStage({ sessionId, simState, onOperatingUpdated }: Props) {
  const [textInput, setTextInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isOldStation = simState.sim_mode === "old_station";
  const operating = simState.sim_operating_conditions;

  // === 基线耗电量 ===
  const [baselineWanKwh, setBaselineWanKwh] = useState<string>(
    simState.sim_baseline_power_kwh != null
      ? String(simState.sim_baseline_power_kwh / 10000)
      : ""
  );
  const [baselineSaving, setBaselineSaving] = useState(false);
  const [baselineMsg, setBaselineMsg] = useState<string | null>(null);

  // === 优化方案 ===
  const [schemes, setSchemes] = useState<SimScheme[]>(
    simState.sim_schemes && simState.sim_schemes.length > 0
      ? simState.sim_schemes
      : DEFAULT_SCHEMES
  );
  const [schemesSaving, setSchemesSaving] = useState(false);
  const [schemesMsg, setSchemesMsg] = useState<string | null>(null);

  // 同步来自后端的旧值
  useEffect(() => {
    if (simState.sim_baseline_power_kwh != null) {
      setBaselineWanKwh(String(simState.sim_baseline_power_kwh / 10000));
    }
  }, [simState.sim_baseline_power_kwh]);

  useEffect(() => {
    if (simState.sim_schemes && simState.sim_schemes.length > 0) {
      setSchemes(simState.sim_schemes);
    }
  }, [simState.sim_schemes]);

  const handleGenerate = async () => {
    if (!textInput.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await generateOperating(sessionId, textInput);
      onOperatingUpdated();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleBaselineSave = async () => {
    const v = parseFloat(baselineWanKwh);
    if (!v || v <= 0) {
      setBaselineMsg("基准耗电量必须 > 0");
      return;
    }
    setBaselineSaving(true);
    setBaselineMsg(null);
    try {
      await saveBaseline(sessionId, v * 10000);
      setBaselineMsg("已保存");
      onOperatingUpdated();
    } catch (e) {
      setBaselineMsg(String(e));
    } finally {
      setBaselineSaving(false);
    }
  };

  const handleSchemesSave = async () => {
    if (schemes.length === 0) {
      setSchemesMsg("至少需要一个优化方案");
      return;
    }
    setSchemesSaving(true);
    setSchemesMsg(null);
    try {
      await saveSchemes(sessionId, schemes);
      setSchemesMsg("已保存");
      onOperatingUpdated();
    } catch (e) {
      setSchemesMsg(String(e));
    } finally {
      setSchemesSaving(false);
    }
  };

  const updateScheme = (idx: number, patch: Partial<SimScheme>) => {
    setSchemes((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  };
  const addScheme = () => {
    const id = nextSchemeId(schemes);
    setSchemes((prev) => [
      ...prev,
      {
        id,
        name: `方案${id}`,
        description: "",
        target_saving_rate_pct: 5,
        intervention_tags: [],
      },
    ]);
  };
  const removeScheme = (idx: number) => {
    setSchemes((prev) => prev.filter((_, i) => i !== idx));
  };

  // ============ 未生成工况：显示文本输入 ============
  if (!operating) {
    return (
      <div>
        <h3 className="text-lg font-bold mb-4">Step 3: 工况需求收集</h3>
        <p className="text-sm text-gray-600 mb-4">
          请描述各季节的运行模式（哪些月份开哪些主机、负载率等），AI 将生成月度运行组合。
        </p>

        <details className="mb-4">
          <summary className="text-sm text-indigo-600 cursor-pointer">查看填写示例</summary>
          <pre className="bg-gray-100 p-3 rounded text-xs mt-2 whitespace-pre-wrap">
            {OPERATING_EXAMPLE}
          </pre>
        </details>

        <textarea
          placeholder="请描述各季节运行模式..."
          value={textInput}
          onChange={(e) => setTextInput(e.target.value)}
          rows={8}
          className="w-full border rounded px-3 py-2 mb-4"
        />

        <button
          onClick={handleGenerate}
          disabled={loading || !textInput.trim()}
          className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
        >
          {loading ? "AI 生成中..." : "AI 生成工况需求"}
        </button>

        {error && <div className="text-red-600 text-sm mt-4">{error}</div>}
        {loading && <div className="text-sm text-gray-500 mt-4">AI 正在分析运行模式...</div>}
      </div>
    );
  }

  // ============ 已生成工况：显示摘要 + old_station 专属基线/方案 ============
  return (
    <div>
      <h3 className="text-lg font-bold mb-4">Step 3: 工况需求（已生成）</h3>

      <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
        <p className="text-green-700 text-sm">工况数据已生成</p>
        {operating.monthly_table && (
          <div className="mt-2 text-xs text-gray-600">
            {operating.monthly_table.length} 条月度运行记录
          </div>
        )}
      </div>

      <details className="mb-4">
        <summary className="text-sm text-indigo-600 cursor-pointer">查看工况数据</summary>
        <pre className="bg-gray-100 p-3 rounded text-xs mt-2 overflow-auto max-h-64">
          {JSON.stringify(operating, null, 2)}
        </pre>
      </details>

      {/* ========== old_station 专属：基准耗电量 + 优化方案 ========== */}
      {isOldStation && (
        <div className="space-y-6 border-t border-indigo-200 pt-6 mt-4">
          {/* --- 基准耗电量 --- */}
          <section>
            <h4 className="font-bold text-sm mb-2 text-indigo-900">
              基准工况年耗电量
              <span className="text-xs text-gray-500 font-normal ml-2">
                （用户提供的实际年度电费基准，仿真将严格对齐）
              </span>
            </h4>
            <div className="flex items-center gap-3">
              <input
                type="number"
                step="0.01"
                min="0"
                placeholder="如：1127.71"
                value={baselineWanKwh}
                onChange={(e) => setBaselineWanKwh(e.target.value)}
                className="border rounded px-3 py-2 w-48 text-sm"
              />
              <span className="text-sm text-gray-600">万 kWh / 年</span>
              <button
                onClick={handleBaselineSave}
                disabled={baselineSaving}
                className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 text-sm"
              >
                {baselineSaving ? "保存中..." : "保存"}
              </button>
            </div>
            {baselineMsg && (
              <div
                className={`text-xs mt-2 ${
                  baselineMsg === "已保存" ? "text-green-600" : "text-red-600"
                }`}
              >
                {baselineMsg}
              </div>
            )}
          </section>

          {/* --- 优化方案表格 --- */}
          <section>
            <h4 className="font-bold text-sm mb-2 text-indigo-900">
              优化方案定义
              <span className="text-xs text-gray-500 font-normal ml-2">
                （每个方案仿真后将严格对齐期望节能率）
              </span>
            </h4>

            <div className="overflow-x-auto border rounded">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-2 py-2 text-left w-12">ID</th>
                    <th className="px-2 py-2 text-left w-32">方案名称</th>
                    <th className="px-2 py-2 text-left">改造措施描述</th>
                    <th className="px-2 py-2 text-left w-28">期望节能率(%)</th>
                    <th className="px-2 py-2 text-left w-12"></th>
                  </tr>
                </thead>
                <tbody>
                  {schemes.map((s, idx) => (
                    <tr key={idx} className="border-t">
                      <td className="px-2 py-1 font-mono text-indigo-700">{s.id}</td>
                      <td className="px-2 py-1">
                        <input
                          type="text"
                          value={s.name}
                          onChange={(e) => updateScheme(idx, { name: e.target.value })}
                          className="w-full border rounded px-2 py-1 text-xs"
                        />
                      </td>
                      <td className="px-2 py-1">
                        <textarea
                          value={s.description}
                          onChange={(e) =>
                            updateScheme(idx, { description: e.target.value })
                          }
                          rows={2}
                          className="w-full border rounded px-2 py-1 text-xs"
                        />
                      </td>
                      <td className="px-2 py-1">
                        <input
                          type="number"
                          step="0.1"
                          min="0.1"
                          max="99"
                          value={s.target_saving_rate_pct}
                          onChange={(e) =>
                            updateScheme(idx, {
                              target_saving_rate_pct: parseFloat(e.target.value) || 0,
                            })
                          }
                          className="w-full border rounded px-2 py-1 text-xs"
                        />
                      </td>
                      <td className="px-2 py-1 text-center">
                        <button
                          onClick={() => removeScheme(idx)}
                          disabled={schemes.length <= 1}
                          className="text-red-500 hover:text-red-700 disabled:opacity-30 text-xs"
                        >
                          删除
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center gap-3 mt-3">
              <button
                onClick={addScheme}
                className="px-3 py-1 border border-indigo-400 text-indigo-600 rounded text-xs hover:bg-indigo-50"
              >
                + 添加方案
              </button>
              <button
                onClick={handleSchemesSave}
                disabled={schemesSaving || schemes.length === 0}
                className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 text-sm"
              >
                {schemesSaving ? "保存中..." : "保存方案列表"}
              </button>
            </div>
            {schemesMsg && (
              <div
                className={`text-xs mt-2 ${
                  schemesMsg === "已保存" ? "text-green-600" : "text-red-600"
                }`}
              >
                {schemesMsg}
              </div>
            )}
          </section>
        </div>
      )}

      <button className="mt-6 px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">
        确认工况，进入仿真执行
      </button>
    </div>
  );
}
