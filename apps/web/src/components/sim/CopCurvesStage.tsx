"use client";

import { useState, useRef } from "react";
import { parseCopCurve, useDefaultCop, setSimStage, type SimState } from "@/lib/api";

interface Props {
  sessionId: string;
  simState: SimState;
  onCopUpdated: () => void;
}

export function CopCurvesStage({ sessionId, simState, onCopUpdated }: Props) {
  const topology = simState.sim_topology;
  const copData = simState.sim_cop_data ?? {};
  const [loading, setLoading] = useState<Record<number, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [advancing, setAdvancing] = useState(false);
  const fileRefs = useRef<(HTMLInputElement | null)[]>([]);

  if (!topology?.chillers?.length) {
    return <div className="text-red-600">未识别到冷水主机，请返回上一步检查</div>;
  }

  const allHaveCop = topology.chillers.every((ch) => {
    const key = `${ch.brand} ${ch.model} (${ch.type})`;
    return !!copData[key];
  });

  const handleUploadCop = async (idx: number) => {
    const file = fileRefs.current[idx]?.files?.[0];
    if (!file) return;
    const ch = topology.chillers[idx];
    const modelName = `${ch.brand} ${ch.model} (${ch.type})`;
    setLoading((prev) => ({ ...prev, [idx]: true }));
    setError(null);
    try {
      await parseCopCurve(sessionId, idx, modelName, ch.rated_cop, file);
      onCopUpdated();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading((prev) => ({ ...prev, [idx]: false }));
    }
  };

  const handleSkip = async (idx: number) => {
    const ch = topology.chillers[idx];
    const modelName = `${ch.brand} ${ch.model} (${ch.type})`;
    try {
      await useDefaultCop(sessionId, idx, modelName, ch.rated_cop);
      onCopUpdated();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div>
      <h3 className="text-lg font-bold mb-4">Step 2: 设备性能曲线收集</h3>
      <p className="text-sm text-gray-600 mb-6">
        请为每种型号主机上传 COP 性能曲线图片，或选择使用默认曲线跳过。
      </p>

      {topology.chillers.map((ch, idx) => {
        const modelName = `${ch.brand} ${ch.model} (${ch.type})`;
        const hasData = !!copData[modelName];
        const copInfo = copData[modelName];

        return (
          <div key={idx} className="border rounded-lg p-4 mb-4">
            <h4 className="font-bold mb-2">
              {ch.brand} {ch.model} ({ch.type}) × {ch.count} 台 | 额定COP: {ch.rated_cop}
            </h4>

            {hasData ? (
              <div>
                <span className="text-green-600 text-sm">
                  COP 数据已收集
                  {copInfo?._source === "skip_default" && " (使用默认曲线)"}
                  {copInfo?._source === "auto_fallback" && " (图片识别失败，使用默认)"}
                </span>
                {copInfo?.cw_temps && copInfo?.load_ratios && (
                  <span className="text-xs text-gray-500 ml-2">
                    ({copInfo.cw_temps.length} 温度点 × {copInfo.load_ratios.length} 负荷点)
                  </span>
                )}
              </div>
            ) : (
              <div className="flex gap-4 items-center">
                <div>
                  <input
                    ref={(el) => { fileRefs.current[idx] = el; }}
                    type="file"
                    accept=".png,.jpg,.jpeg"
                    className="text-sm"
                  />
                  <button
                    onClick={() => handleUploadCop(idx)}
                    disabled={loading[idx]}
                    className="mt-2 px-4 py-1 bg-indigo-600 text-white rounded text-sm disabled:opacity-50"
                  >
                    {loading[idx] ? "识别中..." : "AI 识别 COP"}
                  </button>
                </div>
                <span className="text-gray-400">或</span>
                <button
                  onClick={() => handleSkip(idx)}
                  className="px-4 py-1 border border-gray-300 rounded text-sm hover:bg-gray-50"
                >
                  使用默认曲线（跳过）
                </button>
              </div>
            )}
          </div>
        );
      })}

      {error && <div className="text-red-600 text-sm mt-4">{error}</div>}

      <div className="mt-6">
        <button
          disabled={!allHaveCop || advancing}
          onClick={async () => {
            setAdvancing(true);
            try {
              await setSimStage(sessionId, "operating");
              onCopUpdated();
            } catch (e) {
              setError(String(e));
            } finally {
              setAdvancing(false);
            }
          }}
          className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {advancing ? "跳转中..." : allHaveCop ? "确认，进入工况收集" : "请为所有主机提供 COP 数据"}
        </button>
      </div>
    </div>
  );
}
