'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertCircle,
  ArrowRight,
  Brain,
  CheckCircle2,
  Clock3,
  FileText,
  Film,
  Loader2,
  MessageSquareText,
  Mic,
  Music4,
  PauseCircle,
  PlayCircle,
  RefreshCcw,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Video,
} from 'lucide-react';

import { ApiClient } from '@/lib/api';
import {
  getRuntimeFailureMessage,
  getRuntimeWorkspaceProjection,
  isBootstrapRuntimePlaceholder,
  isPreNodeFailure,
} from '@/lib/runtimeReadModel';
import { cn } from '@/lib/utils';
import { useAppStore } from '@/store/useAppStore';
import type { RuntimeDisplayNode } from '@/lib/runtimeReadModel';

type FocusMode =
  | 'running'
  | 'hitl'
  | 'resume_available'
  | 'resume_blocked'
  | 'failed'
  | 'completed'
  | 'detached';

type NodeMeta = {
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  accentClass: string;
  iconClass: string;
};

const actionLabelMap: Record<string, string> = {
  approve: '批准并继续',
  revise: '要求重写',
  replan: '要求重规划',
};

const nodeMetaMap: Record<string, NodeMeta> = {
  concept: {
    label: '概念规划',
    description: '整理创意方向、角色关系与场景目标。',
    icon: Brain,
    accentClass: 'from-emerald-500/18 via-emerald-400/10 to-transparent',
    iconClass: 'bg-emerald-100 text-emerald-700',
  },
  script: {
    label: '脚本创作',
    description: '产出可执行脚本，并在 gate 时进入人工确认。',
    icon: FileText,
    accentClass: 'from-amber-500/18 via-amber-400/10 to-transparent',
    iconClass: 'bg-amber-100 text-amber-700',
  },
  image: {
    label: '图像生成',
    description: '生成镜头所需的关键视觉资产。',
    icon: Sparkles,
    accentClass: 'from-fuchsia-500/18 via-fuchsia-400/10 to-transparent',
    iconClass: 'bg-fuchsia-100 text-fuchsia-700',
  },
  video: {
    label: '视频生成',
    description: '将镜头与动作描述推进为动态片段。',
    icon: Film,
    accentClass: 'from-sky-500/18 via-sky-400/10 to-transparent',
    iconClass: 'bg-sky-100 text-sky-700',
  },
  voice: {
    label: '语音合成',
    description: '生成旁白或对白所需的语音轨道。',
    icon: Mic,
    accentClass: 'from-violet-500/18 via-violet-400/10 to-transparent',
    iconClass: 'bg-violet-100 text-violet-700',
  },
  compose: {
    label: '视频合成',
    description: '把镜头、音频与资产组装成可交付成片。',
    icon: Video,
    accentClass: 'from-indigo-500/18 via-indigo-400/10 to-transparent',
    iconClass: 'bg-indigo-100 text-indigo-700',
  },
  audio: {
    label: '音频处理',
    description: '补充或混合背景音乐与音效层。',
    icon: Music4,
    accentClass: 'from-rose-500/18 via-rose-400/10 to-transparent',
    iconClass: 'bg-rose-100 text-rose-700',
  },
  quality: {
    label: '质量检查',
    description: '检查交付结果与最终运行质量。',
    icon: ShieldCheck,
    accentClass: 'from-teal-500/18 via-teal-400/10 to-transparent',
    iconClass: 'bg-teal-100 text-teal-700',
  },
};

const fallbackNodeMeta: NodeMeta = {
  label: '运行节点',
  description: '当前 runtime 节点未提供专门的视觉元数据。',
  icon: Activity,
  accentClass: 'from-slate-500/18 via-slate-400/10 to-transparent',
  iconClass: 'bg-slate-100 text-slate-700',
};

const statusMetaMap: Record<
  string,
  { label: string; badgeClass: string; railDotClass: string }
> = {
  queued: {
    label: '等待启动',
    badgeClass: 'bg-slate-100 text-slate-700 border-slate-200',
    railDotClass: 'bg-slate-300',
  },
  running: {
    label: '正在执行',
    badgeClass: 'bg-sky-100 text-sky-700 border-sky-200',
    railDotClass: 'bg-sky-500',
  },
  pending_gate: {
    label: '等待确认',
    badgeClass: 'bg-amber-100 text-amber-800 border-amber-200',
    railDotClass: 'bg-amber-500',
  },
  approved: {
    label: '审核通过',
    badgeClass: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    railDotClass: 'bg-emerald-500',
  },
  needs_revision: {
    label: '等待修订',
    badgeClass: 'bg-orange-100 text-orange-700 border-orange-200',
    railDotClass: 'bg-orange-500',
  },
  completed: {
    label: '已完成',
    badgeClass: 'bg-green-100 text-green-700 border-green-200',
    railDotClass: 'bg-green-600',
  },
  failed: {
    label: '运行失败',
    badgeClass: 'bg-red-100 text-red-700 border-red-200',
    railDotClass: 'bg-red-500',
  },
  skipped: {
    label: '已跳过',
    badgeClass: 'bg-zinc-100 text-zinc-600 border-zinc-200',
    railDotClass: 'bg-zinc-400',
  },
  stale: {
    label: '历史版本',
    badgeClass: 'bg-zinc-100 text-zinc-700 border-zinc-300',
    railDotClass: 'bg-zinc-500',
  },
};

function getNodeMeta(nodeKey?: string | null): NodeMeta {
  if (!nodeKey) {
    return fallbackNodeMeta;
  }
  return nodeMetaMap[nodeKey] || {
    ...fallbackNodeMeta,
    label: nodeKey,
  };
}

function getStatusMeta(status?: string | null) {
  if (!status) {
    return statusMetaMap.queued;
  }
  return statusMetaMap[status] || {
    label: status,
    badgeClass: 'bg-slate-100 text-slate-700 border-slate-200',
    railDotClass: 'bg-slate-400',
  };
}

function formatTimestamp(value?: string | null): string {
  if (!value) {
    return '-';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString('zh-CN', { hour12: false });
}

function flattenValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '-';
  }
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function extractDiagnosticLines(node?: RuntimeDisplayNode | null): string[] {
  if (!node) {
    return [];
  }

  return node.diagnostics
    .flatMap((diagnostic) => {
      if (typeof diagnostic === 'string') {
        return [diagnostic];
      }
      const keys = ['message', 'detail', 'code', 'reason', 'status'];
      return keys
        .map((key) => diagnostic?.[key])
        .filter((value): value is string | number | boolean => value !== undefined && value !== null)
        .map((value) => String(value));
    })
    .filter((line) => line.trim().length > 0)
    .slice(0, 3);
}

function getArtifactHighlights(node?: RuntimeDisplayNode | null) {
  if (!node) {
    return [];
  }

  return node.artifact_refs.slice(0, 3).map((artifact, index) => ({
    title:
      (typeof artifact.label === 'string' && artifact.label) ||
      (typeof artifact.kind === 'string' && artifact.kind) ||
      (typeof artifact.artifact_type === 'string' && artifact.artifact_type) ||
      `artifact_${index + 1}`,
    detail:
      (typeof artifact.url === 'string' && artifact.url) ||
      (typeof artifact.path === 'string' && artifact.path) ||
      (typeof artifact.ref === 'string' && artifact.ref) ||
      'runtime 已记录产物引用',
  }));
}

function getSummaryHighlights(summaryOutput?: Record<string, unknown>) {
  return Object.entries(summaryOutput || {})
    .filter(([, value]) => value !== null && value !== undefined && String(flattenValue(value)).trim().length > 0)
    .slice(0, 3)
    .map(([key, value]) => ({
      key,
      value: flattenValue(value),
    }));
}

const ContextSection: React.FC<{
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}> = ({ eyebrow, title, children }) => (
  <section className="rounded-[24px] border border-slate-200 bg-white/90 p-5 shadow-card">
    <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">{eyebrow}</div>
    <h3 className="mt-2 text-base font-semibold text-slate-900">{title}</h3>
    <div className="mt-4 space-y-2 text-sm text-slate-600">{children}</div>
  </section>
);

const KeyValueRow: React.FC<{
  label: string;
  value: React.ReactNode;
}> = ({ label, value }) => (
  <div className="rounded-2xl bg-slate-50 px-4 py-3">
    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">{label}</div>
    <div className="mt-1 text-sm font-medium leading-6 text-slate-900 break-words">{value}</div>
  </div>
);

const QuickModeWorkspace: React.FC = () => {
  const {
    currentRequest,
    quickProcessingContext,
    quickRuntime,
    setQuickRuntime,
    addNotification,
  } = useAppStore();
  const [feedbackText, setFeedbackText] = useState('');
  const [submittingAction, setSubmittingAction] = useState<string | null>(null);
  const [resumingRuntime, setResumingRuntime] = useState(false);
  const [resumeHint, setResumeHint] = useState<string | null>(null);

  const activeGate = quickRuntime?.active_gate;
  const resumeControl = quickRuntime?.resume_control;
  const isScriptGate = activeGate?.gate_name === 'script_review';
  const scriptPreviewText = useMemo(
    () => String(activeGate?.facts?.script_preview_text || '').trim(),
    [activeGate?.facts]
  );
  const runtimeFailureMessage = useMemo(
    () => getRuntimeFailureMessage(quickRuntime),
    [quickRuntime]
  );
  const showPreNodeFailureHint = useMemo(
    () => isPreNodeFailure(quickRuntime),
    [quickRuntime]
  );
  const isFreshSubmitBootstrap = useMemo(
    () =>
      quickProcessingContext === 'fresh_submit' &&
      (!quickRuntime || isBootstrapRuntimePlaceholder(quickRuntime)),
    [quickProcessingContext, quickRuntime]
  );

  useEffect(() => {
    if (activeGate?.status === 'awaiting_human') {
      setResumeHint(null);
    }
  }, [activeGate?.id, activeGate?.status]);

  const workspace = useMemo(
    () => getRuntimeWorkspaceProjection(quickRuntime),
    [quickRuntime]
  );
  const focusNode = workspace.focusNode;
  const currentNode = workspace.currentNode;
  const focusNodeMeta = getNodeMeta(focusNode?.node_key);
  const focusNodeStatus = getStatusMeta(
    currentNode?.displayStatus ||
      focusNode?.displayStatus ||
      (quickRuntime?.status === 'failed'
        ? 'failed'
        : quickRuntime?.status === 'completed'
          ? 'completed'
          : 'queued')
  );
  const diagnosticLines = useMemo(
    () => extractDiagnosticLines(focusNode),
    [focusNode]
  );
  const artifactHighlights = useMemo(
    () => getArtifactHighlights(focusNode),
    [focusNode]
  );
  const summaryHighlights = useMemo(
    () => getSummaryHighlights(quickRuntime?.summary_output),
    [quickRuntime?.summary_output]
  );
  const FocusIcon = focusNodeMeta.icon;

  const focusMode: FocusMode = useMemo(() => {
    if (isScriptGate && activeGate?.status === 'awaiting_human') {
      return 'hitl';
    }
    if (runtimeFailureMessage) {
      return 'failed';
    }
    if (resumeControl?.state === 'resume_available') {
      return 'resume_available';
    }
    if (resumeControl?.state === 'resume_blocked') {
      return 'resume_blocked';
    }
    if (quickRuntime?.status === 'completed') {
      return 'completed';
    }
    if (quickRuntime) {
      return 'running';
    }
    return 'detached';
  }, [
    activeGate?.status,
    isScriptGate,
    quickRuntime,
    resumeControl?.state,
    runtimeFailureMessage,
  ]);

  const handleResumeRuntime = async () => {
    if (!currentRequest?.id || !resumeControl?.can_resume) {
      return;
    }
    try {
      setResumingRuntime(true);
      const result = await ApiClient.resumeTaskRuntime(currentRequest.id);
      setQuickRuntime(result.runtime);
      addNotification({
        type: 'success',
        title: '已请求恢复执行',
        message: `任务 ${currentRequest.id} 已重新进入执行流程。`,
        autoClose: 3000,
      });
    } catch (error) {
      addNotification({
        type: 'error',
        title: '恢复执行失败',
        message: error instanceof Error ? error.message : '恢复执行失败，请稍后重试',
        autoClose: 6000,
      });
    } finally {
      setResumingRuntime(false);
    }
  };

  const handleDecision = async (action: 'approve' | 'revise' | 'replan') => {
    if (!currentRequest?.id) {
      return;
    }
    try {
      setSubmittingAction(action);
      const result = await ApiClient.submitScriptGateDecision(currentRequest.id, {
        action,
        feedback_text: feedbackText.trim() || undefined,
      });
      setQuickRuntime(result.runtime);
      setResumeHint(`已提交${actionLabelMap[action]}，等待主线恢复…`);
      if (action !== 'approve') {
        setFeedbackText('');
      }
      addNotification({
        type: 'success',
        title: '脚本审核已提交',
        message: actionLabelMap[action],
        autoClose: 3000,
      });
    } catch (error) {
      addNotification({
        type: 'error',
        title: '提交失败',
        message: error instanceof Error ? error.message : '脚本审核提交失败',
        autoClose: 6000,
      });
    } finally {
      setSubmittingAction(null);
    }
  };

  const renderFocusModeBadge = () => {
    const commonClassName =
      'inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold';
    switch (focusMode) {
      case 'hitl':
        return (
          <div className={`${commonClassName} border-amber-300 bg-amber-500/15 text-amber-100`}>
            <MessageSquareText className="h-4 w-4" />
            等待人工确认
          </div>
        );
      case 'resume_available':
        return (
          <div className={`${commonClassName} border-emerald-300 bg-emerald-500/15 text-emerald-100`}>
            <PlayCircle className="h-4 w-4" />
            可恢复执行
          </div>
        );
      case 'resume_blocked':
        return (
          <div className={`${commonClassName} border-orange-300 bg-orange-500/15 text-orange-100`}>
            <PauseCircle className="h-4 w-4" />
            查看态诊断
          </div>
        );
      case 'failed':
        return (
          <div className={`${commonClassName} border-red-300 bg-red-500/15 text-red-100`}>
            <AlertCircle className="h-4 w-4" />
            运行失败
          </div>
        );
      case 'completed':
        return (
          <div className={`${commonClassName} border-emerald-300 bg-emerald-500/15 text-emerald-100`}>
            <CheckCircle2 className="h-4 w-4" />
            结果已生成
          </div>
        );
      case 'detached':
        return (
          <div className={`${commonClassName} border-slate-300 bg-white/10 text-slate-100`}>
            <Clock3 className="h-4 w-4" />
            等待 runtime 数据
          </div>
        );
      default:
        return (
          <div className={`${commonClassName} border-sky-300 bg-sky-500/15 text-sky-100`}>
            <Loader2 className="h-4 w-4 animate-spin" />
            runtime 正在推进
          </div>
        );
    }
  };

  const renderNodeSnapshot = (title: string, description: string) => (
    <div className="rounded-[24px] border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
            {title}
          </div>
          <h3 className="mt-2 text-xl font-semibold text-slate-900">{focusNodeMeta.label}</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
        </div>
        <span
          className={cn(
            'inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium',
            focusNodeStatus.badgeClass
          )}
        >
          {focusNodeStatus.label}
        </span>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div className="rounded-2xl bg-slate-50 px-4 py-3">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-400">revision</div>
          <div className="mt-2 font-semibold text-slate-900">{focusNode?.revision_index ?? 0}</div>
        </div>
        <div className="rounded-2xl bg-slate-50 px-4 py-3">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-400">gate</div>
          <div className="mt-2 font-semibold text-slate-900">
            {focusNode?.gate_required ? 'required' : 'none'}
          </div>
        </div>
        <div className="rounded-2xl bg-slate-50 px-4 py-3">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-400">artifacts</div>
          <div className="mt-2 font-semibold text-slate-900">{focusNode?.artifact_refs.length ?? 0}</div>
        </div>
        <div className="rounded-2xl bg-slate-50 px-4 py-3">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-400">diagnostics</div>
          <div className="mt-2 font-semibold text-slate-900">{focusNode?.diagnostics.length ?? 0}</div>
        </div>
      </div>
    </div>
  );

  const renderArtifactPanel = () => (
    <div className="rounded-[24px] border border-slate-200 bg-slate-50/70 p-5">
      <div className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">primary signal</div>
      <h3 className="mt-2 text-base font-semibold text-slate-900">当前产物与诊断</h3>
      {artifactHighlights.length > 0 ? (
        <div className="mt-4 space-y-3">
          {artifactHighlights.map((artifact) => (
            <div key={`${artifact.title}-${artifact.detail}`} className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
              <div className="font-medium text-slate-900">{artifact.title}</div>
              <div className="mt-1 text-sm text-slate-600 break-all">{artifact.detail}</div>
            </div>
          ))}
        </div>
      ) : diagnosticLines.length > 0 ? (
        <ul className="mt-4 space-y-3">
          {diagnosticLines.map((line) => (
            <li key={line} className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
              {line}
            </li>
          ))}
        </ul>
      ) : (
        <div className="mt-4 rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-5 text-sm leading-6 text-slate-600">
          当前节点还没有暴露新的 artifact 引用。工作台会继续跟随 runtime read-model 自动刷新，不再预先占满未来节点。
        </div>
      )}
    </div>
  );

  const renderFocusBody = () => {
    if (focusMode === 'hitl') {
      return (
        <div className="grid gap-5 2xl:grid-cols-[minmax(0,1.2fr)_320px]">
          <div className="space-y-5">
            {renderNodeSnapshot('current node', '当前主线已进入脚本审核 gate。人工决策会直接改变后续 runtime 走向。')}
            <div className="rounded-[24px] border border-amber-200 bg-amber-50/80 p-5">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.22em] text-amber-700">script preview</div>
                  <h3 className="mt-2 text-base font-semibold text-slate-900">脚本工作台</h3>
                </div>
                <div className="text-right text-xs text-amber-800">
                  <div>推荐动作：{activeGate?.recommended_action || 'approve'}</div>
                  <div>允许动作：{(activeGate?.allowed_actions || []).join(' / ') || 'approve'}</div>
                </div>
              </div>
              <pre className="mt-4 max-h-[420px] overflow-auto whitespace-pre-wrap rounded-2xl border border-amber-200 bg-white px-4 py-4 text-sm leading-6 text-slate-700">
                {scriptPreviewText || '暂无脚本预览'}
              </pre>
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-[24px] border border-slate-200 bg-white p-5">
              <div className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">decision workspace</div>
              <h3 className="mt-2 text-base font-semibold text-slate-900">审核反馈</h3>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                `approve` 会直接续跑；`revise` 和 `replan` 建议附带反馈，让主线可以回到正确分支。
              </p>
              <textarea
                className="mt-4 min-h-[180px] w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="例如：剧情冲突不够强、角色目标要更明确、镜头语言偏离原设定"
                value={feedbackText}
                onChange={(event) => setFeedbackText(event.target.value)}
              />
              {resumeHint && (
                <div className="mt-4 rounded-2xl border border-primary-200 bg-primary-50 px-4 py-3 text-sm text-primary-700">
                  {resumeHint}
                </div>
              )}
            </div>

            <div className="grid gap-3">
              <button
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-emerald-600 px-4 py-3 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
                disabled={!!submittingAction}
                onClick={() => void handleDecision('approve')}
              >
                {submittingAction === 'approve' ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" />
                )}
                批准并继续
              </button>
              <button
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-orange-600 px-4 py-3 text-sm font-medium text-white hover:bg-orange-700 disabled:opacity-60"
                disabled={!!submittingAction}
                onClick={() => void handleDecision('revise')}
              >
                {submittingAction === 'revise' ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RotateCcw className="h-4 w-4" />
                )}
                要求重写
              </button>
              <button
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-900 px-4 py-3 text-sm font-medium text-white hover:bg-slate-950 disabled:opacity-60"
                disabled={!!submittingAction}
                onClick={() => void handleDecision('replan')}
              >
                {submittingAction === 'replan' ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCcw className="h-4 w-4" />
                )}
                要求重规划
              </button>
            </div>
          </div>
        </div>
      );
    }

    if (focusMode === 'resume_available') {
      return (
        <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_280px]">
          <div className="space-y-5">
            {renderNodeSnapshot('resume checkpoint', '当前页面附着的是既有 runtime。control-plane 已确认 continuation checkpoint 存在，可以显式续跑。')}
            <div className="rounded-[24px] border border-emerald-200 bg-emerald-50/80 p-5 text-sm leading-6 text-emerald-900">
              <div className="font-semibold">恢复原因</div>
              <div className="mt-2">reason: {resumeControl?.reason_code || 'checkpoint_ready'}</div>
            </div>
          </div>
          <div className="rounded-[24px] bg-slate-950 p-5 text-white">
            <div className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-300">primary action</div>
            <h3 className="mt-2 text-lg font-semibold">恢复执行</h3>
            <p className="mt-3 text-sm leading-6 text-slate-300">
              只有在当前 run 确认存在合法 checkpoint 时，这个工作台才会给出恢复 CTA。
            </p>
            <button
              className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-white px-4 py-3 text-sm font-medium text-slate-900 hover:bg-slate-100 disabled:opacity-60"
              disabled={resumingRuntime}
              onClick={() => void handleResumeRuntime()}
            >
              {resumingRuntime ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCcw className="h-4 w-4" />
              )}
              恢复执行
            </button>
          </div>
        </div>
      );
    }

    if (focusMode === 'resume_blocked') {
      return (
        <div className="space-y-5">
          {renderNodeSnapshot('view mode', '当前工作台已经附着到 runtime，但 control-plane 并未给出可消费的 continuation checkpoint。')}
          <div className="rounded-[24px] border border-orange-200 bg-orange-50/90 p-5 text-sm leading-6 text-orange-900">
            <div className="font-semibold">恢复条件缺失</div>
            <p className="mt-2">
              这不是 fresh bootstrap；它表示当前处于查看态诊断。用户仍可以阅读已发生轨迹和上下文，但当前没有显式恢复入口。
            </p>
            <p className="mt-2 text-xs text-orange-800">reason: {resumeControl?.reason_code || 'missing_checkpoint'}</p>
          </div>
          {renderArtifactPanel()}
        </div>
      );
    }

    if (focusMode === 'failed') {
      return (
        <div className="space-y-5">
          {renderNodeSnapshot('failure snapshot', '工作台保留已发生轨迹，并把失败原因提升为主焦点，而不是继续渲染一个铺满的固定流水线。')}
          <div className="rounded-[24px] border border-red-200 bg-red-50/90 p-5">
            <div className="text-sm font-semibold text-red-900">运行失败</div>
            <p className="mt-2 text-sm leading-6 text-red-800">{runtimeFailureMessage}</p>
            {showPreNodeFailureHint && (
              <p className="mt-3 text-xs text-red-700">
                失败发生在进入首个 workflow 节点之前，因此节点列表仍保持 queued。
              </p>
            )}
          </div>
          {renderArtifactPanel()}
        </div>
      );
    }

    if (focusMode === 'completed') {
      return (
        <div className="space-y-5">
          {renderNodeSnapshot('delivery summary', '当前 run 已完成。工作台会把用户送往结果评审与下载，而不是继续停留在固定节点骨架上。')}
          <div className="grid gap-4 2xl:grid-cols-2">
            <div className="rounded-[24px] border border-emerald-200 bg-emerald-50/80 p-5 text-sm leading-6 text-emerald-900">
              <div className="font-semibold">结果已可交付</div>
              <p className="mt-2">轮询会在拿到最终视频地址后把页面切到结果评审与导出视图。</p>
            </div>
            <div className="rounded-[24px] border border-slate-200 bg-white p-5">
              <div className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">summary output</div>
              <div className="mt-4 space-y-3 text-sm text-slate-700">
                {summaryHighlights.length > 0 ? (
                  summaryHighlights.map((item) => (
                    <div key={item.key}>
                      <div className="font-medium text-slate-900">{item.key}</div>
                      <div className="mt-1 break-words text-slate-600">{item.value}</div>
                    </div>
                  ))
                ) : (
                  <div className="text-slate-600">summary_output 还没有可展示的摘要字段。</div>
                )}
              </div>
            </div>
          </div>
        </div>
      );
    }

    if (focusMode === 'detached') {
      return (
        <div className="rounded-[24px] border border-slate-200 bg-white p-6 text-sm leading-6 text-slate-600">
          任务已进入 processing，但当前还没有拿到 runtime 读模型。工作台会在下一轮同步后自动附着。
        </div>
      );
    }

    return (
      <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-5">
          {renderNodeSnapshot('current node', '主焦点只跟随当前节点和已发生轨迹。未来节点不会预占版面，直到 runtime 真正推进到那里。')}
          <div className="rounded-[24px] border border-slate-200 bg-white p-5">
            <div className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">primary action</div>
            <h3 className="mt-2 text-base font-semibold text-slate-900">等待 runtime 继续推进</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              当前阶段不需要人工动作。若 runtime 进入 HITL gate、失败态或显式恢复态，中心卡会直接切换为对应工作面板。
            </p>
          </div>
        </div>
        <div className="space-y-5">
          {renderArtifactPanel()}
          <div className="rounded-[24px] border border-slate-200 bg-white p-5">
            <div className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">runtime note</div>
            <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-sky-50 px-3 py-1 text-sm font-medium text-sky-700">
              <ArrowRight className="h-4 w-4" />
              下一步只在节点真实到达后出现
            </div>
          </div>
        </div>
      </div>
    );
  };

  if (isFreshSubmitBootstrap) {
    return (
      <div className="flex-1 overflow-auto">
        <section className="rounded-[28px] border border-blue-200 bg-white/95 p-6 shadow-card">
          <div className="flex items-start gap-3">
            <Loader2 className="mt-0.5 h-5 w-5 animate-spin text-blue-600" />
            <div>
              <h3 className="text-lg font-semibold text-slate-900">正在连接运行时</h3>
              <p className="mt-1 text-sm leading-6 text-slate-600">
                任务已经创建成功，当前仍处于首个 attempt 建立前的 bootstrap 阶段。前端会在 runtime 真正附着后切入新的工作台视图。
              </p>
            </div>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto">
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[220px_minmax(0,1fr)] 2xl:grid-cols-[220px_minmax(0,1fr)_280px]">
        <aside className="min-w-0 space-y-4">
          <section className="rounded-[24px] border border-slate-200 bg-white/90 p-5 shadow-card">
            <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">storyboard rail</div>
            <h2 className="mt-2 text-lg font-semibold text-slate-900">执行轨迹</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              这里只展示已到达节点。未来节点会等到 runtime 真正推进后再出现。
            </p>
          </section>

          <section className="rounded-[24px] border border-slate-200 bg-white/90 p-5 shadow-card">
            {workspace.arrivedNodes.length > 0 ? (
              <div className="relative pl-3">
                {workspace.arrivedNodes.map((node, index) => {
                  const meta = getNodeMeta(node.node_key);
                  const status = getStatusMeta(node.displayStatus);
                  const Icon = meta.icon;
                  const isCurrent = currentNode?.id === node.id;

                  return (
                    <div key={node.id} className="relative pb-4 last:pb-0">
                      {index < workspace.arrivedNodes.length - 1 && (
                        <div className="absolute left-[5px] top-7 h-[calc(100%-8px)] w-px bg-slate-200" />
                      )}
                      <div className={cn('absolute left-0 top-5 h-3 w-3 rounded-full', status.railDotClass)} />
                      <div
                        className={cn(
                          'ml-6 rounded-[22px] border bg-white p-3.5 transition',
                          isCurrent ? 'border-primary-300 ring-2 ring-primary-100' : 'border-slate-200'
                        )}
                      >
                        <div className="flex items-start gap-3">
                          <div className={cn('flex h-9 w-9 items-center justify-center rounded-2xl', meta.iconClass)}>
                            <Icon className="h-4.5 w-4.5" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <div className="font-medium text-slate-900">{meta.label}</div>
                              {isCurrent && (
                                <span className="rounded-full bg-primary-50 px-2 py-0.5 text-[11px] font-medium text-primary-700">
                                  当前
                                </span>
                              )}
                            </div>
                            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                              <span
                                className={cn(
                                  'inline-flex items-center rounded-full border px-2.5 py-1 font-medium',
                                  status.badgeClass
                                )}
                              >
                                {status.label}
                              </span>
                              <span>rev {node.revision_index}</span>
                            </div>
                            {isCurrent ? (
                              <p className="mt-3 text-xs leading-5 text-slate-500">
                                当前节点的详细操作面板已在中央展开。
                              </p>
                            ) : null}
                            {activeGate?.node_id === node.id && activeGate?.status === 'awaiting_human' && (
                              <p className="mt-3 text-xs font-medium text-amber-700">等待人工审核后继续。</p>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="rounded-[20px] border border-dashed border-slate-300 bg-slate-50 px-4 py-5 text-sm leading-6 text-slate-600">
                当前还没有已到达节点。工作台会在 runtime 真正附着后开始形成执行轨迹。
              </div>
            )}
          </section>
        </aside>

        <main className="min-w-0 space-y-5">
          <section className="overflow-hidden rounded-[28px] border border-slate-200 bg-white/95 shadow-card">
            <div className={cn('relative overflow-hidden bg-slate-950 px-6 py-6 text-white', `bg-gradient-to-r ${focusNodeMeta.accentClass}`)}>
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.12),transparent_45%)]" />
              <div className="relative flex flex-wrap items-start justify-between gap-5">
                <div className="max-w-2xl">
                  {renderFocusModeBadge()}
                  <div className="mt-5 flex items-center gap-3">
                    <div className={cn('flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/10', focusNodeMeta.iconClass)}>
                      <FocusIcon className="h-6 w-6" />
                    </div>
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-300">
                        {currentRequest?.title || 'quick runtime workspace'}
                      </div>
                      <h1 className="mt-1 text-2xl font-semibold text-white">{focusNodeMeta.label}</h1>
                    </div>
                  </div>
                  <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-300">
                    {focusMode === 'running' && '主视觉只围绕当前节点、已发生轨迹和当前诊断展开，不再使用铺满全页的固定流水线。'}
                    {focusMode === 'hitl' && '当前节点已进入人工确认。工作台把脚本预览、反馈输入和决策动作并置到一个可执行面板里。'}
                    {focusMode === 'resume_available' && '这是已存在 runtime 的显式恢复态，不是 fresh run 的启动阶段。'}
                    {focusMode === 'resume_blocked' && '这里呈现的是查看态诊断，不再把它误判成 fresh run 的异常启动。'}
                    {focusMode === 'failed' && '失败被提升为当前主焦点，同时保留已发生轨迹作为上下文。'}
                    {focusMode === 'completed' && '运行已经走完，工作台会把焦点转向最终交付摘要。'}
                    {focusMode === 'detached' && 'processing 页面已经打开，但 runtime 读模型还没有完成首轮附着。'}
                  </p>
                </div>

                <div className="rounded-[24px] border border-white/10 bg-white/10 p-4 backdrop-blur">
                  <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-300">runtime status</div>
                  <div className="mt-3 text-3xl font-semibold text-white">{quickRuntime?.status || 'queued'}</div>
                  <div className="mt-2 text-sm text-slate-300">
                    当前节点：{focusNodeMeta.label}
                  </div>
                  <div className="mt-1 text-sm text-slate-300">
                    已到达节点：{workspace.arrivedNodes.length}
                  </div>
                </div>
              </div>
            </div>

            <div className="p-6">{renderFocusBody()}</div>
          </section>
        </main>

        <aside className="min-w-0 space-y-4 lg:col-span-2 2xl:col-span-1">
          <ContextSection eyebrow="runtime snapshot" title="运行上下文">
            <KeyValueRow label="任务" value={currentRequest?.id || '-'} />
            <KeyValueRow label="session" value={quickRuntime?.session_id ?? '-'} />
            <KeyValueRow label="attempt" value={quickRuntime?.current_attempt_id ?? '-'} />
            <KeyValueRow label="状态" value={quickRuntime?.status || 'queued'} />
            <KeyValueRow label="更新时间" value={formatTimestamp(quickRuntime?.updated_at)} />
          </ContextSection>

          <ContextSection eyebrow="runtime guidance" title="当前提示">
            <KeyValueRow label="当前 gate" value={activeGate?.gate_name || '无'} />
            <KeyValueRow label="未来节点" value={`${workspace.futureNodes.length} 个隐藏节点`} />
            {(focusMode === 'resume_available' || focusMode === 'resume_blocked') && (
              <KeyValueRow label="恢复状态" value={resumeControl?.state || '-'} />
            )}
            {focusMode === 'resume_blocked' && (
              <KeyValueRow label="缺失原因" value={resumeControl?.reason_code || 'missing_checkpoint'} />
            )}
            {workspace.futureNodes.length > 0 && (
              <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-600">
                未来节点不会预占页面。它们只会在 runtime 真正到达时进入轨迹和焦点区。
              </div>
            )}
          </ContextSection>

          <ContextSection eyebrow="skipped path" title="本次未走通道">
            {workspace.skippedNodes.length > 0 ? (
              workspace.skippedNodes.map((node) => {
                const meta = getNodeMeta(node.node_key);
                return (
                  <div key={node.id} className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3">
                    <div className="font-medium text-slate-900">{meta.label}</div>
                    <div className="mt-1 text-xs text-zinc-600">status: skipped</div>
                    <div className="mt-2 text-sm leading-6 text-slate-600">{meta.description}</div>
                  </div>
                );
              })
            ) : (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-4 py-5 text-sm leading-6 text-slate-600">
                本次主线没有跳过节点。
              </div>
            )}
          </ContextSection>
        </aside>
      </div>
    </div>
  );
};

export default QuickModeWorkspace;
