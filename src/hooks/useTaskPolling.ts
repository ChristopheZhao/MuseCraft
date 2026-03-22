"use client";

import { useEffect, useRef } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { ApiClient } from '@/lib/api';
import { resolvePublicMediaUrl } from '@/lib/mediaPaths';

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

    const tick = async () => {
      try {
        const taskId = currentRequest.id;
        if (!taskId) return;
        try {
          const runtime = await ApiClient.getTaskRuntime(taskId);
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
        } catch {
          // runtime endpoint may lag behind task creation; keep polling
        }

        const status = await ApiClient.getTaskStatus(taskId);

        // De-dup notifications
        const prev = lastStatusRef.current;
        lastStatusRef.current = status.status;

        if (status.status === 'failed') {
          try {
            const runtime = await ApiClient.getTaskRuntime(taskId);
            setQuickRuntime(runtime);
          } catch {
            const latestRuntime = useAppStore.getState().quickRuntime;
            if (latestRuntime && latestRuntime.status !== 'failed') {
              setQuickRuntime({
                ...latestRuntime,
                status: 'failed',
                error_message: status.error_message || latestRuntime.error_message || '后端任务失败',
              });
            }
          }
          if (prev !== 'failed') {
            addNotification({
              type: 'error',
              title: '生成失败',
              message: status.error_message || '后端任务失败',
              autoClose: 8000,
            });
          }
          return;
        }

        if (status.status === 'completed') {
          // Try to read final url/path from status first (some backends include it)
          const candidates: Array<string | undefined> = [
            (status as any)?.final_video_url,
            (status as any)?.result?.final_video_url,
            (status as any)?.output_metadata?.final_video_url,
          ];

          // As a secondary source, attempt to fetch detailed result (optional backend)
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

          // Pick first valid candidate and normalize to public URL
          const picked = candidates.find((c) => typeof c === 'string' && c.length > 0);
          const publicUrl = resolvePublicMediaUrl(picked as string | undefined);
          if (publicUrl) {
            setFinalVideoUrl(publicUrl);
          } else if (picked) {
            // Last resort: set raw and let VideoPlayer show error overlay if inaccessible
            setFinalVideoUrl(String(picked));
          }
          // 弹出结果就绪抽屉，保持当前页为 processing；用户关闭后再进入 review
          setModal({
            type: 'result-ready',
            data: {},
            onClose: () => {
              setCurrentStep('review');
              setModal(null);
            },
          });
          clear();
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
