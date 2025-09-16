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
    wsConnected,
    setCurrentStep,
    setFinalVideoUrl,
    addNotification,
    setModal,
  } = useAppStore();

  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const lastStatusRef = useRef<string | null>(null);

  useEffect(() => {
    const intervalMs = Number(process.env.NEXT_PUBLIC_TASK_POLL_INTERVAL_MS || 3000);

    const clear = () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null as any;
      }
    };

    // No task or WS active → no polling
    if (!currentRequest || wsConnected) {
      clear();
      return;
    }

    const tick = async () => {
      try {
        const taskId = currentRequest.id;
        if (!taskId) return;
        const status = await ApiClient.getTaskStatus(taskId);

        // De-dup notifications
        const prev = lastStatusRef.current;
        lastStatusRef.current = status.status;

        if (status.status === 'failed') {
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
  }, [currentRequest, wsConnected, setCurrentStep, setFinalVideoUrl, addNotification]);
}
