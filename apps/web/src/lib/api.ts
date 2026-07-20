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
    chiller_saving?: number;
    pump_saving?: number;
    tower_saving?: number;
    completeness?: number;
    filled_count?: number;
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
