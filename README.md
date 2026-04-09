# ClassFox Teacher

面向老师的课堂实时 AI 助教。  
本项目基于 [ouyangyipeng/ClassAssistant](https://github.com/ouyangyipeng/ClassAssistant) 二次改造而来，原项目定位是“大学生上课救场 / 摸鱼辅助”，当前版本将核心使用者切换为老师，目标场景也从“被点名时自救”改为“课堂授课时辅助答疑”。

## 项目定位

`ClassFox Teacher` 主要服务于 1v1 / 1v2 小班课、补习课、在线授课等老师单兵作战场景：

- 持续监听课堂音频，转录师生对话
- 自动检测学生提问
- 在老师来不及完整组织答案时，快速生成一句话兜底答案
- 支持展开详细解释和继续追问
- 长课堂会自动压缩摘要，帮助老师快速回看进度

一句话概括：

> 原项目是“学生怕被老师点名时的救场助手”，这个版本是“老师面对学生提问时的课堂助教”。

## v1.1.2 双阶段总结目标

`v1.1.2` 的核心目标已经从“滚动摘要 + 课后总结”的松散组合，升级为一个明确分工的双阶段本地总结系统：

- `Qwen` 只负责实时结构化整理
  - 输入是课堂转写流
  - 输出是 `30 秒窗口产物`、课堂阶段摘要和后续知识树可消费的中间结果
  - 不再承担整堂课最终总结职责
- `Gemma4` 只负责课后最终总结
  - 输入必须来自 session 级中间产物
  - 不再直接吃整堂课原始 ASR 或“半压缩半原文”的旧上下文
- “有效问题”必须绑定老师真实确认动作
  - 当前确认动作以老师点击“查看兜底答案”为准
  - 不是所有 `question_detected` 事件都能直接算有效问题

这条约束的目的很明确：

- 避免把全量课堂原文再次直接送给 `Gemma4`
- 让实时链路和课后链路职责分离，便于调试、回放和后续演进
- 为后续知识树、问题挂接、最终总结输入包预留稳定中间层

## v1.1.1 架构目标

`v1.1.1` 的改造目标不是重做界面，而是在尽量保留现有 HUD 和交互的前提下，把课堂推理链路切到“本地优先”：

- 云端只保留 ASR 能力，用于课堂语音转写
- 本地 `Ollama` 负责学生提问短答、课堂追问和课后总结
- 前端继续承担 HUD 状态展示、老师操作入口和低干扰交互
- 后端负责问题检测、上下文管理、本地模型调用、结果回传与会话编排

这套架构的核心目标是：

- 降低课堂现场的响应延迟
- 避免把课堂文本继续发送到云端 LLM
- 让模型切换、预热、健康检查都可以在本机完成
- 让后续维护者能明确区分“主链路”和“历史兼容链路”

补充说明：

- 当前仓库仍处在 `v1.1 -> v1.1.1` 的迁移过程中，部分云端 LLM 配置和旧 `rescue_*` 文件仍然存在
- 这些残留属于历史兼容内容，不应再作为新功能的默认落点
- 本地推理迁移说明、Ollama 安装与故障排查可直接查看 [docs/local-llm-migration.md](docs/local-llm-migration.md)

## 当前主链路边界

后续所有与本地模型、上下文治理、课堂短答相关的改造，优先围绕以下文件进行：

- `backend/services/llm_service.py`
- `backend/services/monitor_service.py`
- `backend/routers/question_router.py`
- `backend/routers/monitor_router.py`
- `frontend/src/components/FallbackPanel.tsx`
- `frontend/src/components/ClassStatusPanel.tsx`
- `frontend/src/App.tsx`

如果需求涉及 `Ollama`、课堂短答、追问、上下文、HUD 状态，这条链路是唯一优先改造对象。

## 旧链路与新链路边界

为了避免后续改造继续叠加在旧逻辑上，`v1.1.2` 需要明确区分两类链路：

- 当前旧链路（兼容保留，不再作为新能力主落点）
  - `LLMService.generate_realtime_summary_if_enabled()`
  - `TranscriptService.get_summary_context()`
  - `data/class_transcript.txt`
  - `data/classroom_state.json`
  - `data/timeline/current_session.json`
  - `data/summaries/*.md`
- 当前要建立的新主链路
  - `data/sessions/<session_id>/` 作为主存储
  - `30 秒窗口产物`
  - `session` 级 transcript / state / timeline
  - 后续知识树与最终总结输入包

这意味着：

- 旧平铺文件继续保留，但只作为兼容镜像
- 新需求默认先落到 `session` 主存储，而不是继续往“滚动摘要=最终总结中间层”上加逻辑
- 在 `final_summary_packager` 完成前，旧链路仍可继续服务现有课后总结，但它已经不再代表 `v1.1.2` 的目标架构

## 旧链路残留说明

以下内容目前仍在仓库中，但都属于旧推理链路残留，不应继续承接新需求：

- `backend/routers/rescue_router.py`
- `frontend/src/components/RescuePanel.tsx`
- `backend/backend.spec` 中的 `routers.rescue_router`
- [docs/migration-map.md](docs/migration-map.md) 中与 `rescue_*` 相关的历史映射
- [docs/terminology-map.md](docs/terminology-map.md) 中与 `rescue_*` 相关的历史术语

这些文件暂时保留，是为了兼容旧版本认知和后续迁移核对，不代表它们仍是教师版主链路。

## 与原项目的关系

原项目仓库：

- [ClassAssistant](https://github.com/ouyangyipeng/ClassAssistant)

原项目核心特点：

- 面向学生
- 重点处理“老师点名 / 抽查 / 课堂进度跟不上”的场景
- 关键词命中后触发红色告警
- 从“学生视角”生成应急回答

本仓库保留了原项目的整体技术路线：

- `FastAPI` 后端
- `React + Tauri` 桌面端前端
- 实时转录、LLM 生成、WebSocket 推送
- 课堂记录落盘、资料引用、总结生成

但在产品定位、触发逻辑、文案语气、前端交互和部分接口语义上做了系统性重构。

## 详细差异

### 1. 用户角色变化

| 维度 | 原项目 ClassAssistant | 本项目 ClassFox Teacher |
| --- | --- | --- |
| 面向群体 | 学生 | 老师 |
| 核心问题 | 没认真听课，怕被点名 | 正在讲课，学生突然提问 |
| 工作目标 | 帮学生临场自救 | 帮老师快速稳住课堂节奏 |
| 产出语气 | 学生回答老师 | 老师回答学生 |

### 2. 触发机制变化

| 维度 | 原项目 | 本项目 |
| --- | --- | --- |
| 触发方式 | 关键词命中、点名预警 | 学生提问检测 |
| 触发事件名 | `keyword_alert` | `question_detected` |
| 核心逻辑 | “老师是不是在点我” | “学生是不是在问问题” |

### 3. 输出内容变化

| 能力 | 原项目 | 本项目 |
| --- | --- | --- |
| 应急输出 | 救场答案 | 一句话兜底答案 |
| 展开能力 | 查看救场内容 | 查看完整解释、继续追问 |
| 摘要用途 | 帮学生跟上课堂 | 帮老师掌握当前教学进度 |

### 4. UI 与交互变化

| 维度 | 原项目 | 本项目 |
| --- | --- | --- |
| 告警风格 | 红色覆盖层，强调“危险” | 安静小卡片，强调“低干扰” |
| 主界面文案 | 开始摸鱼 / 停止摸鱼 | 开始监听 / 停止监听 |
| 心理预期 | 临时救火 | 课堂内嵌辅助 |

### 5. 提示词与角色设定变化

原项目偏向学生视角：

- “你是一个正在上课但没有认真听讲的学生”
- “老师刚刚点到了你的名字”

本项目全部切换为老师视角：

- “你是一位正在授课的老师”
- “学生刚刚向你提出了一个问题”
- “请给出简洁、专业、可立即接上的回答”

### 6. 代码与模块层面的主要调整

以下是当前版本对原仓库的主要映射与重构方向：

| 原项目模块 | 当前模块 | 调整说明 |
| --- | --- | --- |
| `api-service/main.py` | `backend/main.py` | 项目标题与入口信息切换为教师版 |
| `api-service/routers/rescue_router.py` | `backend/routers/question_router.py` | 从“救场”语义改为“提问答复”语义 |
| `api-service/services/monitor_service.py` | `backend/services/monitor_service.py` | 从关键词检测改为问题检测广播 |
| `api-service/services/llm_service.py` | `backend/services/llm_service.py` | 全部提示词按老师视角重写 |
| `app-ui/src/components/AlertOverlay.tsx` | `frontend/src/components/QuestionCard.tsx` | 红色危险覆盖层替换为轻量提问卡片 |
| `app-ui/src/components/RescuePanel.tsx` | `frontend/src/components/FallbackPanel.tsx` | 面板定位改为教师答疑辅助 |
| `app-ui/src/components/CatchupPanel.tsx` | `frontend/src/components/ClassStatusPanel.tsx` | 课堂状态展示语义调整 |
| `app-ui/src/services/api.ts` | `frontend/src/services/api.ts` | API 命名切换到教师版场景 |

补充说明：

- 具体术语变更可见 [docs/terminology-map.md](docs/terminology-map.md)
- 模块迁移关系可见 [docs/migration-map.md](docs/migration-map.md)
- 本地推理迁移说明可见 [docs/local-llm-migration.md](docs/local-llm-migration.md)
- 产品定位文档可见 [docs/product-positioning.md](docs/product-positioning.md)

## 当前功能

- 实时语音监听与课堂转录
- 学生提问检测
- 一句话兜底答案生成
- 详细解释展开
- 基于当前上下文的继续追问
- 本地模型健康检查与课堂短答模型预热
- 课堂上下文状态查看与手动重置
- 课堂状态实时摘要
- `Qwen` 30 秒窗口结构化整理与 session 级窗口落盘
- 知识树实时增量更新、知识树回顾面板与快照持久化
- “查看兜底答案”即确认有效问题，并自动挂到知识树或待确认位置
- 问题时间轴记录与课后问题轨迹回顾
- `Gemma4` 基于 `final_summary_input_package.json` 生成课后总结
- `data/sessions/<session_id>/debug/local_llm_events.jsonl` 调试日志
- `scripts/replay_session.py` 离线回放 session
- 资料引用
- 设置面板配置 ASR、本地 Ollama 与历史兼容云端参数

## v1.1.2 新增运行产物

从 `v1.1.2` 开始，主存储以 session 为单位：

- `data/sessions/<session_id>/windows/w_0001.json`
- `data/sessions/<session_id>/knowledge_tree/current_tree.json`
- `data/sessions/<session_id>/knowledge_tree/snapshots/tree_after_w_0001.json`
- `data/sessions/<session_id>/questions/question_index.json`
- `data/sessions/<session_id>/summaries/final_summary_input_package.json`
- `data/sessions/<session_id>/summaries/final_summary.md`
- `data/sessions/<session_id>/debug/local_llm_events.jsonl`

旧的平铺文件仍保留兼容镜像，但不再是 `v1.1.2` 新能力的主落点。

## 调试与回放

常用入口：

```bash
python3 scripts/replay_session.py --list
python3 scripts/replay_session.py --latest --show-windows
python3 scripts/replay_session.py --session-id <session_id> --json
```

可直接配合以下接口调试前端状态：

- `GET /api/knowledge_tree/current`
- `GET /api/knowledge_tree/snapshots`
- `GET /api/timeline`
- `GET /api/timeline/summary`
- `GET /api/monitor/final_summary_status`

## 技术栈

- 前端：`React` + `TypeScript` + `Vite` + `Tauri`
- 后端：`FastAPI`
- 实时通信：`WebSocket`
- 语音识别：本地 ASR / DashScope / Seed-ASR
- 大模型：默认走本地 `Ollama`，旧 OpenAI Compatible 链路仅保留给历史排障

## 目录结构

```text
.
├── backend/        # FastAPI 后端
├── frontend/       # React + Tauri 前端
├── docs/           # 产品定位 / 术语映射 / 迁移说明
├── prompts/        # 提示词相关材料
├── scripts/        # 启动与环境配置脚本
└── data/           # 运行期数据（默认不提交）
```

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/SSSTTTTTE/classfox-teacher.git
cd classfox-teacher
```

### 2. 安装依赖

```bash
bash scripts/setup.sh
```

### 3. 配置环境变量

```bash
cp backend/.env.example backend/.env
```

`v1.1.1` 默认按“本地 Ollama + 本地 ASR”启动。建议先在本机准备 Ollama：

```bash
ollama pull qwen2.5:1.5b
ollama pull gemma4:e4b
```

开发环境最少确认以下配置即可：

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CHAT_MODEL=qwen2.5:1.5b
OLLAMA_FINAL_SUMMARY_MODEL=gemma4:e4b
ASR_MODE=local
```

说明：

- 默认短答模型是 `qwen2.5:1.5b`
- 默认课后总体总结模型是 `gemma4:e4b`
- 实时总结本轮默认关闭，只保留开关和空接口
- `LLM_*` 字段仍保留在 `.env.example` 中，但只用于历史兼容排障，不再是默认依赖
- 如果你是在继续推进 `v1.1.1` 改造，请优先参考根目录的 `v1.1.1.md` 和 [docs/local-llm-migration.md](docs/local-llm-migration.md)

如果你要启用云端语音识别，再继续填写：

- `DASHSCOPE_API_KEY`
- `SEED_ASR_APP_KEY`
- `SEED_ASR_ACCESS_KEY`

上课前建议先确认一次：

1. `ollama serve` 已启动
2. `qwen2.5:1.5b` 与 `gemma4:e4b` 已拉取
3. 前端设置面板或 `/api/local_llm/health` 显示在线
4. 开始课堂时能完成自动预热

### 4. 启动开发环境

```bash
bash scripts/dev.sh
```

## 脱敏说明

为了安全公开仓库，当前版本已经做了以下处理：

- 不提交本地 `backend/.env`
- 不提交 `data/` 运行数据
- 不提交本地 `output/` 和 `.playwright-cli/` 测试产物
- 测试脚本中的百炼 / Seed-ASR 本地 key 已改为环境变量读取

更多安装、迁移、排障与课前准备细节，请查看 [docs/local-llm-migration.md](docs/local-llm-migration.md)。

如果你是从本地私有开发环境继续使用，请自行在 `backend/.env` 中填写真实配置，不要把密钥重新提交到 Git。

## 适用与不适用场景

适合：

- 小班课老师
- 在线答疑老师
- 需要边讲边应对提问的授课场景

不适合：

- 需要完整教务管理、排课、作业系统的场景
- 对正式教学结论有强一致性要求、不能接受 AI 草稿辅助的场景

## 致谢

本项目基于原作者的 `ClassAssistant` 进行二次改造。  
感谢原项目提供的整体架构、桌面端方案与课堂辅助思路。本仓库主要完成了从“学生救场工具”到“老师课堂助教”的产品重构与工程改造。
