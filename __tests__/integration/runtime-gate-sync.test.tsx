import '@testing-library/jest-dom';
import React from 'react';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import QuickModeWorkspace from '@/components/preview/QuickModeWorkspace';
import { useAppStore } from '@/store/useAppStore';
import { ApiClient } from '@/lib/api';
import type { TaskRuntimeView } from '@/types';
import { I18nProvider } from '@/i18n/I18nProvider';

jest.mock('@/store/useAppStore');
jest.mock('@/components/agents/AgentOrchestrator', () => () => (
  <div data-testid="agent-orchestrator-stub">agent-orchestrator</div>
));
jest.mock('@/components/progress/RealTimeProgress', () => () => (
  <div data-testid="realtime-progress-stub">realtime-progress</div>
));
jest.mock('@/lib/api', () => ({
  ApiClient: {
    submitScriptGateDecision: jest.fn(),
  },
}));

const mockUseAppStore = useAppStore as jest.MockedFunction<typeof useAppStore>;
const mockSubmitScriptGateDecision = ApiClient.submitScriptGateDecision as jest.MockedFunction<
  typeof ApiClient.submitScriptGateDecision
>;

const buildRuntime = (overrides: Partial<TaskRuntimeView> = {}): TaskRuntimeView => ({
  session_id: 12,
  task_db_id: 34,
  mode: 'quick',
  status: 'waiting_gate',
  current_node_key: 'script',
  current_attempt_id: 56,
  active_gate: {
    id: 78,
    node_id: 2,
    attempt_id: 56,
    gate_name: 'script_review',
    gate_type: 'human_review',
    status: 'awaiting_human',
    contract_version: '1',
    artifact_refs: [],
    facts: {
      trigger_reason: 'initial',
      script_preview_text: '场景 1：主角登场\\n场景 2：冲突展开',
    },
    result_code: null,
    reason_code: null,
    allowed_actions: ['approve', 'revise', 'replan'],
    recommended_action: 'approve',
    latest_decision: null,
    created_at: '2026-03-19T00:00:00Z',
    updated_at: '2026-03-19T00:00:00Z',
  },
  error_message: null,
  summary_output: {},
  nodes: [
    {
      id: 1,
      node_key: 'concept',
      node_type: 'agent',
      order_index: 0,
      scope_type: 'episode',
      scope_ref: null,
      status: 'completed',
      revision_index: 0,
      gate_required: false,
      last_gate_id: null,
      artifact_refs: [],
      diagnostics: [],
    },
    {
      id: 2,
      node_key: 'script',
      node_type: 'agent',
      order_index: 1,
      scope_type: 'episode',
      scope_ref: null,
      status: 'running',
      revision_index: 0,
      gate_required: true,
      last_gate_id: 78,
      artifact_refs: [],
      diagnostics: [],
    },
    {
      id: 3,
      node_key: 'image',
      node_type: 'agent',
      order_index: 2,
      scope_type: 'episode',
      scope_ref: null,
      status: 'queued',
      revision_index: 0,
      gate_required: false,
      last_gate_id: null,
      artifact_refs: [],
      diagnostics: [],
    },
  ],
  created_at: '2026-03-19T00:00:00Z',
  updated_at: '2026-03-19T00:00:00Z',
  ...overrides,
});

const renderWorkspace = (storeOverrides: Record<string, any> = {}) => {
  const baseRuntime = buildRuntime();
  const store = {
    currentRequest: {
      id: 'task-123',
      title: '测试单集任务',
    },
    quickProcessingContext: 'attached_runtime',
    quickRuntime: baseRuntime,
    agents: [
      {
        id: 'concept-generator',
        name: '概念生成',
        type: 'concept-generator',
        status: 'working',
        progress: 60,
        description: '遥测占位',
        capabilities: [],
        currentTask: '遥测中',
      },
    ],
    setQuickRuntime: jest.fn(),
    addNotification: jest.fn(),
    ...storeOverrides,
  };

  mockUseAppStore.mockReturnValue(store as any);

  return {
    ...render(
      <I18nProvider defaultLang="zh">
        <QuickModeWorkspace />
      </I18nProvider>
    ),
    store,
  };
};

describe('runtime gate sync', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders script gate and runtime-driven node states', () => {
    renderWorkspace();

    expect(screen.getByText('脚本工作台')).toBeInTheDocument();
    expect(screen.getByText('等待人工确认')).toBeInTheDocument();
    expect(screen.getByText('场景 1：主角登场\\n场景 2：冲突展开')).toBeInTheDocument();
    expect(screen.getAllByText('脚本创作').length).toBeGreaterThan(0);
    expect(screen.getByText('执行轨迹')).toBeInTheDocument();
    expect(screen.getByText(/等待人工审核后继续/)).toBeInTheDocument();
    expect(screen.queryByText('图像生成')).not.toBeInTheDocument();
  });

  it('submits approve and writes resumed runtime state back to store', async () => {
    const resumedRuntime = buildRuntime({
      status: 'running',
      current_node_key: 'image',
      active_gate: null,
      nodes: buildRuntime().nodes.map((node) =>
        node.node_key === 'script'
          ? { ...node, status: 'completed' }
          : node.node_key === 'image'
            ? { ...node, status: 'running' }
            : node
      ),
    });
    mockSubmitScriptGateDecision.mockResolvedValue({
      message: 'ok',
      task_id: 'task-123',
      runtime: resumedRuntime,
    });

    const user = userEvent.setup();
    const { store } = renderWorkspace();
    await act(async () => {
      await user.click(screen.getByRole('button', { name: '批准并继续' }));
    });

    await waitFor(() => {
      expect(mockSubmitScriptGateDecision).toHaveBeenCalledWith('task-123', {
        action: 'approve',
        feedback_text: undefined,
      });
      expect(store.setQuickRuntime).toHaveBeenCalledWith(resumedRuntime);
    });

    expect(screen.getByText('已提交批准并继续，等待主线恢复…')).toBeInTheDocument();
  });

  it('submits revise and replan with visible resume hints', async () => {
    mockSubmitScriptGateDecision.mockResolvedValue({
      message: 'ok',
      task_id: 'task-123',
      runtime: buildRuntime({
        status: 'running',
        current_node_key: 'script',
        active_gate: null,
      }),
    });

    const user = userEvent.setup();
    const { rerender } = renderWorkspace();

    await act(async () => {
      await user.click(screen.getByRole('button', { name: '要求重写' }));
    });
    await waitFor(() => {
      expect(mockSubmitScriptGateDecision).toHaveBeenCalledWith('task-123', {
        action: 'revise',
        feedback_text: undefined,
      });
    });
    expect(await screen.findByText('已提交要求重写，等待主线恢复…')).toBeInTheDocument();

    rerender(
      <I18nProvider defaultLang="zh">
        <QuickModeWorkspace />
      </I18nProvider>
    );

    await act(async () => {
      await user.click(screen.getByRole('button', { name: '要求重规划' }));
    });
    await waitFor(() => {
      expect(mockSubmitScriptGateDecision).toHaveBeenCalledWith('task-123', {
        action: 'replan',
        feedback_text: undefined,
      });
    });
    expect(await screen.findByText('已提交要求重规划，等待主线恢复…')).toBeInTheDocument();
  });

  it('renders runtime failure as the primary state even when nodes remain queued', () => {
    renderWorkspace({
      quickRuntime: buildRuntime({
        status: 'failed',
        current_node_key: null,
        active_gate: null,
        error_message: 'step-0 failed before entering first node',
        nodes: buildRuntime().nodes.map((node) => ({ ...node, status: 'queued' })),
      }),
    });

    expect(screen.getAllByText('运行失败').length).toBeGreaterThan(0);
    expect(screen.getByText('step-0 failed before entering first node')).toBeInTheDocument();
    expect(screen.getByText('失败发生在进入首个 workflow 节点之前，因此节点列表仍保持 queued。')).toBeInTheDocument();
  });

  it('renders role continuity diagnostics from runtime summary output only', () => {
    renderWorkspace({
      quickRuntime: buildRuntime({
        status: 'completed',
        current_node_key: 'quality',
        active_gate: null,
        summary_output: {
          final_video_url: '/files/final.mp4',
          role_continuity_diagnostics: {
            version: 'v1',
            status: 'not_evaluated',
            review_status: 'unverified',
            role_continuity_score: null,
            visual_evidence_verified: false,
            score_cap: 89,
            fallback_reason: 'role_continuity_visual_evidence_missing',
            unverified_reason: 'role_continuity_visual_evidence_missing',
            requires_human_review: true,
            approval_status: 'conditional',
            contract_readiness: {
              status: 'ready',
              score: 100,
              same_carrier_verified: true,
            },
            identity_drift_findings: [],
            display_summary: {
              characters: [
                {
                  canonical_id: 'child',
                  display_name: 'Child',
                  stable_anchor_count: 3,
                  allowed_variant_count: 3,
                  reference_asset_count: 0,
                },
              ],
              character_count: 1,
              scene_lock_count: 6,
              locked_scene_numbers: [1, 2, 3, 4, 5, 6],
              missing_lock_scenes: [],
              empty_cast_scenes: [],
            },
          },
        },
      }),
    });

    expect(screen.getByText('角色一致性未验证')).toBeInTheDocument();
    expect(screen.getAllByText('未验证').length).toBeGreaterThan(0);
    expect(screen.getByText('ready / 同源')).toBeInTheDocument();
    expect(screen.getByText('Child')).toBeInTheDocument();
    expect(screen.getByText('1, 2, 3, 4, 5, 6')).toBeInTheDocument();
    expect(screen.getByText('reason: role_continuity_visual_evidence_missing')).toBeInTheDocument();
    expect(screen.queryByText(/canonical_id/)).not.toBeInTheDocument();
  });

  it('keeps fresh-submit bootstrap separate from resume-blocked workspace state', () => {
    renderWorkspace({
      quickProcessingContext: 'fresh_submit',
      quickRuntime: buildRuntime({
        status: 'queued',
        current_node_key: null,
        current_attempt_id: null,
        active_gate: null,
        resume_control: {
          state: 'resume_blocked',
          can_resume: false,
          reason_code: 'missing_current_attempt',
        },
        nodes: buildRuntime().nodes.map((node) => ({
          ...node,
          status: 'queued',
        })),
      }),
    });

    expect(screen.getByText('正在连接运行时')).toBeInTheDocument();
    expect(screen.queryByText('恢复条件缺失')).not.toBeInTheDocument();
  });

  it('folds skipped nodes into the side summary instead of the main storyboard rail', () => {
    renderWorkspace({
      quickRuntime: buildRuntime({
        status: 'running',
        current_node_key: 'compose',
        current_attempt_id: 91,
        active_gate: null,
        nodes: [
          {
            id: 1,
            node_key: 'concept',
            node_type: 'agent',
            order_index: 0,
            scope_type: 'episode',
            scope_ref: null,
            status: 'completed',
            revision_index: 0,
            gate_required: false,
            last_gate_id: null,
            artifact_refs: [],
            diagnostics: [],
          },
          {
            id: 2,
            node_key: 'script',
            node_type: 'agent',
            order_index: 1,
            scope_type: 'episode',
            scope_ref: null,
            status: 'completed',
            revision_index: 0,
            gate_required: true,
            last_gate_id: 78,
            artifact_refs: [],
            diagnostics: [],
          },
          {
            id: 3,
            node_key: 'voice',
            node_type: 'agent',
            order_index: 2,
            scope_type: 'episode',
            scope_ref: null,
            status: 'skipped',
            revision_index: 0,
            gate_required: false,
            last_gate_id: null,
            artifact_refs: [],
            diagnostics: [],
          },
          {
            id: 4,
            node_key: 'compose',
            node_type: 'agent',
            order_index: 3,
            scope_type: 'episode',
            scope_ref: null,
            status: 'running',
            revision_index: 0,
            gate_required: false,
            last_gate_id: null,
            artifact_refs: [],
            diagnostics: [],
          },
        ],
      }),
    });

    const skippedSection = screen.getByText('本次未走通道').closest('section');
    expect(skippedSection).not.toBeNull();
    expect(within(skippedSection as HTMLElement).getByText('语音合成')).toBeInTheDocument();
    expect(screen.queryAllByText('语音合成')).toHaveLength(1);
  });
});
