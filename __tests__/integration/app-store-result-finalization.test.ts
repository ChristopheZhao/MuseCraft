import { useAppStore } from '@/store/useAppStore';

describe('app store result finalization', () => {
  beforeEach(() => {
    useAppStore.getState().reset();
  });

  afterEach(() => {
    useAppStore.getState().reset();
  });

  it('clears stale final video state when switching to a different task', () => {
    useAppStore.getState().setCurrentRequest({
      id: 'task-1',
      sessionId: 'session-1',
      title: 'First task',
      description: 'first',
      style: {
        id: 'default',
        name: 'Default',
        description: 'Default style',
        thumbnail: '',
        category: 'corporate',
      },
      duration: 30,
      resolution: '720p',
      aspectRatio: '16:9',
      musicSettings: {
        enabled: true,
        genre: 'ambient',
        mood: 'calm',
        volume: 0.5,
      },
      createdAt: new Date('2026-04-07T08:00:00Z'),
      updatedAt: new Date('2026-04-07T08:00:00Z'),
    });
    useAppStore.getState().setQuickRuntime({
      session_id: 1,
      task_db_id: 10,
      mode: 'quick',
      status: 'completed',
      current_node_key: 'quality',
      current_attempt_id: 99,
      active_gate: null,
      error_message: null,
      summary_output: {
        final_video_url: '/files/outputs/videos/final_story_1.mp4',
      },
      resume_control: null,
      nodes: [],
      created_at: '2026-04-07T08:00:00Z',
      updated_at: '2026-04-07T08:10:00Z',
    });
    useAppStore.getState().setFinalVideoUrl(
      'http://127.0.0.1:8005/files/outputs/videos/final_story_1.mp4'
    );
    useAppStore.getState().setModal({
      type: 'result-ready',
      data: {},
      onClose: jest.fn(),
    });

    useAppStore.getState().setCurrentRequest({
      id: 'task-2',
      sessionId: 'session-1',
      title: 'Second task',
      description: 'second',
      style: {
        id: 'default',
        name: 'Default',
        description: 'Default style',
        thumbnail: '',
        category: 'corporate',
      },
      duration: 45,
      resolution: '1080p',
      aspectRatio: '16:9',
      musicSettings: {
        enabled: true,
        genre: 'ambient',
        mood: 'calm',
        volume: 0.5,
      },
      createdAt: new Date('2026-04-07T08:20:00Z'),
      updatedAt: new Date('2026-04-07T08:20:00Z'),
    });

    const state = useAppStore.getState();
    expect(state.currentRequest?.id).toBe('task-2');
    expect(state.finalVideoUrl).toBeUndefined();
    expect(state.quickRuntime).toBeNull();
    expect(state.ui.modal).toBeNull();
  });
});
