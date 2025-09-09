"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useI18n } from '@/i18n/I18nProvider';
import { Video, User } from 'lucide-react';

export default function NavBar() {
  const { lang, setLang } = useI18n();
  const pathname = usePathname();

  const nav = [
    { href: '/home', label: '首页' },
    { href: '/home/#product', label: '产品' },
    { href: '/pricing', label: '定价' },
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

        <div className="flex items-center gap-3">
          <button
            onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
            className="hidden sm:block px-3 py-1 text-xs rounded-full border border-gray-200 hover:bg-gray-100 text-gray-600"
          >
            {lang === 'zh' ? '中文' : 'EN'}
          </button>
          <button aria-label="User profile" className="w-9 h-9 rounded-full bg-primary-100 hover:bg-primary-200 flex items-center justify-center text-primary-700">
            <User className="w-5 h-5" />
          </button>
        </div>
      </div>
    </header>
  );
}
