'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, Loader2, MessageSquareText, RefreshCcw, RotateCcw } from 'lucide-react';

import AgentOrchestrator from '@/components/agents/AgentOrchestrator';
import RealTimeProgress from '@/components/progress/RealTimeProgress';
import { ApiClient } from '@/lib/api';
import { useAppStore } from '@/store/useAppStore';

const statusClassMap: Record<string, string> = {
  queued: 'bg-gray-100 text-gray-700',
  running: 'bg-blue-100 text-blue-700',
  pending_gate: 'bg-amber-100 text-amber-700',
  approved: 'bg-emerald-100 text-emerald-700',
  needs_revision: 'bg-orange-100 text-orange-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  skipped: 'bg-gray-100 text-gray-500',
  stale: 'bg-zinc-100 text-zinc-600',
};

const actionLabelMap: Record<string, string> = {
  approve: '批准并继续',
  revise: '要求重写',
  replan: '要求重规划',
};

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

const QuickModeWorkspace: React.FC = () => {
  const { currentRequest, quickRuntime, setQuickRuntime, addNotification } = useAppStore();
  const [feedbackText, setFeedbackText] = useState('');
  const [submittingAction, setSubmittingAction] = useState<string | null>(null);
  const [resumeHint, setResumeHint] = useState<string | null>(null);

  const activeGate = quickRuntime?.active_gate;
  const isScriptGate = activeGate?.gate_name === 'script_review';
  const scriptPreviewText = useMemo(
    () => String(activeGate?.facts?.script_preview_text || '').trim(),
    [activeGate?.facts]
  );

  useEffect(() => {
    if (activeGate?.status === 'awaiting_human') {
      setResumeHint(null);
    }
  }, [activeGate?.id, activeGate?.status]);

  const handleDecision = async (action: 'approve' | 'revise' | 'replan') => {
    if (!currentRequest?.id) return;
    try {
      setSubmittingAction(action);
      const result = await ApiClient.submitScriptGateDecision(currentRequest.id, {
        action,
        feedback_text: feedbackText.trim() || undefined,
      });
      if (result.workflow_status) {
        setQuickRuntime(result.workflow_status);
      }
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

  const runtimeNodes = useMemo(
    () =>
      (quickRuntime?.nodes || []).map((node) => {
        const gateBound = activeGate?.node_id === node.id && activeGate?.status === 'awaiting_human';
        return {
          ...node,
          displayStatus: gateBound ? 'pending_gate' : node.status,
        };
      }),
    [quickRuntime?.nodes, activeGate?.node_id, activeGate?.status]
  );

  return (
    <div className="flex-1 flex flex-col gap-6 overflow-auto">
      {isScriptGate && activeGate?.status === 'awaiting_human' && (
        <section className="bg-white/95 backdrop-blur rounded-xl shadow-card border border-amber-200 p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full bg-amber-100 text-amber-800 px-3 py-1 text-xs font-medium">
                <MessageSquareText className="w-4 h-4" />
                等待脚本确认
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mt-3">脚本工作台</h3>
              <p className="text-sm text-gray-600 mt-1">当前流程已在 `script gate` 暂停。确认后才会继续后续生成。</p>
            </div>
            <div className="text-right text-sm text-gray-500">
              <div>推荐动作：{activeGate.recommended_action || 'approve'}</div>
              <div>允许动作：{(activeGate.allowed_actions || []).join(' / ') || 'approve'}</div>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-1 xl:grid-cols-[minmax(0,1.4fr)_360px] gap-6">
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
              <div className="flex items-center justify-between mb-3">
                <h4 className="font-medium text-gray-900">脚本预览</h4>
                <span className="text-xs text-gray-500">触发原因：{String(activeGate.facts?.trigger_reason || 'initial')}</span>
              </div>
              <pre className="whitespace-pre-wrap text-sm leading-6 text-gray-700 max-h-[420px] overflow-auto">
                {scriptPreviewText || '暂无脚本预览'}
              </pre>
            </div>

            <div className="rounded-xl border border-gray-200 bg-white p-4">
              <h4 className="font-medium text-gray-900">审核反馈</h4>
              <p className="text-sm text-gray-600 mt-1">`approve` 可直接续跑；`revise` 和 `replan` 建议补充反馈。</p>
              <textarea
                className="mt-4 w-full min-h-[180px] rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="例如：剧情方向不对、角色设定需要调整、某段对白要更简洁"
                value={feedbackText}
                onChange={(e) => setFeedbackText(e.target.value)}
              />
              {resumeHint && (
                <div className="mt-4 rounded-lg border border-primary-200 bg-primary-50 px-3 py-2 text-sm text-primary-700">
                  {resumeHint}
                </div>
              )}
              <div className="mt-4 grid grid-cols-1 gap-3">
                <button
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
                  disabled={!!submittingAction}
                  onClick={() => void handleDecision('approve')}
                >
                  {submittingAction === 'approve' ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                  批准并继续
                </button>
                <button
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-orange-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-orange-700 disabled:opacity-60"
                  disabled={!!submittingAction}
                  onClick={() => void handleDecision('revise')}
                >
                  {submittingAction === 'revise' ? <Loader2 className="w-4 h-4 animate-spin" /> : <RotateCcw className="w-4 h-4" />}
                  要求重写
                </button>
                <button
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-800 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-60"
                  disabled={!!submittingAction}
                  onClick={() => void handleDecision('replan')}
                >
                  {submittingAction === 'replan' ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCcw className="w-4 h-4" />}
                  要求重规划
                </button>
              </div>
            </div>
          </div>
        </section>
      )}

      {quickRuntime?.status === 'failed' && (
        <section className="bg-white/95 backdrop-blur rounded-xl shadow-card border border-red-200 p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-600 mt-0.5" />
            <div>
              <h3 className="text-lg font-semibold text-red-900">运行失败</h3>
              <p className="text-sm text-red-700 mt-1">
                {quickRuntime.error_message || '当前 run 已失败。'}
              </p>
              {!quickRuntime.current_node_key && (
                <p className="text-xs text-red-600 mt-2">
                  失败发生在进入首个 workflow 节点之前，因此节点列表仍保持 queued。
                </p>
              )}
            </div>
          </div>
        </section>
      )}

      <section className="bg-white/90 backdrop-blur rounded-xl shadow-card border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">运行时状态</h3>
            <p className="text-sm text-gray-600">session: {quickRuntime?.session_id ?? '-'} / status: {quickRuntime?.status ?? 'queued'}</p>
          </div>
          {quickRuntime?.current_node_key && (
            <span className="rounded-full bg-primary-50 text-primary-700 px-3 py-1 text-xs font-medium">
              当前节点：{nodeLabelMap[quickRuntime.current_node_key] || quickRuntime.current_node_key}
            </span>
          )}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          {runtimeNodes.map((node) => (
            <div key={node.node_key} className="rounded-lg border border-gray-200 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-gray-900">{nodeLabelMap[node.node_key] || node.node_key}</div>
                  <div className="text-xs text-gray-500 mt-1">rev {node.revision_index}</div>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusClassMap[node.displayStatus] || 'bg-gray-100 text-gray-700'}`}>
                  {node.displayStatus}
                </span>
              </div>
              {activeGate?.node_id === node.id && activeGate?.status === 'awaiting_human' && (
                <p className="mt-3 text-xs text-amber-700">该节点等待人工审核后继续。</p>
              )}
            </div>
          ))}
        </div>
      </section>

      <div className="bg-white/90 backdrop-blur rounded-xl shadow-card border border-gray-200 p-6 mt-2">
        <AgentOrchestrator />
      </div>
      <div className="bg-white/90 backdrop-blur rounded-xl shadow-card border border-gray-200 p-6">
        <RealTimeProgress />
      </div>
    </div>
  );
};

export default QuickModeWorkspace;
