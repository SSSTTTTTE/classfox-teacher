# 迁移映射文档 — classfox → v1.1

> `v1.1.1` 说明：本表用于保留历史迁移关系，不代表所有映射后的文件都仍是当前主链路。
> 其中 `backend/routers/rescue_router.py` 属于旧推理链路残留，当前教师版主路径应优先看 `backend/routers/question_router.py`。

## 模块映射总览

### 后端模块

| 原 classfox 模块 | 新 v1.1 模块 | 改动类型 | 说明 |
|----------------|-------------|---------|------|
| `api-service/main.py` | `backend/main.py` | 重命名 + 小改 | 移除 ppt_router，标题改为 ClassFox Teacher |
| `api-service/config.py` | `backend/config.py` | 路径修改 | DATA_DIR 指向 v1.1/data/ |
| `api-service/routers/monitor_router.py` | `backend/routers/monitor_router.py` | 少量改动 | 移除 keywords 相关端点（或保留为调试用） |
| `api-service/routers/rescue_router.py` | `backend/routers/question_router.py` | **重命名+重写** | 历史迁移关系保留；当前 `backend/routers/rescue_router.py` 仅为 legacy 残留，主链路已切到 `question_router.py` |
| `api-service/routers/ppt_router.py` | ~~删除~~ | 删除 | PPT 功能暂不需要 |
| `api-service/routers/settings_router.py` | `backend/routers/settings_router.py` | 保留 | 配置管理不变 |
| `api-service/routers/summary_router.py` | `backend/routers/summary_router.py` | 保留 | 课堂摘要保留 |
| `api-service/services/monitor_service.py` | `backend/services/monitor_service.py` | **核心改动** | 移除 keyword_alert，新增 question_detected 广播 |
| `api-service/services/llm_service.py` | `backend/services/llm_service.py` | **提示词重写** | 全部改为老师视角 |
| `api-service/services/asr_service.py` | `backend/services/asr_service.py` | 保留 | ASR 逻辑不变 |
| `api-service/services/transcript_service.py` | `backend/services/transcript_service.py` | 路径修改 | 文件路径改为 v1.1/data/ |

### 前端模块

| 原 classfox 模块 | 新 v1.1 模块 | 改动类型 | 说明 |
|----------------|-------------|---------|------|
| `app-ui/src/App.tsx` | `frontend/src/App.tsx` | **重构** | 移除 showRescuePanel 模态逻辑，改为浮动卡片状态 |
| `app-ui/src/components/AlertOverlay.tsx` | `frontend/src/components/QuestionCard.tsx` | **替换** | 红色覆盖层 → 安静小卡片 |
| `app-ui/src/components/RescuePanel.tsx` | `frontend/src/components/FallbackPanel.tsx` | **重命名+主路径迁移** | 主链路已切到 `FallbackPanel`；仓库里的 `frontend/src/components/RescuePanel.tsx` 仅保留 legacy 占位，不再承接新需求 |
| `app-ui/src/components/CatchupPanel.tsx` | `frontend/src/components/ClassStatusPanel.tsx` | **重命名+改文案** | 课堂状态面板 |
| `app-ui/src/components/ToolBar.tsx` | `frontend/src/components/ToolBar.tsx` | **文案改动** | "开始摸鱼" → "开始监听" 等 |
| `app-ui/src/hooks/useWebSocket.ts` | `frontend/src/hooks/useWebSocket.ts` | **消息类型更新** | keyword_alert → question_detected |
| `app-ui/src/services/api.ts` | `frontend/src/services/api.ts` | **API 名称更新** | emergencyRescue / emergencyRescueChat 已退场，主链路改为 `getFallbackAnswer` / `questionFollowup` |

## 数据目录映射

| 原路径 | 新路径 |
|--------|--------|
| `classfox/api-service/data/` | `v1.1/data/` |
| `data/summaries/` | `data/summaries/` |
| `data/cite/` | `data/materials/` |
| — | `data/transcripts/` |
| — | `data/timeline/` |
| — | `data/debug/` |

## 提示词迁移

原 `llm_service.py` 中所有提示词冻结至 `prompts/legacy/`，新提示词使用老师视角重写：

| 功能 | 旧角色设定 | 新角色设定 |
|------|----------|----------|
| 兜底答案 | "你是一个正在上课被点名的学生" | "你是一位正在授课的老师，学生刚刚提了一个问题" |
| 课堂摘要 | "总结课堂内容（学生视角）" | "总结课堂进展，帮助老师掌握当前教学状态" |
| 历史压缩 | 学生听课记录 | 课堂转录（师生对话）压缩 |
