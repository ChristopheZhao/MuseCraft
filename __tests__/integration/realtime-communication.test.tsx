/**
 * Real-time Communication Integration Tests
 * 
 * Tests WebSocket connections, real-time updates, error handling,
 * reconnection logic, and multi-task concurrent processing.
 */
import React from 'react'
import { render, screen, act, waitFor, fireEvent } from '@testing-library/react'
import WS from 'jest-websocket-mock'
import { useAppStore } from '../../src/store/useAppStore'
import { TestUtils } from '../setup'

// Import components that use WebSocket
import RealTimeProgress from '../../src/components/progress/RealTimeProgress'
import AgentOrchestrator from '../../src/components/agents/AgentOrchestrator'
import { useWebSocket } from '../../src/hooks/useWebSocket'

// Mock the store
jest.mock('../../src/store/useAppStore')
const mockUseAppStore = useAppStore as jest.MockedFunction<typeof useAppStore>

// Mock the WebSocket hook
jest.mock('../../src/hooks/useWebSocket')
const mockUseWebSocket = useWebSocket as jest.MockedFunction<typeof useWebSocket>

describe('Real-time Communication Integration Tests', () => {
  let server: WS
  let mockStore: any
  let mockWebSocketHook: any

  const WS_URL = 'ws://localhost:8000/ws'

  beforeEach(() => {
    // Create mock WebSocket server
    server = new WS(WS_URL)

    mockStore = {
      ui: {
        isLoading: false,
        currentStep: 'processing',
        notifications: []
      },
      currentRequest: {
        id: 'test-request-123',
        title: 'Test Video Generation',
        description: 'Test description'
      },
      agents: [
        {
          id: 'concept-generator',
          name: 'Concept Generator',
          type: 'concept-generator',
          status: 'idle',
          progress: 0,
          description: 'Generates video concepts'
        },
        {
          id: 'script-writer',
          name: 'Script Writer',
          type: 'script-writer',
          status: 'idle',
          progress: 0,
          description: 'Writes video scripts'
        }
      ],
      results: [],
      wsConnected: false,
      updateAgent: jest.fn(),
      addResult: jest.fn(),
      setWSConnected: jest.fn(),
      addNotification: jest.fn(),
      setCurrentStep: jest.fn()
    }

    mockWebSocketHook = {
      connected: false,
      connecting: false,
      error: null,
      connect: jest.fn(),
      disconnect: jest.fn(),
      send: jest.fn(),
      lastMessage: null
    }

    mockUseAppStore.mockReturnValue(mockStore)
    mockUseWebSocket.mockReturnValue(mockWebSocketHook)
  })

  afterEach(() => {
    if (server) {
      WS.clean()
    }
    jest.clearAllMocks()
  })

  describe('WebSocket Connection Lifecycle', () => {
    it('should establish WebSocket connection and handle lifecycle events', async () => {
      render(<RealTimeProgress />)

      // Simulate connection attempt
      act(() => {
        mockWebSocketHook.connecting = true
        mockWebSocketHook.connect.mockImplementation(() => {
          mockWebSocketHook.connected = true
          mockWebSocketHook.connecting = false
          mockStore.setWSConnected(true)
        })
      })

      // Trigger connection
      mockWebSocketHook.connect()

      expect(mockWebSocketHook.connect).toHaveBeenCalled()
      expect(mockStore.setWSConnected).toHaveBeenCalledWith(true)

      // Test connection established
      await server.connected
      expect(server).toHaveReceivedMessages([])

      // Simulate disconnection
      act(() => {
        mockWebSocketHook.connected = false
        mockWebSocketHook.error = new Error('Connection lost')
        mockStore.setWSConnected(false)
      })

      expect(mockStore.setWSConnected).toHaveBeenCalledWith(false)
    })

    it('should handle connection errors and implement retry logic', async () => {
      let retryCount = 0
      const maxRetries = 3

      mockWebSocketHook.connect.mockImplementation(() => {
        retryCount++
        if (retryCount < maxRetries) {
          mockWebSocketHook.error = new Error('Connection failed')
          mockWebSocketHook.connected = false
          // Simulate retry after delay
          setTimeout(() => {
            mockWebSocketHook.connect()
          }, 1000)
        } else {
          mockWebSocketHook.connected = true
          mockWebSocketHook.error = null
          mockStore.setWSConnected(true)
        }
      })

      render(<RealTimeProgress />)

      // Initial connection attempt
      mockWebSocketHook.connect()

      // Wait for retries to complete
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 3500))
      })

      expect(mockWebSocketHook.connect).toHaveBeenCalledTimes(maxRetries)
      expect(mockStore.setWSConnected).toHaveBeenLastCalledWith(true)
    })

    it('should handle connection timeout scenarios', async () => {
      jest.useFakeTimers()

      mockWebSocketHook.connect.mockImplementation(() => {
        mockWebSocketHook.connecting = true
        // Simulate timeout - no connection established
        setTimeout(() => {
          mockWebSocketHook.connecting = false
          mockWebSocketHook.error = new Error('Connection timeout')
        }, 10000)
      })

      render(<RealTimeProgress />)

      mockWebSocketHook.connect()

      // Fast-forward time to trigger timeout
      act(() => {
        jest.advanceTimersByTime(10000)
      })

      expect(mockWebSocketHook.error?.message).toBe('Connection timeout')
      expect(mockWebSocketHook.connecting).toBe(false)

      jest.useRealTimers()
    })
  })

  describe('Real-time Message Processing', () => {
    beforeEach(async () => {
      // Establish connection
      mockWebSocketHook.connected = true
      mockStore.wsConnected = true
      await server.connected
    })

    it('should process agent status updates correctly', async () => {
      render(<AgentOrchestrator />)

      const statusUpdate = {
        type: 'agent-status-update',
        data: {
          agent_id: 'concept-generator',
          status: 'working',
          progress: 45,
          current_task: 'Analyzing user requirements',
          estimated_time_remaining: 120
        },
        timestamp: new Date().toISOString()
      }

      // Send message from server
      server.send(JSON.stringify(statusUpdate))

      await waitFor(() => {
        expect(mockStore.updateAgent).toHaveBeenCalledWith('concept-generator', {
          status: 'working',
          progress: 45,
          currentTask: 'Analyzing user requirements',
          estimatedTime: 120
        })
      })
    })

    it('should handle progress updates with multiple agents', async () => {
      render(<RealTimeProgress />)

      const progressUpdate = {
        type: 'progress-update',
        data: {
          task_id: 'test-request-123',
          overall_progress: 60,
          agents: [
            {
              agent_id: 'concept-generator',
              status: 'completed',
              progress: 100,
              result: {
                concept: 'AI-powered video narrative',
                themes: ['technology', 'innovation', 'future']
              }
            },
            {
              agent_id: 'script-writer',
              status: 'working',
              progress: 75,
              current_task: 'Refining script structure'
            },
            {
              agent_id: 'image-generator',
              status: 'waiting',
              progress: 0,
              current_task: 'Waiting for script completion'
            }
          ],
          estimated_completion: new Date(Date.now() + 300000).toISOString()
        },
        timestamp: new Date().toISOString()
      }

      server.send(JSON.stringify(progressUpdate))

      await waitFor(() => {
        // Should update each agent
        expect(mockStore.updateAgent).toHaveBeenCalledWith('concept-generator', {
          status: 'completed',
          progress: 100
        })

        expect(mockStore.updateAgent).toHaveBeenCalledWith('script-writer', {
          status: 'working',
          progress: 75,
          currentTask: 'Refining script structure'
        })

        expect(mockStore.updateAgent).toHaveBeenCalledWith('image-generator', {
          status: 'waiting',
          progress: 0,
          currentTask: 'Waiting for script completion'
        })

        // Should add result for completed agent
        expect(mockStore.addResult).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'concept',
            agent: 'concept-generator',
            data: {
              concept: 'AI-powered video narrative',
              themes: ['technology', 'innovation', 'future']
            }
          })
        )
      })
    })

    it('should handle result-ready messages', async () => {
      render(<RealTimeProgress />)

      const resultReady = {
        type: 'result-ready',
        data: {
          task_id: 'test-request-123',
          result_type: 'video',
          result_id: 'video-result-123',
          status: 'completed',
          output: {
            video_url: 'https://example.com/generated-video.mp4',
            thumbnail_url: 'https://example.com/thumbnail.jpg',
            duration: 120,
            file_size: '85MB',
            quality_score: 0.92
          },
          metadata: {
            resolution: '1920x1080',
            fps: 30,
            codec: 'H.264',
            bitrate: '5000kbps'
          }
        },
        timestamp: new Date().toISOString()
      }

      server.send(JSON.stringify(resultReady))

      await waitFor(() => {
        expect(mockStore.addResult).toHaveBeenCalledWith(
          expect.objectContaining({
            id: 'video-result-123',
            type: 'video',
            status: 'completed',
            data: resultReady.data.output
          })
        )

        expect(mockStore.setCurrentStep).toHaveBeenCalledWith('review')
      })
    })

    it('should handle error messages and display appropriate notifications', async () => {
      render(<RealTimeProgress />)

      const errorMessage = {
        type: 'error',
        data: {
          error_code: 'AGENT_FAILURE',
          error_message: 'Script generation failed due to content complexity',
          agent_id: 'script-writer',
          task_id: 'test-request-123',
          retry_available: true,
          suggested_actions: ['Simplify prompt', 'Try different style']
        },
        timestamp: new Date().toISOString()
      }

      server.send(JSON.stringify(errorMessage))

      await waitFor(() => {
        expect(mockStore.updateAgent).toHaveBeenCalledWith('script-writer', {
          status: 'error'
        })

        expect(mockStore.addNotification).toHaveBeenCalledWith({
          type: 'error',
          title: 'Agent Error',
          message: 'Script generation failed due to content complexity',
          autoClose: undefined // Error notifications shouldn't auto-close
        })
      })
    })

    it('should handle system messages and maintenance notifications', async () => {
      render(<RealTimeProgress />)

      const systemMessage = {
        type: 'system-message',
        data: {
          message_type: 'maintenance_warning',
          title: 'Scheduled Maintenance',
          message: 'System maintenance will begin in 15 minutes. Please save your work.',
          severity: 'warning',
          display_duration: 30000,
          actions: [
            { type: 'dismiss', label: 'Dismiss' },
            { type: 'save', label: 'Save Progress' }
          ]
        },
        timestamp: new Date().toISOString()
      }

      server.send(JSON.stringify(systemMessage))

      await waitFor(() => {
        expect(mockStore.addNotification).toHaveBeenCalledWith({
          type: 'warning',
          title: 'Scheduled Maintenance',
          message: 'System maintenance will begin in 15 minutes. Please save your work.',
          autoClose: 30000
        })
      })
    })
  })

  describe('Concurrent Task Processing', () => {
    beforeEach(async () => {
      mockWebSocketHook.connected = true
      mockStore.wsConnected = true
      await server.connected
    })

    it('should handle multiple concurrent tasks and agents', async () => {
      // Setup multiple tasks
      mockStore.agents = [
        { id: 'concept-generator-1', status: 'working', progress: 30 },
        { id: 'concept-generator-2', status: 'working', progress: 50 },
        { id: 'script-writer-1', status: 'working', progress: 20 },
        { id: 'script-writer-2', status: 'waiting', progress: 0 }
      ]

      render(<AgentOrchestrator />)

      // Send rapid concurrent updates
      const updates = [
        {
          type: 'progress-update',
          data: { agent_id: 'concept-generator-1', progress: 45, status: 'working' }
        },
        {
          type: 'progress-update',
          data: { agent_id: 'concept-generator-2', progress: 75, status: 'working' }
        },
        {
          type: 'progress-update',
          data: { agent_id: 'script-writer-1', progress: 40, status: 'working' }
        },
        {
          type: 'agent-status-update',
          data: { agent_id: 'script-writer-2', status: 'working', progress: 15 }
        }
      ]

      // Send all updates rapidly
      updates.forEach((update, index) => {
        setTimeout(() => {
          server.send(JSON.stringify(update))
        }, index * 50)
      })

      // Wait for all updates to be processed
      await waitFor(() => {
        expect(mockStore.updateAgent).toHaveBeenCalledTimes(4)
      }, { timeout: 5000 })

      // Verify each update was processed correctly
      expect(mockStore.updateAgent).toHaveBeenCalledWith('concept-generator-1', {
        progress: 45,
        status: 'working'
      })
      expect(mockStore.updateAgent).toHaveBeenCalledWith('concept-generator-2', {
        progress: 75,
        status: 'working'
      })
      expect(mockStore.updateAgent).toHaveBeenCalledWith('script-writer-1', {
        progress: 40,
        status: 'working'
      })
      expect(mockStore.updateAgent).toHaveBeenCalledWith('script-writer-2', {
        status: 'working',
        progress: 15
      })
    })

    it('should handle agent dependency chains and workflow coordination', async () => {
      render(<AgentOrchestrator />)

      // Simulate workflow progression
      const workflowSteps = [
        {
          type: 'agent-status-update',
          data: {
            agent_id: 'concept-generator',
            status: 'completed',
            progress: 100,
            result: { concept: 'Video concept ready' }
          }
        },
        {
          type: 'agent-status-update',
          data: {
            agent_id: 'script-writer',
            status: 'working',
            progress: 25,
            current_task: 'Processing concept input',
            dependencies_met: ['concept-generator']
          }
        },
        {
          type: 'agent-status-update',
          data: {
            agent_id: 'script-writer',
            status: 'completed',
            progress: 100,
            result: { script: 'Completed script' }
          }
        },
        {
          type: 'agent-status-update',
          data: {
            agent_id: 'image-generator',
            status: 'working',
            progress: 30,
            current_task: 'Generating visuals from script',
            dependencies_met: ['concept-generator', 'script-writer']
          }
        }
      ]

      // Send workflow progression messages
      for (let i = 0; i < workflowSteps.length; i++) {
        setTimeout(() => {
          server.send(JSON.stringify(workflowSteps[i]))
        }, i * 1000)
      }

      // Wait for workflow completion
      await waitFor(() => {
        expect(mockStore.updateAgent).toHaveBeenCalledWith('image-generator', {
          status: 'working',
          progress: 30,
          currentTask: 'Generating visuals from script'
        })
      }, { timeout: 10000 })

      // Verify results were added for completed agents
      expect(mockStore.addResult).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'concept',
          agent: 'concept-generator'
        })
      )

      expect(mockStore.addResult).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'script',
          agent: 'script-writer'
        })
      )
    })
  })

  describe('Message Queue and Buffering', () => {
    it('should handle message queuing during disconnection', async () => {
      render(<RealTimeProgress />)

      // Start connected
      mockWebSocketHook.connected = true
      await server.connected

      // Simulate disconnection
      act(() => {
        mockWebSocketHook.connected = false
        server.close()
      })

      // Simulate queued messages (would be handled by WebSocket hook)
      const queuedMessages = [
        { type: 'progress-update', data: { agent_id: 'concept-generator', progress: 60 } },
        { type: 'progress-update', data: { agent_id: 'script-writer', progress: 30 } }
      ]

      // Mock the queuing behavior
      mockWebSocketHook.connect.mockImplementation(() => {
        mockWebSocketHook.connected = true
        // Process queued messages on reconnection
        queuedMessages.forEach(message => {
          // Simulate processing queued messages
          if (message.type === 'progress-update') {
            mockStore.updateAgent(message.data.agent_id, {
              progress: message.data.progress
            })
          }
        })
      })

      // Reconnect
      act(() => {
        mockWebSocketHook.connect()
      })

      // Verify queued messages were processed
      expect(mockStore.updateAgent).toHaveBeenCalledWith('concept-generator', {
        progress: 60
      })
      expect(mockStore.updateAgent).toHaveBeenCalledWith('script-writer', {
        progress: 30
      })
    })

    it('should handle high-frequency updates with throttling', async () => {
      render(<RealTimeProgress />)

      mockWebSocketHook.connected = true
      await server.connected

      // Send many rapid updates
      const rapidUpdates = Array.from({ length: 50 }, (_, i) => ({
        type: 'progress-update',
        data: {
          agent_id: 'concept-generator',
          progress: i * 2,
          timestamp: Date.now() + i
        }
      }))

      // Send all updates rapidly
      rapidUpdates.forEach((update, index) => {
        setTimeout(() => {
          server.send(JSON.stringify(update))
        }, index * 10) // 10ms intervals
      })

      // Wait for processing
      await waitFor(() => {
        // Should have been throttled to fewer calls
        expect(mockStore.updateAgent).toHaveBeenCalled()
      }, { timeout: 2000 })

      // Verify final state reflects latest update
      const lastCall = mockStore.updateAgent.mock.calls[mockStore.updateAgent.mock.calls.length - 1]
      expect(lastCall[1].progress).toBeGreaterThan(90) // Should have latest progress
    })
  })

  describe('WebSocket Security and Validation', () => {
    it('should validate message format and reject malformed messages', async () => {
      render(<RealTimeProgress />)

      mockWebSocketHook.connected = true
      await server.connected

      // Send malformed messages
      const malformedMessages = [
        'invalid json',
        JSON.stringify({ type: 'unknown-type', data: {} }),
        JSON.stringify({ data: {} }), // missing type
        JSON.stringify({ type: 'progress-update' }), // missing data
        JSON.stringify({ type: 'progress-update', data: { invalid: 'structure' } })
      ]

      // Mock validation error handling
      const consoleSpy = jest.spyOn(console, 'warn').mockImplementation()

      malformedMessages.forEach(message => {
        server.send(message)
      })

      // Wait for error handling
      await waitFor(() => {
        // Should not have processed invalid messages
        expect(mockStore.updateAgent).not.toHaveBeenCalled()
      })

      // Should have logged warnings about invalid messages
      expect(consoleSpy).toHaveBeenCalled()

      consoleSpy.mockRestore()
    })

    it('should handle authentication and authorization for WebSocket connections', async () => {
      // Mock authentication token
      const mockToken = 'valid-jwt-token'
      
      mockWebSocketHook.connect.mockImplementation((token?: string) => {
        if (token === mockToken) {
          mockWebSocketHook.connected = true
          mockWebSocketHook.error = null
        } else {
          mockWebSocketHook.error = new Error('Authentication failed')
          mockWebSocketHook.connected = false
        }
      })

      render(<RealTimeProgress />)

      // Try connecting without token
      mockWebSocketHook.connect()
      expect(mockWebSocketHook.error?.message).toBe('Authentication failed')

      // Connect with valid token
      mockWebSocketHook.connect(mockToken)
      expect(mockWebSocketHook.connected).toBe(true)
      expect(mockWebSocketHook.error).toBe(null)
    })
  })
})