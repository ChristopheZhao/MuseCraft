'use client';

import { useCallback, useState } from 'react';

import { useI18n } from '@/i18n/I18nProvider';
import { downloadMediaUrl } from '@/lib/downloadMedia';
import { getMediaDownloadFilename } from '@/lib/mediaPaths';
import { useAppStore } from '@/store/useAppStore';

export function useCurrentVideoDownload(videoUrl?: string, fallbackBase?: string) {
  const { t } = useI18n();
  const { currentRequest, addNotification } = useAppStore();
  const [isDownloading, setIsDownloading] = useState(false);

  const downloadCurrentVideo = useCallback(async (): Promise<boolean> => {
    if (!videoUrl || isDownloading) {
      return false;
    }

    const filename = getMediaDownloadFilename(
      videoUrl,
      fallbackBase || currentRequest?.title || 'generated-video'
    );

    try {
      setIsDownloading(true);
      await downloadMediaUrl(videoUrl, filename);
      addNotification({
        type: 'success',
        title: t('export.notify.downloadStarted.title'),
        message: t('export.notify.downloadStarted.msg').replace('{filename}', filename),
        autoClose: 4000,
      });
      return true;
    } catch (error) {
      addNotification({
        type: 'error',
        title: t('export.notify.downloadFailed.title'),
        message: error instanceof Error ? error.message : t('export.notify.downloadFailed.msg'),
        autoClose: 6000,
      });
      return false;
    } finally {
      setIsDownloading(false);
    }
  }, [addNotification, currentRequest?.title, fallbackBase, isDownloading, t, videoUrl]);

  return {
    isDownloading,
    downloadCurrentVideo,
  };
}
