import type { RuntimeGate, RuntimeNodeState, TaskRuntimeView } from '@/types';

export interface RuntimeDisplayNode extends RuntimeNodeState {
  displayStatus: string;
}

export interface RuntimeWorkspaceProjection {
  currentNode: RuntimeDisplayNode | null;
  focusNode: RuntimeDisplayNode | null;
  arrivedNodes: RuntimeDisplayNode[];
  skippedNodes: RuntimeDisplayNode[];
  futureNodes: RuntimeDisplayNode[];
}

export type RuntimeTerminalStatus = 'failed' | 'completed' | null;

const arrivedDisplayStatuses = new Set([
  'completed',
  'running',
  'pending_gate',
  'approved',
  'needs_revision',
  'failed',
  'stale',
]);

export function getRuntimeTerminalStatus(runtime?: TaskRuntimeView | null): RuntimeTerminalStatus {
  const status = runtime?.status;
  if (status === 'failed' || status === 'completed') {
    return status;
  }
  return null;
}

export function getRuntimeFailureMessage(
  runtime?: TaskRuntimeView | null,
  fallback = '当前 run 已失败。'
): string | null {
  if (getRuntimeTerminalStatus(runtime) !== 'failed') {
    return null;
  }

  const message = typeof runtime?.error_message === 'string' ? runtime.error_message.trim() : '';
  return message || fallback;
}

export function isPreNodeFailure(runtime?: TaskRuntimeView | null): boolean {
  return getRuntimeTerminalStatus(runtime) === 'failed' && !runtime?.current_node_key;
}

export function isBootstrapRuntimePlaceholder(runtime?: TaskRuntimeView | null): boolean {
  if (!runtime) {
    return false;
  }

  return (
    runtime.status === 'queued' &&
    !runtime.current_node_key &&
    !runtime.current_attempt_id &&
    !runtime.active_gate &&
    runtime.resume_control?.state === 'resume_blocked' &&
    runtime.resume_control.reason_code === 'missing_current_attempt'
  );
}

export function getRuntimeNodeDisplayStatus(
  node: RuntimeNodeState,
  activeGate?: RuntimeGate | null
): string {
  const gateBound = activeGate?.node_id === node.id && activeGate?.status === 'awaiting_human';
  return gateBound ? 'pending_gate' : node.status;
}

export function getRuntimeDisplayNodes(runtime?: TaskRuntimeView | null): RuntimeDisplayNode[] {
  const activeGate = runtime?.active_gate;
  return (runtime?.nodes || []).map((node) => ({
    ...node,
    displayStatus: getRuntimeNodeDisplayStatus(node, activeGate),
  }));
}

export function getRuntimeWorkspaceProjection(
  runtime?: TaskRuntimeView | null
): RuntimeWorkspaceProjection {
  const nodes = getRuntimeDisplayNodes(runtime).sort((left, right) => left.order_index - right.order_index);
  const currentNodeKey = runtime?.current_node_key ?? null;
  const currentNode = nodes.find((node) => node.node_key === currentNodeKey) ?? null;
  const arrivedNodes: RuntimeDisplayNode[] = [];
  const skippedNodes: RuntimeDisplayNode[] = [];
  const futureNodes: RuntimeDisplayNode[] = [];

  nodes.forEach((node) => {
    const isCurrentNode = currentNode?.id === node.id;
    if (node.displayStatus === 'skipped' && !isCurrentNode) {
      skippedNodes.push(node);
      return;
    }

    if (isCurrentNode || arrivedDisplayStatuses.has(node.displayStatus)) {
      arrivedNodes.push(node);
      return;
    }

    futureNodes.push(node);
  });

  return {
    currentNode,
    focusNode: currentNode ?? arrivedNodes[arrivedNodes.length - 1] ?? null,
    arrivedNodes,
    skippedNodes,
    futureNodes,
  };
}
