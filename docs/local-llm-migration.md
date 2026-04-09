# 本地推理迁移说明（v1.1.2）

本文用于说明 `v1.1` 为什么迁到本地推理、如何安装 `Ollama`、默认模型分工、`v1.1.2` 相对 `v1.1.1` 的新增结构化链路、关键配置项、课前准备流程以及常见故障排查。后续接手者即使不看历史上下文，也应能从这里继续维护。

## 1. 为什么改成本地推理

`v1.1.1` 的目标不是继续扩写云端 LLM 链路，而是把课堂文本生成能力收回本机：

- 降低课堂现场的首答延迟
- 避免把课堂文本默认发送到云端 LLM
- 让模型预热、健康检查、上下文重置都能在本地完成
- 保持现有前端 HUD，不为切换模型重做一套新界面

当前仍可保留云端 ASR，但课堂问答、追问和课后总结默认走本地 `Ollama`。

## 2. 新旧架构对比

| 维度 | 旧链路 | `v1.1.1` 新链路 |
| --- | --- | --- |
| 语音识别 | 本地 / DashScope / Seed-ASR | 保持不变 |
| 课堂问答 | 云端 OpenAI Compatible LLM | 本地 `Ollama` |
| 课堂追问 | 云端 OpenAI Compatible LLM | 本地 `Ollama` |
| 课后总体总结 | 云端 OpenAI Compatible LLM | 本地 `Ollama` |
| 实时总结 | 可能直接依赖 LLM | 默认关闭，仅保留开关与空接口 |
| 运行前检查 | 依赖人工判断 | 提供健康检查、状态查看、模型预热 |

主链路以这些文件为准：

- `backend/services/llm_service.py`
- `backend/services/monitor_service.py`
- `backend/routers/local_llm_router.py`
- `backend/routers/question_router.py`
- `frontend/src/components/SettingsPanel.tsx`
- `frontend/src/components/ToolBar.tsx`
- `frontend/src/App.tsx`

以下文件仍是历史兼容残留：

- `backend/routers/rescue_router.py`
- `frontend/src/components/RescuePanel.tsx`
- `LLM_*` 旧配置项

## 2.5 `v1.1.2` 相对 `v1.1.1` 的关键变化

`v1.1.1` 的重点是把问答和总结迁到本地 `Ollama`。  
`v1.1.2` 则进一步把“实时整理”和“课后总结”拆成两层：

- `Qwen` 只做 30 秒窗口结构化整理
  - 输出 `stage_summary`
  - 抽取主题、子主题、概念、关系
  - 驱动知识树增量更新
- `Gemma4` 只做课后最终总结
  - 输入来自 `data/sessions/<session_id>/summaries/final_summary_input_package.json`
  - 不再直接读取整堂课原始 ASR
- “有效问题”必须绑定老师点击“查看兜底答案”
  - 确认后进入问题状态机
  - 并挂到知识树或标记为 `unresolved_link`

新增的关键运行期文件：

- `data/sessions/<session_id>/windows/w_*.json`
- `data/sessions/<session_id>/knowledge_tree/current_tree.json`
- `data/sessions/<session_id>/knowledge_tree/snapshots/tree_after_w_*.json`
- `data/sessions/<session_id>/questions/question_index.json`
- `data/sessions/<session_id>/summaries/final_summary_input_package.json`
- `data/sessions/<session_id>/debug/local_llm_events.jsonl`

## 3. Ollama 安装与模型拉取

### macOS

可通过 [Ollama 官网](https://ollama.com/download) 安装，或按官网文档使用包管理器安装。安装完成后确认本机命令可用：

```bash
ollama --version
```

默认模型分工如下：

- 课堂短答 / 追问：`qwen2.5:1.5b`
- 课后总体总结：`gemma4:e4b`
- 实时总结：默认关闭，不要求本轮拉取专用模型

首次使用前执行：

```bash
ollama pull qwen2.5:1.5b
ollama pull gemma4:e4b
```

若本机没有后台服务，先启动：

```bash
ollama serve
```

默认服务地址：

```text
http://127.0.0.1:11434
```

## 4. 默认模型建议

本轮不要把所有任务写成一个统一模型字段，默认分工是硬约束：

- `OLLAMA_CHAT_MODEL=qwen2.5:1.5b`
- `OLLAMA_FINAL_SUMMARY_MODEL=gemma4:e4b`
- `OLLAMA_REALTIME_SUMMARY_ENABLED=false`
- `OLLAMA_REALTIME_SUMMARY_MODEL=qwen2.5:1.5b`

建议维持这个分工，先保证课堂短答稳定，再按需评估更大的总结模型。

## 5. 配置项说明

`backend/.env.example` 里的核心字段如下：

| 配置项 | 作用 | 默认值 |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | 本地 Ollama 服务地址 | `http://127.0.0.1:11434` |
| `OLLAMA_CHAT_MODEL` | 课堂短答与追问模型 | `qwen2.5:1.5b` |
| `OLLAMA_FINAL_SUMMARY_MODEL` | 课后总体总结模型 | `gemma4:e4b` |
| `OLLAMA_TIMEOUT` | 单次本地推理超时秒数 | `45` |
| `OLLAMA_MAX_TOKENS` | 生成长度上限 | `1024` |
| `OLLAMA_TEMPERATURE` | 本地生成温度 | `0.3` |
| `OLLAMA_REALTIME_SUMMARY_ENABLED` | 是否启用实时总结 | `false` |
| `OLLAMA_REALTIME_SUMMARY_MODEL` | 实时总结模型 | `qwen2.5:1.5b` |
| `ASR_MODE` | 语音识别模式 | `local` |

历史兼容字段：

- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_SUMMARY_MODEL`
- `LLM_FALLBACK_MODEL`

这些字段只保留给旧排障脚本和迁移兼容，不应再作为主链路默认配置。

## 6. 课前准备流程

建议老师或维护者在上课前按下面顺序检查：

1. 确认 `backend/.env` 中的 `OLLAMA_*` 字段正确。
2. 执行 `ollama serve`，确保服务在本机运行。
3. 执行 `ollama list`，确认 `qwen2.5:1.5b` 与 `gemma4:e4b` 已存在。
4. 启动后端与前端。
5. 在设置面板或主界面查看本地模型状态是否在线。
6. 点击开始课堂，等待自动健康检查与课堂短答模型预热完成。
7. 如课堂上下文异常膨胀，可使用“重置上下文”。

相关接口：

- `GET /api/local_llm/health`
- `GET /api/local_llm/status`
- `POST /api/local_llm/warmup`
- `GET /api/local_llm/evaluation`
- `GET /api/monitor/context_status`
- `POST /api/monitor/reset_context`
- `GET /api/knowledge_tree/current`
- `GET /api/timeline/summary`

## 7. 打包与依赖收口说明

本轮和打包有关的关键文件：

- `backend/requirements.txt`
- `backend/backend.spec`
- `backend/class-assistant-backend.spec`

当前收口原则：

- `requirements.txt` 中保留本地推理主链路所需的 `httpx`
- `openai` 仅保留给历史兼容排障脚本 `backend/test_llm.py`
- 两个 `.spec` 都显式覆盖 `routers` 与 `services` 全量子模块，避免新增 `local_llm_*`、`prompt_builder`、`session_state_service` 等文件后漏打包
- `.env.example` 一并随打包产物带出，便于部署后校对配置

## 8. 故障排查

### `GET /api/local_llm/health` 显示离线

优先检查：

1. `ollama serve` 是否已启动
2. `OLLAMA_BASE_URL` 是否仍指向 `http://127.0.0.1:11434`
3. 本机防火墙或代理是否拦截了本地端口

### 模型在线但开始课堂时报“未找到课堂短答模型”

执行：

```bash
ollama list
ollama pull qwen2.5:1.5b
```

然后重新进入开始课堂流程或手动点击预热。

### 课后总结失败

优先检查：

1. `gemma4:e4b` 是否已拉取
2. `OLLAMA_FINAL_SUMMARY_MODEL` 是否被改成了本机不存在的名称
3. 本机内存是否不足，导致总结模型装载失败

额外检查：

4. `data/sessions/<session_id>/summaries/final_summary_input_package.json` 是否已生成
5. `data/sessions/<session_id>/debug/local_llm_events.jsonl` 中是否记录了 `final_class_summary`

### 课堂文本过长，回答变慢或跑偏

可依次检查：

1. `GET /api/monitor/context_status` 中的上下文预算是否接近上限
2. 是否需要执行“重置上下文”
3. `data/debug/local_llm_events.jsonl` 中是否持续出现 `was_trimmed=true`

### 实时总结为什么没有生成

在 `v1.1.1` 里这通常是预期行为，因为默认：

- `OLLAMA_REALTIME_SUMMARY_ENABLED=false`
- 实时总结只保留占位接口与状态字段
- `POST /api/local_llm/realtime_summary_probe` 用于验证关闭状态时会直接跳过模型调用

但在 `v1.1.2` 中，如果你已经启用了实时结构化链路，优先检查：

1. `data/sessions/<session_id>/windows/` 下是否已有 `w_0001.json`
2. `data/sessions/<session_id>/debug/local_llm_events.jsonl` 中是否有 `window_structuring`
3. `GET /api/knowledge_tree/current` 是否能返回节点
4. 前端 WebSocket 是否已收到 `knowledge_tree_update`

## 9. 离线回放与调试

推荐直接用回放脚本看某节课的结构化中间产物：

```bash
python3 scripts/replay_session.py --list
python3 scripts/replay_session.py --latest --show-windows
python3 scripts/replay_session.py --session-id <session_id> --json
```

调试日志里现在应至少能看到：

- `session_id`
- `window_id`（Qwen 窗口结构化任务）
- `prompt_preview`
- `summary_package_bytes`（Gemma4 课后总结任务）
- `total_duration_ms`

这些字段的目标是让维护者能快速回答两类问题：

- 某个 30 秒窗口为什么没有抽出主题
- 某节课的最终总结为什么输入包过大或耗时异常
## 10. 接手建议

如果后续继续推进 `v1.1.1`：

1. 新功能优先落在 `question_router` / `llm_service` / `monitor_service` 主链路。
2. 不要把新需求继续叠到 `rescue_*` 文件。
3. 先维持当前模型分工，再评估更复杂的多模型策略。
4. 若修改了 `backend/services/` 或 `backend/routers/` 新模块，记得同步检查两个 `.spec` 是否仍满足打包需求。
