/**
 * 学生提问卡片组件（教师版）
 * ============================
 * 检测到学生提问时，在角落显示安静的通知卡片，不打断老师讲课
 */

import { useEffect, useMemo, useState } from "react";

interface QuestionCardProps {
  /** 是否激活 */
  active: boolean;
  /** 触发的原文 */
  text: string;
  /** 点击查看兜底答案 */
  onViewAnswer: () => void;
  /** 点击关闭 */
  onDismiss: () => void;
}

export default function QuestionCard({
  active,
  text,
  onViewAnswer,
  onDismiss,
}: QuestionCardProps) {
  if (!active) return null;

  const countdownMs = 5000;
  const [remainingMs, setRemainingMs] = useState(countdownMs);

  useEffect(() => {
    if (!active) return;

    const startedAt = Date.now();
    setRemainingMs(countdownMs);

    const intervalId = window.setInterval(() => {
      const nextRemaining = Math.max(countdownMs - (Date.now() - startedAt), 0);
      setRemainingMs(nextRemaining);
      if (nextRemaining <= 0) {
        window.clearInterval(intervalId);
        onDismiss();
      }
    }, 100);

    return () => window.clearInterval(intervalId);
  }, [active, text, onDismiss]);

  const progress = useMemo(() => remainingMs / countdownMs, [remainingMs]);
  const countdownSeconds = useMemo(() => Math.max(1, Math.ceil(remainingMs / 1000)), [remainingMs]);
  const ringRadius = 16;
  const ringCircumference = 2 * Math.PI * ringRadius;
  const ringOffset = ringCircumference * (1 - progress);

  return (
    <div
      className="absolute inset-0 z-50 flex flex-col items-start justify-end p-3
                  pointer-events-none"
    >
      <div
        className="pointer-events-auto w-full rounded-xl
                    bg-indigo-900/70 border border-indigo-400/30
                    backdrop-blur-md shadow-lg
                    animate-in slide-in-from-bottom-2 duration-200"
      >
        {/* 标题行 */}
        <div className="flex items-center gap-2 px-3 pt-2.5 pb-1">
          <span className="text-base">💬</span>
          <span className="text-xs font-semibold text-indigo-200">
            检测到学生提问
          </span>
          <button
            onClick={onDismiss}
            aria-label={`关闭提问卡片，剩余 ${countdownSeconds} 秒`}
            title={`剩余 ${countdownSeconds} 秒`}
            className="ml-auto relative inline-flex h-10 w-10 items-center justify-center rounded-full text-[10px] font-semibold text-white/70 transition-colors hover:text-white"
          >
            <svg
              className="-rotate-90 absolute inset-0 h-full w-full"
              viewBox="0 0 40 40"
              aria-hidden="true"
            >
              <circle
                cx="20"
                cy="20"
                r={ringRadius}
                fill="none"
                stroke="rgba(255,255,255,0.14)"
                strokeWidth="2.5"
              />
              <circle
                cx="20"
                cy="20"
                r={ringRadius}
                fill="none"
                stroke="rgba(165,180,252,0.95)"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeDasharray={ringCircumference}
                strokeDashoffset={ringOffset}
              />
            </svg>
            <span className="relative z-10">关闭</span>
          </button>
        </div>

        {/* 提问原文 */}
        <div className="px-3 pb-1">
          <p className="text-xs text-white/70 line-clamp-2 leading-relaxed">
            "{text}"
          </p>
        </div>

        {/* 操作按钮 */}
        <div className="px-3 pb-2.5 pt-1">
          <button
            onClick={onViewAnswer}
            className="w-full py-1.5 text-xs font-semibold rounded-lg
                       bg-indigo-500/60 text-indigo-100
                       hover:bg-indigo-500/80 hover:text-white
                       transition-all duration-150"
          >
            查看兜底答案
          </button>
        </div>
      </div>
    </div>
  );
}
