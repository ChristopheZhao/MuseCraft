// 基础类型定义
export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
}

// 视频生成相关类型
export interface VideoRequest {
  id: string;
  sessionId?: string;
  title: string;
  description: string;
  style: VideoStyle;
  duration: number;
  resolution: string;
  aspectRatio: AspectRatio;
  musicSettings: MusicSettings;
  createdAt: Date;
  updatedAt: Date;
}

export interface VideoStyle {
  id: string;
  name: string;
  description: string;
  thumbnail: string;
  category: StyleCategory;
}

export type StyleCategory = 
  | 'corporate' 
  | 'creative' 
  | 'educational' 
  | 'entertainment' 
  | 'marketing' 
  | 'social';

export type AspectRatio = '16:9' | '9:16' | '1:1' | '4:3';

export interface MusicSettings {
  enabled: boolean;
  genre: string;
  mood: string;
  volume: number;
}

// 智能体相关类型
export interface Agent {
  id: string;
  name: string;
  type: AgentType;
  status: AgentStatus;
  progress: number;
  description: string;
  capabilities: string[];
  currentTask?: string;
  estimatedTime?: number;
}

export type AgentType = 
  | 'concept-generator'
  | 'script-writer'
  | 'image-generator'
  | 'video-generator'
  | 'voice-synthesizer'
  | 'video-composer'
  | 'quality-controller';

export type AgentStatus = 
  | 'idle'
  | 'thinking'
  | 'working'
  | 'completed'
  | 'error'
  | 'waiting';

// 生成结果类型
export interface GenerationResult {
  id: string;
  requestId: string;
  type: ResultType;
  status: GenerationStatus;
  data: any;
  createdAt: Date;
  agent: string;
  confidence: number;
}

export type ResultType = 
  | 'concept'
  | 'script'
  | 'storyboard'
  | 'image'
  | 'voice'
  | 'video'
  | 'thumbnail';

export type GenerationStatus = 
  | 'pending'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'rejected';

// 实时通信类型
export interface WebSocketMessage {
  type: MessageType;
  data: any;
  timestamp: Date;
  requestId?: string;
}

export type MessageType = 
  | 'agent-status-update'
  | 'progress-update'
  | 'result-ready'
  | 'error'
  | 'system-message'
  // Backend Event Bus types
  | 'event.state'
  | 'event.progress'
  // Legacy/Direct types (for backward compatibility)
  | 'agent_progress'
  | 'workflow_completed'
  | 'workflow_failed'
  | 'enhanced_workflow_completed'
  | 'enhanced_workflow_failed'
  | 'task_notification'
  | 'system_notification'
  | 'connection_established'
  | 'subscription_confirmed'
  | 'concept_plan_ready'
  | 'image_assets_ready'
  | 'video_assets_ready';

// UI状态类型
export interface UIState {
  isLoading: boolean;
  currentStep: GenerationStep;
  sidebarCollapsed: boolean;
  notifications: Notification[];
  modal: ModalState | null;
}

export type GenerationStep = 
  | 'input'
  | 'processing'
  | 'review'
  | 'export';

export interface Notification {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message: string;
  timestamp: Date;
  autoClose?: number;
}

export interface ModalState {
  type: string;
  data?: any;
  onClose: () => void;
}

// 文件上传类型
export interface FileUpload {
  id: string;
  file: File;
  progress: number;
  status: 'pending' | 'uploading' | 'completed' | 'failed';
  url?: string;
  type: 'image' | 'video' | 'audio' | 'document';
}

// API响应类型
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export interface RuntimeGateDecision {
  id: number;
  gate_id: number;
  action: 'approve' | 'revise' | 'replan' | string;
  actor_type: string;
  actor_id?: string | null;
  feedback_text?: string | null;
  structured_constraints: Record<string, any>;
  invalidation_scope: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface RuntimeGate {
  id: number;
  node_id: number;
  attempt_id?: number | null;
  gate_name: string;
  gate_type: string;
  status: string;
  contract_version?: string;
  artifact_refs: Array<Record<string, any>>;
  facts: Record<string, any>;
  result_code?: string | null;
  reason_code?: string | null;
  allowed_actions: string[];
  recommended_action?: string | null;
  latest_decision?: RuntimeGateDecision | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface RuntimeNodeState {
  id: number;
  node_key: string;
  node_type: string;
  order_index: number;
  scope_type: string;
  scope_ref?: string | null;
  status: string;
  revision_index: number;
  gate_required: boolean;
  last_gate_id?: number | null;
  artifact_refs: Array<Record<string, any>>;
  diagnostics: Array<Record<string, any>>;
}

export interface TaskRuntimeView {
  session_id: number;
  task_db_id: number;
  mode: string;
  project_id?: string | null;
  episode_id?: string | null;
  shared_memory_id?: string | null;
  status: string;
  current_node_key?: string | null;
  current_attempt_id?: number | null;
  active_gate?: RuntimeGate | null;
  error_message?: string | null;
  summary_output: Record<string, any>;
  nodes: RuntimeNodeState[];
  created_at?: string | null;
  updated_at?: string | null;
}

// 应用配置类型
export interface AppConfig {
  apiUrl: string;
  wsUrl: string;
  maxFileSize: number;
  supportedFormats: {
    image: string[];
    video: string[];
    audio: string[];
  };
  features: {
    realTimeUpdates: boolean;
    multipleAgents: boolean;
    voiceSynthesis: boolean;
    backgroundMusic: boolean;
  };
}
