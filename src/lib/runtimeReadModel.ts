import type { RuntimeGate, RuntimeNodeState, TaskRuntimeView } from '@/types';

export interface RuntimeDisplayNode extends RuntimeNodeState {
  displayStatus: string;
}

export type RuntimeTerminalStatus = 'failed' | 'completed' | null;

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
