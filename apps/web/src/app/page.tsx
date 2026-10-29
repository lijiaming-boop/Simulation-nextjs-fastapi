"use client";

import { useState } from "react";
import Workflow from "@/components/Workflow";
import { SimulationWorkflow } from "@/components/SimulationWorkflow";
import { QuoteWorkflow } from "@/components/QuoteWorkflow";

type Module = "home" | "ac" | "compressor" | "simulation" | "quote";

export default function Home() {
  const [module, setModule] = useState<Module>("home");
  const [simSavingRate, setSimSavingRate] = useState<number | undefined>(undefined);
  const [simSourceSessionId, setSimSourceSessionId] = useState<string | undefined>(undefined);

  if (module === "ac" || module === "compressor") {
    const title = module === "ac" ? "空调节能率计算" : "空压机节能率计算";
    const moduleType = module === "ac" ? "air_conditioner" : "air_compressor";
    return (
      <div>
        <nav className="px-4 py-2 bg-white border-b">
          <button onClick={() => setModule("home")} className="text-sm text-indigo-600 hover:underline">
            ← 返回首页
          </button>
        </nav>
        <Workflow
          moduleType={moduleType}
          title={title}
          onEnterSimulation={module === "ac" ? (rate, srcId) => {
            setSimSavingRate(rate);
            setSimSourceSessionId(srcId);
            setModule("simulation");
          } : undefined}
        />
      </div>
    );
  }

  if (module === "simulation") {
    return (
      <div>
        <nav className="px-4 py-2 bg-white border-b">
          <button onClick={() => setModule("home")} className="text-sm text-indigo-600 hover:underline">
            ← 返回首页
          </button>
        </nav>
        <SimulationWorkflow
          initialMode={simSavingRate != null ? "old_station" : undefined}
          initialSavingRate={simSavingRate}
          sourceSessionId={simSourceSessionId}
          onClearInitial={() => { setSimSavingRate(undefined); setSimSourceSessionId(undefined); }}
        />
      </div>
    );
  }

  if (module === "quote") {
    return (
      <div>
        <nav className="px-4 py-2 bg-white border-b">
          <button onClick={() => setModule("home")} className="text-sm text-indigo-600 hover:underline">
            ← 返回首页
          </button>
        </nav>
        <QuoteWorkflow />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto pt-16 px-6">
        <h1 className="text-3xl font-bold text-center mb-2">暖通节能率智能测算工具</h1>
        <p className="text-center text-gray-500 mb-12">基于 AI 的智能节能评估系统</p>

        <div className="grid grid-cols-4 gap-6">
          {/* 空调 */}
          <div
            className="border rounded-xl p-6 bg-white hover:shadow-lg cursor-pointer transition-shadow"
            onClick={() => setModule("ac")}
          >
            <div className="text-3xl mb-3">❄️</div>
            <h2 className="font-bold text-lg mb-2">空调节能率计算</h2>
            <p className="text-sm text-gray-500">
              上传空调调研表，AI 提取数据、质量检查、节能测算
            </p>
          </div>

          {/* 空压机 */}
          <div
            className="border rounded-xl p-6 bg-white hover:shadow-lg cursor-pointer transition-shadow"
            onClick={() => setModule("compressor")}
          >
            <div className="text-3xl mb-3">🔧</div>
            <h2 className="font-bold text-lg mb-2">空压机节能率计算</h2>
            <p className="text-sm text-gray-500">
              上传空压机调研表，AI 提取数据、计算节能率
            </p>
          </div>

          {/* 仿真 */}
          <div
            className="border rounded-xl p-6 bg-white hover:shadow-lg cursor-pointer transition-shadow"
            onClick={() => setModule("simulation")}
          >
            <div className="text-3xl mb-3">🔬</div>
            <h2 className="font-bold text-lg mb-2">冷站性能仿真</h2>
            <p className="text-sm text-gray-500">
              输入设备拓扑，全年 8760h 仿真分析，输出优化控制策略报告
            </p>
          </div>

          {/* 报价 */}
          <div
            className="border rounded-xl p-6 bg-white hover:shadow-lg cursor-pointer transition-shadow"
            onClick={() => setModule("quote")}
          >
            <div className="text-3xl mb-3">💰</div>
            <h2 className="font-bold text-lg mb-2">智能生成报价表</h2>
            <p className="text-sm text-gray-500">
              上传调研表，AI 识别、计算报价、生成报价表和方案文档
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
