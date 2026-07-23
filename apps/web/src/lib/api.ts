/**
 * 前端 API 客户端：封装与 FastAPI 后端的通信
 *
 * 默认直连 FastAPI (http://127.0.0.1:8000)，避免 Next.js rewrites 对
 * multipart/form-data 大文件转发的兼容性问题。CORS 已允许 localhost:3000。
 * 生产环境可通过 NEXT_PUBLIC_API_BASE 环境变量切换。
 */

export const API_BASE =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE) ||
  "http://127.0.0.1:8000/api";

export interface UploadResponse {
  session_id: string;
  module_type: string;
  original_filename: string;
  saved_path: string;
  session_dir: string;
  created_at: string;
}

export interface SessionInfo {
  session_id: string;
  module_type: string;
  original_filename?: string;
  user_id?: string;
  stage: string;
  ai_logs_count: number;
  ai_logs: Array<{ timestamp: string; message: string; level?: string }>;
  created_at?: string;
}

export interface ExtractStartResponse {
  session_id: string;
  status: "extracting";
  module_type: string;
  input_file: string;
  output_json: string;
  stream_url: string;
}

export interface CalculateStartResponse {
  session_id: string;
  status: "calculating";
  module_type: string;
  stream_url: string;
}

export interface ResultResponse {
  session_id: string;
  stage: string;
  module_type: string;
  result?: {
    energy_saving_rate_range?: string;
    energy_saving_rate?: number;
    energy_saving_rate_min?: number;
    energy_saving_rate_max?: number;
    total_saving?: number;
    total_saving_min?: number;
    total_saving_max?: number;
    chiller_saving?: number;
    chiller_saving_min?: number;
    chiller_saving_max?: number;
    pump_saving?: number;
    pump_saving_min?: number;
    pump_saving_max?: number;
    tower_saving?: number;
    tower_saving_min?: number;
    tower_saving_max?: number;
    completeness?: number;
    filled_count?: number;
    calculation_method?: string;
    mock?: boolean;
    [key: string]: unknown;
  };
  formatted_result?: unknown;
  filling_suggestions?: unknown;
}

/** 上传调研表 */
export async function uploadSurvey(
  file: File,
  moduleType: "air_conditioner" | "air_compressor" = "air_conditioner"
): Promise<UploadResponse> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API_BASE}/upload?module_type=${moduleType}`, {
    method: "POST",
    body: fd,
  });
  if (!res.ok) {
    throw new Error(`上传失败: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

/** 触发数据提取（异步，立即返回） */
export async function startExtract(sessionId: string): Promise<ExtractStartResponse> {
  const res = await fetch(`${API_BASE}/extract/${sessionId}`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`启动提取失败: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

/** SSE 流式日志（EventSource） */
export interface StreamEvent {
  type: "log" | "done" | "error";
  timestamp?: string;
  message?: string;
}

export function subscribeExtractStream(
  sessionId: string,
  onEvent: (ev: StreamEvent) => void,
  signal?: AbortSignal
): () => void {
  const url = `${API_BASE}/extract/${sessionId}/stream`;
  const es = new EventSource(url);

  es.onmessage = (msg) => {
    try {
      const ev = JSON.parse(msg.data) as StreamEvent;
      onEvent(ev);
      if (ev.type === "done" || ev.type === "error") {
        es.close();
      }
    } catch {
      // ignore
    }
  };
  es.onerror = () => {
    // 连接断开，主动关闭
    es.close();
  };
  if (signal) {
    signal.addEventListener("abort", () => es.close());
  }
  return () => es.close();
}

/** 触发计算 */
export async function startCalculate(
  sessionId: string,
  extractedData?: Record<string, unknown>
): Promise<CalculateStartResponse> {
  const res = await fetch(`${API_BASE}/calculate/${sessionId}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ extracted_data: extractedData ?? null }),
  });
  if (!res.ok) {
    throw new Error(`启动计算失败: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

/** 轮询最终结果 */
export async function fetchResult(sessionId: string): Promise<ResultResponse | null> {
  const res = await fetch(`${API_BASE}/result/${sessionId}`);
  if (res.status === 404 || res.status === 409) return null;
  if (!res.ok) throw new Error(`获取结果失败: ${res.status}`);
  return res.json();
}

/** 查询 session 状态 */
export async function fetchSession(sessionId: string): Promise<SessionInfo> {
  const res = await fetch(`${API_BASE}/session/${sessionId}`);
  if (!res.ok) throw new Error(`查询 session 失败: ${res.status}`);
  return res.json();
}

// ==================== /suggest（规则 + LLM 增强） ====================

export interface SuggestStartResponse {
  session_id: string;
  status: "suggesting";
  use_llm: boolean;
  stream_url: string;
}

export interface SuggestResult {
  can_proceed: boolean;
  unfillable_fields?: unknown[];
  fillable_suggestions?: unknown[];
  llm_enhanced_tips?: string;
  [key: string]: unknown;
}

/** 触发填充建议（规则 + 可选 LLM 增强） */
export async function startSuggest(
  sessionId: string,
  useLlm: boolean = true
): Promise<SuggestStartResponse> {
  const res = await fetch(`${API_BASE}/suggest/${sessionId}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ use_llm: useLlm }),
  });
  if (!res.ok) {
    throw new Error(`启动建议失败: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

/** 获取填充建议 */
export async function fetchSuggest(
  sessionId: string
): Promise<SuggestResult | null> {
  const res = await fetch(`${API_BASE}/suggest/${sessionId}`);
  if (res.status === 404 || res.status === 409) return null;
  if (!res.ok) throw new Error(`获取建议失败: ${res.status}`);
  return res.json();
}

// ==================== /sim（仿真模块） ====================

export interface SimState {
  session_id: string;
  sim_stage: "topology" | "cop_curves" | "operating" | "simulate" | "done";
  sim_mode: "new_station" | "old_station";
  sim_topology: SimTopology | null;
  sim_cop_data: Record<string, SimCopData>;
  sim_operating_conditions: SimOperating | null;
  sim_result: SimResult | null;
  sim_project_name: string;
  is_running: boolean;
}

export interface SimTopology {
  project_name: string;
  chillers: SimChiller[];
  cooling_pumps: SimPump[];
  chilled_pumps: SimPump[];
  towers: SimTower[];
  special: { type: string };
}

export interface SimChiller {
  brand: string;
  model: string;
  type: string;
  count: number;
  capacity_kw: number;
  power_kw: number;
  rated_cop: number;
  vfd: boolean;
}

export interface SimPump {
  brand?: string;
  model?: string;
  power_kw: number;
  count: number;
  vfd: boolean;
  flow_rate_m3h?: number;
  head_m?: number;
}

export interface SimTower {
  brand?: string;
  model?: string;
  fan_power_kw: number;
  count: number;
  vfd: boolean;
  type?: string;
  flow_rate_m3h?: number;
}

export interface SimCopData {
  cw_temps?: number[];
  load_ratios?: number[];
  cop_table?: number[][];
  _source?: string;
}

export interface SimOperating {
  monthly_table?: Record<string, unknown>[];
  [key: string]: unknown;
}

export interface SimResult {
  success: boolean;
  output_dir: string;
  files: string[];
  report?: string;
  summary?: {
    annual_cop?: number;
    annual_power_mwh?: number;
    annual_cooling_mwh?: number;
    energy_saving_rate?: number;
    annual_saving_yuan?: number;
    [key: string]: unknown;
  };
}

/** 初始化仿真 session */
export async function initSimSession(
  simMode: "new_station" | "old_station" = "new_station"
): Promise<{ session_id: string; sim_mode: string; sim_stage: string }> {
  const res = await fetch(`${API_BASE}/sim/init`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ sim_mode: simMode }),
  });
  if (!res.ok) throw new Error(`初始化仿真失败: ${res.status} ${await res.text()}`);
  return res.json();
}

/** 获取仿真状态 */
export async function fetchSimState(sessionId: string): Promise<SimState> {
  const res = await fetch(`${API_BASE}/sim/state/${sessionId}`);
  if (!res.ok) throw new Error(`获取仿真状态失败: ${res.status}`);
  return res.json();
}

/** 上传调研表提取拓扑 */
export async function extractTopology(sessionId: string, file: File): Promise<{ status: string; stream_url: string }> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API_BASE}/sim/topology/extract/${sessionId}`, {
    method: "POST",
    body: fd,
  });
  if (!res.ok) throw new Error(`提取拓扑失败: ${res.status} ${await res.text()}`);
  return res.json();
}

/** 文本解析拓扑 */
export async function parseTopology(
  sessionId: string,
  text: string,
  projectName: string = ""
): Promise<{ status: string; stream_url: string }> {
  const res = await fetch(`${API_BASE}/sim/topology/parse/${sessionId}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text, project_name: projectName }),
  });
  if (!res.ok) throw new Error(`解析拓扑失败: ${res.status} ${await res.text()}`);
  return res.json();
}

/** 保存编辑后的拓扑 */
export async function saveTopology(sessionId: string, topology: SimTopology): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/sim/topology/${sessionId}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(topology),
  });
  if (!res.ok) throw new Error(`保存拓扑失败: ${res.status}`);
  return res.json();
}

/** 图片识别 COP 曲线 */
export async function parseCopCurve(
  sessionId: string,
  idx: number,
  model_name: string,
  rated_cop: number,
  file: File
): Promise<{ status: string; stream_url: string }> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(
    `${API_BASE}/sim/cop/parse/${sessionId}/${idx}?model_name=${encodeURIComponent(model_name)}&rated_cop=${rated_cop}`,
    { method: "POST", body: fd }
  );
  if (!res.ok) throw new Error(`识别 COP 失败: ${res.status} ${await res.text()}`);
  return res.json();
}

/** 使用默认 COP 曲线 */
export async function useDefaultCop(
  sessionId: string,
  idx: number,
  model_name: string,
  rated_cop: number
): Promise<{ status: string; cop_data: SimCopData }> {
  const res = await fetch(
    `${API_BASE}/sim/cop/default/${sessionId}/${idx}?model_name=${encodeURIComponent(model_name)}&rated_cop=${rated_cop}`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error(`设置默认 COP 失败: ${res.status}`);
  return res.json();
}

/** 生成工况 */
export async function generateOperating(
  sessionId: string,
  text: string
): Promise<{ status: string; stream_url: string }> {
  const res = await fetch(`${API_BASE}/sim/operating/generate/${sessionId}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`生成工况失败: ${res.status} ${await res.text()}`);
  return res.json();
}

/** 保存编辑后的工况 */
export async function saveOperating(sessionId: string, data: SimOperating): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/sim/operating/${sessionId}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`保存工况失败: ${res.status}`);
  return res.json();
}

/** 执行仿真 */
export async function executeSimulation(sessionId: string): Promise<{ status: string; stream_url: string }> {
  const res = await fetch(`${API_BASE}/sim/execute/${sessionId}`, { method: "POST" });
  if (!res.ok) throw new Error(`执行仿真失败: ${res.status} ${await res.text()}`);
  return res.json();
}

/** 获取仿真结果 */
export async function fetchSimResult(sessionId: string): Promise<SimResult | null> {
  const res = await fetch(`${API_BASE}/sim/result/${sessionId}`);
  if (res.status === 404 || res.status === 409) return null;
  if (!res.ok) throw new Error(`获取仿真结果失败: ${res.status}`);
  return res.json();
}

/** 构造计算结果 Excel 下载 URL
 *
 * - simplified_result.xlsx：简化版，直接下载
 * - calculation_result.xlsx：完整版，需传 password 校验
 */
export function resultDownloadUrl(
  sessionId: string,
  filename: string,
  password?: string
): string {
  const q = password ? `?password=${encodeURIComponent(password)}` : "";
  return `${API_BASE}/download/${sessionId}/${filename}${q}`;
}
