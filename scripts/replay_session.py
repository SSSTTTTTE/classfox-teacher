#!/usr/bin/env python3
"""
Session 回放脚本
================
离线查看某个课堂 session 的窗口摘要、知识树快照、问题轨迹与总结输入包。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
SESSIONS_DIR = ROOT_DIR / "data" / "sessions"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def list_sessions() -> list[Path]:
    if not SESSIONS_DIR.exists():
        return []
    return sorted([path for path in SESSIONS_DIR.iterdir() if path.is_dir()], reverse=True)


def build_session_report(session_dir: Path) -> dict[str, Any]:
    meta = load_json(session_dir / "session_meta.json", {})
    windows: list[dict[str, Any]] = []
    windows_dir = session_dir / "windows"
    if windows_dir.exists():
      for path in sorted(windows_dir.glob("w_*.json")):
          payload = load_json(path, {})
          if isinstance(payload, dict):
              windows.append(
                  {
                      "window_id": payload.get("window_id", path.stem),
                      "start_time": payload.get("start_time", ""),
                      "end_time": payload.get("end_time", ""),
                      "main_topic": payload.get("main_topic", ""),
                      "stage_summary": payload.get("stage_summary", ""),
                      "linked_question_ids": payload.get("linked_question_ids", []),
                  }
              )

    knowledge_tree = load_json(session_dir / "knowledge_tree" / "current_tree.json", {})
    snapshots_dir = session_dir / "knowledge_tree" / "snapshots"
    snapshots = []
    if snapshots_dir.exists():
        for path in sorted(snapshots_dir.glob("tree_after_*.json")):
            payload = load_json(path, {})
            if isinstance(payload, dict):
                snapshots.append(
                    {
                        "snapshot_id": path.stem,
                        "current_main_topic": payload.get("current_main_topic", ""),
                        "total_nodes": len(payload.get("nodes", [])),
                        "total_edges": len(payload.get("edges", [])),
                        "updated_at": payload.get("updated_at", ""),
                    }
                )

    question_index = load_json(session_dir / "questions" / "question_index.json", [])
    final_package = load_json(session_dir / "summaries" / "final_summary_input_package.json", {})
    final_summary_path = session_dir / "summaries" / "final_summary.md"
    debug_events_path = session_dir / "debug" / "local_llm_events.jsonl"
    debug_event_count = 0
    if debug_events_path.exists():
        debug_event_count = sum(1 for _ in debug_events_path.open("r", encoding="utf-8"))

    return {
        "session_id": session_dir.name,
        "meta": meta,
        "window_count": len(windows),
        "windows": windows,
        "knowledge_tree": {
            "current_main_topic": knowledge_tree.get("current_main_topic", ""),
            "total_nodes": len(knowledge_tree.get("nodes", [])),
            "total_edges": len(knowledge_tree.get("edges", [])),
            "updated_at": knowledge_tree.get("updated_at", ""),
        },
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
        "question_count": len(question_index) if isinstance(question_index, list) else 0,
        "questions": question_index if isinstance(question_index, list) else [],
        "final_summary_package": {
            "exists": bool(final_package),
            "window_summaries": len(final_package.get("window_summaries", [])) if isinstance(final_package, dict) else 0,
            "valid_questions": len(final_package.get("valid_questions", [])) if isinstance(final_package, dict) else 0,
            "topic_timeline": len(final_package.get("topic_timeline", [])) if isinstance(final_package, dict) else 0,
            "path": str((session_dir / "summaries" / "final_summary_input_package.json").relative_to(ROOT_DIR)),
        },
        "final_summary_markdown": {
            "exists": final_summary_path.exists(),
            "path": str(final_summary_path.relative_to(ROOT_DIR)),
        },
        "debug": {
            "event_count": debug_event_count,
            "path": str(debug_events_path.relative_to(ROOT_DIR)),
        },
    }


def print_session_list(sessions: list[Path]) -> None:
    if not sessions:
        print("当前没有可回放的 session。")
        return
    print("可回放 session:")
    for session_dir in sessions:
        meta = load_json(session_dir / "session_meta.json", {})
        started_at = meta.get("started_at", "")
        course_name = meta.get("course_name", "")
        status = meta.get("status", "")
        print(f"- {session_dir.name} | {course_name or '未命名课程'} | {started_at or '未知开始时间'} | {status or 'unknown'}")


def print_report(report: dict[str, Any], *, show_windows: bool) -> None:
    meta = report.get("meta", {})
    print(f"Session: {report.get('session_id', '')}")
    print(f"课程: {meta.get('course_name', '') or '未命名课程'}")
    print(f"学科: {meta.get('subject', '') or '未指定'}")
    print(f"开始/结束: {meta.get('started_at', '') or '未知'} -> {meta.get('ended_at', '') or '进行中'}")
    print(f"窗口数: {report.get('window_count', 0)} | 问题数: {report.get('question_count', 0)}")

    tree = report.get("knowledge_tree", {})
    print(
        "知识树: "
        f"{tree.get('current_main_topic', '') or '暂无主主题'} | "
        f"节点 {tree.get('total_nodes', 0)} | 连线 {tree.get('total_edges', 0)} | "
        f"快照 {report.get('snapshot_count', 0)}"
    )

    package = report.get("final_summary_package", {})
    print(
        "总结输入包: "
        f"{'已生成' if package.get('exists') else '未生成'} | "
        f"窗口摘要 {package.get('window_summaries', 0)} | "
        f"有效问题 {package.get('valid_questions', 0)} | "
        f"主题演进 {package.get('topic_timeline', 0)}"
    )

    debug = report.get("debug", {})
    print(f"调试日志: {debug.get('event_count', 0)} 条 | {debug.get('path', '')}")
    print(f"总结 Markdown: {report.get('final_summary_markdown', {}).get('path', '')}")

    if show_windows:
        print("\n窗口回放:")
        windows = report.get("windows", [])
        if not windows:
            print("- 暂无窗口产物")
        for window in windows:
            print(
                f"- {window.get('window_id', '')} "
                f"[{window.get('start_time', '')} -> {window.get('end_time', '')}] "
                f"{window.get('main_topic', '') or '未命名主题'}"
            )
            print(f"  摘要: {window.get('stage_summary', '') or '暂无'}")
            linked_question_ids = window.get("linked_question_ids", []) or []
            print(f"  关联问题: {', '.join(linked_question_ids) if linked_question_ids else '无'}")


def resolve_session_dir(args: argparse.Namespace) -> Path | None:
    sessions = list_sessions()
    if not sessions:
        return None
    if args.session_id:
        target = SESSIONS_DIR / args.session_id
        return target if target.exists() else None
    return sessions[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="离线回放某个课堂 session 的窗口、知识树和总结产物")
    parser.add_argument("--list", action="store_true", help="列出所有可回放 session")
    parser.add_argument("--session-id", help="指定 session_id")
    parser.add_argument("--latest", action="store_true", help="回放最新 session（默认行为）")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON 报告")
    parser.add_argument("--show-windows", action="store_true", help="打印每个窗口的摘要和关联问题")
    args = parser.parse_args()

    sessions = list_sessions()
    if args.list:
        print_session_list(sessions)
        return 0

    session_dir = resolve_session_dir(args)
    if session_dir is None:
        print("未找到可回放的 session，请先跑一节课生成 data/sessions/<session_id>/。")
        return 1

    report = build_session_report(session_dir)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print_report(report, show_windows=args.show_windows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
