import { create } from 'zustand';
import { devtools, subscribeWithSelector } from 'zustand/middleware';
import { 
  VideoRequest, 
  Agent, 
  GenerationResult, 
  UIState, 
  Notification,
  ModalState,
  GenerationStep,
  TaskRuntimeView,
} from '@/types';

interface AppState {
  mode: 'quick' | 'project';
  quickProcessingContext: 'fresh_submit' | 'attached_runtime' | null;
  // 当前视频请求
  currentRequest: VideoRequest | null;
  // 最终合成视频地址（可选，本地路径或URL）
  finalVideoUrl?: string;
  
  // 智能体状态
  agents: Agent[];
  
  // 生成结果
  results: GenerationResult[];
  quickRuntime: TaskRuntimeView | null;
  
  // UI状态
  ui: UIState;
  
  // WebSocket连接状态
  wsConnected: boolean;
  
  // Actions
  setCurrentRequest: (request: VideoRequest | null) => void;
  setMode: (mode: 'quick' | 'project') => void;
  setQuickProcessingContext: (context: 'fresh_submit' | 'attached_runtime' | null) => void;
  updateAgent: (agentId: string, updates: Partial<Agent>) => void;
  addResult: (result: GenerationResult) => void;
  updateResult: (resultId: string, updates: Partial<GenerationResult>) => void;
  setCurrentStep: (step: GenerationStep) => void;
  setQuickRuntime: (runtime: TaskRuntimeView | null) => void;
  addNotification: (notification: Omit<Notification, 'id' | 'timestamp'>) => void;
  removeNotification: (id: string) => void;
  setModal: (modal: ModalState | null) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setLoading: (loading: boolean) => void;
  setWSConnected: (connected: boolean) => void;
  setFinalVideoUrl: (url?: string) => void;
  
  // 重置状态
  reset: () => void;
}

const createInitialUIState = (): UIState => ({
  isLoading: false,
  currentStep: 'input',
  sidebarCollapsed: false,
  notifications: [],
  modal: null,
});

const createInitialAgents = (): Agent[] => [
  {
    id: 'concept-generator',
    name: '概念生成',
    type: 'concept-generator',
    status: 'idle',
    progress: 0,
    description: '分析需求并生成创意概念',
    capabilities: ['concept-generation', 'idea-brainstorming', 'creative-analysis'],
  },
  {
    id: 'script-writer',
    name: '剧本撰写',
    type: 'script-writer',
    status: 'idle',
    progress: 0,
    description: '撰写生动的脚本与叙事',
    capabilities: ['script-writing', 'storytelling', 'dialogue-creation'],
  },
  {
    id: 'image-generator',
    name: '视觉创作',
    type: 'image-generator',
    status: 'idle',
    progress: 0,
    description: '生成图片与视觉元素',
    capabilities: ['image-generation', 'visual-design', 'illustration'],
  },
  {
    id: 'video-generator',
    name: '视频生成',
    type: 'video-generator',
    status: 'idle',
    progress: 0,
    description: '根据场景与描述生成视频片段',
    capabilities: ['video-generation', 'motion-design'],
  },
  {
    id: 'voice-synthesizer',
    name: '配音合成',
    type: 'voice-synthesizer',
    status: 'idle',
    progress: 0,
    description: '生成自然流畅的语音旁白',
    capabilities: ['voice-synthesis', 'audio-processing', 'speech-generation'],
  },
  {
    id: 'video-composer',
    name: '视频合成',
    type: 'video-composer',
    status: 'idle',
    progress: 0,
    description: '将各组件合成为完整视频',
    capabilities: ['video-editing', 'composition', 'post-production'],
  },
  {
    id: 'quality-controller',
    name: '质量检测',
    type: 'quality-controller',
    status: 'idle',
    progress: 0,
    description: '审查并保障输出质量',
    capabilities: ['quality-assurance', 'content-review', 'optimization'],
  },
];

export const useAppStore = create<AppState>()(
  devtools(
    subscribeWithSelector((set, get) => ({
      // Initial state
      currentRequest: null,
      finalVideoUrl: undefined,
      mode: 'quick',
      quickProcessingContext: null,
      agents: createInitialAgents(),
      results: [],
      quickRuntime: null,
      ui: createInitialUIState(),
      wsConnected: false,

      // Actions
      setMode: (mode) =>
        set({ mode }, false, 'setMode'),

      setQuickProcessingContext: (context) =>
        set({ quickProcessingContext: context }, false, 'setQuickProcessingContext'),

      setCurrentRequest: (request) =>
        set((state) => {
          const previousTaskId = state.currentRequest?.id ?? null;
          const nextTaskId = request?.id ?? null;
          const taskChanged = previousTaskId !== nextTaskId;

          if (!taskChanged) {
            return { currentRequest: request };
          }

          return {
            currentRequest: request,
            finalVideoUrl: undefined,
            quickRuntime: null,
            ui: {
              ...state.ui,
              modal: null,
            },
          };
        }, false, 'setCurrentRequest'),

      setFinalVideoUrl: (url) =>
        set({ finalVideoUrl: url }, false, 'setFinalVideoUrl'),

      updateAgent: (agentId, updates) =>
        set((state) => ({
          agents: state.agents.map((agent) =>
            agent.id === agentId ? { ...agent, ...updates } : agent
          ),
        }), false, 'updateAgent'),

      addResult: (result) =>
        set((state) => ({
          results: [...state.results, result],
        }), false, 'addResult'),

      updateResult: (resultId, updates) =>
        set((state) => ({
          results: state.results.map((result) =>
            result.id === resultId ? { ...result, ...updates } : result
          ),
        }), false, 'updateResult'),

      setCurrentStep: (step) =>
        set((state) => ({
          ui: { ...state.ui, currentStep: step },
        }), false, 'setCurrentStep'),

      setQuickRuntime: (runtime) =>
        set({ quickRuntime: runtime }, false, 'setQuickRuntime'),

      addNotification: (notification) => {
        const newNotification: Notification = {
          ...notification,
          id: `notification-${Date.now()}-${Math.random()}`,
          timestamp: new Date(),
        };
        
        set((state) => ({
          ui: {
            ...state.ui,
            notifications: [...state.ui.notifications, newNotification],
          },
        }), false, 'addNotification');

        // Auto-remove notification after specified time
        if (notification.autoClose) {
          setTimeout(() => {
            get().removeNotification(newNotification.id);
          }, notification.autoClose);
        }
      },

      removeNotification: (id) =>
        set((state) => ({
          ui: {
            ...state.ui,
            notifications: state.ui.notifications.filter((n) => n.id !== id),
          },
        }), false, 'removeNotification'),

      setModal: (modal) =>
        set((state) => ({
          ui: { ...state.ui, modal },
        }), false, 'setModal'),

      setSidebarCollapsed: (collapsed) =>
        set((state) => ({
          ui: { ...state.ui, sidebarCollapsed: collapsed },
        }), false, 'setSidebarCollapsed'),

      setLoading: (loading) =>
        set((state) => ({
          ui: { ...state.ui, isLoading: loading },
        }), false, 'setLoading'),

      setWSConnected: (connected) =>
        set({ wsConnected: connected }, false, 'setWSConnected'),

      reset: () =>
        set({
          currentRequest: null,
          finalVideoUrl: undefined,
          quickProcessingContext: null,
          agents: createInitialAgents(),
          results: [],
          quickRuntime: null,
          ui: createInitialUIState(),
          wsConnected: false,
        }, false, 'reset'),
    })),
    {
      name: 'app-store',
    }
  )
);
