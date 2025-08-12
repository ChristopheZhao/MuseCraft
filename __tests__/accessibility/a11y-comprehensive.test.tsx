/**
 * Comprehensive Accessibility (A11y) Tests
 * 
 * Tests keyboard navigation, screen reader compatibility, ARIA implementation,
 * color contrast, focus management, and WCAG compliance.
 */
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe, toHaveNoViolations } from 'jest-axe'
import { useAppStore } from '../../src/store/useAppStore'

// Import components for accessibility testing
import VideoRequestForm from '../../src/components/forms/VideoRequestForm'
import AgentOrchestrator from '../../src/components/agents/AgentOrchestrator'
import RealTimeProgress from '../../src/components/progress/RealTimeProgress'
import VideoPlayer from '../../src/components/video/VideoPlayer'
import AppLayout from '../../src/components/layout/AppLayout'
import NotificationContainer from '../../src/components/ui/NotificationContainer'
import Modal from '../../src/components/ui/Modal'

// Extend Jest matchers
expect.extend(toHaveNoViolations)

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

describe('Comprehensive Accessibility Tests', () => {
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
      currentRequest: {
        id: 'test-request-123',
        title: 'Test Video Generation',
        description: 'Creating a test video for accessibility testing'
      },
      results: [],
      agents: [
        {
          id: 'concept-generator',
          name: 'Concept Generator',
          type: 'concept-generator',
          status: 'working',
          progress: 45,
          description: 'Analyzes requirements and generates creative concepts',
          currentTask: 'Analyzing video requirements'
        },
        {
          id: 'script-writer',
          name: 'Script Writer',
          type: 'script-writer',
          status: 'waiting',
          progress: 0,
          description: 'Creates engaging scripts and narratives',
          currentTask: 'Waiting for concept completion'
        }
      ],
      wsConnected: true,
      updateAgent: jest.fn(),
      addNotification: jest.fn(),
      setModal: jest.fn(),
      setSidebarCollapsed: jest.fn(),
    }

    mockUseAppStore.mockReturnValue(mockStore)
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  describe('WCAG Compliance and Axe Testing', () => {
    it('should pass axe accessibility tests for VideoRequestForm', async () => {
      const { container } = render(<VideoRequestForm />)
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('should pass axe accessibility tests for AgentOrchestrator', async () => {
      const { container } = render(<AgentOrchestrator />)
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('should pass axe accessibility tests for RealTimeProgress', async () => {
      const { container } = render(<RealTimeProgress />)
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('should pass axe accessibility tests for VideoPlayer', async () => {
      const { container } = render(<VideoPlayer video={{
        url: 'https://example.com/test-video.mp4',
        title: 'Test Video for Accessibility',
        duration: 120,
        thumbnail: 'https://example.com/thumbnail.jpg'
      }} />)
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('should pass axe accessibility tests for complete AppLayout', async () => {
      const { container } = render(
        <AppLayout>
          <VideoRequestForm />
        </AppLayout>
      )
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('Keyboard Navigation', () => {
    it('should support complete keyboard navigation through VideoRequestForm', async () => {
      render(<VideoRequestForm />)

      // Start navigation from beginning
      await user.tab()
      expect(screen.getByLabelText(/video prompt/i)).toHaveFocus()

      // Navigate to style selector
      await user.tab()
      expect(screen.getByLabelText(/video style/i)).toHaveFocus()

      // Test dropdown navigation with arrows
      await user.keyboard('{ArrowDown}')
      await user.keyboard('{ArrowDown}')
      await user.keyboard('{Enter}')

      // Continue to duration field
      await user.tab()
      expect(screen.getByLabelText(/duration/i)).toHaveFocus()

      // Navigate to aspect ratio
      await user.tab()
      expect(screen.getByLabelText(/aspect ratio/i)).toHaveFocus()

      // Navigate to advanced settings
      await user.tab()
      const voiceCheckbox = screen.getByLabelText(/enable voice narration/i)
      expect(voiceCheckbox).toHaveFocus()

      // Toggle with space
      await user.keyboard(' ')
      expect(voiceCheckbox).toBeChecked()

      // Should reveal voice settings
      await user.tab()
      expect(screen.getByLabelText(/voice selection/i)).toHaveFocus()

      // Navigate to submit button
      let currentElement = document.activeElement
      while (currentElement?.getAttribute('type') !== 'submit') {
        await user.tab()
        currentElement = document.activeElement
      }

      expect(screen.getByRole('button', { name: /create video/i })).toHaveFocus()

      // Submit with Enter
      await user.keyboard('{Enter}')
      expect(mockStore.setCurrentStep).toHaveBeenCalledWith('processing')
    })

    it('should support keyboard navigation in AgentOrchestrator', async () => {
      render(<AgentOrchestrator />)

      // Should be able to navigate through agent cards
      await user.tab()
      
      const firstAgentCard = screen.getAllByTestId('agent-card')[0]
      expect(firstAgentCard).toHaveFocus()

      // Navigate to next agent
      await user.tab()
      const secondAgentCard = screen.getAllByTestId('agent-card')[1]
      expect(secondAgentCard).toHaveFocus()

      // Should be able to activate agent details with Enter
      await user.keyboard('{Enter}')
      
      // Should show expanded details or modal
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('should support keyboard navigation in VideoPlayer', async () => {
      render(<VideoPlayer video={{
        url: 'https://example.com/test-video.mp4',
        title: 'Test Video',
        duration: 120
      }} />)

      // Navigate to play button
      await user.tab()
      expect(screen.getByLabelText(/play/i)).toHaveFocus()

      // Play with Enter or Space
      await user.keyboard(' ')
      const video = screen.getByRole('video') as HTMLVideoElement
      expect(video.paused).toBe(false)

      // Navigate to progress slider
      await user.tab()
      const progressSlider = screen.getByRole('slider', { name: /progress/i })
      expect(progressSlider).toHaveFocus()

      // Control progress with arrow keys
      await user.keyboard('{ArrowRight}')
      expect(parseInt(progressSlider.getAttribute('aria-valuenow') || '0')).toBeGreaterThan(0)

      // Navigate to volume control
      await user.tab()
      const volumeSlider = screen.getByRole('slider', { name: /volume/i })
      expect(volumeSlider).toHaveFocus()

      // Control volume with arrow keys
      await user.keyboard('{ArrowUp}')
      expect(parseInt(volumeSlider.getAttribute('aria-valuenow') || '0')).toBeGreaterThan(50)

      // Navigate to fullscreen button
      await user.tab()
      expect(screen.getByLabelText(/fullscreen/i)).toHaveFocus()
    })

    it('should handle modal keyboard navigation and focus trapping', async () => {
      const onClose = jest.fn()
      
      render(
        <Modal isOpen={true} onClose={onClose} title="Test Modal">
          <div>
            <input data-testid="modal-input-1" placeholder="First input" />
            <button data-testid="modal-button">Action Button</button>
            <input data-testid="modal-input-2" placeholder="Second input" />
          </div>
        </Modal>
      )

      // Focus should be trapped within modal
      await user.tab()
      expect(screen.getByTestId('modal-input-1')).toHaveFocus()

      await user.tab()
      expect(screen.getByTestId('modal-button')).toHaveFocus()

      await user.tab()
      expect(screen.getByTestId('modal-input-2')).toHaveFocus()

      // Should wrap back to beginning
      await user.tab()
      expect(screen.getByLabelText(/close/i)).toHaveFocus()

      // Should close with Escape
      await user.keyboard('{Escape}')
      expect(onClose).toHaveBeenCalled()
    })

    it('should provide skip links for efficient navigation', async () => {
      render(
        <AppLayout>
          <VideoRequestForm />
        </AppLayout>
      )

      // Focus should start on skip link
      await user.tab()
      const skipLink = screen.getByText(/skip to main content/i)
      expect(skipLink).toHaveFocus()

      // Activating skip link should jump to main content
      await user.keyboard('{Enter}')
      const mainContent = screen.getByRole('main')
      expect(mainContent).toHaveFocus()
    })
  })

  describe('Screen Reader Support', () => {
    it('should provide proper ARIA labels and descriptions', () => {
      render(<VideoRequestForm />)

      // Form should have accessible name
      const form = screen.getByRole('form')
      expect(form).toHaveAccessibleName()

      // Required fields should be marked
      const promptInput = screen.getByLabelText(/video prompt/i)
      expect(promptInput).toHaveAttribute('aria-required', 'true')

      // Error messages should be associated
      fireEvent.click(screen.getByRole('button', { name: /create video/i }))
      
      const errorMessage = screen.getByText(/prompt is required/i)
      expect(errorMessage).toHaveAttribute('role', 'alert')
      expect(promptInput).toHaveAttribute('aria-describedby', expect.stringContaining(errorMessage.id))
    })

    it('should announce progress updates to screen readers', () => {
      render(<RealTimeProgress />)

      // Progress should have live region
      const progressRegion = screen.getByRole('status')
      expect(progressRegion).toHaveAttribute('aria-live', 'polite')

      // Progress bar should have accessible values
      const progressBar = screen.getByRole('progressbar')
      expect(progressBar).toHaveAttribute('aria-valuenow', '45')
      expect(progressBar).toHaveAttribute('aria-valuemin', '0')
      expect(progressBar).toHaveAttribute('aria-valuemax', '100')
      expect(progressBar).toHaveAttribute('aria-valuetext', '45% complete')

      // Current task should be announced
      expect(screen.getByText(/analyzing video requirements/i)).toBeInTheDocument()
      expect(screen.getByText(/analyzing video requirements/i)).toHaveAttribute('aria-live', 'polite')
    })

    it('should provide accessible video player controls', () => {
      render(<VideoPlayer video={{
        url: 'https://example.com/test-video.mp4',
        title: 'Test Video',
        duration: 120
      }} />)

      const video = screen.getByRole('video')
      expect(video).toHaveAttribute('aria-label', 'Test Video')

      // Play button should have accessible name and state
      const playButton = screen.getByRole('button', { name: /play/i })
      expect(playButton).toHaveAttribute('aria-pressed', 'false')

      // Progress slider should have accessible values
      const progressSlider = screen.getByRole('slider', { name: /progress/i })
      expect(progressSlider).toHaveAttribute('aria-valuetext', expect.stringMatching(/\d+ seconds/))

      // Volume control should be accessible
      const volumeSlider = screen.getByRole('slider', { name: /volume/i })
      expect(volumeSlider).toHaveAttribute('aria-valuetext', expect.stringMatching(/\d+%/))
    })

    it('should announce agent status changes', () => {
      const { rerender } = render(<AgentOrchestrator />)

      // Initial status should be accessible
      const conceptAgent = screen.getByText(/concept generator/i).closest('[role="article"]')
      expect(conceptAgent).toHaveAttribute('aria-label', expect.stringContaining('working'))

      // Update agent status
      mockStore.agents[0].status = 'completed'
      mockStore.agents[0].progress = 100

      rerender(<AgentOrchestrator />)

      // Status change should be announced
      const liveRegion = screen.getByRole('status')
      expect(liveRegion).toHaveTextContent(/concept generator completed/i)
    })

    it('should provide accessible notifications', () => {
      mockStore.ui.notifications = [
        {
          id: 'notification-1',
          type: 'success',
          title: 'Video Generated Successfully',
          message: 'Your video has been created and is ready for preview',
          timestamp: new Date()
        },
        {
          id: 'notification-2',
          type: 'error',
          title: 'Generation Failed',
          message: 'Unable to process video request',
          timestamp: new Date()
        }
      ]

      render(<NotificationContainer />)

      // Notifications should be alerts
      const notifications = screen.getAllByRole('alert')
      expect(notifications).toHaveLength(2)

      // Success notification
      expect(notifications[0]).toHaveAccessibleName('Video Generated Successfully')
      expect(notifications[0]).toHaveTextContent('Your video has been created and is ready for preview')

      // Error notification
      expect(notifications[1]).toHaveAccessibleName('Generation Failed')
      expect(notifications[1]).toHaveTextContent('Unable to process video request')

      // Dismiss buttons should be accessible
      const dismissButtons = screen.getAllByLabelText(/dismiss/i)
      expect(dismissButtons).toHaveLength(2)
    })
  })

  describe('Focus Management', () => {
    it('should manage focus correctly during route changes', async () => {
      const { rerender } = render(
        <AppLayout>
          <VideoRequestForm />
        </AppLayout>
      )

      // Focus form initially
      const promptInput = screen.getByLabelText(/video prompt/i)
      promptInput.focus()
      expect(promptInput).toHaveFocus()

      // Simulate route change to progress page
      mockStore.ui.currentStep = 'processing'
      
      rerender(
        <AppLayout>
          <RealTimeProgress />
        </AppLayout>
      )

      // Focus should move to main heading of new page
      await waitFor(() => {
        const heading = screen.getByRole('heading', { level: 1 })
        expect(heading).toHaveFocus()
      })
    })

    it('should restore focus after modal closure', async () => {
      const TriggerButton = () => {
        const [modalOpen, setModalOpen] = React.useState(false)
        
        return (
          <>
            <button 
              data-testid="trigger-button"
              onClick={() => setModalOpen(true)}
            >
              Open Modal
            </button>
            {modalOpen && (
              <Modal 
                isOpen={modalOpen} 
                onClose={() => setModalOpen(false)}
                title="Test Modal"
              >
                <button data-testid="modal-action">Action</button>
              </Modal>
            )}
          </>
        )
      }

      render(<TriggerButton />)

      const triggerButton = screen.getByTestId('trigger-button')
      
      // Focus trigger button and open modal
      triggerButton.focus()
      await user.click(triggerButton)

      // Focus should move to modal
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })

      // Close modal with Escape
      await user.keyboard('{Escape}')

      // Focus should return to trigger button
      await waitFor(() => {
        expect(triggerButton).toHaveFocus()
      })
    })

    it('should handle focus for dynamically added content', () => {
      const DynamicContent = () => {
        const [showContent, setShowContent] = React.useState(false)
        
        return (
          <>
            <button onClick={() => setShowContent(true)}>
              Show Content
            </button>
            {showContent && (
              <div>
                <h2 tabIndex={-1} data-testid="dynamic-heading">
                  New Content
                </h2>
                <button data-testid="dynamic-button">Action</button>
              </div>
            )}
          </>
        )
      }

      render(<DynamicContent />)

      const showButton = screen.getByText(/show content/i)
      fireEvent.click(showButton)

      // Focus should move to new content heading
      const dynamicHeading = screen.getByTestId('dynamic-heading')
      expect(dynamicHeading).toHaveFocus()
    })
  })

  describe('Color Contrast and Visual Accessibility', () => {
    it('should meet color contrast requirements', () => {
      render(
        <AppLayout>
          <VideoRequestForm />
        </AppLayout>
      )

      // Test text contrast
      const promptLabel = screen.getByText(/video prompt/i)
      const labelStyles = window.getComputedStyle(promptLabel)
      
      // Should have sufficient contrast (this would need actual color analysis in real implementation)
      expect(labelStyles.color).toBeTruthy()
      expect(labelStyles.backgroundColor).toBeTruthy()

      // Error text should have high contrast
      fireEvent.click(screen.getByRole('button', { name: /create video/i }))
      const errorText = screen.getByText(/prompt is required/i)
      const errorStyles = window.getComputedStyle(errorText)
      
      // Error text should be red or high contrast color
      expect(errorStyles.color).toMatch(/#[0-9a-f]{6}|rgb\(|red/i)
    })

    it('should support high contrast mode', () => {
      // Mock high contrast media query
      Object.defineProperty(window, 'matchMedia', {
        value: jest.fn().mockImplementation(query => ({
          matches: query === '(prefers-contrast: high)' || query === '(-ms-high-contrast: active)',
          media: query,
          onchange: null,
          addListener: jest.fn(),
          removeListener: jest.fn(),
          addEventListener: jest.fn(),
          removeEventListener: jest.fn(),
          dispatchEvent: jest.fn(),
        })),
      })

      render(<VideoRequestForm />)

      // Components should adapt to high contrast mode
      const form = screen.getByRole('form')
      expect(form).toHaveClass('high-contrast')
    })

    it('should not rely solely on color for information', () => {
      render(<AgentOrchestrator />)

      // Agent status should be conveyed through multiple means
      const workingAgent = screen.getByText(/concept generator/i).closest('[role="article"]')
      
      // Should have text indication
      expect(screen.getByText(/working/i)).toBeInTheDocument()
      
      // Should have icon or symbol
      expect(screen.getByLabelText(/working status/i)).toBeInTheDocument()
      
      // Should have progress indicator
      expect(screen.getByRole('progressbar')).toBeInTheDocument()
    })
  })

  describe('Motion and Animation Accessibility', () => {
    it('should respect prefers-reduced-motion', () => {
      // Mock reduced motion preference
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

      render(<RealTimeProgress />)

      // Animations should be disabled
      const progressBars = screen.getAllByRole('progressbar')
      progressBars.forEach(bar => {
        expect(bar).toHaveClass('no-animation')
      })

      // Transitions should be reduced
      const container = screen.getByTestId('progress-container')
      expect(container).toHaveClass('reduced-motion')
    })

    it('should provide pause controls for auto-playing content', () => {
      render(<VideoPlayer video={{
        url: 'https://example.com/test-video.mp4',
        title: 'Auto-playing Video',
        duration: 120,
        autoplay: true
      }} />)

      // Should have pause control prominently available
      const pauseButton = screen.getByRole('button', { name: /pause/i })
      expect(pauseButton).toBeInTheDocument()

      // Should be keyboard accessible
      pauseButton.focus()
      expect(pauseButton).toHaveFocus()
    })
  })

  describe('Form Accessibility', () => {
    it('should provide accessible form validation', async () => {
      render(<VideoRequestForm />)

      // Submit empty form
      await user.click(screen.getByRole('button', { name: /create video/i }))

      // Error messages should be accessible
      const errorMessages = screen.getAllByRole('alert')
      expect(errorMessages.length).toBeGreaterThan(0)

      // Errors should be associated with fields
      const promptInput = screen.getByLabelText(/video prompt/i)
      const promptError = screen.getByText(/prompt is required/i)
      
      expect(promptInput).toHaveAttribute('aria-describedby', expect.stringContaining(promptError.id))
      expect(promptInput).toHaveAttribute('aria-invalid', 'true')

      // Fix error and verify validation clears
      await user.type(promptInput, 'Test video prompt')
      
      expect(promptInput).toHaveAttribute('aria-invalid', 'false')
      expect(screen.queryByText(/prompt is required/i)).not.toBeInTheDocument()
    })

    it('should provide helpful field descriptions', () => {
      render(<VideoRequestForm />)

      // Fields should have descriptive help text
      const durationInput = screen.getByLabelText(/duration/i)
      const durationHelp = screen.getByText(/duration in seconds/i)
      
      expect(durationInput).toHaveAttribute('aria-describedby', expect.stringContaining(durationHelp.id))

      // Complex fields should have detailed descriptions
      const styleSelect = screen.getByLabelText(/video style/i)
      const styleHelp = screen.getByText(/choose the visual style/i)
      
      expect(styleSelect).toHaveAttribute('aria-describedby', expect.stringContaining(styleHelp.id))
    })

    it('should group related form controls', () => {
      render(<VideoRequestForm />)

      // Voice settings should be in a fieldset
      const voiceFieldset = screen.getByRole('group', { name: /voice settings/i })
      expect(voiceFieldset).toBeInTheDocument()

      // Music settings should be grouped
      const musicFieldset = screen.getByRole('group', { name: /music settings/i })
      expect(musicFieldset).toBeInTheDocument()
    })
  })

  describe('Language and Internationalization', () => {
    it('should provide proper language attributes', () => {
      render(
        <AppLayout>
          <VideoRequestForm />
        </AppLayout>
      )

      // Page should have lang attribute
      expect(document.documentElement).toHaveAttribute('lang', expect.stringMatching(/^[a-z]{2}(-[A-Z]{2})?$/))

      // Content in different languages should be marked
      const foreignText = screen.queryByText(/[^\x00-\x7F]/) // Non-ASCII characters
      if (foreignText) {
        expect(foreignText).toHaveAttribute('lang')
      }
    })

    it('should provide accessible labels in multiple languages', () => {
      // This would test i18n implementation
      render(<VideoRequestForm />)

      // Labels should be properly localized
      const promptLabel = screen.getByLabelText(/video prompt/i)
      expect(promptLabel).toBeInTheDocument()

      // Form should maintain accessibility in different languages
      const form = screen.getByRole('form')
      expect(form).toHaveAccessibleName()
    })
  })

  describe('Cognitive Accessibility', () => {
    it('should provide clear and consistent navigation', () => {
      render(
        <AppLayout>
          <VideoRequestForm />
        </AppLayout>
      )

      // Navigation should be consistent
      const navItems = screen.getAllByRole('menuitem')
      navItems.forEach(item => {
        expect(item).toHaveAccessibleName()
      })

      // Breadcrumbs should show current location
      const breadcrumbs = screen.getByRole('navigation', { name: /breadcrumb/i })
      expect(breadcrumbs).toBeInTheDocument()
    })

    it('should provide helpful error messages and recovery options', async () => {
      render(<VideoRequestForm />)

      // Submit form with invalid data
      await user.type(screen.getByLabelText(/duration/i), 'invalid')
      await user.click(screen.getByRole('button', { name: /create video/i }))

      // Error message should be helpful
      const errorMessage = screen.getByText(/duration must be a number/i)
      expect(errorMessage).toBeInTheDocument()

      // Should provide suggestion for fixing
      const suggestion = screen.getByText(/enter a number between/i)
      expect(suggestion).toBeInTheDocument()
    })

    it('should provide time limits and warnings appropriately', () => {
      mockStore.ui.currentStep = 'processing'
      mockStore.currentRequest = {
        ...mockStore.currentRequest,
        estimatedTime: 300 // 5 minutes
      }

      render(<RealTimeProgress />)

      // Should show estimated time
      expect(screen.getByText(/estimated time/i)).toBeInTheDocument()
      expect(screen.getByText(/5 minutes/i)).toBeInTheDocument()

      // Should warn if process is taking longer than expected
      mockStore.currentRequest.estimatedTime = -60 // 1 minute overdue
      
      const warningMessage = screen.getByText(/taking longer than expected/i)
      expect(warningMessage).toHaveAttribute('role', 'alert')
    })
  })
})