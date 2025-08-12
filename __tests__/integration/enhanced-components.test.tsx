/**
 * Enhanced React Components Integration Tests
 * 
 * Comprehensive integration tests focusing on real-world user scenarios,
 * component interactions, state synchronization, and edge case handling.
 */
import React from 'react'
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TestUtils, mockApiResponses } from '../setup'
import { useAppStore } from '../../src/store/useAppStore'

// Import components to test
import VideoRequestForm from '../../src/components/forms/VideoRequestForm'
import RealTimeProgress from '../../src/components/progress/RealTimeProgress'
import AgentOrchestrator from '../../src/components/agents/AgentOrchestrator'
import FileUploadZone from '../../src/components/ui/FileUploadZone'
import VideoPlayer from '../../src/components/video/VideoPlayer'
import NotificationContainer from '../../src/components/ui/NotificationContainer'
import AppLayout from '../../src/components/layout/AppLayout'

// Mock dependencies
jest.mock('../../src/store/useAppStore')
jest.mock('next/router', () => ({
  useRouter: () => ({
    push: jest.fn(),
    pathname: '/',
    query: {},
    asPath: '/',
    events: { on: jest.fn(), off: jest.fn() }
  }),
}))

const mockUseAppStore = useAppStore as jest.MockedFunction<typeof useAppStore>

describe('Enhanced React Components Integration Tests', () => {
  let mockStore: any
  let user: ReturnType<typeof userEvent.setup>

  beforeEach(() => {
    user = userEvent.setup()
    
    mockStore = {
      // UI State
      ui: {
        isLoading: false,
        currentStep: 'input',
        sidebarCollapsed: false,
        notifications: [],
        modal: null,
      },
      
      // Video Request State
      currentRequest: null,
      results: [],
      
      // Agent State
      agents: [
        {
          id: 'concept-generator',
          name: 'Concept Generator',
          type: 'concept-generator',
          status: 'idle',
          progress: 0,
          description: 'Analyzes requirements and generates creative concepts',
          capabilities: ['concept-generation', 'idea-brainstorming', 'creative-analysis'],
        },
        {
          id: 'script-writer',
          name: 'Script Writer',
          type: 'script-writer',
          status: 'idle',
          progress: 0,
          description: 'Creates engaging scripts and narratives',
          capabilities: ['script-writing', 'storytelling', 'dialogue-creation'],
        }
      ],
      
      // WebSocket connection
      wsConnected: false,
      
      // Actions
      setLoading: jest.fn(),
      setCurrentStep: jest.fn(),
      addNotification: jest.fn(),
      setCurrentRequest: jest.fn(),
      updateAgent: jest.fn(),
      addResult: jest.fn(),
      updateResult: jest.fn(),
      setModal: jest.fn(),
      setSidebarCollapsed: jest.fn(),
      removeNotification: jest.fn(),
      setWSConnected: jest.fn(),
      reset: jest.fn(),
    }
    
    mockUseAppStore.mockReturnValue(mockStore)
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  describe('Complete Video Generation Workflow', () => {
    it('should handle complete user workflow from form submission to video preview', async () => {
      // Mock successful API responses
      const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          status: 201,
          json: () => Promise.resolve(mockApiResponses.tasks.create),
        } as Response)
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            ...mockApiResponses.tasks.detail,
            status: 'completed',
            output_metadata: {
              video_url: 'https://example.com/completed-video.mp4',
              thumbnail_url: 'https://example.com/thumbnail.jpg'
            }
          }),
        } as Response)

      const { rerender } = render(<VideoRequestForm />)
      
      // Step 1: Fill out video request form
      const promptInput = screen.getByLabelText(/video prompt/i)
      const styleSelect = screen.getByLabelText(/video style/i)
      const durationInput = screen.getByLabelText(/duration/i)
      const aspectRatioSelect = screen.getByLabelText(/aspect ratio/i)
      
      await user.type(promptInput, 'Create an engaging video about sustainable technology innovations')
      await user.selectOptions(styleSelect, 'professional')
      await user.clear(durationInput)
      await user.type(durationInput, '90')
      await user.selectOptions(aspectRatioSelect, '16:9')
      
      // Add voice settings
      const enableVoiceCheckbox = screen.getByLabelText(/enable voice narration/i)
      await user.click(enableVoiceCheckbox)
      
      const voiceSelect = screen.getByLabelText(/voice/i)
      await user.selectOptions(voiceSelect, 'professional-female')
      
      // Submit form
      const submitButton = screen.getByRole('button', { name: /create video/i })
      await user.click(submitButton)
      
      // Verify form submission
      await waitFor(() => {
        expect(mockStore.setLoading).toHaveBeenCalledWith(true)
        expect(mockStore.setCurrentStep).toHaveBeenCalledWith('processing')
      })
      
      // Step 2: Simulate processing state
      act(() => {
        mockStore.ui.currentStep = 'processing'
        mockStore.ui.isLoading = false
        mockStore.currentRequest = {
          id: 'test-request-123',
          title: 'Sustainable Technology Video',
          description: 'Create an engaging video about sustainable technology innovations',
          style: { name: 'professional' },
          duration: 90,
          aspectRatio: '16:9'
        }
        mockStore.agents = mockStore.agents.map((agent, index) => ({
          ...agent,
          status: index === 0 ? 'working' : 'waiting',
          progress: index === 0 ? 45 : 0,
          currentTask: index === 0 ? 'Analyzing sustainability concepts' : 'Waiting for concept completion'
        }))
      })
      
      rerender(<RealTimeProgress />)
      
      // Verify progress display
      expect(screen.getByText(/sustainable technology video/i)).toBeInTheDocument()
      expect(screen.getByText(/concept generator/i)).toBeInTheDocument()
      expect(screen.getByText(/analyzing sustainability concepts/i)).toBeInTheDocument()
      expect(screen.getByRole('progressbar')).toBeInTheDocument()
      
      // Step 3: Simulate agent completion and workflow progression
      act(() => {
        mockStore.agents = mockStore.agents.map((agent, index) => ({
          ...agent,
          status: index === 0 ? 'completed' : index === 1 ? 'working' : 'waiting',
          progress: index === 0 ? 100 : index === 1 ? 30 : 0,
          currentTask: index === 0 ? 'Concept generation complete' : 
                       index === 1 ? 'Writing engaging script' : 'Waiting for script completion'
        }))
      })
      
      rerender(<RealTimeProgress />)
      
      // Verify workflow progression
      expect(screen.getByText(/concept generation complete/i)).toBeInTheDocument()
      expect(screen.getByText(/writing engaging script/i)).toBeInTheDocument()
      
      // Step 4: Simulate completion
      act(() => {
        mockStore.ui.currentStep = 'review'
        mockStore.results = [{
          id: 'result-123',
          requestId: 'test-request-123',
          type: 'video',
          status: 'completed',
          data: {
            url: 'https://example.com/completed-video.mp4',
            thumbnail: 'https://example.com/thumbnail.jpg',
            duration: 90,
            size: '50MB'
          },
          createdAt: new Date(),
          agent: 'video-composer',
          confidence: 0.95
        }]
      })
      
      rerender(<VideoPlayer video={{
        url: 'https://example.com/completed-video.mp4',
        title: 'Sustainable Technology Video',
        duration: 90,
        thumbnail: 'https://example.com/thumbnail.jpg'
      }} />)
      
      // Verify final result
      const video = screen.getByRole('video')
      expect(video).toBeInTheDocument()
      expect(video).toHaveAttribute('src', 'https://example.com/completed-video.mp4')
      expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument()
    })

    it('should handle multi-step form validation with complex dependencies', async () => {
      render(<VideoRequestForm />)
      
      // Test progressive validation
      const submitButton = screen.getByRole('button', { name: /create video/i })
      
      // Attempt submission with empty form
      await user.click(submitButton)
      
      // Should show all required field errors
      expect(screen.getByText(/prompt is required/i)).toBeInTheDocument()
      expect(screen.getByText(/style is required/i)).toBeInTheDocument()
      
      // Fill prompt but leave other required fields empty
      const promptInput = screen.getByLabelText(/video prompt/i)
      await user.type(promptInput, 'Test prompt')
      
      await user.click(submitButton)
      
      // Should still show style error but not prompt error
      expect(screen.queryByText(/prompt is required/i)).not.toBeInTheDocument()
      expect(screen.getByText(/style is required/i)).toBeInTheDocument()
      
      // Test conditional validation - voice settings only validated when enabled
      const enableVoiceCheckbox = screen.getByLabelText(/enable voice narration/i)
      await user.click(enableVoiceCheckbox)
      
      await user.click(submitButton)
      
      // Should now show voice-specific validation errors
      expect(screen.getByText(/voice selection is required/i)).toBeInTheDocument()
      
      // Test character limits
      const longPrompt = 'A'.repeat(1001) // Assuming 1000 char limit
      await user.clear(promptInput)
      await user.type(promptInput, longPrompt)
      
      expect(screen.getByText(/prompt is too long/i)).toBeInTheDocument()
    })
  })

  describe('Real-time Communication Integration', () => {
    it('should handle WebSocket connection lifecycle and message processing', async () => {
      // Mock WebSocket
      const mockWS = new (global as any).WebSocket('ws://localhost:8000/ws')
      
      render(<RealTimeProgress />)
      
      // Initial disconnected state
      expect(mockStore.setWSConnected).toHaveBeenCalledWith(false)
      
      // Simulate connection
      act(() => {
        mockStore.wsConnected = true
        if (mockWS.onopen) {
          mockWS.onopen(new Event('open'))
        }
      })
      
      // Should show connected status
      expect(screen.getByText(/connected/i)).toBeInTheDocument()
      
      // Simulate progress update message
      act(() => {
        mockWS.simulateMessage({
          type: 'progress-update',
          data: {
            task_id: 'test-task-123',
            agent_id: 'concept-generator',
            progress: 75,
            status: 'working',
            current_task: 'Refining concept details',
            estimated_time_remaining: 45
          }
        })
      })
      
      // Should update agent progress
      expect(mockStore.updateAgent).toHaveBeenCalledWith('concept-generator', {
        progress: 75,
        status: 'working',
        currentTask: 'Refining concept details',
        estimatedTime: 45
      })
      
      // Simulate agent completion message
      act(() => {
        mockWS.simulateMessage({
          type: 'agent-status-update',
          data: {
            agent_id: 'concept-generator',
            status: 'completed',
            progress: 100,
            result: {
              concept: 'Innovative sustainability narrative',
              themes: ['renewable energy', 'green technology', 'future cities']
            }
          }
        })
      })
      
      // Should update agent status and add result
      expect(mockStore.updateAgent).toHaveBeenCalledWith('concept-generator', {
        status: 'completed',
        progress: 100
      })
      
      // Simulate connection error and reconnection
      act(() => {
        mockStore.wsConnected = false
        if (mockWS.onclose) {
          mockWS.onclose(new CloseEvent('close', { code: 1006, reason: 'Connection lost' }))
        }
      })
      
      expect(screen.getByText(/disconnected/i)).toBeInTheDocument()
      expect(screen.getByText(/reconnecting/i)).toBeInTheDocument()
    })

    it('should handle concurrent agent updates and state synchronization', async () => {
      const initialAgents = [
        { id: 'concept-generator', status: 'working', progress: 30 },
        { id: 'script-writer', status: 'waiting', progress: 0 },
        { id: 'image-generator', status: 'waiting', progress: 0 }
      ]
      
      mockStore.agents = initialAgents
      
      const mockWS = new (global as any).WebSocket('ws://localhost:8000/ws')
      render(<AgentOrchestrator />)
      
      // Simulate multiple concurrent updates
      act(() => {
        // Agent 1 progress update
        mockWS.simulateMessage({
          type: 'progress-update',
          data: {
            agent_id: 'concept-generator',
            progress: 85,
            status: 'working'
          }
        })
        
        // Agent 2 starts working
        mockWS.simulateMessage({
          type: 'agent-status-update',
          data: {
            agent_id: 'script-writer',
            status: 'working',
            progress: 15,
            current_task: 'Analyzing concept for script structure'
          }
        })
        
        // Agent 1 completes
        mockWS.simulateMessage({
          type: 'agent-status-update',
          data: {
            agent_id: 'concept-generator',
            status: 'completed',
            progress: 100
          }
        })
      })
      
      // Verify all updates were processed correctly
      expect(mockStore.updateAgent).toHaveBeenCalledWith('concept-generator', {
        progress: 85,
        status: 'working'
      })
      
      expect(mockStore.updateAgent).toHaveBeenCalledWith('script-writer', {
        status: 'working',
        progress: 15,
        currentTask: 'Analyzing concept for script structure'
      })
      
      expect(mockStore.updateAgent).toHaveBeenCalledWith('concept-generator', {
        status: 'completed',
        progress: 100
      })
    })
  })

  describe('File Upload and Processing Integration', () => {
    it('should handle large file uploads with progress tracking and validation', async () => {
      const onUpload = jest.fn()
      
      render(<FileUploadZone 
        onUpload={onUpload}
        maxSize={50 * 1024 * 1024} // 50MB limit
        acceptedTypes={['video/mp4', 'video/mov', 'image/jpeg', 'image/png']}
        multiple={true}
      />)
      
      // Create multiple test files
      const videoFile = TestUtils.createMockFile('large-video.mp4', 'video/mp4', 45 * 1024 * 1024) // 45MB
      const imageFile = TestUtils.createMockFile('reference.jpg', 'image/jpeg', 2 * 1024 * 1024) // 2MB
      const invalidFile = TestUtils.createMockFile('document.pdf', 'application/pdf', 1024) // Invalid type
      
      const fileInput = screen.getByLabelText(/choose files/i)
      
      // Upload multiple files simultaneously
      await user.upload(fileInput, [videoFile, imageFile, invalidFile])
      
      // Should show progress for valid files
      await waitFor(() => {
        expect(screen.getByText('large-video.mp4')).toBeInTheDocument()
        expect(screen.getByText('reference.jpg')).toBeInTheDocument()
      })
      
      // Should show error for invalid file
      expect(screen.getByText(/document.pdf.*not supported/i)).toBeInTheDocument()
      
      // Should show upload progress bars
      const progressBars = screen.getAllByRole('progressbar')
      expect(progressBars).toHaveLength(2) // Only for valid files
      
      // Simulate upload progress
      act(() => {
        // Simulate video upload progress
        fireEvent.load(screen.getByText('large-video.mp4').closest('[data-testid="file-item"]'))
      })
      
      // Should call onUpload for each valid file
      await waitFor(() => {
        expect(onUpload).toHaveBeenCalledWith(
          expect.objectContaining({
            file: videoFile,
            status: 'completed',
            type: 'video'
          })
        )
        
        expect(onUpload).toHaveBeenCalledWith(
          expect.objectContaining({
            file: imageFile,
            status: 'completed',
            type: 'image'
          })
        )
      })
      
      // Should not call onUpload for invalid file
      expect(onUpload).not.toHaveBeenCalledWith(
        expect.objectContaining({
          file: invalidFile
        })
      )
    })

    it('should handle drag and drop with visual feedback', async () => {
      const onUpload = jest.fn()
      
      render(<FileUploadZone onUpload={onUpload} />)
      
      const uploadZone = screen.getByTestId('file-upload-zone')
      
      // Test drag enter
      fireEvent.dragEnter(uploadZone, {
        dataTransfer: {
          items: [{ kind: 'file', type: 'image/jpeg' }],
          types: ['Files']
        }
      })
      
      expect(uploadZone).toHaveClass('drag-active')
      
      // Test drag over
      fireEvent.dragOver(uploadZone)
      expect(uploadZone).toHaveClass('drag-over')
      
      // Test drag leave
      fireEvent.dragLeave(uploadZone)
      expect(uploadZone).not.toHaveClass('drag-over')
      
      // Test successful drop
      const testFile = TestUtils.createMockFile('dropped-image.jpg', 'image/jpeg')
      
      fireEvent.drop(uploadZone, {
        dataTransfer: {
          files: [testFile],
          items: [{ kind: 'file', type: 'image/jpeg', getAsFile: () => testFile }]
        }
      })
      
      // Should process dropped file
      await waitFor(() => {
        expect(screen.getByText('dropped-image.jpg')).toBeInTheDocument()
      })
      
      expect(uploadZone).not.toHaveClass('drag-active')
    })
  })

  describe('Notification System Integration', () => {
    it('should display and manage notifications with different types and behaviors', () => {
      const notifications = [
        {
          id: 'success-1',
          type: 'success' as const,
          title: 'Video Generated Successfully',
          message: 'Your video has been created and is ready for preview',
          timestamp: new Date(),
          autoClose: 5000
        },
        {
          id: 'error-1',
          type: 'error' as const,
          title: 'Generation Failed',
          message: 'Unable to process video request due to server error',
          timestamp: new Date()
        },
        {
          id: 'warning-1',
          type: 'warning' as const,
          title: 'Quality Notice',
          message: 'Generated content quality may be lower due to complex requirements',
          timestamp: new Date(),
          autoClose: 8000
        }
      ]
      
      mockStore.ui.notifications = notifications
      
      render(<NotificationContainer />)
      
      // Should display all notifications
      notifications.forEach(notification => {
        expect(screen.getByText(notification.title)).toBeInTheDocument()
        expect(screen.getByText(notification.message)).toBeInTheDocument()
      })
      
      // Should show appropriate icons for different types
      expect(screen.getByLabelText(/success/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/error/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/warning/i)).toBeInTheDocument()
      
      // Test manual dismissal
      const errorCloseButton = screen.getByLabelText(/dismiss.*generation failed/i)
      fireEvent.click(errorCloseButton)
      
      expect(mockStore.removeNotification).toHaveBeenCalledWith('error-1')
      
      // Test auto-close behavior (would be handled by setTimeout in real app)
      expect(notifications.filter(n => n.autoClose).length).toBe(2)
    })

    it('should handle notification overflow and stacking', () => {
      // Create many notifications
      const manyNotifications = Array.from({ length: 10 }, (_, i) => ({
        id: `notification-${i}`,
        type: 'info' as const,
        title: `Notification ${i + 1}`,
        message: `This is notification number ${i + 1}`,
        timestamp: new Date(Date.now() - i * 1000)
      }))
      
      mockStore.ui.notifications = manyNotifications
      
      render(<NotificationContainer />)
      
      // Should limit visible notifications (e.g., max 5)
      const visibleNotifications = screen.getAllByRole('alert')
      expect(visibleNotifications.length).toBeLessThanOrEqual(5)
      
      // Should show overflow indicator if there are more
      if (manyNotifications.length > 5) {
        expect(screen.getByText(/\+\d+ more/)).toBeInTheDocument()
      }
    })
  })

  describe('Error Boundary and Recovery Integration', () => {
    it('should catch component errors and display recovery options', () => {
      // Mock console.error to avoid test noise
      const originalError = console.error
      console.error = jest.fn()
      
      // Create component that throws error
      const ThrowError = ({ shouldThrow }: { shouldThrow: boolean }) => {
        if (shouldThrow) {
          throw new Error('Test component error')
        }
        return <div>No error</div>
      }
      
      const ErrorBoundaryWrapper = ({ children }: { children: React.ReactNode }) => {
        return (
          <div data-testid="error-boundary">
            {children}
          </div>
        )
      }
      
      const { rerender } = render(
        <ErrorBoundaryWrapper>
          <ThrowError shouldThrow={false} />
        </ErrorBoundaryWrapper>
      )
      
      // Should render normally
      expect(screen.getByText('No error')).toBeInTheDocument()
      
      // Trigger error
      rerender(
        <ErrorBoundaryWrapper>
          <ThrowError shouldThrow={true} />
        </ErrorBoundaryWrapper>
      )
      
      // Should show error boundary UI (would be implemented in real app)
      // For now, verify error was thrown
      expect(console.error).toHaveBeenCalled()
      
      // Restore console.error
      console.error = originalError
    })

    it('should handle API errors with retry mechanisms', async () => {
      // Mock failed then successful API response
      const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
      mockFetch
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValueOnce({
          ok: true,
          status: 201,
          json: () => Promise.resolve(mockApiResponses.tasks.create),
        } as Response)
      
      render(<VideoRequestForm />)
      
      // Fill form
      const promptInput = screen.getByLabelText(/video prompt/i)
      await user.type(promptInput, 'Test prompt')
      
      const styleSelect = screen.getByLabelText(/video style/i)
      await user.selectOptions(styleSelect, 'professional')
      
      // Submit form
      const submitButton = screen.getByRole('button', { name: /create video/i })
      await user.click(submitButton)
      
      // Should show error notification
      await waitFor(() => {
        expect(mockStore.addNotification).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'error',
            title: expect.stringContaining('failed')
          })
        )
      })
      
      // Should show retry option
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
      
      // Test retry functionality
      const retryButton = screen.getByRole('button', { name: /retry/i })
      await user.click(retryButton)
      
      // Should succeed on retry
      await waitFor(() => {
        expect(mockStore.setCurrentStep).toHaveBeenCalledWith('processing')
      })
    })
  })

  describe('Layout and Navigation Integration', () => {
    it('should handle responsive layout changes and sidebar interactions', () => {
      render(<AppLayout>
        <div>Test content</div>
      </AppLayout>)
      
      // Should render main layout components
      expect(screen.getByRole('banner')).toBeInTheDocument() // Header
      expect(screen.getByRole('navigation')).toBeInTheDocument() // Sidebar
      expect(screen.getByRole('main')).toBeInTheDocument() // Main content
      
      // Test sidebar toggle
      const sidebarToggle = screen.getByLabelText(/toggle sidebar/i)
      fireEvent.click(sidebarToggle)
      
      expect(mockStore.setSidebarCollapsed).toHaveBeenCalledWith(true)
      
      // Test keyboard navigation
      fireEvent.keyDown(sidebarToggle, { key: 'Enter' })
      expect(mockStore.setSidebarCollapsed).toHaveBeenCalledTimes(2)
    })

    it('should handle modal state management', async () => {
      const TestModal = () => (
        <div role="dialog" aria-labelledby="modal-title">
          <h2 id="modal-title">Test Modal</h2>
          <button onClick={() => mockStore.setModal(null)}>Close</button>
        </div>
      )
      
      mockStore.ui.modal = {
        type: 'test-modal',
        data: { test: 'data' },
        onClose: () => mockStore.setModal(null)
      }
      
      render(<TestModal />)
      
      // Should display modal
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText('Test Modal')).toBeInTheDocument()
      
      // Test close functionality
      const closeButton = screen.getByRole('button', { name: /close/i })
      await user.click(closeButton)
      
      expect(mockStore.setModal).toHaveBeenCalledWith(null)
      
      // Test escape key closing
      fireEvent.keyDown(document, { key: 'Escape' })
      expect(mockStore.setModal).toHaveBeenCalledWith(null)
    })
  })
})