"use client";

import { useState } from "react";
import Workflow from "@/components/Workflow";
import { SimulationWorkflow } from "@/components/SimulationWorkflow";

type Module = "home" | "ac" | "simulation";

export default function Home() {
  const [module, setModule] = useState<Module>("home");

  if (module === "ac") {
    return (
      <div>
        <nav className="px-4 py-2 bg-white border-b">
          <button onClick={() => setModule("home")} className="text-sm text-indigo-600 hover:underline">
            ← 返回首页
          </button>
        </nav>
        <Workflow />
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
        <SimulationWorkflow />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto pt-16 px-6">
        <h1 className="text-3xl font-bold text-center mb-2">暖通节能率智能测算工具</h1>
        <p className="text-center text-gray-500 mb-12">基于 AI 的智能节能评估系统</p>

        <div className="grid grid-cols-3 gap-6">
          {/* 空调/空压 */}
          <div
            className="border rounded-xl p-6 bg-white hover:shadow-lg cursor-pointer transition-shadow"
            onClick={() => setModule("ac")}
          >
            <div className="text-3xl mb-3">❄️</div>
            <h2 className="font-bold text-lg mb-2">空调 / 空压节能率计算</h2>
            <p className="text-sm text-gray-500">
              上传调研表，AI 自动提取数据、计算节能率
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

          {/* 占位 */}
          <div className="border rounded-xl p-6 bg-gray-100 opacity-50">
            <div className="text-3xl mb-3">📊</div>
            <h2 className="font-bold text-lg mb-2">更多功能</h2>
            <p className="text-sm text-gray-400">即将推出...</p>
          </div>
        </div>
      </div>
    </div>
  );
}
