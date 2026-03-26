'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { cn, formatTime, getProgressColor } from '@/lib/utils';
import {
  Activity,
  AlertCircle,
  CheckCircle,
  Clock,
  Loader2,
  Timer,
  Zap,
} from 'lucide-react';
import { motion } from 'framer-motion';
import { useI18n } from '@/i18n/I18nProvider';

interface ProgressMetrics {
  overallProgress: number;
  activeNodes: number;
  completedNodes: number;
  totalNodes: number;
  waitingGate: boolean;
  currentPhase: string;
}

const nodeLabelMap: Record<string, string> = {
  concept: '概念规划',
  script: '脚本创作',
  image: '图像生成',
  video: '视频生成',
  voice: '语音合成',
  compose: '视频合成',
  audio: '音频处理',
  quality: '质量检查',
};

const RealTimeProgress: React.FC = () => {
  const { agents, currentRequest, quickRuntime } = useAppStore();
  const { t } = useI18n();
  const [startTime] = useState(Date.now());
  const [elapsedTime, setElapsedTime] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsedTime(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [startTime]);

  const nodes = quickRuntime?.nodes || [];
  const activeGate = quickRuntime?.active_gate;

  const metrics = useMemo<ProgressMetrics>(() => {
    const totalNodes = nodes.length;
    const completedStatuses = ['completed', 'skipped'];
    const activeStatuses = ['running', 'pending_gate', 'approved', 'needs_revision'];
    const completedNodes = nodes.filter((node) => completedStatuses.indexOf(node.status) >= 0).length;
    const activeNodes = nodes.filter((node) => activeStatuses.indexOf(node.status) >= 0).length;
    const waitingGate = activeGate?.status === 'awaiting_human';
    const inFlightWeight = waitingGate || activeNodes > 0 ? 0.5 : 0;
    const overallProgress = totalNodes > 0 ? Math.round(((completedNodes + inFlightWeight) / totalNodes) * 100) : 0;

    let currentPhase = t('progress.phase.initializing');
    if (quickRuntime?.status === 'failed') {
      currentPhase = '运行失败';
    } else if (quickRuntime?.status === 'completed') {
      currentPhase = t('progress.phase.completed');
    } else if (waitingGate) {
      currentPhase = '等待脚本审核';
    } else if (quickRuntime?.current_node_key) {
      currentPhase = nodeLabelMap[quickRuntime.current_node_key] || quickRuntime.current_node_key;
    }

    return {
      overallProgress,
      activeNodes,
      completedNodes,
      totalNodes,
      waitingGate,
      currentPhase,
    };
  }, [activeGate?.status, nodes, quickRuntime?.current_node_key, quickRuntime?.status, t]);

  if (!currentRequest) {
    return null;
  }

  const progressSteps = nodes.map((node) => {
    const gateBound = activeGate?.node_id === node.id && activeGate?.status === 'awaiting_human';
    const status = gateBound ? 'pending_gate' : node.status;
    return {
      key: node.node_key,
      name: nodeLabelMap[node.node_key] || node.node_key,
      status,
      isCurrent: quickRuntime?.current_node_key === node.node_key,
    };
  });

  const telemetryAgents = agents.filter((agent) => agent.status === 'working' || agent.status === 'thinking');

  return (
    <div className="space-y-6">
      <div className="-mx-6 px-6">
        <div className="pt-2 pb-3 border-b border-gray-100">
          <h3 className="text-lg font-semibold text-gray-900">{t('progress.title')}</h3>
          <p className="text-sm text-gray-600">{t('progress.subtitle')}{currentRequest.title}</p>
        </div>
      </div>

      <div className="bg-gradient-to-r from-primary-50 to-accent-50 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h4 className="text-xl font-semibold text-gray-900">总体完成度 {metrics.overallProgress}%</h4>
            <p className="text-gray-600">{metrics.currentPhase}</p>
            {metrics.waitingGate && <p className="text-amber-700 mt-1">流程已暂停，等待脚本审核后继续。</p>}
          </div>
          <div className="flex items-center space-x-4 flex-wrap justify-end">
            <div className="flex items-center space-x-2">
              <Activity className="w-5 h-5 text-green-500" />
              <span className="text-sm font-medium text-gray-700">活跃节点 {metrics.activeNodes}</span>
            </div>
            <div className="flex items-center space-x-2">
              <CheckCircle className="w-5 h-5 text-blue-500" />
              <span className="text-sm font-medium text-gray-700">{metrics.completedNodes}/{metrics.totalNodes} 节点</span>
            </div>
          </div>
        </div>

        <div className="relative">
          <div className="w-full bg-white bg-opacity-50 rounded-full h-3 overflow-hidden">
            <motion.div
              className={cn('h-full rounded-full transition-all duration-500', getProgressColor(metrics.overallProgress))}
              initial={{ width: 0 }}
              animate={{ width: `${metrics.overallProgress}%` }}
              transition={{ duration: 1, ease: 'easeOut' }}
            />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-center gap-2 text-sm text-gray-600 mb-2">
            <Clock className="w-4 h-4" /> 当前 session
          </div>
          <div className="text-lg font-semibold text-gray-900">{quickRuntime?.status || 'queued'}</div>
          {quickRuntime?.current_node_key && (
            <div className="text-sm text-gray-600 mt-1">当前节点：{nodeLabelMap[quickRuntime.current_node_key] || quickRuntime.current_node_key}</div>
          )}
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-center gap-2 text-sm text-gray-600 mb-2">
            <Timer className="w-4 h-4" /> 已运行时长
          </div>
          <div className="text-lg font-semibold text-gray-900">{formatTime(elapsedTime)}</div>
          {metrics.waitingGate && <div className="text-sm text-amber-700 mt-1">已进入人工审核等待</div>}
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-center gap-2 text-sm text-gray-600 mb-2">
            <Zap className="w-4 h-4" /> 遥测
          </div>
          <div className="text-lg font-semibold text-gray-900">{telemetryAgents.length}</div>
          <div className="text-sm text-gray-600 mt-1">WS 遥测仅作辅助，业务进度以 runtime read-model 为准</div>
        </div>
      </div>

      <div className="space-y-3">
        <h4 className="font-medium text-gray-900">{t('progress.pipeline')}</h4>
        <div className="space-y-2">
          {progressSteps.map((step, index) => (
            <motion.div
              key={step.key}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.05 }}
              className={cn(
                'flex items-center space-x-4 p-4 rounded-lg border transition-all',
                {
                  'bg-blue-50 border-blue-200': step.status === 'running',
                  'bg-amber-50 border-amber-200': step.status === 'pending_gate',
                  'bg-emerald-50 border-emerald-200': step.status === 'approved',
                  'bg-orange-50 border-orange-200': step.status === 'needs_revision',
                  'bg-green-100 border-green-300': step.status === 'completed',
                  'bg-red-50 border-red-200': step.status === 'failed',
                  'bg-zinc-50 border-zinc-200': step.status === 'queued' || step.status === 'skipped' || step.status === 'stale',
                },
                step.isCurrent && 'ring-2 ring-primary-300'
              )}
            >
              <div className={cn(
                'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center',
                {
                  'bg-blue-500': step.status === 'running',
                  'bg-amber-500': step.status === 'pending_gate',
                  'bg-emerald-500': step.status === 'approved',
                  'bg-orange-500': step.status === 'needs_revision',
                  'bg-green-600': step.status === 'completed',
                  'bg-red-500': step.status === 'failed',
                  'bg-gray-400': step.status === 'queued' || step.status === 'skipped' || step.status === 'stale',
                }
              )}>
                {step.status === 'completed' || step.status === 'approved' ? (
                  <CheckCircle className="w-5 h-5 text-white" />
                ) : step.status === 'failed' ? (
                  <AlertCircle className="w-5 h-5 text-white" />
                ) : step.status === 'running' ? (
                  <Loader2 className="w-5 h-5 text-white animate-spin" />
                ) : (
                  <Clock className="w-5 h-5 text-white" />
                )}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <h5 className="font-medium text-gray-900">{step.name}</h5>
                  <span className="text-xs font-medium capitalize px-2 py-1 rounded-full bg-white/70 text-gray-700">
                    {step.status}
                  </span>
                </div>
                {step.isCurrent && <p className="text-sm text-gray-600">当前主线正在该节点运行或等待恢复。</p>}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default RealTimeProgress;
