"use client";

import { useState, useRef } from "react";
import {
  extractTopology,
  parseTopology,
  saveTopology,
  type SimState,
  type SimTopology,
} from "@/lib/api";

interface Props {
  sessionId: string;
  simState: SimState;
  onTopologyUpdated: () => void;
}

const TOPOLOGY_EXAMPLE = `冷水主机：
- 约克 YZ系列 3000RT 中温变频离心机 × 2台，额定制冷量10551kW，额定功率750kW，额定COP 6.5
- 约克 YZ系列 1800RT 低温变频离心机 × 1台，额定制冷量6331kW，额定功率480kW，额定COP 5.8

冷却泵：90kW × 4台，变频
冷冻泵：75kW × 3台 + 37kW × 2台，变频
冷却塔：45kW风机 × 12台，变频，闭式
特殊结构：无`;

export function TopologyStage({ sessionId, simState, onTopologyUpdated }: Props) {
  const [textInput, setTextInput] = useState("");
  const [projectName, setProjectName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inputMode, setInputMode] = useState<"upload" | "text">("upload");
  const fileRef = useRef<HTMLInputElement>(null);

  const topology = simState.sim_topology;

  // 已有关联拓扑：展示编辑界面
  if (topology) {
    return (
      <TopologyEditor
        sessionId={sessionId}
        topology={topology}
        onSaved={onTopologyUpdated}
      />
    );
  }

  const handleUploadExtract = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      await extractTopology(sessionId, file);
      onTopologyUpdated();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleTextParse = async () => {
    if (!textInput.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await parseTopology(sessionId, textInput, projectName);
      onTopologyUpdated();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h3 className="text-lg font-bold mb-4">Step 1: 站房拓扑信息收集</h3>

      <div className="flex gap-4 mb-4">
        <button
          className={`px-4 py-2 rounded ${inputMode === "upload" ? "bg-indigo-600 text-white" : "bg-gray-200"}`}
          onClick={() => setInputMode("upload")}
        >
          上传调研表
        </button>
        <button
          className={`px-4 py-2 rounded ${inputMode === "text" ? "bg-indigo-600 text-white" : "bg-gray-200"}`}
          onClick={() => setInputMode("text")}
        >
          手动输入
        </button>
      </div>

      {inputMode === "upload" ? (
        <div>
          <p className="text-sm text-gray-600 mb-2">上传调研表 Excel，AI 将自动识别设备拓扑</p>
          <input ref={fileRef} type="file" accept=".xlsx,.xls" className="mb-4" />
          <button
            onClick={handleUploadExtract}
            disabled={loading}
            className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? "AI 识别中..." : "开始识别设备拓扑"}
          </button>
        </div>
      ) : (
        <div>
          <details className="mb-4">
            <summary className="text-sm text-indigo-600 cursor-pointer">查看填写示例</summary>
            <div className="bg-gray-100 p-3 rounded text-xs mt-2 whitespace-pre-wrap select-text">
              {TOPOLOGY_EXAMPLE}
            </div>
          </details>
          <button
            onClick={() => {
              setProjectName("XX工厂中央空调冷站");
              setTextInput(TOPOLOGY_EXAMPLE);
            }}
            className="mb-2 px-3 py-1 border border-indigo-400 text-indigo-600 rounded text-xs hover:bg-indigo-50"
          >
            一键填入示例
          </button>
          <input
            type="text"
            placeholder="项目名称"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            className="w-full border rounded px-3 py-2 mb-2"
          />
          <textarea
            placeholder="请输入设备拓扑信息..."
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            rows={10}
            className="w-full border rounded px-3 py-2 mb-4"
          />
          <button
            onClick={handleTextParse}
            disabled={loading || !textInput.trim()}
            className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? "AI 解析中..." : "AI 解析拓扑信息"}
          </button>
        </div>
      )}

      {error && <div className="text-red-600 text-sm mt-4">{error}</div>}
      {loading && <div className="text-sm text-gray-500 mt-4">AI 正在分析，请查看上方日志面板...</div>}
    </div>
  );
}

// ==================== 拓扑编辑器 ====================

function TopologyEditor({
  sessionId,
  topology,
  onSaved,
}: {
  sessionId: string;
  topology: SimTopology;
  onSaved: () => void;
}) {
  const [local, setLocal] = useState<SimTopology>(topology);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveTopology(sessionId, local);
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <h3 className="text-lg font-bold mb-4">拓扑信息（已识别）</h3>
      <input
        type="text"
        value={local.project_name}
        onChange={(e) => setLocal({ ...local, project_name: e.target.value })}
        className="w-full border rounded px-3 py-2 mb-4"
        placeholder="项目名称"
      />

      {/* 冷水主机 */}
      <h4 className="font-bold mb-2">冷水主机 ({local.chillers?.length ?? 0})</h4>
      {local.chillers?.map((ch, i) => (
        <div key={i} className="border rounded p-3 mb-2 grid grid-cols-4 gap-2 text-sm">
          <input value={ch.brand} onChange={(e) => updateChiller(i, "brand", e.target.value)} className="border rounded px-2 py-1" placeholder="品牌" />
          <input value={ch.model} onChange={(e) => updateChiller(i, "model", e.target.value)} className="border rounded px-2 py-1" placeholder="型号" />
          <input type="number" value={ch.capacity_kw} onChange={(e) => updateChiller(i, "capacity_kw", +e.target.value)} className="border rounded px-2 py-1" placeholder="制冷量kW" />
          <input type="number" value={ch.power_kw} onChange={(e) => updateChiller(i, "power_kw", +e.target.value)} className="border rounded px-2 py-1" placeholder="功率kW" />
          <input type="number" step="0.01" value={ch.rated_cop} onChange={(e) => updateChiller(i, "rated_cop", +e.target.value)} className="border rounded px-2 py-1" placeholder="COP" />
          <input type="number" value={ch.count} onChange={(e) => updateChiller(i, "count", +e.target.value)} className="border rounded px-2 py-1" placeholder="台数" />
          <label className="flex items-center gap-1"><input type="checkbox" checked={ch.vfd} onChange={(e) => updateChiller(i, "vfd", e.target.checked)} />变频</label>
          <button onClick={() => removeChiller(i)} className="text-red-500 text-xs">删除</button>
        </div>
      ))}
      <button onClick={addChiller} className="text-sm text-indigo-600 mb-4">+ 添加冷水主机</button>

      {/* 冷却泵/冷冻泵/冷却塔简化展示 */}
      <div className="grid grid-cols-3 gap-4 mt-4 text-sm">
        <div>
          <h4 className="font-bold">冷却泵 ({local.cooling_pumps?.length ?? 0})</h4>
          {local.cooling_pumps?.map((p, i) => (
            <div key={i} className="text-xs text-gray-600">{p.brand} {p.model} {p.power_kw}kW ×{p.count}</div>
          ))}
        </div>
        <div>
          <h4 className="font-bold">冷冻泵 ({local.chilled_pumps?.length ?? 0})</h4>
          {local.chilled_pumps?.map((p, i) => (
            <div key={i} className="text-xs text-gray-600">{p.brand} {p.model} {p.power_kw}kW ×{p.count}</div>
          ))}
        </div>
        <div>
          <h4 className="font-bold">冷却塔 ({local.towers?.length ?? 0})</h4>
          {local.towers?.map((t, i) => (
            <div key={i} className="text-xs text-gray-600">{t.brand} {t.fan_power_kw}kW ×{t.count}</div>
          ))}
        </div>
      </div>

      {/* 特殊结构类型 */}
      <div className="mt-4">
        <h4 className="font-bold text-sm mb-2">特殊结构类型</h4>
        <select
          value={local.special?.type ?? "none"}
          onChange={(e) => setLocal({ ...local, special: { type: e.target.value } })}
          className="border rounded px-3 py-2 text-sm"
        >
          <option value="none">无</option>
          <option value="storage">水蓄冷</option>
          <option value="ice">冰蓄冷</option>
          <option value="heat_recovery">热回收</option>
          <option value="storage_and_heat_recovery">蓄冷+热回收</option>
        </select>
      </div>

      <div className="mt-6">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
        >
          {saving ? "保存中..." : "确认拓扑，进入下一步"}
        </button>
      </div>

      {/* 内部 helpers */}
      <EditHelpers
        local={local}
        setLocal={setLocal}
      />
    </div>
  );

  function updateChiller(idx: number, field: string, value: unknown) {
    const updated = [...(local.chillers || [])];
    updated[idx] = { ...updated[idx], [field]: value };
    setLocal({ ...local, chillers: updated });
  }

  function removeChiller(idx: number) {
    const updated = (local.chillers || []).filter((_, i) => i !== idx);
    setLocal({ ...local, chillers: updated });
  }

  function addChiller() {
    setLocal({
      ...local,
      chillers: [...(local.chillers || []), { brand: "", model: "", type: "", count: 1, capacity_kw: 0, power_kw: 0, rated_cop: 5.0, vfd: true }],
    });
  }
}

// 辅助组件：传递 setLocal 引用（解决闭包问题）
function EditHelpers({ local: _, setLocal: __ }: { local: SimTopology; setLocal: (v: SimTopology) => void }) {
  return null; // 仅作占位，实际逻辑在父组件内联函数中
}
