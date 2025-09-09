import type { Metadata, Viewport } from 'next';
import { Inter } from 'next/font/google';
import { I18nProvider } from '@/i18n/I18nProvider';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'MuseCraft AI — 多智能体动漫生成平台',
  description:
    'MuseCraft AI：企业级多智能体编排，一站式概念、剧本、角色与场景、配音、合成与质检协作，快速生成商业级动漫。',
  keywords: ['AI动漫', '多智能体', '动漫生成', '企业级', '内容生产'],
  authors: [{ name: 'MuseCraft AI' }],
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#0ea5e9',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh">
      <head>
        <link rel="icon" href="/favicon.ico" />
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
        <meta name="theme-color" content="#0ea5e9" />
      </head>
      <body className={inter.className}>
        <I18nProvider defaultLang="zh">{children}</I18nProvider>
      </body>
    </html>
  );
}
