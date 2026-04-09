import { useEffect, useState } from "react";
import { getMaterials } from "../services/api";
import { PANEL_WINDOW_SIZES } from "../services/windowSizing";
const LAST_SUBJECT_KEY = "classfox-teacher-last-subject";
const LAST_COURSE_NAME_KEY = "classfox-teacher-last-course-name";
const LAST_MATERIAL_FILENAME_KEY = "classfox-teacher-last-material-filename";

interface StartMonitorPanelProps {
  visible: boolean;
  onClose: () => void;
  onConfirm: (payload: { subject: string; courseName: string; materialFilename: string | null }) => Promise<void>;
  refreshToken: number;
}

export default function StartMonitorPanel({
  visible,
  onClose,
  onConfirm,
  refreshToken,
}: StartMonitorPanelProps) {
  const [subject, setSubject] = useState("");
  const [courseName, setCourseName] = useState("");
  const [materialFilename, setMaterialFilename] = useState("");
  const [items, setItems] = useState<Array<{ filename: string; updated_at: string; size: number }>>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;

    setLoading(true);
    setError(null);
    const rememberedSubject = window.localStorage.getItem(LAST_SUBJECT_KEY) || "";
    const rememberedCourseName = window.localStorage.getItem(LAST_COURSE_NAME_KEY) || "";
    const rememberedMaterial = window.localStorage.getItem(LAST_MATERIAL_FILENAME_KEY) || "";
    setSubject(rememberedSubject);
    setCourseName(rememberedCourseName);
    setMaterialFilename(rememberedMaterial);
    getMaterials()
      .then((res) => {
        setItems(res.items);
        if (rememberedMaterial && !res.items.some((item) => item.filename === rememberedMaterial)) {
          setMaterialFilename("");
        }
      })
      .catch((err) => setError(err.message || "获取资料列表失败"))
      .finally(() => setLoading(false));
  }, [visible, refreshToken]);

  useEffect(() => {
    if (!visible) return;

    (async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const { LogicalSize } = await import("@tauri-apps/api/dpi");
        const win = getCurrentWindow();
        await win.setSize(new LogicalSize(PANEL_WINDOW_SIZES.startMonitor.width, PANEL_WINDOW_SIZES.startMonitor.height));
      } catch {
        /* 忽略窗口操作错误 */
      }
    })();
  }, [visible]);

  if (!visible) return null;

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      window.localStorage.setItem(LAST_SUBJECT_KEY, subject.trim());
      window.localStorage.setItem(LAST_COURSE_NAME_KEY, courseName.trim());
      window.localStorage.setItem(LAST_MATERIAL_FILENAME_KEY, materialFilename || "");
      await onConfirm({
        subject: subject.trim(),
        courseName: courseName.trim(),
        materialFilename: materialFilename || null,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "启动失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 p-4 animate-in fade-in duration-300 text-white/85">
      <div>
        <h2 className="text-sm font-semibold text-white">准备开始监听哪门课？</h2>
        <p className="mt-1 text-xs text-white/55">填写科目、课程名并选择可选的参考资料，开始后会先检查 Ollama、预热课堂短答模型，再进入实时监听。</p>
        <p className="mt-1 text-[11px] text-white/40">会自动记住你上次使用的科目、课程名和资料选择。</p>
      </div>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-white/65">科目</span>
        <input
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="例如：数学 / 物理 / 英语"
          className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none transition focus:border-cyan-400/50 focus:bg-white/8"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-white/65">课程名称</span>
        <input
          value={courseName}
          onChange={(e) => setCourseName(e.target.value)}
          placeholder="例如：机器学习 / 计算机视觉"
          className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none transition focus:border-cyan-400/50 focus:bg-white/8"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-white/65">参考资料（可选）</span>
        <select
          value={materialFilename}
          onChange={(e) => setMaterialFilename(e.target.value)}
          className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none transition focus:border-cyan-400/50"
        >
          <option value="">不选择资料</option>
          {items.map((item) => (
            <option key={item.filename} value={item.filename}>
              {item.filename}
            </option>
          ))}
        </select>
      </label>

      <div className="min-h-5 text-xs text-white/45">
        {loading ? "正在读取参考资料列表..." : null}
        {!loading && items.length > 0 ? `已发现 ${items.length} 份参考资料` : null}
      </div>

      {error && <div className="rounded-xl border border-red-500/30 bg-red-500/15 px-3 py-2 text-xs text-red-200">⚠️ {error}</div>}

      <div className="mt-1 flex items-center justify-end gap-2">
        <button
          onClick={onClose}
          disabled={submitting}
          className="rounded-lg bg-white/8 px-4 py-2 text-xs text-white/70 transition hover:bg-white/14 hover:text-white disabled:opacity-50"
        >
          取消
        </button>
        <button
          onClick={handleSubmit}
          disabled={submitting}
          className="rounded-lg bg-green-500/20 px-4 py-2 text-xs font-medium text-green-200 transition hover:bg-green-500/30 disabled:opacity-50"
        >
          {submitting ? "初始化课堂..." : "开始监听"}
        </button>
      </div>
    </div>
  );
}
