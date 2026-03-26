/**
 * Frontend Testing Setup Configuration
 * 
 * Sets up the testing environment for React components and integration tests
 */
import '@testing-library/jest-dom'
import { TextEncoder, TextDecoder } from 'util'

// Polyfills for Node.js environment
global.TextEncoder = TextEncoder
global.TextDecoder = TextDecoder as any

// Mock WebSocket for testing
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  static instances: MockWebSocket[] = []

  public readyState: number = MockWebSocket.CONNECTING
  public onopen: ((event: Event) => void) | null = null
  public onclose: ((event: CloseEvent) => void) | null = null
  public onmessage: ((event: MessageEvent) => void) | null = null
  public onerror: ((event: Event) => void) | null = null
  public sentMessages: Array<string | ArrayBuffer | Blob | ArrayBufferView> = []

  constructor(public url: string) {
    MockWebSocket.instances.push(this)
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN
      if (this.onopen) {
        this.onopen(new Event('open'))
      }
    }, 0)
  }

  send(data: string | ArrayBuffer | Blob | ArrayBufferView) {
    this.sentMessages.push(data)
    console.log('Mock WebSocket send:', data)
  }

  close(code?: number, reason?: string) {
    this.readyState = MockWebSocket.CLOSED
    if (this.onclose) {
      this.onclose(new CloseEvent('close', { code, reason }))
    }
  }

  // Mock message simulation for testing
  simulateMessage(data: any) {
    if (this.onmessage) {
      this.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }))
    }
  }

  static resetInstances() {
    MockWebSocket.instances = []
  }
}

// @ts-ignore
global.WebSocket = MockWebSocket

export const mockWebSocketTestUtils = {
  reset() {
    MockWebSocket.resetInstances()
  },
  getLastSocket(): MockWebSocket | null {
    return MockWebSocket.instances[MockWebSocket.instances.length - 1] || null
  },
}

// Mock IntersectionObserver
global.IntersectionObserver = class IntersectionObserver {
  constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {}
  
  observe() {
    return null
  }
  
  disconnect() {
    return null
  }
  
  unobserve() {
    return null
  }
}

// Mock ResizeObserver
global.ResizeObserver = class ResizeObserver {
  constructor(callback: ResizeObserverCallback) {}
  
  observe() {
    return null
  }
  
  disconnect() {
    return null
  }
  
  unobserve() {
    return null
  }
}

// Mock matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
})

// Mock URL.createObjectURL
global.URL.createObjectURL = jest.fn(() => 'mocked-url')
global.URL.revokeObjectURL = jest.fn()

// Mock FileReader
global.FileReader = class {
  public result: string | ArrayBuffer | null = null
  public onload: ((event: ProgressEvent<FileReader>) => void) | null = null
  public onerror: ((event: ProgressEvent<FileReader>) => void) | null = null

  readAsDataURL(file: File | Blob) {
    setTimeout(() => {
      this.result = 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQ...'
      if (this.onload) {
        this.onload({ target: this } as ProgressEvent<FileReader>)
      }
    }, 0)
  }

  readAsText(file: File | Blob) {
    setTimeout(() => {
      this.result = 'mock file content'
      if (this.onload) {
        this.onload({ target: this } as ProgressEvent<FileReader>)
      }
    }, 0)
  }
} as any

// Mock HTMLMediaElement
Object.defineProperty(HTMLMediaElement.prototype, 'play', {
  writable: true,
  value: jest.fn().mockImplementation(() => Promise.resolve()),
})

Object.defineProperty(HTMLMediaElement.prototype, 'pause', {
  writable: true,
  value: jest.fn(),
})

// Mock fetch for API calls
global.fetch = jest.fn()

// Setup mock API responses
export const mockApiResponses = {
  tasks: {
    create: {
      id: 1,
      task_id: 'test-task-123',
      title: 'Test Video Generation',
      status: 'pending',
      progress_percentage: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    list: [
      {
        id: 1,
        task_id: 'test-task-123',
        title: 'Test Video Generation',
        status: 'completed',
        progress_percentage: 100,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
    ],
    detail: {
      id: 1,
      task_id: 'test-task-123',
      title: 'Test Video Generation',
      status: 'completed',
      progress_percentage: 100,
      description: 'Test video description',
      input_parameters: {
        user_prompt: 'Create a test video',
        video_style: 'professional',
        duration: 30,
        aspect_ratio: '16:9'
      },
      output_metadata: {
        video_url: 'https://example.com/test-video.mp4',
        thumbnail_url: 'https://example.com/test-thumbnail.jpg'
      },
      scenes_count: 3,
      resources_count: 5,
      agent_executions_count: 6,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
  },
  health: {
    status: 'healthy',
    service: 'Short Video Maker API',
    version: '1.0.0',
    environment: 'test'
  },
  files: {
    upload: {
      file_id: 'test-file-123',
      filename: 'test-image.jpg',
      content_type: 'image/jpeg',
      file_size: 1024,
      url: 'https://example.com/test-image.jpg',
      upload_time: new Date().toISOString()
    }
  }
}

// Helper function to setup fetch mocks
export const setupFetchMocks = () => {
  const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
  
  mockFetch.mockImplementation((url: string | URL | Request, options?: RequestInit) => {
    const urlString = url.toString()
    
    // Mock API endpoints
    if (urlString.includes('/api/v1/tasks') && options?.method === 'POST') {
      return Promise.resolve({
        ok: true,
        status: 201,
        json: () => Promise.resolve(mockApiResponses.tasks.create),
      } as Response)
    }
    
    if (urlString.includes('/api/v1/tasks') && (!options?.method || options.method === 'GET')) {
      if (urlString.includes('test-task-123')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(mockApiResponses.tasks.detail),
        } as Response)
      } else {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(mockApiResponses.tasks.list),
        } as Response)
      }
    }
    
    if (urlString.includes('/health')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockApiResponses.health),
      } as Response)
    }
    
    if (urlString.includes('/api/v1/files/upload')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockApiResponses.files.upload),
      } as Response)
    }
    
    // Default mock response
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    } as Response)
  })
}

// Helper function to reset all mocks
export const resetAllMocks = () => {
  jest.clearAllMocks()
  if (global.fetch) {
    (global.fetch as jest.Mock).mockClear()
  }
}

// Test utilities
export class TestUtils {
  static async waitFor(condition: () => boolean, timeout = 5000): Promise<void> {
    const startTime = Date.now()
    
    while (Date.now() - startTime < timeout) {
      if (condition()) {
        return
      }
      await new Promise(resolve => setTimeout(resolve, 50))
    }
    
    throw new Error(`Condition not met within ${timeout}ms`)
  }
  
  static createMockFile(name = 'test-file.jpg', type = 'image/jpeg', size = 1024): File {
    const content = new Array(size).fill('a').join('')
    return new File([content], name, { type })
  }
  
  static createMockVideoRequest() {
    return {
      user_prompt: 'Create a test video about AI technology',
      video_style: 'professional',
      duration: 60,
      aspect_ratio: '16:9' as const,
    }
  }
  
  static simulateWebSocketMessage(ws: MockWebSocket, message: any) {
    ws.simulateMessage(message)
  }
}

// Global test configuration
beforeEach(() => {
  setupFetchMocks()
})

afterEach(() => {
  resetAllMocks()
})
