'use client';

import React, { useMemo } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { cn, getStatusColor as getTelemetryStatusColor } from '@/lib/utils';
import {
  AlertCircle,
  ArrowRight,
  Brain,
  CheckCircle,
  Clock,
  Database,
  FileText,
  Film,
  Image,
  Loader2,
  Mic,
  Sparkles,
  Video,
} from 'lucide-react';
import { motion } from 'framer-motion';
import { useI18n } from '@/i18n/I18nProvider';

type DisplayNodeStatus =
  | 'queued'
  | 'running'
  | 'pending_gate'
  | 'approved'
  | 'needs_revision'
  | 'completed'
  | 'failed'
  | 'skipped'
  | 'stale';

const nodeMeta: Record<string, { label: string; description: string; icon: React.ComponentType<{ className?: string }> }> = {
  concept: {
    label: '概念规划',
    description: '生成整体创意、风格与场景规划',
    icon: Brain,
  },
  script: {
    label: '脚本创作',
    description: '生成并审核可继续执行的正式脚本',
    icon: FileText,
  },
  image: {
    label: '图像生成',
    description: '产出场景所需的视觉资产',
    icon: Image,
  },
  video: {
    label: '分镜视频',
    description: '按场景生成视频片段',
    icon: Film,
  },
  voice: {
    label: '语音合成',
    description: '生成旁白或对白语音',
    icon: Mic,
  },
  compose: {
    label: '视频合成',
    description: '汇总资产并合成为完整视频',
    icon: Video,
  },
  audio: {
    label: '音频处理',
    description: '生成或混合 BGM 与音频轨道',
    icon: Sparkles,
  },
  quality: {
    label: '质量检查',
    description: '检查最终输出与交付质量',
    icon: CheckCircle,
  },
};

const statusLabelMap: Record<DisplayNodeStatus, string> = {
  queued: 'queued',
  running: 'running',
  pending_gate: 'waiting',
  approved: 'approved',
  needs_revision: 'revise',
  completed: 'completed',
  failed: 'failed',
  skipped: 'skipped',
  stale: 'stale',
};

const statusTextColorMap: Record<DisplayNodeStatus, string> = {
  queued: 'text-gray-500',
  running: 'text-blue-600',
  pending_gate: 'text-amber-700',
  approved: 'text-emerald-700',
  needs_revision: 'text-orange-700',
  completed: 'text-green-700',
  failed: 'text-red-600',
  skipped: 'text-zinc-500',
  stale: 'text-zinc-600',
};

const AgentOrchestrator: React.FC = () => {
  const { agents, currentRequest, quickRuntime } = useAppStore();
  const { t } = useI18n();

  const runtimeNodes = quickRuntime?.nodes || [];
  const activeGate = quickRuntime?.active_gate;
  const telemetryAgents = useMemo(() => agents.filter((agent) => agent.status !== 'idle'), [agents]);

  const nodes = useMemo(
    () =>
      runtimeNodes.map((node) => {
        const gateBound = activeGate?.node_id === node.id && activeGate?.status === 'awaiting_human';
        const status = (gateBound ? 'pending_gate' : node.status) as DisplayNodeStatus;
        return {
          ...node,
          status,
          meta: nodeMeta[node.node_key] || {
            label: node.node_key,
            description: node.node_type || 'runtime node',
            icon: Sparkles,
          },
        };
      }),
    [runtimeNodes, activeGate?.node_id, activeGate?.status]
  );

  const getNodeStatusColor = (status: DisplayNodeStatus) => {
    switch (status) {
      case 'queued':
        return 'bg-gray-100 border-gray-200';
      case 'running':
        return 'bg-blue-50 border-blue-200';
      case 'pending_gate':
        return 'bg-amber-50 border-amber-200';
      case 'approved':
        return 'bg-emerald-50 border-emerald-200';
      case 'needs_revision':
        return 'bg-orange-50 border-orange-200';
      case 'completed':
        return 'bg-green-100 border-green-300';
      case 'failed':
        return 'bg-red-50 border-red-200';
      case 'skipped':
        return 'bg-zinc-50 border-zinc-200';
      case 'stale':
        return 'bg-zinc-100 border-zinc-300';
      default:
        return 'bg-gray-100 border-gray-200';
    }
  };

  const getStatusIcon = (status: DisplayNodeStatus) => {
    const iconProps = { className: 'w-4 h-4' };
    switch (status) {
      case 'running':
        return <Loader2 {...iconProps} className="w-4 h-4 animate-spin text-blue-500" />;
      case 'pending_gate':
        return <Clock {...iconProps} className="w-4 h-4 text-amber-500" />;
      case 'approved':
        return <CheckCircle {...iconProps} className="w-4 h-4 text-emerald-500" />;
      case 'needs_revision':
        return <AlertCircle {...iconProps} className="w-4 h-4 text-orange-500" />;
      case 'completed':
        return <CheckCircle {...iconProps} className="w-4 h-4 text-green-500" />;
      case 'failed':
        return <AlertCircle {...iconProps} className="w-4 h-4 text-red-500" />;
      default:
        return <Clock {...iconProps} className="w-4 h-4 text-gray-400" />;
    }
  };

  if (!currentRequest) {
    return (
      <div className="p-8 text-center">
        <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <Brain className="w-8 h-8 text-gray-400" />
        </div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">{t('orch.title')}</h3>
        <p className="text-gray-600">{t('orch.empty')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="sticky top-0 z-10 -mx-6 px-6 py-3 bg-white/80 backdrop-blur border-b border-gray-100 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">{t('orch.title')}</h3>
          <p className="text-sm text-gray-600">{t('orch.subtitle')}{currentRequest.title}</p>
          {quickRuntime?.current_node_key && (
            <p className="text-xs text-primary-700 mt-1">
              当前运行节点：{nodeMeta[quickRuntime.current_node_key]?.label || quickRuntime.current_node_key}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden md:flex items-center text-xs px-3 py-1 rounded-full bg-primary-50 text-primary-700 border border-primary-200">
            {t('orch.mode.multi')}
          </div>
          <div className="hidden md:flex items-center space-x-2 px-3 py-1 bg-indigo-50 text-indigo-700 rounded-full text-sm border border-indigo-200">
            <Database className="w-4 h-4" />
            <span>{t('orch.memory')}</span>
          </div>
          <div className="flex items-center space-x-2 px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-medium">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
            <span>{quickRuntime?.status || t('orch.active')}</span>
          </div>
        </div>
      </div>

      {activeGate?.status === 'awaiting_human' && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          当前流程在 `{activeGate.gate_name}` 等待人工确认，节点图已切换到真实 runtime 状态。
        </div>
      )}

      <div className="relative mt-4">
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-full h-0.5 bg-gray-200">
            <motion.div
              className="h-full bg-gradient-to-r from-primary-500 to-green-500"
              initial={{ width: '0%' }}
              animate={{ width: '100%' }}
              transition={{ duration: 2, repeat: Infinity, repeatType: 'loop' }}
            />
          </div>
        </div>

        <div className={cn('relative grid gap-4', nodes.length > 6 ? 'grid-cols-2 md:grid-cols-4' : 'grid-cols-2 md:grid-cols-4 lg:grid-cols-6')}>
          {nodes.map((node, index) => {
            const Icon = node.meta.icon;
            const isCurrent = quickRuntime?.current_node_key === node.node_key;
            const statusLabel = statusLabelMap[node.status] || node.status;
            return (
              <motion.div
                key={node.node_key}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.08 }}
                className={cn(
                  'relative p-4 rounded-xl border-2 transition-all duration-300',
                  getNodeStatusColor(node.status),
                  isCurrent && 'shadow-lg ring-2 ring-primary-300'
                )}
              >
                <div className="flex items-center justify-center w-12 h-12 bg-white rounded-full shadow-sm mb-3 mx-auto">
                  <div className={statusTextColorMap[node.status] || 'text-gray-500'}>
                    <Icon className="w-6 h-6" />
                  </div>
                </div>

                <div className="text-center">
                  <h4 className="font-medium text-gray-900 text-sm mb-1">{node.meta.label}</h4>
                  <div className="flex items-center justify-center space-x-1 mb-2">
                    {getStatusIcon(node.status)}
                    <span className={cn('text-xs font-medium capitalize', statusTextColorMap[node.status] || 'text-gray-500')}>
                      {statusLabel}
                    </span>
                  </div>
                  <p className="text-xs text-gray-600 line-clamp-2">{node.meta.description}</p>
                  <div className="mt-2 text-[11px] text-gray-500">rev {node.revision_index}</div>
                </div>

                <div
                  className={cn(
                    'absolute -top-1 -right-1 w-3 h-3 rounded-full border-2 border-white',
                    {
                      'bg-gray-400': node.status === 'queued' || node.status === 'skipped' || node.status === 'stale',
                      'bg-blue-500 animate-pulse': node.status === 'running',
                      'bg-amber-500': node.status === 'pending_gate',
                      'bg-emerald-500': node.status === 'approved',
                      'bg-orange-500': node.status === 'needs_revision',
                      'bg-green-600': node.status === 'completed',
                      'bg-red-500': node.status === 'failed',
                    }
                  )}
                />

                {index < nodes.length - 1 && (
                  <div className="absolute top-1/2 -right-2 transform -translate-y-1/2 hidden lg:block">
                    <ArrowRight className="w-4 h-4 text-gray-400" />
                  </div>
                )}
              </motion.div>
            );
          })}
        </div>
      </div>

      {telemetryAgents.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {telemetryAgents.map((agent) => (
            <div
              key={`details-${agent.id}`}
              className="p-4 bg-white/90 backdrop-blur border border-gray-200 rounded-lg shadow-card"
            >
              <div className="flex items-center justify-between gap-3 mb-2">
                <div>
                  <h4 className="font-medium text-gray-900">{agent.name}</h4>
                  <p className={cn('text-sm capitalize', getTelemetryStatusColor(agent.status))}>{agent.status}</p>
                </div>
                {agent.currentTask && <span className="text-xs text-gray-500">遥测</span>}
              </div>
              <p className="text-sm text-gray-600 mb-3">{agent.description}</p>
              {agent.currentTask && (
                <div className="mb-3">
                  <p className="text-xs font-medium text-gray-700 mb-1">{t('orch.currentTask')}：</p>
                  <p className="text-sm text-gray-600">{agent.currentTask}</p>
                </div>
              )}
              {agent.progress > 0 && (
                <div className="mb-3">
                  <div className="flex justify-between text-xs text-gray-600 mb-1">
                    <span>{t('common.progress')}</span>
                    <span>{agent.progress}%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <motion.div
                      className="bg-primary-500 h-2 rounded-full"
                      initial={{ width: 0 }}
                      animate={{ width: `${agent.progress}%` }}
                      transition={{ duration: 0.5 }}
                    />
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default AgentOrchestrator;
