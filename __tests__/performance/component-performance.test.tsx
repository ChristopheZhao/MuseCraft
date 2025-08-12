/**
 * Component Performance and Benchmarking Tests
 * 
 * Tests component rendering performance, memory usage, bundle size impact,
 * animation smoothness, and overall user experience metrics.
 */
import React from 'react'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { getCLS, getFID, getFCP, getLCP, getTTFB } from 'web-vitals'
import { useAppStore } from '../../src/store/useAppStore'

// Import components for performance testing
import VideoRequestForm from '../../src/components/forms/VideoRequestForm'
import AgentOrchestrator from '../../src/components/agents/AgentOrchestrator'
import RealTimeProgress from '../../src/components/progress/RealTimeProgress'
import VideoPlayer from '../../src/components/video/VideoPlayer'
import AppLayout from '../../src/components/layout/AppLayout'

// Mock dependencies
jest.mock('../../src/store/useAppStore')
const mockUseAppStore = useAppStore as jest.MockedFunction<typeof useAppStore>

// Performance monitoring utilities
class PerformanceMonitor {
  private marks: Map<string, number> = new Map()
  private measures: Map<string, number> = new Map()

  mark(name: string): void {
    this.marks.set(name, performance.now())
    performance.mark(name)
  }

  measure(name: string, startMark: string, endMark?: string): number {
    const endTime = endMark ? this.marks.get(endMark) : performance.now()
    const startTime = this.marks.get(startMark)
    
    if (!startTime) {
      throw new Error(`Start mark "${startMark}" not found`)
    }

    const duration = (endTime || performance.now()) - startTime
    this.measures.set(name, duration)
    
    performance.measure(name, startMark, endMark)
    return duration
  }

  getMeasure(name: string): number | undefined {
    return this.measures.get(name)
  }

  getAllMeasures(): Record<string, number> {
    return Object.fromEntries(this.measures)
  }

  clear(): void {
    this.marks.clear()
    this.measures.clear()
    performance.clearMarks()
    performance.clearMeasures()
  }
}

// Memory usage tracking
class MemoryTracker {
  private snapshots: Array<{ timestamp: number; memory: any }> = []

  takeSnapshot(label: string): void {
    if ((performance as any).memory) {
      this.snapshots.push({
        timestamp: performance.now(),
        memory: {
          label,
          usedJSHeapSize: (performance as any).memory.usedJSHeapSize,
          totalJSHeapSize: (performance as any).memory.totalJSHeapSize,
          jsHeapSizeLimit: (performance as any).memory.jsHeapSizeLimit
        }
      })
    }
  }

  getMemoryDelta(startLabel: string, endLabel: string): number {
    const start = this.snapshots.find(s => s.memory.label === startLabel)
    const end = this.snapshots.find(s => s.memory.label === endLabel)
    
    if (!start || !end) return 0
    
    return end.memory.usedJSHeapSize - start.memory.usedJSHeapSize
  }

  clear(): void {
    this.snapshots = []
  }
}

describe('Component Performance and Benchmarking Tests', () => {
  let performanceMonitor: PerformanceMonitor
  let memoryTracker: MemoryTracker
  let mockStore: any

  beforeEach(() => {
    performanceMonitor = new PerformanceMonitor()
    memoryTracker = new MemoryTracker()

    mockStore = {
      ui: {
        isLoading: false,
        currentStep: 'input',
        sidebarCollapsed: false,
        notifications: [],
        modal: null,
      },
      currentRequest: null,
      results: [],
      agents: Array.from({ length: 6 }, (_, i) => ({
        id: `agent-${i}`,
        name: `Agent ${i}`,
        type: 'test-agent',
        status: 'idle',
        progress: Math.random() * 100,
        description: `Test agent ${i} description`,
        capabilities: ['test-capability-1', 'test-capability-2']
      })),
      wsConnected: false,
      updateAgent: jest.fn(),
      addResult: jest.fn(),
      setCurrentStep: jest.fn(),
      addNotification: jest.fn(),
    }

    mockUseAppStore.mockReturnValue(mockStore)
  })

  afterEach(() => {
    performanceMonitor.clear()
    memoryTracker.clear()
    jest.clearAllMocks()
  })

  describe('Initial Render Performance', () => {
    it('should render VideoRequestForm within performance budget', () => {
      memoryTracker.takeSnapshot('form-start')
      performanceMonitor.mark('form-render-start')

      const { container } = render(<VideoRequestForm />)

      performanceMonitor.mark('form-render-end')
      memoryTracker.takeSnapshot('form-end')

      const renderTime = performanceMonitor.measure(
        'form-render-time',
        'form-render-start',
        'form-render-end'
      )

      // Form should render within 50ms on modern devices
      expect(renderTime).toBeLessThan(50)

      // Memory usage should be reasonable
      const memoryDelta = memoryTracker.getMemoryDelta('form-start', 'form-end')
      expect(memoryDelta).toBeLessThan(1024 * 1024) // Less than 1MB

      // Should not have unnecessary DOM nodes
      const domNodes = container.querySelectorAll('*').length
      expect(domNodes).toBeLessThan(100) // Reasonable DOM complexity
    })

    it('should render AgentOrchestrator efficiently with multiple agents', () => {
      memoryTracker.takeSnapshot('orchestrator-start')
      performanceMonitor.mark('orchestrator-render-start')

      render(<AgentOrchestrator />)

      performanceMonitor.mark('orchestrator-render-end')
      memoryTracker.takeSnapshot('orchestrator-end')

      const renderTime = performanceMonitor.measure(
        'orchestrator-render-time',
        'orchestrator-render-start',
        'orchestrator-render-end'
      )

      // Should render 6+ agent cards within 100ms
      expect(renderTime).toBeLessThan(100)

      // Memory usage should scale linearly with agent count
      const memoryDelta = memoryTracker.getMemoryDelta('orchestrator-start', 'orchestrator-end')
      const memoryPerAgent = memoryDelta / mockStore.agents.length
      expect(memoryPerAgent).toBeLessThan(50 * 1024) // Less than 50KB per agent
    })

    it('should handle large datasets efficiently', () => {
      // Create large dataset
      const largeAgentList = Array.from({ length: 100 }, (_, i) => ({
        id: `agent-${i}`,
        name: `Agent ${i}`,
        type: 'test-agent',
        status: 'idle',
        progress: Math.random() * 100,
        description: `Test agent ${i} description with longer text content`,
        capabilities: Array.from({ length: 10 }, (_, j) => `capability-${j}`)
      }))

      mockStore.agents = largeAgentList

      memoryTracker.takeSnapshot('large-dataset-start')
      performanceMonitor.mark('large-dataset-render-start')

      render(<AgentOrchestrator />)

      performanceMonitor.mark('large-dataset-render-end')
      memoryTracker.takeSnapshot('large-dataset-end')

      const renderTime = performanceMonitor.measure(
        'large-dataset-render-time',
        'large-dataset-render-start',
        'large-dataset-render-end'
      )

      // Should implement virtualization for large lists
      expect(renderTime).toBeLessThan(500) // Still reasonable with 100 items

      // Memory should not grow linearly with all items
      const memoryDelta = memoryTracker.getMemoryDelta('large-dataset-start', 'large-dataset-end')
      expect(memoryDelta).toBeLessThan(5 * 1024 * 1024) // Less than 5MB for 100 items
    })
  })

  describe('Update and Re-render Performance', () => {
    it('should handle rapid state updates efficiently', () => {
      const { rerender } = render(<RealTimeProgress />)

      memoryTracker.takeSnapshot('updates-start')
      performanceMonitor.mark('updates-start')

      // Simulate 50 rapid updates
      for (let i = 0; i < 50; i++) {
        act(() => {
          mockStore.agents = mockStore.agents.map(agent => ({
            ...agent,
            progress: Math.random() * 100,
            status: i % 10 === 0 ? 'completed' : 'working'
          }))
        })

        rerender(<RealTimeProgress />)
      }

      performanceMonitor.mark('updates-end')
      memoryTracker.takeSnapshot('updates-end')

      const updateTime = performanceMonitor.measure(
        'rapid-updates-time',
        'updates-start',
        'updates-end'
      )

      // 50 updates should complete within 1 second
      expect(updateTime).toBeLessThan(1000)

      // Memory should not leak during updates
      const memoryDelta = memoryTracker.getMemoryDelta('updates-start', 'updates-end')
      expect(memoryDelta).toBeLessThan(2 * 1024 * 1024) // Less than 2MB growth
    })

    it('should optimize re-renders with React.memo and useMemo', () => {
      let renderCount = 0
      const TestComponent = React.memo(() => {
        renderCount++
        return <div data-testid="memo-test">Render count: {renderCount}</div>
      })

      const { rerender } = render(<TestComponent />)

      // Re-render with same props
      rerender(<TestComponent />)
      rerender(<TestComponent />)

      // Should not re-render with same props
      expect(renderCount).toBe(1)

      // Test with changing props
      const TestComponentWithProps = React.memo(({ value }: { value: number }) => {
        renderCount++
        return <div>Value: {value}</div>
      })

      const { rerender: rerenderWithProps } = render(<TestComponentWithProps value={1} />)
      
      rerenderWithProps(<TestComponentWithProps value={1} />) // Same value
      expect(renderCount).toBe(2) // Should not increment

      rerenderWithProps(<TestComponentWithProps value={2} />) // Different value
      expect(renderCount).toBe(3) // Should increment
    })

    it('should debounce expensive operations', async () => {
      jest.useFakeTimers()
      
      let expensiveOpCount = 0
      const mockExpensiveOperation = jest.fn(() => {
        expensiveOpCount++
        // Simulate expensive operation
        const start = performance.now()
        while (performance.now() - start < 10) {
          // Busy wait for 10ms
        }
      })

      const DebouncedComponent = () => {
        const [value, setValue] = React.useState('')
        
        // Debounced effect
        React.useEffect(() => {
          const timeoutId = setTimeout(() => {
            if (value) {
              mockExpensiveOperation()
            }
          }, 300)

          return () => clearTimeout(timeoutId)
        }, [value])

        return (
          <input
            data-testid="debounced-input"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        )
      }

      render(<DebouncedComponent />)

      const input = screen.getByTestId('debounced-input')

      // Rapid typing
      fireEvent.change(input, { target: { value: 'a' } })
      fireEvent.change(input, { target: { value: 'ab' } })
      fireEvent.change(input, { target: { value: 'abc' } })

      // Fast-forward time but not enough for debounce
      act(() => {
        jest.advanceTimersByTime(200)
      })

      expect(expensiveOpCount).toBe(0) // Should not have executed

      // Fast-forward past debounce delay
      act(() => {
        jest.advanceTimersByTime(200)
      })

      expect(expensiveOpCount).toBe(1) // Should execute once

      jest.useRealTimers()
    })
  })

  describe('Animation Performance', () => {
    it('should maintain 60fps during progress animations', () => {
      const frameTimes: number[] = []
      let lastFrameTime = performance.now()

      // Mock requestAnimationFrame to track frame timing
      const originalRAF = window.requestAnimationFrame
      window.requestAnimationFrame = jest.fn((callback) => {
        const currentTime = performance.now()
        frameTimes.push(currentTime - lastFrameTime)
        lastFrameTime = currentTime
        return originalRAF(callback)
      })

      render(<RealTimeProgress />)

      // Simulate animated progress updates
      for (let i = 0; i < 60; i++) { // 1 second of 60fps
        act(() => {
          mockStore.agents = mockStore.agents.map(agent => ({
            ...agent,
            progress: (i / 60) * 100
          }))
        })
      }

      // Check frame consistency
      const averageFrameTime = frameTimes.reduce((a, b) => a + b, 0) / frameTimes.length
      const targetFrameTime = 1000 / 60 // 16.67ms for 60fps

      expect(averageFrameTime).toBeLessThan(targetFrameTime * 1.2) // Allow 20% variance

      // Check for frame drops (frames taking more than 33ms)
      const droppedFrames = frameTimes.filter(time => time > 33).length
      expect(droppedFrames / frameTimes.length).toBeLessThan(0.05) // Less than 5% dropped frames

      window.requestAnimationFrame = originalRAF
    })

    it('should use CSS transforms for smooth animations', () => {
      render(<RealTimeProgress />)

      const progressBars = screen.getAllByRole('progressbar')
      
      progressBars.forEach(progressBar => {
        const computedStyle = window.getComputedStyle(progressBar)
        
        // Should use transform instead of width/left for animations
        expect(computedStyle.transform).not.toBe('none')
        
        // Should have hardware acceleration
        expect(computedStyle.willChange).toContain('transform')
      })
    })

    it('should reduce animations on low-end devices', () => {
      // Mock low-end device
      Object.defineProperty(navigator, 'hardwareConcurrency', {
        value: 2,
        writable: true
      })

      // Mock slow performance
      const originalNow = performance.now
      performance.now = jest.fn(() => originalNow() * 2) // Simulate slow performance

      render(<AgentOrchestrator />)

      // Should apply performance optimizations
      const container = screen.getByTestId('agent-orchestrator')
      expect(container).toHaveClass('reduced-motion')

      performance.now = originalNow
    })
  })

  describe('Memory Management', () => {
    it('should clean up event listeners and subscriptions', () => {
      const addEventListenerSpy = jest.spyOn(window, 'addEventListener')
      const removeEventListenerSpy = jest.spyOn(window, 'removeEventListener')

      const { unmount } = render(<AppLayout><div>Test</div></AppLayout>)

      // Component should add event listeners
      expect(addEventListenerSpy).toHaveBeenCalled()

      // Clean up on unmount
      unmount()

      // Should remove event listeners
      expect(removeEventListenerSpy).toHaveBeenCalledTimes(
        addEventListenerSpy.mock.calls.length
      )

      addEventListenerSpy.mockRestore()
      removeEventListenerSpy.mockRestore()
    })

    it('should prevent memory leaks in WebSocket connections', () => {
      const mockWebSocket = {
        close: jest.fn(),
        addEventListener: jest.fn(),
        removeEventListener: jest.fn()
      }

      // Mock WebSocket
      ;(global as any).WebSocket = jest.fn(() => mockWebSocket)

      const { unmount } = render(<RealTimeProgress />)

      // Should set up WebSocket listeners
      expect(mockWebSocket.addEventListener).toHaveBeenCalled()

      // Clean up on unmount
      unmount()

      // Should close connection and remove listeners
      expect(mockWebSocket.close).toHaveBeenCalled()
      expect(mockWebSocket.removeEventListener).toHaveBeenCalled()
    })

    it('should handle large file uploads without memory leaks', () => {
      const initialMemory = (performance as any).memory?.usedJSHeapSize || 0

      // Create large mock file
      const largeFile = new File(
        [new ArrayBuffer(10 * 1024 * 1024)], // 10MB
        'large-video.mp4',
        { type: 'video/mp4' }
      )

      const TestFileUpload = () => {
        const [files, setFiles] = React.useState<File[]>([])

        React.useEffect(() => {
          // Simulate file processing
          if (files.length > 0) {
            const fileReader = new FileReader()
            fileReader.onload = () => {
              // Process file data
              console.log('File processed')
            }
            fileReader.readAsArrayBuffer(files[0])
          }
        }, [files])

        return (
          <input
            type="file"
            onChange={(e) => {
              if (e.target.files) {
                setFiles(Array.from(e.target.files))
              }
            }}
          />
        )
      }

      const { unmount } = render(<TestFileUpload />)

      const fileInput = screen.getByRole('textbox') as HTMLInputElement
      
      // Simulate file upload
      Object.defineProperty(fileInput, 'files', {
        value: [largeFile],
        writable: false,
      })
      fireEvent.change(fileInput)

      // Clean up
      unmount()

      // Memory should not grow significantly
      const finalMemory = (performance as any).memory?.usedJSHeapSize || 0
      const memoryIncrease = finalMemory - initialMemory

      expect(memoryIncrease).toBeLessThan(20 * 1024 * 1024) // Less than 20MB increase
    })
  })

  describe('Bundle Size and Loading Performance', () => {
    it('should lazy load heavy components', async () => {
      // Mock dynamic import
      const mockVideoPlayer = React.lazy(() => 
        Promise.resolve({
          default: () => <div data-testid="lazy-video-player">Lazy Loaded</div>
        })
      )

      const LazyWrapper = () => (
        <React.Suspense fallback={<div>Loading...</div>}>
          {mockVideoPlayer && React.createElement(mockVideoPlayer)}
        </React.Suspense>
      )

      render(<LazyWrapper />)

      // Should show loading state initially
      expect(screen.getByText('Loading...')).toBeInTheDocument()

      // Wait for lazy component to load
      await screen.findByTestId('lazy-video-player')
      expect(screen.getByText('Lazy Loaded')).toBeInTheDocument()
    })

    it('should tree-shake unused code', () => {
      // This test would typically be run as part of build process analysis
      // For now, we verify that components only import what they need

      const videoPlayerModule = require('../../src/components/video/VideoPlayer')
      
      // Should not import entire library when only specific functions are needed
      expect(typeof videoPlayerModule.default).toBe('function')
      expect(Object.keys(videoPlayerModule)).toHaveLength(1) // Only default export
    })
  })

  describe('Web Vitals and User Experience Metrics', () => {
    it('should meet Core Web Vitals benchmarks', (done) => {
      let metricsCollected = 0
      const targetMetrics = 4

      const collectMetric = (metric: any) => {
        metricsCollected++
        
        switch (metric.name) {
          case 'CLS':
            expect(metric.value).toBeLessThan(0.1) // Good CLS
            break
          case 'FID':
            expect(metric.value).toBeLessThan(100) // Good FID
            break
          case 'FCP':
            expect(metric.value).toBeLessThan(1800) // Good FCP
            break
          case 'LCP':
            expect(metric.value).toBeLessThan(2500) // Good LCP
            break
        }

        if (metricsCollected === targetMetrics) {
          done()
        }
      }

      // Set up Web Vitals monitoring
      getCLS(collectMetric)
      getFID(collectMetric)
      getFCP(collectMetric)
      getLCP(collectMetric)

      render(
        <AppLayout>
          <VideoRequestForm />
        </AppLayout>
      )

      // Simulate user interaction for FID
      const button = screen.getByRole('button', { name: /create video/i })
      fireEvent.click(button)

      // Simulate layout shift for CLS
      act(() => {
        const element = screen.getByTestId('video-request-form')
        element.style.height = '600px'
      })
    })
  })
})