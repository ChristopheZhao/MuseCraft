import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

import {
  ApiClient,
} from '@/lib/api';
import type {
  CreateProjectRequest,
  ProjectStateResponse,
  UpdateEpisodeScriptRequest,
  OrchestrateProjectRequest,
  OrchestrateProjectResponse,
} from '@/types/project';

interface ProjectStoreState {
  project: ProjectStateResponse | null;
  loading: boolean;
  episodeAction: string | null;
  pollingTimer: number | null;
  pollingProjectId: string | null;
  pollingEpisodeIds: string[];
  createProject: (payload: CreateProjectRequest) => Promise<ProjectStateResponse>;
  refreshProject: (projectId: string) => Promise<ProjectStateResponse>;
  updateEpisodeScript: (
    projectId: string,
    episodeId: string,
    payload: UpdateEpisodeScriptRequest,
  ) => Promise<ProjectStateResponse>;
  orchestrateProject: (
    projectId: string,
    payload: OrchestrateProjectRequest,
  ) => Promise<OrchestrateProjectResponse>;
  setProject: (project: ProjectStateResponse | null) => void;
  setLoading: (loading: boolean) => void;
  setEpisodeAction: (episodeId: string | null) => void;
  startPollingProject: (projectId: string, episodeIds?: string[]) => void;
  stopPollingProject: () => void;
}

export const useProjectStore = create<ProjectStoreState>()(
  devtools((set, get) => ({
    project: null,
    loading: false,
    episodeAction: null,

    setProject: (project) => set({ project }, false, 'projects/setProject'),
    setLoading: (loading) => set({ loading }, false, 'projects/setLoading'),
    setEpisodeAction: (episodeId) => set({ episodeAction: episodeId }, false, 'projects/setEpisodeAction'),
    pollingTimer: null,
    pollingProjectId: null,
    pollingEpisodeIds: [],

    async createProject(payload) {
      get().stopPollingProject();
      set({ loading: true }, false, 'projects/create/start');
      try {
        const project = await ApiClient.createProject(payload);
        set({ project }, false, 'projects/create/success');
        return project;
      } catch (error) {
        set({ loading: false }, false, 'projects/create/error');
        throw error;
      } finally {
        set({ loading: false }, false, 'projects/create/finish');
      }
    },

    async refreshProject(projectId) {
      set({ loading: true }, false, 'projects/refresh/start');
      try {
        const project = await ApiClient.getProject(projectId);
        set({ project }, false, 'projects/refresh/success');
        return project;
      } catch (error) {
        set({ loading: false }, false, 'projects/refresh/error');
        throw error;
      } finally {
        set({ loading: false }, false, 'projects/refresh/finish');
      }
    },

    async updateEpisodeScript(projectId, episodeId, payload) {
      set({ episodeAction: episodeId }, false, 'projects/episode/update/start');
      try {
        const project = await ApiClient.updateEpisodeScript(projectId, episodeId, payload);
        set({ project }, false, 'projects/episode/update/success');
        return project;
      } catch (error) {
        set({ episodeAction: null }, false, 'projects/episode/update/error');
        throw error;
      } finally {
        set({ episodeAction: null }, false, 'projects/episode/update/finish');
      }
    },

    async orchestrateProject(projectId, payload) {
      set({ episodeAction: 'orchestrate' }, false, 'projects/orchestrate/start');
      try {
        const response = await ApiClient.orchestrateProject(projectId, payload);
        set({ project: response.project }, false, 'projects/orchestrate/success');

        const targetIds = (() => {
          if (payload.episode_ids && payload.episode_ids.length > 0) {
            return payload.episode_ids;
          }
          if (payload.episode_indices && payload.episode_indices.length > 0) {
            const lookup = new Map(
              response.project.story_plan.episodes.map((ep) => [ep.sequence_index, ep.episode_id]),
            );
            return payload.episode_indices
              .map((index) => lookup.get(index))
              .filter((id): id is string => Boolean(id));
          }
          return response.project.story_plan.episodes.map((ep) => ep.episode_id);
        })();

        get().startPollingProject(projectId, targetIds);

        return response;
      } catch (error) {
        set({ episodeAction: null }, false, 'projects/orchestrate/error');
        throw error;
      } finally {
        set({ episodeAction: null }, false, 'projects/orchestrate/finish');
      }
    },

    startPollingProject(projectId, episodeIds = []) {
      const { pollingTimer, stopPollingProject } = get();
      if (pollingTimer) {
        stopPollingProject();
      }

      const targets = episodeIds.length > 0 ? Array.from(new Set(episodeIds)) : undefined;

      const poll = async () => {
        try {
          const project = await ApiClient.getProject(projectId);
          set({ project, loading: false }, false, 'projects/poll/update');

          const runtime = project.episodes_runtime || {};
          const idsToCheck = targets ?? Object.keys(runtime);
          const stillGenerating = idsToCheck.some((id) => {
            const status = runtime[id]?.status;
            return status === 'generating';
          });

          if (!stillGenerating) {
            stopPollingProject();
          }
        } catch (error) {
          console.warn('Project polling failed', error);
        }
      };

      if (typeof window !== 'undefined') {
        poll();
        const intervalMs = Number(process.env.NEXT_PUBLIC_PROJECT_POLLING_INTERVAL_MS) || 15000;
        const timer = window.setInterval(poll, intervalMs);
        set(
          {
            pollingTimer: timer,
            pollingProjectId: projectId,
            pollingEpisodeIds: targets ?? [],
          },
          false,
          'projects/poll/start',
        );
      }
    },

    stopPollingProject() {
      const timer = get().pollingTimer;
      if (timer) {
        if (typeof window !== 'undefined') {
          window.clearInterval(timer);
        } else {
          clearInterval(timer);
        }
      }
      set(
        {
          pollingTimer: null,
          pollingProjectId: null,
          pollingEpisodeIds: [],
        },
        false,
        'projects/poll/stop',
      );
    },
  }))
);
