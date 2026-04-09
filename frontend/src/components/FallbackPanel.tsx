/**
 * 兜底答案面板组件（教师版）
 * ============================
 * 展示 LLM 生成的学生问题和一句话兜底答案，支持展开详情和追问
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  confirmValidQuestion,
  getFallbackAnswer,
  questionFollowup,
  type FallbackAnswerResponse,
  type KnowledgeTreePayload,
} from "../services/api";

interface FallbackPanelProps {
  visible: boolean;
  onClose: () => void;
  detectedQuestion?: string;
  detectedTimestamp?: string;
  prefetchedAnswer?: FallbackAnswerResponse | null;
  prefetchedQuestion?: string;
  prefetchLoading?: boolean;
  onConfirmed?: (data: { linked_topic_title: string; question_status: string }) => void;
  onKnowledgeTreeSnapshot?: (tree: KnowledgeTreePayload) => void;
  onDetailExpanded?: () => void;
}

interface FallbackData {
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
}

export default function FallbackPanel({
  visible,
  onClose,
  detectedQuestion,
  detectedTimestamp,
  prefetchedAnswer,
  prefetchedQuestion,
  prefetchLoading = false,
  onConfirmed,
  onKnowledgeTreeSnapshot,
  onDetailExpanded,
}: FallbackPanelProps) {
  const [data, setData] = useState<FallbackData | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Array<{ role: "user" | "assistant"; content: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [confirmStatus, setConfirmStatus] = useState<{
    question_status: string;
    linked_topic_title: string;
    confirmed_at: string;
  } | null>(null);
  const expandedNotified = useRef(false);
  const confirmedSignatureRef = useRef("");

  const canAsk = useMemo(() => Boolean(data && question.trim() && !asking), [data, question, asking]);

  const applyAnswerData = (
    res: Pick<
      FallbackAnswerResponse,
      | "student_question"
      | "one_line_answer"
      | "teacher_speakable_answer"
      | "short_explanation"
      | "confidence"
      | "answer_mode"
      | "question_type"
      | "used_subject"
      | "question_id"
      | "answer_id"
      | "trigger_time"
    >
  ) => {
    const answerData = {
      student_question: res.student_question,
      one_line_answer: res.one_line_answer,
      teacher_speakable_answer: res.teacher_speakable_answer,
      short_explanation: res.short_explanation,
      confidence: res.confidence,
      answer_mode: res.answer_mode,
      question_type: res.question_type,
      used_subject: res.used_subject,
      question_id: res.question_id,
      answer_id: res.answer_id,
      trigger_time: res.trigger_time,
    };
    setData(answerData);
  };

  // 面板打开时请求兜底答案
  useEffect(() => {
    if (!visible) return;

    setError(null);
    setQuestion("");
    setMessages([]);
    setExpanded(false);
    setConfirmStatus(null);
    setConfirming(false);
    expandedNotified.current = false;
    confirmedSignatureRef.current = "";

    const hasPrefetchedAnswer =
      Boolean(prefetchedAnswer) &&
      Boolean(prefetchedQuestion) &&
      prefetchedQuestion === (detectedQuestion ?? "");

    if (hasPrefetchedAnswer && prefetchedAnswer) {
      applyAnswerData(prefetchedAnswer);
      setLoading(false);
      return;
    }

    if (prefetchLoading && prefetchedQuestion === (detectedQuestion ?? "")) {
      setData(null);
      setLoading(true);
      return;
    }

    let cancelled = false;
    setData(null);
    setLoading(true);

    getFallbackAnswer(detectedQuestion, detectedTimestamp)
      .then((res) => {
        if (cancelled) return;
        applyAnswerData(res);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message || "请求失败");
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [visible, detectedQuestion, detectedTimestamp, prefetchedAnswer, prefetchedQuestion, prefetchLoading]);

  useEffect(() => {
    if (!visible || !data?.question_id || !data?.answer_id) return;

    const signature = `${data.question_id}::${data.answer_id}`;
    if (confirmedSignatureRef.current === signature) return;

    let cancelled = false;
    confirmedSignatureRef.current = signature;
    setConfirming(true);
    setConfirmStatus(null);

    confirmValidQuestion({
      question_id: data.question_id,
      answer_id: data.answer_id,
      confirmed_by_teacher_action: true,
    })
      .then((res) => {
        if (cancelled) return;
        const payload = {
          question_status: res.question_status,
          linked_topic_title: res.linked_topic_title,
          confirmed_at: res.confirmed_at,
        };
        setConfirmStatus(payload);
        onConfirmed?.({
          linked_topic_title: payload.linked_topic_title,
          question_status: payload.question_status,
        });
        if (res.knowledge_tree_snapshot?.nodes) {
          onKnowledgeTreeSnapshot?.(res.knowledge_tree_snapshot);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "确认有效问题失败");
      })
      .finally(() => {
        if (!cancelled) {
          setConfirming(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [data, onConfirmed, visible]);

  if (!visible) return null;

  const handleAsk = async () => {
    if (!data || !question.trim() || asking) return;

    const followup = question.trim();
    const nextHistory = [...messages, { role: "user" as const, content: followup }];
    setMessages(nextHistory);
    setQuestion("");
    setAsking(true);
    setError(null);

    try {
      const res = await questionFollowup({
        student_question: data.student_question,
        teacher_speakable_answer: data.teacher_speakable_answer,
        followup,
        history: messages,
      });
      setMessages((prev) => [...prev, { role: "assistant", content: res.answer }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "追问失败");
    } finally {
      setAsking(false);
    }
  };

  return (
    <div className="fallback-stack-overlay pointer-events-none absolute inset-0 z-[70]">
      <div className="fallback-stack-scrim absolute inset-0" />
      <div className="fallback-stack-card absolute inset-x-2 top-10 bottom-3 pointer-events-auto overflow-hidden rounded-[28px] border border-cyan-300/12 bg-[rgba(4,14,28,0.96)] shadow-[0_30px_80px_rgba(8,145,178,0.18)] backdrop-blur-xl">
        <div className="flex h-full min-h-0 flex-col overflow-hidden p-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm">🧠</span>
              <span className="text-xs font-semibold tracking-wide text-white/82">兜底答案</span>
            </div>
            <button
              onClick={onClose}
              className="rounded-full border border-white/10 bg-white/6 px-2.5 py-1 text-[10px] text-white/58 transition hover:bg-white/12 hover:text-white/82"
            >
              收起
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto pr-1">
            {loading && (
              <div className="flex items-center justify-center py-8 text-white/60">
                <div className="mr-2 h-5 w-5 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                <span className="text-sm">正在生成兜底答案...</span>
              </div>
            )}

            {error && (
              <div className="mb-2 rounded-xl border border-red-500/30 bg-red-500/20 p-3 text-xs text-red-300">
                ⚠️ {error}
              </div>
            )}

            {data && !loading && (
              <div className="flex flex-col gap-2 pb-1">
                <div className="shrink-0 rounded-xl border border-indigo-500/20 bg-indigo-500/10 p-3">
                  <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                    <span className="text-sm">💬</span>
                    <span className="text-xs font-semibold text-indigo-300">学生问题</span>
                    {data.used_subject && (
                      <span className="ml-auto rounded-full border border-indigo-300/20 px-1.5 py-0.5 text-[10px] text-indigo-100/75">
                        {data.used_subject}
                      </span>
                    )}
                    {data.question_type && (
                      <span className="rounded-full border border-white/10 px-1.5 py-0.5 text-[10px] text-white/55">
                        {data.question_type}
                      </span>
                    )}
                  </div>
                  <p className="text-xs leading-relaxed text-white/90">{data.student_question}</p>
                </div>

                <div className="shrink-0 rounded-xl border border-green-500/20 bg-green-500/10 p-3">
                  <div className="mb-1.5 flex items-center gap-1.5">
                    <span className="text-sm">💡</span>
                    <span className="text-xs font-semibold text-green-300">老师可直接说</span>
                    {(data.confidence === "low" || data.answer_mode === "cautious") && (
                      <span className="ml-auto rounded-full border border-amber-400/30 px-1.5 py-0.5 text-[10px] text-amber-400/70">
                        谨慎回答
                      </span>
                    )}
                  </div>
                  <p className="text-sm font-medium leading-relaxed text-white">
                    {data.teacher_speakable_answer}
                  </p>
                </div>

                <div className="shrink-0 rounded-xl border border-cyan-400/18 bg-cyan-400/8 px-3 py-2">
                  <div className="mb-1 text-[11px] text-cyan-200/72">有效问题确认</div>
                  {confirming && (
                    <p className="text-[12px] leading-5 text-white/78">
                      正在记入课后回顾并尝试挂到知识树...
                    </p>
                  )}
                  {!confirming && confirmStatus && (
                    <p className="text-[12px] leading-5 text-white/84">
                      {confirmStatus.question_status === "linked_to_tree"
                        ? `已记入课后回顾，并挂接到「${confirmStatus.linked_topic_title || "当前主题"}」`
                        : `已记入课后回顾，待确认挂载位置${confirmStatus.linked_topic_title ? `（当前暂挂到「${confirmStatus.linked_topic_title}」）` : ""}`}
                    </p>
                  )}
                  {!confirming && !confirmStatus && !error && (
                    <p className="text-[12px] leading-5 text-white/60">等待确认结果...</p>
                  )}
                </div>

                {data.one_line_answer && (
                  <div className="shrink-0 rounded-xl border border-white/10 bg-white/5 px-3 py-2">
                    <div className="mb-1 text-[11px] text-white/45">一句话提要</div>
                    <p className="break-words whitespace-normal text-[13px] leading-6 text-white/82">
                      {data.one_line_answer}
                    </p>
                  </div>
                )}

                {data.short_explanation && (
                  <div className="shrink-0 rounded-xl border border-white/10 bg-white/5">
                    <button
                      onClick={() => {
                        const next = !expanded;
                        setExpanded(next);
                        if (next && !expandedNotified.current) {
                          expandedNotified.current = true;
                          onDetailExpanded?.();
                        }
                      }}
                      className="flex w-full items-center gap-1.5 px-3 py-2 text-xs text-white/60 transition-colors hover:text-white/80"
                    >
                      <span>{expanded ? "▼" : "▶"}</span>
                      <span>展开补充说明</span>
                    </button>
                    {expanded && (
                      <div className="px-3 pb-3">
                        <p className="text-xs leading-relaxed text-white/75">{data.short_explanation}</p>
                      </div>
                    )}
                  </div>
                )}

                <div className="flex flex-col rounded-2xl border border-white/10 bg-white/5 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-semibold text-white/80">继续追问 AI</span>
                    <span className="text-[11px] text-white/40">会结合当前问题上下文回答</span>
                  </div>

                  <div className="flex max-h-40 flex-col gap-2 overflow-y-auto pr-1">
                    {messages.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-white/10 bg-black/10 px-3 py-3 text-xs leading-6 text-white/45">
                        可以追问更详细的解释、相关概念、或者如何用更简单的语言说明。
                      </div>
                    ) : (
                      messages.map((message, index) => (
                        <div
                          key={`${message.role}-${index}`}
                          className={`rounded-2xl px-3 py-2 text-xs leading-6 ${
                            message.role === "user"
                              ? "self-end bg-cyan-500/16 text-cyan-50"
                              : "self-start border border-white/10 bg-white/7 text-white/88"
                          }`}
                        >
                          {message.content}
                        </div>
                      ))
                    )}
                    {asking && (
                      <div className="self-start rounded-2xl border border-white/10 bg-white/7 px-3 py-2 text-xs text-white/55">
                        正在思考中...
                      </div>
                    )}
                  </div>

                  <div className="mt-2 flex items-stretch gap-2">
                    <textarea
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      placeholder="比如：能用更简单的方式解释吗？"
                      className="h-12 flex-1 resize-none rounded-2xl border border-white/10 bg-black/15 px-3 py-2 text-xs text-white outline-none transition focus:border-cyan-400/50"
                    />
                    <button
                      onClick={handleAsk}
                      disabled={!canAsk}
                      className="h-12 rounded-2xl border border-cyan-400/20 bg-cyan-500/16 px-4 text-xs font-medium text-cyan-100 transition hover:bg-cyan-500/24 disabled:opacity-50"
                    >
                      追问
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="mt-3 flex shrink-0 justify-center border-t border-white/10 bg-[rgba(3,10,20,0.92)] pt-3">
            <button
              onClick={onClose}
              className="rounded-lg bg-white/10 px-4 py-1.5 text-xs text-white/60 transition-all duration-150 hover:bg-white/20 hover:text-white"
            >
              收起面板
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
