# 术语映射表 — 学生版 → 教师版

> `v1.1.1` 说明：本表用于解释旧术语如何迁移到教师版语义，不代表旧 `rescue_*` 标识仍应承接新需求。
> 所有新增课堂短答、本地模型和上下文治理改动，默认都应落在 `question_*` / `FallbackPanel` 主链路。

## UI 文案术语

| 学生版（classfox） | 教师版（v1.1） | 说明 |
|------------------|--------------|------|
| 上课摸鱼搭子 | ClassFox 课堂助教 | 产品名称 |
| 开始摸鱼 | 开始监听 | 启动监听按钮 |
| 停止摸鱼 | 停止监听 | 停止监听按钮 |
| 摸鱼模式 | 课堂监听模式 | 工作状态描述 |
| 点名警报 | 学生提问检测 | 触发事件 |
| 救场答案 | 兜底答案 | 主要输出 |
| 看看进度 | 课堂进展 | 查看摘要功能 |
| 救场！ | 查看答案 | 展开面板按钮 |
| 安全了 | 关闭 | 消除卡片按钮 |
| 老师在问你 | 学生在问你 | 警报标题（已从危险变为通知） |
| 紧急救场 | 快速答题 | 功能标签 |
| 跟上进度 | 课堂进展 | 功能标签 |

## 代码层术语

| 学生版标识符 | 教师版标识符 | 文件 |
|------------|------------|------|
| `keyword_alert` | `question_detected` | WebSocket 消息类型 |
| `MonitorService.keywords` | ~~移除~~ | 不再需要关键词列表 |
| `MonitorService._check_keywords()` | `MonitorService._check_question()` | 检测方法 |
| `emergency_rescue()` | `detect_question_answer()` | LLM 方法名 |
| `analyze_rescue()` | `generate_fallback_answer()` | LLM Service 方法 |
| `analyze_catchup()` | `summarize_class_status()` | LLM Service 方法 |
| `RescuePanel` | `FallbackPanel` | React 组件 |
| `CatchupPanel` | `ClassStatusPanel` | React 组件 |
| `AlertOverlay` | `QuestionCard` | React 组件 |
| `showRescuePanel` | `showFallbackPanel` | React 状态 |
| `level: "danger"/"warning"` | `confidence: "high"/"low"` | 事件元数据字段 |
| `cite_files` | `materials` | 参考资料目录 |
| `/api/emergency_rescue` | `/api/question/answer` | HTTP 端点 |
| `/api/catchup` | `/api/status/summary` | HTTP 端点 |

补充说明：

- `RescuePanel`、`emergency_rescue` 等名称目前只用于历史映射和残留排查
- 后续功能不应继续新增到 `rescue_*` 文件和接口

## 提示词角色设定

| 学生版角色 | 教师版角色 |
|----------|----------|
| 你是一个正在上课但没有认真听讲的学生 | 你是一位正在授课的经验丰富的老师 |
| 老师刚刚点到了你的名字 | 学生刚刚向你提出了一个问题 |
| 你需要用几句话蒙混过关 | 你需要给出简洁、专业的答案 |
| 显得你认真听了 | 帮助学生理解，维持课堂流畅 |

## 数据文件名称

| 学生版文件名 | 教师版文件名 |
|------------|------------|
| `class_transcript.txt` | `class_transcript.txt`（保留） |
| `current_class_material.txt` | `current_class_material.txt`（保留） |
| `data/cite/` | `data/materials/` |
| `data/summaries/` | `data/summaries/`（保留） |
