/**
 * 课堂状态面板（教师版）
 * =======================
 * 帮助老师快速了解当前课堂进展，支持追问
 */

import { useEffect, useMemo, useState } from "react";
import { getClassStatus, statusChat } from "../services/api";
import { PANEL_WINDOW_SIZES } from "../services/windowSizing";

interface ClassStatusPanelProps {
  visible: boolean;
  onClose: () => void;
}

export default function ClassStatusPanel({ visible, onClose }: ClassStatusPanelProps) {
  const [summary, setSummary] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Array<{ role: "user" | "assistant"; content: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canAsk = useMemo(() => Boolean(summary && question.trim() && !asking), [summary, question, asking]);

  useEffect(() => {
    if (!visible) return;

    setLoading(true);
    setError(null);
    setSummary(null);
    setQuestion("");
    setMessages([]);

    getClassStatus()
      .then((res) => setSummary(res.summary))
      .catch((err) => setError(err.message || "请求失败"))
      .finally(() => setLoading(false));
  }, [visible]);

  // 面板打开时调大窗口
  useEffect(() => {
    if (!visible) return;

    (async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const { LogicalSize } = await import("@tauri-apps/api/dpi");
        await getCurrentWindow().setSize(new LogicalSize(PANEL_WINDOW_SIZES.classStatus.width, PANEL_WINDOW_SIZES.classStatus.height));
      } catch {
        /* 忽略窗口操作错误 */
      }
    })();
  }, [visible]);

  if (!visible) return null;

  const handleAsk = async () => {
    if (!summary || !question.trim() || asking) return;

    const nextQuestion = question.trim();
    const nextHistory = [...messages, { role: "user" as const, content: nextQuestion }];
    setMessages(nextHistory);
    setQuestion("");
    setAsking(true);
    setError(null);

    try {
      const res = await statusChat({
        summary,
        question: nextQuestion,
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
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden p-3 animate-in fade-in duration-300">
      <div className="min-h-0 flex-1 overflow-y-auto pb-24 pr-1">
        {loading && (
          <div className="flex items-center justify-center py-8 text-white/60">
            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2" />
            <span className="text-sm">正在分析课堂状态...</span>
          </div>
        )}

        {error && (
          <div className="mb-3 p-3 rounded-xl bg-red-500/20 border border-red-500/30 text-red-300 text-xs">
            ⚠️ {error}
          </div>
        )}

        {summary && !loading && (
          <div className="flex flex-col gap-3">
            <div className="shrink-0 rounded-xl border border-teal-500/20 bg-teal-500/10 p-3">
              <div className="flex items-center gap-1.5 mb-2">
                <span className="text-sm">📊</span>
                <span className="text-xs font-semibold text-teal-300">当前课堂状态</span>
              </div>
              <p className="text-xs text-white/85 leading-relaxed whitespace-pre-wrap">{summary}</p>
            </div>

            <div className="rounded-2xl border border-white/10 bg-white/5 p-3 flex flex-col">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-semibold text-white/80">继续追问 AI</span>
                <span className="text-[11px] text-white/40">会结合当前课堂上下文回答</span>
              </div>

              <div className="max-h-40 flex flex-col gap-2 overflow-y-auto pr-1">
                {messages.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-white/10 bg-black/10 px-3 py-4 text-xs leading-6 text-white/45">
                    可以问课堂节奏、学生理解情况、或者下一步教学建议。
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
                    正在结合当前上下文回答...
                  </div>
                )}
              </div>

              <div className="mt-2 flex items-stretch gap-2">
                <textarea
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="比如：学生对哪个知识点还不够清楚？"
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

      <div className="absolute bottom-12 left-3 right-3 flex justify-center border-t border-white/10 bg-[rgba(3,10,20,0.92)] pt-3">
        <button
          onClick={onClose}
          className="px-4 py-1.5 text-xs rounded-lg
                     bg-white/10 text-white/60
                     hover:bg-white/20 hover:text-white
                     transition-all duration-150"
        >
          收起面板
        </button>
      </div>
    </div>
  );
}
