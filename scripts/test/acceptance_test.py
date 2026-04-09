#!/usr/bin/env python3
"""
ClassFox 验收测试脚本 (macOS)
=================================
模拟课堂场景，验证 v1.1.1 主链路功能。
用法: python3 scripts/test/acceptance_test.py
前提: 后端已启动 (bash scripts/start_backend.sh)
"""

from __future__ import annotations

import requests

BASE = "http://127.0.0.1:8765/api"
PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"

passed = 0
failed = 0


def ok(msg: str):
    global passed
    passed += 1
    print(f"  {PASS} {msg}")


def fail(msg: str, detail: str = ""):
    global failed
    failed += 1
    print(f"  {FAIL} {msg}" + (f": {detail}" if detail else ""))


def check(cond: bool, label: str, detail: str = ""):
    if cond:
        ok(label)
    else:
        fail(label, detail)


def section(title: str):
    print(f"\n【{title}】")


def request_json(method: str, path: str, **kwargs):
    response = requests.request(method, f"{BASE}{path}", timeout=8, **kwargs)
    payload = {}
    if response.content:
        try:
            payload = response.json()
        except Exception:
            payload = {"raw": response.text}
    return response, payload


# ------------------------------------------------------------------
section("健康检查")
try:
    r, health = request_json("GET", "/health")
    check(r.status_code == 200, "后端在线")
    check(health.get("status") == "healthy", "健康接口返回 healthy")
except Exception as exc:
    fail("后端在线", str(exc))
    print("\n后端未启动，请先运行: bash scripts/start_backend.sh\n")
    raise SystemExit(1)

# ------------------------------------------------------------------
section("本地模型健康检查")
r, local_health = request_json("GET", "/local_llm/health")
check(r.ok, "Ollama 健康检查成功", str(local_health))
check(local_health.get("online") is True, "Ollama 在线", str(local_health.get("last_error", "")))
check(local_health.get("chat_model_available") is True, "短答模型可用")
check(local_health.get("final_summary_model_available") is True, "课后总结模型可用")

# ------------------------------------------------------------------
section("本地模型预热")
r, warmup = request_json("POST", "/local_llm/warmup")
check(r.ok, "短答模型预热成功", str(warmup))
check(warmup.get("warmup_state") == "ready", "预热状态为 ready")
check(warmup.get("is_warmed") is True, "短答模型已就绪")

# ------------------------------------------------------------------
section("实时总结关闭保护")
r, probe = request_json("POST", "/local_llm/realtime_summary_probe")
check(r.ok, "实时总结探针请求成功", str(probe))
check(probe.get("skipped") is True, "实时总结关闭时直接跳过")
check(probe.get("reason") == "disabled_by_config", "跳过原因标记为 disabled_by_config")

r, evaluation = request_json("GET", "/local_llm/evaluation")
check(r.ok, "读取本地推理评估快照成功")
metrics = evaluation.get("metrics", {})
task_counts = evaluation.get("task_counts", {})
recent_events = evaluation.get("recent_events", [])
check("first_answer_latency_ms" in metrics, "评估指标包含首答延迟")
check("teacher_speakable_rate" in metrics, "评估指标包含老师可转述率")
check(task_counts.get("realtime_summary", 0) >= 1, "评估快照记录到实时总结事件")
check(
    any(event.get("task") == "realtime_summary" and event.get("skipped") for event in recent_events),
    "实时总结关闭事件已进入专门日志",
)

# ------------------------------------------------------------------
section("课堂初始化（dry run）")
start_payload = {
    "subject": "数学",
    "course_name": "函数单调性复习",
    "dry_run": True,
}
r, start_data = request_json("POST", "/start_monitor", json=start_payload)
check(r.ok, "dry run 初始化成功", str(start_data))
check(start_data.get("status") == "dry_run_ready", "返回 dry_run_ready 状态")
check(start_data.get("subject") == "数学", "课堂科目注入成功")
steps = {step.get("step"): step for step in start_data.get("init_steps", [])}
check(steps.get("audio_capture_skipped", {}).get("ok") is True, "dry run 未启动麦克风")
check(steps.get("chat_model_warmed", {}).get("ok") is True, "初始化阶段已预热短答模型")

r, context_payload = request_json("GET", "/monitor/context_status")
context = context_payload.get("context", {})
check(r.ok, "读取课堂上下文状态成功")
check(context.get("subject") == "数学", "上下文状态保留当前科目")
check(context.get("llm_ready") is True, "上下文状态记录 llm_ready")
check(context.get("realtime_summary_enabled") is False, "上下文状态可见实时总结开关且默认关闭")

# ------------------------------------------------------------------
section("本地问答主链路")
question_payload = {"detected_question": "老师，为什么导数是负值就说明它在下降？"}
r, answer = request_json("POST", "/question/answer", json=question_payload)
check(r.ok, "本地兜底回答成功", str(answer))
check(answer.get("status") == "success", "问答接口返回 success")
check(bool(answer.get("teacher_speakable_answer")), "返回老师可转述答案")
check(answer.get("used_subject") == "数学", "回答链路使用已注入科目")
check(answer.get("question_type") == "原因型", f"问题类型识别为原因型 (实际={answer.get('question_type')})")

r, evaluation_after_answer = request_json("GET", "/local_llm/evaluation")
recent_events = evaluation_after_answer.get("recent_events", [])
check(
    any(event.get("task") == "fallback_answer" and event.get("success") for event in recent_events),
    "课堂短答事件已写入专门日志",
)

# ------------------------------------------------------------------
section("上下文重置")
r, reset_payload = request_json("POST", "/monitor/reset_context")
reset_context = reset_payload.get("context", {})
check(r.ok, "课堂上下文重置成功", str(reset_payload))
check(reset_payload.get("status") == "success", "重置接口返回 success")
check(reset_context.get("recent_questions") == 0, "重置后 recent_questions 清零")
check(reset_context.get("recent_answers") == 0, "重置后 recent_answers 清零")
check(reset_context.get("subject") == "数学", "重置后保留当前科目")

# ------------------------------------------------------------------
section("时间轴清空")
r, _ = request_json("POST", "/timeline/clear")
check(r.ok, "清空时间轴")

# ------------------------------------------------------------------
section("场景1: 模拟学生提问 → 时间轴记录")
node1 = {
    "timestamp": "09:00",
    "text": "老师，什么是递归？",
    "student_question": "什么是递归？",
    "one_sentence_answer": "函数调用自身来解决更小的同类问题。",
}
r, data = request_json("POST", "/timeline/add", json=node1)
check(r.ok, "添加提问节点")
check(data.get("status") == "added", "首次提问写入时间轴")
check(data.get("repeat_count", 1) == 1, "首次提问 repeat_count 语义正常")
node_id_1 = data.get("node_id", "")
check(bool(node_id_1), "返回 node_id")

# ------------------------------------------------------------------
section("场景2: 模拟连续追问 → 自动书签")
node2 = {
    "timestamp": "09:05",
    "text": "老师，递归不就是无限循环吗？",
    "student_question": "递归是不是无限循环？",
    "one_sentence_answer": "不是，递归有终止条件（base case）防止无限调用。",
}
r, _ = request_json("POST", "/timeline/add", json=node2)
check(r.ok, "添加追问节点")

node3 = {
    "timestamp": "09:08",
    "text": "老师，还是不懂递归，能举例吗？",
    "student_question": "递归能举个例子吗？",
    "one_sentence_answer": "斐波那契数列：f(n)=f(n-1)+f(n-2)，f(0)=0, f(1)=1。",
}
r, _ = request_json("POST", "/timeline/add", json=node3)
check(r.ok, "添加第三次提问")

r, timeline = request_json("GET", "/timeline")
check(r.ok, "获取时间轴")
check(timeline.get("total", 0) >= 1, f"时间轴有节点 (total={timeline.get('total', 0)})")

# ------------------------------------------------------------------
section("场景3: 展开标记")
if node_id_1:
    r, _ = request_json("POST", "/timeline/expanded", json={"node_id": node_id_1})
    check(r.ok, "标记节点已展开")

    r, timeline = request_json("GET", "/timeline")
    node_found = next((node for node in timeline.get("nodes", []) if node["node_id"] == node_id_1), None)
    check(node_found is not None, "展开后节点仍在时间轴")
    if node_found:
        check(node_found.get("expanded"), "节点 expanded=True")
        check(node_found.get("bookmarked"), "展开后自动书签")

# ------------------------------------------------------------------
section("场景4: 书签筛选")
r, bookmarked = request_json("GET", "/timeline?bookmarked_only=true")
check(r.ok, "书签筛选请求成功")
all_bookmarked = all(node.get("bookmarked") for node in bookmarked.get("nodes", []))
check(all_bookmarked or len(bookmarked.get("nodes", [])) == 0, "书签列表节点均已书签")

# ------------------------------------------------------------------
section("场景5: 时间轴摘要")
r, summary = request_json("GET", "/timeline/summary")
check(r.ok, "获取时间轴摘要")
check("total_questions" in summary, "摘要包含 total_questions")
check("trajectory" in summary, "摘要包含 trajectory")

# ------------------------------------------------------------------
section("场景6: 参考资料列表")
r, _ = request_json("GET", "/materials")
check(r.ok, "获取资料列表")

# ------------------------------------------------------------------
section("场景7: 监控状态接口")
r, status = request_json("GET", "/monitor_status")
check(r.ok, "获取监控状态")
check("is_monitoring" in status, "状态包含 is_monitoring")
check("is_paused" in status, "状态包含 is_paused")
check("context" in status, "状态包含上下文快照")

# ------------------------------------------------------------------
print("\n" + "=" * 40)
total = passed + failed
print(f"结果: {passed}/{total} 通过", end="")
if failed > 0:
    print(f"，{failed} 失败")
else:
    print("  ✓ 全部通过")
print()
