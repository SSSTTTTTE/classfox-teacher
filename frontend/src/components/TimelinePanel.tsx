/**
 * 问题时间轴面板（教师版）
 * ==========================
 * 展示课堂问题轨迹，支持书签筛选和关键问题回顾
 */

import { useEffect, useState } from "react";
import { getKnowledgeTree, getTimeline, getTimelineSummary, type KnowledgeTreeSummary } from "../services/api";
import { PANEL_WINDOW_SIZES } from "../services/windowSizing";

interface TimelineNode {
  node_id: string;
  timestamp: string;
  student_question: string;
  one_sentence_answer: string;
  bookmarked: boolean;
  expanded: boolean;
  repeat_count: number;
  question_status?: string;
  linked_topic_title?: string;
}

interface TimelinePanelProps {
  visible: boolean;
  onClose: () => void;
}

export default function TimelinePanel({ visible, onClose }: TimelinePanelProps) {
  const [nodes, setNodes] = useState<TimelineNode[]>([]);
  const [bookmarkedOnly, setBookmarkedOnly] = useState(false);
  const [trajectory, setTrajectory] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [totalQuestions, setTotalQuestions] = useState(0);
  const [repeatedCount, setRepeatedCount] = useState(0);
  const [linkedCount, setLinkedCount] = useState(0);
  const [pendingLinks, setPendingLinks] = useState(0);
  const [statusCounts, setStatusCounts] = useState<Record<string, number>>({});
  const [knowledgeSummary, setKnowledgeSummary] = useState<KnowledgeTreeSummary | null>(null);

  useEffect(() => {
    if (!visible) return;
    setLoading(true);
    setError(null);

    // 同时加载时间轴列表和摘要
    Promise.all([
      getTimeline(bookmarkedOnly),
      getTimelineSummary(),
      getKnowledgeTree(),
    ])
      .then(([timelineRes, summaryRes, knowledgeRes]) => {
        setNodes(timelineRes.nodes);
        setTotalQuestions(summaryRes.total_questions);
        setRepeatedCount(summaryRes.repeated_questions);
        setLinkedCount(summaryRes.linked_questions);
        setPendingLinks(summaryRes.pending_links);
        setStatusCounts(summaryRes.status_counts ?? {});
        setTrajectory(summaryRes.trajectory);
        setKnowledgeSummary(knowledgeRes.summary);
      })
      .catch((err) => setError(err.message || "加载时间轴失败"))
      .finally(() => setLoading(false));
  }, [visible, bookmarkedOnly]);

  useEffect(() => {
    if (!visible) return;
    (async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const { LogicalSize } = await import("@tauri-apps/api/dpi");
        await getCurrentWindow().setSize(new LogicalSize(PANEL_WINDOW_SIZES.timeline.width, PANEL_WINDOW_SIZES.timeline.height));
      } catch {
        /* 忽略窗口操作错误 */
      }
    })();
  }, [visible]);

  if (!visible) return null;

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden p-3 animate-in fade-in duration-300">
      {/* 顶部统计 */}
      <div className="mb-3 flex items-center gap-3 text-xs text-white/55">
        <span>共 {totalQuestions} 个问题</span>
        <span>已挂树 {linkedCount} 个</span>
        {pendingLinks > 0 && <span className="text-amber-300/80">待确认挂载 {pendingLinks} 个</span>}
        {repeatedCount > 0 && (
          <span className="text-amber-400/80">⚠ {repeatedCount} 个重复追问</span>
        )}
        <label className="ml-auto flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={bookmarkedOnly}
            onChange={(e) => setBookmarkedOnly(e.target.checked)}
            className="h-3 w-3 accent-cyan-400"
          />
          <span>仅看书签</span>
        </label>
      </div>

      {knowledgeSummary && (
        <div className="mb-3 rounded-2xl border border-cyan-400/15 bg-cyan-500/8 p-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.24em] text-cyan-100/55">Knowledge Tree</div>
              <div className="mt-1 text-sm font-semibold text-white/86">
                {knowledgeSummary.current_main_topic || "暂无主主题"}
              </div>
            </div>
            <div className="text-right text-[10px] leading-5 text-white/45">
              <div>节点 {knowledgeSummary.total_nodes}</div>
              <div>连线 {knowledgeSummary.total_edges}</div>
            </div>
          </div>
        </div>
      )}

      {/* 列表区域 */}
      <div className="min-h-0 flex-1 overflow-y-auto pb-14 pr-1 flex flex-col gap-2">
        {loading && (
          <div className="flex items-center justify-center py-8 text-white/50">
            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2" />
            <span className="text-xs">加载中...</span>
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/15 px-3 py-2 text-xs text-red-200">
            ⚠️ {error}
          </div>
        )}

        {!loading && nodes.length === 0 && (
          <div className="flex flex-col items-center justify-center py-10 text-white/35 text-xs gap-2">
            <span className="text-2xl">📋</span>
            <span>{bookmarkedOnly ? "暂无书签问题" : "本节课暂无问题记录"}</span>
          </div>
        )}

        {nodes.map((node) => (
          <div
            key={node.node_id}
            className={`rounded-xl border p-3 ${
              node.bookmarked
                ? "border-amber-400/30 bg-amber-500/8"
                : "border-white/10 bg-white/4"
            }`}
          >
            <div className="flex items-start gap-2">
              <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] text-white/40">{node.timestamp}</span>
                  {node.question_status && (
                    <span className="text-[10px] text-cyan-300/75 border border-cyan-400/20 px-1 rounded-full">
                      {node.question_status}
                    </span>
                  )}
                  {node.repeat_count > 1 && (
                    <span className="text-[10px] text-amber-400/70 border border-amber-400/30 px-1 rounded-full">
                      追问×{node.repeat_count}
                    </span>
                  )}
                  {node.bookmarked && (
                    <span className="text-[10px] text-amber-300/80">🔖</span>
                  )}
                  {node.expanded && (
                    <span className="text-[10px] text-cyan-400/60">已展开</span>
                  )}
                </div>
                <p className="text-xs text-white/85 leading-relaxed mt-0.5">
                  {node.student_question}
                </p>
                <p className="text-[11px] text-white/50 leading-relaxed mt-0.5 italic">
                  → {node.one_sentence_answer}
                </p>
                {node.linked_topic_title && (
                  <p className="text-[10px] text-cyan-200/65 leading-relaxed mt-1">
                    挂载主题：{node.linked_topic_title}
                  </p>
                )}
              </div>
            </div>
          </div>
        ))}

        {/* 关键问题轨迹（仅在有内容时显示） */}
        {!loading && trajectory && (
          <div className="mt-2 rounded-xl border border-indigo-500/20 bg-indigo-500/8 p-3">
            <div className="text-[10px] text-indigo-300/70 font-semibold mb-1.5">
              关键问题轨迹
            </div>
            <pre className="text-[10px] text-white/55 whitespace-pre-wrap leading-5">
              {trajectory}
            </pre>
          </div>
        )}

        {!loading && Object.keys(statusCounts).length > 0 && (
          <div className="mt-2 rounded-xl border border-white/10 bg-white/4 p-3">
            <div className="text-[10px] text-white/55 font-semibold mb-1.5">
              状态分布
            </div>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(statusCounts).map(([status, count]) => (
                <span
                  key={status}
                  className="rounded-full border border-white/10 bg-black/15 px-2 py-0.5 text-[10px] text-white/60"
                >
                  {status} {count}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 底部关闭按钮 */}
      <div className="absolute bottom-12 left-3 right-3 flex justify-center border-t border-white/10 bg-[rgba(3,10,20,0.92)] pt-3">
        <button
          onClick={onClose}
          className="px-4 py-1.5 text-xs rounded-lg bg-white/10 text-white/60 hover:bg-white/20 hover:text-white transition-all duration-150"
        >
          收起面板
        </button>
      </div>
    </div>
  );
}
