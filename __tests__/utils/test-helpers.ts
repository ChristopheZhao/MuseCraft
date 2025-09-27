/**
 * Comprehensive Test Utilities and Helper Functions
 * 
 * Provides common testing utilities, mock factories, custom matchers,
 * and helper functions used across all test suites.
 */
import { render, RenderOptions, RenderResult } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReactElement, ReactNode } from 'react'
import { VideoRequest, Agent, GenerationResult, Notification, FileUpload } from '../../src/types'

// Custom render function with providers
interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  initialState?: any
  withRouter?: boolean
  withTheme?: boolean
}

export const customRender = (
  ui: ReactElement,
  options: CustomRenderOptions = {}
): RenderResult & { user: ReturnType<typeof userEvent.setup> } => {
  const { initialState, withRouter = true, withTheme = true, ...renderOptions } = options

  const AllTheProviders = ({ children }: { children: ReactNode }) => {
    // Here you would wrap with your app providers (Router, Theme, etc.)
    return <div data-testid="test-wrapper">{children}</div>
  }

  const result = render(ui, { wrapper: AllTheProviders, ...renderOptions })
  
  return {
    ...result,
    user: userEvent.setup()
  }
}

// Factory functions for creating mock data
export class MockDataFactory {
  static createVideoRequest(overrides: Partial<VideoRequest> = {}): VideoRequest {
    return {
      id: `request-${Date.now()}`,
      title: 'Test Video Request',
      description: 'A test video request for automated testing',
      style: {
        id: 'professional',
        name: 'Professional',
        description: 'Clean and professional style',
        thumbnail: 'https://example.com/professional.jpg',
        category: 'corporate'
      },
      duration: 60,
      aspectRatio: '16:9',
      musicSettings: {
        enabled: false,
        genre: 'corporate',
        mood: 'upbeat',
        volume: 0.3
      },
      createdAt: new Date(),
      updatedAt: new Date(),
      ...overrides
    }
  }

  static createAgent(overrides: Partial<Agent> = {}): Agent {
    const agentId = overrides.id || `agent-${Date.now()}`
    
    return {
      id: agentId,
      name: `Test Agent ${agentId}`,
      type: 'concept-generator',
      status: 'idle',
      progress: 0,
      description: 'A test agent for automated testing',
      capabilities: ['test-capability-1', 'test-capability-2'],
      currentTask: undefined,
      estimatedTime: undefined,
      ...overrides
    }
  }

  static createGenerationResult(overrides: Partial<GenerationResult> = {}): GenerationResult {
    return {
      id: `result-${Date.now()}`,
      requestId: 'test-request-123',
      type: 'concept',
      status: 'completed',
      data: {
        concept: 'Test generated concept',
        themes: ['technology', 'innovation'],
        narrative: 'A test narrative for the concept'
      },
      createdAt: new Date(),
      agent: 'concept-generator',
      confidence: 0.85,
      ...overrides
    }
  }

  static createNotification(overrides: Partial<Notification> = {}): Notification {
    return {
      id: `notification-${Date.now()}`,
      type: 'info',
      title: 'Test Notification',
      message: 'This is a test notification for automated testing',
      timestamp: new Date(),
      autoClose: undefined,
      ...overrides
    }
  }

  static createFileUpload(overrides: Partial<FileUpload> = {}): FileUpload {
    return {
      id: `file-${Date.now()}`,
      file: this.createMockFile(),
      progress: 0,
      status: 'pending',
      url: undefined,
      type: 'image',
      ...overrides
    }
  }

  static createMockFile(
    name: string = 'test-file.jpg',
    type: string = 'image/jpeg',
    size: number = 1024 * 1024 // 1MB
  ): File {
    const content = new Array(size).fill('a').join('')
    return new File([content], name, { type })
  }

  static createMockBlob(
    content: string = 'test content',
    type: string = 'text/plain'
  ): Blob {
    return new Blob([content], { type })
  }

  static createMockWebSocketMessage<T = any>(
    type: string,
    data: T,
    overrides: any = {}
  ) {
    return {
      type,
      data,
      timestamp: new Date().toISOString(),
      requestId: 'test-request-123',
      ...overrides
    }
  }
}

// Test data generators
export class TestDataGenerator {
  static generateLargeDataset<T>(
    factory: () => T,
    count: number = 100
  ): T[] {
    return Array.from({ length: count }, factory)
  }

  static generateSequentialData<T>(
    factory: (index: number) => T,
    count: number = 10
  ): T[] {
    return Array.from({ length: count }, (_, index) => factory(index))
  }

  static generateRandomAgentUpdates(agentIds: string[], count: number = 50) {
    return Array.from({ length: count }, (_, index) => ({
      agentId: agentIds[Math.floor(Math.random() * agentIds.length)],
      update: {
        progress: Math.floor(Math.random() * 100),
        status: ['idle', 'working', 'completed', 'error'][Math.floor(Math.random() * 4)],
        currentTask: `Task ${index + 1}`
      }
    }))
  }

  static generateStressTestData() {
    return {
      agents: this.generateLargeDataset(() => MockDataFactory.createAgent(), 50),
      results: this.generateLargeDataset(() => MockDataFactory.createGenerationResult(), 100),
      notifications: this.generateLargeDataset(() => MockDataFactory.createNotification(), 25)
    }
  }
}

// Mock implementations
export class MockImplementations {
  static createMockWebSocket() {
    const mockWS = {
      readyState: WebSocket.CONNECTING,
      url: 'ws://localhost:8000/ws',
      onopen: null as ((event: Event) => void) | null,
      onclose: null as ((event: CloseEvent) => void) | null,
      onmessage: null as ((event: MessageEvent) => void) | null,
      onerror: null as ((event: Event) => void) | null,
      
      send: jest.fn(),
      close: jest.fn(),
      
      // Test utilities
      simulateOpen: () => {
        mockWS.readyState = WebSocket.OPEN
        if (mockWS.onopen) {
          mockWS.onopen(new Event('open'))
        }
      },
      
      simulateClose: (code: number = 1000, reason: string = 'Normal closure') => {
        mockWS.readyState = WebSocket.CLOSED
        if (mockWS.onclose) {
          mockWS.onclose(new CloseEvent('close', { code, reason }))
        }
      },
      
      simulateMessage: (data: any) => {
        if (mockWS.onmessage) {
          mockWS.onmessage(new MessageEvent('message', { 
            data: typeof data === 'string' ? data : JSON.stringify(data)
          }))
        }
      },
      
      simulateError: () => {
        if (mockWS.onerror) {
          mockWS.onerror(new Event('error'))
        }
      }
    }
    
    return mockWS
  }

  static createMockIntersectionObserver() {
    return class MockIntersectionObserver {
      constructor(
        private callback: IntersectionObserverCallback,
        private options?: IntersectionObserverInit
      ) {}

      observe = jest.fn()
      unobserve = jest.fn()
      disconnect = jest.fn()

      // Test utility to trigger callback
      trigger(entries: Partial<IntersectionObserverEntry>[]) {
        const fullEntries = entries.map(entry => ({
          isIntersecting: false,
          target: document.createElement('div'),
          intersectionRatio: 0,
          boundingClientRect: {} as DOMRectReadOnly,
          intersectionRect: {} as DOMRectReadOnly,
          rootBounds: {} as DOMRectReadOnly,
          time: performance.now(),
          ...entry
        }))
        
        this.callback(fullEntries as IntersectionObserverEntry[], this as any)
      }
    }
  }

  static createMockResizeObserver() {
    return class MockResizeObserver {
      constructor(private callback: ResizeObserverCallback) {}

      observe = jest.fn()
      unobserve = jest.fn()
      disconnect = jest.fn()

      // Test utility to trigger callback
      trigger(entries: Partial<ResizeObserverEntry>[]) {
        const fullEntries = entries.map(entry => ({
          target: document.createElement('div'),
          contentRect: { width: 100, height: 100 } as DOMRectReadOnly,
          borderBoxSize: [] as any,
          contentBoxSize: [] as any,
          devicePixelContentBoxSize: [] as any,
          ...entry
        }))
        
        this.callback(fullEntries as ResizeObserverEntry[], this as any)
      }
    }
  }

  static createMockGeolocation() {
    return {
      getCurrentPosition: jest.fn(),
      watchPosition: jest.fn(),
      clearWatch: jest.fn()
    }
  }

  static createMockMediaDevices() {
    return {
      getUserMedia: jest.fn().mockResolvedValue({
        getTracks: () => [],
        getVideoTracks: () => [],
        getAudioTracks: () => []
      }),
      enumerateDevices: jest.fn().mockResolvedValue([]),
      getSupportedConstraints: jest.fn().mockReturnValue({})
    }
  }
}

// Custom Jest matchers
export const customMatchers = {
  toHaveValidationError: (received: HTMLElement, expected: string) => {
    const hasAriaInvalid = received.getAttribute('aria-invalid') === 'true'
    const hasErrorMessage = received.getAttribute('aria-describedby')
    
    let errorElement: Element | null = null
    if (hasErrorMessage) {
      errorElement = document.getElementById(received.getAttribute('aria-describedby')!)
    }
    
    const hasExpectedError = errorElement?.textContent?.includes(expected)
    
    const pass = hasAriaInvalid && hasErrorMessage && hasExpectedError
    
    return {
      message: () => 
        pass 
          ? `Expected element not to have validation error "${expected}"`
          : `Expected element to have validation error "${expected}"`,
      pass
    }
  },

  toBeAccessible: (received: HTMLElement) => {
    const hasAccessibleName = !!(
      received.getAttribute('aria-label') ||
      received.getAttribute('aria-labelledby') ||
      received.textContent
    )
    
    const hasProperRole = received.getAttribute('role') || 
                         ['BUTTON', 'INPUT', 'A', 'SELECT', 'TEXTAREA'].includes(received.tagName)
    
    const pass = hasAccessibleName && hasProperRole
    
    return {
      message: () => 
        pass 
          ? 'Expected element not to be accessible'
          : 'Expected element to be accessible (have accessible name and proper role)',
      pass
    }
  },

  toHavePerformantRender: (received: () => void, maxTime: number = 50) => {
    const start = performance.now()
    received()
    const end = performance.now()
    const renderTime = end - start
    
    const pass = renderTime < maxTime
    
    return {
      message: () => 
        pass 
          ? `Expected render to take more than ${maxTime}ms but took ${renderTime}ms`
          : `Expected render to take less than ${maxTime}ms but took ${renderTime}ms`,
      pass
    }
  }
}

// Test environment setup utilities
export class TestEnvironment {
  static setupMobileViewport() {
    Object.defineProperty(window, 'innerWidth', { value: 375, writable: true })
    Object.defineProperty(window, 'innerHeight', { value: 667, writable: true })
    window.dispatchEvent(new Event('resize'))
  }

  static setupTabletViewport() {
    Object.defineProperty(window, 'innerWidth', { value: 768, writable: true })
    Object.defineProperty(window, 'innerHeight', { value: 1024, writable: true })
    window.dispatchEvent(new Event('resize'))
  }

  static setupDesktopViewport() {
    Object.defineProperty(window, 'innerWidth', { value: 1920, writable: true })
    Object.defineProperty(window, 'innerHeight', { value: 1080, writable: true })
    window.dispatchEvent(new Event('resize'))
  }

  static mockUserMedia() {
    Object.defineProperty(navigator, 'mediaDevices', {
      value: MockImplementations.createMockMediaDevices(),
      writable: true
    })
  }

  static mockGeolocation() {
    Object.defineProperty(navigator, 'geolocation', {
      value: MockImplementations.createMockGeolocation(),
      writable: true
    })
  }

  static simulateOffline() {
    Object.defineProperty(navigator, 'onLine', { value: false, writable: true })
    window.dispatchEvent(new Event('offline'))
  }

  static simulateOnline() {
    Object.defineProperty(navigator, 'onLine', { value: true, writable: true })
    window.dispatchEvent(new Event('online'))
  }

  static simulateSlowConnection() {
    Object.defineProperty(navigator, 'connection', {
      value: {
        effectiveType: '2g',
        downlink: 0.5,
        rtt: 300,
        saveData: true
      },
      writable: true
    })
  }

  static simulateFastConnection() {
    Object.defineProperty(navigator, 'connection', {
      value: {
        effectiveType: '4g',
        downlink: 10,
        rtt: 50,
        saveData: false
      },
      writable: true
    })
  }
}

// Assertion helpers
export class AssertionHelpers {
  static async waitForStateChange<T>(
    getCurrentState: () => T,
    expectedState: T,
    timeout: number = 5000
  ): Promise<void> {
    const startTime = Date.now()
    
    while (Date.now() - startTime < timeout) {
      if (getCurrentState() === expectedState) {
        return
      }
      await new Promise(resolve => setTimeout(resolve, 50))
    }
    
    throw new Error(`State did not change to expected value within ${timeout}ms`)
  }

  static expectEventuallyToBeTrue(
    condition: () => boolean,
    timeout: number = 5000,
    interval: number = 100
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const startTime = Date.now()
      
      const checkCondition = () => {
        if (condition()) {
          resolve()
        } else if (Date.now() - startTime > timeout) {
          reject(new Error(`Condition was not met within ${timeout}ms`))
        } else {
          setTimeout(checkCondition, interval)
        }
      }
      
      checkCondition()
    })
  }

  static expectArrayToContainObjectWith<T>(
    array: T[],
    matcher: Partial<T>
  ): void {
    const found = array.find(item => 
      Object.entries(matcher).every(([key, value]) => 
        (item as any)[key] === value
      )
    )
    
    if (!found) {
      throw new Error(`Array does not contain object matching ${JSON.stringify(matcher)}`)
    }
  }

  static expectElementToHaveAccessibleState(
    element: HTMLElement,
    state: string,
    value: string
  ): void {
    const actualValue = element.getAttribute(`aria-${state}`)
    if (actualValue !== value) {
      throw new Error(`Expected aria-${state} to be "${value}" but got "${actualValue}"`)
    }
  }
}

// Performance testing utilities
export class PerformanceTestUtils {
  static measureRenderTime(renderFn: () => void): number {
    const start = performance.now()
    renderFn()
    return performance.now() - start
  }

  static measureAsyncOperation<T>(operation: () => Promise<T>): Promise<{ result: T; duration: number }> {
    const start = performance.now()
    return operation().then(result => ({
      result,
      duration: performance.now() - start
    }))
  }

  static simulateSlowCPU(slowdownFactor: number = 2): () => void {
    const originalRequestAnimationFrame = window.requestAnimationFrame
    
    window.requestAnimationFrame = (callback) => {
      return originalRequestAnimationFrame(() => {
        setTimeout(callback, 16 * slowdownFactor) // Slow down by factor
      })
    }
    
    return () => {
      window.requestAnimationFrame = originalRequestAnimationFrame
    }
  }

  static trackMemoryUsage() {
    if ('memory' in performance) {
      return {
        usedJSHeapSize: (performance as any).memory.usedJSHeapSize,
        totalJSHeapSize: (performance as any).memory.totalJSHeapSize,
        jsHeapSizeLimit: (performance as any).memory.jsHeapSizeLimit
      }
    }
    return null
  }
}

// Export everything for easy importing
export { customRender as render }
export * from '@testing-library/react'
export { default as userEvent } from '@testing-library/user-event'
