"use client";

import { useEffect, useRef } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { ApiClient, TaskRuntimeEndpointError } from '@/lib/api';
import { resolvePublicMediaUrl } from '@/lib/mediaPaths';
import { getRuntimeFailureMessage, getRuntimeTerminalStatus } from '@/lib/runtimeReadModel';

/**
 * Lightweight task polling hook.
 * - Polls backend task status when WS is not connected
 * - On completion, fetches result and sets final video URL
 * - Advances UI step to 'review'
 */
export function useTaskPolling() {
  const {
    currentRequest,
    setCurrentStep,
    setFinalVideoUrl,
    setQuickRuntime,
    addNotification,
    setModal,
  } = useAppStore();

  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const lastStatusRef = useRef<string | null>(null);
  const lastGateIdRef = useRef<number | null>(null);
  const lastRuntimeReadErrorRef = useRef<string | null>(null);

  useEffect(() => {
    const intervalMs = Number(process.env.NEXT_PUBLIC_TASK_POLL_INTERVAL_MS || 3000);

    const clear = () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null as any;
      }
    };

    if (!currentRequest) {
      clear();
      return;
    }

    const notifyFailure = (message: string) => {
      const prev = lastStatusRef.current;
      lastStatusRef.current = 'failed';
      if (prev !== 'failed') {
        addNotification({
          type: 'error',
          title: '生成失败',
          message,
          autoClose: 8000,
        });
      }
    };

    const notifyRuntimeReadError = (message: string) => {
      if (lastRuntimeReadErrorRef.current === message) {
        return;
      }
      lastRuntimeReadErrorRef.current = message;
      addNotification({
        type: 'error',
        title: '运行时状态不可用',
        message,
        autoClose: 6000,
      });
    };

    const openCompletedResult = async (taskId: string) => {
      const candidates: Array<string | undefined> = [];
      try {
        const detail = await ApiClient.getTaskDetail(taskId);
        lastStatusRef.current = 'completed';
        candidates.push(
          detail?.output_metadata?.final_video_url,
          detail?.output_metadata?.final_video_path,
        );
      } catch {
        // keep trying other result sources
      }

      try {
        const res = await ApiClient.getTaskResult(taskId);
        candidates.push(
          res?.final_video_url,
          res?.video_url,
          res?.data?.video_url,
          res?.result?.video_url,
          res?.final_video_path,
          res?.video_path,
          res?.file_path,
          res?.result?.file_path,
        );
      } catch {
        // Ignore if endpoint not available
      }

      const picked = candidates.find((c) => typeof c === 'string' && c.length > 0);
      const publicUrl = resolvePublicMediaUrl(picked as string | undefined);
      if (publicUrl) {
        setFinalVideoUrl(publicUrl);
      } else if (picked) {
        setFinalVideoUrl(String(picked));
      }

      setModal({
        type: 'result-ready',
        data: {},
        onClose: () => {
          setCurrentStep('review');
          setModal(null);
        },
      });
      clear();
    };

    const tick = async () => {
      try {
        const taskId = currentRequest.id;
        if (!taskId) return;
        let runtime: any = null;
        let runtimeAvailable = false;
        let runtimeLagFallbackAllowed = false;
        try {
          runtime = await ApiClient.getTaskRuntime(taskId);
          runtimeAvailable = true;
          lastRuntimeReadErrorRef.current = null;
          setQuickRuntime(runtime);
          const activeGate = runtime?.active_gate;
          const gateId = typeof activeGate?.id === 'number' ? activeGate.id : null;
          if (gateId && activeGate?.status === 'awaiting_human' && gateId !== lastGateIdRef.current) {
            lastGateIdRef.current = gateId;
            addNotification({
              type: 'info',
              title: '等待人工确认',
              message: activeGate.gate_name === 'script_review' ? '脚本已生成，请确认后继续。' : '有新的审核节点等待处理。',
              autoClose: 4000,
            });
            setCurrentStep('processing');
          } else if (!gateId) {
            lastGateIdRef.current = null;
          }

          const runtimeTerminalStatus = getRuntimeTerminalStatus(runtime);
          if (runtimeTerminalStatus === 'failed') {
            notifyFailure(getRuntimeFailureMessage(runtime, '后端任务失败') || '后端任务失败');
            return;
          }

          if (runtimeTerminalStatus === 'completed') {
            await openCompletedResult(taskId);
            return;
          }
        } catch (error) {
          if (
            error instanceof TaskRuntimeEndpointError &&
            error.status === 404 &&
            error.detail === 'Runtime session not found'
          ) {
            runtimeLagFallbackAllowed = true;
          } else {
            notifyRuntimeReadError(
              error instanceof Error ? error.message : 'Failed to get task runtime'
            );
            return;
          }
        }

        if (runtimeAvailable) {
          lastStatusRef.current = runtime?.status || lastStatusRef.current;
          return;
        }

        if (!runtimeLagFallbackAllowed) {
          return;
        }

        const status = await ApiClient.getTaskCoarseStatus(taskId);

        if (status.status === 'failed' || status.status === 'completed') {
          // Keep polling until the authoritative runtime read-model becomes available.
          lastStatusRef.current = status.status;
          return;
        }

        lastStatusRef.current = status.status;
      } catch (e) {
        // Soft fail; keep polling
      }
    };

    // fire immediately and then interval
    tick();
    timerRef.current = setInterval(tick, intervalMs);

    return () => clear();
  }, [currentRequest, setCurrentStep, setFinalVideoUrl, setQuickRuntime, addNotification]);
}
