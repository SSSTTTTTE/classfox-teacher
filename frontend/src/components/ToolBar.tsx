/**
 * 工具栏组件（教师版）
 * ====================
 * 包含「开始监听」「课堂状态」「上传资料」等核心操作
 */

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { RealtimeSummaryCard } from "../hooks/useWebSocket";
import type { ContextStatus, LocalLLMStatus } from "../services/api";
import { MAIN_WINDOW_SIZE } from "../services/windowSizing";

interface ToolBarProps {
  /** 是否正在监控 */
  isMonitoring: boolean;
  /** 是否暂停中 */
  isPaused: boolean;
  /** 是否正在加载中 */
  isLoading: boolean;
  /** 当前课程名 */
  courseName: string;
  /** 本地模型状态 */
  localLLMStatus?: LocalLLMStatus | null;
  /** 本地模型状态加载中 */
  localLLMLoading?: boolean;
  /** 本地模型状态错误 */
  localLLMError?: string | null;
  /** 课堂上下文状态 */
  contextStatus?: ContextStatus | null;
  /** 最近几条稳定转录文本 */
  recentTranscripts: string[];
  /** 当前正在识别中的 partial 文本 */
  partialTranscript?: string;
  /** 实时总结 */
  liveSummary?: string;
  /** 实时总结卡片 */
  liveSummaryCards?: RealtimeSummaryCard[];
  /** 是否有提问卡片正在显示 */
  hasActiveQuestion?: boolean;
  /** 是否正在展示兜底答案面板 */
  showFallbackPanel?: boolean;
  /** 点击开始监听 */
  onStartMonitor: () => void;
  /** 点击停止监听 */
  onStopMonitor: () => void;
  /** 点击暂停/继续 */
  onPauseResume: () => void;
  /** 点击「课堂状态」 */
  onClassStatus: () => void;
  /** 点击「问题时间轴」 */
  onTimeline: () => void;
  /** 点击「知识树回顾」 */
  onKnowledgeTree: () => void;
  /** 点击设置 */
  onSettings: () => void;
  /** 手动重置上下文 */
  onResetContext: () => void;
  /** 手动重新预热本地模型 */
  onWarmupLocalLLM: () => void;
  /** 手动重新检查本地模型 */
  onRefreshLocalLLM: () => void;
  /** 上传参考资料后回调 */
  onMaterialUploaded: () => void;
}

function TranscriptLine({ text, dimmed = false }: { text: string; dimmed?: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLSpanElement>(null);
  const metricsRef = useRef({ text: "", maxOffset: 0, updatedAt: 0 });
  const [offset, setOffset] = useState(0);
  const [durationMs, setDurationMs] = useState(0);

  useLayoutEffect(() => {
    const syncScroll = (instant = false) => {
      const container = containerRef.current;
      const textNode = textRef.current;
      if (!container || !textNode) return;

      const maxOffset = Math.max(0, textNode.scrollWidth - container.clientWidth);
      const now = performance.now();
      const previous = metricsRef.current;
      const isContinuation = previous.text.length > 0 && text.startsWith(previous.text);
      const nextDuration = instant || !isContinuation
        ? 0
        : Math.min(1400, Math.max(120, now - previous.updatedAt || 180));

      setOffset(maxOffset);
      if (maxOffset <= previous.maxOffset || maxOffset === 0) {
        setDurationMs(0);
      } else {
        setDurationMs(nextDuration);
      }

      metricsRef.current = { text, maxOffset, updatedAt: now };
    };

    syncScroll();

    const observer = new ResizeObserver(() => syncScroll(true));
    if (containerRef.current) observer.observe(containerRef.current);
    if (textRef.current) observer.observe(textRef.current);

    return () => observer.disconnect();
  }, [text]);

  const textClassName = `whitespace-nowrap ${dimmed ? "text-white/45" : "text-white/80"}`;

  return (
    <div ref={containerRef} className="overflow-hidden whitespace-nowrap">
      <span
        ref={textRef}
        className={`${textClassName} block w-max`}
        style={{
          transform: `translate3d(-${offset}px, 0, 0)`,
          transition: durationMs > 0 ? `transform ${durationMs}ms linear` : "none",
          willChange: "transform",
        }}
      >
        {text}
      </span>
    </div>
  );
}

function RealtimeSummaryStream({
  cards,
  summaryText,
  isPaused,
}: {
  cards: RealtimeSummaryCard[];
  summaryText: string;
  isPaused: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
  }, [cards]);

  if (cards.length === 0) {
    return (
      <p className="text-[10px] text-white/25 italic">
        {isPaused ? "已暂停更新总结" : "正在积累课堂内容，稍后自动生成章节总结..."}
      </p>
    );
  }

  return (
    <div ref={containerRef} className="max-h-[150px] space-y-2 overflow-y-auto pr-1">
      {cards.map((card, index) => (
        <div key={`${card.section_title}-${index}`} className="summary-stream-card">
          <div className="summary-stream-card__rail" />
          <div className="summary-stream-card__body">
            <div className="summary-stream-card__tag">{card.section_title}</div>
            <div className="mt-2 space-y-1.5">
              {card.points.map((point, pointIndex) => (
                <div key={`${card.section_title}-${pointIndex}`} className="summary-stream-card__point">
                  {point}
                </div>
              ))}
            </div>
            {card.flow_steps && card.flow_steps.length > 0 && (
              <div className="summary-stream-card__flow">
                <div className="summary-stream-card__flow-title">{card.flow_title || "关键流程"}</div>
                <div className="summary-stream-card__steps">
                  {card.flow_steps.map((step, stepIndex) => (
                    <div key={`${card.section_title}-step-${stepIndex}`} className="summary-stream-card__step">
                      <span className="summary-stream-card__step-dot" />
                      <span>{step}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      ))}
      {summaryText && (
        <p className="px-1 text-[10px] leading-5 text-white/45">
          {summaryText}
        </p>
      )}
    </div>
  );
}

export default function ToolBar({
  isMonitoring,
  isPaused,
  isLoading,
  courseName,
  localLLMStatus,
  localLLMLoading = false,
  localLLMError,
  contextStatus,
  recentTranscripts,
  partialTranscript = "",
  liveSummary = "",
  liveSummaryCards = [],
  hasActiveQuestion = false,
  showFallbackPanel = false,
  onStartMonitor,
  onStopMonitor,
  onPauseResume,
  onClassStatus,
  onTimeline,
  onKnowledgeTree,
  onSettings,
  onResetContext,
  onWarmupLocalLLM,
  onRefreshLocalLLM,
  onMaterialUploaded,
}: ToolBarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [showMore, setShowMore] = useState(false);
  const [uploading, setUploading] = useState(false);

  const sessionLabel = isLoading
    ? "初始化中"
    : isMonitoring
      ? (isPaused ? "已暂停" : "监听中")
      : "待命";

  const readinessLabel = (() => {
    if (localLLMError) return "状态异常";
    if (localLLMLoading && !localLLMStatus) return "检查中";
    if (!localLLMStatus) return "未检测";
    if (!localLLMStatus.online) return "Ollama 离线";
    if (!localLLMStatus.chat_model_available) return "模型缺失";
    if (localLLMStatus.warmup_state === "warming") return "预热中";
    if (localLLMStatus.is_warmed || localLLMStatus.warmup_state === "ready") return "可答";
    return "待预热";
  })();

  const readinessTone = !localLLMStatus?.online || localLLMError
    ? "border-red-400/25 bg-red-500/12 text-red-100"
    : readinessLabel === "可答"
      ? "border-emerald-400/25 bg-emerald-500/12 text-emerald-100"
      : "border-amber-400/25 bg-amber-500/12 text-amber-100";

  const contextUsageLabel = contextStatus
    ? `上下文 ${Math.round(contextStatus.usage_ratio * 100)}%`
    : "上下文未读";

  const contextTone = contextStatus?.reset_recommended
    ? "border-amber-400/25 bg-amber-500/12 text-amber-100"
    : "border-white/10 bg-black/15 text-white/72";

  const modelDetailLine = localLLMStatus
    ? [
        `短答 ${localLLMStatus.chat_model}`,
        `总结 ${localLLMStatus.final_summary_model}`,
        localLLMStatus.realtime_summary_enabled ? `实时总结 ${localLLMStatus.realtime_summary_model}` : "实时总结关闭",
      ].join(" · ")
    : "默认短答 qwen2.5:1.5b · 默认总结 gemma4:e4b";

  useLayoutEffect(() => {
    (async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const { LogicalSize } = await import("@tauri-apps/api/dpi");
        const win = getCurrentWindow();

        const width = MAIN_WINDOW_SIZE.width;
        let height: number;
        if (showFallbackPanel) {
          height = MAIN_WINDOW_SIZE.fallbackHeight;
        } else if (showMore) {
          height = isMonitoring
            ? (hasActiveQuestion ? MAIN_WINDOW_SIZE.monitoringExpandedWithQuestionHeight : MAIN_WINDOW_SIZE.monitoringExpandedHeight)
            : MAIN_WINDOW_SIZE.idleExpandedHeight;
        } else {
          height = isMonitoring
            ? (hasActiveQuestion ? MAIN_WINDOW_SIZE.monitoringWithQuestionHeight : MAIN_WINDOW_SIZE.monitoringHeight)
            : MAIN_WINDOW_SIZE.idleHeight;
        }

        await win.setSize(new LogicalSize(width, height));
      } catch {
        /* 忽略窗口操作错误 */
      }
    })();
  }, [hasActiveQuestion, isMonitoring, showFallbackPanel, showMore]);

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("http://127.0.0.1:8765/api/materials/upload", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error("上传失败");
      onMaterialUploaded();
    } catch {
      // 上传失败静默处理
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="relative flex flex-col gap-1 px-2 pb-2">
      <input
        ref={fileInputRef}
        type="file"
        accept=".pptx,.ppt,.pdf,.docx,.doc,.txt,.md"
        className="hidden"
        onChange={handleFileChange}
        aria-label="上传参考资料文件"
      />

      <div className="rounded-[calc(var(--window-radius)+2px)] border border-white/10 bg-white/[0.045] px-2.5 py-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`rounded-full border px-2 py-0.5 text-[10px] ${readinessTone}`}>
            {readinessLabel}
          </span>
          <span className="rounded-full border border-cyan-400/15 bg-cyan-500/8 px-2 py-0.5 text-[10px] text-cyan-100/80">
            模型 {localLLMStatus?.chat_model || "qwen2.5:1.5b"}
          </span>
          <span className="rounded-full border border-white/10 bg-black/15 px-2 py-0.5 text-[10px] text-white/72">
            课程 {courseName || "未设"}
          </span>
          <span className="rounded-full border border-white/10 bg-black/15 px-2 py-0.5 text-[10px] text-white/72">
            会话 {sessionLabel}
          </span>
          <span className={`rounded-full border px-2 py-0.5 text-[10px] ${contextTone}`}>
            {contextUsageLabel}
          </span>
        </div>
        <div className="mt-1 text-[10px] leading-4 text-white/42">
          {localLLMError
            ? localLLMError
            : localLLMStatus?.online
              ? `Ollama 在线 · 预热 ${localLLMStatus.warmup_state === "ready" || localLLMStatus.is_warmed ? "已就绪" : localLLMStatus.warmup_state === "warming" ? "进行中" : "未完成"}`
              : "开始课堂前会自动检查 Ollama 并预热课堂短答模型"}
        </div>
        {contextStatus && (
          <div className="mt-1 text-[10px] leading-4 text-white/36">
            最近窗口 {contextStatus.recent_transcript_lines} 条 · 问答 {contextStatus.recent_questions}/{contextStatus.recent_answers}
            {contextStatus.reset_recommended ? " · 建议重置上下文" : ""}
          </div>
        )}
        <div className="mt-1 text-[10px] leading-4 text-white/32">
          {modelDetailLine}
          {localLLMStatus?.missing_models.length
            ? ` · 缺少 ${localLLMStatus.missing_models.join(" / ")}`
            : ""}
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <button
            onClick={onRefreshLocalLLM}
            disabled={isLoading}
            className="rounded-full border border-white/10 bg-black/15 px-2.5 py-1 text-[10px] text-white/72 transition hover:bg-white/10 hover:text-white disabled:opacity-50"
          >
            检查模型
          </button>
          <button
            onClick={onWarmupLocalLLM}
            disabled={isLoading}
            className="rounded-full border border-cyan-400/20 bg-cyan-500/12 px-2.5 py-1 text-[10px] text-cyan-100 transition hover:bg-cyan-500/20 disabled:opacity-50"
          >
            重新预热
          </button>
          {isMonitoring && (
            <button
              onClick={onResetContext}
              disabled={isLoading}
              className="rounded-full border border-amber-400/20 bg-amber-500/12 px-2.5 py-1 text-[10px] text-amber-100 transition hover:bg-amber-500/20 disabled:opacity-50"
            >
              重置上下文
            </button>
          )}
        </div>
      </div>

      {!isMonitoring ? (
        <>
          <div className="grid grid-cols-5 gap-1.5 pt-0.5">
            <button
              onClick={onStartMonitor}
              disabled={isLoading}
              className="theme-primary-button col-span-4 flex h-8 items-center justify-center rounded-[calc(var(--window-radius)+4px)] text-[13px] font-bold tracking-wide transition hover:brightness-110 disabled:opacity-50"
              title="开始录音与监控"
            >
              🎓 开始监听
            </button>

            <button
              onClick={() => setShowMore((prev) => !prev)}
              className="theme-secondary-button col-span-1 flex h-8 items-center justify-center rounded-[calc(var(--window-radius)+2px)] text-[12px] font-medium transition hover:brightness-110"
            >
              {showMore ? "收起" : "更多"}
            </button>
          </div>

          {!showMore && <div className="theme-muted-text mt-0.5 text-center text-[10px] opacity-60">点击开始监听课堂，实时检测学生提问</div>}
        </>
      ) : (
        <>
          <div className="grid grid-cols-5 gap-1.5 pt-0.5">
            <button
              onClick={onPauseResume}
              disabled={isLoading}
              className={`col-span-2 flex h-7 items-center justify-center rounded-[calc(var(--window-radius)+3px)] text-[11px] font-medium transition disabled:opacity-50 ${
                isPaused ? "theme-primary-button" : "theme-secondary-button"
              }`}
            >
              {isPaused ? "▶ 继续" : "⏸ 暂停"}
            </button>

            <button
              onClick={onStopMonitor}
              disabled={isLoading}
              className="col-span-2 flex h-7 items-center justify-center rounded-[calc(var(--window-radius)+3px)] border border-red-400/25 bg-red-500/16 text-[11px] font-medium text-red-100 transition hover:bg-red-500/26 disabled:opacity-60"
            >
              {isLoading ? "正在生成报告..." : "⏹ 结束"}
            </button>

            <button
              onClick={() => setShowMore((prev) => !prev)}
              className="col-span-1 theme-secondary-button flex h-7 items-center justify-center rounded-[calc(var(--window-radius)+2px)] text-[11px] transition hover:brightness-110"
            >
              {showMore ? "收起" : "⚙️"}
            </button>
          </div>

          {/* 实时语音转录区域 */}
          <div className="mt-1 rounded-[calc(var(--window-radius)+2px)] border border-white/8 bg-black/20 px-2.5 py-2 min-h-[68px]">
            <div className="mb-1 flex items-center gap-1">
              <span className={`h-1.5 w-1.5 rounded-full ${isPaused ? "bg-white/30" : "bg-green-400 animate-pulse"}`} />
              <span className="text-[9px] text-white/40 tracking-wide">实时转录</span>
            </div>
            {(recentTranscripts.length > 0 || partialTranscript) ? (
              <div className="space-y-1 text-[11px] leading-relaxed">
                {recentTranscripts.map((line, index) => (
                  <TranscriptLine key={`${index}-${line}`} text={line} />
                ))}
                {partialTranscript && (
                  <TranscriptLine text={partialTranscript} dimmed />
                )}
              </div>
            ) : (
              <p className="text-[10px] text-white/25 italic">
                {isPaused ? "已暂停" : "等待语音输入..."}
              </p>
            )}
          </div>

          <div className="rounded-[calc(var(--window-radius)+2px)] border border-cyan-400/12 bg-cyan-500/8 px-2.5 py-2 min-h-[76px]">
            <div className="mb-1 flex items-center gap-1">
              <span className={`h-1.5 w-1.5 rounded-full ${isPaused ? "bg-white/30" : "bg-cyan-300 animate-pulse"}`} />
              <span className="text-[9px] text-cyan-100/55 tracking-wide">实时总结</span>
            </div>
            <RealtimeSummaryStream cards={liveSummaryCards} summaryText={liveSummary} isPaused={isPaused} />
          </div>
        </>
      )}

      {showMore && (
        <div className="theme-panel grid gap-2 rounded-[calc(var(--window-radius)+8px)] p-2 backdrop-blur-md">
          <button
            onClick={handleUploadClick}
            disabled={isLoading || uploading}
            className="theme-feature-button rounded-[calc(var(--window-radius)+4px)] px-3 py-3 text-left text-sm font-medium transition hover:brightness-110 disabled:opacity-50"
            title="上传课程参考资料"
          >
            📄 {uploading ? "上传中..." : "上传参考资料"}
          </button>

          {isMonitoring && (
            <button
              onClick={onClassStatus}
              disabled={isLoading}
              className="theme-feature-button rounded-[calc(var(--window-radius)+4px)] px-3 py-3 text-left text-sm font-medium transition hover:brightness-110 disabled:opacity-50"
            >
              📊 当前课堂状态
            </button>
          )}

          <button
            onClick={onWarmupLocalLLM}
            disabled={isLoading}
            className="theme-feature-button rounded-[calc(var(--window-radius)+4px)] px-3 py-3 text-left text-sm font-medium transition hover:brightness-110 disabled:opacity-50"
          >
            ♨️ 重新预热模型
          </button>

          <button
            onClick={onRefreshLocalLLM}
            disabled={isLoading}
            className="theme-feature-button rounded-[calc(var(--window-radius)+4px)] px-3 py-3 text-left text-sm font-medium transition hover:brightness-110 disabled:opacity-50"
          >
            🔌 重新检查 Ollama
          </button>

          <button
            onClick={onResetContext}
            disabled={isLoading}
            className="rounded-[calc(var(--window-radius)+4px)] border border-amber-400/20 bg-amber-500/12 px-3 py-3 text-left text-sm font-medium text-amber-100 transition hover:bg-amber-500/20 disabled:opacity-50"
          >
            🧹 重置课堂上下文
          </button>

          <button
            onClick={onTimeline}
            disabled={isLoading}
            className="theme-feature-button rounded-[calc(var(--window-radius)+4px)] px-3 py-3 text-left text-sm font-medium transition hover:brightness-110 disabled:opacity-50"
          >
            🕐 问题时间轴
          </button>

          <button
            onClick={onKnowledgeTree}
            disabled={isLoading}
            className="theme-feature-button rounded-[calc(var(--window-radius)+4px)] px-3 py-3 text-left text-sm font-medium transition hover:brightness-110 disabled:opacity-50"
          >
            🌿 知识树回顾
          </button>

          <button
            onClick={onSettings}
            disabled={isLoading}
            className="theme-secondary-button rounded-[calc(var(--window-radius)+4px)] px-3 py-3 text-left text-sm font-medium transition hover:brightness-110 disabled:opacity-50"
          >
            ⚙️ 设置
          </button>
        </div>
      )}
    </div>
  );
}
