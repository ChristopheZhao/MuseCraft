// API client for backend communication

import type {
  CreateProjectRequest,
  ProjectStateResponse,
  UpdateEpisodeScriptRequest,
  OrchestrateProjectRequest,
  OrchestrateProjectResponse,
} from '@/types/project';
import type { TaskRuntimeView } from '@/types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

export interface CreateTaskRequest {
  user_prompt: string;
  video_style?: string;
  duration: number;
  resolution?: string;
  aspect_ratio: string;
  session_id?: string;
  voice_settings?: {
    voice_id?: string;
    language?: string;
    speed?: number;
    pitch?: number;
    sample_rate?: number;
    audio_format?: string;
    style?: string;
  };
}

export interface TaskResponse {
  id: number;
  task_id: string;
  title: string;
  status: string;
  progress_percentage: number;
  current_step?: string;
  created_at: string;
  updated_at: string;
  estimated_duration?: number;
  error_message?: string;
}

export interface TaskDetailResponse extends TaskResponse {
  description?: string;
  input_parameters: Record<string, any>;
  output_metadata: Record<string, any>;
  scenes_count: number;
  resources_count: number;
  agent_executions_count: number;
}

export interface TaskRuntimeDecisionRequest {
  action: 'approve' | 'revise' | 'replan';
  feedback_text?: string;
  structured_constraints?: Record<string, any>;
  actor_id?: string;
}

export interface QuickCurrentRunTask {
  id: number;
  task_id: string;
  title: string;
  description?: string;
  status: string;
  session_id?: string;
  input_parameters: Record<string, any>;
  created_at: string;
  updated_at: string;
  error_message?: string;
}

export interface QuickCurrentRunResponse {
  task: QuickCurrentRunTask;
  runtime: TaskRuntimeView;
}

export interface TaskRuntimeActionResponse {
  message: string;
  task_id: string;
  runtime: TaskRuntimeView;
}

export class TaskRuntimeEndpointError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail?: string) {
    super(detail || 'Failed to get task runtime');
    this.name = 'TaskRuntimeEndpointError';
    this.status = status;
    this.detail = detail || 'Failed to get task runtime';
  }
}

export class ApiClient {
  static async createTask(request: CreateTaskRequest): Promise<TaskResponse> {
    console.log('🚀 ApiClient.createTask called');
    console.log('📝 Request payload:', request);
    console.log('🌐 API_BASE_URL:', API_BASE_URL);
    console.log('🎯 Full URL:', `${API_BASE_URL}/tasks/`);
    
    const response = await fetch(`${API_BASE_URL}/tasks/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
      // 绕过代理设置
      mode: 'cors',
    });

    console.log('Response status:', response.status);

    if (!response.ok) {
      const errorText = await response.text();
      let error;
      try {
        error = JSON.parse(errorText);
      } catch {
        error = { detail: errorText };
      }
      console.error('API Error:', error);
      console.error('Full error response:', {
        status: response.status,
        statusText: response.statusText,
        error: error
      });
      throw new Error(error.detail || JSON.stringify(error) || 'Failed to create task');
    }

    const data = await response.json();
    console.log('Task created:', data);
    return data;
  }

  static async getTaskDetail(taskId: string): Promise<TaskDetailResponse> {
    const response = await fetch(`${API_BASE_URL}/tasks/${taskId}`, {
      cache: 'no-store',
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to get task status');
    }

    return response.json();
  }

  static async getTaskResult(taskId: string): Promise<any> {
    const response = await fetch(`${API_BASE_URL}/tasks/${taskId}/result`, {
      cache: 'no-store',
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to get task result');
    }

    return response.json();
  }

  static async getTaskRuntime(taskId: string): Promise<TaskRuntimeView> {
    const response = await fetch(`${API_BASE_URL}/tasks/${taskId}/runtime`, {
      cache: 'no-store',
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new TaskRuntimeEndpointError(
        response.status,
        error.detail || 'Failed to get task runtime'
      );
    }

    return response.json();
  }

  static async getCurrentQuickRun(sessionId: string): Promise<QuickCurrentRunResponse | null> {
    const response = await fetch(
      `${API_BASE_URL}/tasks/quick/current?session_id=${encodeURIComponent(sessionId)}`,
      {
        cache: 'no-store',
      }
    );

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'Failed to discover current quick run');
    }

    return response.json();
  }

  static async submitScriptGateDecision(
    taskId: string,
    payload: TaskRuntimeDecisionRequest,
  ): Promise<TaskRuntimeActionResponse> {
    const response = await fetch(`${API_BASE_URL}/tasks/${taskId}/runtime/script/decision`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      mode: 'cors',
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'Failed to submit script gate decision');
    }

    return response.json();
  }

  static async resumeTaskRuntime(taskId: string): Promise<TaskRuntimeActionResponse> {
    const response = await fetch(`${API_BASE_URL}/tasks/${taskId}/runtime/resume`, {
      method: 'POST',
      mode: 'cors',
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'Failed to resume runtime execution');
    }

    return response.json();
  }

  static async createProject(request: CreateProjectRequest): Promise<ProjectStateResponse> {
    const response = await fetch(`${API_BASE_URL}/projects/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      mode: 'cors',
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || 'Failed to create project');
    }

    const data = await response.json();
    return data.project as ProjectStateResponse;
  }

  static async getProject(projectId: string): Promise<ProjectStateResponse> {
    const response = await fetch(`${API_BASE_URL}/projects/${projectId}`);

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || 'Failed to fetch project');
    }

    const data = await response.json();
    return data as ProjectStateResponse;
  }

  static async updateEpisodeScript(
    projectId: string,
    episodeId: string,
    payload: UpdateEpisodeScriptRequest,
  ): Promise<ProjectStateResponse> {
    const response = await fetch(
      `${API_BASE_URL}/projects/${projectId}/episodes/${episodeId}/script`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        mode: 'cors',
      },
    );

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || 'Failed to update episode script');
    }

    const data = await response.json();
    return data as ProjectStateResponse;
  }

  static async orchestrateProject(
    projectId: string,
    payload: OrchestrateProjectRequest,
  ): Promise<OrchestrateProjectResponse> {
    const response = await fetch(`${API_BASE_URL}/projects/${projectId}/orchestrate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      mode: 'cors',
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || 'Failed to orchestrate project');
    }

    const data = await response.json();
    return data as OrchestrateProjectResponse;
  }
}
