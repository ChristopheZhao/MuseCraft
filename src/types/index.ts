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
  title: string;
  description: string;
  style: VideoStyle;
  duration: number;
  resolution: string;
  aspectRatio: AspectRatio;
  voiceSettings: VoiceSettings;
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

export interface VoiceSettings {
  enabled: boolean;
  voice: string;
  speed: number;
  pitch: number;
  language: string;
}

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
  | 'system-message';

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