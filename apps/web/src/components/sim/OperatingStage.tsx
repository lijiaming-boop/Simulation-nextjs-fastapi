"use client";

import { useState } from "react";
import { generateOperating, saveOperating, type SimState } from "@/lib/api";

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

export function OperatingStage({ sessionId, simState, onOperatingUpdated }: Props) {
  const [textInput, setTextInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const operating = simState.sim_operating_conditions;

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

  // 已有工况数据：展示摘要 + 确认按钮
  if (operating) {
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
        <button className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">
          确认工况，进入仿真执行
        </button>
      </div>
    );
  }

  return (
    <div>
      <h3 className="text-lg font-bold mb-4">Step 3: 工况需求收集</h3>
      <p className="text-sm text-gray-600 mb-4">
        请描述各季节的运行模式（哪些月份开哪些主机、负载率等），AI 将生成月度运行组合。
      </p>

      <details className="mb-4">
        <summary className="text-sm text-indigo-600 cursor-pointer">查看填写示例</summary>
        <pre className="bg-gray-100 p-3 rounded text-xs mt-2 whitespace-pre-wrap">{OPERATING_EXAMPLE}</pre>
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
