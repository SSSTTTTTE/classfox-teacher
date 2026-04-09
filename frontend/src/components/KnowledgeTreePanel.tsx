import { useEffect, useMemo, useState } from "react";
import {
  getKnowledgeTree,
  getKnowledgeTreeSnapshots,
  type KnowledgeTreePayload,
  type KnowledgeTreeSummary,
} from "../services/api";
import { PANEL_WINDOW_SIZES } from "../services/windowSizing";

interface KnowledgeTreePanelProps {
  visible: boolean;
  onClose: () => void;
  liveTree?: KnowledgeTreePayload | null;
  highlightedNodeIds?: string[];
}

type TreeNodeMap = Record<string, Array<KnowledgeTreePayload["nodes"][number]>>;

function typeLabel(nodeType: string) {
  const mapping: Record<string, string> = {
    topic: "主题",
    subtopic: "子主题",
    concept: "概念",
    fact: "事实",
    example: "例子",
    question: "问题",
  };
  return mapping[nodeType] || nodeType;
}

export default function KnowledgeTreePanel({
  visible,
  onClose,
  liveTree = null,
  highlightedNodeIds = [],
}: KnowledgeTreePanelProps) {
  const [tree, setTree] = useState<KnowledgeTreePayload | null>(null);
  const [summary, setSummary] = useState<KnowledgeTreeSummary | null>(null);
  const [snapshots, setSnapshots] = useState<Array<{
    snapshot_id: string;
    filename: string;
    current_main_topic: string;
    total_nodes: number;
    total_edges: number;
    updated_at: string;
  }>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    setLoading(true);
    setError(null);
    Promise.all([getKnowledgeTree(), getKnowledgeTreeSnapshots(6)])
      .then(([treeRes, snapshotRes]) => {
        setTree(treeRes.knowledge_tree);
        setSummary(treeRes.summary);
        setSnapshots(snapshotRes.snapshots);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "加载知识树失败"))
      .finally(() => setLoading(false));
  }, [visible]);

  useEffect(() => {
    if (!visible || !liveTree) return;
    setTree(liveTree);
    setSummary((prev) => {
      const nodeTypeCounts: Record<string, number> = {};
      for (const node of liveTree.nodes ?? []) {
        nodeTypeCounts[node.node_type] = (nodeTypeCounts[node.node_type] || 0) + 1;
      }
      return {
        session_id: liveTree.session_id,
        current_main_topic: liveTree.current_main_topic,
        total_nodes: liveTree.nodes.length,
        total_edges: liveTree.edges.length,
        node_type_counts: nodeTypeCounts,
        recent_snapshots: prev?.recent_snapshots ?? [],
        updated_at: liveTree.updated_at,
      };
    });
  }, [liveTree, visible]);

  useEffect(() => {
    if (!visible) return;
    (async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const { LogicalSize } = await import("@tauri-apps/api/dpi");
        await getCurrentWindow().setSize(
          new LogicalSize(PANEL_WINDOW_SIZES.knowledgeTree.width, PANEL_WINDOW_SIZES.knowledgeTree.height)
        );
      } catch {
        /* 忽略窗口操作错误 */
      }
    })();
  }, [visible]);

  const roots = useMemo(() => {
    if (!tree?.nodes?.length) return [];
    const nodeIds = new Set(tree.nodes.map((node) => node.node_id));
    return tree.nodes.filter((node) => !node.parent_id || !nodeIds.has(node.parent_id));
  }, [tree]);

  const childMap = useMemo<TreeNodeMap>(() => {
    const map: TreeNodeMap = {};
    for (const node of tree?.nodes ?? []) {
      const parentId = node.parent_id || "__root__";
      if (!map[parentId]) map[parentId] = [];
      map[parentId].push(node);
    }
    Object.values(map).forEach((items) =>
      items.sort((a, b) => {
        if (a.node_type !== b.node_type) return a.node_type.localeCompare(b.node_type, "zh-Hans-CN");
        return a.title.localeCompare(b.title, "zh-Hans-CN");
      })
    );
    return map;
  }, [tree]);

  const highlightedSet = useMemo(() => new Set(highlightedNodeIds), [highlightedNodeIds]);
  const snapshotItems = useMemo(
    () =>
      snapshots.length
        ? snapshots
        : (summary?.recent_snapshots ?? []).map((name) => ({
            snapshot_id: name.replace(/\.json$/, ""),
            filename: name,
            current_main_topic: "",
            total_nodes: 0,
            total_edges: 0,
            updated_at: "",
          })),
    [snapshots, summary?.recent_snapshots]
  );

  const renderNode = (node: KnowledgeTreePayload["nodes"][number], depth: number) => {
    const children = childMap[node.node_id] ?? [];
    return (
      <div key={node.node_id} className="space-y-2">
        <div
          className="rounded-2xl border border-white/10 bg-white/5 px-3 py-2"
          style={{ marginLeft: `${depth * 14}px` }}
        >
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-white/10 bg-black/15 px-2 py-0.5 text-[10px] text-white/58">
              {typeLabel(node.node_type)}
            </span>
            {highlightedSet.has(node.node_id) && (
              <span className="rounded-full border border-cyan-400/25 bg-cyan-500/16 px-2 py-0.5 text-[10px] text-cyan-100">
                新增
              </span>
            )}
            <span className="min-w-0 flex-1 text-xs font-medium text-white/86">{node.title}</span>
          </div>
          <div className="mt-1 text-[10px] leading-5 text-white/42">
            支撑窗口 {node.supporting_window_ids.length} 个 · 最近更新 {node.last_updated_at || "暂无"}
          </div>
        </div>
        {children.map((child) => renderNode(child, depth + 1))}
      </div>
    );
  };

  if (!visible) return null;

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden p-3 animate-in fade-in duration-300">
      <div className="mb-3 grid grid-cols-2 gap-2">
        <div className="rounded-2xl border border-cyan-400/18 bg-cyan-500/10 p-3">
          <div className="text-[10px] uppercase tracking-[0.22em] text-cyan-100/55">Current Topic</div>
          <div className="mt-1 text-sm font-semibold text-white/88">
            {summary?.current_main_topic || tree?.current_main_topic || "暂无主主题"}
          </div>
          <div className="mt-2 text-[10px] leading-5 text-white/42">
            节点 {summary?.total_nodes ?? tree?.nodes.length ?? 0} · 连线 {summary?.total_edges ?? tree?.edges.length ?? 0}
          </div>
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
          <div className="text-[10px] uppercase tracking-[0.22em] text-white/45">Recent Snapshots</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {snapshotItems.slice(-4).map((snapshot) => (
              <span
                key={snapshot.snapshot_id}
                className="rounded-full border border-white/10 bg-black/20 px-2 py-0.5 text-[10px] text-white/60"
              >
                {snapshot.filename.replace(".json", "")}
              </span>
            ))}
            {!snapshots.length && !(summary?.recent_snapshots?.length) && (
              <span className="text-[10px] text-white/38">尚未生成快照</span>
            )}
          </div>
        </div>
      </div>

      <div className="mb-3 flex flex-wrap gap-1.5">
        {Object.entries(summary?.node_type_counts ?? {}).map(([type, count]) => (
          <span
            key={type}
            className="rounded-full border border-white/10 bg-black/20 px-2 py-1 text-[10px] text-white/66"
          >
            {typeLabel(type)} {count}
          </span>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        {loading && (
          <div className="flex items-center justify-center py-8 text-white/55">
            <div className="mr-2 h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
            <span className="text-xs">正在加载知识树...</span>
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/15 px-3 py-2 text-xs text-red-200">
            ⚠️ {error}
          </div>
        )}

        {!loading && !error && !(tree?.nodes.length) && (
          <div className="flex flex-col items-center justify-center py-10 text-xs text-white/38">
            <span className="text-2xl">🌿</span>
            <span className="mt-2">当前 session 还没有生成知识树节点</span>
          </div>
        )}

        {!loading && !error && (tree?.nodes.length ?? 0) > 0 && (
          <div className="space-y-2">
            {roots.map((node) => renderNode(node, 0))}
          </div>
        )}
      </div>

      <div className="absolute bottom-12 left-3 right-3 flex justify-center border-t border-white/10 bg-[rgba(3,10,20,0.92)] pt-3">
        <button
          onClick={onClose}
          className="px-4 py-1.5 text-xs rounded-lg bg-white/10 text-white/60 hover:bg-white/20 hover:text-white transition-all duration-150"
        >
          收起面板
        </button>
      </div>
    </div>
  );
}
