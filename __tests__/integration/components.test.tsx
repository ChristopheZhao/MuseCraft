/**
 * React Components Integration Tests
 * 
 * Tests the integration between React components and backend API,
 * user interactions, state management, and real-time updates.
 */
import React from 'react'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TestUtils, mockApiResponses } from '../setup'

// Import components to test
import VideoRequestForm from '../../src/components/forms/VideoRequestForm'
import RealTimeProgress from '../../src/components/progress/RealTimeProgress'
import AgentOrchestrator from '../../src/components/agents/AgentOrchestrator'
import FileUploadZone from '../../src/components/ui/FileUploadZone'
import VideoPlayer from '../../src/components/video/VideoPlayer'
import { useAppStore } from '../../src/store/useAppStore'

// Mock Zustand store
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

describe('React Components Integration Tests', () => {
  let mockStore: any

  beforeEach(() => {
    mockStore = {
      // UI State
      isLoading: false,
      currentStep: 'input',
      sidebarCollapsed: false,
      notifications: [],
      modal: null,
      
      // Video Request State
      currentRequest: null,
      videoRequests: [],
      
      // Agent State
      agents: [],
      activeTask: null,
      
      // Actions
      setLoading: jest.fn(),
      setCurrentStep: jest.fn(),
      addNotification: jest.fn(),
      createVideoRequest: jest.fn(),
      updateAgent: jest.fn(),
      setActiveTask: jest.fn(),
      
      // WebSocket connection
      wsConnected: false,
      connectWebSocket: jest.fn(),
      disconnectWebSocket: jest.fn(),
    }
    
    mockUseAppStore.mockReturnValue(mockStore)
  })

  describe('VideoRequestForm Integration', () => {
    it('should submit video request and handle API response', async () => {
      const user = userEvent.setup()
      
      // Mock successful API response
      mockStore.createVideoRequest.mockResolvedValue({
        success: true,
        data: mockApiResponses.tasks.create
      })
      
      render(<VideoRequestForm />)
      
      // Fill out the form
      const promptInput = screen.getByLabelText(/video prompt/i)
      const styleSelect = screen.getByLabelText(/video style/i)
      const durationInput = screen.getByLabelText(/duration/i)
      const submitButton = screen.getByRole('button', { name: /create video/i })
      
      await user.type(promptInput, 'Create a professional video about AI technology')
      await user.selectOptions(styleSelect, 'professional')
      await user.clear(durationInput)
      await user.type(durationInput, '60')
      
      // Submit the form
      await user.click(submitButton)
      
      // Wait for API call
      await waitFor(() => {
        expect(mockStore.createVideoRequest).toHaveBeenCalledWith({
          user_prompt: 'Create a professional video about AI technology',
          video_style: 'professional',
          duration: 60,
          aspect_ratio: '16:9'
        })
      })
      
      // Verify loading state was handled
      expect(mockStore.setLoading).toHaveBeenCalledWith(true)
      expect(mockStore.setCurrentStep).toHaveBeenCalledWith('processing')
    })

    it('should handle form validation errors', async () => {
      const user = userEvent.setup()
      
      render(<VideoRequestForm />)
      
      const submitButton = screen.getByRole('button', { name: /create video/i })
      
      // Try to submit empty form
      await user.click(submitButton)
      
      // Should show validation errors
      expect(screen.getByText(/prompt is required/i)).toBeInTheDocument()
      
      // Should not call API
      expect(mockStore.createVideoRequest).not.toHaveBeenCalled()
    })

    it('should handle API errors gracefully', async () => {
      const user = userEvent.setup()
      
      // Mock API error
      mockStore.createVideoRequest.mockRejectedValue(new Error('API Error'))
      
      render(<VideoRequestForm />)
      
      // Fill minimum required fields
      const promptInput = screen.getByLabelText(/video prompt/i)
      await user.type(promptInput, 'Test prompt')
      
      const submitButton = screen.getByRole('button', { name: /create video/i })
      await user.click(submitButton)
      
      // Wait for error handling
      await waitFor(() => {
        expect(mockStore.addNotification).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'error',
            title: 'Request Failed'
          })
        )
      })
    })
  })

  describe('RealTimeProgress Integration', () => {
    it('should display progress updates from WebSocket', async () => {
      const mockTask = {
        id: 'test-task-123',
        title: 'Test Video Generation',
        status: 'processing',
        progress: 45,
        currentAgent: 'script_writer',
        estimatedTimeRemaining: 120
      }
      
      mockStore.activeTask = mockTask
      mockStore.agents = [
        {
          id: 'concept_planner',
          name: 'Concept Planner',
          status: 'completed',
          progress: 100
        },
        {
          id: 'script_writer',
          name: 'Script Writer',
          status: 'working',
          progress: 45
        },
        {
          id: 'image_generator',
          name: 'Image Generator',
          status: 'waiting',
          progress: 0
        }
      ]
      
      render(<RealTimeProgress />)
      
      // Check initial state
      expect(screen.getByText('Test Video Generation')).toBeInTheDocument()
      expect(screen.getByText('45%')).toBeInTheDocument()
      expect(screen.getByText(/script writer/i)).toBeInTheDocument()
      
      // Check agent status indicators
      expect(screen.getByText(/concept planner/i)).toBeInTheDocument()
      expect(screen.getByText(/completed/i)).toBeInTheDocument()
      expect(screen.getByText(/working/i)).toBeInTheDocument()
      expect(screen.getByText(/waiting/i)).toBeInTheDocument()
    })

    it('should update when WebSocket messages are received', async () => {
      mockStore.activeTask = {
        id: 'test-task-123',
        title: 'Test Video Generation',
        status: 'processing',
        progress: 25
      }
      
      const { rerender } = render(<RealTimeProgress />)
      
      // Initial state
      expect(screen.getByText('25%')).toBeInTheDocument()
      
      // Simulate WebSocket update
      act(() => {
        mockStore.activeTask.progress = 75
        mockStore.activeTask.status = 'processing'
      })
      
      rerender(<RealTimeProgress />)
      
      // Should show updated progress
      expect(screen.getByText('75%')).toBeInTheDocument()
    })
  })

  describe('AgentOrchestrator Integration', () => {
    it('should display agent status and coordination', () => {
      const mockAgents = [
        {
          id: 'concept_planner',
          name: 'Concept Planner',
          type: 'concept-generator',
          status: 'completed',
          progress: 100,
          description: 'Generates video concepts',
          currentTask: 'Completed concept generation'
        },
        {
          id: 'script_writer',
          name: 'Script Writer',
          type: 'script-writer',
          status: 'working',
          progress: 60,
          description: 'Writes video scripts',
          currentTask: 'Writing scene narration'
        },
        {
          id: 'image_generator',
          name: 'Image Generator',
          type: 'image-generator',
          status: 'waiting',
          progress: 0,
          description: 'Generates visual content',
          currentTask: 'Waiting for script completion'
        }
      ]
      
      mockStore.agents = mockAgents
      
      render(<AgentOrchestrator />)
      
      // Check all agents are displayed
      mockAgents.forEach(agent => {
        expect(screen.getByText(agent.name)).toBeInTheDocument()
        expect(screen.getByText(agent.description)).toBeInTheDocument()
        expect(screen.getByText(agent.currentTask)).toBeInTheDocument()
      })
      
      // Check status indicators
      expect(screen.getByText(/completed/i)).toBeInTheDocument()
      expect(screen.getByText(/working/i)).toBeInTheDocument()
      expect(screen.getByText(/waiting/i)).toBeInTheDocument()
    })

    it('should show agent coordination flow', () => {
      const mockAgents = [
        {
          id: 'concept_planner',
          name: 'Concept Planner',
          status: 'completed',
          progress: 100
        },
        {
          id: 'script_writer',
          name: 'Script Writer',
          status: 'working',
          progress: 75,
          dependencies: ['concept_planner']
        }
      ]
      
      mockStore.agents = mockAgents
      
      render(<AgentOrchestrator />)
      
      // Should show workflow connections
      expect(screen.getByText(/concept planner/i)).toBeInTheDocument()
      expect(screen.getByText(/script writer/i)).toBeInTheDocument()
      
      // Check for visual flow indicators (arrows, connections, etc.)
      const flowElements = screen.getAllByRole('presentation')
      expect(flowElements.length).toBeGreaterThan(0)
    })
  })

  describe('FileUploadZone Integration', () => {
    it('should handle file uploads and show progress', async () => {
      const user = userEvent.setup()
      const onUpload = jest.fn()
      
      render(<FileUploadZone onUpload={onUpload} />)
      
      const uploadZone = screen.getByTestId('file-upload-zone')
      const fileInput = screen.getByLabelText(/choose files/i)
      
      // Create mock file
      const testFile = TestUtils.createMockFile('test-video.mp4', 'video/mp4', 1024 * 1024)
      
      // Upload file
      await user.upload(fileInput, testFile)
      
      // Should show file in upload list
      await waitFor(() => {
        expect(screen.getByText('test-video.mp4')).toBeInTheDocument()
      })
      
      // Should show upload progress
      expect(screen.getByRole('progressbar')).toBeInTheDocument()
      
      // Should call onUpload callback
      await waitFor(() => {
        expect(onUpload).toHaveBeenCalledWith(
          expect.objectContaining({
            file: testFile,
            status: 'completed'
          })
        )
      })
    })

    it('should handle drag and drop', async () => {
      const onUpload = jest.fn()
      
      render(<FileUploadZone onUpload={onUpload} />)
      
      const uploadZone = screen.getByTestId('file-upload-zone')
      
      // Create mock file for drag and drop
      const testFile = TestUtils.createMockFile('test-image.jpg', 'image/jpeg')
      
      // Simulate drag and drop
      fireEvent.dragOver(uploadZone)
      expect(uploadZone).toHaveClass('drag-over')
      
      fireEvent.drop(uploadZone, {
        dataTransfer: {
          files: [testFile]
        }
      })
      
      // Should process dropped file
      await waitFor(() => {
        expect(screen.getByText('test-image.jpg')).toBeInTheDocument()
      })
    })

    it('should validate file types and sizes', async () => {
      const user = userEvent.setup()
      const onUpload = jest.fn()
      
      render(
        <FileUploadZone 
          onUpload={onUpload}
          acceptedTypes={['image/jpeg', 'image/png']}
          maxSize={1024 * 1024} // 1MB
        />
      )
      
      const fileInput = screen.getByLabelText(/choose files/i)
      
      // Test invalid file type
      const invalidFile = TestUtils.createMockFile('test.txt', 'text/plain')
      await user.upload(fileInput, invalidFile)
      
      expect(screen.getByText(/file type not supported/i)).toBeInTheDocument()
      expect(onUpload).not.toHaveBeenCalled()
      
      // Test file too large
      const largeFile = TestUtils.createMockFile('large.jpg', 'image/jpeg', 2 * 1024 * 1024)
      await user.upload(fileInput, largeFile)
      
      expect(screen.getByText(/file too large/i)).toBeInTheDocument()
    })
  })

  describe('VideoPlayer Integration', () => {
    it('should display video and controls', () => {
      const mockVideo = {
        url: 'https://example.com/test-video.mp4',
        title: 'Test Video',
        duration: 60,
        thumbnail: 'https://example.com/thumbnail.jpg'
      }
      
      render(<VideoPlayer video={mockVideo} />)
      
      // Check video element
      const video = screen.getByRole('video')
      expect(video).toBeInTheDocument()
      expect(video).toHaveAttribute('src', mockVideo.url)
      
      // Check controls
      expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument()
      expect(screen.getByRole('slider', { name: /progress/i })).toBeInTheDocument()
      expect(screen.getByText(/00:00/)).toBeInTheDocument() // Time display
    })

    it('should handle video playback controls', async () => {
      const user = userEvent.setup()
      
      const mockVideo = {
        url: 'https://example.com/test-video.mp4',
        title: 'Test Video',
        duration: 60
      }
      
      render(<VideoPlayer video={mockVideo} />)
      
      const playButton = screen.getByRole('button', { name: /play/i })
      const video = screen.getByRole('video') as HTMLVideoElement
      
      // Mock video methods
      const mockPlay = jest.fn().mockResolvedValue(undefined)
      const mockPause = jest.fn()
      video.play = mockPlay
      video.pause = mockPause
      
      // Test play
      await user.click(playButton)
      expect(mockPlay).toHaveBeenCalled()
      
      // Button should change to pause
      expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument()
      
      // Test pause
      const pauseButton = screen.getByRole('button', { name: /pause/i })
      await user.click(pauseButton)
      expect(mockPause).toHaveBeenCalled()
    })
  })

  describe('WebSocket Integration', () => {
    it('should connect to WebSocket and handle messages', async () => {
      mockStore.wsConnected = false
      
      const { rerender } = render(<RealTimeProgress />)
      
      // Should attempt WebSocket connection
      expect(mockStore.connectWebSocket).toHaveBeenCalled()
      
      // Simulate connection established
      act(() => {
        mockStore.wsConnected = true
      })
      
      rerender(<RealTimeProgress />)
      
      // Should show connected status
      expect(screen.getByText(/connected/i)).toBeInTheDocument()
    })

    it('should handle WebSocket disconnection', async () => {
      mockStore.wsConnected = true
      
      const { rerender } = render(<RealTimeProgress />)
      
      // Simulate disconnection
      act(() => {
        mockStore.wsConnected = false
      })
      
      rerender(<RealTimeProgress />)
      
      // Should show disconnected status and attempt reconnection
      expect(screen.getByText(/disconnected/i)).toBeInTheDocument()
      expect(mockStore.connectWebSocket).toHaveBeenCalled()
    })
  })

  describe('Error Handling Integration', () => {
    it('should display API errors to user', async () => {
      const user = userEvent.setup()
      
      // Mock API error
      mockStore.createVideoRequest.mockRejectedValue({
        message: 'Server error: Service temporarily unavailable'
      })
      
      render(<VideoRequestForm />)
      
      // Fill and submit form
      const promptInput = screen.getByLabelText(/video prompt/i)
      await user.type(promptInput, 'Test prompt')
      
      const submitButton = screen.getByRole('button', { name: /create video/i })
      await user.click(submitButton)
      
      // Should show error notification
      await waitFor(() => {
        expect(mockStore.addNotification).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'error',
            title: 'Request Failed',
            message: expect.stringContaining('Service temporarily unavailable')
          })
        )
      })
    })

    it('should handle network errors gracefully', async () => {
      const user = userEvent.setup()
      
      // Mock network error
      mockStore.createVideoRequest.mockRejectedValue(new Error('Network error'))
      
      render(<VideoRequestForm />)
      
      const promptInput = screen.getByLabelText(/video prompt/i)
      await user.type(promptInput, 'Test prompt')
      
      const submitButton = screen.getByRole('button', { name: /create video/i })
      await user.click(submitButton)
      
      // Should show generic error message
      await waitFor(() => {
        expect(mockStore.addNotification).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'error',
            title: 'Connection Error'
          })
        )
      })
    })
  })

  describe('Responsive Design Integration', () => {
    it('should adapt to mobile viewport', () => {
      // Mock mobile viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      })
      
      Object.defineProperty(window, 'innerHeight', {
        writable: true,
        configurable: true,
        value: 667,
      })
      
      render(<VideoRequestForm />)
      
      // Should apply mobile-responsive classes
      const form = screen.getByRole('form')
      expect(form).toHaveClass('mobile-responsive')
    })

    it('should handle tablet viewport', () => {
      // Mock tablet viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 768,
      })
      
      render(<AgentOrchestrator />)
      
      // Should use tablet layout
      const container = screen.getByTestId('agent-orchestrator')
      expect(container).toHaveClass('tablet-layout')
    })
  })

  describe('Accessibility Integration', () => {
    it('should be keyboard navigable', async () => {
      const user = userEvent.setup()
      
      render(<VideoRequestForm />)
      
      // Should be able to navigate form with keyboard
      await user.tab()
      expect(screen.getByLabelText(/video prompt/i)).toHaveFocus()
      
      await user.tab()
      expect(screen.getByLabelText(/video style/i)).toHaveFocus()
      
      await user.tab()
      expect(screen.getByLabelText(/duration/i)).toHaveFocus()
    })

    it('should have proper ARIA labels and roles', () => {
      render(<RealTimeProgress />)
      
      // Check ARIA attributes
      expect(screen.getByRole('progressbar')).toBeInTheDocument()
      expect(screen.getByLabelText(/progress/i)).toBeInTheDocument()
      
      // Check live regions for screen readers
      expect(screen.getByRole('status')).toBeInTheDocument()
    })

    it('should support screen readers', () => {
      const mockTask = {
        id: 'test-task-123',
        title: 'Test Video Generation',
        status: 'processing',
        progress: 45
      }
      
      mockStore.activeTask = mockTask
      
      render(<RealTimeProgress />)
      
      // Should have screen reader announcements
      expect(screen.getByText(/video generation in progress/i)).toBeInTheDocument()
      expect(screen.getByText(/45 percent complete/i)).toBeInTheDocument()
    })
  })
})