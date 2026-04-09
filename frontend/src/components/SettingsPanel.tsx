import { useEffect, useMemo, useState } from "react";
import {
  getLocalLLMHealth,
  getLocalLLMStatus,
  getSettings,
  restartBackend,
  saveSettings,
  validateSeedAsr,
  warmupLocalLLM,
  type LocalLLMStatus,
} from "../services/api";
import {
  DEFAULT_UI_STYLE_SETTINGS,
  applyUiStyleSettings,
  readUiStyleSettings,
  saveUiStyleSettings,
  type UiStyleSettings,
} from "../services/preferences";
import { PANEL_WINDOW_SIZES } from "../services/windowSizing";

type EnvFieldConfig = {
  key: string;
  label: string;
  placeholder?: string;
  type?: "text" | "password" | "number" | "select";
  options?: Array<{ label: string; value: string }>;
};

type EnvSectionConfig = {
  title: string;
  description?: string;
  fields: EnvFieldConfig[];
};

const ENV_SECTIONS: EnvSectionConfig[] = [
  {
    title: "服务与识别",
    description: "保留当前后端端口和 ASR 入口；开始课堂前会先检查并预热本地短答模型。",
    fields: [
      {
        key: "ASR_MODE",
        label: "ASR 模式",
        type: "select",
        options: [
          { label: "本地识别 local", value: "local" },
          { label: "Mock 测试", value: "mock" },
          { label: "DashScope", value: "dashscope" },
          { label: "Seed-ASR", value: "seed-asr" },
        ],
      },
      { key: "API_PORT", label: "后端端口", type: "number", placeholder: "8765" },
    ],
  },
  {
    title: "本地 Ollama",
    description: "v1.1.1 主链路默认使用本地 Ollama：短答走 qwen2.5:1.5b，课后总结走 gemma4:e4b，实时总结默认关闭。",
    fields: [
      { key: "OLLAMA_BASE_URL", label: "Ollama 地址", placeholder: "http://127.0.0.1:11434" },
      {
        key: "OLLAMA_CHAT_MODEL",
        label: "课堂短答模型",
        placeholder: "qwen2.5:1.5b",
        options: [
          { label: "Qwen 2.5 1.5B（默认）", value: "qwen2.5:1.5b" },
          { label: "Qwen 2.5 3B", value: "qwen2.5:3b" },
          { label: "Gemma 4 E4B", value: "gemma4:e4b" },
        ],
      },
      {
        key: "OLLAMA_FINAL_SUMMARY_MODEL",
        label: "课后总结模型",
        placeholder: "gemma4:e4b",
        options: [
          { label: "Gemma 4 E4B（默认）", value: "gemma4:e4b" },
          { label: "Qwen 2.5 1.5B", value: "qwen2.5:1.5b" },
          { label: "Qwen 2.5 3B", value: "qwen2.5:3b" },
        ],
      },
      { key: "OLLAMA_TIMEOUT", label: "请求超时（秒）", type: "number", placeholder: "45" },
      { key: "OLLAMA_MAX_TOKENS", label: "最大输出 Token", type: "number", placeholder: "1024" },
      { key: "OLLAMA_TEMPERATURE", label: "温度", type: "number", placeholder: "0.3" },
      {
        key: "OLLAMA_REALTIME_SUMMARY_ENABLED",
        label: "实时总结开关",
        type: "select",
        options: [
          { label: "关闭（默认）", value: "false" },
          { label: "开启", value: "true" },
        ],
      },
      {
        key: "OLLAMA_REALTIME_SUMMARY_MODEL",
        label: "实时总结模型（预留）",
        placeholder: "qwen2.5:1.5b",
        options: [
          { label: "Qwen 2.5 1.5B（默认）", value: "qwen2.5:1.5b" },
          { label: "Gemma 4 E4B", value: "gemma4:e4b" },
        ],
      },
    ],
  },
  {
    title: "历史兼容云端 LLM",
    description: "仅在排查旧 OpenAI Compatible 云端链路时填写；v1.1.1 默认不再要求老师先准备 API Key。",
    fields: [
      { key: "LLM_BASE_URL", label: "兼容接口 Base URL", placeholder: "例如 https://dashscope.aliyuncs.com/compatible-mode/v1" },
      { key: "LLM_API_KEY", label: "兼容接口 API Key", type: "password", placeholder: "仅旧链路调试需要时填写" },
      {
        key: "LLM_SUMMARY_MODEL",
        label: "历史兼容总结模型",
        placeholder: "qwen-plus / gpt-4o",
        type: "select",
        options: [
          { label: "通义千问 3.5 Flash 2026-02-23", value: "qwen3.5-flash-2026-02-23" },
          { label: "通义千问 3.5 Flash (qwen3.5-flash)", value: "qwen3.5-flash" },
          { label: "通义千问 Max (qwen-max)", value: "qwen-max" },
          { label: "通义千问 Plus (qwen-plus)", value: "qwen-plus" },
          { label: "通义千问 Turbo (qwen-turbo)", value: "qwen-turbo" },
          { label: "通义千问 Long (qwen-long)", value: "qwen-long" },
          { label: "GPT-4o", value: "gpt-4o" },
          { label: "GPT-4o-mini", value: "gpt-4o-mini" },
          { label: "Claude 3.5 Sonnet", value: "claude-3-5-sonnet-20240620" }
        ]
      },
      {
        key: "LLM_FALLBACK_MODEL",
        label: "历史兼容兜底模型",
        placeholder: "qwen-plus / gpt-4o",
        type: "select",
        options: [
          { label: "通义千问 3.5 Flash 2026-02-23", value: "qwen3.5-flash-2026-02-23" },
          { label: "通义千问 3.5 Flash (qwen3.5-flash)", value: "qwen3.5-flash" },
          { label: "通义千问 Max (qwen-max)", value: "qwen-max" },
          { label: "通义千问 Plus (qwen-plus)", value: "qwen-plus" },
          { label: "通义千问 Turbo (qwen-turbo)", value: "qwen-turbo" },
          { label: "通义千问 Long (qwen-long)", value: "qwen-long" },
          { label: "GPT-4o", value: "gpt-4o" },
          { label: "GPT-4o-mini", value: "gpt-4o-mini" },
          { label: "Claude 3.5 Sonnet", value: "claude-3-5-sonnet-20240620" }
        ]
      },
    ],
  },
  {
    title: "Seed-ASR",
    fields: [
      { key: "SEED_ASR_APP_KEY", label: "APP ID (X-Api-App-Key)", type: "password", placeholder: "火山引擎控制台 APP ID" },
      { key: "SEED_ASR_ACCESS_KEY", label: "Access Token (X-Api-Access-Key)", type: "password", placeholder: "火山引擎控制台 Access Token" },
      {
        key: "SEED_ASR_RESOURCE_ID",
        label: "Resource ID (X-Api-Resource-Id)",
        type: "select",
        options: [
          { label: "豆包 2.0 小时版 (volc.seedasr.sauc.duration)", value: "volc.seedasr.sauc.duration" },
          { label: "豆包 2.0 并发版 (volc.seedasr.sauc.concurrent)", value: "volc.seedasr.sauc.concurrent" },
          { label: "豆包 1.0 小时版 (volc.bigasr.sauc.duration)", value: "volc.bigasr.sauc.duration" },
          { label: "豆包 1.0 并发版 (volc.bigasr.sauc.concurrent)", value: "volc.bigasr.sauc.concurrent" },
        ],
      },
      {
        key: "SEED_ASR_WS_URL",
        label: "WebSocket 接口地址",
        type: "select",
        options: [
          { label: "双向流式优化版 bigmodel_async（推荐）", value: "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async" },
          { label: "双向流式 bigmodel", value: "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel" },
          { label: "流式输入 bigmodel_nostream（高准确率）", value: "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream" },
        ],
      },
    ],
  },
  {
    title: "音频与其他",
    fields: [
      { key: "DASHSCOPE_API_KEY", label: "DashScope API Key", type: "password" },
      { key: "AUDIO_SAMPLE_RATE", label: "采样率", type: "number", placeholder: "16000" },
      { key: "AUDIO_CHANNELS", label: "声道数", type: "number", placeholder: "1" },
      { key: "AUDIO_CHUNK_SIZE", label: "Chunk Size", type: "number", placeholder: "3200" },
    ],
  },
];

const ALL_ENV_KEYS = ENV_SECTIONS.flatMap((section) => section.fields.map((field) => field.key));

const DEFAULT_ENV_VALUES: Record<string, string> = {
  OLLAMA_BASE_URL: "http://127.0.0.1:11434",
  OLLAMA_CHAT_MODEL: "qwen2.5:1.5b",
  OLLAMA_FINAL_SUMMARY_MODEL: "gemma4:e4b",
  OLLAMA_TIMEOUT: "45",
  OLLAMA_MAX_TOKENS: "1024",
  OLLAMA_TEMPERATURE: "0.3",
  OLLAMA_REALTIME_SUMMARY_ENABLED: "false",
  OLLAMA_REALTIME_SUMMARY_MODEL: "qwen2.5:1.5b",
};

function createEmptyEnvValues() {
  return {
    ...Object.fromEntries(ALL_ENV_KEYS.map((key) => [key, ""])),
  } as Record<string, string>;
}

const SECTION_COMMENT_LINES = new Set([
  ...ENV_SECTIONS.map((s) => `# ${s.title}`),
  "# 其他原始配置",
]);

function parseEnvContent(content: string) {
  const values = createEmptyEnvValues();
  const extras: string[] = [];
  const legacyValues: Record<string, string> = {
    LLM_MODEL: "",
    LLM_SUMMARY_MODEL: "",
    LLM_FALLBACK_MODEL: "",
  };

  for (const line of content.split(/\r?\n/)) {
    if (!line.trim()) {
      extras.push(line);
      continue;
    }

    if (line.trimStart().startsWith("#")) {
      // Skip section-title comments to prevent accumulation on each save
      if (SECTION_COMMENT_LINES.has(line.trim())) continue;
      extras.push(line);
      continue;
    }

    const separatorIndex = line.indexOf("=");
    if (separatorIndex === -1) {
      extras.push(line);
      continue;
    }

    const key = line.slice(0, separatorIndex).trim();
    const value = line.slice(separatorIndex + 1);
    if (ALL_ENV_KEYS.includes(key)) {
      values[key] = value;
    } else if (key in legacyValues) {
      legacyValues[key] = value;
      extras.push(line);
    } else {
      extras.push(line);
    }
  }

  const legacyModel = legacyValues["LLM_MODEL"].trim();
  const legacyFallbackModel = legacyValues["LLM_FALLBACK_MODEL"].trim() || legacyModel;
  const legacySummaryModel = legacyValues["LLM_SUMMARY_MODEL"].trim() || legacyModel;

  if (!values["LLM_SUMMARY_MODEL"] && legacySummaryModel) values["LLM_SUMMARY_MODEL"] = legacySummaryModel;
  if (!values["LLM_FALLBACK_MODEL"] && legacyFallbackModel) values["LLM_FALLBACK_MODEL"] = legacyFallbackModel;

  for (const [key, defaultValue] of Object.entries(DEFAULT_ENV_VALUES)) {
    if (!values[key]) values[key] = defaultValue;
  }

  return { values, extraContent: extras.join("\n").trim() };
}

function buildEnvContent(values: Record<string, string>, extraContent: string) {
  const lines: string[] = [];
  for (const section of ENV_SECTIONS) {
    lines.push(`# ${section.title}`);
    for (const field of section.fields) {
      const value = values[field.key]?.trim();
      if (value) {
        lines.push(`${field.key}=${value}`);
      }
    }
    lines.push("");
  }

  const extra = extraContent.trim();
  if (extra) {
    lines.push("# 其他原始配置");
    lines.push(extra);
  }

  return `${lines.join("\n").trim()}\n`;
}

interface SettingsPanelProps {
  visible: boolean;
  onClose: () => void;
  onSaved: (message: string) => void;
}

export default function SettingsPanel({ visible, onClose, onSaved }: SettingsPanelProps) {
  const [envValues, setEnvValues] = useState<Record<string, string>>(createEmptyEnvValues);
  const [extraContent, setExtraContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validateResult, setValidateResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [path, setPath] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [styleSettings, setStyleSettings] = useState<UiStyleSettings>(DEFAULT_UI_STYLE_SETTINGS);
  const [localLLMStatus, setLocalLLMStatus] = useState<LocalLLMStatus | null>(null);
  const [localLLMLoading, setLocalLLMLoading] = useState(false);
  const [localLLMActionLoading, setLocalLLMActionLoading] = useState<"health" | "status" | "warmup" | null>(null);
  const [localLLMMessage, setLocalLLMMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const styleSummary = useMemo(
    () => `${styleSettings.backgroundPreset} / 圆角 ${styleSettings.windowRadius}px / 透明度 ${Math.round(styleSettings.shellOpacity * 100)}%`,
    [styleSettings]
  );

  const localLLMReadyLabel = useMemo(() => {
    if (!localLLMStatus) return "未读取";
    if (!localLLMStatus.online) return "离线";
    if (localLLMStatus.warmup_state === "warming") return "预热中";
    if (localLLMStatus.is_warmed || localLLMStatus.warmup_state === "ready") return "已就绪";
    if (!localLLMStatus.chat_model_available) return "模型缺失";
    return "待预热";
  }, [localLLMStatus]);

  useEffect(() => {
    if (!visible) return;

    setLoading(true);
    setError(null);
    setLocalLLMMessage(null);
    setStyleSettings(readUiStyleSettings());
    getSettings()
      .then((res) => {
        const parsed = parseEnvContent(res.content);
        setEnvValues(parsed.values);
        setExtraContent(parsed.extraContent);
        setPath(res.path);
      })
      .catch((err) => setError(err.message || "读取设置失败"))
      .finally(() => setLoading(false));
  }, [visible]);

  useEffect(() => {
    if (!visible) return;

    let disposed = false;
    setLocalLLMLoading(true);
    getLocalLLMHealth()
      .then((status) => {
        if (!disposed) setLocalLLMStatus(status);
      })
      .catch((err) => {
        if (!disposed) {
          setLocalLLMMessage({ ok: false, text: err instanceof Error ? err.message : "读取本地模型状态失败" });
        }
      })
      .finally(() => {
        if (!disposed) setLocalLLMLoading(false);
      });

    return () => {
      disposed = true;
    };
  }, [visible]);

  useEffect(() => {
    if (!visible) return;

    (async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const { LogicalSize } = await import("@tauri-apps/api/dpi");
        const win = getCurrentWindow();
        await win.setSize(new LogicalSize(PANEL_WINDOW_SIZES.settings.width, PANEL_WINDOW_SIZES.settings.height));
      } catch {
        /* 忽略窗口操作错误 */
      }
    })();
  }, [visible]);

  if (!visible) return null;

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await saveSettings(buildEnvContent(envValues, extraContent));
      saveUiStyleSettings(styleSettings);
      applyUiStyleSettings(styleSettings);
      // Trigger backend reload so new .env values take effect
      try { await restartBackend(); } catch { /* non-critical */ }
      onSaved(res.message);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleValidateSeedAsr = async () => {
    setValidating(true);
    setValidateResult(null);
    setError(null);
    try {
      const res = await validateSeedAsr({
        app_key: envValues["SEED_ASR_APP_KEY"] || "",
        access_key: envValues["SEED_ASR_ACCESS_KEY"] || "",
        resource_id: envValues["SEED_ASR_RESOURCE_ID"] || "",
        ws_url: envValues["SEED_ASR_WS_URL"] || "",
      });
      setValidateResult({ ok: true, msg: res.message });
    } catch (err) {
      setValidateResult({ ok: false, msg: err instanceof Error ? err.message : "验证失败" });
    } finally {
      setValidating(false);
    }
  };

  const handleFieldChange = (key: string, value: string) => {
    setEnvValues((prev) => ({ ...prev, [key]: value }));
  };

  const handleLocalLLMAction = async (action: "health" | "status" | "warmup") => {
    setLocalLLMActionLoading(action);
    setLocalLLMMessage(null);
    try {
      const status =
        action === "health"
          ? await getLocalLLMHealth()
          : action === "status"
            ? await getLocalLLMStatus()
            : await warmupLocalLLM();
      setLocalLLMStatus(status);
      setLocalLLMMessage({
        ok: true,
        text:
          action === "health"
            ? (status.online ? "已完成本地模型检查" : "已刷新状态，当前 Ollama 仍离线")
            : action === "status"
              ? "已重读当前本地模型状态"
              : `已重新预热 ${status.chat_model}`,
      });
    } catch (err) {
      setLocalLLMMessage({ ok: false, text: err instanceof Error ? err.message : "本地模型操作失败" });
    } finally {
      setLocalLLMActionLoading(null);
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden p-4 text-white/85 animate-in fade-in duration-300">
      <div className="flex items-center justify-between border-b border-white/10 pb-2 mb-2">
        <h2 className="text-sm font-semibold text-white">系统设置</h2>
        {path && <p className="text-[10px] text-white/35 truncate max-w-[200px]">{path}</p>}
      </div>

      <div className="flex-1 min-h-0 overflow-hidden flex flex-col relative">
        {loading ? (
          <div className="flex flex-1 items-center justify-center py-10 text-sm text-white/55">正在读取设置...</div>
        ) : (
          <div className="flex-1 space-y-3 overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/10 pb-24">
            <section className="rounded-[var(--window-radius)] border border-cyan-400/15 bg-cyan-500/[0.08] p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] ${
                      !localLLMStatus?.online
                        ? "border-red-400/25 bg-red-500/12 text-red-100"
                        : localLLMReadyLabel === "已就绪"
                          ? "border-emerald-400/25 bg-emerald-500/12 text-emerald-100"
                          : "border-amber-400/25 bg-amber-500/12 text-amber-100"
                    }`}>
                      本地模型 {localLLMReadyLabel}
                    </span>
                    <span className="rounded-full border border-white/10 bg-black/15 px-2 py-0.5 text-[10px] text-white/72">
                      短答 {localLLMStatus?.chat_model || envValues["OLLAMA_CHAT_MODEL"] || "qwen2.5:1.5b"}
                    </span>
                    <span className="rounded-full border border-white/10 bg-black/15 px-2 py-0.5 text-[10px] text-white/72">
                      总结 {localLLMStatus?.final_summary_model || envValues["OLLAMA_FINAL_SUMMARY_MODEL"] || "gemma4:e4b"}
                    </span>
                    <span className="rounded-full border border-white/10 bg-black/15 px-2 py-0.5 text-[10px] text-white/72">
                      实时总结 {envValues["OLLAMA_REALTIME_SUMMARY_ENABLED"] === "true" ? "开启" : "关闭"}
                    </span>
                  </div>
                  <p className="text-[10px] leading-4 text-white/48">
                    {localLLMStatus?.base_url
                      ? `Ollama 地址：${localLLMStatus.base_url}`
                      : "优先确认 Ollama 在线，再决定是否保存配置并重启后端。"}
                  </p>
                  {localLLMStatus && (
                    <p className="text-[10px] leading-4 text-white/38">
                      可用模型 {localLLMStatus.available_models.length || 0} 个
                      {localLLMStatus.missing_models.length > 0 ? ` · 缺少 ${localLLMStatus.missing_models.join(" / ")}` : ""}
                      {localLLMStatus.last_checked_at ? ` · 最近检查 ${localLLMStatus.last_checked_at}` : ""}
                      {localLLMStatus.last_warmed_at ? ` · 最近预热 ${localLLMStatus.last_warmed_at}` : ""}
                    </p>
                  )}
                </div>

                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => void handleLocalLLMAction("health")}
                    disabled={localLLMLoading || saving || localLLMActionLoading !== null}
                    className="rounded-lg bg-white/8 px-3 py-1 text-xs text-white/75 transition hover:bg-white/14 hover:text-white disabled:opacity-50"
                  >
                    {localLLMActionLoading === "health" ? "检查中..." : "检查 / 重连"}
                  </button>
                  <button
                    onClick={() => void handleLocalLLMAction("warmup")}
                    disabled={localLLMLoading || saving || localLLMActionLoading !== null}
                    className="rounded-lg bg-cyan-500/14 px-3 py-1 text-xs text-cyan-100 transition hover:bg-cyan-500/22 disabled:opacity-50"
                  >
                    {localLLMActionLoading === "warmup" ? "预热中..." : "预热短答模型"}
                  </button>
                  <button
                    onClick={() => void handleLocalLLMAction("status")}
                    disabled={localLLMLoading || saving || localLLMActionLoading !== null}
                    className="rounded-lg bg-white/8 px-3 py-1 text-xs text-white/70 transition hover:bg-white/14 hover:text-white disabled:opacity-50"
                  >
                    {localLLMActionLoading === "status" ? "读取中..." : "重读状态"}
                  </button>
                </div>
              </div>

              {localLLMLoading && <p className="mt-2 text-[10px] text-white/45">正在读取本地模型运行状态...</p>}
              {localLLMStatus?.last_error && (
                <p className="mt-2 text-[10px] text-red-200">⚠️ {localLLMStatus.last_error}</p>
              )}
              {localLLMMessage && (
                <p className={`mt-2 text-[10px] ${localLLMMessage.ok ? "text-emerald-200" : "text-red-200"}`}>
                  {localLLMMessage.ok ? "✓ " : "✗ "}
                  {localLLMMessage.text}
                </p>
              )}
            </section>

            {ENV_SECTIONS.map((section) => (
              section.title === "历史兼容云端 LLM" ? (
                <details key={section.title} className="rounded-[var(--window-radius)] border border-white/10 bg-white/6 p-3">
                  <summary className="cursor-pointer list-none">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <h3 className="text-[11px] font-semibold text-white/90">{section.title}</h3>
                        {section.description && <p className="mt-1 text-[10px] leading-4 text-white/45">{section.description}</p>}
                      </div>
                      <span className="rounded-full border border-white/10 bg-black/15 px-2 py-0.5 text-[10px] text-white/55">
                        默认隐藏
                      </span>
                    </div>
                  </summary>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    {section.fields.map((field) => (
                      <label key={field.key} className="flex flex-col gap-1">
                        <span className="text-[10px] text-white/58">{field.label}</span>
                        {field.type === "select" ? (
                          <select
                            value={envValues[field.key] || ""}
                            onChange={(e) => handleFieldChange(field.key, e.target.value)}
                            className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white outline-none transition focus:border-cyan-400/50"
                          >
                            <option value="">请选择</option>
                            {field.options?.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <div className="relative flex flex-col">
                            <input
                              list={field.options ? `${field.key}-options` : undefined}
                              type={field.type ?? "text"}
                              value={envValues[field.key] || ""}
                              onChange={(e) => handleFieldChange(field.key, e.target.value)}
                              placeholder={field.placeholder}
                              className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white outline-none transition focus:border-cyan-400/50 focus:bg-white/8 w-full"
                            />
                            {field.options && (
                              <datalist id={`${field.key}-options`}>
                                {field.options.map((option) => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </datalist>
                            )}
                          </div>
                        )}
                      </label>
                    ))}
                  </div>
                </details>
              ) : (
                <section key={section.title} className="rounded-[var(--window-radius)] border border-white/10 bg-white/6 p-3">
                  <h3 className="mb-1 text-[11px] font-semibold text-white/90">{section.title}</h3>
                  {section.description && <p className="mb-2 text-[10px] leading-4 text-white/45">{section.description}</p>}
                  <div className="grid gap-3 md:grid-cols-2">
                    {section.fields.map((field) => (
                      <label key={field.key} className="flex flex-col gap-1">
                        <span className="text-[10px] text-white/58">{field.label}</span>
                        {field.type === "select" ? (
                          <select
                            value={envValues[field.key] || ""}
                            onChange={(e) => handleFieldChange(field.key, e.target.value)}
                            className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white outline-none transition focus:border-cyan-400/50"
                          >
                            <option value="">请选择</option>
                            {field.options?.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <div className="relative flex flex-col">
                            <input
                              list={field.options ? `${field.key}-options` : undefined}
                              type={field.type ?? "text"}
                              value={envValues[field.key] || ""}
                              onChange={(e) => handleFieldChange(field.key, e.target.value)}
                              placeholder={field.placeholder}
                              className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white outline-none transition focus:border-cyan-400/50 focus:bg-white/8 w-full"
                            />
                            {field.options && (
                              <datalist id={`${field.key}-options`}>
                                {field.options.map((option) => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </datalist>
                            )}
                          </div>
                        )}
                      </label>
                    ))}
                  </div>
                  {section.title === "Seed-ASR" && (
                    <div className="mt-3 flex flex-col gap-1.5">
                      <button
                        onClick={handleValidateSeedAsr}
                        disabled={validating || saving}
                        className="self-start rounded-lg bg-white/8 px-3 py-1 text-xs text-white/70 transition hover:bg-white/14 hover:text-white disabled:opacity-50"
                      >
                        {validating ? "验证中..." : "验证 Seed-ASR 凭证"}
                      </button>
                      {validateResult && (
                        <p className={`text-[10px] ${validateResult.ok ? "text-green-300" : "text-red-300"}`}>
                          {validateResult.ok ? "✓ " : "✗ "}{validateResult.msg}
                        </p>
                      )}
                    </div>
                  )}
                </section>
              )
            ))}

            <section className="rounded-[var(--window-radius)] border border-white/10 bg-white/6 p-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-[11px] font-semibold text-white/90">前端外观</h3>
                  <p className="mt-0.5 text-[10px] text-white/45">{styleSummary}</p>
                </div>
                <div className={`style-preview style-preview--${styleSettings.backgroundPreset} h-8 w-16 rounded-lg border border-white/10`} />
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <label className="flex flex-col gap-1">
                  <span className="text-[10px] text-white/58">背景主题</span>
                  <select
                    value={styleSettings.backgroundPreset}
                    onChange={(e) => setStyleSettings((prev) => ({ ...prev, backgroundPreset: e.target.value as UiStyleSettings["backgroundPreset"] }))}
                    className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white outline-none transition focus:border-cyan-400/50"
                  >
                    <option value="ocean">Ocean</option>
                    <option value="sunset">Sunset</option>
                    <option value="forest">Forest</option>
                    <option value="slate">Slate</option>
                  </select>
                </label>

                <label className="flex flex-col gap-1">
                  <span className="text-[10px] text-white/58">圆角 {styleSettings.windowRadius}px</span>
                  <input
                    type="range"
                    min="10"
                    max="28"
                    value={styleSettings.windowRadius}
                    onChange={(e) => setStyleSettings((prev) => ({ ...prev, windowRadius: Number(e.target.value) }))}
                    className="h-1.5"
                  />
                </label>

                <label className="flex flex-col gap-1">
                  <span className="text-[10px] text-white/58">透明度 {Math.round(styleSettings.shellOpacity * 100)}%</span>
                  <input
                    type="range"
                    min="55"
                    max="95"
                    value={Math.round(styleSettings.shellOpacity * 100)}
                    onChange={(e) => setStyleSettings((prev) => ({ ...prev, shellOpacity: Number(e.target.value) / 100 }))}
                    className="h-1.5"
                  />
                </label>

                <label className="flex flex-col gap-1">
                  <span className="text-[10px] text-white/58">缩放 {styleSettings.fontScale.toFixed(2)}x</span>
                  <input
                    type="range"
                    min="90"
                    max="115"
                    value={Math.round(styleSettings.fontScale * 100)}
                    onChange={(e) => setStyleSettings((prev) => ({ ...prev, fontScale: Number(e.target.value) / 100 }))}
                    className="h-1.5"
                  />
                </label>
              </div>
            </section>

            <section className="rounded-[var(--window-radius)] border border-white/10 bg-white/6 p-3">
              <h3 className="mb-2 text-[11px] font-semibold text-white/90">高级原始配置</h3>
              <textarea
                value={extraContent}
                onChange={(e) => setExtraContent(e.target.value)}
                aria-label="其他原始配置"
                title="其他原始配置"
                placeholder="..."
                className="min-h-24 w-full resize-y rounded-lg border border-white/10 bg-white/5 p-2 font-mono text-[10px] leading-5 text-white outline-none transition focus:border-cyan-400/50 focus:bg-white/7"
                spellCheck={false}
              />
            </section>
          </div>
        )}

        {error && <div className="absolute bottom-20 left-0 right-0 rounded-lg border border-red-500/30 bg-red-500/15 px-2 py-1 text-[10px] text-red-200">⚠️ {error}</div>}

        <div className="absolute bottom-3 left-0 right-0 flex items-center justify-end gap-2 rounded-xl border border-white/10 bg-[#1a1c1e]/96 px-3 py-3 shadow-[0_-12px_24px_rgba(0,0,0,0.18)] mt-auto">
          <button
            onClick={onClose}
            disabled={saving}
            className="rounded-lg bg-white/8 px-4 py-1.5 text-xs text-white/70 transition hover:bg-white/14 hover:text-white disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={saving || loading}
            className="rounded-lg bg-cyan-500/20 px-4 py-1.5 text-xs font-semibold text-cyan-200 transition hover:bg-cyan-500/30 disabled:opacity-50"
          >
            {saving ? "保存中..." : "保存设置"}
          </button>
        </div>
      </div>
    </div>
  );
}
