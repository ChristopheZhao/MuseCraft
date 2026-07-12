import type { Metadata, Viewport } from 'next';
import { I18nProvider } from '@/i18n/I18nProvider';
import './globals.css';

export const metadata: Metadata = {
  title: 'MuseCraft AI — 多智能体动漫生成平台',
  description:
    'MuseCraft AI：以可观测 MAS runtime 组织概念、剧本、媒体生成、合成与质量检查。',
  keywords: ['AI动漫', '多智能体', '动漫生成', 'MAS runtime', '内容生产'],
  authors: [{ name: 'MuseCraft AI' }],
  icons: {
    icon: '/marketing/musecraft-console.png',
    apple: '/marketing/musecraft-console.png',
  },
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
      <body>
        <I18nProvider defaultLang="zh">{children}</I18nProvider>
      </body>
    </html>
  );
}
