import '@testing-library/jest-dom';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
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
    expect(screen.getByText('等待脚本确认')).toBeInTheDocument();
    expect(screen.getByText('场景 1：主角登场\\n场景 2：冲突展开')).toBeInTheDocument();
    expect(screen.getAllByText('脚本创作').length).toBeGreaterThan(0);
    expect(screen.getAllByText('pending_gate').length).toBeGreaterThan(0);
    expect(screen.getByText(/该节点等待人工审核后继续/)).toBeInTheDocument();
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
    await user.click(screen.getByRole('button', { name: '批准并继续' }));

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

    await user.click(screen.getByRole('button', { name: '要求重写' }));
    await waitFor(() => {
      expect(mockSubmitScriptGateDecision).toHaveBeenCalledWith('task-123', {
        action: 'revise',
        feedback_text: undefined,
      });
    });
    expect(screen.getByText('已提交要求重写，等待主线恢复…')).toBeInTheDocument();

    rerender(
      <I18nProvider defaultLang="zh">
        <QuickModeWorkspace />
      </I18nProvider>
    );

    await user.click(screen.getByRole('button', { name: '要求重规划' }));
    await waitFor(() => {
      expect(mockSubmitScriptGateDecision).toHaveBeenCalledWith('task-123', {
        action: 'replan',
        feedback_text: undefined,
      });
    });
    expect(screen.getByText('已提交要求重规划，等待主线恢复…')).toBeInTheDocument();
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

    expect(screen.getByText('运行失败')).toBeInTheDocument();
    expect(screen.getByText('step-0 failed before entering first node')).toBeInTheDocument();
    expect(screen.getByText('失败发生在进入首个 workflow 节点之前，因此节点列表仍保持 queued。')).toBeInTheDocument();
  });
});
