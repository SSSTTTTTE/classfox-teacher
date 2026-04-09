/**
 * 标题栏组件
 * ==========
 * 无边框窗口的自定义拖拽标题栏
 */

import { useState } from "react";

interface TitleBarProps {
  /** 是否正在监控中 */
  isMonitoring: boolean;
  /** 是否暂停中 */
  isPaused: boolean;
  /** 当前课程名称 */
  courseName: string;
}

export default function TitleBar({ isMonitoring, isPaused, courseName }: TitleBarProps) {
  const [isHovered, setIsHovered] = useState(false);

  /** 关闭窗口 */
  const handleClose = async () => {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    getCurrentWindow().close();
  };

  /** 最小化窗口 */
  const handleMinimize = async () => {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    getCurrentWindow().minimize();
  };

  return (
    <div
      data-tauri-drag-region
      className="flex items-center justify-between h-10 px-3 select-none cursor-move"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* 左侧标题 - 也作为拖拽区域 */}
      <div data-tauri-drag-region className="flex items-center gap-1.5 text-xs text-white/80 pointer-events-none">
        <span className="text-sm">🦊</span>
        <span className="font-medium tracking-wide">课狐助教 ClassFox</span>
        {isMonitoring && (
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${isPaused ? "bg-amber-300" : "bg-green-400 animate-pulse"}`} />
        )}
        {courseName && <span className="max-w-40 truncate text-[11px] text-white/45">{courseName}</span>}
      </div>

      {/* 右侧窗口控制按钮 - 悬浮时显示 */}
      <div
        className={`flex gap-1 transition-opacity duration-200 ${
          isHovered ? "opacity-100" : "opacity-0"
        }`}
      >
        <button
          onClick={handleMinimize}
          className="w-5 h-5 rounded-full bg-yellow-500/60 hover:bg-yellow-500 
                     flex items-center justify-center text-[10px] text-white/80 
                     transition-colors duration-150"
          title="最小化"
        >
          −
        </button>
        <button
          onClick={handleClose}
          className="w-5 h-5 rounded-full bg-red-500/60 hover:bg-red-500 
                     flex items-center justify-center text-[10px] text-white/80 
                     transition-colors duration-150"
          title="关闭"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
