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

export type RoleContinuityReviewStatus =
  | 'deliverable'
  | 'needs_human_review'
  | 'unverified'
  | 'failed'
  | 'not_required'
  | 'not_available'
  | 'unknown'
  | string;

export interface RoleContinuityDisplayCharacter {
  displayName: string;
  stableAnchorCount: number | null;
  allowedVariantCount: number | null;
  referenceAssetCount: number | null;
}

export interface RoleContinuityDiagnostics {
  version: string;
  status: string;
  reviewStatus: RoleContinuityReviewStatus;
  roleContinuityScore: number | null;
  visualEvidenceVerified: boolean;
  scoreCap: number | null;
  fallbackReason: string;
  unverifiedReason: string;
  requiresHumanReview: boolean;
  approvalStatus: string;
  contractReadiness: {
    status: string;
    score: number | null;
    sameCarrierVerified: boolean;
  };
  identityDriftFindings: Array<Record<string, unknown>>;
  displaySummary: {
    characters: RoleContinuityDisplayCharacter[];
    characterCount: number;
    sceneLockCount: number;
    lockedSceneNumbers: number[];
    missingLockScenes: number[];
    emptyCastScenes: number[];
  };
}

const arrivedDisplayStatuses = new Set([
  'completed',
  'running',
  'pending_gate',
  'approved',
  'needs_revision',
  'failed',
  'stale',
]);

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value.trim().length > 0 ? value : fallback;
}

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function asBoolean(value: unknown): boolean {
  return value === true;
}

function numberList(value: unknown, limit = 20): number[] {
  return asArray(value)
    .map(asNumber)
    .filter((item): item is number => item !== null)
    .slice(0, limit);
}

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

export function getRoleContinuityDiagnostics(
  summaryOutput?: Record<string, unknown> | null
): RoleContinuityDiagnostics | null {
  const raw = asRecord(summaryOutput?.role_continuity_diagnostics);
  if (Object.keys(raw).length === 0) {
    return null;
  }

  const contractReadiness = asRecord(raw.contract_readiness);
  const displaySummary = asRecord(raw.display_summary);
  const characters = asArray(displaySummary.characters)
    .map((character, index): RoleContinuityDisplayCharacter => {
      const record = asRecord(character);
      return {
        displayName: asString(record.display_name, `角色 ${index + 1}`),
        stableAnchorCount: asNumber(record.stable_anchor_count),
        allowedVariantCount: asNumber(record.allowed_variant_count),
        referenceAssetCount: asNumber(record.reference_asset_count),
      };
    })
    .slice(0, 8);

  return {
    version: asString(raw.version, 'v1'),
    status: asString(raw.status, 'unknown'),
    reviewStatus: asString(raw.review_status, 'unknown'),
    roleContinuityScore: asNumber(raw.role_continuity_score),
    visualEvidenceVerified: asBoolean(raw.visual_evidence_verified),
    scoreCap: asNumber(raw.score_cap),
    fallbackReason: asString(raw.fallback_reason),
    unverifiedReason: asString(raw.unverified_reason),
    requiresHumanReview: asBoolean(raw.requires_human_review),
    approvalStatus: asString(raw.approval_status),
    contractReadiness: {
      status: asString(contractReadiness.status, 'unknown'),
      score: asNumber(contractReadiness.score),
      sameCarrierVerified: asBoolean(contractReadiness.same_carrier_verified),
    },
    identityDriftFindings: asArray(raw.identity_drift_findings)
      .map((finding) => asRecord(finding))
      .filter((finding) => Object.keys(finding).length > 0)
      .slice(0, 10),
    displaySummary: {
      characters,
      characterCount: asNumber(displaySummary.character_count) ?? characters.length,
      sceneLockCount: asNumber(displaySummary.scene_lock_count) ?? 0,
      lockedSceneNumbers: numberList(displaySummary.locked_scene_numbers),
      missingLockScenes: numberList(displaySummary.missing_lock_scenes),
      emptyCastScenes: numberList(displaySummary.empty_cast_scenes),
    },
  };
}
