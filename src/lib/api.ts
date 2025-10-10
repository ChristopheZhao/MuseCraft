// API client for backend communication

import type {
  CreateProjectRequest,
  ProjectStateResponse,
  UpdateEpisodeScriptRequest,
  OrchestrateProjectRequest,
  OrchestrateProjectResponse,
} from '@/types/project';

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

  static async getTaskStatus(taskId: string): Promise<TaskResponse> {
    const response = await fetch(`${API_BASE_URL}/tasks/${taskId}`);
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to get task status');
    }

    return response.json();
  }

  static async getTaskResult(taskId: string): Promise<any> {
    const response = await fetch(`${API_BASE_URL}/tasks/${taskId}/result`);
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to get task result');
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
