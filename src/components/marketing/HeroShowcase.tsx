"use client";
import Image from 'next/image';
import { Bot, Film, Wand2, AudioLines } from 'lucide-react';
import { useEffect, useState } from 'react';

// A visually stronger, domain-relevant hero showcase
// - Central animated preview (cross-fades between frames)
// - Stacked storyboard cards
// - Floating agent chips to reinforce Multi‑Agent workflow
export default function HeroShowcase() {
  const frames = [
    { src: '/marketing/hero-1.jpg', alt: 'Anime frame – environment' },
    { src: '/marketing/hero-2.jpg', alt: 'Anime frame – character' },
    { src: '/marketing/hero-3.jpg', alt: 'Anime frame – motion' },
  ];

  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setIdx((p) => (p + 1) % frames.length), 2200);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="hidden md:block">
      <div className="relative">
        {/* glowing background */}
        <div className="absolute -inset-6 rounded-3xl bg-gradient-to-tr from-primary-200/60 via-accent-200/50 to-primary-200/60 blur-3xl" />

        <div className="relative grid grid-cols-2 gap-5">
          {/* Main animated preview */}
          <div className="col-span-1 row-span-2">
            <div className="rounded-2xl p-[2px] bg-gradient-to-tr from-primary-500 via-accent-500 to-primary-500 shadow-card">
              <div className="relative rounded-[1rem] overflow-hidden bg-white/60 backdrop-blur-xs">
                {/* faux player header */}
                <div className="flex items-center gap-2 px-3 py-2 text-xs text-gray-600">
                  <span className="inline-block size-2 rounded-full bg-error/80" />
                  <span className="font-medium">Studio Preview</span>
                </div>

                {/* frame cross-fade */}
                <div className="relative h-72">
                  {frames.map((f, i) => (
                    <Image
                      key={i}
                      src={f.src}
                      alt={f.alt}
                      fill
                      priority={i === 0}
                      sizes="(min-width: 768px) 480px, 100vw"
                      className={`object-cover transition-opacity duration-700 ${idx === i ? 'opacity-100' : 'opacity-0'}`}
                    />
                  ))}
                  {/* subtle gradient overlay */}
                  <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/20 to-transparent" />
                </div>

                {/* timeline */}
                <div className="px-3 py-2 bg-white/70 backdrop-blur-xs border-t">
                  <div className="h-1.5 w-full rounded bg-gray-200">
                    <div
                      className="h-1.5 rounded bg-gradient-to-r from-primary-500 to-accent-500 transition-all"
                      style={{ width: `${((idx + 1) / frames.length) * 100}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Storyboard cards */}
          <div className="space-y-5">
            <div className="relative h-32 rounded-xl overflow-hidden border shadow-card bg-white/80">
              <Image src="/marketing/hero-2.jpg" alt="Storyboard A" fill className="object-cover" />
              <div className="absolute inset-0 bg-gradient-to-br from-primary-500/0 to-primary-500/10" />
              <div className="absolute left-3 top-3 text-xs font-medium px-2 py-1 rounded bg-white/90 text-gray-800">分镜 · 镜头运动</div>
            </div>
            <div className="relative h-32 rounded-xl overflow-hidden border shadow-card bg-white/80">
              <Image src="/marketing/hero-3.jpg" alt="Storyboard B" fill className="object-cover" />
              <div className="absolute inset-0 bg-gradient-to-br from-accent-500/0 to-accent-500/10" />
              <div className="absolute left-3 top-3 text-xs font-medium px-2 py-1 rounded bg-white/90 text-gray-800">角色 · 表演节奏</div>
            </div>
          </div>

          {/* Floating chips */}
          <div className="pointer-events-none">
            <div className="absolute -left-5 top-8 flex items-center gap-2 rounded-full bg-white/90 border px-3 py-1 text-xs text-gray-800 shadow-card animate-bounce-gentle">
              <Bot className="w-3.5 h-3.5 text-primary-600" /> 协同分工
            </div>
            <div className="absolute -right-2 top-14 flex items-center gap-2 rounded-full bg-white/90 border px-3 py-1 text-xs text-gray-800 shadow-card animate-pulse">
              <Wand2 className="w-3.5 h-3.5 text-accent-600" /> 视觉风格
            </div>
            <div className="absolute -left-3 bottom-8 flex items-center gap-2 rounded-full bg-white/90 border px-3 py-1 text-xs text-gray-800 shadow-card">
              <AudioLines className="w-3.5 h-3.5 text-primary-600" /> 配音音乐
            </div>
            <div className="absolute right-6 -bottom-3 flex items-center gap-2 rounded-full bg-white/90 border px-3 py-1 text-xs text-gray-800 shadow-card">
              <Film className="w-3.5 h-3.5 text-accent-600" /> 合成质检
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

