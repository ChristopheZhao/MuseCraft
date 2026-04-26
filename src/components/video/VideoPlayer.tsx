'use client';

import React, { useState, useRef, useEffect } from 'react';
import { cn, formatTime } from '@/lib/utils';
import { useCurrentVideoDownload } from '@/hooks/useCurrentVideoDownload';
import { 
  Play, 
  Pause, 
  Volume2, 
  VolumeX, 
  Maximize, 
  Minimize,
  SkipBack,
  SkipForward,
  Settings,
  Download,
  Share2,
  Heart
} from 'lucide-react';
import { motion } from 'framer-motion';
import { useI18n } from '@/i18n/I18nProvider';

interface VideoPlayerProps {
  src?: string;
  poster?: string;
  title?: string;
  duration?: number;
  className?: string;
  autoPlay?: boolean;
  controls?: boolean;
  onTimeUpdate?: (currentTime: number) => void;
  onEnded?: () => void;
}

const VideoPlayer: React.FC<VideoPlayerProps> = ({
  src,
  poster,
  title = undefined,
  duration = 0,
  className,
  autoPlay = false,
  controls = true,
  onTimeUpdate,
  onEnded,
}) => {
  const { t } = useI18n();
  const { isDownloading, downloadCurrentVideo } = useCurrentVideoDownload(src, title);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showControls, setShowControls] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);

  const controlsTimeoutRef = useRef<NodeJS.Timeout>();

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const handleTimeUpdate = () => {
      const time = video.currentTime;
      setCurrentTime(time);
      onTimeUpdate?.(time);
    };

    const handleLoadStart = () => {
      setHasError(false);
      setIsLoading(true);
    };
    const handleLoadedData = () => setIsLoading(false);
    const handleError = () => {
      // Stop the spinner and surface a friendly error state
      setIsLoading(false);
      setHasError(true);
      setIsPlaying(false);
    };
    const handleEnded = () => {
      setIsPlaying(false);
      onEnded?.();
    };

    video.addEventListener('timeupdate', handleTimeUpdate);
    video.addEventListener('loadstart', handleLoadStart);
    video.addEventListener('loadeddata', handleLoadedData);
    video.addEventListener('ended', handleEnded);
    video.addEventListener('error', handleError);

    return () => {
      video.removeEventListener('timeupdate', handleTimeUpdate);
      video.removeEventListener('loadstart', handleLoadStart);
      video.removeEventListener('loadeddata', handleLoadedData);
      video.removeEventListener('ended', handleEnded);
      video.removeEventListener('error', handleError);
    };
  }, [onTimeUpdate, onEnded]);

  const togglePlay = () => {
    const video = videoRef.current;
    if (!video) return;

    if (isPlaying) {
      video.pause();
    } else {
      video.play();
    }
    setIsPlaying(!isPlaying);
  };

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    const video = videoRef.current;
    if (!video) return;

    const rect = e.currentTarget.getBoundingClientRect();
    const percentage = (e.clientX - rect.left) / rect.width;
    const newTime = percentage * video.duration;
    
    video.currentTime = newTime;
    setCurrentTime(newTime);
  };

  const toggleMute = () => {
    const video = videoRef.current;
    if (!video) return;

    video.muted = !isMuted;
    setIsMuted(!isMuted);
  };

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const video = videoRef.current;
    if (!video) return;

    const newVolume = parseFloat(e.target.value);
    video.volume = newVolume;
    setVolume(newVolume);
    setIsMuted(newVolume === 0);
  };

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      videoRef.current?.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  const skipTime = (seconds: number) => {
    const video = videoRef.current;
    if (!video) return;

    const newTime = Math.max(0, Math.min(video.duration, video.currentTime + seconds));
    video.currentTime = newTime;
    setCurrentTime(newTime);
  };

  const changePlaybackRate = (rate: number) => {
    const video = videoRef.current;
    if (!video) return;

    video.playbackRate = rate;
    setPlaybackRate(rate);
  };

  const handleMouseMove = () => {
    setShowControls(true);
    
    if (controlsTimeoutRef.current) {
      clearTimeout(controlsTimeoutRef.current);
    }
    
    controlsTimeoutRef.current = setTimeout(() => {
      if (isPlaying) {
        setShowControls(false);
      }
    }, 3000);
  };

  const videoDuration = videoRef.current?.duration || duration;
  const progress = videoDuration > 0 ? (currentTime / videoDuration) * 100 : 0;

  if (!src) {
    return (
      <div className={cn(
        "relative bg-gray-900 rounded-lg overflow-hidden aspect-video flex items-center justify-center",
        className
      )}>
        <div className="text-center">
          <div className="w-16 h-16 bg-gray-800 rounded-full flex items-center justify-center mx-auto mb-4">
            <Play className="w-8 h-8 text-gray-400" />
          </div>
          <h3 className="text-white font-medium mb-2">{t('player.noVideoTitle')}</h3>
          <p className="text-gray-400 text-sm">{t('player.noVideoDesc')}</p>
        </div>
      </div>
    );
  }

  return (
    <div 
      className={cn(
        "relative bg-black rounded-lg overflow-hidden group",
        className
      )}
      onMouseMove={handleMouseMove}
      onMouseLeave={() => setShowControls(false)}
    >
      {/* Video Element */}
      <video
        ref={videoRef}
        src={src}
        poster={poster}
        className="w-full h-full object-contain"
        autoPlay={autoPlay}
        preload="metadata"
        onClick={togglePlay}
      />

      {/* Loading Overlay */}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50">
          <div className="w-12 h-12 border-4 border-white border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {/* Error Overlay */}
      {hasError && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/70 text-center p-6">
          <div className="text-white/90 mb-2">视频加载失败</div>
          <div className="text-white/60 text-sm mb-4">请检查资源地址或稍后重试</div>
          <button
            onClick={() => {
              const v = videoRef.current;
              if (!v) return;
              setHasError(false);
              setIsLoading(true);
              // Force reload
              const current = v.src;
              v.src = '';
              // next tick
              setTimeout(() => {
                v.src = current;
                v.load();
              }, 0);
            }}
            className="px-3 py-1.5 rounded bg-white/20 hover:bg-white/30 text-white text-sm"
          >
            重试
          </button>
        </div>
      )}

      {/* Controls Overlay */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: showControls ? 1 : 0 }}
        transition={{ duration: 0.2 }}
        className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-black/30 pointer-events-none"
      >
        {/* Top Controls */}
        <div className="absolute top-4 left-4 right-4 flex items-center justify-between pointer-events-auto">
          <h3 className="text-white font-medium truncate mr-4">{title || t('player.defaultTitle')}</h3>
          <div className="flex items-center space-x-2">
            <button className="p-2 text-white/80 hover:text-white transition-colors">
              <Heart className="w-5 h-5" />
            </button>
            <button className="p-2 text-white/80 hover:text-white transition-colors">
              <Share2 className="w-5 h-5" />
            </button>
            <button
              onClick={() => void downloadCurrentVideo()}
              disabled={!src || isDownloading}
              aria-label={t('export.downloadCurrent')}
              title={t('export.downloadCurrent')}
              className={cn(
                'p-2 transition-colors',
                !src || isDownloading
                  ? 'cursor-not-allowed text-white/40'
                  : 'text-white/80 hover:text-white'
              )}
            >
              <Download className={cn('w-5 h-5', isDownloading && 'animate-pulse')} />
            </button>
          </div>
        </div>

        {/* Center Play Button */}
        {!isPlaying && (
          <motion.button
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            onClick={togglePlay}
            className="absolute inset-0 flex items-center justify-center pointer-events-auto"
          >
            <div className="w-20 h-20 bg-white/20 backdrop-blur-sm rounded-full flex items-center justify-center hover:bg-white/30 transition-colors">
              <Play className="w-10 h-10 text-white ml-1" />
            </div>
          </motion.button>
        )}

        {/* Bottom Controls */}
        {controls && (
          <div className="absolute bottom-0 left-0 right-0 p-4 pointer-events-auto">
            {/* Progress Bar */}
            <div className="mb-4">
              <div 
                className="w-full h-1 bg-white/30 rounded-full cursor-pointer"
                onClick={handleSeek}
              >
                <div 
                  className="h-full bg-white rounded-full transition-all duration-200"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>

            {/* Control Buttons */}
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <button
                  onClick={togglePlay}
                  className="p-2 text-white hover:bg-white/20 rounded-full transition-colors"
                >
                  {isPlaying ? (
                    <Pause className="w-5 h-5" />
                  ) : (
                    <Play className="w-5 h-5" />
                  )}
                </button>

                <button
                  onClick={() => skipTime(-10)}
                  className="p-2 text-white/80 hover:text-white hover:bg-white/20 rounded-full transition-colors"
                >
                  <SkipBack className="w-4 h-4" />
                </button>

                <button
                  onClick={() => skipTime(10)}
                  className="p-2 text-white/80 hover:text-white hover:bg-white/20 rounded-full transition-colors"
                >
                  <SkipForward className="w-4 h-4" />
                </button>

                {/* Volume Control */}
                <div className="flex items-center space-x-2">
                  <button
                    onClick={toggleMute}
                    className="p-2 text-white/80 hover:text-white transition-colors"
                  >
                    {isMuted || volume === 0 ? (
                      <VolumeX className="w-4 h-4" />
                    ) : (
                      <Volume2 className="w-4 h-4" />
                    )}
                  </button>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={isMuted ? 0 : volume}
                    onChange={handleVolumeChange}
                    className="w-16 h-1 bg-white/30 rounded-full appearance-none cursor-pointer"
                  />
                </div>

                {/* Time Display */}
                <span className="text-white/80 text-sm font-mono">
                  {formatTime(currentTime)} / {formatTime(videoDuration)}
                </span>
              </div>

              <div className="flex items-center space-x-2">
                {/* Playback Speed */}
                <select
                  value={playbackRate}
                  onChange={(e) => changePlaybackRate(parseFloat(e.target.value))}
                  className="bg-transparent text-white text-sm border border-white/30 rounded px-2 py-1"
                >
                  <option value={0.5}>0.5x</option>
                  <option value={0.75}>0.75x</option>
                  <option value={1}>1x</option>
                  <option value={1.25}>1.25x</option>
                  <option value={1.5}>1.5x</option>
                  <option value={2}>2x</option>
                </select>

                <button className="p-2 text-white/80 hover:text-white transition-colors">
                  <Settings className="w-4 h-4" />
                </button>

                <button
                  onClick={toggleFullscreen}
                  className="p-2 text-white/80 hover:text-white transition-colors"
                >
                  {isFullscreen ? (
                    <Minimize className="w-4 h-4" />
                  ) : (
                    <Maximize className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </motion.div>
    </div>
  );
};

export default VideoPlayer;
