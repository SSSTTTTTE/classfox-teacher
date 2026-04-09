/**
 * API 服务模块（教师版）
 * ======================
 * 封装所有与 FastAPI 后端的 HTTP 通信
 */

const API_BASE = "http://127.0.0.1:8765/api";

export interface StartMonitorPayload {
  subject?: string;
  course_name: string;
  material_filename?: string | null;
}

export interface LocalLLMStatus {
  status: string;
  online: boolean;
  base_url: string;
  chat_model: string;
  final_summary_model: string;
  realtime_summary_enabled: boolean;
  realtime_summary_model: string;
  available_models: string[];
  missing_models: string[];
  chat_model_available: boolean;
  final_summary_model_available: boolean;
  realtime_summary_model_available: boolean;
  is_warmed: boolean;
  warmed_models: string[];
  warmup_state: string;
  last_error: string;
  last_checked_at: string;
  last_warmed_at: string;
  version?: string;
  warmup?: {
    status: string;
    models: Array<{ ok: boolean; model: string; response: string }>;
  };
}

export interface ContextStatus {
  char_count: number;
  char_limit: number;
  usage_ratio: number;
  reset_recommended: boolean;
  recent_transcript_lines: number;
  recent_questions: number;
  recent_answers: number;
  confusion_points: number;
  topic_summary_chars: number;
  material_chars: number;
  limits: {
    max_recent_transcript_lines: number;
    max_recent_questions: number;
    max_recent_answers: number;
    max_confusion_points: number;
    max_topic_summary_chars: number;
    max_material_chars: number;
    max_text_chars: number;
  };
}

export interface StartMonitorResponse {
  status: string;
  message: string;
  local_llm?: LocalLLMStatus;
  init_steps?: Array<{
    step: string;
    ok: boolean;
    subject?: string;
    course_name?: string;
    chat_model?: string;
    online?: boolean;
    models?: string[];
  }>;
}

export interface StopMonitorResponse {
  status: string;
  message: string;
  summary?: {
    filename: string;
    course_name: string;
  };
  summary_error?: string;
}

export interface FinalSummaryStatus {
  active: boolean;
  phase: "idle" | "preparing" | "thinking" | "writing" | "saving" | "completed" | "failed";
  message: string;
  model: string;
  course_name: string;
  thinking_text: string;
  content_text: string;
  filename: string;
  error: string;
  started_at: string;
  finished_at: string;
}

export interface KnowledgeTreeNode {
  node_id: string;
  session_id: string;
  node_type: string;
  title: string;
  normalized_title: string;
  parent_id: string;
  aliases: string[];
  supporting_window_ids: string[];
  first_seen_at: string;
  last_updated_at: string;
  status: string;
}

export interface KnowledgeTreeEdge {
  edge_id: string;
  session_id: string;
  source_node_id: string;
  target_node_id: string;
  edge_type: string;
  supporting_window_ids: string[];
  created_at: string;
}

export interface KnowledgeTreePayload {
  session_id: string;
  current_main_topic: string;
  nodes: KnowledgeTreeNode[];
  edges: KnowledgeTreeEdge[];
  updated_at: string;
}

export interface KnowledgeTreeSummary {
  session_id: string;
  current_main_topic: string;
  total_nodes: number;
  total_edges: number;
  node_type_counts: Record<string, number>;
  recent_snapshots: string[];
  updated_at: string;
}

export interface TimelineSummaryResponse {
  status: string;
  total_questions: number;
  bookmarked_count: number;
  repeated_questions: number;
  linked_questions: number;
  pending_links: number;
  trajectory: string;
  status_counts: Record<string, number>;
  nodes: Array<{
    node_id: string;
    timestamp: string;
    student_question: string;
    one_sentence_answer: string;
    repeat_count: number;
    linked_topic_title?: string;
    question_status?: string;
  }>;
}

async function readApiError(res: Response, fallback: string) {
  try {
    const payload = await res.json();
    return payload.detail || payload.message || fallback;
  } catch {
    return fallback;
  }
}

/**
 * 开始课堂监听
 */
export async function startMonitor(
  payload: StartMonitorPayload
): Promise<StartMonitorResponse> {
  const res = await fetch(`${API_BASE}/start_monitor`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readApiError(res, "启动监听失败"));
  return res.json();
}

/**
 * 停止监听
 */
export async function stopMonitor(): Promise<StopMonitorResponse> {
  const res = await fetch(`${API_BASE}/stop_monitor`, { method: "POST" });
  if (!res.ok) throw new Error("停止监听失败");
  return res.json();
}

export async function pauseMonitor(): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_BASE}/pause_monitor`, { method: "POST" });
  if (!res.ok) throw new Error("暂停监听失败");
  return res.json();
}

export async function resumeMonitor(): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_BASE}/resume_monitor`, { method: "POST" });
  if (!res.ok) throw new Error("继续监听失败");
  return res.json();
}

export async function getFinalSummaryStatus(): Promise<FinalSummaryStatus> {
  const res = await fetch(`${API_BASE}/monitor/final_summary_status`);
  if (!res.ok) throw new Error(await readApiError(res, "读取课后总结状态失败"));
  const payload = await res.json();
  return payload.summary;
}

/**
 * 获取学生提问的兜底答案
 */
export type FallbackAnswerResponse = {
  status: string;
  student_question: string;
  one_line_answer: string;
  teacher_speakable_answer: string;
  short_explanation: string;
  confidence: string;
  answer_mode?: string;
  question_type?: string;
  used_subject?: string;
  question_id?: string;
  answer_id?: string;
  trigger_time?: string;
  one_sentence_answer?: string;
  detail?: string;
};

export async function getFallbackAnswer(
  detectedQuestion?: string,
  detectedTimestamp?: string,
  signal?: AbortSignal
): Promise<FallbackAnswerResponse> {
  const res = await fetch(`${API_BASE}/question/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      detected_question: detectedQuestion ?? null,
      detected_timestamp: detectedTimestamp ?? null,
    }),
    signal,
  });
  if (!res.ok) throw new Error("获取兜底答案失败");
  return res.json();
}

export async function confirmValidQuestion(payload: {
  question_id: string;
  answer_id: string;
  confirmed_by_teacher_action?: boolean;
}): Promise<{
  status: string;
  question_id: string;
  answer_id: string;
  question_status: string;
  linked_topic_id: string;
  linked_topic_title: string;
  confirmed_at: string;
  knowledge_tree_snapshot: KnowledgeTreePayload;
}> {
  const res = await fetch(`${API_BASE}/question/confirm_valid`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readApiError(res, "确认有效问题失败"));
  return res.json();
}

export async function questionFollowup(payload: {
  student_question: string;
  teacher_speakable_answer: string;
  followup: string;
  history: Array<{ role: string; content: string }>;
}): Promise<{
  status: string;
  answer: string;
}> {
  const res = await fetch(`${API_BASE}/question/followup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("追问失败");
  return res.json();
}

/**
 * 获取课堂状态摘要
 */
export async function getClassStatus(): Promise<{
  status: string;
  summary: string;
}> {
  const res = await fetch(`${API_BASE}/status/summary`, { method: "POST" });
  if (!res.ok) throw new Error("获取课堂状态失败");
  return res.json();
}

export async function statusChat(payload: {
  summary: string;
  question: string;
  history: Array<{ role: string; content: string }>;
}): Promise<{
  status: string;
  answer: string;
}> {
  const res = await fetch(`${API_BASE}/status/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("课堂状态追问失败");
  return res.json();
}

/**
 * 生成课后总结
 */
export async function generateSummary(): Promise<{
  status: string;
  filename: string;
  summary: string;
}> {
  const res = await fetch(`${API_BASE}/generate_summary`, { method: "POST" });
  if (!res.ok) throw new Error("生成总结失败");
  return res.json();
}

/**
 * 获取参考资料列表
 */
export async function getMaterials(): Promise<{
  status: string;
  items: Array<{ filename: string; updated_at: string; size: number }>;
}> {
  const res = await fetch(`${API_BASE}/materials`);
  if (!res.ok) throw new Error("获取资料列表失败");
  return res.json();
}

/**
 * 时间轴相关 API
 */
export async function addTimelineNode(payload: {
  timestamp: string;
  text: string;
  student_question: string;
  one_sentence_answer: string;
}): Promise<{ status: string; node_id?: string; repeat_count?: number }> {
  const res = await fetch(`${API_BASE}/timeline/add`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("添加时间轴节点失败");
  return res.json();
}

export async function markTimelineExpanded(node_id: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/timeline/expanded`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_id }),
  });
  if (!res.ok) throw new Error("标记展开失败");
  return res.json();
}

export async function getTimeline(bookmarkedOnly = false): Promise<{
  status: string;
  total: number;
  nodes: Array<{
    node_id: string;
    timestamp: string;
    student_question: string;
    one_sentence_answer: string;
    bookmarked: boolean;
    expanded: boolean;
    repeat_count: number;
    question_status?: string;
    linked_topic_title?: string;
  }>;
}> {
  const url = bookmarkedOnly ? `${API_BASE}/timeline?bookmarked_only=true` : `${API_BASE}/timeline`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("获取时间轴失败");
  return res.json();
}

export async function getTimelineSummary(): Promise<{
  status: string;
  total_questions: number;
  bookmarked_count: number;
  repeated_questions: number;
  linked_questions: number;
  pending_links: number;
  trajectory: string;
  status_counts: Record<string, number>;
  nodes: Array<{
    node_id: string;
    timestamp: string;
    student_question: string;
    one_sentence_answer: string;
    repeat_count: number;
    linked_topic_title?: string;
    question_status?: string;
  }>;
}> {
  const res = await fetch(`${API_BASE}/timeline/summary`);
  if (!res.ok) throw new Error("获取时间轴摘要失败");
  return res.json();
}

export async function getKnowledgeTree(): Promise<{
  status: string;
  knowledge_tree: KnowledgeTreePayload;
  summary: KnowledgeTreeSummary;
}> {
  const res = await fetch(`${API_BASE}/knowledge_tree/current`);
  if (!res.ok) throw new Error(await readApiError(res, "获取知识树失败"));
  return res.json();
}

export async function getKnowledgeTreeSnapshots(limit = 12): Promise<{
  status: string;
  snapshots: Array<{
    snapshot_id: string;
    filename: string;
    current_main_topic: string;
    total_nodes: number;
    total_edges: number;
    updated_at: string;
  }>;
}> {
  const res = await fetch(`${API_BASE}/knowledge_tree/snapshots?limit=${encodeURIComponent(String(limit))}`);
  if (!res.ok) throw new Error(await readApiError(res, "获取知识树快照失败"));
  return res.json();
}

export async function clearTimeline(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/timeline/clear`, { method: "POST" });
  if (!res.ok) throw new Error("清空时间轴失败");
  return res.json();
}

export async function getSettings(): Promise<{
  status: string;
  content: string;
  path: string;
}> {
  const res = await fetch(`${API_BASE}/settings`);
  if (!res.ok) throw new Error("读取设置失败");
  return res.json();
}

export async function saveSettings(content: string): Promise<{
  status: string;
  message: string;
}> {
  const res = await fetch(`${API_BASE}/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "保存设置失败");
  }
  return res.json();
}

export async function validateSeedAsr(payload: {
  app_key: string;
  access_key: string;
  resource_id: string;
  ws_url: string;
}): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_BASE}/settings/validate_seed_asr`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "验证失败");
  }
  return res.json();
}

export async function restartBackend(): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_BASE}/settings/restart_backend`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "重启失败");
  }
  return res.json();
}

export async function getLocalLLMHealth(): Promise<LocalLLMStatus> {
  const res = await fetch(`${API_BASE}/local_llm/health`);
  if (!res.ok) throw new Error(await readApiError(res, "本地模型健康检查失败"));
  return res.json();
}

export async function getLocalLLMStatus(): Promise<LocalLLMStatus> {
  const res = await fetch(`${API_BASE}/local_llm/status`);
  if (!res.ok) throw new Error(await readApiError(res, "读取本地模型状态失败"));
  return res.json();
}

export async function warmupLocalLLM(): Promise<LocalLLMStatus> {
  const res = await fetch(`${API_BASE}/local_llm/warmup`, { method: "POST" });
  if (!res.ok) throw new Error(await readApiError(res, "本地模型预热失败"));
  return res.json();
}

export async function getMonitorContextStatus(): Promise<{
  status: string;
  is_monitoring: boolean;
  is_paused: boolean;
  context: ContextStatus;
}> {
  const res = await fetch(`${API_BASE}/monitor/context_status`);
  if (!res.ok) throw new Error(await readApiError(res, "读取课堂上下文状态失败"));
  return res.json();
}

export async function resetMonitorContext(): Promise<{
  status: string;
  message: string;
  summary_kept: boolean;
  context: ContextStatus;
  warmup?: LocalLLMStatus | null;
  warmup_error?: string;
}> {
  const res = await fetch(`${API_BASE}/monitor/reset_context`, { method: "POST" });
  if (!res.ok) throw new Error(await readApiError(res, "重置课堂上下文失败"));
  return res.json();
}
