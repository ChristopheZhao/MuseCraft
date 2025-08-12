/**
 * Performance Testing Setup Configuration
 * 
 * Setup for performance benchmarking and monitoring tests
 */
import '@testing-library/jest-dom'

// Performance testing timeout
jest.setTimeout(30000) // 30 seconds for performance tests

// Mock performance APIs if not available
if (typeof performance === 'undefined') {
  global.performance = {
    now: () => Date.now(),
    mark: () => {},
    measure: () => {},
    clearMarks: () => {},
    clearMeasures: () => {},
    getEntriesByType: () => [],
    getEntriesByName: () => []
  } as any
}

// Mock memory API for memory testing
if (!(performance as any).memory) {
  (performance as any).memory = {
    usedJSHeapSize: 50 * 1024 * 1024, // 50MB
    totalJSHeapSize: 100 * 1024 * 1024, // 100MB
    jsHeapSizeLimit: 2 * 1024 * 1024 * 1024 // 2GB
  }
}

// Mock Web Vitals APIs
const mockWebVitalsMetric = {
  name: 'test-metric',
  value: 100,
  id: 'test-id',
  delta: 100,
  entries: []
}

jest.mock('web-vitals', () => ({
  getCLS: (callback: any) => callback({ ...mockWebVitalsMetric, name: 'CLS', value: 0.05 }),
  getFID: (callback: any) => callback({ ...mockWebVitalsMetric, name: 'FID', value: 50 }),
  getFCP: (callback: any) => callback({ ...mockWebVitalsMetric, name: 'FCP', value: 1200 }),
  getLCP: (callback: any) => callback({ ...mockWebVitalsMetric, name: 'LCP', value: 2000 }),
  getTTFB: (callback: any) => callback({ ...mockWebVitalsMetric, name: 'TTFB', value: 300 })
}))

// Mock requestAnimationFrame for animation testing
let rafCallbacks: Array<() => void> = []
const mockRequestAnimationFrame = (callback: () => void) => {
  rafCallbacks.push(callback)
  return rafCallbacks.length
}

const mockCancelAnimationFrame = (id: number) => {
  rafCallbacks = rafCallbacks.filter((_, index) => index !== id - 1)
}

global.requestAnimationFrame = mockRequestAnimationFrame
global.cancelAnimationFrame = mockCancelAnimationFrame

// Utility to flush RAF callbacks
global.flushRAFCallbacks = () => {
  const callbacks = [...rafCallbacks]
  rafCallbacks = []
  callbacks.forEach(callback => callback())
}

// Mock Intersection Observer for performance testing
global.IntersectionObserver = class IntersectionObserver {
  constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
    // Immediately trigger callback for testing
    setTimeout(() => {
      callback([{
        isIntersecting: true,
        target: document.createElement('div'),
        intersectionRatio: 1,
        boundingClientRect: {} as DOMRectReadOnly,
        intersectionRect: {} as DOMRectReadOnly,
        rootBounds: {} as DOMRectReadOnly,
        time: performance.now()
      }], this)
    }, 0)
  }
  
  observe() {}
  disconnect() {}
  unobserve() {}
}

// Performance testing utilities
export const PerformanceTestUtils = {
  // Measure component render time
  measureRenderTime: (renderFn: () => void): number => {
    const start = performance.now()
    renderFn()
    return performance.now() - start
  },

  // Simulate memory pressure
  simulateMemoryPressure: () => {
    const originalMemory = (performance as any).memory.usedJSHeapSize
    ;(performance as any).memory.usedJSHeapSize = originalMemory * 1.8 // 80% increase
  },

  // Reset memory simulation
  resetMemorySimulation: () => {
    ;(performance as any).memory.usedJSHeapSize = 50 * 1024 * 1024 // Reset to 50MB
  },

  // Simulate slow CPU
  simulateSlowCPU: (slowdownFactor: number = 2) => {
    const originalNow = performance.now
    performance.now = () => originalNow() * slowdownFactor
    return () => {
      performance.now = originalNow
    }
  },

  // Create large dataset for testing
  createLargeDataset: (size: number) => {
    return Array.from({ length: size }, (_, i) => ({
      id: `item-${i}`,
      name: `Item ${i}`,
      description: `Description for item ${i}`.repeat(10), // Make it larger
      data: Array.from({ length: 100 }, (_, j) => ({ key: `key-${j}`, value: Math.random() }))
    }))
  },

  // Measure memory usage
  measureMemoryUsage: () => {
    if ((performance as any).memory) {
      return {
        used: (performance as any).memory.usedJSHeapSize,
        total: (performance as any).memory.totalJSHeapSize,
        limit: (performance as any).memory.jsHeapSizeLimit
      }
    }
    return null
  },

  // Wait for idle period
  waitForIdle: (timeout: number = 1000): Promise<void> => {
    return new Promise((resolve) => {
      let timeoutId: NodeJS.Timeout
      
      const checkIdle = () => {
        if (rafCallbacks.length === 0) {
          clearTimeout(timeoutId)
          resolve()
        } else {
          timeoutId = setTimeout(checkIdle, 10)
        }
      }
      
      timeoutId = setTimeout(checkIdle, 10)
      
      // Fallback timeout
      setTimeout(() => {
        clearTimeout(timeoutId)
        resolve()
      }, timeout)
    })
  }
}

// Global performance benchmarks
export const PerformanceBenchmarks = {
  COMPONENT_RENDER_TIME: 50, // ms
  MEMORY_USAGE_PER_COMPONENT: 1024 * 1024, // 1MB
  ANIMATION_FRAME_TIME: 16.67, // ms (60fps)
  INTERACTION_RESPONSE_TIME: 100, // ms
  MEMORY_LEAK_THRESHOLD: 5 * 1024 * 1024, // 5MB
  BUNDLE_SIZE_THRESHOLD: 500 * 1024, // 500KB
}

// Mock hardware capabilities for testing
export const mockHardwareCapabilities = {
  highEnd: {
    hardwareConcurrency: 8,
    deviceMemory: 8,
    connection: {
      effectiveType: '4g',
      downlink: 10,
      saveData: false
    }
  },
  midRange: {
    hardwareConcurrency: 4,
    deviceMemory: 4,
    connection: {
      effectiveType: '3g',
      downlink: 2,
      saveData: false
    }
  },
  lowEnd: {
    hardwareConcurrency: 2,
    deviceMemory: 2,
    connection: {
      effectiveType: '2g',
      downlink: 0.5,
      saveData: true
    }
  }
}

// Apply hardware simulation
export const simulateHardware = (type: keyof typeof mockHardwareCapabilities) => {
  const capabilities = mockHardwareCapabilities[type]
  
  Object.defineProperty(navigator, 'hardwareConcurrency', {
    value: capabilities.hardwareConcurrency,
    writable: true
  })
  
  Object.defineProperty(navigator, 'deviceMemory', {
    value: capabilities.deviceMemory,
    writable: true
  })
  
  Object.defineProperty(navigator, 'connection', {
    value: capabilities.connection,
    writable: true
  })
}

// Performance monitoring during tests
let performanceEntries: any[] = []

const originalMark = performance.mark
const originalMeasure = performance.measure

performance.mark = function(name: string) {
  performanceEntries.push({ type: 'mark', name, timestamp: performance.now() })
  return originalMark.call(this, name)
}

performance.measure = function(name: string, startMark?: string, endMark?: string) {
  const result = originalMeasure.call(this, name, startMark, endMark)
  performanceEntries.push({ 
    type: 'measure', 
    name, 
    startMark, 
    endMark, 
    timestamp: performance.now() 
  })
  return result
}

// Export performance data for analysis
export const getPerformanceData = () => [...performanceEntries]
export const clearPerformanceData = () => { performanceEntries = [] }

// Cleanup after each test
afterEach(() => {
  clearPerformanceData()
  PerformanceTestUtils.resetMemorySimulation()
  rafCallbacks = []
})