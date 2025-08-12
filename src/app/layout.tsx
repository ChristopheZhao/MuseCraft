import type { Metadata, Viewport } from 'next';
import { Inter } from 'next/font/google';
import AppLayout from '@/components/layout/AppLayout';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'VideoMaker AI - Intelligent Video Generation Platform',
  description: 'Create professional videos with AI-powered multi-agent collaboration. Generate concepts, scripts, visuals, and voice narration automatically.',
  keywords: ['AI video generation', 'automated video creation', 'multi-agent AI', 'video maker', 'artificial intelligence'],
  authors: [{ name: 'VideoMaker AI Team' }],
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
    <html lang="en">
      <head>
        <link rel="icon" href="/favicon.ico" />
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
        <meta name="theme-color" content="#0ea5e9" />
      </head>
      <body className={inter.className}>
        <AppLayout>
          {children}
        </AppLayout>
      </body>
    </html>
  );
}