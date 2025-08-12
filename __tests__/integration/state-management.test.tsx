/**
 * State Management Integration Tests
 * 
 * Tests Zustand store behavior, state synchronization across components,
 * persistence, concurrent updates, and state consistency.
 */
import React from 'react'
import { render, screen, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useAppStore } from '../../src/store/useAppStore'
import { VideoRequest, Agent, GenerationResult, Notification } from '../../src/types'

// Test components that use the store
const StoreTestComponent = () => {
  const store = useAppStore()
  
  return (
    <div data-testid="store-test">
      <div data-testid="current-step">{store.ui.currentStep}</div>
      <div data-testid="loading">{store.ui.isLoading.toString()}</div>
      <div data-testid="sidebar-collapsed">{store.ui.sidebarCollapsed.toString()}</div>
      <div data-testid="ws-connected">{store.wsConnected.toString()}</div>
      <div data-testid="agents-count">{store.agents.length}</div>
      <div data-testid="results-count">{store.results.length}</div>
      <div data-testid="notifications-count">{store.ui.notifications.length}</div>
      
      <button onClick={() => store.setCurrentStep('processing')}>
        Set Processing
      </button>
      <button onClick={() => store.setLoading(true)}>
        Set Loading
      </button>
      <button onClick={() => store.setSidebarCollapsed(true)}>
        Collapse Sidebar
      </button>
      <button onClick={() => store.setWSConnected(true)}>
        Connect WS
      </button>
      <button onClick={() => store.addNotification({
        type: 'success',
        title: 'Test Notification',
        message: 'Test message'
      })}>
        Add Notification
      </button>
      <button onClick={() => store.reset()}>
        Reset Store
      </button>
    </div>
  )
}

const AgentTestComponent = () => {
  const { agents, updateAgent } = useAppStore()
  
  return (
    <div data-testid="agent-test">
      {agents.map(agent => (
        <div key={agent.id} data-testid={`agent-${agent.id}`}>
          <span data-testid={`agent-${agent.id}-status`}>{agent.status}</span>
          <span data-testid={`agent-${agent.id}-progress`}>{agent.progress}</span>
          <button onClick={() => updateAgent(agent.id, { status: 'working', progress: 50 })}>
            Update Agent
          </button>
        </div>
      ))}
    </div>
  )
}

const MultiComponentStoreTest = () => {
  return (
    <div>
      <StoreTestComponent />
      <AgentTestComponent />
    </div>
  )
}

describe('State Management Integration Tests', () => {
  let user: ReturnType<typeof userEvent.setup>

  beforeEach(() => {
    user = userEvent.setup()
    // Reset store to initial state before each test
    const store = useAppStore.getState()
    store.reset()
  })

  afterEach(() => {
    // Clean up after each test
    const store = useAppStore.getState()
    store.reset()
  })

  describe('Basic Store Operations', () => {
    it('should initialize with correct default state', () => {
      render(<StoreTestComponent />)

      expect(screen.getByTestId('current-step')).toHaveTextContent('input')
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
      expect(screen.getByTestId('sidebar-collapsed')).toHaveTextContent('false')
      expect(screen.getByTestId('ws-connected')).toHaveTextContent('false')
      expect(screen.getByTestId('agents-count')).toHaveTextContent('6') // Default agents
      expect(screen.getByTestId('results-count')).toHaveTextContent('0')
      expect(screen.getByTestId('notifications-count')).toHaveTextContent('0')
    })

    it('should update UI state correctly', async () => {
      render(<StoreTestComponent />)

      // Test current step update
      await user.click(screen.getByText('Set Processing'))
      expect(screen.getByTestId('current-step')).toHaveTextContent('processing')

      // Test loading state update
      await user.click(screen.getByText('Set Loading'))
      expect(screen.getByTestId('loading')).toHaveTextContent('true')

      // Test sidebar state update
      await user.click(screen.getByText('Collapse Sidebar'))
      expect(screen.getByTestId('sidebar-collapsed')).toHaveTextContent('true')

      // Test WebSocket connection state
      await user.click(screen.getByText('Connect WS'))
      expect(screen.getByTestId('ws-connected')).toHaveTextContent('true')
    })

    it('should handle notifications correctly', async () => {
      render(<StoreTestComponent />)

      expect(screen.getByTestId('notifications-count')).toHaveTextContent('0')

      // Add notification
      await user.click(screen.getByText('Add Notification'))
      expect(screen.getByTestId('notifications-count')).toHaveTextContent('1')

      // Check notification content
      const store = useAppStore.getState()
      const notification = store.ui.notifications[0]
      expect(notification.type).toBe('success')
      expect(notification.title).toBe('Test Notification')
      expect(notification.message).toBe('Test message')
      expect(notification.id).toBeTruthy()
      expect(notification.timestamp).toBeInstanceOf(Date)
    })

    it('should reset store to initial state', async () => {
      render(<StoreTestComponent />)

      // Make some changes
      await user.click(screen.getByText('Set Processing'))
      await user.click(screen.getByText('Set Loading'))
      await user.click(screen.getByText('Add Notification'))

      // Verify changes
      expect(screen.getByTestId('current-step')).toHaveTextContent('processing')
      expect(screen.getByTestId('loading')).toHaveTextContent('true')
      expect(screen.getByTestId('notifications-count')).toHaveTextContent('1')

      // Reset store
      await user.click(screen.getByText('Reset Store'))

      // Verify reset
      expect(screen.getByTestId('current-step')).toHaveTextContent('input')
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
      expect(screen.getByTestId('notifications-count')).toHaveTextContent('0')
    })
  })

  describe('Agent Management', () => {
    it('should update agent state correctly', async () => {
      render(<AgentTestComponent />)

      // Find first agent
      const firstAgent = screen.getByTestId('agent-concept-generator')
      expect(firstAgent).toBeInTheDocument()

      // Check initial state
      expect(screen.getByTestId('agent-concept-generator-status')).toHaveTextContent('idle')
      expect(screen.getByTestId('agent-concept-generator-progress')).toHaveTextContent('0')

      // Update agent
      const updateButton = firstAgent.querySelector('button')
      await user.click(updateButton!)

      // Check updated state
      expect(screen.getByTestId('agent-concept-generator-status')).toHaveTextContent('working')
      expect(screen.getByTestId('agent-concept-generator-progress')).toHaveTextContent('50')
    })

    it('should handle multiple agent updates independently', async () => {
      render(<AgentTestComponent />)

      const conceptAgent = screen.getByTestId('agent-concept-generator')
      const scriptAgent = screen.getByTestId('agent-script-writer')

      // Update concept generator
      const conceptButton = conceptAgent.querySelector('button')
      await user.click(conceptButton!)

      // Update script writer with different values
      act(() => {
        const store = useAppStore.getState()
        store.updateAgent('script-writer', { status: 'completed', progress: 100 })
      })

      // Verify independent updates
      expect(screen.getByTestId('agent-concept-generator-status')).toHaveTextContent('working')
      expect(screen.getByTestId('agent-concept-generator-progress')).toHaveTextContent('50')
      expect(screen.getByTestId('agent-script-writer-status')).toHaveTextContent('completed')
      expect(screen.getByTestId('agent-script-writer-progress')).toHaveTextContent('100')
    })

    it('should handle non-existent agent updates gracefully', () => {
      render(<AgentTestComponent />)

      const store = useAppStore.getState()
      const initialAgents = [...store.agents]

      // Try to update non-existent agent
      act(() => {
        store.updateAgent('non-existent-agent', { status: 'working' })
      })

      // Agents should remain unchanged
      const updatedAgents = useAppStore.getState().agents
      expect(updatedAgents).toEqual(initialAgents)
    })
  })

  describe('Results Management', () => {
    it('should add and update results correctly', () => {
      const TestResultComponent = () => {
        const { results, addResult, updateResult } = useAppStore()
        
        return (
          <div>
            <div data-testid="results-count">{results.length}</div>
            {results.map(result => (
              <div key={result.id} data-testid={`result-${result.id}`}>
                <span data-testid={`result-${result.id}-status`}>{result.status}</span>
              </div>
            ))}
            <button onClick={() => addResult({
              id: 'test-result-1',
              requestId: 'test-request',
              type: 'concept',
              status: 'completed',
              data: { concept: 'Test concept' },
              createdAt: new Date(),
              agent: 'concept-generator',
              confidence: 0.9
            })}>
              Add Result
            </button>
            <button onClick={() => updateResult('test-result-1', { status: 'processing' })}>
              Update Result
            </button>
          </div>
        )
      }

      render(<TestResultComponent />)

      expect(screen.getByTestId('results-count')).toHaveTextContent('0')

      // Add result
      const addButton = screen.getByText('Add Result')
      act(() => {
        addButton.click()
      })

      expect(screen.getByTestId('results-count')).toHaveTextContent('1')
      expect(screen.getByTestId('result-test-result-1-status')).toHaveTextContent('completed')

      // Update result
      const updateButton = screen.getByText('Update Result')
      act(() => {
        updateButton.click()
      })

      expect(screen.getByTestId('result-test-result-1-status')).toHaveTextContent('processing')
    })
  })

  describe('Cross-Component State Synchronization', () => {
    it('should synchronize state across multiple components', async () => {
      render(<MultiComponentStoreTest />)

      // Update state from one component
      await user.click(screen.getByText('Set Processing'))

      // Verify state is reflected in both components
      const stepElements = screen.getAllByTestId('current-step')
      stepElements.forEach(element => {
        expect(element).toHaveTextContent('processing')
      })

      // Update agent from agent component
      const firstAgentUpdateButton = screen.getAllByText('Update Agent')[0]
      await user.click(firstAgentUpdateButton)

      // Verify agent state is updated
      expect(screen.getByTestId('agent-concept-generator-status')).toHaveTextContent('working')
    })

    it('should handle rapid state updates without race conditions', () => {
      const RapidUpdateTest = () => {
        const { agents, updateAgent } = useAppStore()
        
        React.useEffect(() => {
          // Simulate rapid updates
          for (let i = 0; i < 10; i++) {
            setTimeout(() => {
              updateAgent('concept-generator', { 
                progress: i * 10,
                status: i === 9 ? 'completed' : 'working'
              })
            }, i * 10)
          }
        }, [updateAgent])

        const conceptAgent = agents.find(a => a.id === 'concept-generator')
        
        return (
          <div>
            <div data-testid="progress">{conceptAgent?.progress || 0}</div>
            <div data-testid="status">{conceptAgent?.status || 'idle'}</div>
          </div>
        )
      }

      render(<RapidUpdateTest />)

      // Wait for all updates to complete
      act(() => {
        jest.advanceTimersByTime(200)
      })

      // Should have final values
      expect(screen.getByTestId('progress')).toHaveTextContent('90')
      expect(screen.getByTestId('status')).toHaveTextContent('completed')
    })
  })

  describe('Notification Auto-Close Behavior', () => {
    it('should auto-remove notifications with autoClose timeout', async () => {
      const NotificationTest = () => {
        const { ui, addNotification, removeNotification } = useAppStore()
        
        return (
          <div>
            <div data-testid="notifications-count">{ui.notifications.length}</div>
            <button onClick={() => addNotification({
              type: 'info',
              title: 'Auto Close Test',
              message: 'This will auto close',
              autoClose: 100 // 100ms for testing
            })}>
              Add Auto-Close Notification
            </button>
            <button onClick={() => addNotification({
              type: 'error',
              title: 'Persistent Test',
              message: 'This will not auto close'
              // No autoClose property
            })}>
              Add Persistent Notification
            </button>
          </div>
        )
      }

      jest.useFakeTimers()
      render(<NotificationTest />)

      expect(screen.getByTestId('notifications-count')).toHaveTextContent('0')

      // Add auto-close notification
      await user.click(screen.getByText('Add Auto-Close Notification'))
      expect(screen.getByTestId('notifications-count')).toHaveTextContent('1')

      // Add persistent notification
      await user.click(screen.getByText('Add Persistent Notification'))
      expect(screen.getByTestId('notifications-count')).toHaveTextContent('2')

      // Fast-forward time to trigger auto-close
      act(() => {
        jest.advanceTimersByTime(150)
      })

      // Only persistent notification should remain
      expect(screen.getByTestId('notifications-count')).toHaveTextContent('1')

      const remainingNotification = useAppStore.getState().ui.notifications[0]
      expect(remainingNotification.title).toBe('Persistent Test')

      jest.useRealTimers()
    })
  })

  describe('State Persistence and Hydration', () => {
    it('should handle store subscription correctly', () => {
      let subscriptionCallCount = 0
      let lastState: any = null

      const unsubscribe = useAppStore.subscribe((state) => {
        subscriptionCallCount++
        lastState = state
      })

      const TestComponent = () => {
        const { setLoading } = useAppStore()
        
        return (
          <button onClick={() => setLoading(true)}>
            Trigger Update
          </button>
        )
      }

      render(<TestComponent />)

      expect(subscriptionCallCount).toBe(0)

      // Trigger state update
      const button = screen.getByText('Trigger Update')
      act(() => {
        button.click()
      })

      expect(subscriptionCallCount).toBe(1)
      expect(lastState?.ui.isLoading).toBe(true)

      unsubscribe()
    })

    it('should handle partial state updates correctly', () => {
      const store = useAppStore.getState()
      const initialAgents = [...store.agents]

      // Update only specific agent properties
      act(() => {
        store.updateAgent('concept-generator', { progress: 75 })
      })

      const updatedStore = useAppStore.getState()
      const updatedAgent = updatedStore.agents.find(a => a.id === 'concept-generator')
      
      // Should update only the specified property
      expect(updatedAgent?.progress).toBe(75)
      expect(updatedAgent?.status).toBe('idle') // Should remain unchanged
      expect(updatedAgent?.name).toBe('Concept Generator') // Should remain unchanged

      // Other agents should be unchanged
      const otherAgents = updatedStore.agents.filter(a => a.id !== 'concept-generator')
      const originalOtherAgents = initialAgents.filter(a => a.id !== 'concept-generator')
      expect(otherAgents).toEqual(originalOtherAgents)
    })
  })

  describe('Concurrent State Management', () => {
    it('should handle concurrent updates from multiple sources', async () => {
      const ConcurrentUpdateTest = () => {
        const { agents, updateAgent, addNotification } = useAppStore()
        
        const handleConcurrentUpdates = () => {
          // Simulate concurrent updates from different sources
          Promise.all([
            Promise.resolve().then(() => updateAgent('concept-generator', { progress: 25 })),
            Promise.resolve().then(() => updateAgent('script-writer', { progress: 30 })),
            Promise.resolve().then(() => addNotification({
              type: 'info',
              title: 'Update 1',
              message: 'First update'
            })),
            Promise.resolve().then(() => updateAgent('concept-generator', { progress: 50 })),
            Promise.resolve().then(() => addNotification({
              type: 'info', 
              title: 'Update 2',
              message: 'Second update'
            }))
          ])
        }

        const conceptAgent = agents.find(a => a.id === 'concept-generator')
        const scriptAgent = agents.find(a => a.id === 'script-writer')
        
        return (
          <div>
            <div data-testid="concept-progress">{conceptAgent?.progress}</div>
            <div data-testid="script-progress">{scriptAgent?.progress}</div>
            <button onClick={handleConcurrentUpdates}>
              Trigger Concurrent Updates
            </button>
          </div>
        )
      }

      render(<ConcurrentUpdateTest />)

      const button = screen.getByText('Trigger Concurrent Updates')
      
      await act(async () => {
        button.click()
        // Allow all promises to resolve
        await new Promise(resolve => setTimeout(resolve, 0))
      })

      // Should have final values from all updates
      expect(screen.getByTestId('concept-progress')).toHaveTextContent('50')
      expect(screen.getByTestId('script-progress')).toHaveTextContent('30')
      
      const store = useAppStore.getState()
      expect(store.ui.notifications).toHaveLength(2)
    })

    it('should maintain state consistency during complex workflows', async () => {
      const WorkflowTest = () => {
        const store = useAppStore()
        
        const simulateVideoGenerationWorkflow = async () => {
          // Step 1: Start processing
          store.setCurrentStep('processing')
          store.setLoading(true)
          
          // Step 2: Update agents progressively
          store.updateAgent('concept-generator', { status: 'working', progress: 25 })
          await new Promise(resolve => setTimeout(resolve, 10))
          
          store.updateAgent('concept-generator', { status: 'working', progress: 100 })
          store.updateAgent('script-writer', { status: 'working', progress: 30 })
          await new Promise(resolve => setTimeout(resolve, 10))
          
          // Step 3: Complete first agent, continue with others
          store.updateAgent('concept-generator', { status: 'completed', progress: 100 })
          store.addResult({
            id: 'concept-result',
            requestId: 'test-workflow',
            type: 'concept',
            status: 'completed',
            data: { concept: 'Generated concept' },
            createdAt: new Date(),
            agent: 'concept-generator',
            confidence: 0.95
          })
          
          // Step 4: Complete workflow
          store.updateAgent('script-writer', { status: 'completed', progress: 100 })
          store.setCurrentStep('review')
          store.setLoading(false)
          
          store.addNotification({
            type: 'success',
            title: 'Video Generated',
            message: 'Your video is ready for review'
          })
        }

        return (
          <div>
            <div data-testid="current-step">{store.ui.currentStep}</div>
            <div data-testid="loading">{store.ui.isLoading.toString()}</div>
            <div data-testid="results-count">{store.results.length}</div>
            <div data-testid="notifications-count">{store.ui.notifications.length}</div>
            <div data-testid="completed-agents">
              {store.agents.filter(a => a.status === 'completed').length}
            </div>
            <button onClick={simulateVideoGenerationWorkflow}>
              Start Workflow
            </button>
          </div>
        )
      }

      render(<WorkflowTest />)

      const button = screen.getByText('Start Workflow')
      
      await act(async () => {
        button.click()
        // Wait for all async operations
        await new Promise(resolve => setTimeout(resolve, 50))
      })

      // Verify final state consistency
      expect(screen.getByTestId('current-step')).toHaveTextContent('review')
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
      expect(screen.getByTestId('results-count')).toHaveTextContent('1')
      expect(screen.getByTestId('notifications-count')).toHaveTextContent('1')
      expect(screen.getByTestId('completed-agents')).toHaveTextContent('2')
    })
  })

  describe('Error Handling in State Management', () => {
    it('should handle invalid state updates gracefully', () => {
      const store = useAppStore.getState()
      
      // Try to update with invalid data
      expect(() => {
        store.updateAgent('concept-generator', { progress: -10 })
      }).not.toThrow()
      
      expect(() => {
        store.updateAgent('concept-generator', { progress: 150 })
      }).not.toThrow()
      
      // State should handle invalid values appropriately
      const agent = store.agents.find(a => a.id === 'concept-generator')
      expect(agent?.progress).toBeGreaterThanOrEqual(0)
      expect(agent?.progress).toBeLessThanOrEqual(100)
    })

    it('should maintain referential equality for unchanged nested objects', () => {
      const store = useAppStore.getState()
      const initialUI = store.ui
      const initialAgents = store.agents
      
      // Update unrelated state
      act(() => {
        store.setWSConnected(true)
      })
      
      const updatedStore = useAppStore.getState()
      
      // UI object should be new (because it's the container for wsConnected)
      // but agents should maintain referential equality
      expect(updatedStore.agents).toBe(initialAgents)
      expect(updatedStore.ui).not.toBe(initialUI)
    })
  })
})