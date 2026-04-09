/**
 * ClassFox 课堂助教 - 主应用组件
 * =================================
 * 整合所有子组件，管理全局状态
 */

import { useCallback, useEffect, useRef, useState } from "react";
import TitleBar from "./components/TitleBar";
import ToolBar from "./components/ToolBar";
import QuestionCard from "./components/QuestionCard";
import FallbackPanel from "./components/FallbackPanel";
import ClassStatusPanel from "./components/ClassStatusPanel";
import StartMonitorPanel from "./components/StartMonitorPanel";
import SettingsPanel from "./components/SettingsPanel";
import TimelinePanel from "./components/TimelinePanel";
import SummaryGenerationPanel from "./components/SummaryGenerationPanel";
import KnowledgeTreePanel from "./components/KnowledgeTreePanel";
import ToastContainer, { type ToastMessage } from "./components/Toast";
import { useWebSocket } from "./hooks/useWebSocket";
import classFoxIcon from "../src-tauri/icons/icon.png";
import {
  getMonitorContextStatus,
  startMonitor,
  stopMonitor,
  pauseMonitor,
  resumeMonitor,
  clearTimeline,
  getFallbackAnswer,
  getLocalLLMHealth,
  resetMonitorContext,
  warmupLocalLLM,
  getFinalSummaryStatus,
  type ContextStatus,
  type FallbackAnswerResponse,
  type LocalLLMStatus,
  type StartMonitorResponse,
} from "./services/api";
import { applyUiStyleSettings, readUiStyleSettings } from "./services/preferences";

// Toast ID 计数器
let toastId = 0;

function SplashScreen() {
  return (
    <div className="splash-scene flex h-full w-full items-center justify-center bg-transparent">
      <div className="startup-card flex flex-col items-center bg-transparent px-6 py-5 text-center">
        <div className="startup-ring mb-4 flex h-24 w-24 items-center justify-center rounded-full border border-cyan-300/20 bg-white/6">
          <img src={classFoxIcon} alt="课狐 ClassFox" className="startup-logo h-14 w-14 object-contain" />
        </div>
        <p className="text-base font-semibold tracking-[0.18em] text-white/92">课狐启动中</p>
        <p className="mt-2 text-[11px] leading-6 text-cyan-50/70">ClassFox — 课堂助教</p>
      </div>
    </div>
  );
}

function MainApp() {
  // ---- 状态管理 ----
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [showFallbackPanel, setShowFallbackPanel] = useState(false);
  const [showClassStatusPanel, setShowClassStatusPanel] = useState(false);
  const [showStartMonitorPanel, setShowStartMonitorPanel] = useState(false);
  const [showSettingsPanel, setShowSettingsPanel] = useState(false);
  const [showTimelinePanel, setShowTimelinePanel] = useState(false);
  const [showKnowledgeTreePanel, setShowKnowledgeTreePanel] = useState(false);
  const [showSummaryGenerationPanel, setShowSummaryGenerationPanel] = useState(false);
  const [materialRefreshToken, setMaterialRefreshToken] = useState(0);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [activeCourseName, setActiveCourseName] = useState("");
  const [localLLMStatus, setLocalLLMStatus] = useState<LocalLLMStatus | null>(null);
  const [localLLMError, setLocalLLMError] = useState<string | null>(null);
  const [localLLMLoading, setLocalLLMLoading] = useState(true);
  const [contextStatus, setContextStatus] = useState<ContextStatus | null>(null);
  const [prefetchedFallback, setPrefetchedFallback] = useState<FallbackAnswerResponse | null>(null);
  const [prefetchedQuestion, setPrefetchedQuestion] = useState("");
  const [prefetchedTimestamp, setPrefetchedTimestamp] = useState("");
  const [prefetchLoading, setPrefetchLoading] = useState(false);
  const [lockedFallbackQuestion, setLockedFallbackQuestion] = useState("");
  const [lockedFallbackTimestamp, setLockedFallbackTimestamp] = useState("");
  const [lockedFallbackAnswer, setLockedFallbackAnswer] = useState<FallbackAnswerResponse | null>(null);
  const [lockedPrefetchedQuestion, setLockedPrefetchedQuestion] = useState("");
  const prefetchAbortRef = useRef<AbortController | null>(null);

  // WebSocket 连接
  const {
    lastQuestion,
    questionActive,
    recentTranscripts,
    partialTranscript,
    liveSummary,
    liveSummaryCards,
    finalSummaryStatus,
    knowledgeTree,
    knowledgeTreeHighlightNodeIds,
    connect,
    disconnect,
    dismissQuestion,
    clearFinalSummary,
    applyFinalSummaryStatus,
    applyKnowledgeTreeSnapshot,
  } =
    useWebSocket();
  const hasActiveQuestionCard = questionActive;
  const detectedQuestionText = lastQuestion?.text ?? "";
  const detectedQuestionTimestamp = lastQuestion?.timestamp ?? "";

  useEffect(() => {
    applyUiStyleSettings(readUiStyleSettings());
  }, []);

  const refreshLocalLLMStatus = useCallback(async () => {
    try {
      setLocalLLMError(null);
      const res = await getLocalLLMHealth();
      setLocalLLMStatus(res);
    } catch (err) {
      setLocalLLMError(err instanceof Error ? err.message : "读取本地模型状态失败");
    } finally {
      setLocalLLMLoading(false);
    }
  }, []);

  const refreshContextStatus = useCallback(async () => {
    try {
      const res = await getMonitorContextStatus();
      setContextStatus(res.context);
    } catch (err) {
      console.error("读取课堂上下文状态失败:", err);
    }
  }, []);

  useEffect(() => {
    void refreshLocalLLMStatus();
    void refreshContextStatus();
    const timer = window.setInterval(() => {
      void refreshLocalLLMStatus();
      void refreshContextStatus();
    }, 15000);
    return () => window.clearInterval(timer);
  }, [refreshContextStatus, refreshLocalLLMStatus]);

  // ---- Toast 管理 ----
  const addToast = useCallback(
    (text: string, type: ToastMessage["type"] = "info") => {
      const id = ++toastId;
      setToasts((prev) => [...prev, { id, text, type }]);
    },
    []
  );

  const showToast = useCallback(
    (text: string, type: ToastMessage["type"] = "info") => {
      const id = ++toastId;
      setToasts([{ id, text, type }]);
    },
    []
  );

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const cancelFallbackPrefetch = useCallback((clearCache = true) => {
    prefetchAbortRef.current?.abort();
    prefetchAbortRef.current = null;
    setPrefetchLoading(false);
    if (clearCache) {
      setPrefetchedFallback(null);
      setPrefetchedQuestion("");
      setPrefetchedTimestamp("");
    }
  }, []);

  const prefetchFallbackAnswer = useCallback(
    (question: string, timestamp: string) => {
      const trimmedQuestion = question.trim();
      if (!trimmedQuestion) return;
      if (prefetchLoading && prefetchedQuestion === trimmedQuestion && prefetchedTimestamp === timestamp) return;
      if (prefetchedFallback && prefetchedQuestion === trimmedQuestion && prefetchedTimestamp === timestamp) return;

      cancelFallbackPrefetch(true);

      const controller = new AbortController();
      prefetchAbortRef.current = controller;
      setPrefetchedQuestion(trimmedQuestion);
      setPrefetchedTimestamp(timestamp);
      setPrefetchLoading(true);

      getFallbackAnswer(trimmedQuestion, timestamp, controller.signal)
        .then((res) => {
          if (controller.signal.aborted) return;
          setPrefetchedFallback(res);
        })
        .catch((err) => {
          if (err instanceof Error && err.name === "AbortError") return;
          console.error("预生成兜底答案失败:", err);
        })
        .finally(() => {
          if (prefetchAbortRef.current === controller) {
            prefetchAbortRef.current = null;
            setPrefetchLoading(false);
          }
        });
    },
    [cancelFallbackPrefetch, prefetchedFallback, prefetchLoading, prefetchedQuestion, prefetchedTimestamp]
  );

  useEffect(() => {
    if (!questionActive || showFallbackPanel || !detectedQuestionText) return;
    prefetchFallbackAnswer(detectedQuestionText, detectedQuestionTimestamp);
  }, [detectedQuestionText, detectedQuestionTimestamp, prefetchFallbackAnswer, questionActive, showFallbackPanel]);

  useEffect(() => {
    if (!showSummaryGenerationPanel) return;

    let cancelled = false;
    let timer: number | null = null;

    const poll = async () => {
      try {
        const status = await getFinalSummaryStatus();
        if (cancelled) return;
        if (
          status.phase &&
          (status.phase !== "idle" ||
            status.thinking_text ||
            status.content_text ||
            status.filename ||
            status.error)
        ) {
          applyFinalSummaryStatus({
            type: "final_summary_update",
            ...status,
          });
        }
      } catch (err) {
        if (!cancelled) {
          console.error("轮询课后总结状态失败:", err);
        }
      } finally {
        if (!cancelled) {
          timer = window.setTimeout(poll, 600);
        }
      }
    };

    void poll();

    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [applyFinalSummaryStatus, showSummaryGenerationPanel]);

  // ---- 停止监听 ----
  const handleStopMonitor = useCallback(async () => {
    setIsLoading(true);
    dismissQuestion();
    setShowSummaryGenerationPanel(true);
    showToast("正在生成课堂报告，请稍候...", "info");
    try {
      const res = await stopMonitor();
      cancelFallbackPrefetch();
      setIsMonitoring(false);
      setIsPaused(false);
      setActiveCourseName("");
      void refreshLocalLLMStatus();
      void refreshContextStatus();

      if (res.summary?.filename) {
        showToast(`监控已停止，已自动生成总结：${res.summary.filename}`, "success");
      } else if (res.summary_error) {
        showToast(`监控已停止，但总结生成失败：${res.summary_error}`, "error");
      } else {
        showToast(res.message, "info");
      }
    } catch (err) {
      setShowSummaryGenerationPanel(false);
      showToast(
        `操作失败: ${err instanceof Error ? err.message : "未知错误"}`,
        "error"
      );
    } finally {
      setIsLoading(false);
    }
  }, [cancelFallbackPrefetch, dismissQuestion, refreshContextStatus, showToast]);

  const handleOpenStartMonitor = useCallback(() => {
    setShowStartMonitorPanel(true);
  }, []);

  const handlePauseResume = useCallback(async () => {
    setIsLoading(true);
    try {
      if (isPaused) {
        const res = await resumeMonitor();
        connect();
        setIsPaused(false);
        addToast(res.message, "success");
        void refreshContextStatus();
      } else {
        const res = await pauseMonitor();
        cancelFallbackPrefetch();
        disconnect();
        setIsPaused(true);
        addToast(res.message, "info");
        void refreshContextStatus();
      }
    } catch (err) {
      addToast(
        `操作失败: ${err instanceof Error ? err.message : "未知错误"}`,
        "error"
      );
    } finally {
      setIsLoading(false);
    }
  }, [isPaused, connect, disconnect, addToast, cancelFallbackPrefetch, refreshContextStatus]);

  const handleStartMonitorConfirm = useCallback(
    async ({
      subject,
      courseName,
      materialFilename,
    }: {
      subject: string;
      courseName: string;
      materialFilename: string | null;
    }) => {
      const subjectLabel = subject.trim();
      const courseLabel = courseName.trim();
      const displayLabel = [subjectLabel, courseLabel].filter(Boolean).join(" · ");
      const startPrefix = displayLabel ? `${displayLabel} · ` : "";
      let res: StartMonitorResponse;
      setIsLoading(true);
      try {
        res = await startMonitor({
          subject,
          course_name: courseName,
          material_filename: materialFilename,
        });
        if (res.local_llm) {
          setLocalLLMStatus(res.local_llm);
          setLocalLLMError(null);
        }
        void refreshContextStatus();
      } catch (err) {
        addToast(`启动失败: ${err instanceof Error ? err.message : "未知错误"}`, "error");
        throw err;
      } finally {
        setIsLoading(false);
      }
      // 开始监听时清空上次时间轴
      clearTimeline().catch(() => {/* 静默失败 */});
      cancelFallbackPrefetch();
      connect();
      setIsMonitoring(true);
      setIsPaused(false);
      setActiveCourseName(displayLabel || res.init_steps?.find((step) => step.step === "subject_ready")?.subject || "");
      setShowStartMonitorPanel(false);
      const warmedModel = res.local_llm?.chat_model;
      addToast(
        warmedModel
          ? `开始监听 🎓 ${startPrefix}已检查 Ollama 并预热 ${warmedModel}`
          : (displayLabel ? `开始监听 🎓 ${displayLabel}` : "开始监听 🎓"),
        "success"
      );
    },
    [cancelFallbackPrefetch, connect, addToast, refreshContextStatus]
  );

  const handleResetContext = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await resetMonitorContext();
      if (res.warmup) {
        setLocalLLMStatus(res.warmup);
        setLocalLLMError(null);
      }
      setContextStatus(res.context);
      addToast(
        res.warmup_error
          ? `上下文已重置，但模型预热失败：${res.warmup_error}`
          : "课堂上下文已重置，并重新预热短答模型",
        res.warmup_error ? "error" : "success"
      );
    } catch (err) {
      addToast(`重置失败: ${err instanceof Error ? err.message : "未知错误"}`, "error");
    } finally {
      setIsLoading(false);
    }
  }, [addToast]);

  const handleWarmupLocalLLM = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await warmupLocalLLM();
      setLocalLLMStatus(res);
      setLocalLLMError(null);
      addToast(`已重新预热 ${res.chat_model}`, "success");
    } catch (err) {
      addToast(`预热失败: ${err instanceof Error ? err.message : "未知错误"}`, "error");
    } finally {
      setIsLoading(false);
    }
  }, [addToast]);

  const handleRefreshLocalLLM = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await getLocalLLMHealth();
      setLocalLLMStatus(res);
      setLocalLLMError(null);
      addToast(res.online ? "已刷新本地模型状态" : "已刷新状态，当前 Ollama 仍离线", res.online ? "success" : "error");
    } catch (err) {
      addToast(`检查失败: ${err instanceof Error ? err.message : "未知错误"}`, "error");
    } finally {
      setIsLoading(false);
    }
  }, [addToast]);

  // ---- 查看兜底答案 ----
  const handleViewAnswer = useCallback(() => {
    const currentQuestion = detectedQuestionText.trim();
    const currentTimestamp = detectedQuestionTimestamp.trim();
    const hasMatchingPrefetch =
      Boolean(prefetchedFallback) &&
      prefetchedQuestion === currentQuestion &&
      prefetchedTimestamp === currentTimestamp;

    setLockedFallbackQuestion(currentQuestion);
    setLockedFallbackTimestamp(currentTimestamp);
    setLockedFallbackAnswer(hasMatchingPrefetch ? prefetchedFallback : null);
    setLockedPrefetchedQuestion(hasMatchingPrefetch ? currentQuestion : "");
    cancelFallbackPrefetch(!hasMatchingPrefetch);
    dismissQuestion();
    setShowFallbackPanel(true);
  }, [
    cancelFallbackPrefetch,
    detectedQuestionText,
    detectedQuestionTimestamp,
    dismissQuestion,
    prefetchedFallback,
    prefetchedQuestion,
    prefetchedTimestamp,
  ]);

  // ---- 关闭兜底答案面板 ----
  const handleCloseFallback = useCallback(() => {
    setShowFallbackPanel(false);
    setLockedFallbackQuestion("");
    setLockedFallbackTimestamp("");
    setLockedFallbackAnswer(null);
    setLockedPrefetchedQuestion("");
    cancelFallbackPrefetch();
  }, [cancelFallbackPrefetch]);

  const handleDismissQuestion = useCallback(() => {
    cancelFallbackPrefetch();
    dismissQuestion();
  }, [cancelFallbackPrefetch, dismissQuestion]);

  // ---- 查看课堂状态 ----
  const handleClassStatus = useCallback(() => {
    dismissQuestion();
    setShowClassStatusPanel(true);
  }, [dismissQuestion]);

  // ---- 关闭课堂状态面板 ----
  const handleCloseClassStatus = useCallback(() => {
    setShowClassStatusPanel(false);
  }, []);

  const handleOpenSettings = useCallback(() => {
    setShowSettingsPanel(true);
  }, []);

  const handleCloseSettings = useCallback(() => {
    setShowSettingsPanel(false);
  }, []);

  const handleTimeline = useCallback(() => {
    setShowTimelinePanel(true);
  }, []);

  const handleCloseTimeline = useCallback(() => {
    setShowTimelinePanel(false);
  }, []);

  const handleKnowledgeTree = useCallback(() => {
    setShowKnowledgeTreePanel(true);
  }, []);

  const handleCloseKnowledgeTree = useCallback(() => {
    setShowKnowledgeTreePanel(false);
  }, []);

  const handleCloseSummaryGeneration = useCallback(() => {
    setShowSummaryGenerationPanel(false);
    disconnect();
    clearFinalSummary();
  }, [clearFinalSummary, disconnect]);

  return (
    <div className="app-shell relative h-full w-full overflow-hidden rounded-[var(--window-radius)] border border-[var(--theme-shell-border)] shadow-2xl backdrop-blur-xl">
      {/* 标题栏 */}
      <TitleBar isMonitoring={isMonitoring} isPaused={isPaused} courseName={activeCourseName} />

      {/* 工具栏（非面板模式时显示） */}
      {!showClassStatusPanel && !showStartMonitorPanel && !showSettingsPanel && !showTimelinePanel && !showKnowledgeTreePanel && !showSummaryGenerationPanel && (
        <ToolBar
          isMonitoring={isMonitoring}
          isPaused={isPaused}
          isLoading={isLoading}
          courseName={activeCourseName}
          localLLMStatus={localLLMStatus}
          localLLMError={localLLMError}
          localLLMLoading={localLLMLoading}
          contextStatus={contextStatus}
          recentTranscripts={recentTranscripts}
          partialTranscript={partialTranscript}
          liveSummary={liveSummary}
          liveSummaryCards={liveSummaryCards}
          hasActiveQuestion={hasActiveQuestionCard}
          showFallbackPanel={showFallbackPanel}
          onStartMonitor={handleOpenStartMonitor}
          onStopMonitor={handleStopMonitor}
          onPauseResume={handlePauseResume}
          onClassStatus={handleClassStatus}
          onTimeline={handleTimeline}
          onKnowledgeTree={handleKnowledgeTree}
          onSettings={handleOpenSettings}
          onResetContext={handleResetContext}
          onWarmupLocalLLM={handleWarmupLocalLLM}
          onRefreshLocalLLM={handleRefreshLocalLLM}
          onMaterialUploaded={() => setMaterialRefreshToken((prev) => prev + 1)}
        />
      )}

      <StartMonitorPanel
        visible={showStartMonitorPanel}
        onClose={() => setShowStartMonitorPanel(false)}
        onConfirm={handleStartMonitorConfirm}
        refreshToken={materialRefreshToken}
      />

      <SettingsPanel
        visible={showSettingsPanel}
        onClose={handleCloseSettings}
        onSaved={(message) => addToast(message, "success")}
      />

      {/* 兜底答案面板 */}
      <FallbackPanel
        visible={showFallbackPanel}
        onClose={handleCloseFallback}
        detectedQuestion={lockedFallbackQuestion}
        detectedTimestamp={lockedFallbackTimestamp}
        prefetchedAnswer={lockedFallbackAnswer}
        prefetchedQuestion={lockedPrefetchedQuestion}
        prefetchLoading={false}
        onConfirmed={({ linked_topic_title, question_status }) => {
          addToast(
            question_status === "linked_to_tree"
              ? `已记入课后回顾，并挂到 ${linked_topic_title || "当前主题"}`
              : "已记入课后回顾，挂载位置待确认",
            "success"
          );
        }}
        onKnowledgeTreeSnapshot={(snapshot) => {
          applyKnowledgeTreeSnapshot(snapshot);
        }}
        onDetailExpanded={() => {
          // markTimelineExpanded requires node_id; we don't have it here without tracking state.
          // The auto-bookmark via addTimelineNode repeat detection handles most cases.
        }}
      />

      {/* 课堂状态面板 */}
      <ClassStatusPanel visible={showClassStatusPanel} onClose={handleCloseClassStatus} />

      {/* 问题时间轴面板 */}
      <TimelinePanel visible={showTimelinePanel} onClose={handleCloseTimeline} />

      <KnowledgeTreePanel
        visible={showKnowledgeTreePanel}
        onClose={handleCloseKnowledgeTree}
        liveTree={knowledgeTree}
        highlightedNodeIds={knowledgeTreeHighlightNodeIds}
      />

      <SummaryGenerationPanel
        visible={showSummaryGenerationPanel}
        summaryStatus={finalSummaryStatus}
        onClose={handleCloseSummaryGeneration}
      />

      {/* 学生提问检测卡片 */}
      <QuestionCard
        active={questionActive && !showSummaryGenerationPanel}
        text={detectedQuestionText}
        onViewAnswer={handleViewAnswer}
        onDismiss={handleDismissQuestion}
      />

      {/* Toast 提示 */}
      <ToastContainer messages={toasts} onRemove={removeToast} />
    </div>
  );
}

export default function App() {
  const [windowLabel, setWindowLabel] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;

    (async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        if (!disposed) {
          setWindowLabel(getCurrentWindow().label);
        }
      } catch {
        if (!disposed) {
          setWindowLabel("main");
        }
      }
    })();

    return () => {
      disposed = true;
    };
  }, []);

  if (windowLabel === null) {
    return null;
  }

  if (windowLabel === "splash") {
    return <SplashScreen />;
  }
  return <MainApp />;
}
