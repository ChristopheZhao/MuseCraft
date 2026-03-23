"use client";

import { useEffect, useRef } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { ApiClient } from '@/lib/api';
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

    const openCompletedResult = async (taskId: string) => {
      const candidates: Array<string | undefined> = [];
      try {
        const status = await ApiClient.getTaskStatus(taskId);
        lastStatusRef.current = 'completed';
        candidates.push(
          (status as any)?.final_video_url,
          (status as any)?.result?.final_video_url,
          (status as any)?.output_metadata?.final_video_url,
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
        try {
          runtime = await ApiClient.getTaskRuntime(taskId);
          runtimeAvailable = true;
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
        } catch {
          // runtime endpoint may lag behind task creation; keep polling
        }

        if (runtimeAvailable) {
          lastStatusRef.current = runtime?.status || lastStatusRef.current;
          return;
        }

        const status = await ApiClient.getTaskStatus(taskId);

        if (status.status === 'failed') {
          try {
            runtime = await ApiClient.getTaskRuntime(taskId);
            setQuickRuntime(runtime);
            notifyFailure(
              getRuntimeFailureMessage(runtime, status.error_message || '后端任务失败') ||
                status.error_message ||
                '后端任务失败'
            );
          } catch {
            const latestRuntime = useAppStore.getState().quickRuntime;
            if (latestRuntime && latestRuntime.status !== 'failed') {
              setQuickRuntime({
                ...latestRuntime,
                status: 'failed',
                error_message: status.error_message || latestRuntime.error_message || '后端任务失败',
              });
            }
            notifyFailure(status.error_message || '后端任务失败');
          }
          return;
        }

        if (status.status === 'completed') {
          await openCompletedResult(taskId);
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
