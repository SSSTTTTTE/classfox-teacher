/**
 * WebSocket 连接 Hook（教师版）
 * ==============================
 * 管理与后端的 WebSocket 连接，接收实时学生提问检测事件
 */

import { useState, useEffect, useRef, useCallback } from "react";
import type { KnowledgeTreePayload } from "../services/api";

/** 学生提问检测事件 */
export interface QuestionEvent {
  type: "question_detected";
  text: string;
  timestamp: string;
  confidence: "high" | "low";
}

/** 实时转录更新事件 */
export interface TranscriptUpdateEvent {
  type: "transcript_update";
  text: string;
  timestamp: string;
  is_final?: boolean;
}

/** 实时总结更新事件 */
export interface RealtimeSummaryCard {
  section_title: string;
  points: string[];
  flow_title?: string;
  flow_steps?: string[];
}

export interface SummaryUpdateEvent {
  type: "summary_update";
  summary_text: string;
  cards: RealtimeSummaryCard[];
}

export interface FinalSummaryUpdateEvent {
  type: "final_summary_update";
  active: boolean;
  phase: "idle" | "preparing" | "thinking" | "writing" | "saving" | "completed" | "failed";
  message: string;
  model: string;
  course_name: string;
  thinking_text: string;
  content_text: string;
  filename: string;
  error: string;
  started_at: string;
  finished_at: string;
}

export interface KnowledgeTreeUpdateEvent {
  type: "knowledge_tree_update";
  current_main_topic: string;
  knowledge_tree: KnowledgeTreePayload;
}

const WS_URL = "ws://127.0.0.1:8765/api/ws/alerts";

export function useWebSocket() {
  const [isConnected, setIsConnected] = useState(false);
  const [lastQuestion, setLastQuestion] = useState<QuestionEvent | null>(null);
  const [questionActive, setQuestionActive] = useState(false);
  const [recentTranscripts, setRecentTranscripts] = useState<string[]>([]);
  const [partialTranscript, setPartialTranscript] = useState<string>("");
  const [liveSummary, setLiveSummary] = useState<string>("");
  const [liveSummaryCards, setLiveSummaryCards] = useState<RealtimeSummaryCard[]>([]);
  const [finalSummaryStatus, setFinalSummaryStatus] = useState<FinalSummaryUpdateEvent | null>(null);
  const [knowledgeTree, setKnowledgeTree] = useState<KnowledgeTreePayload | null>(null);
  const [knowledgeTreeHighlightNodeIds, setKnowledgeTreeHighlightNodeIds] = useState<string[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const shouldReconnectRef = useRef(false);
  const recentQuestionRef = useRef<{ text: string; receivedAt: number } | null>(null);

  /** 建立 WebSocket 连接 */
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    shouldReconnectRef.current = true;

    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setIsConnected(true);
      console.log("[WS] 已连接到课堂监听服务");

      // 心跳保活，每 30 秒发一次 ping
      heartbeatRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send("ping");
        }
      }, 30000);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as
          | QuestionEvent
          | TranscriptUpdateEvent
          | SummaryUpdateEvent
          | FinalSummaryUpdateEvent
          | KnowledgeTreeUpdateEvent;
        if (data.type === "question_detected") {
          const normalizedText = data.text.trim();
          const now = Date.now();
          const recentQuestion = recentQuestionRef.current;
          if (
            normalizedText &&
            recentQuestion &&
            recentQuestion.text === normalizedText &&
            now - recentQuestion.receivedAt < 6000
          ) {
            return;
          }
          recentQuestionRef.current = { text: normalizedText, receivedAt: now };
          console.log("[WS] 检测到学生提问:", data);
          setLastQuestion({ ...data, text: normalizedText });
          setQuestionActive(true);
        } else if (data.type === "transcript_update") {
          if (data.is_final) {
            setRecentTranscripts((prev) => {
              const nextText = data.text.trim();
              if (!nextText) return prev;
              if (prev[prev.length - 1] === nextText) return prev;
              return [...prev, nextText].slice(-3);
            });
            setPartialTranscript("");
          } else {
            setPartialTranscript(data.text);
          }
        } else if (data.type === "summary_update") {
          setLiveSummary(data.summary_text.trim());
          setLiveSummaryCards(data.cards ?? []);
        } else if (data.type === "final_summary_update") {
          setFinalSummaryStatus(data);
        } else if (data.type === "knowledge_tree_update") {
          setKnowledgeTree((prev) => {
            const previousIds = new Set((prev?.nodes ?? []).map((node) => node.node_id));
            const nextTree = data.knowledge_tree;
            const newNodeIds = (nextTree.nodes ?? [])
              .map((node) => node.node_id)
              .filter((nodeId) => nodeId && !previousIds.has(nodeId));
            setKnowledgeTreeHighlightNodeIds(newNodeIds);
            return nextTree;
          });
        }
      } catch {
        // pong 或其他非 JSON 消息忽略
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
      if (shouldReconnectRef.current) {
        console.log("[WS] 连接断开，5 秒后重连...");
        setTimeout(connect, 5000);
      }
    };

    ws.onerror = (err) => {
      console.error("[WS] 连接错误:", err);
      ws.close();
    };

    wsRef.current = ws;
  }, []);

  /** 断开连接 */
  const disconnect = useCallback((options?: { preserveFinalSummary?: boolean }) => {
    shouldReconnectRef.current = false;
    if (heartbeatRef.current) clearInterval(heartbeatRef.current);
    wsRef.current?.close();
    wsRef.current = null;
    setIsConnected(false);
    setRecentTranscripts([]);
    setPartialTranscript("");
    setLiveSummary("");
    setLiveSummaryCards([]);
    setKnowledgeTree(null);
    setKnowledgeTreeHighlightNodeIds([]);
    if (!options?.preserveFinalSummary) {
      setFinalSummaryStatus(null);
    }
    recentQuestionRef.current = null;
  }, []);

  const clearFinalSummary = useCallback(() => {
    setFinalSummaryStatus(null);
  }, []);

  const applyFinalSummaryStatus = useCallback((status: FinalSummaryUpdateEvent | null) => {
    setFinalSummaryStatus(status);
  }, []);

  const applyKnowledgeTreeSnapshot = useCallback((tree: KnowledgeTreePayload | null) => {
    setKnowledgeTree((prev) => {
      const previousIds = new Set((prev?.nodes ?? []).map((node) => node.node_id));
      const nextIds = new Set((tree?.nodes ?? []).map((node) => node.node_id));
      const newNodeIds = Array.from(nextIds).filter((nodeId) => !previousIds.has(nodeId));
      setKnowledgeTreeHighlightNodeIds(newNodeIds);
      return tree;
    });
  }, []);

  /** 关闭提问卡片 */
  const dismissQuestion = useCallback(() => {
    setQuestionActive(false);
  }, []);

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    isConnected,
    lastQuestion,
    questionActive,
    recentTranscripts,
    partialTranscript,
    liveSummary,
    liveSummaryCards,
    finalSummaryStatus,
    knowledgeTree,
    knowledgeTreeHighlightNodeIds,
    connect,
    disconnect,
    dismissQuestion,
    clearFinalSummary,
    applyFinalSummaryStatus,
    applyKnowledgeTreeSnapshot,
  };
}
