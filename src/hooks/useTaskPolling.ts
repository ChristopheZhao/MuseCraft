"use client";

import { useEffect, useRef } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { ApiClient } from '@/lib/api';
import { resolvePublicMediaUrl } from '@/lib/mediaPaths';
import { getRuntimeFailureMessage, getRuntimeTerminalStatus } from '@/lib/runtimeReadModel';

/**
 * Lightweight task polling hook.
 * - Polls backend task status when WS is not connected
 * - On completion, resolves the final video from runtime/detail/resources
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

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
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

    const openCompletedResult = async (taskId: string, runtime?: Record<string, any> | null) => {
      const candidates: Array<string | undefined> = [];
      const summaryOutput = runtime?.summary_output || {};
      candidates.push(
        summaryOutput?.final_video_url,
        summaryOutput?.final_video_path,
        summaryOutput?.video_url,
        summaryOutput?.video_path,
        summaryOutput?.output_assets?.final_video_url,
        summaryOutput?.output_assets?.video_url,
      );

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
        const resources = await ApiClient.getTaskResources(taskId);
        const finalResource = resources.find((resource) => resource.is_final_output);
        candidates.push(finalResource?.file_url);
      } catch {
        // Ignore if resources are not available yet
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
        try {
          const runtime = await ApiClient.getTaskRuntime(taskId);
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
            await openCompletedResult(taskId, runtime);
            return;
          }
        } catch (error) {
          notifyRuntimeReadError(
            error instanceof Error ? error.message : 'Failed to get task runtime'
          );
          return;
        }
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
