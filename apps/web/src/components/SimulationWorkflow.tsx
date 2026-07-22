"use client";

import { useState, useEffect, useCallback } from "react";
import {
  initSimSession,
  fetchSimState,
  subscribeExtractStream,
  type SimState,
  type StreamEvent,
} from "@/lib/api";
import { TopologyStage } from "./sim/TopologyStage";
import { CopCurvesStage } from "./sim/CopCurvesStage";
import { OperatingStage } from "./sim/OperatingStage";
import { SimulateStage } from "./sim/SimulateStage";

type SimStageKey = "topology" | "cop_curves" | "operating" | "simulate" | "done";

const STAGES: { key: SimStageKey; label: string }[] = [
  { key: "topology", label: "拓扑信息" },
  { key: "cop_curves", label: "性能曲线" },
  { key: "operating", label: "工况需求" },
  { key: "simulate", label: "仿真执行" },
];

const STAGE_ORDER: SimStageKey[] = ["topology", "cop_curves", "operating", "simulate", "done"];

export function SimulationWorkflow() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [simState, setSimState] = useState<SimState | null>(null);
  const [aiLogs, setAiLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [simMode, setSimMode] = useState<"new_station" | "old_station">("new_station");

  // 初始化 session
  const handleInit = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await initSimSession(simMode);
      setSessionId(res.session_id);
      const state = await fetchSimState(res.session_id);
      setSimState(state);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [simMode]);

  // 刷新状态
  const refreshState = useCallback(async () => {
    if (!sessionId) return;
    try {
      const state = await fetchSimState(sessionId);
      setSimState(state);
    } catch {
      // ignore
    }
  }, [sessionId]);

  // 监听 SSE 日志
  const subscribeStream = useCallback(
    (sid: string) => {
      setAiLogs([]);
      const unsub = subscribeExtractStream(sid, (ev: StreamEvent) => {
        if (ev.type === "log" && ev.message) {
          setAiLogs((prev) => [...prev, `[${ev.timestamp}] ${ev.message}`]);
        }
        if (ev.type === "done" || ev.type === "error") {
          // 完成后刷新状态
          setTimeout(() => refreshState(), 500);
        }
      });
      return unsub;
    },
    [refreshState]
  );

  // 轮询状态（当 is_running 为 true 时）
  useEffect(() => {
    if (!simState?.is_running || !sessionId) return;
    const unsub = subscribeStream(sessionId);
    const interval = setInterval(refreshState, 3000);
    return () => {
      unsub();
      clearInterval(interval);
    };
  }, [simState?.is_running, sessionId, subscribeStream, refreshState]);

  // 初始状态：选择模式
  if (!sessionId) {
    return (
      <div className="max-w-2xl mx-auto p-8">
        <h2 className="text-xl font-bold mb-4">冷站性能仿真</h2>
        <p className="text-sm text-gray-600 mb-6">
          选择仿真模式后开始，系统将引导你完成拓扑收集 → 性能曲线 → 工况需求 → 仿真执行四步流程。
        </p>
        <div className="flex gap-4 mb-4">
          <label className="flex items-center gap-2">
            <input
              type="radio"
              checked={simMode === "new_station"}
              onChange={() => setSimMode("new_station")}
            />
            新站房仿真
          </label>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              checked={simMode === "old_station"}
              onChange={() => setSimMode("old_station")}
            />
            旧站房仿真（基准+优化对比）
          </label>
        </div>
        {error && <div className="text-red-600 text-sm mb-4">{error}</div>}
        <button
          onClick={handleInit}
          disabled={loading}
          className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
        >
          {loading ? "初始化中..." : "开始仿真"}
        </button>
      </div>
    );
  }

  const currentStage = simState?.sim_stage ?? "topology";
  const currentIdx = STAGE_ORDER.indexOf(currentStage as SimStageKey);

  return (
    <div className="max-w-4xl mx-auto p-6">
      {/* 进度指示器 */}
      <div className="flex items-center gap-2 mb-8">
        {STAGES.map((s, i) => (
          <div key={s.key} className="flex items-center gap-2">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                i < currentIdx
                  ? "bg-green-500 text-white"
                  : i === currentIdx
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-200 text-gray-500"
              }`}
            >
              {i < currentIdx ? "✓" : i + 1}
            </div>
            <span className={`text-sm ${i === currentIdx ? "font-bold" : "text-gray-500"}`}>
              {s.label}
            </span>
            {i < STAGES.length - 1 && <span className="text-gray-300 mx-1">→</span>}
          </div>
        ))}
      </div>

      {/* AI 日志面板 */}
      {aiLogs.length > 0 && (
        <div className="mb-6 bg-gray-900 text-green-400 rounded-lg p-4 max-h-48 overflow-y-auto font-mono text-xs">
          {aiLogs.map((log, i) => (
            <div key={i}>{log}</div>
          ))}
        </div>
      )}

      {/* 阶段内容 */}
      {currentStage === "topology" && (
        <TopologyStage
          sessionId={sessionId}
          simState={simState!}
          onTopologyUpdated={refreshState}
        />
      )}
      {currentStage === "cop_curves" && (
        <CopCurvesStage
          sessionId={sessionId}
          simState={simState!}
          onCopUpdated={refreshState}
        />
      )}
      {currentStage === "operating" && (
        <OperatingStage
          sessionId={sessionId}
          simState={simState!}
          onOperatingUpdated={refreshState}
        />
      )}
      {(currentStage === "simulate" || currentStage === "done") && (
        <SimulateStage
          sessionId={sessionId}
          simState={simState!}
          onSimComplete={refreshState}
        />
      )}
    </div>
  );
}
