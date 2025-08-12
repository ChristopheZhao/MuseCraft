/**
 * Responsive Design and Cross-Device Integration Tests
 * 
 * Tests responsive layouts, touch interactions, orientation changes,
 * and device-specific behaviors across different screen sizes.
 */
import React from 'react'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useAppStore } from '../../src/store/useAppStore'

// Import components to test
import AppLayout from '../../src/components/layout/AppLayout'
import VideoRequestForm from '../../src/components/forms/VideoRequestForm'
import AgentOrchestrator from '../../src/components/agents/AgentOrchestrator'
import RealTimeProgress from '../../src/components/progress/RealTimeProgress'
import VideoPlayer from '../../src/components/video/VideoPlayer'

// Mock dependencies
jest.mock('../../src/store/useAppStore')
const mockUseAppStore = useAppStore as jest.MockedFunction<typeof useAppStore>

// Mock next/router
jest.mock('next/router', () => ({
  useRouter: () => ({
    push: jest.fn(),
    pathname: '/',
    query: {},
    asPath: '/',
  }),
}))

// Mock ResizeObserver
const mockResizeObserver = jest.fn(() => ({
  observe: jest.fn(),
  disconnect: jest.fn(),
  unobserve: jest.fn(),
}))
global.ResizeObserver = mockResizeObserver

describe('Responsive Design and Cross-Device Integration Tests', () => {
  let mockStore: any
  let user: ReturnType<typeof userEvent.setup>

  beforeEach(() => {
    user = userEvent.setup()

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
      agents: [
        {
          id: 'concept-generator',
          name: 'Concept Generator',
          status: 'idle',
          progress: 0,
        },
        {
          id: 'script-writer',
          name: 'Script Writer',
          status: 'idle',
          progress: 0,
        }
      ],
      wsConnected: false,
      setSidebarCollapsed: jest.fn(),
      setModal: jest.fn(),
      addNotification: jest.fn(),
      updateAgent: jest.fn(),
    }

    mockUseAppStore.mockReturnValue(mockStore)

    // Reset viewport to default
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 1024,
    })
    Object.defineProperty(window, 'innerHeight', {
      writable: true,
      configurable: true,
      value: 768,
    })
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  describe('Viewport Adaptations', () => {
    const setViewport = (width: number, height: number) => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: width,
      })
      Object.defineProperty(window, 'innerHeight', {
        writable: true,
        configurable: true,
        value: height,
      })

      // Trigger resize event
      act(() => {
        window.dispatchEvent(new Event('resize'))
      })
    }

    it('should adapt layout for mobile devices (320px - 768px)', () => {
      setViewport(375, 667) // iPhone 6/7/8 dimensions

      render(
        <AppLayout>
          <VideoRequestForm />
        </AppLayout>
      )

      // Check mobile-specific layout classes
      const layout = screen.getByTestId('app-layout')
      expect(layout).toHaveClass('mobile-layout')

      // Sidebar should be collapsed on mobile
      expect(mockStore.setSidebarCollapsed).toHaveBeenCalledWith(true)

      // Form should stack vertically
      const form = screen.getByTestId('video-request-form')
      expect(form).toHaveClass('mobile-form')

      // Check touch-friendly button sizes
      const submitButton = screen.getByRole('button', { name: /create video/i })
      const buttonStyles = window.getComputedStyle(submitButton)
      const minTouchTarget = parseInt(buttonStyles.minHeight) >= 44 // iOS recommended minimum
      expect(minTouchTarget).toBe(true)
    })

    it('should adapt layout for tablet devices (768px - 1024px)', () => {
      setViewport(768, 1024) // iPad dimensions

      render(
        <AppLayout>
          <AgentOrchestrator />
        </AppLayout>
      )

      // Check tablet-specific layout
      const layout = screen.getByTestId('app-layout')
      expect(layout).toHaveClass('tablet-layout')

      // Sidebar might be collapsed but can be toggled
      const sidebarToggle = screen.getByLabelText(/toggle sidebar/i)
      expect(sidebarToggle).toBeInTheDocument()

      // Agent cards should be arranged in grid
      const agentContainer = screen.getByTestId('agent-orchestrator')
      expect(agentContainer).toHaveClass('tablet-grid')
    })

    it('should use desktop layout for large screens (>1024px)', () => {
      setViewport(1920, 1080) // Desktop dimensions

      render(
        <AppLayout>
          <VideoRequestForm />
        </AppLayout>
      )

      // Check desktop layout
      const layout = screen.getByTestId('app-layout')
      expect(layout).toHaveClass('desktop-layout')

      // Sidebar should be visible by default
      expect(mockStore.setSidebarCollapsed).not.toHaveBeenCalledWith(true)

      // Form should use horizontal layout
      const form = screen.getByTestId('video-request-form')
      expect(form).toHaveClass('desktop-form')
    })

    it('should handle ultra-wide screens (>1920px)', () => {
      setViewport(2560, 1440) // Ultra-wide monitor

      render(
        <AppLayout>
          <RealTimeProgress />
        </AppLayout>
      )

      // Content should be constrained to prevent overstretching
      const mainContent = screen.getByRole('main')
      const contentStyles = window.getComputedStyle(mainContent)
      const maxWidth = parseInt(contentStyles.maxWidth)
      expect(maxWidth).toBeLessThanOrEqual(1920) // Should constrain content width
    })
  })

  describe('Orientation Changes', () => {
    it('should handle portrait to landscape orientation change on mobile', () => {
      // Start in portrait
      setViewport(375, 667)
      
      const { rerender } = render(
        <AppLayout>
          <VideoPlayer video={{
            url: 'https://example.com/video.mp4',
            title: 'Test Video',
            duration: 60
          }} />
        </AppLayout>
      )

      // Verify portrait layout
      const videoContainer = screen.getByTestId('video-player-container')
      expect(videoContainer).toHaveClass('portrait-layout')

      // Change to landscape
      setViewport(667, 375)

      rerender(
        <AppLayout>
          <VideoPlayer video={{
            url: 'https://example.com/video.mp4',
            title: 'Test Video',
            duration: 60
          }} />
        </AppLayout>
      )

      // Should adapt to landscape
      expect(videoContainer).toHaveClass('landscape-layout')

      // Video should use more screen space in landscape
      const video = screen.getByRole('video')
      const videoStyles = window.getComputedStyle(video)
      expect(parseInt(videoStyles.height)).toBeGreaterThan(300)
    })

    it('should handle orientation lock for video playback', async () => {
      // Mock screen orientation API
      const mockOrientation = {
        lock: jest.fn().mockResolvedValue(undefined),
        unlock: jest.fn(),
        angle: 0,
        type: 'portrait-primary'
      }
      
      Object.defineProperty(screen, 'orientation', {
        value: mockOrientation,
        writable: true
      })

      render(<VideoPlayer video={{
        url: 'https://example.com/video.mp4',
        title: 'Test Video',
        duration: 60
      }} />)

      // Start video playback
      const playButton = screen.getByTestId('play-button')
      await user.click(playButton)

      // Should attempt to lock orientation for fullscreen
      const fullscreenButton = screen.getByTestId('fullscreen-button')
      await user.click(fullscreenButton)

      expect(mockOrientation.lock).toHaveBeenCalledWith('landscape')
    })
  })

  describe('Touch Interactions', () => {
    beforeEach(() => {
      // Mock touch capabilities
      Object.defineProperty(window, 'ontouchstart', {
        value: () => {},
        writable: true
      })
    })

    it('should handle touch gestures for video controls', async () => {
      setViewport(375, 667) // Mobile viewport

      render(<VideoPlayer video={{
        url: 'https://example.com/video.mp4',
        title: 'Test Video',
        duration: 60
      }} />)

      const videoElement = screen.getByRole('video')

      // Test tap to play/pause
      fireEvent.touchStart(videoElement, {
        touches: [{ clientX: 100, clientY: 100 }]
      })
      fireEvent.touchEnd(videoElement)

      await waitFor(() => {
        expect(videoElement).toHaveAttribute('data-playing', 'true')
      })

      // Test swipe for volume control
      fireEvent.touchStart(videoElement, {
        touches: [{ clientX: 100, clientY: 200 }]
      })
      fireEvent.touchMove(videoElement, {
        touches: [{ clientX: 100, clientY: 150 }]
      })
      fireEvent.touchEnd(videoElement)

      // Should adjust volume based on swipe direction
      expect(videoElement.volume).toBeGreaterThan(0.5)
    })

    it('should handle pinch-to-zoom for video player', () => {
      setViewport(375, 667)

      render(<VideoPlayer video={{
        url: 'https://example.com/video.mp4',
        title: 'Test Video',
        duration: 60
      }} />)

      const videoContainer = screen.getByTestId('video-player-container')

      // Simulate pinch gesture
      fireEvent.touchStart(videoContainer, {
        touches: [
          { clientX: 100, clientY: 100 },
          { clientX: 200, clientY: 200 }
        ]
      })

      fireEvent.touchMove(videoContainer, {
        touches: [
          { clientX: 80, clientY: 80 },
          { clientX: 220, clientY: 220 }
        ]
      })

      fireEvent.touchEnd(videoContainer)

      // Should enable zoom controls
      const zoomControls = screen.getByTestId('zoom-controls')
      expect(zoomControls).toBeVisible()
    })

    it('should handle pull-to-refresh for progress updates', async () => {
      setViewport(375, 667)

      render(<RealTimeProgress />)

      const progressContainer = screen.getByTestId('progress-container')

      // Simulate pull-to-refresh gesture
      fireEvent.touchStart(progressContainer, {
        touches: [{ clientX: 200, clientY: 50 }]
      })

      fireEvent.touchMove(progressContainer, {
        touches: [{ clientX: 200, clientY: 150 }]
      })

      // Should show refresh indicator
      await waitFor(() => {
        const refreshIndicator = screen.getByTestId('refresh-indicator')
        expect(refreshIndicator).toBeVisible()
      })

      fireEvent.touchEnd(progressContainer)

      // Should trigger refresh action
      await waitFor(() => {
        expect(screen.getByText(/refreshing/i)).toBeInTheDocument()
      })
    })
  })

  describe('Responsive Typography and Spacing', () => {
    it('should scale typography appropriately across devices', () => {
      const testCases = [
        { width: 320, expectedScale: 'small' },
        { width: 768, expectedScale: 'medium' },
        { width: 1024, expectedScale: 'large' },
        { width: 1920, expectedScale: 'xlarge' }
      ]

      testCases.forEach(({ width, expectedScale }) => {
        setViewport(width, 800)

        const { rerender } = render(
          <AppLayout>
            <div data-testid="typography-test">
              <h1>Main Heading</h1>
              <p>Body text content</p>
            </div>
          </AppLayout>
        )

        const heading = screen.getByRole('heading', { level: 1 })
        const paragraph = screen.getByText('Body text content')

        expect(heading).toHaveClass(`text-${expectedScale}`)
        expect(paragraph).toHaveClass(`text-${expectedScale}`)

        rerender(<div />) // Clean up for next iteration
      })
    })

    it('should adjust spacing and padding for different screen sizes', () => {
      setViewport(375, 667) // Mobile

      render(
        <AppLayout>
          <VideoRequestForm />
        </AppLayout>
      )

      const form = screen.getByTestId('video-request-form')
      const mobileStyles = window.getComputedStyle(form)
      const mobilePadding = parseInt(mobileStyles.padding)

      // Change to desktop
      setViewport(1920, 1080)

      const desktopStyles = window.getComputedStyle(form)
      const desktopPadding = parseInt(desktopStyles.padding)

      // Desktop should have more generous spacing
      expect(desktopPadding).toBeGreaterThan(mobilePadding)
    })
  })

  describe('Progressive Enhancement', () => {
    it('should provide fallbacks for unsupported features', () => {
      // Mock lack of touch support
      Object.defineProperty(window, 'ontouchstart', {
        value: undefined,
        writable: true
      })

      setViewport(375, 667)

      render(<VideoPlayer video={{
        url: 'https://example.com/video.mp4',
        title: 'Test Video',
        duration: 60
      }} />)

      // Should show mouse-friendly controls instead of touch gestures
      const mouseControls = screen.getByTestId('mouse-controls')
      expect(mouseControls).toBeVisible()

      const touchControls = screen.queryByTestId('touch-controls')
      expect(touchControls).not.toBeInTheDocument()
    })

    it('should adapt to reduced motion preferences', () => {
      // Mock prefers-reduced-motion
      Object.defineProperty(window, 'matchMedia', {
        value: jest.fn().mockImplementation(query => ({
          matches: query === '(prefers-reduced-motion: reduce)',
          media: query,
          onchange: null,
          addListener: jest.fn(),
          removeListener: jest.fn(),
          addEventListener: jest.fn(),
          removeEventListener: jest.fn(),
          dispatchEvent: jest.fn(),
        })),
      })

      render(<AgentOrchestrator />)

      // Should disable animations
      const agentCards = screen.getAllByTestId('agent-card')
      agentCards.forEach(card => {
        expect(card).toHaveClass('no-animation')
      })
    })

    it('should handle high contrast mode', () => {
      // Mock high contrast media query
      Object.defineProperty(window, 'matchMedia', {
        value: jest.fn().mockImplementation(query => ({
          matches: query === '(prefers-contrast: high)',
          media: query,
          onchange: null,
          addListener: jest.fn(),
          removeListener: jest.fn(),
          addEventListener: jest.fn(),
          removeEventListener: jest.fn(),
          dispatchEvent: jest.fn(),
        })),
      })

      render(
        <AppLayout>
          <VideoRequestForm />
        </AppLayout>
      )

      // Should apply high contrast styles
      const form = screen.getByTestId('video-request-form')
      expect(form).toHaveClass('high-contrast')

      // Buttons should have stronger borders
      const submitButton = screen.getByRole('button', { name: /create video/i })
      const buttonStyles = window.getComputedStyle(submitButton)
      expect(parseInt(buttonStyles.borderWidth)).toBeGreaterThanOrEqual(2)
    })
  })

  describe('Performance on Different Devices', () => {
    it('should optimize rendering for low-end devices', () => {
      // Mock low-end device capabilities
      Object.defineProperty(navigator, 'hardwareConcurrency', {
        value: 2,
        writable: true
      })

      Object.defineProperty(navigator, 'deviceMemory', {
        value: 2, // 2GB RAM
        writable: true
      })

      setViewport(375, 667)

      render(<AgentOrchestrator />)

      // Should enable performance optimizations
      const container = screen.getByTestId('agent-orchestrator')
      expect(container).toHaveClass('performance-optimized')

      // Should reduce animation complexity
      const animations = container.querySelectorAll('[data-animation="complex"]')
      expect(animations).toHaveLength(0)
    })

    it('should lazy load images on mobile connections', () => {
      // Mock slow connection
      Object.defineProperty(navigator, 'connection', {
        value: {
          effectiveType: '2g',
          downlink: 0.5,
          saveData: true
        },
        writable: true
      })

      setViewport(375, 667)

      render(<VideoPlayer video={{
        url: 'https://example.com/video.mp4',
        title: 'Test Video',
        duration: 60,
        thumbnail: 'https://example.com/thumbnail.jpg'
      }} />)

      // Should use low-quality thumbnail or placeholder
      const thumbnail = screen.getByRole('img')
      expect(thumbnail).toHaveAttribute('loading', 'lazy')
      expect(thumbnail.src).toMatch(/placeholder|low-quality/)
    })
  })

  describe('Cross-Browser Compatibility', () => {
    it('should handle different viewport units support', () => {
      // Test CSS custom properties fallbacks
      render(
        <AppLayout>
          <div data-testid="viewport-test" style={{ height: '100vh' }}>
            Content
          </div>
        </AppLayout>
      )

      const element = screen.getByTestId('viewport-test')
      const styles = window.getComputedStyle(element)

      // Should have fallback height values
      expect(styles.height).toBeTruthy()
    })

    it('should provide flexbox fallbacks for older browsers', () => {
      render(<VideoRequestForm />)

      const formGrid = screen.getByTestId('form-grid')
      
      // Should have both flexbox and float-based layouts
      expect(formGrid).toHaveClass('flex-layout')
      expect(formGrid).toHaveClass('float-fallback')
    })
  })

  describe('Accessibility Across Devices', () => {
    it('should maintain focus management on different input methods', async () => {
      setViewport(375, 667)

      render(<VideoRequestForm />)

      // Test keyboard navigation
      await user.tab()
      expect(screen.getByLabelText(/video prompt/i)).toHaveFocus()

      // Test programmatic focus (touch simulation)
      const styleSelect = screen.getByLabelText(/video style/i)
      act(() => {
        styleSelect.focus()
      })

      expect(styleSelect).toHaveFocus()

      // Focus should be visible for keyboard users
      await user.keyboard('{Enter}')
      expect(styleSelect).toHaveClass('focus-visible')
    })

    it('should adjust touch targets for accessibility', () => {
      setViewport(375, 667)

      render(<AgentOrchestrator />)

      const interactiveElements = screen.getAllByRole('button')
      
      interactiveElements.forEach(element => {
        const styles = window.getComputedStyle(element)
        const minSize = Math.min(
          parseInt(styles.minWidth),
          parseInt(styles.minHeight)
        )
        
        // Should meet WCAG touch target size guidelines (44px minimum)
        expect(minSize).toBeGreaterThanOrEqual(44)
      })
    })
  })
})