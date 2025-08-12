'use client';

import React, { useState } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { cn, formatFileSize } from '@/lib/utils';
import { 
  Download, 
  Share2, 
  Copy, 
  ExternalLink,
  Settings,
  Film,
  Smartphone,
  Monitor,
  Globe,
  Facebook,
  Twitter,
  Youtube,
  Instagram,
  Linkedin,
  CheckCircle,
  Clock,
  AlertCircle
} from 'lucide-react';
import { motion } from 'framer-motion';

interface ExportFormat {
  id: string;
  name: string;
  description: string;
  resolution: string;
  aspectRatio: string;
  fileSize: string;
  platform?: string;
  icon: React.ElementType;
  recommended?: boolean;
}

interface ExportInterfaceProps {
  videoUrl?: string;
  className?: string;
}

const ExportInterface: React.FC<ExportInterfaceProps> = ({
  videoUrl,
  className,
}) => {
  const { currentRequest, addNotification } = useAppStore();
  const [selectedFormat, setSelectedFormat] = useState<string>('mp4-1080p');
  const [isExporting, setIsExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState(0);
  const [customSettings, setCustomSettings] = useState({
    quality: 'high',
    bitrate: '8000',
    fps: '30',
    codec: 'h264',
  });

  const exportFormats: ExportFormat[] = [
    {
      id: 'mp4-4k',
      name: '4K Ultra HD',
      description: 'Best quality for professional use',
      resolution: '3840×2160',
      aspectRatio: '16:9',
      fileSize: '~200MB',
      icon: Monitor,
      recommended: true,
    },
    {
      id: 'mp4-1080p',
      name: 'Full HD',
      description: 'High quality for most platforms',
      resolution: '1920×1080',
      aspectRatio: '16:9',
      fileSize: '~80MB',
      icon: Monitor,
      recommended: true,
    },
    {
      id: 'mp4-720p',
      name: 'HD',
      description: 'Good quality, smaller file size',
      resolution: '1280×720',
      aspectRatio: '16:9',
      fileSize: '~40MB',
      icon: Monitor,
    },
    {
      id: 'mp4-mobile',
      name: 'Mobile Optimized',
      description: 'Optimized for mobile viewing',
      resolution: '1080×1920',
      aspectRatio: '9:16',
      fileSize: '~60MB',
      platform: 'Mobile',
      icon: Smartphone,
    },
    {
      id: 'mp4-square',
      name: 'Square Format',
      description: 'Perfect for Instagram posts',
      resolution: '1080×1080',
      aspectRatio: '1:1',
      fileSize: '~50MB',
      platform: 'Instagram',
      icon: Instagram,
    },
  ];

  const socialPlatforms = [
    { id: 'youtube', name: 'YouTube', icon: Youtube, color: 'text-red-500' },
    { id: 'facebook', name: 'Facebook', icon: Facebook, color: 'text-blue-600' },
    { id: 'twitter', name: 'Twitter', icon: Twitter, color: 'text-blue-400' },
    { id: 'instagram', name: 'Instagram', icon: Instagram, color: 'text-pink-500' },
    { id: 'linkedin', name: 'LinkedIn', icon: Linkedin, color: 'text-blue-700' },
  ];

  const qualityOptions = [
    { value: 'ultra', label: 'Ultra High', bitrate: '12000', description: 'Best quality, largest file' },
    { value: 'high', label: 'High', bitrate: '8000', description: 'Excellent quality, recommended' },
    { value: 'medium', label: 'Medium', bitrate: '4000', description: 'Good quality, balanced size' },
    { value: 'low', label: 'Low', bitrate: '2000', description: 'Smaller file, lower quality' },
  ];

  const handleExport = async (format: string) => {
    setIsExporting(true);
    setExportProgress(0);

    // Simulate export progress
    const interval = setInterval(() => {
      setExportProgress(prev => {
        if (prev >= 100) {
          clearInterval(interval);
          setIsExporting(false);
          addNotification({
            type: 'success',
            title: 'Export Complete',
            message: 'Your video has been exported successfully',
            autoClose: 5000,
          });
          return 100;
        }
        return prev + Math.random() * 15;
      });
    }, 500);

    // Cleanup after export
    setTimeout(() => {
      clearInterval(interval);
      setIsExporting(false);
      setExportProgress(0);
    }, 8000);
  };

  const handleShare = (platform: string) => {
    addNotification({
      type: 'info',
      title: 'Share Feature',
      message: `Sharing to ${platform} will be available soon`,
      autoClose: 3000,
    });
  };

  const copyShareLink = () => {
    const shareUrl = `${window.location.origin}/share/${currentRequest?.id}`;
    navigator.clipboard.writeText(shareUrl);
    addNotification({
      type: 'success',
      title: 'Link Copied',
      message: 'Share link copied to clipboard',
      autoClose: 3000,
    });
  };

  const selectedFormatData = exportFormats.find(f => f.id === selectedFormat);

  return (
    <div className={cn("space-y-6", className)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">
            Export & Share
          </h3>
          <p className="text-sm text-gray-600">
            Download your video or share it directly to social platforms
          </p>
        </div>
        {videoUrl && (
          <div className="flex items-center space-x-2 px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-medium">
            <CheckCircle className="w-4 h-4" />
            <span>Ready to Export</span>
          </div>
        )}
      </div>

      {/* Export Progress */}
      {isExporting && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-blue-50 border border-blue-200 rounded-lg p-4"
        >
          <div className="flex items-center space-x-3 mb-3">
            <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <div>
              <h4 className="font-medium text-blue-900">Exporting Video</h4>
              <p className="text-sm text-blue-700">
                Processing {selectedFormatData?.name}...
              </p>
            </div>
          </div>
          <div className="w-full bg-blue-200 rounded-full h-2">
            <motion.div
              className="bg-blue-500 h-2 rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${exportProgress}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>
          <p className="text-sm text-blue-600 mt-2">
            {Math.round(exportProgress)}% complete
          </p>
        </motion.div>
      )}

      {/* Format Selection */}
      <div>
        <h4 className="font-medium text-gray-900 mb-4">Choose Export Format</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {exportFormats.map((format) => {
            const Icon = format.icon;
            return (
              <button
                key={format.id}
                onClick={() => setSelectedFormat(format.id)}
                disabled={isExporting}
                className={cn(
                  "relative p-4 rounded-lg border-2 transition-all text-left",
                  selectedFormat === format.id
                    ? "border-primary-500 bg-primary-50"
                    : "border-gray-200 hover:border-gray-300 bg-white",
                  isExporting && "opacity-50 cursor-not-allowed"
                )}
              >
                {format.recommended && (
                  <div className="absolute -top-2 -right-2 bg-primary-500 text-white text-xs px-2 py-1 rounded-full">
                    Recommended
                  </div>
                )}
                
                <div className="flex items-start space-x-3">
                  <div className={cn(
                    "p-2 rounded-lg",
                    selectedFormat === format.id ? "bg-primary-100" : "bg-gray-100"
                  )}>
                    <Icon className={cn(
                      "w-5 h-5",
                      selectedFormat === format.id ? "text-primary-600" : "text-gray-600"
                    )} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h5 className="font-medium text-gray-900 mb-1">
                      {format.name}
                    </h5>
                    <p className="text-sm text-gray-600 mb-2">
                      {format.description}
                    </p>
                    <div className="text-xs text-gray-500 space-y-1">
                      <div>{format.resolution} • {format.aspectRatio}</div>
                      <div className="flex items-center justify-between">
                        <span>{format.fileSize}</span>
                        {format.platform && (
                          <span className="px-2 py-1 bg-gray-100 rounded-full">
                            {format.platform}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Advanced Settings */}
      <div className="bg-gray-50 rounded-lg p-4">
        <div className="flex items-center space-x-2 mb-4">
          <Settings className="w-5 h-5 text-gray-600" />
          <h4 className="font-medium text-gray-900">Advanced Settings</h4>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Quality Preset
            </label>
            <select
              value={customSettings.quality}
              onChange={(e) => setCustomSettings(prev => ({ ...prev, quality: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            >
              {qualityOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label} - {option.description}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Frame Rate
            </label>
            <select
              value={customSettings.fps}
              onChange={(e) => setCustomSettings(prev => ({ ...prev, fps: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            >
              <option value="24">24 FPS (Cinematic)</option>
              <option value="30">30 FPS (Standard)</option>
              <option value="60">60 FPS (Smooth)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Export Actions */}
      <div className="flex flex-col sm:flex-row gap-4">
        <button
          onClick={() => handleExport(selectedFormat)}
          disabled={!videoUrl || isExporting}
          className={cn(
            "flex-1 flex items-center justify-center space-x-2 px-6 py-3 rounded-lg font-medium transition-colors",
            videoUrl && !isExporting
              ? "bg-primary-600 text-white hover:bg-primary-700"
              : "bg-gray-300 text-gray-500 cursor-not-allowed"
          )}
        >
          {isExporting ? (
            <>
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              <span>Exporting...</span>
            </>
          ) : (
            <>
              <Download className="w-4 h-4" />
              <span>Export {selectedFormatData?.name}</span>
            </>
          )}
        </button>

        <button
          onClick={copyShareLink}
          disabled={!videoUrl}
          className={cn(
            "flex items-center justify-center space-x-2 px-6 py-3 border rounded-lg font-medium transition-colors",
            videoUrl
              ? "border-gray-300 text-gray-700 hover:bg-gray-50"
              : "border-gray-200 text-gray-400 cursor-not-allowed"
          )}
        >
          <Copy className="w-4 h-4" />
          <span>Copy Link</span>
        </button>
      </div>

      {/* Social Media Sharing */}
      <div>
        <h4 className="font-medium text-gray-900 mb-4">Share to Social Media</h4>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {socialPlatforms.map((platform) => {
            const Icon = platform.icon;
            return (
              <button
                key={platform.id}
                onClick={() => handleShare(platform.name)}
                disabled={!videoUrl}
                className={cn(
                  "flex flex-col items-center space-y-2 p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors",
                  !videoUrl && "opacity-50 cursor-not-allowed"
                )}
              >
                <Icon className={cn("w-6 h-6", platform.color)} />
                <span className="text-sm font-medium text-gray-700">
                  {platform.name}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* No Video State */}
      {!videoUrl && (
        <div className="text-center py-8 bg-gray-50 rounded-lg">
          <div className="w-16 h-16 bg-gray-200 rounded-full flex items-center justify-center mx-auto mb-4">
            <Clock className="w-8 h-8 text-gray-400" />
          </div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">
            Video Not Ready
          </h3>
          <p className="text-gray-600">
            Your video is still being generated. Export options will be available once complete.
          </p>
        </div>
      )}
    </div>
  );
};

export default ExportInterface;