/**
 * 旧救场面板占位组件（legacy）
 * =============================
 * 当前教师版主链路已经切到 `FallbackPanel`，这里仅保留迁移占位，
 * 避免再把新需求叠加到旧 `RescuePanel` 语义上。
 */

import { useEffect } from "react";
import { PANEL_WINDOW_SIZES } from "../services/windowSizing";

interface RescuePanelProps {
  /** 面板是否可见 */
  visible: boolean;
  /** 关闭面板 */
  onClose: () => void;
}

export default function RescuePanel({ visible, onClose }: RescuePanelProps) {
  useEffect(() => {
    if (!visible) return;

    void (async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const { LogicalSize } = await import("@tauri-apps/api/dpi");
        await getCurrentWindow().setSize(new LogicalSize(PANEL_WINDOW_SIZES.rescue.width, PANEL_WINDOW_SIZES.rescue.height));
      } catch {
        /* 忽略窗口操作错误 */
      }
    })();
  }, [visible]);

  if (!visible) return null;

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden p-3 animate-in fade-in duration-300">
      <div className="min-h-0 flex-1 overflow-y-auto pb-24 pr-1">
        <div className="rounded-2xl border border-amber-400/20 bg-amber-500/10 p-4">
          <div className="flex items-center gap-2">
            <span className="text-sm">🧭</span>
            <span className="text-xs font-semibold text-amber-100">旧 RescuePanel 已退出主链路</span>
          </div>
          <p className="mt-3 text-xs leading-6 text-white/78">
            当前教师版只保留一套“兜底答案”语义，新功能请统一接入 <code>FallbackPanel</code> 和
            <code>question_router.py</code>。
          </p>
          <div className="mt-3 rounded-xl border border-white/10 bg-black/15 px-3 py-3 text-xs leading-6 text-white/60">
            保留这个组件的目的只有两个：兼容历史迁移映射，以及提醒后续开发不要再向旧救场面板继续加功能。
          </div>
        </div>
      </div>

      <div className="absolute bottom-12 left-3 right-3 flex justify-center border-t border-white/10 bg-[rgba(3,10,20,0.92)] pt-3">
        <button
          onClick={onClose}
          className="rounded-lg bg-white/10 px-4 py-1.5 text-xs text-white/60 transition-all duration-150 hover:bg-white/20 hover:text-white"
        >
          收起面板
        </button>
      </div>
    </div>
  );
}
