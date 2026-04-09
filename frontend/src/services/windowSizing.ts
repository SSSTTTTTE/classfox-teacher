export const MAIN_WINDOW_SIZE = {
  width: 420,
  idleHeight: 250,
  idleExpandedHeight: 390,
  monitoringHeight: 520,
  monitoringWithQuestionHeight: 620,
  fallbackHeight: 620,
  monitoringExpandedHeight: 700,
  monitoringExpandedWithQuestionHeight: 820,
  minWidth: 420,
  minHeight: 250,
} as const;

export const PANEL_WINDOW_SIZES = {
  startMonitor: { width: 560, height: 430 },
  settings: { width: 560, height: 680 },
  classStatus: { width: 520, height: 560 },
  catchup: { width: 520, height: 560 },
  timeline: { width: 520, height: 520 },
  knowledgeTree: { width: 580, height: 680 },
  summaryGeneration: { width: 620, height: 760 },
  rescue: { width: 520, height: 360 },
  alert: { width: 420, height: 160 },
} as const;
