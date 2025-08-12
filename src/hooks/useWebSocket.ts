'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { WebSocketMessage, MessageType, Agent, GenerationResult } from '@/types';
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
  const {
    url = 'ws://localhost:8000/api/v1/ws/connect',
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

  const {
    setWSConnected,
    updateAgent,
    addResult,
    updateResult,
    addNotification,
    currentRequest,
  } = useAppStore();

  const connect = useCallback(() => {
    try {
      ws.current = new WebSocket(url);

      ws.current.onopen = () => {
        console.log('WebSocket connected');
        setWSConnected(true);
        reconnectAttempts.current = 0;
        onOpen?.();

        addNotification({
          type: 'success',
          title: 'Connected',
          message: 'Real-time updates enabled',
          autoClose: 3000,
        });

        // Send initial handshake or subscription message
        if (currentRequest) {
          sendMessage({
            type: 'subscribe',
            data: { requestId: currentRequest.id },
            timestamp: new Date(),
          });
        }
      };

      ws.current.onclose = (event) => {
        console.log('WebSocket disconnected', event.code, event.reason);
        setWSConnected(false);
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
        console.error('WebSocket error:', error);
        onError?.(error);
        
        addNotification({
          type: 'error',
          title: 'Connection Error',
          message: 'Real-time updates may be unavailable',
          autoClose: 5000,
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

  const handleMessage = useCallback((message: WebSocketMessage) => {
    console.log('Received WebSocket message:', message);

    switch (message.type) {
      case 'agent-status-update':
        handleAgentStatusUpdate(message.data);
        break;
      
      case 'progress-update':
        handleProgressUpdate(message.data);
        break;
      
      case 'result-ready':
        handleResultReady(message.data);
        break;
      
      case 'error':
        handleError(message.data);
        break;
      
      case 'system-message':
        handleSystemMessage(message.data);
        break;
      
      default:
        console.warn('Unknown message type:', message.type);
    }
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

  // Initialize connection
  useEffect(() => {
    connect();
    
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  // Reconnect when currentRequest changes
  useEffect(() => {
    if (currentRequest && ws.current?.readyState === WebSocket.OPEN) {
      sendMessage({
        type: 'subscribe',
        data: { requestId: currentRequest.id },
      });
    }
  }, [currentRequest, sendMessage]);

  return {
    sendMessage,
    disconnect,
    reconnect: connect,
    isConnected: ws.current?.readyState === WebSocket.OPEN,
  };
};