"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Video } from 'lucide-react';

export default function NavBar() {
  const pathname = usePathname();

  const nav = [
    { href: '/home', label: '首页' },
    { href: '/home/#product', label: '架构' },
  ];

  return (
    <header className="sticky top-0 z-30 bg-white/80 backdrop-blur border-b">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <span className="p-2 rounded-md bg-gradient-to-br from-primary-500 to-accent-500 text-white">
            <Video className="w-5 h-5" />
          </span>
          <div className="leading-tight">
            <div className="font-bold">MuseCraft AI</div>
            <div className="text-xs text-gray-500">多智能体动漫生成平台</div>
          </div>
        </Link>

        <nav className="hidden md:flex items-center gap-6 text-sm text-gray-700">
          {nav.map((n) => (
            <Link key={n.href} href={n.href} className={pathname === n.href ? 'text-primary-600 font-medium' : 'hover:text-gray-900'}>
              {n.label}
            </Link>
          ))}
        </nav>

        <Link href="/console" className="px-4 py-2 rounded-md bg-primary-600 text-sm font-medium text-white hover:bg-primary-700">
          打开控制台
        </Link>
      </div>
    </header>
  );
}
