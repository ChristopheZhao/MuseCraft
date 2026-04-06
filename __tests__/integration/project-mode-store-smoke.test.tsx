import { act } from 'react';
import { waitFor } from '@testing-library/react';

import { ApiClient } from '@/lib/api';
import { useProjectStore } from '@/store/useProjectStore';
import type { OrchestrateProjectResponse, ProjectStateResponse } from '@/types/project';


jest.mock('@/lib/api', () => ({
  ApiClient: {
    createProject: jest.fn(),
    getProject: jest.fn(),
    updateEpisodeScript: jest.fn(),
    orchestrateProject: jest.fn(),
  },
}));

const mockCreateProject = ApiClient.createProject as jest.MockedFunction<typeof ApiClient.createProject>;
const mockGetProject = ApiClient.getProject as jest.MockedFunction<typeof ApiClient.getProject>;
const mockOrchestrateProject = ApiClient.orchestrateProject as jest.MockedFunction<typeof ApiClient.orchestrateProject>;


const buildProjectState = (
  overrides: Partial<ProjectStateResponse> = {},
): ProjectStateResponse => ({
  project_id: 'project-smoke-1',
  mode: 'project',
  story_plan: {
    project_id: 'project-smoke-1',
    user_prompt: 'Rabbit detective project',
    target_duration_seconds: 180,
    aspect_ratio: '16:9',
    episodes: [
      {
        episode_id: 'episode-1',
        sequence_index: 0,
        title: 'Episode 1',
        target_duration_seconds: 60,
        summary: 'Intro',
        narrative_purpose: 'Open the story',
        continuity_notes: {},
        required_assets: {},
        script_draft: 'draft-1',
        status: 'approved',
      },
    ],
    global_theme: 'friendship',
    character_bible: {},
    visual_style: {},
    tone_and_mood: '',
    additional_notes: {},
  },
  episodes_runtime: {},
  progress: {
    planning: {
      status: 'queued',
      task_id: 'task-plan-1',
      error: null,
    },
    character_references: {
      status: 'idle',
      task_id: null,
      error: null,
    },
  },
  global_settings: {},
  cost_budget: null,
  total_cost: 0,
  total_tokens: 0,
  completed_episodes: 0,
  style_profile: {},
  character_bible: {},
  ...overrides,
});


const resetProjectStore = () => {
  const current = useProjectStore.getState();
  current.stopPollingProject();
  useProjectStore.setState({
    project: null,
    loading: false,
    episodeAction: null,
    pollingTimer: null,
    pollingProjectId: null,
    pollingEpisodeIds: [],
  });
};


describe('project mode store smoke', () => {
  const originalPollingInterval = process.env.NEXT_PUBLIC_PROJECT_POLLING_INTERVAL_MS;

  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    process.env.NEXT_PUBLIC_PROJECT_POLLING_INTERVAL_MS = '25';
    resetProjectStore();
  });

  afterEach(() => {
    resetProjectStore();
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
    process.env.NEXT_PUBLIC_PROJECT_POLLING_INTERVAL_MS = originalPollingInterval;
  });

  it('consumes create -> planning poll -> workspace projection -> orchestrate through authority projections only', async () => {
    const placeholderProject = buildProjectState({
      progress: {
        planning: { status: 'queued', task_id: 'task-plan-1', error: null },
        character_references: { status: 'idle', task_id: null, error: null },
      },
    });
    const planningProject = buildProjectState({
      progress: {
        planning: { status: 'in_progress', task_id: 'task-plan-1', error: null },
        character_references: { status: 'in_progress', task_id: null, error: null },
      },
    });
    const plannedProject = buildProjectState({
      progress: {
        planning: { status: 'completed', task_id: 'task-plan-1', error: null },
        character_references: { status: 'completed', task_id: null, error: null },
      },
      character_bible: {
        rabbit_detective: {
          canonical_id: 'rabbit_detective',
          display_name: 'Rabbit Detective',
        },
      },
      style_profile: {
        style_name: 'storybook',
      },
    });
    const orchestratingProject = buildProjectState({
      progress: {
        planning: { status: 'completed', task_id: 'task-plan-1', error: null },
        character_references: { status: 'completed', task_id: null, error: null },
      },
      episodes_runtime: {
        'episode-1': {
          episode_id: 'episode-1',
          status: 'generating',
          approved_script: 'approved-draft-1',
          workflow_task_id: 'workflow-1',
          aggregated_cost: 0,
          aggregated_tokens: 0,
          output_assets: {},
          error: null,
        },
      },
      character_bible: {
        rabbit_detective: {
          canonical_id: 'rabbit_detective',
          display_name: 'Rabbit Detective',
        },
      },
      style_profile: {
        style_name: 'storybook',
      },
    });
    const orchestrateResponse: OrchestrateProjectResponse = {
      task_id: 'task-orchestrate-1',
      status: 'queued',
      result: {},
      project: orchestratingProject,
    };

    mockCreateProject.mockResolvedValue(placeholderProject);
    mockGetProject
      .mockResolvedValueOnce(planningProject)
      .mockResolvedValueOnce(plannedProject)
      .mockResolvedValueOnce(orchestratingProject);
    mockOrchestrateProject.mockResolvedValue(orchestrateResponse);

    await act(async () => {
      await useProjectStore.getState().createProject({
        user_prompt: 'Rabbit detective project',
        target_duration_seconds: 180,
        mode: 'project',
      });
    });

    expect(useProjectStore.getState().project?.progress.planning.status).toBe('queued');

    await act(async () => {
      useProjectStore.getState().startPollingProject(placeholderProject.project_id);
    });

    await waitFor(() => {
      expect(mockGetProject).toHaveBeenCalledTimes(1);
      expect(useProjectStore.getState().project?.progress.planning.status).toBe('in_progress');
      expect(useProjectStore.getState().pollingProjectId).toBe(placeholderProject.project_id);
    });

    await act(async () => {
      jest.advanceTimersByTime(25);
    });

    await waitFor(() => {
      const current = useProjectStore.getState();
      expect(mockGetProject).toHaveBeenCalledTimes(2);
      expect(current.project?.progress.planning.status).toBe('completed');
      expect(current.project?.character_bible?.rabbit_detective?.display_name).toBe('Rabbit Detective');
      expect(current.project?.style_profile?.style_name).toBe('storybook');
      expect(current.pollingTimer).toBeNull();
      expect(current.pollingProjectId).toBeNull();
    });

    await act(async () => {
      await useProjectStore.getState().orchestrateProject(placeholderProject.project_id, {
        episode_ids: ['episode-1'],
      });
    });

    await waitFor(() => {
      const current = useProjectStore.getState();
      expect(mockOrchestrateProject).toHaveBeenCalledWith(placeholderProject.project_id, {
        episode_ids: ['episode-1'],
      });
      expect(mockGetProject).toHaveBeenCalledTimes(3);
      expect(current.project?.episodes_runtime['episode-1']?.status).toBe('generating');
      expect(current.pollingProjectId).toBe(placeholderProject.project_id);
      expect(current.pollingEpisodeIds).toEqual(['episode-1']);
    });
  });
});
