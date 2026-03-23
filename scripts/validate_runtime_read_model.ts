import {
  getRuntimeDisplayNodes,
  getRuntimeFailureMessage,
  getRuntimeTerminalStatus,
  isPreNodeFailure,
} from '../src/lib/runtimeReadModel';
import type { TaskRuntimeView } from '../src/types';

function assertCondition(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

function buildRuntime(overrides: Partial<TaskRuntimeView> = {}): TaskRuntimeView {
  return {
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
  };
}

function validateStepZeroFailure(): void {
  const baseRuntime = buildRuntime();
  const runtime = buildRuntime({
    status: 'failed',
    current_node_key: null,
    active_gate: null,
    error_message: 'step-0 failed before entering first node',
    nodes: baseRuntime.nodes.map((node) => ({ ...node, status: 'queued' })),
  });

  assertCondition(
    getRuntimeTerminalStatus(runtime) === 'failed',
    'step-0 failure should be treated as terminal runtime failure'
  );
  assertCondition(
    getRuntimeFailureMessage(runtime) === 'step-0 failed before entering first node',
    'step-0 failure should preserve runtime error message'
  );
  assertCondition(isPreNodeFailure(runtime), 'step-0 failure should be marked as pre-node failure');
  console.log('PASS step-0 failure stays runtime-first even when all nodes remain queued');
}

function validateAwaitingHumanGate(): void {
  const runtime = buildRuntime();
  const scriptNode = getRuntimeDisplayNodes(runtime).find((node) => node.node_key === 'script');

  assertCondition(scriptNode, 'script node should exist in runtime display nodes');
  assertCondition(
    scriptNode.displayStatus === 'pending_gate',
    'awaiting_human gate should override node display status to pending_gate'
  );
  console.log('PASS awaiting_human gate maps the bound node to pending_gate');
}

function validateResumeState(): void {
  const baseRuntime = buildRuntime();
  const runtime = buildRuntime({
    status: 'running',
    current_node_key: 'image',
    active_gate: null,
    nodes: baseRuntime.nodes.map((node) =>
      node.node_key === 'script'
        ? { ...node, status: 'completed' }
        : node.node_key === 'image'
          ? { ...node, status: 'running' }
          : node
    ),
  });

  const displayNodes = getRuntimeDisplayNodes(runtime);
  const scriptNode = displayNodes.find((node) => node.node_key === 'script');
  const imageNode = displayNodes.find((node) => node.node_key === 'image');

  assertCondition(getRuntimeTerminalStatus(runtime) === null, 'resumed runtime should not be marked terminal');
  assertCondition(scriptNode?.displayStatus === 'completed', 'resume should clear pending_gate after gate closure');
  assertCondition(
    imageNode?.displayStatus === 'running',
    'resume should expose the next running node from runtime view'
  );
  console.log('PASS resume state clears gate overlay and keeps runtime current node authoritative');
}

function validateCompletedTerminalState(): void {
  const runtime = buildRuntime({
    status: 'completed',
    current_node_key: 'compose',
    active_gate: null,
  });

  assertCondition(
    getRuntimeTerminalStatus(runtime) === 'completed',
    'completed runtime should be treated as terminal'
  );
  assertCondition(
    getRuntimeFailureMessage(runtime) === null,
    'completed runtime should not surface a failure message'
  );
  console.log('PASS completed runtime stays separate from failure presentation');
}

validateStepZeroFailure();
validateAwaitingHumanGate();
validateResumeState();
validateCompletedTerminalState();

console.log('Runtime read-model validation passed');
