'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { WebSocketMessage, MessageType, Agent, GenerationResult, AgentStatus } from '@/types';
import { resolvePublicMediaUrl } from '@/lib/mediaPaths';
import { generateId } from '@/lib/utils';

interface UseWebSocketOptions {
  url?: string;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
}

export const useWebSocket = (options: UseWebSocketOptions = {}) => {
  // Resolve WS URL with robust fallbacks to avoid localhost/IPv6 pitfalls
  const resolveWsUrl = (): string => {
    // Explicit option takes precedence
    if (options.url) return options.url;
    // Env override
    const envWs = process.env.NEXT_PUBLIC_WS_URL;
    if (envWs && typeof envWs === 'string') return envWs;
    // Derive from API URL if provided
    const envApi = process.env.NEXT_PUBLIC_API_URL;
    if (envApi && typeof envApi === 'string') {
      try {
        const u = new URL(envApi);
        const scheme = u.protocol === 'https:' ? 'wss' : 'ws';
        return `${scheme}://${u.host}/api/v1/ws/connect`;
      } catch {}
    }
    // Browser location as last resort; prefer 127.0.0.1 to bypass ::1 issues
    if (typeof window !== 'undefined') {
      const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const host = window.location.hostname === 'localhost' ? '127.0.0.1' : window.location.hostname;
      const port = '8000';
      return `${scheme}://${host}:${port}/api/v1/ws/connect`;
    }
    // Server-side default
    return 'ws://127.0.0.1:8000/api/v1/ws/connect';
  };

  const {
    url = resolveWsUrl(),
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
    onOpen,
    onClose,
    onError,
  } = options;

  const ws = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimeoutId = useRef<NodeJS.Timeout | null>(null);
  const isManualClose = useRef(false);
  const isConnecting = useRef(false);

  const {
    setWSConnected,
    updateAgent,
    addResult,
    updateResult,
    addNotification,
    setCurrentStep,
    currentRequest,
  } = useAppStore();

  const eventStateToAgentStatus: Record<string, AgentStatus> = {
    running: 'working',
    started: 'working',
    processing: 'working',
    in_progress: 'working',
    completed: 'completed',
    success: 'completed',
    failed: 'error',
    error: 'error',
    idle: 'idle',
    waiting: 'waiting',
    thinking: 'thinking',
  };

  const agentTypeMap: Record<string, string> = {
    concept_planner: 'concept-generator',
    script_writer: 'script-writer',
    image_generator: 'image-generator',
    video_generator: 'video-generator',
    audio_generator: 'voice-synthesizer',
    voice_synthesizer: 'voice-synthesizer',
    video_composer: 'video-composer',
    quality_checker: 'quality-controller',
    orchestrator: 'orchestrator',
  };

  const getAgentId = (agentType: string) => {
    const key = (agentType || '').toLowerCase();
    return agentTypeMap[key] || agentType;
  };

  const connect = useCallback(() => {
    try {
      // Prevent duplicate connections (React StrictMode / double mount)
      if (ws.current && (ws.current.readyState === WebSocket.OPEN || ws.current.readyState === WebSocket.CONNECTING)) {
        console.log('WebSocket already open/connecting, skip new connect');
        return;
      }
      if (isConnecting.current) {
        console.log('WebSocket connect already in progress');
        return;
      }
      isConnecting.current = true;
      console.log('Connecting WebSocket to:', url);
      ws.current = new WebSocket(url);

      ws.current.onopen = () => {
        console.log('WebSocket connected');
        setWSConnected(true);
        reconnectAttempts.current = 0;
        isConnecting.current = false;
        onOpen?.();

        addNotification({
          type: 'success',
          title: 'Connected',
          message: 'Real-time updates enabled',
          autoClose: 3000,
        });

        // Send initial subscription (backend expects subscribe_task)
        if (currentRequest?.id) {
          // Backend expects top-level task_id in subscribe_task message
          ws.current?.send(
            JSON.stringify({ type: 'subscribe_task', task_id: currentRequest.id, timestamp: new Date() })
          );
        }
      };

      ws.current.onclose = (event) => {
        console.log('WebSocket disconnected', event.code, event.reason);
        setWSConnected(false);
        isConnecting.current = false;
        onClose?.();

        if (!isManualClose.current && reconnectAttempts.current < maxReconnectAttempts) {
          addNotification({
            type: 'warning',
            title: 'Connection Lost',
            message: `Attempting to reconnect... (${reconnectAttempts.current + 1}/${maxReconnectAttempts})`,
            autoClose: 5000,
          });

          reconnectTimeoutId.current = setTimeout(() => {
            reconnectAttempts.current++;
            connect();
          }, reconnectInterval);
        } else if (reconnectAttempts.current >= maxReconnectAttempts) {
          addNotification({
            type: 'error',
            title: 'Connection Failed',
            message: 'Unable to establish real-time connection. Please refresh the page.',
            autoClose: 10000,
          });
        }
      };

      ws.current.onerror = (error) => {
        console.warn('WebSocket error (non-fatal in dev):', error);
        isConnecting.current = false;
        onError?.(error);
        
        addNotification({
          type: 'warning',
          title: '实时连接异常',
          message: '正在重试或使用轮询备选方案',
          autoClose: 3000,
        });
      };

      ws.current.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          handleMessage(message);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      setWSConnected(false);
    }
  }, [url, reconnectInterval, maxReconnectAttempts, onOpen, onClose, onError, setWSConnected, addNotification, currentRequest]);

  const disconnect = useCallback(() => {
    isManualClose.current = true;
    
    if (reconnectTimeoutId.current) {
      clearTimeout(reconnectTimeoutId.current);
      reconnectTimeoutId.current = null;
    }

    if (ws.current) {
      ws.current.close(1000, 'Manual close');
      ws.current = null;
    }

    setWSConnected(false);
  }, [setWSConnected]);

  const sendMessage = useCallback((message: Omit<WebSocketMessage, 'timestamp'>) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      const fullMessage: WebSocketMessage = {
        ...message,
        timestamp: new Date(),
      };
      
      ws.current.send(JSON.stringify(fullMessage));
      return true;
    }
    
    console.warn('WebSocket is not connected');
    return false;
  }, []);

  const handleAgentStatusUpdate = useCallback((data: any) => {
    const { agentId, status, currentTask, estimatedTime, progress } = data;
    
    updateAgent(agentId, {
      status,
      currentTask,
      estimatedTime,
      progress: progress || 0,
    });

    // Show notification for significant status changes
    if (status === 'working') {
      addNotification({
        type: 'info',
        title: 'Agent Started',
        message: `${data.agentName || agentId} is now working on your video`,
        autoClose: 3000,
      });
    } else if (status === 'completed') {
      addNotification({
        type: 'success',
        title: 'Agent Completed',
        message: `${data.agentName || agentId} has finished its task`,
        autoClose: 3000,
      });
    }
  }, [updateAgent, addNotification]);

  const handleProgressUpdate = useCallback((data: any) => {
    const { agentId, progress, message: progressMessage } = data;
    
    updateAgent(agentId, {
      progress: progress || 0,
      currentTask: progressMessage,
    });
  }, [updateAgent]);

  // Map backend event.progress to frontend update
  const handleEventProgress = useCallback((msg: any) => {
    try {
      const payload = msg.payload || {};
      const agentType = String((msg as any).agent_type || '').toLowerCase();
      const agentId = getAgentId(agentType) || (msg as any).agent_name || agentType || 'unknown-agent';
      const progress = payload.progress ?? payload.percentage ?? 0;
      const current_step = payload.current_step || payload.substep || '';
      updateAgent(agentId, {
        progress: progress || 0,
        currentTask: current_step,
      });
    } catch (e) {
      console.warn('Failed to handle event.progress:', e);
    }
  }, [updateAgent]);

  // Map backend agent_progress to frontend update
  const handleBackendAgentProgress = useCallback((msg: any) => {
    try {
      const typeToId: Record<string, string> = {
        concept_planner: 'concept-generator',
        script_writer: 'script-writer',
        image_generator: 'image-generator',
        video_generator: 'video-generator',
        audio_generator: 'voice-synthesizer',
        video_composer: 'video-composer',
        quality_checker: 'quality-controller',
      };
      const agentType = String((msg as any).agent_type || '').toLowerCase();
      const agentId = typeToId[agentType] || (msg as any).agent_name || agentType || 'unknown-agent';
      const progress = (msg as any).progress ?? 0;
      const rawStatus = String((msg as any).status || '').toLowerCase();
      const status = eventStateToAgentStatus[rawStatus] || 'working';
      const current_step = (msg as any).current_step || '';
      updateAgent(agentId, {
        status,
        progress,
        currentTask: current_step,
      });
    } catch (e) {
      console.warn('Failed to handle agent_progress:', e);
    }
  }, [updateAgent]);

  // Concept plan ready → update scenesPlanned
  const handleConceptPlanReady = useCallback((msg: any) => {
    try {
      const count = (msg as any).scenes_count ?? ((msg as any).data && (msg as any).data.scenes_count);
      if (typeof count === 'number') {
        useAppStore.getState().setScenesPlanned(count);
      }
    } catch (e) {
      console.warn('Failed to handle concept_plan_ready:', e);
    }
  }, []);

  const handleImageAssetsReady = useCallback((msg: any) => {
    try {
      const count = (msg as any).images_count ?? ((msg as any).data && (msg as any).data.images_count);
      if (typeof count === 'number') {
        useAppStore.getState().setImagesGenerated(count);
      }
    } catch (e) {
      console.warn('Failed to handle image_assets_ready:', e);
    }
  }, []);

  const handleVideoAssetsReady = useCallback((msg: any) => {
    try {
      const count = (msg as any).videos_count ?? ((msg as any).data && (msg as any).data.videos_count);
      if (typeof count === 'number') {
        useAppStore.getState().setVideosGenerated(count);
      }
    } catch (e) {
      console.warn('Failed to handle video_assets_ready:', e);
    }
  }, []);

  const handleWorkflowCompleted = useCallback((msg: any) => {
    try {
      const results = (msg && (msg.results || (msg.data && msg.data.results))) || {};
      const composer = results.video_composer || results['video-composer'] || {};
      const qc = results.quality_checker || results['quality-checker'] || {};
      const candidates: Array<string | undefined> = [
        composer.final_video_url,
        composer.final_video_path,
        qc.final_video_url,
        qc.final_video_path,
        results.final_video_url,
      ];
      const picked = candidates.find((c) => typeof c === 'string' && c.length > 0);
      const publicUrl = resolvePublicMediaUrl(picked);
      if (publicUrl) {
        useAppStore.getState().setFinalVideoUrl(publicUrl);
      } else if (picked) {
        useAppStore.getState().setFinalVideoUrl(String(picked));
      }
    } catch (e) {
      // non-fatal
    }

    addNotification({
      type: 'success',
      title: '生成完成',
      message: '多智能体协作已完成，进入结果预览',
      autoClose: 5000,
    });
    setCurrentStep('review' as any);
  }, [addNotification, setCurrentStep]);

  const handleWorkflowFailed = useCallback((msg: any) => {
    addNotification({
      type: 'error',
      title: '生成失败',
      message: msg.error || '多智能体协作执行失败',
      autoClose: 8000,
    });
    setCurrentStep('input' as any);
  }, [addNotification, setCurrentStep]);

  // Handle new event.state messages
  const handleEventState = useCallback((msg: any) => {
    try {
      const payload = msg.payload || {};
      const state = payload.state || payload.status;
      const normalized = String(state || '').toLowerCase();

      switch (normalized) {
        case 'concept_plan_ready':
          handleConceptPlanReady({ ...msg, ...payload });
          break;
        case 'image_assets_ready':
          handleImageAssetsReady({ ...msg, ...payload });
          break;
        case 'video_assets_ready':
          handleVideoAssetsReady({ ...msg, ...payload });
          break;
        case 'workflow_completed':
        case 'enhanced_workflow_completed':
          handleWorkflowCompleted({ ...msg, results: payload.results, ...payload });
          break;
        case 'workflow_failed':
        case 'enhanced_workflow_failed':
          handleWorkflowFailed({ ...msg, error: payload.error, ...payload });
          break;
        default:
          if (msg.agent_name) {
            const agentId = getAgentId(msg.agent_name);
            const status = eventStateToAgentStatus[normalized];
            if (status) {
              updateAgent(agentId, { status });
            }
          }
      }
    } catch (e) {
      console.warn('Failed to handle event.state:', e);
    }
  }, [handleConceptPlanReady, handleImageAssetsReady, handleVideoAssetsReady, handleWorkflowCompleted, handleWorkflowFailed, updateAgent]);

  const handleConnectionEstablished = useCallback((msg: any) => {
    setWSConnected(true);
  }, [setWSConnected]);

  const handleSubscriptionConfirmed = useCallback((msg: any) => {
    // no-op
  }, []);

  const handleResultReady = useCallback((data: any) => {
    const result: GenerationResult = {
      id: data.id || generateId(),
      requestId: data.requestId,
      type: data.type,
      status: data.status || 'completed',
      data: data.content,
      createdAt: new Date(data.createdAt || Date.now()),
      agent: data.agent,
      confidence: data.confidence || 1.0,
    };

    if (data.id) {
      updateResult(data.id, result);
    } else {
      addResult(result);
    }

    addNotification({
      type: 'success',
      title: 'New Result Available',
      message: `${result.type} has been generated and is ready for review`,
      autoClose: 5000,
    });
  }, [addResult, updateResult, addNotification]);

  const handleError = useCallback((data: any) => {
    const { agentId, error, code } = data;
    
    if (agentId) {
      updateAgent(agentId, {
        status: 'error',
        currentTask: `Error: ${error}`,
      });
    }

    addNotification({
      type: 'error',
      title: 'Generation Error',
      message: error || 'An error occurred during video generation',
      autoClose: 8000,
    });
  }, [updateAgent, addNotification]);

  const handleSystemMessage = useCallback((data: any) => {
    const { message, level = 'info' } = data;
    
    addNotification({
      type: level as any,
      title: 'System Message',
      message,
      autoClose: level === 'error' ? 10000 : 5000,
    });
  }, [addNotification]);

  const handleMessage = useCallback((message: WebSocketMessage) => {
    console.log('Received WebSocket message:', message);

    // 事件总线消息（统一走事件语义）
    const eventBusHandlers: Record<string, (msg: any) => void> = {
      'event.progress': handleEventProgress,
      'event.state': handleEventState,
    };

    // 直传/遗留消息（保留少量仍在用的类型，其他状态类事件统一走 event.*）
    const directHandlers: Record<string, (msg: any) => void> = {
      task_notification: (msg) => handleSystemMessage({ message: msg.message, level: msg.level || 'info' }),
      system_notification: (msg) => handleSystemMessage({ message: msg.message, level: msg.level || 'info' }),
      'agent-status-update': (msg) => handleAgentStatusUpdate(msg.data),
      'progress-update': (msg) => handleProgressUpdate(msg.data),
      connection_established: handleConnectionEstablished,
      subscription_confirmed: handleSubscriptionConfirmed,
      'result-ready': (msg) => handleResultReady(msg.data),
      error: (msg) => handleError(msg.data),
      'system-message': (msg) => handleSystemMessage(msg.data),
    };

    const handler = eventBusHandlers[message.type] || directHandlers[message.type];
    if (handler) {
      handler(message);
    } else {
      console.warn('Unknown message type:', message.type);
    }
  }, [
    handleAgentStatusUpdate,
    handleProgressUpdate,
    handleEventProgress,
    handleEventState,
    handleBackendAgentProgress,
    handleWorkflowCompleted,
    handleWorkflowFailed,
    handleSystemMessage,
    handleConnectionEstablished,
    handleSubscriptionConfirmed,
    handleConceptPlanReady,
    handleImageAssetsReady,
    handleVideoAssetsReady,
    handleResultReady,
    handleError,
  ]);

  // Initialize connection only when a task exists, to avoid early connect/close noise
  useEffect(() => {
    if (!currentRequest?.id) return;
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect, currentRequest?.id]);

  // Reconnect when currentRequest changes
  useEffect(() => {
    if (currentRequest && ws.current?.readyState === WebSocket.OPEN) {
      ws.current?.send(
        JSON.stringify({ type: 'subscribe_task', task_id: currentRequest.id, timestamp: new Date() })
      );
    }
  }, [currentRequest, sendMessage]);

  return {
    sendMessage,
    disconnect,
    reconnect: connect,
    isConnected: ws.current?.readyState === WebSocket.OPEN,
  };
};
