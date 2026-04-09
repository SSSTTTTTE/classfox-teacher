/**
 * 警报覆盖层组件
 * ===============
 * 点名触发时，整个悬浮窗闪烁红光并显示「救场」按钮
 */

import { useEffect, useState } from "react";
import { MAIN_WINDOW_SIZE, PANEL_WINDOW_SIZES } from "../services/windowSizing";

interface AlertOverlayProps {
  /** 是否激活警报 */
  active: boolean;
  /** 警报等级 */
  level: "danger" | "warning";
  /** 触发警报的关键词 */
  keywords: string[];
  /** 触发的原文 */
  text: string;
  /** 点击救场按钮 */
  onRescue: () => void;
  /** 点击课堂进度 */
  onCatchup: () => void;
  /** 点击忽略/关闭 */
  onDismiss: () => void;
}

export default function AlertOverlay({
  active,
  level,
  keywords,
  text,
  onRescue,
  onCatchup,
  onDismiss,
}: AlertOverlayProps) {
  const [flash, setFlash] = useState(false);

  const restoreCompactSize = async () => {
    try {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      const { LogicalSize } = await import("@tauri-apps/api/dpi");
      await getCurrentWindow().setSize(new LogicalSize(MAIN_WINDOW_SIZE.width, MAIN_WINDOW_SIZE.idleHeight));
    } catch (e) {
      console.error("窗口恢复失败:", e);
    }
  };

  // 闪烁效果
  useEffect(() => {
    if (!active) return;

    const interval = setInterval(() => {
      setFlash((prev) => !prev);
    }, 500);

    return () => clearInterval(interval);
  }, [active]);

  // 窗口激活到前台（当检测到点名时）
  useEffect(() => {
    if (active) {
      (async () => {
        try {
          const { getCurrentWindow } = await import("@tauri-apps/api/window");
          const win = getCurrentWindow();
          await win.setFocus();
          await win.setSize(
            new (await import("@tauri-apps/api/dpi")).LogicalSize(
              PANEL_WINDOW_SIZES.alert.width,
              PANEL_WINDOW_SIZES.alert.height
            )
          );
        } catch (e) {
          console.error("窗口操作失败:", e);
        }
      })();
    }
  }, [active]);

  if (!active) return null;

  const isDanger = level === "danger";

  return (
    <div
      className={`absolute inset-0 z-50 flex flex-col items-center justify-center
                  rounded-2xl transition-all duration-300
                  ${
                    isDanger
                      ? flash
                        ? "bg-red-600/40"
                        : "bg-red-900/30"
                      : flash
                        ? "bg-amber-500/35"
                        : "bg-yellow-800/25"
                  }
                  border-2 ${
                    isDanger
                      ? flash
                        ? "border-red-400"
                        : "border-red-600/50"
                      : flash
                        ? "border-amber-300"
                        : "border-yellow-500/50"
                  }
                  backdrop-blur-md`}
    >
      {/* 警报标题 */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-2xl animate-bounce">{isDanger ? "🚨" : "⚠️"}</span>
        <span className={`text-lg font-bold ${isDanger ? "text-red-200" : "text-yellow-100"}`}>
          {isDanger ? "检测到红色提醒!" : "检测到黄色提醒"}
        </span>
        <span className="text-2xl animate-bounce">{isDanger ? "🚨" : "⚠️"}</span>
      </div>

      {/* 触发信息 */}
      <div className={`mb-1 text-xs ${isDanger ? "text-red-200/80" : "text-yellow-100/85"}`}>
        关键词: {keywords.join(", ")}
      </div>
      <div className={`mb-3 px-4 text-center text-xs line-clamp-2 ${isDanger ? "text-red-200/60" : "text-yellow-100/70"}`}>
        "{text}"
      </div>

      {/* 操作按钮 */}
      <div className="flex gap-3">
        {isDanger ? (
          <button
            onClick={onRescue}
            className="px-6 py-2 text-sm font-bold rounded-xl
                       bg-red-500 text-white shadow-lg shadow-red-500/50
                       hover:bg-red-400 hover:scale-105
                       active:scale-95 transition-all duration-150
                       animate-pulse"
          >
            🆘 救场!
          </button>
        ) : (
          <button
            onClick={onCatchup}
            className="rounded-xl bg-yellow-300/90 px-5 py-2 text-sm font-semibold text-slate-900 transition hover:bg-yellow-200"
          >
            📍 看看进度
          </button>
        )}
        <button
          onClick={async () => {
            await restoreCompactSize();
            onDismiss();
          }}
          className="px-4 py-2 text-xs rounded-xl
                     bg-white/10 text-white/60
                     hover:bg-white/20 hover:text-white/80
                     transition-all duration-150"
        >
          忽略
        </button>
      </div>
    </div>
  );
}
