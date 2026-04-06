'use client';

import React, { useState } from 'react';
import { CheckCircle, Clock, Copy, Download, Facebook, Film, Instagram, Linkedin, Twitter, Youtube } from 'lucide-react';

import { useI18n } from '@/i18n/I18nProvider';
import { getMediaDownloadFilename } from '@/lib/mediaPaths';
import { cn } from '@/lib/utils';
import { useAppStore } from '@/store/useAppStore';

interface ExportInterfaceProps {
  videoUrl?: string;
  className?: string;
}

const socialPlatforms = [
  { id: 'youtube', name: 'YouTube', icon: Youtube, color: 'text-red-500' },
  { id: 'facebook', name: 'Facebook', icon: Facebook, color: 'text-blue-600' },
  { id: 'twitter', name: 'Twitter', icon: Twitter, color: 'text-blue-400' },
  { id: 'instagram', name: 'Instagram', icon: Instagram, color: 'text-pink-500' },
  { id: 'linkedin', name: 'LinkedIn', icon: Linkedin, color: 'text-blue-700' },
];

const ExportInterface: React.FC<ExportInterfaceProps> = ({
  videoUrl,
  className,
}) => {
  const { t } = useI18n();
  const { currentRequest, addNotification } = useAppStore();
  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownloadCurrentVideo = async () => {
    if (!videoUrl || isDownloading) {
      return;
    }

    const filename = getMediaDownloadFilename(videoUrl, currentRequest?.title || 'generated-video');

    try {
      setIsDownloading(true);
      const response = await fetch(videoUrl);
      if (!response.ok) {
        throw new Error(`Failed to download video: ${response.status}`);
      }

      const blob = await response.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = blobUrl;
      anchor.download = filename;
      anchor.style.display = 'none';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(blobUrl);

      addNotification({
        type: 'success',
        title: t('export.notify.downloadStarted.title'),
        message: t('export.notify.downloadStarted.msg').replace('{filename}', filename),
        autoClose: 4000,
      });
    } catch (error) {
      addNotification({
        type: 'error',
        title: t('export.notify.downloadFailed.title'),
        message: error instanceof Error ? error.message : t('export.notify.downloadFailed.msg'),
        autoClose: 6000,
      });
    } finally {
      setIsDownloading(false);
    }
  };

  const handleShare = (platform: string) => {
    addNotification({
      type: 'info',
      title: t('export.notify.share.title'),
      message: t('export.notify.share.msg').replace('{platform}', platform),
      autoClose: 3000,
    });
  };

  const copyShareLink = async () => {
    const shareUrl = `${window.location.origin}/share/${currentRequest?.id}`;
    await navigator.clipboard.writeText(shareUrl);
    addNotification({
      type: 'success',
      title: t('export.notify.copied.title'),
      message: t('export.notify.copied.msg'),
      autoClose: 3000,
    });
  };

  return (
    <div className={cn('space-y-6', className)}>
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">{t('export.header')}</h3>
          <p className="text-sm text-gray-600">{t('export.headerDesc')}</p>
        </div>
        {videoUrl && (
          <div className="flex items-center space-x-2 px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-medium">
            <CheckCircle className="w-4 h-4" />
            <span>{t('export.ready')}</span>
          </div>
        )}
      </div>

      {videoUrl ? (
        <>
          <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-primary-100 p-2">
                <Film className="w-5 h-5 text-primary-700" />
              </div>
              <div>
                <h4 className="font-medium text-gray-900">{t('export.currentFile.title')}</h4>
                <p className="text-sm text-gray-600 mt-1">{t('export.currentFile.desc')}</p>
                <p className="text-xs text-gray-500 mt-2">
                  {currentRequest?.title || t('player.defaultTitle')}
                </p>
              </div>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row gap-4">
            <button
              onClick={() => void handleDownloadCurrentVideo()}
              disabled={isDownloading}
              className={cn(
                'flex-1 flex items-center justify-center space-x-2 px-6 py-3 rounded-lg font-medium transition-colors',
                isDownloading
                  ? 'bg-primary-500 text-white cursor-wait'
                  : 'bg-primary-600 text-white hover:bg-primary-700'
              )}
            >
              {isDownloading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>{t('export.downloading')}</span>
                </>
              ) : (
                <>
                  <Download className="w-4 h-4" />
                  <span>{t('export.downloadCurrent')}</span>
                </>
              )}
            </button>

            <button
              onClick={() => void copyShareLink()}
              className="flex items-center justify-center space-x-2 px-6 py-3 border rounded-lg font-medium transition-colors border-gray-300 text-gray-700 hover:bg-gray-50"
            >
              <Copy className="w-4 h-4" />
              <span>{t('export.copyLink')}</span>
            </button>
          </div>

          <div>
            <h4 className="font-medium text-gray-900 mb-4">{t('export.share')}</h4>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              {socialPlatforms.map((platform) => {
                const Icon = platform.icon;
                return (
                  <button
                    key={platform.id}
                    onClick={() => handleShare(platform.name)}
                    className="flex flex-col items-center space-y-2 p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                  >
                    <Icon className={cn('w-6 h-6', platform.color)} />
                    <span className="text-sm font-medium text-gray-700">
                      {platform.name}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </>
      ) : (
        <div className="text-center py-8 bg-gray-50 rounded-lg">
          <div className="w-16 h-16 bg-gray-200 rounded-full flex items-center justify-center mx-auto mb-4">
            <Clock className="w-8 h-8 text-gray-400" />
          </div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">{t('export.notReady.title')}</h3>
          <p className="text-gray-600">{t('export.notReady.desc')}</p>
        </div>
      )}
    </div>
  );
};

export default ExportInterface;
