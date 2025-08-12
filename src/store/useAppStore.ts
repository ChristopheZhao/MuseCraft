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
    name: 'Concept Generator',
    type: 'concept-generator',
    status: 'idle',
    progress: 0,
    description: 'Analyzes requirements and generates creative concepts',
    capabilities: ['concept-generation', 'idea-brainstorming', 'creative-analysis'],
  },
  {
    id: 'script-writer',
    name: 'Script Writer',
    type: 'script-writer',
    status: 'idle',
    progress: 0,
    description: 'Creates engaging scripts and narratives',
    capabilities: ['script-writing', 'storytelling', 'dialogue-creation'],
  },
  {
    id: 'image-generator',
    name: 'Visual Creator',
    type: 'image-generator',
    status: 'idle',
    progress: 0,
    description: 'Generates images and visual elements',
    capabilities: ['image-generation', 'visual-design', 'illustration'],
  },
  {
    id: 'voice-synthesizer',
    name: 'Voice Synthesizer',
    type: 'voice-synthesizer',
    status: 'idle',
    progress: 0,
    description: 'Creates natural-sounding voice narration',
    capabilities: ['voice-synthesis', 'audio-processing', 'speech-generation'],
  },
  {
    id: 'video-composer',
    name: 'Video Composer',
    type: 'video-composer',
    status: 'idle',
    progress: 0,
    description: 'Assembles final video from all components',
    capabilities: ['video-editing', 'composition', 'post-production'],
  },
  {
    id: 'quality-controller',
    name: 'Quality Controller',
    type: 'quality-controller',
    status: 'idle',
    progress: 0,
    description: 'Reviews and ensures output quality',
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