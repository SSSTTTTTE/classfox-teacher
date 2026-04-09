"""
知识树服务
==========
负责窗口结构化结果的增量合并、快照持久化，以及有效问题挂树。
"""

from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
from copy import deepcopy
from datetime import datetime
from typing import Any, Optional

from services.session_storage_service import session_storage_service


class KnowledgeTreeService:
    """管理当前 session 的知识树。"""

    ALLOWED_EDGE_TYPES = {
        "has_subtopic",
        "includes",
        "explains",
        "causes",
        "contrasts_with",
        "example_of",
        "asked_about",
    }

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def _default_tree(self) -> dict[str, Any]:
        return {
            "session_id": session_storage_service.get_active_session_id(),
            "current_main_topic": "",
            "nodes": [],
            "edges": [],
            "updated_at": "",
        }

    def _tree_dir(self) -> str:
        return session_storage_service.ensure_session_subdir("knowledge_tree")

    def _current_tree_path(self) -> str:
        base_dir = self._tree_dir()
        return os.path.join(base_dir, "current_tree.json") if base_dir else ""

    def _node_index_path(self) -> str:
        base_dir = self._tree_dir()
        return os.path.join(base_dir, "node_index.json") if base_dir else ""

    def _snapshot_path(self, window_id: str) -> str:
        snapshots_dir = session_storage_service.ensure_session_subdir("knowledge_tree", "snapshots")
        return os.path.join(snapshots_dir, f"tree_after_{window_id}.json") if snapshots_dir else ""

    def _normalize_title(self, title: str) -> str:
        cleaned = unicodedata.normalize("NFKC", (title or "").strip())
        cleaned = re.sub(r"[\(\[（【].*?[\)\]）】]", "", cleaned)
        cleaned = re.sub(r"\s+", "", cleaned)
        cleaned = re.sub(r"[，,。！？!?；;:：·•]", "", cleaned)
        return cleaned.lower()

    def _slugify(self, title: str) -> str:
        normalized = self._normalize_title(title)
        slug = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "_", normalized, flags=re.IGNORECASE)
        slug = re.sub(r"_+", "_", slug).strip("_")
        return slug[:80] or "node"

    def _load_tree_locked(self) -> dict[str, Any]:
        tree_path = self._current_tree_path()
        if not tree_path or not os.path.exists(tree_path):
            return self._default_tree()

        try:
            with open(tree_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
        except Exception:
            return self._default_tree()

        if not isinstance(payload, dict):
            return self._default_tree()
        payload.setdefault("nodes", [])
        payload.setdefault("edges", [])
        payload.setdefault("current_main_topic", "")
        payload.setdefault("session_id", session_storage_service.get_active_session_id())
        payload.setdefault("updated_at", "")
        return payload

    def _save_tree_locked(self, tree: dict[str, Any], *, window_id: str = "") -> None:
        tree["session_id"] = session_storage_service.get_active_session_id()
        tree["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")

        current_tree_path = self._current_tree_path()
        node_index_path = self._node_index_path()
        if not current_tree_path or not node_index_path:
            return

        os.makedirs(os.path.dirname(current_tree_path), exist_ok=True)
        with open(current_tree_path, "w", encoding="utf-8") as file_obj:
            json.dump(tree, file_obj, ensure_ascii=False, indent=2)

        node_index = {
            node["normalized_title"]: node["node_id"]
            for node in tree.get("nodes", [])
            if node.get("normalized_title") and node.get("node_id")
        }
        with open(node_index_path, "w", encoding="utf-8") as file_obj:
            json.dump(node_index, file_obj, ensure_ascii=False, indent=2)

        if window_id:
            snapshot_path = self._snapshot_path(window_id)
            if snapshot_path:
                os.makedirs(os.path.dirname(snapshot_path), exist_ok=True)
                with open(snapshot_path, "w", encoding="utf-8") as file_obj:
                    json.dump(tree, file_obj, ensure_ascii=False, indent=2)

    def get_current_tree(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._load_tree_locked())

    def get_tree_summary(self, *, snapshot_limit: int = 6) -> dict[str, Any]:
        with self._lock:
            tree = self._load_tree_locked()
            node_type_counts: dict[str, int] = {}
            for node in tree.get("nodes", []):
                node_type = str(node.get("node_type") or "unknown").strip() or "unknown"
                node_type_counts[node_type] = node_type_counts.get(node_type, 0) + 1

            snapshots: list[str] = []
            snapshots_dir = session_storage_service.get_session_path("knowledge_tree", "snapshots")
            if snapshots_dir and os.path.exists(snapshots_dir):
                for filename in sorted(os.listdir(snapshots_dir), reverse=True):
                    if filename.endswith(".json"):
                        snapshots.append(filename)
                    if len(snapshots) >= snapshot_limit:
                        break

            return {
                "session_id": tree.get("session_id", ""),
                "current_main_topic": tree.get("current_main_topic", ""),
                "total_nodes": len(tree.get("nodes", [])),
                "total_edges": len(tree.get("edges", [])),
                "node_type_counts": node_type_counts,
                "recent_snapshots": list(reversed(snapshots)),
                "updated_at": tree.get("updated_at", ""),
            }

    def list_snapshots(self, *, limit: int = 12) -> list[dict[str, Any]]:
        snapshots_dir = session_storage_service.get_session_path("knowledge_tree", "snapshots")
        if not snapshots_dir or not os.path.exists(snapshots_dir):
            return []

        rows: list[dict[str, Any]] = []
        for filename in sorted(os.listdir(snapshots_dir), reverse=True):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(snapshots_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as file_obj:
                    payload = json.load(file_obj)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            rows.append(
                {
                    "snapshot_id": filename[:-5],
                    "filename": filename,
                    "current_main_topic": payload.get("current_main_topic", ""),
                    "total_nodes": len(payload.get("nodes", [])),
                    "total_edges": len(payload.get("edges", [])),
                    "updated_at": payload.get("updated_at", ""),
                }
            )
            if len(rows) >= limit:
                break
        return list(reversed(rows))

    def get_current_main_topic(self) -> str:
        with self._lock:
            tree = self._load_tree_locked()
            return str(tree.get("current_main_topic", "")).strip()

    def get_outline_text(self, *, max_nodes: int = 12) -> str:
        with self._lock:
            tree = self._load_tree_locked()
            nodes = tree.get("nodes", [])
            if not nodes:
                return "暂无知识树"

            lines: list[str] = []
            for node in nodes[:max_nodes]:
                label = node.get("title", "")
                node_type = node.get("node_type", "")
                parent_id = node.get("parent_id", "")
                if parent_id:
                    lines.append(f"- {node_type}: {label} (parent={parent_id})")
                else:
                    lines.append(f"- {node_type}: {label}")
            return "\n".join(lines)

    def _find_node_locked(self, tree: dict[str, Any], *, normalized_title: str) -> Optional[dict[str, Any]]:
        if not normalized_title:
            return None
        for node in tree.get("nodes", []):
            if node.get("normalized_title") == normalized_title:
                return node
        return None

    def _ensure_node_locked(
        self,
        tree: dict[str, Any],
        *,
        title: str,
        node_type: str,
        parent_id: str,
        window_id: str,
        timestamp: str,
    ) -> Optional[dict[str, Any]]:
        cleaned_title = (title or "").strip()
        if not cleaned_title:
            return None

        normalized_title = self._normalize_title(cleaned_title)
        if not normalized_title:
            return None

        existing = self._find_node_locked(tree, normalized_title=normalized_title)
        if existing is not None:
            if parent_id and not existing.get("parent_id"):
                existing["parent_id"] = parent_id
            if cleaned_title != existing.get("title") and cleaned_title not in existing.get("aliases", []):
                existing.setdefault("aliases", []).append(cleaned_title)
            window_ids = existing.setdefault("supporting_window_ids", [])
            if window_id and window_id not in window_ids:
                window_ids.append(window_id)
            existing["last_updated_at"] = timestamp or existing.get("last_updated_at", "")
            existing["status"] = "active"
            return existing

        node_id = f"{node_type}_{self._slugify(cleaned_title)}"
        node = {
            "node_id": node_id,
            "session_id": session_storage_service.get_active_session_id(),
            "node_type": node_type,
            "title": cleaned_title,
            "normalized_title": normalized_title,
            "parent_id": parent_id,
            "aliases": [],
            "supporting_window_ids": [window_id] if window_id else [],
            "first_seen_at": timestamp,
            "last_updated_at": timestamp,
            "status": "active",
        }
        tree.setdefault("nodes", []).append(node)
        return node

    def _ensure_edge_locked(
        self,
        tree: dict[str, Any],
        *,
        source_node_id: str,
        target_node_id: str,
        edge_type: str,
        window_id: str,
    ) -> Optional[dict[str, Any]]:
        if not source_node_id or not target_node_id or source_node_id == target_node_id:
            return None

        normalized_edge_type = edge_type if edge_type in self.ALLOWED_EDGE_TYPES else "includes"

        for edge in tree.get("edges", []):
            if (
                edge.get("source_node_id") == source_node_id
                and edge.get("target_node_id") == target_node_id
                and edge.get("edge_type") == normalized_edge_type
            ):
                supporting = edge.setdefault("supporting_window_ids", [])
                if window_id and window_id not in supporting:
                    supporting.append(window_id)
                return edge

        edge_id = f"e_{len(tree.get('edges', [])) + 1:04d}"
        edge = {
            "edge_id": edge_id,
            "session_id": session_storage_service.get_active_session_id(),
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "edge_type": normalized_edge_type,
            "supporting_window_ids": [window_id] if window_id else [],
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        tree.setdefault("edges", []).append(edge)
        return edge

    def merge_window_record(self, window_record: dict[str, Any]) -> dict[str, Any]:
        window_id = str(window_record.get("window_id") or "").strip()
        timestamp = str(window_record.get("end_time") or window_record.get("start_time") or "").strip()
        main_topic = str(window_record.get("main_topic") or "").strip()

        with self._lock:
            tree = self._load_tree_locked()
            topic_node = self._ensure_node_locked(
                tree,
                title=main_topic or "未命名主题",
                node_type="topic",
                parent_id="",
                window_id=window_id,
                timestamp=timestamp,
            )
            topic_node_id = topic_node.get("node_id", "") if topic_node else ""

            subtopic_nodes: list[dict[str, Any]] = []
            for title in window_record.get("extracted_subtopics", []) or []:
                node = self._ensure_node_locked(
                    tree,
                    title=str(title),
                    node_type="subtopic",
                    parent_id=topic_node_id,
                    window_id=window_id,
                    timestamp=timestamp,
                )
                if node:
                    subtopic_nodes.append(node)
                    if topic_node_id:
                        self._ensure_edge_locked(
                            tree,
                            source_node_id=topic_node_id,
                            target_node_id=node["node_id"],
                            edge_type="has_subtopic",
                            window_id=window_id,
                        )

            concept_parent_id = subtopic_nodes[0]["node_id"] if subtopic_nodes else topic_node_id
            concept_nodes: list[dict[str, Any]] = []
            for title in window_record.get("extracted_concepts", []) or []:
                node = self._ensure_node_locked(
                    tree,
                    title=str(title),
                    node_type="concept",
                    parent_id=concept_parent_id,
                    window_id=window_id,
                    timestamp=timestamp,
                )
                if node:
                    concept_nodes.append(node)
                    if concept_parent_id:
                        self._ensure_edge_locked(
                            tree,
                            source_node_id=concept_parent_id,
                            target_node_id=node["node_id"],
                            edge_type="includes",
                            window_id=window_id,
                        )

            for fact in window_record.get("facts", []) or []:
                node = self._ensure_node_locked(
                    tree,
                    title=str(fact),
                    node_type="fact",
                    parent_id=topic_node_id,
                    window_id=window_id,
                    timestamp=timestamp,
                )
                if node and topic_node_id:
                    self._ensure_edge_locked(
                        tree,
                        source_node_id=topic_node_id,
                        target_node_id=node["node_id"],
                        edge_type="includes",
                        window_id=window_id,
                    )

            for example in window_record.get("examples", []) or []:
                node = self._ensure_node_locked(
                    tree,
                    title=str(example),
                    node_type="example",
                    parent_id=topic_node_id,
                    window_id=window_id,
                    timestamp=timestamp,
                )
                if node and topic_node_id:
                    self._ensure_edge_locked(
                        tree,
                        source_node_id=node["node_id"],
                        target_node_id=topic_node_id,
                        edge_type="example_of",
                        window_id=window_id,
                    )

            for relation in window_record.get("extracted_relations", []) or []:
                if not isinstance(relation, dict):
                    continue
                source_title = str(relation.get("source") or "").strip()
                target_title = str(relation.get("target") or "").strip()
                if not source_title or not target_title:
                    continue
                source_node = self._ensure_node_locked(
                    tree,
                    title=source_title,
                    node_type="concept",
                    parent_id=concept_parent_id or topic_node_id,
                    window_id=window_id,
                    timestamp=timestamp,
                )
                target_node = self._ensure_node_locked(
                    tree,
                    title=target_title,
                    node_type="concept",
                    parent_id=concept_parent_id or topic_node_id,
                    window_id=window_id,
                    timestamp=timestamp,
                )
                if source_node and target_node:
                    self._ensure_edge_locked(
                        tree,
                        source_node_id=source_node["node_id"],
                        target_node_id=target_node["node_id"],
                        edge_type=str(relation.get("type") or "includes"),
                        window_id=window_id,
                    )

            tree["current_main_topic"] = topic_node.get("title", "") if topic_node else main_topic
            self._save_tree_locked(tree, window_id=window_id)
            return {
                "main_topic_id": topic_node_id,
                "main_topic_title": topic_node.get("title", "") if topic_node else "",
                "tree": deepcopy(tree),
            }

    def _best_match_node_locked(
        self,
        tree: dict[str, Any],
        *,
        question_text: str,
        preferred_titles: list[str] | None = None,
    ) -> Optional[dict[str, Any]]:
        preferred_titles = preferred_titles or []
        preferred_normalized = {self._normalize_title(title) for title in preferred_titles if title}
        normalized_question = self._normalize_title(question_text)
        if not normalized_question:
            return None

        for node in tree.get("nodes", []):
            if node.get("normalized_title") in preferred_normalized:
                return node

        best_node: Optional[dict[str, Any]] = None
        best_score = 0.0
        question_chars = set(normalized_question)

        for node in tree.get("nodes", []):
            node_title = str(node.get("normalized_title") or "")
            if not node_title:
                continue
            if node_title in normalized_question or normalized_question in node_title:
                return node
            overlap = len(question_chars & set(node_title)) / max(len(set(node_title) | question_chars), 1)
            if overlap > best_score:
                best_score = overlap
                best_node = node

        return best_node if best_score >= 0.18 else None

    def link_valid_question(
        self,
        question_record: dict[str, Any],
        *,
        preferred_titles: list[str] | None = None,
    ) -> dict[str, Any]:
        question_text = str(question_record.get("question_text") or question_record.get("raw_text") or "").strip()
        timestamp = str(question_record.get("trigger_time") or question_record.get("confirmed_at") or "").strip()
        window_id = str(question_record.get("window_id") or "").strip()

        with self._lock:
            tree = self._load_tree_locked()
            matched_node = self._best_match_node_locked(
                tree,
                question_text=question_text,
                preferred_titles=preferred_titles,
            )
            unresolved_link = False

            if matched_node is None:
                unresolved_link = True
                current_main_topic = str(tree.get("current_main_topic") or "").strip()
                matched_node = self._ensure_node_locked(
                    tree,
                    title=current_main_topic or "待确认主题",
                    node_type="topic",
                    parent_id="",
                    window_id=window_id,
                    timestamp=timestamp,
                )

            question_node = self._ensure_node_locked(
                tree,
                title=question_text,
                node_type="question",
                parent_id="",
                window_id=window_id,
                timestamp=timestamp,
            )
            if question_node and matched_node:
                self._ensure_edge_locked(
                    tree,
                    source_node_id=question_node["node_id"],
                    target_node_id=matched_node["node_id"],
                    edge_type="asked_about",
                    window_id=window_id,
                )

            self._save_tree_locked(tree)
            return {
                "status": "unresolved_link" if unresolved_link else "linked_to_tree",
                "linked_topic_id": matched_node.get("node_id", "") if matched_node else "",
                "linked_topic_title": matched_node.get("title", "") if matched_node else "",
                "question_node_id": question_node.get("node_id", "") if question_node else "",
                "knowledge_tree_snapshot": deepcopy(tree),
            }


knowledge_tree_service = KnowledgeTreeService()
