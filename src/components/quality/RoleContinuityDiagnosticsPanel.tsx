'use client';

import React from 'react';
import {
  AlertTriangle,
  Eye,
  EyeOff,
  Info,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';

import {
  getRoleContinuityDiagnostics,
  type RoleContinuityReviewStatus,
} from '@/lib/runtimeReadModel';
import { cn } from '@/lib/utils';

interface RoleContinuityDiagnosticsPanelProps {
  summaryOutput?: Record<string, unknown> | null;
  className?: string;
  compact?: boolean;
}

const reviewMeta: Record<
  string,
  {
    title: string;
    badge: string;
    description: string;
    icon: React.ComponentType<{ className?: string }>;
    panelClass: string;
    iconClass: string;
    badgeClass: string;
  }
> = {
  deliverable: {
    title: '角色一致性可交付',
    badge: '可交付',
    description: '视觉证据已验证，角色连续性进入可交付状态。',
    icon: ShieldCheck,
    panelClass: 'border-emerald-200 bg-emerald-50/80',
    iconClass: 'bg-emerald-100 text-emerald-700',
    badgeClass: 'border-emerald-200 bg-white text-emerald-700',
  },
  needs_human_review: {
    title: '角色一致性需复核',
    badge: '需复核',
    description: '角色合同或视觉证据不足，当前结果需要人工确认。',
    icon: AlertTriangle,
    panelClass: 'border-amber-200 bg-amber-50/80',
    iconClass: 'bg-amber-100 text-amber-700',
    badgeClass: 'border-amber-200 bg-white text-amber-800',
  },
  unverified: {
    title: '角色一致性未验证',
    badge: '未验证',
    description: '角色合同已进入读模型，但当前缺少视觉观察证据。',
    icon: EyeOff,
    panelClass: 'border-sky-200 bg-sky-50/80',
    iconClass: 'bg-sky-100 text-sky-700',
    badgeClass: 'border-sky-200 bg-white text-sky-700',
  },
  failed: {
    title: '角色漂移失败',
    badge: '失败',
    description: '质量检查发现角色连续性漂移，系统评分应受限制。',
    icon: ShieldAlert,
    panelClass: 'border-red-200 bg-red-50/80',
    iconClass: 'bg-red-100 text-red-700',
    badgeClass: 'border-red-200 bg-white text-red-700',
  },
  not_required: {
    title: '未要求角色一致性检查',
    badge: '未要求',
    description: '当前运行读模型声明本次无需角色一致性验收。',
    icon: Info,
    panelClass: 'border-slate-200 bg-slate-50/80',
    iconClass: 'bg-slate-100 text-slate-700',
    badgeClass: 'border-slate-200 bg-white text-slate-700',
  },
  not_available: {
    title: '角色诊断不可用',
    badge: '不可用',
    description: '当前运行读模型没有可用的角色一致性诊断结果。',
    icon: Info,
    panelClass: 'border-slate-200 bg-slate-50/80',
    iconClass: 'bg-slate-100 text-slate-700',
    badgeClass: 'border-slate-200 bg-white text-slate-700',
  },
  unknown: {
    title: '角色诊断未知',
    badge: '未知',
    description: '当前运行读模型返回了未知的角色一致性状态。',
    icon: Info,
    panelClass: 'border-slate-200 bg-slate-50/80',
    iconClass: 'bg-slate-100 text-slate-700',
    badgeClass: 'border-slate-200 bg-white text-slate-700',
  },
};

function getReviewMeta(status: RoleContinuityReviewStatus) {
  return reviewMeta[status] || reviewMeta.unknown;
}

function formatScore(value: number | null): string {
  return value === null ? '-' : String(value);
}

function formatScenes(scenes: number[]): string {
  if (scenes.length === 0) {
    return '-';
  }
  return scenes.join(', ');
}

function formatFinding(finding: Record<string, unknown>, index: number): string {
  const sceneNumber =
    typeof finding.scene_number === 'number'
      ? `场景 ${finding.scene_number}`
      : typeof finding.scene === 'number'
        ? `场景 ${finding.scene}`
        : '';
  const message =
    typeof finding.message === 'string'
      ? finding.message
      : typeof finding.reason === 'string'
        ? finding.reason
        : typeof finding.code === 'string'
          ? finding.code
          : `漂移发现 ${index + 1}`;
  return sceneNumber ? `${sceneNumber}: ${message}` : message;
}

const Metric: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="rounded-lg border border-white/70 bg-white/80 px-3 py-2">
    <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">{label}</div>
    <div className="mt-1 text-sm font-medium leading-5 text-slate-900 break-words">{value}</div>
  </div>
);

const RoleContinuityDiagnosticsPanel: React.FC<RoleContinuityDiagnosticsPanelProps> = ({
  summaryOutput,
  className,
  compact = false,
}) => {
  const diagnostics = getRoleContinuityDiagnostics(summaryOutput);
  if (!diagnostics) {
    return null;
  }

  const meta = getReviewMeta(diagnostics.reviewStatus);
  const Icon = meta.icon;
  const characters = diagnostics.displaySummary.characters;
  const characterNames =
    characters.length > 0
      ? characters.map((character) => character.displayName).join(' / ')
      : `${diagnostics.displaySummary.characterCount} 个角色`;
  const fallbackText = diagnostics.unverifiedReason || diagnostics.fallbackReason || diagnostics.status;

  return (
    <section className={cn('rounded-xl border p-4', meta.panelClass, className)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className={cn('flex h-10 w-10 shrink-0 items-center justify-center rounded-lg', meta.iconClass)}>
            <Icon className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
              role continuity
            </div>
            <h3 className="mt-1 text-base font-semibold text-slate-950">{meta.title}</h3>
            {!compact && <p className="mt-1 text-sm leading-6 text-slate-700">{meta.description}</p>}
          </div>
        </div>
        <span className={cn('inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold', meta.badgeClass)}>
          {meta.badge}
        </span>
      </div>

      <div className={cn('mt-4 grid gap-2', compact ? 'grid-cols-2' : 'grid-cols-2 xl:grid-cols-4')}>
        <Metric
          label="视觉证据"
          value={
            <span className="inline-flex items-center gap-1.5">
              {diagnostics.visualEvidenceVerified ? (
                <Eye className="h-3.5 w-3.5 text-emerald-600" />
              ) : (
                <EyeOff className="h-3.5 w-3.5 text-sky-700" />
              )}
              {diagnostics.visualEvidenceVerified ? '已验证' : '未验证'}
            </span>
          }
        />
        <Metric label="角色分" value={formatScore(diagnostics.roleContinuityScore)} />
        <Metric label="score cap" value={formatScore(diagnostics.scoreCap)} />
        <Metric
          label="合同状态"
          value={`${diagnostics.contractReadiness.status}${
            diagnostics.contractReadiness.sameCarrierVerified ? ' / 同源' : ''
          }`}
        />
      </div>

      {!compact && (
        <div className="mt-3 grid gap-2 text-sm lg:grid-cols-2">
          <Metric label="角色" value={characterNames} />
          <Metric label="锁定场景" value={formatScenes(diagnostics.displaySummary.lockedSceneNumbers)} />
        </div>
      )}

      {fallbackText && diagnostics.reviewStatus !== 'deliverable' && (
        <div className="mt-3 rounded-lg border border-white/70 bg-white/70 px-3 py-2 text-xs leading-5 text-slate-700">
          reason: {fallbackText}
        </div>
      )}

      {diagnostics.identityDriftFindings.length > 0 && (
        <div className="mt-3 space-y-2">
          {diagnostics.identityDriftFindings.slice(0, 2).map((finding, index) => (
            <div
              key={`${formatFinding(finding, index)}-${index}`}
              className="rounded-lg border border-red-100 bg-white/80 px-3 py-2 text-xs leading-5 text-red-800"
            >
              {formatFinding(finding, index)}
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

export default RoleContinuityDiagnosticsPanel;
