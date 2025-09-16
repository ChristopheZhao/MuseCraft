"use client";

import React from 'react';
import { useAppStore } from '@/store/useAppStore';
import VideoPlayer from './VideoPlayer';
import { X, CheckCircle } from 'lucide-react';

export default function ResultOverlay() {
  const { ui, finalVideoUrl, setModal } = useAppStore();
  const modal = ui.modal;
  const open = modal?.type === 'result-ready';

  if (!open) return null;

  const handleClose = () => {
    try {
      modal?.onClose?.();
    } finally {
      setModal(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={handleClose} />
      {/* Panel */}
      <div className="absolute right-0 top-0 bottom-0 w-full sm:w-[520px] bg-white shadow-2xl border-l border-gray-200 flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b bg-white/95 backdrop-blur">
          <div className="flex items-center space-x-2 text-green-700">
            <CheckCircle className="w-5 h-5" />
            <h3 className="text-base font-semibold">生成完成</h3>
          </div>
          <button className="p-1.5 text-gray-500 hover:text-gray-700" onClick={handleClose}>
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-5 space-y-4 overflow-auto">
          <div className="rounded-lg border border-gray-200 overflow-hidden">
            <VideoPlayer src={finalVideoUrl} className="aspect-video" />
          </div>
          <p className="text-sm text-gray-600">
            视频已就绪。点击右上角关闭进入“结果评审”进行导出与分享。
          </p>
          <button
            className="w-full py-2.5 rounded-lg bg-primary-600 hover:bg-primary-700 text-white font-medium"
            onClick={handleClose}
          >
            前往结果评审
          </button>
        </div>
      </div>
    </div>
  );
}

