import { useEffect, useMemo, useRef, useState } from "react";
import type { FinalSummaryUpdateEvent } from "../hooks/useWebSocket";
import { getKnowledgeTree, getTimelineSummary, type KnowledgeTreeSummary, type TimelineSummaryResponse } from "../services/api";
import { MAIN_WINDOW_SIZE, PANEL_WINDOW_SIZES } from "../services/windowSizing";

interface SummaryGenerationPanelProps {
  visible: boolean;
  summaryStatus: FinalSummaryUpdateEvent | null;
  onClose: () => void;
}

const PHASE_LABELS: Record<string, string> = {
  idle: "待命",
  preparing: "准备中",
  thinking: "思考中",
  writing: "写作中",
  saving: "保存中",
  completed: "已完成",
  failed: "失败",
};

const PHASE_SEQUENCE = ["preparing", "thinking", "writing", "saving", "completed"] as const;

function SummaryTextBlock({
  title,
  text,
  emptyText,
  tone = "default",
}: {
  title: string;
  text: string;
  emptyText: string;
  tone?: "default" | "thinking";
}) {
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = contentRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  }, [text]);

  return (
    <section
      className={`summary-generation-block ${tone === "thinking" ? "summary-generation-block--thinking" : ""}`}
    >
      <div className="summary-generation-block__header">
        <span>{title}</span>
        <span className="summary-generation-block__meta">{text ? `${text.length} 字` : "等待中"}</span>
      </div>
      <div ref={contentRef} className="summary-generation-block__content">
        {text ? (
          <pre className="summary-generation-block__text">{text}</pre>
        ) : (
          <p className="summary-generation-block__empty">{emptyText}</p>
        )}
      </div>
    </section>
  );
}

export default function SummaryGenerationPanel({
  visible,
  summaryStatus,
  onClose,
}: SummaryGenerationPanelProps) {
  const [knowledgeSummary, setKnowledgeSummary] = useState<KnowledgeTreeSummary | null>(null);
  const [timelineSummary, setTimelineSummary] = useState<TimelineSummaryResponse | null>(null);

  useEffect(() => {
    if (!visible) return;

    (async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const { LogicalSize } = await import("@tauri-apps/api/dpi");
        await getCurrentWindow().setSize(
          new LogicalSize(PANEL_WINDOW_SIZES.summaryGeneration.width, PANEL_WINDOW_SIZES.summaryGeneration.height)
        );
      } catch {
        /* 忽略窗口操作错误 */
      }
    })();
  }, [visible]);

  useEffect(() => {
    if (!visible) return;

    let cancelled = false;
    let timer: number | null = null;

    const syncReviewData = async () => {
      try {
        const [knowledgeRes, timelineRes] = await Promise.all([
          getKnowledgeTree(),
          getTimelineSummary(),
        ]);
        if (cancelled) return;
        setKnowledgeSummary(knowledgeRes.summary);
        setTimelineSummary(timelineRes);
      } catch {
        if (!cancelled) {
          setKnowledgeSummary(null);
          setTimelineSummary(null);
        }
      } finally {
        if (!cancelled && summaryStatus?.active) {
          timer = window.setTimeout(syncReviewData, 1500);
        }
      }
    };

    void syncReviewData();
    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [summaryStatus?.active, visible]);

  const isBusy = Boolean(summaryStatus?.active);
  const phase = summaryStatus?.phase ?? "idle";
  const phaseIndex = PHASE_SEQUENCE.indexOf((phase === "failed" ? "saving" : phase) as (typeof PHASE_SEQUENCE)[number]);
  const courseName = summaryStatus?.course_name || "未命名课程";
  const statusMessage = summaryStatus?.message || "正在准备课后总结界面。";
  const closeLabel = isBusy ? "Gemma4 生成中..." : "关闭面板";
  const completedFilename = summaryStatus?.filename?.trim() || "";

  const progressItems = useMemo(
    () =>
      PHASE_SEQUENCE.map((item, index) => {
        const isCurrent = phase === item || (phase === "failed" && item === "saving");
        const isDone = phaseIndex >= 0 && index < phaseIndex;
        return {
          key: item,
          label: PHASE_LABELS[item],
          isCurrent,
          isDone,
        };
      }),
    [phase, phaseIndex]
  );

  if (!visible) return null;

  return (
    <div className="absolute inset-0 z-[80] bg-[rgba(2,8,18,0.42)] backdrop-blur-[2px]">
      <div className="flex h-full flex-col overflow-hidden bg-[linear-gradient(180deg,rgba(5,16,34,0.96),rgba(3,11,24,0.98))]">
        <div data-tauri-drag-region className="summary-generation-drag-handle" />
        <div className="summary-generation-hero">
          <div>
            <div className="summary-generation-hero__eyebrow">Gemma4 Summary Console</div>
            <h2 className="summary-generation-hero__title">课后总结生成中</h2>
            <p className="summary-generation-hero__subtitle">
              {courseName} · {summaryStatus?.model || "gemma4:e4b"}
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={isBusy}
            className="summary-generation-close"
            data-tauri-drag-region="false"
          >
            {closeLabel}
          </button>
        </div>

        <div className="summary-generation-status">
          <span className={`summary-generation-phase summary-generation-phase--${phase}`}>
            {PHASE_LABELS[phase] || phase}
          </span>
          <span className="summary-generation-message">{statusMessage}</span>
        </div>

        <div className="summary-generation-progress">
          {progressItems.map((item) => (
            <div
              key={item.key}
              className={`summary-generation-progress__item ${
                item.isCurrent ? "is-current" : item.isDone ? "is-done" : ""
              }`}
            >
              <span className="summary-generation-progress__dot" />
              <span>{item.label}</span>
            </div>
          ))}
        </div>

        <div className="summary-generation-layout">
          <SummaryTextBlock
            title="Gemma4 思考轨迹"
            text={summaryStatus?.thinking_text || ""}
            emptyText="Gemma4 还没开始输出 thinking，马上会在这里实时展开。"
            tone="thinking"
          />

          <SummaryTextBlock
            title="课堂总结正文"
            text={summaryStatus?.content_text || ""}
            emptyText="正文会随着模型输出逐步出现在这里。"
          />
        </div>

        <div className="grid grid-cols-2 gap-3 px-5 pb-3">
          <section className="summary-generation-block">
            <div className="summary-generation-block__header">
              <span>知识树回顾</span>
              <span className="summary-generation-block__meta">
                {knowledgeSummary ? `${knowledgeSummary.total_nodes} 节点` : "等待中"}
              </span>
            </div>
            <div className="summary-generation-block__content">
              {knowledgeSummary ? (
                <div className="space-y-2 text-[11px] leading-5 text-white/72">
                  <div>当前主主题：{knowledgeSummary.current_main_topic || "暂无"}</div>
                  <div>连线数量：{knowledgeSummary.total_edges}</div>
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {Object.entries(knowledgeSummary.node_type_counts).map(([type, count]) => (
                      <span
                        key={type}
                        className="rounded-full border border-white/10 bg-black/15 px-2 py-0.5 text-[10px] text-white/60"
                      >
                        {type} {count}
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="summary-generation-block__empty">知识树快照会在这里显示。</p>
              )}
            </div>
          </section>

          <section className="summary-generation-block">
            <div className="summary-generation-block__header">
              <span>问题轨迹回顾</span>
              <span className="summary-generation-block__meta">
                {timelineSummary ? `${timelineSummary.total_questions} 问题` : "等待中"}
              </span>
            </div>
            <div className="summary-generation-block__content">
              {timelineSummary ? (
                <div className="space-y-2 text-[11px] leading-5 text-white/72">
                  <div>有效问题：{timelineSummary.bookmarked_count} 个</div>
                  <div>已挂树：{timelineSummary.linked_questions} 个</div>
                  <div>待确认挂载：{timelineSummary.pending_links} 个</div>
                  <pre className="summary-generation-block__text">
                    {(timelineSummary.trajectory || "问题轨迹会在生成后出现在这里。").trim()}
                  </pre>
                </div>
              ) : (
                <p className="summary-generation-block__empty">问题轨迹会在这里显示。</p>
              )}
            </div>
          </section>
        </div>

        <div className="summary-generation-footer">
          <div className="summary-generation-footer__meta">
            {completedFilename
              ? `已保存文件：${completedFilename}`
              : summaryStatus?.error
                ? `错误：${summaryStatus.error}`
                : "正在等待 Gemma4 完成最后整理。"}
          </div>
          <button
            onClick={async () => {
              try {
                const { getCurrentWindow } = await import("@tauri-apps/api/window");
                const { LogicalSize } = await import("@tauri-apps/api/dpi");
                await getCurrentWindow().setSize(new LogicalSize(MAIN_WINDOW_SIZE.width, MAIN_WINDOW_SIZE.idleHeight));
              } catch {
                /* 忽略窗口操作错误 */
              }
              onClose();
            }}
            disabled={isBusy}
            className="summary-generation-footer__button"
          >
            {summaryStatus?.phase === "completed" ? "查看完成状态" : "关闭"}
          </button>
        </div>
      </div>
    </div>
  );
}
