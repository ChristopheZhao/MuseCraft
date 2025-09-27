/**
 * API Mock Configurations
 * 
 * Provides comprehensive API mocking for different test scenarios,
 * including success cases, error cases, and edge cases.
 */

// Base API response types
interface ApiResponse<T = any> {
  success: boolean
  data?: T
  error?: string
  message?: string
  timestamp?: string
}

interface PaginatedResponse<T = any> {
  items: T[]
  total: number
  page: number
  pageSize: number
  hasNext: boolean
  hasPrevious: boolean
}

// Task-related API responses
export const TaskApiMocks = {
  // Success responses
  createTaskSuccess: (): ApiResponse => ({
    success: true,
    data: {
      id: 1,
      task_id: 'task-12345',
      title: 'AI Video Generation',
      description: 'Create an engaging video about artificial intelligence',
      status: 'pending',
      progress_percentage: 0,
      input_parameters: {
        user_prompt: 'Create an engaging video about artificial intelligence',
        video_style: 'professional',
        duration: 60,
        aspect_ratio: '16:9',
        music_settings: {
          enabled: false,
          genre: 'corporate',
          mood: 'upbeat',
          volume: 0.3
        }
      },
      output_metadata: null,
      scenes_count: 0,
      resources_count: 0,
      agent_executions_count: 0,
      estimated_completion_time: new Date(Date.now() + 300000).toISOString(), // 5 minutes
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    },
    timestamp: new Date().toISOString()
  }),

  getTaskSuccess: (): ApiResponse => ({
    success: true,
    data: {
      id: 1,
      task_id: 'task-12345',
      title: 'AI Video Generation',
      description: 'Create an engaging video about artificial intelligence',
      status: 'completed',
      progress_percentage: 100,
      input_parameters: {
        user_prompt: 'Create an engaging video about artificial intelligence',
        video_style: 'professional',
        duration: 60,
        aspect_ratio: '16:9'
      },
      output_metadata: {
        video_url: 'https://cdn.example.com/videos/task-12345.mp4',
        thumbnail_url: 'https://cdn.example.com/thumbnails/task-12345.jpg',
        duration: 58.5,
        file_size: '45.2 MB',
        resolution: '1920x1080',
        fps: 30,
        quality_score: 0.92
      },
      scenes_count: 5,
      resources_count: 12,
      agent_executions_count: 6,
      estimated_completion_time: null,
      actual_completion_time: new Date().toISOString(),
      created_at: new Date(Date.now() - 300000).toISOString(), // 5 minutes ago
      updated_at: new Date().toISOString()
    },
    timestamp: new Date().toISOString()
  }),

  listTasksSuccess: (): ApiResponse<PaginatedResponse> => ({
    success: true,
    data: {
      items: [
        {
          id: 1,
          task_id: 'task-12345',
          title: 'AI Video Generation',
          status: 'completed',
          progress_percentage: 100,
          created_at: new Date(Date.now() - 300000).toISOString(),
          updated_at: new Date().toISOString()
        },
        {
          id: 2,
          task_id: 'task-12346',
          title: 'Marketing Video',
          status: 'processing',
          progress_percentage: 65,
          created_at: new Date(Date.now() - 600000).toISOString(),
          updated_at: new Date(Date.now() - 60000).toISOString()
        },
        {
          id: 3,
          task_id: 'task-12347',
          title: 'Tutorial Video',
          status: 'failed',
          progress_percentage: 25,
          created_at: new Date(Date.now() - 900000).toISOString(),
          updated_at: new Date(Date.now() - 300000).toISOString()
        }
      ],
      total: 3,
      page: 1,
      pageSize: 10,
      hasNext: false,
      hasPrevious: false
    },
    timestamp: new Date().toISOString()
  }),

  // Error responses
  createTaskValidationError: (): ApiResponse => ({
    success: false,
    error: 'VALIDATION_ERROR',
    message: 'Invalid input parameters',
    data: {
      errors: {
        user_prompt: ['Prompt is required and must be at least 10 characters'],
        duration: ['Duration must be between 10 and 300 seconds'],
        video_style: ['Invalid video style selected']
      }
    },
    timestamp: new Date().toISOString()
  }),

  createTaskServerError: (): ApiResponse => ({
    success: false,
    error: 'SERVER_ERROR',
    message: 'Internal server error occurred while creating task',
    timestamp: new Date().toISOString()
  }),

  createTaskRateLimitError: (): ApiResponse => ({
    success: false,
    error: 'RATE_LIMIT_EXCEEDED',
    message: 'Too many requests. Please try again later.',
    data: {
      retry_after: 60,
      remaining_requests: 0,
      reset_time: new Date(Date.now() + 60000).toISOString()
    },
    timestamp: new Date().toISOString()
  }),

  getTaskNotFound: (): ApiResponse => ({
    success: false,
    error: 'TASK_NOT_FOUND',
    message: 'Task with specified ID not found',
    timestamp: new Date().toISOString()
  }),

  getTaskProcessing: (): ApiResponse => ({
    success: true,
    data: {
      id: 1,
      task_id: 'task-12345',
      title: 'AI Video Generation',
      status: 'processing',
      progress_percentage: 45,
      current_stage: 'script_generation',
      current_agent: 'script-writer',
      agent_status: {
        'concept-generator': { status: 'completed', progress: 100 },
        'script-writer': { status: 'working', progress: 75 },
        'image-generator': { status: 'waiting', progress: 0 },
        'voice-synthesizer': { status: 'waiting', progress: 0 },
        'video-composer': { status: 'waiting', progress: 0 },
        'quality-controller': { status: 'waiting', progress: 0 }
      },
      estimated_time_remaining: 180, // 3 minutes
      created_at: new Date(Date.now() - 120000).toISOString(), // 2 minutes ago
      updated_at: new Date().toISOString()
    },
    timestamp: new Date().toISOString()
  })
}

// File upload API responses
export const FileApiMocks = {
  uploadSuccess: (): ApiResponse => ({
    success: true,
    data: {
      file_id: 'file-67890',
      filename: 'reference-image.jpg',
      original_filename: 'my-reference-image.jpg',
      content_type: 'image/jpeg',
      file_size: 2048576, // 2MB
      url: 'https://cdn.example.com/uploads/file-67890.jpg',
      thumbnail_url: 'https://cdn.example.com/thumbnails/file-67890.jpg',
      metadata: {
        width: 1920,
        height: 1080,
        color_profile: 'sRGB',
        has_transparency: false
      },
      upload_time: new Date().toISOString(),
      expires_at: new Date(Date.now() + 86400000).toISOString() // 24 hours
    },
    timestamp: new Date().toISOString()
  }),

  uploadProgress: (progress: number): ApiResponse => ({
    success: true,
    data: {
      file_id: 'file-67890',
      progress: progress,
      status: progress < 100 ? 'uploading' : 'completed',
      bytes_uploaded: Math.floor((progress / 100) * 2048576),
      total_bytes: 2048576,
      estimated_time_remaining: Math.max(0, Math.floor((100 - progress) * 0.5)) // seconds
    },
    timestamp: new Date().toISOString()
  }),

  uploadError: (): ApiResponse => ({
    success: false,
    error: 'UPLOAD_ERROR',
    message: 'File upload failed',
    data: {
      error_code: 'FILE_TOO_LARGE',
      max_file_size: 50 * 1024 * 1024, // 50MB
      uploaded_size: 75 * 1024 * 1024 // 75MB
    },
    timestamp: new Date().toISOString()
  }),

  uploadValidationError: (): ApiResponse => ({
    success: false,
    error: 'VALIDATION_ERROR',
    message: 'Invalid file type',
    data: {
      error_code: 'INVALID_FILE_TYPE',
      supported_types: ['image/jpeg', 'image/png', 'video/mp4', 'video/mov'],
      received_type: 'application/pdf'
    },
    timestamp: new Date().toISOString()
  })
}

// WebSocket message mocks
export const WebSocketMocks = {
  progressUpdate: (taskId: string, progress: number, agentId?: string) => ({
    type: 'progress-update',
    data: {
      task_id: taskId,
      overall_progress: progress,
      agent_id: agentId,
      agent_progress: agentId ? progress : undefined,
      current_stage: progress < 20 ? 'concept_generation' :
                    progress < 40 ? 'script_writing' :
                    progress < 60 ? 'image_generation' :
                    progress < 80 ? 'voice_synthesis' :
                    progress < 95 ? 'video_composition' : 'quality_control',
      estimated_time_remaining: Math.max(0, Math.floor((100 - progress) * 2)), // 2 seconds per percent
      updated_at: new Date().toISOString()
    },
    timestamp: new Date().toISOString(),
    request_id: taskId
  }),

  agentStatusUpdate: (agentId: string, status: string, progress: number, currentTask?: string) => ({
    type: 'agent-status-update',
    data: {
      agent_id: agentId,
      status,
      progress,
      current_task: currentTask,
      estimated_time: status === 'working' ? Math.floor((100 - progress) * 1.5) : undefined,
      capabilities_used: ['analysis', 'generation', 'optimization'],
      resource_usage: {
        cpu: Math.random() * 100,
        memory: Math.random() * 8192, // MB
        gpu: Math.random() * 100
      }
    },
    timestamp: new Date().toISOString()
  }),

  resultReady: (taskId: string, resultType: string, resultData: any) => ({
    type: 'result-ready',
    data: {
      task_id: taskId,
      result_type: resultType,
      result_id: `result-${Date.now()}`,
      status: 'completed',
      output: resultData,
      metadata: {
        generation_time: Math.floor(Math.random() * 30) + 10, // 10-40 seconds
        quality_score: 0.8 + Math.random() * 0.2, // 0.8-1.0
        confidence: 0.85 + Math.random() * 0.15, // 0.85-1.0
        model_version: '2.1.0',
        parameters_used: {
          temperature: 0.7,
          top_p: 0.9,
          max_tokens: 2048
        }
      },
      agent: getAgentForResultType(resultType)
    },
    timestamp: new Date().toISOString(),
    request_id: taskId
  }),

  systemMessage: (messageType: string, title: string, message: string, severity: string = 'info') => ({
    type: 'system-message',
    data: {
      message_type: messageType,
      title,
      message,
      severity,
      display_duration: severity === 'error' ? 0 : 5000, // 0 = persistent
      actions: severity === 'error' ? [
        { type: 'retry', label: 'Retry' },
        { type: 'report', label: 'Report Issue' }
      ] : [
        { type: 'dismiss', label: 'Dismiss' }
      ],
      metadata: {
        component: 'system',
        category: 'notification',
        priority: severity === 'error' ? 'high' : 'normal'
      }
    },
    timestamp: new Date().toISOString()
  }),

  errorMessage: (errorCode: string, message: string, taskId?: string, agentId?: string) => ({
    type: 'error',
    data: {
      error_code: errorCode,
      error_message: message,
      task_id: taskId,
      agent_id: agentId,
      retry_available: !['AUTH_FAILED', 'QUOTA_EXCEEDED'].includes(errorCode),
      suggested_actions: getSuggestedActions(errorCode),
      error_details: getErrorDetails(errorCode),
      support_reference: `SUP-${Date.now()}`
    },
    timestamp: new Date().toISOString(),
    request_id: taskId
  }),

  connectionStatus: (status: string, reason?: string) => ({
    type: 'connection-status',
    data: {
      status, // 'connected', 'disconnected', 'reconnecting', 'error'
      reason,
      server_time: new Date().toISOString(),
      connection_id: `conn-${Date.now()}`,
      retry_count: status === 'reconnecting' ? Math.floor(Math.random() * 3) + 1 : 0,
      next_retry_in: status === 'reconnecting' ? Math.floor(Math.random() * 5) + 1 : undefined
    },
    timestamp: new Date().toISOString()
  })
}

// Health check API responses
export const HealthApiMocks = {
  healthy: (): ApiResponse => ({
    success: true,
    data: {
      status: 'healthy',
      service: 'Short Video Maker API',
      version: '1.2.0',
      environment: 'production',
      uptime: Math.floor(Math.random() * 86400), // seconds
      timestamp: new Date().toISOString(),
      components: {
        database: { status: 'healthy', response_time: 15 },
        redis: { status: 'healthy', response_time: 3 },
        ai_service: { status: 'healthy', response_time: 250 },
        file_storage: { status: 'healthy', response_time: 45 },
        websocket: { status: 'healthy', connections: 142 }
      },
      metrics: {
        requests_per_minute: Math.floor(Math.random() * 1000) + 500,
        active_tasks: Math.floor(Math.random() * 50) + 10,
        queue_size: Math.floor(Math.random() * 20),
        error_rate: Math.random() * 0.05, // 0-5%
        average_response_time: Math.floor(Math.random() * 200) + 100 // 100-300ms
      }
    },
    timestamp: new Date().toISOString()
  }),

  degraded: (): ApiResponse => ({
    success: true,
    data: {
      status: 'degraded',
      service: 'Short Video Maker API',
      version: '1.2.0',
      environment: 'production',
      timestamp: new Date().toISOString(),
      components: {
        database: { status: 'healthy', response_time: 15 },
        redis: { status: 'healthy', response_time: 3 },
        ai_service: { status: 'degraded', response_time: 1250, error: 'High response times' },
        file_storage: { status: 'healthy', response_time: 45 },
        websocket: { status: 'healthy', connections: 142 }
      },
      issues: [
        {
          component: 'ai_service',
          severity: 'warning',
          message: 'AI service experiencing high response times',
          since: new Date(Date.now() - 300000).toISOString()
        }
      ]
    },
    timestamp: new Date().toISOString()
  }),

  unhealthy: (): ApiResponse => ({
    success: false,
    error: 'SERVICE_UNAVAILABLE',
    message: 'Service is currently unavailable',
    data: {
      status: 'unhealthy',
      service: 'Short Video Maker API',
      timestamp: new Date().toISOString(),
      issues: [
        {
          component: 'database',
          severity: 'critical',
          message: 'Database connection failed',
          since: new Date(Date.now() - 600000).toISOString()
        }
      ]
    },
    timestamp: new Date().toISOString()
  })
}

// Helper functions
function getAgentForResultType(resultType: string): string {
  const agentMap: Record<string, string> = {
    'concept': 'concept-generator',
    'script': 'script-writer',
    'storyboard': 'script-writer',
    'image': 'image-generator',
    'voice': 'voice-synthesizer',
    'video': 'video-composer',
    'thumbnail': 'video-composer'
  }
  return agentMap[resultType] || 'unknown'
}

function getSuggestedActions(errorCode: string): string[] {
  const actionMap: Record<string, string[]> = {
    'NETWORK_ERROR': ['Check internet connection', 'Try again later'],
    'SERVER_ERROR': ['Try again in a few minutes', 'Contact support if problem persists'],
    'VALIDATION_ERROR': ['Check input parameters', 'Review form data'],
    'AUTH_FAILED': ['Log in again', 'Check credentials'],
    'QUOTA_EXCEEDED': ['Upgrade plan', 'Wait for quota reset'],
    'AGENT_FAILURE': ['Simplify prompt', 'Try different parameters'],
    'TIMEOUT': ['Try again', 'Use shorter content']
  }
  return actionMap[errorCode] || ['Try again', 'Contact support']
}

function getErrorDetails(errorCode: string): any {
  const detailsMap: Record<string, any> = {
    'NETWORK_ERROR': { category: 'connectivity', retriable: true },
    'SERVER_ERROR': { category: 'server', retriable: true },
    'VALIDATION_ERROR': { category: 'client', retriable: false },
    'AUTH_FAILED': { category: 'authentication', retriable: false },
    'QUOTA_EXCEEDED': { category: 'limits', retriable: false },
    'AGENT_FAILURE': { category: 'processing', retriable: true },
    'TIMEOUT': { category: 'performance', retriable: true }
  }
  return detailsMap[errorCode] || { category: 'unknown', retriable: true }
}

// Mock response factory
export class MockResponseFactory {
  static createDelayedResponse<T>(data: T, delay: number = 500): Promise<T> {
    return new Promise(resolve => {
      setTimeout(() => resolve(data), delay)
    })
  }

  static createFailingResponse(errorRate: number = 0.3): Promise<never> {
    return new Promise((_, reject) => {
      if (Math.random() < errorRate) {
        setTimeout(() => reject(new Error('Random API failure')), 100)
      }
    })
  }

  static createProgressiveResponse<T>(
    finalData: T,
    steps: number = 5,
    interval: number = 200
  ): Promise<T> {
    return new Promise(resolve => {
      let currentStep = 0
      
      const progressInterval = setInterval(() => {
        currentStep++
        
        if (currentStep >= steps) {
          clearInterval(progressInterval)
          resolve(finalData)
        }
        
        // Emit progress event if needed
        window.dispatchEvent(new CustomEvent('mockProgress', {
          detail: { step: currentStep, total: steps, progress: (currentStep / steps) * 100 }
        }))
      }, interval)
    })
  }
}

// Export mock configurations for different test scenarios
export const TestScenarios = {
  happyPath: {
    createTask: TaskApiMocks.createTaskSuccess,
    getTask: TaskApiMocks.getTaskSuccess,
    listTasks: TaskApiMocks.listTasksSuccess,
    uploadFile: FileApiMocks.uploadSuccess,
    health: HealthApiMocks.healthy
  },
  
  errorCases: {
    validation: TaskApiMocks.createTaskValidationError,
    serverError: TaskApiMocks.createTaskServerError,
    notFound: TaskApiMocks.getTaskNotFound,
    rateLimit: TaskApiMocks.createTaskRateLimitError,
    uploadError: FileApiMocks.uploadError,
    unhealthy: HealthApiMocks.unhealthy
  },
  
  loadingStates: {
    processing: TaskApiMocks.getTaskProcessing,
    uploading: () => FileApiMocks.uploadProgress(Math.floor(Math.random() * 100)),
    degraded: HealthApiMocks.degraded
  }
}
