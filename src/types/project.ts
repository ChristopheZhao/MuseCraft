export type EpisodeStatus =
  | 'draft'
  | 'pending_approval'
  | 'approved'
  | 'generating'
  | 'completed'
  | 'failed'
  | 'needs_revision';

export interface EpisodePlan {
  episode_id: string;
  sequence_index: number;
  title: string;
  target_duration_seconds: number;
  summary: string;
  narrative_purpose: string;
  continuity_notes: Record<string, any>;
  required_assets: Record<string, any>;
  script_draft: string;
  status: EpisodeStatus;
}

export interface EpisodeRuntimeState {
  episode_id: string;
  status: EpisodeStatus;
  approved_script: string;
  workflow_task_id?: string | null;
  aggregated_cost: number;
  aggregated_tokens: number;
  output_assets: Record<string, any>;
  error?: string | null;
  video_url?: string;
}

export interface StoryPlan {
  project_id: string;
  user_prompt: string;
  target_duration_seconds: number;
  aspect_ratio: string;
  episodes: EpisodePlan[];
  global_theme: string;
  character_bible: Record<string, any>;
  visual_style: Record<string, any>;
  tone_and_mood: string;
  additional_notes: Record<string, any>;
}

export interface ProjectStateResponse {
  project_id: string;
  mode: string;
  story_plan: StoryPlan;
  episodes_runtime: Record<string, EpisodeRuntimeState>;
  global_settings: Record<string, any>;
  cost_budget?: number | null;
  total_cost: number;
  total_tokens: number;
  completed_episodes: number;
}

export interface CreateProjectRequest {
  user_prompt: string;
  target_duration_seconds: number;
  mode?: string;
  aspect_ratio?: string;
  resolution?: string | null;
  style_preference?: string | null;
  episode_cap_seconds?: number;
  episode_min_seconds?: number;
  global_theme?: string | null;
  character_bible?: Record<string, any>;
  visual_style?: Record<string, any>;
  tone_and_mood?: string | null;
  additional_notes?: Record<string, any>;
}

export interface UpdateEpisodeScriptRequest {
  script_text: string;
  approve?: boolean;
  additional_notes?: Record<string, string>;
}

export interface OrchestrateProjectRequest {
  episode_ids?: string[];
  episode_indices?: number[];
  auto_approve?: boolean;
  force_rerun?: boolean;
  runtime_overrides?: Record<string, any>;
}

export interface OrchestrateProjectResponse {
  task_id: string;
  status: string;
  result: any;
  project: ProjectStateResponse;
}

export interface ProjectEpisodeView extends EpisodePlan {
  runtime?: EpisodeRuntimeState;
}
