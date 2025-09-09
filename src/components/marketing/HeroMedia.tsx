"use client";
import Image from 'next/image';
import { useEffect, useRef, useState } from 'react';

type Props = {
  videoSrc?: string;
  posterSrc?: string;
  imageSrc?: string;
  className?: string;
  height?: string; // e.g. 'h-[520px]'
};

export default function HeroMedia({
  videoSrc = '/marketing/hero.mp4',
  posterSrc = '/marketing/hero-1.jpg',
  imageSrc = '/marketing/hero-1.jpg',
  className,
  height = 'h-[540px]',
}: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [fallback, setFallback] = useState(false);
  // Allow overriding video/poster via env for deployments without bundling large assets
  const envVideo = process.env.NEXT_PUBLIC_HERO_VIDEO_URL as string | undefined;
  const envPoster = process.env.NEXT_PUBLIC_HERO_POSTER_URL as string | undefined;
  const finalVideoSrc = envVideo && envVideo.trim().length > 0 ? envVideo : videoSrc;
  const finalPosterSrc = envPoster && envPoster.trim().length > 0 ? envPoster : posterSrc;

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onError = () => setFallback(true);
    v.addEventListener('error', onError);
    // try play in case autoplay policy blocks
    const tryPlay = async () => {
      try {
        await v.play();
      } catch {
        setFallback(true);
      }
    };
    tryPlay();
    return () => v.removeEventListener('error', onError);
  }, []);

  return (
    <div className={`absolute inset-0 ${className ?? ''}`} aria-hidden>
      <div className={`relative ${height}`}>
        {!fallback ? (
          <video
            ref={videoRef}
            className="absolute inset-0 w-full h-full object-cover"
            autoPlay
            muted
            loop
            playsInline
            preload="metadata"
            poster={finalPosterSrc}
            src={finalVideoSrc}
          />
        ) : (
          <Image
            src={imageSrc}
            alt="Background"
            fill
            priority
            sizes="100vw"
            className="object-cover"
          />
        )}
        {/* gradient overlay for readability */}
        <div className="absolute inset-0 bg-gradient-to-tr from-white to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-br from-primary-100/40 via-transparent to-accent-100/40" />
      </div>
    </div>
  );
}
