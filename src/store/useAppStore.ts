import { create } from 'zustand';
import { devtools, subscribeWithSelector } from 'zustand/middleware';
import { 
  VideoRequest, 
  Agent, 
  GenerationResult, 
  UIState, 
  Notification,
  ModalState,
  GenerationStep 
} from '@/types';

interface AppState {
  // 当前视频请求
  currentRequest: VideoRequest | null;
  
  // 智能体状态
  agents: Agent[];
  
  // 生成结果
  results: GenerationResult[];
  
  // UI状态
  ui: UIState;
  
  // WebSocket连接状态
  wsConnected: boolean;
  
  // Actions
  setCurrentRequest: (request: VideoRequest | null) => void;
  updateAgent: (agentId: string, updates: Partial<Agent>) => void;
  addResult: (result: GenerationResult) => void;
  updateResult: (resultId: string, updates: Partial<GenerationResult>) => void;
  setCurrentStep: (step: GenerationStep) => void;
  addNotification: (notification: Omit<Notification, 'id' | 'timestamp'>) => void;
  removeNotification: (id: string) => void;
  setModal: (modal: ModalState | null) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setLoading: (loading: boolean) => void;
  setWSConnected: (connected: boolean) => void;
  
  // 重置状态
  reset: () => void;
}

const initialUIState: UIState = {
  isLoading: false,
  currentStep: 'input',
  sidebarCollapsed: false,
  notifications: [],
  modal: null,
};

const initialAgents: Agent[] = [
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
      agents: initialAgents,
      results: [],
      ui: initialUIState,
      wsConnected: false,

      // Actions
      setCurrentRequest: (request) => 
        set({ currentRequest: request }, false, 'setCurrentRequest'),

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
          agents: initialAgents,
          results: [],
          ui: initialUIState,
          wsConnected: false,
        }, false, 'reset'),
    })),
    {
      name: 'app-store',
    }
  )
);
