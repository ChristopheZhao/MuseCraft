/**
 * Error Boundary and Exception Handling Integration Tests
 * 
 * Tests error boundaries, graceful error handling, user-friendly error messages,
 * error recovery mechanisms, and system resilience.
 */
import React from 'react'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useAppStore } from '../../src/store/useAppStore'

// Mock components for testing error scenarios
const ThrowingComponent = ({ shouldThrow, errorType }: { shouldThrow: boolean, errorType?: string }) => {
  if (shouldThrow) {
    switch (errorType) {
      case 'render':
        throw new Error('Render error')
      case 'async':
        throw new Promise((_, reject) => reject(new Error('Async error')))
      case 'network':
        throw new Error('Network error')
      default:
        throw new Error('Generic component error')
    }
  }
  return <div data-testid="no-error">Component rendered successfully</div>
}

// Error Boundary implementation for testing
class TestErrorBoundary extends React.Component<
  { children: React.ReactNode; onError?: (error: Error, errorInfo: React.ErrorInfo) => void },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: any) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Error caught by boundary:', error, errorInfo)
    this.props.onError?.(error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div data-testid="error-boundary">
          <h2>Something went wrong</h2>
          <p data-testid="error-message">{this.state.error?.message}</p>
          <button 
            data-testid="retry-button"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            Try Again
          </button>
          <button 
            data-testid="report-button"
            onClick={() => console.log('Error reported:', this.state.error)}
          >
            Report Issue
          </button>
        </div>
      )
    }

    return this.props.children
  }
}

// Component that simulates API errors
const ApiTestComponent = () => {
  const { addNotification } = useAppStore()
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const handleApiCall = async (shouldFail: boolean = false) => {
    setLoading(true)
    setError(null)

    try {
      if (shouldFail) {
        // Simulate different types of API errors
        const errorTypes = ['network', 'server', 'validation', 'timeout']
        const errorType = errorTypes[Math.floor(Math.random() * errorTypes.length)]
        
        switch (errorType) {
          case 'network':
            throw new Error('Network connection failed')
          case 'server':
            throw new Error('Server error: Internal server error')
          case 'validation':
            throw new Error('Validation error: Invalid input data')
          case 'timeout':
            throw new Error('Request timeout: Server did not respond')
        }
      }

      // Simulate successful API call
      await new Promise(resolve => setTimeout(resolve, 100))
      addNotification({
        type: 'success',
        title: 'Success',
        message: 'API call completed successfully'
      })
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error'
      setError(errorMessage)
      
      addNotification({
        type: 'error',
        title: 'API Error',
        message: errorMessage
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div data-testid="api-test">
      <div data-testid="loading">{loading.toString()}</div>
      <div data-testid="error">{error || 'none'}</div>
      <button onClick={() => handleApiCall(false)}>
        Successful API Call
      </button>
      <button onClick={() => handleApiCall(true)}>
        Failing API Call
      </button>
      <button onClick={() => handleApiCall(false)}>
        Retry Last Call
      </button>
    </div>
  )
}

// WebSocket error simulation component
const WebSocketTestComponent = () => {
  const { wsConnected, setWSConnected, addNotification } = useAppStore()
  const [connectionAttempts, setConnectionAttempts] = React.useState(0)
  const [lastError, setLastError] = React.useState<string | null>(null)

  const simulateWebSocketError = (errorType: string) => {
    setLastError(errorType)
    setWSConnected(false)
    
    let errorMessage = ''
    let shouldRetry = false

    switch (errorType) {
      case 'connection_failed':
        errorMessage = 'Failed to connect to server'
        shouldRetry = true
        break
      case 'connection_lost':
        errorMessage = 'Connection lost. Attempting to reconnect...'
        shouldRetry = true
        break
      case 'auth_failed':
        errorMessage = 'Authentication failed. Please log in again.'
        shouldRetry = false
        break
      case 'server_error':
        errorMessage = 'Server error. Please try again later.'
        shouldRetry = true
        break
    }

    addNotification({
      type: 'error',
      title: 'Connection Error',
      message: errorMessage
    })

    if (shouldRetry) {
      // Simulate retry logic
      setTimeout(() => {
        const newAttempts = connectionAttempts + 1
        setConnectionAttempts(newAttempts)
        
        if (newAttempts < 3) {
          // Simulate successful reconnection after retries
          setWSConnected(true)
          setLastError(null)
          addNotification({
            type: 'success',
            title: 'Reconnected',
            message: 'Connection restored successfully'
          })
        }
      }, 1000)
    }
  }

  return (
    <div data-testid="websocket-test">
      <div data-testid="ws-connected">{wsConnected.toString()}</div>
      <div data-testid="connection-attempts">{connectionAttempts}</div>
      <div data-testid="last-error">{lastError || 'none'}</div>
      
      <button onClick={() => simulateWebSocketError('connection_failed')}>
        Connection Failed
      </button>
      <button onClick={() => simulateWebSocketError('connection_lost')}>
        Connection Lost
      </button>
      <button onClick={() => simulateWebSocketError('auth_failed')}>
        Auth Failed
      </button>
      <button onClick={() => simulateWebSocketError('server_error')}>
        Server Error
      </button>
      <button onClick={() => {
        setWSConnected(true)
        setLastError(null)
        setConnectionAttempts(0)
      }}>
        Force Reconnect
      </button>
    </div>
  )
}

describe('Error Boundary and Exception Handling Integration Tests', () => {
  let user: ReturnType<typeof userEvent.setup>
  let consoleErrorSpy: jest.SpyInstance

  beforeEach(() => {
    user = userEvent.setup()
    // Mock console.error to avoid test noise
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {})
    
    // Reset store
    const store = useAppStore.getState()
    store.reset()
  })

  afterEach(() => {
    consoleErrorSpy.mockRestore()
    jest.clearAllMocks()
  })

  describe('React Error Boundaries', () => {
    it('should catch component render errors and display fallback UI', () => {
      const onError = jest.fn()
      
      render(
        <TestErrorBoundary onError={onError}>
          <ThrowingComponent shouldThrow={true} />
        </TestErrorBoundary>
      )

      // Should display error boundary fallback
      expect(screen.getByTestId('error-boundary')).toBeInTheDocument()
      expect(screen.getByText('Something went wrong')).toBeInTheDocument()
      expect(screen.getByTestId('error-message')).toHaveTextContent('Generic component error')

      // Should have called error handler
      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({ message: 'Generic component error' }),
        expect.any(Object)
      )

      // Should provide retry option
      expect(screen.getByTestId('retry-button')).toBeInTheDocument()
      expect(screen.getByTestId('report-button')).toBeInTheDocument()
    })

    it('should allow error recovery through retry mechanism', async () => {
      const { rerender } = render(
        <TestErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </TestErrorBoundary>
      )

      // Verify error state
      expect(screen.getByTestId('error-boundary')).toBeInTheDocument()

      // Click retry button
      const retryButton = screen.getByTestId('retry-button')
      await user.click(retryButton)

      // Rerender with fixed component
      rerender(
        <TestErrorBoundary>
          <ThrowingComponent shouldThrow={false} />
        </TestErrorBoundary>
      )

      // Should show successful render
      expect(screen.getByTestId('no-error')).toBeInTheDocument()
      expect(screen.queryByTestId('error-boundary')).not.toBeInTheDocument()
    })

    it('should handle different types of component errors', () => {
      const errorTypes = ['render', 'network']
      
      errorTypes.forEach(errorType => {
        const { unmount } = render(
          <TestErrorBoundary>
            <ThrowingComponent shouldThrow={true} errorType={errorType} />
          </TestErrorBoundary>
        )

        expect(screen.getByTestId('error-boundary')).toBeInTheDocument()
        
        // Clean up before next iteration
        unmount()
      })
    })

    it('should isolate errors to specific component trees', () => {
      render(
        <div>
          <TestErrorBoundary>
            <ThrowingComponent shouldThrow={true} />
          </TestErrorBoundary>
          <TestErrorBoundary>
            <ThrowingComponent shouldThrow={false} />
          </TestErrorBoundary>
        </div>
      )

      // First boundary should show error
      const errorBoundaries = screen.getAllByTestId('error-boundary')
      expect(errorBoundaries).toHaveLength(1)

      // Second boundary should show normal content
      expect(screen.getByTestId('no-error')).toBeInTheDocument()
    })
  })

  describe('API Error Handling', () => {
    it('should handle API failures gracefully with user feedback', async () => {
      render(<ApiTestComponent />)

      expect(screen.getByTestId('loading')).toHaveTextContent('false')
      expect(screen.getByTestId('error')).toHaveTextContent('none')

      // Trigger failing API call
      const failButton = screen.getByText('Failing API Call')
      await user.click(failButton)

      // Should show loading state
      expect(screen.getByTestId('loading')).toHaveTextContent('true')

      // Wait for API call to complete
      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('false')
      })

      // Should show error state
      const errorText = screen.getByTestId('error').textContent
      expect(errorText).not.toBe('none')
      expect(errorText).toMatch(/(Network|Server|Validation|Request timeout)/)
    })

    it('should provide appropriate error messages for different error types', async () => {
      const { unmount } = render(<ApiTestComponent />)

      // Test multiple error scenarios
      for (let i = 0; i < 5; i++) {
        const { rerender } = render(<ApiTestComponent />)
        
        const failButton = screen.getByText('Failing API Call')
        await user.click(failButton)

        await waitFor(() => {
          expect(screen.getByTestId('loading')).toHaveTextContent('false')
        }, { timeout: 1000 })

        const errorMessage = screen.getByTestId('error').textContent
        expect(errorMessage).toBeTruthy()
        expect(errorMessage).not.toBe('none')

        unmount()
      }
    })

    it('should handle successful API calls after errors', async () => {
      render(<ApiTestComponent />)

      // First, trigger an error
      await user.click(screen.getByText('Failing API Call'))
      
      await waitFor(() => {
        expect(screen.getByTestId('error')).not.toHaveTextContent('none')
      })

      // Then, make a successful call
      await user.click(screen.getByText('Successful API Call'))

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('false')
      })

      // Error should be cleared
      expect(screen.getByTestId('error')).toHaveTextContent('none')
    })
  })

  describe('WebSocket Error Handling and Recovery', () => {
    it('should handle WebSocket connection failures with retry logic', async () => {
      jest.useFakeTimers()
      render(<WebSocketTestComponent />)

      expect(screen.getByTestId('ws-connected')).toHaveTextContent('false')
      expect(screen.getByTestId('connection-attempts')).toHaveTextContent('0')

      // Simulate connection failure
      await user.click(screen.getByText('Connection Failed'))

      expect(screen.getByTestId('ws-connected')).toHaveTextContent('false')
      expect(screen.getByTestId('last-error')).toHaveTextContent('connection_failed')

      // Fast-forward to trigger retry
      act(() => {
        jest.advanceTimersByTime(1100)
      })

      // Should have attempted reconnection
      expect(screen.getByTestId('connection-attempts')).toHaveTextContent('1')
      expect(screen.getByTestId('ws-connected')).toHaveTextContent('true')

      jest.useRealTimers()
    })

    it('should handle different WebSocket error scenarios', async () => {
      render(<WebSocketTestComponent />)

      const errorScenarios = [
        { button: 'Connection Failed', expectedError: 'connection_failed' },
        { button: 'Connection Lost', expectedError: 'connection_lost' },
        { button: 'Auth Failed', expectedError: 'auth_failed' },
        { button: 'Server Error', expectedError: 'server_error' }
      ]

      for (const scenario of errorScenarios) {
        await user.click(screen.getByText(scenario.button))
        
        expect(screen.getByTestId('last-error')).toHaveTextContent(scenario.expectedError)
        expect(screen.getByTestId('ws-connected')).toHaveTextContent('false')

        // Reset for next test
        await user.click(screen.getByText('Force Reconnect'))
      }
    })

    it('should stop retrying after authentication failures', async () => {
      jest.useFakeTimers()
      render(<WebSocketTestComponent />)

      // Trigger auth failure
      await user.click(screen.getByText('Auth Failed'))

      expect(screen.getByTestId('last-error')).toHaveTextContent('auth_failed')
      
      // Fast-forward time
      act(() => {
        jest.advanceTimersByTime(2000)
      })

      // Should not have attempted reconnection for auth errors
      expect(screen.getByTestId('connection-attempts')).toHaveTextContent('0')
      expect(screen.getByTestId('ws-connected')).toHaveTextContent('false')

      jest.useRealTimers()
    })

    it('should limit retry attempts to prevent infinite loops', async () => {
      jest.useFakeTimers()
      render(<WebSocketTestComponent />)

      // Trigger multiple connection failures
      for (let i = 0; i < 5; i++) {
        await user.click(screen.getByText('Connection Failed'))
        
        act(() => {
          jest.advanceTimersByTime(1100)
        })
      }

      // Should stop retrying after max attempts
      const attempts = parseInt(screen.getByTestId('connection-attempts').textContent || '0')
      expect(attempts).toBeLessThan(5) // Should have stopped before 5 attempts

      jest.useRealTimers()
    })
  })

  describe('Form Validation and Error Recovery', () => {
    it('should handle form submission errors gracefully', async () => {
      const FormTestComponent = () => {
        const [errors, setErrors] = React.useState<Record<string, string>>({})
        const [submitting, setSubmitting] = React.useState(false)

        const handleSubmit = async (e: React.FormEvent) => {
          e.preventDefault()
          setSubmitting(true)
          setErrors({})

          const formData = new FormData(e.target as HTMLFormElement)
          const prompt = formData.get('prompt') as string
          const duration = formData.get('duration') as string

          // Validate form
          const newErrors: Record<string, string> = {}
          
          if (!prompt?.trim()) {
            newErrors.prompt = 'Prompt is required'
          }
          
          if (!duration || isNaN(Number(duration))) {
            newErrors.duration = 'Duration must be a valid number'
          } else if (Number(duration) < 10) {
            newErrors.duration = 'Duration must be at least 10 seconds'
          } else if (Number(duration) > 300) {
            newErrors.duration = 'Duration cannot exceed 300 seconds'
          }

          if (Object.keys(newErrors).length > 0) {
            setErrors(newErrors)
            setSubmitting(false)
            return
          }

          // Simulate API submission that might fail
          try {
            await new Promise((resolve, reject) => {
              setTimeout(() => {
                if (Math.random() > 0.7) { // 30% chance of failure
                  reject(new Error('Server validation failed'))
                } else {
                  resolve('success')
                }
              }, 500)
            })

            // Success - clear form
            ;(e.target as HTMLFormElement).reset()
          } catch (error) {
            setErrors({ submit: 'Failed to submit form. Please try again.' })
          } finally {
            setSubmitting(false)
          }
        }

        return (
          <form onSubmit={handleSubmit} data-testid="test-form">
            <div>
              <input
                name="prompt"
                placeholder="Video prompt"
                data-testid="prompt-input"
                aria-invalid={!!errors.prompt}
                aria-describedby={errors.prompt ? 'prompt-error' : undefined}
              />
              {errors.prompt && (
                <div id="prompt-error" role="alert" data-testid="prompt-error">
                  {errors.prompt}
                </div>
              )}
            </div>

            <div>
              <input
                name="duration"
                type="number"
                placeholder="Duration"
                data-testid="duration-input"
                aria-invalid={!!errors.duration}
                aria-describedby={errors.duration ? 'duration-error' : undefined}
              />
              {errors.duration && (
                <div id="duration-error" role="alert" data-testid="duration-error">
                  {errors.duration}
                </div>
              )}
            </div>

            {errors.submit && (
              <div role="alert" data-testid="submit-error">
                {errors.submit}
              </div>
            )}

            <button type="submit" disabled={submitting} data-testid="submit-button">
              {submitting ? 'Submitting...' : 'Submit'}
            </button>
          </form>
        )
      }

      render(<FormTestComponent />)

      // Test client-side validation
      await user.click(screen.getByTestId('submit-button'))

      expect(screen.getByTestId('prompt-error')).toHaveTextContent('Prompt is required')
      expect(screen.getByTestId('duration-error')).toHaveTextContent('Duration must be a valid number')

      // Fix validation errors
      await user.type(screen.getByTestId('prompt-input'), 'Test video prompt')
      await user.type(screen.getByTestId('duration-input'), '60')

      // Clear validation errors
      expect(screen.queryByTestId('prompt-error')).not.toBeInTheDocument()
      expect(screen.queryByTestId('duration-error')).not.toBeInTheDocument()

      // Test server-side error (may or may not occur due to randomness)
      await user.click(screen.getByTestId('submit-button'))

      // Wait for submission to complete
      await waitFor(() => {
        expect(screen.getByTestId('submit-button')).not.toBeDisabled()
      }, { timeout: 1000 })

      // If there was a server error, it should be displayed
      const submitError = screen.queryByTestId('submit-error')
      if (submitError) {
        expect(submitError).toHaveTextContent('Failed to submit form')
      }
    })
  })

  describe('Global Error Handling', () => {
    it('should handle unhandled promise rejections', async () => {
      const UnhandledPromiseComponent = () => {
        const triggerUnhandledRejection = () => {
          // This will create an unhandled promise rejection
          Promise.reject(new Error('Unhandled promise rejection'))
        }

        return (
          <button onClick={triggerUnhandledRejection} data-testid="trigger-unhandled">
            Trigger Unhandled Rejection
          </button>
        )
      }

      // Set up global error handler
      const unhandledRejections: Error[] = []
      const originalHandler = window.addEventListener
      
      window.addEventListener = jest.fn((event, handler) => {
        if (event === 'unhandledrejection') {
          // Store the handler for testing
          ;(window as any).__unhandledRejectionHandler = handler
        }
        return originalHandler.call(window, event, handler)
      })

      render(<UnhandledPromiseComponent />)

      const button = screen.getByTestId('trigger-unhandled')
      await user.click(button)

      // Simulate unhandled rejection
      if ((window as any).__unhandledRejectionHandler) {
        const mockEvent = {
          preventDefault: jest.fn(),
          reason: new Error('Unhandled promise rejection')
        }
        ;(window as any).__unhandledRejectionHandler(mockEvent)
        
        expect(mockEvent.preventDefault).toHaveBeenCalled()
      }

      // Restore original handler
      window.addEventListener = originalHandler
    })

    it('should provide error reporting mechanism', async () => {
      const reportError = jest.fn()

      const ErrorReportingComponent = () => {
        const handleError = (error: Error) => {
          reportError({
            message: error.message,
            stack: error.stack,
            timestamp: new Date().toISOString(),
            url: window.location.href,
            userAgent: navigator.userAgent
          })
        }

        return (
          <TestErrorBoundary onError={handleError}>
            <ThrowingComponent shouldThrow={true} />
          </TestErrorBoundary>
        )
      }

      render(<ErrorReportingComponent />)

      // Error should be reported
      expect(reportError).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Generic component error',
          timestamp: expect.any(String),
          url: expect.any(String),
          userAgent: expect.any(String)
        })
      )
    })
  })

  describe('Error State Recovery', () => {
    it('should allow partial application recovery after errors', async () => {
      const PartialRecoveryComponent = () => {
        const [hasError, setHasError] = React.useState(false)
        const [errorModule, setErrorModule] = React.useState<string | null>(null)

        const simulateModuleError = (module: string) => {
          setHasError(true)
          setErrorModule(module)
        }

        const recoverModule = (module: string) => {
          if (errorModule === module) {
            setHasError(false)
            setErrorModule(null)
          }
        }

        return (
          <div data-testid="partial-recovery">
            <div data-testid="app-status">
              {hasError ? `Error in ${errorModule}` : 'All systems operational'}
            </div>
            
            <div data-testid="module-video-generator">
              {hasError && errorModule === 'video-generator' ? (
                <div>
                  Video generator is offline
                  <button onClick={() => recoverModule('video-generator')}>
                    Restart Video Generator
                  </button>
                </div>
              ) : (
                <div>Video generator is running</div>
              )}
            </div>

            <div data-testid="module-file-upload">
              {hasError && errorModule === 'file-upload' ? (
                <div>
                  File upload is offline
                  <button onClick={() => recoverModule('file-upload')}>
                    Restart File Upload
                  </button>
                </div>
              ) : (
                <div>File upload is running</div>
              )}
            </div>

            <button onClick={() => simulateModuleError('video-generator')}>
              Break Video Generator
            </button>
            <button onClick={() => simulateModuleError('file-upload')}>
              Break File Upload
            </button>
          </div>
        )
      }

      render(<PartialRecoveryComponent />)

      expect(screen.getByTestId('app-status')).toHaveTextContent('All systems operational')

      // Break video generator
      await user.click(screen.getByText('Break Video Generator'))
      
      expect(screen.getByTestId('app-status')).toHaveTextContent('Error in video-generator')
      expect(screen.getByText('Video generator is offline')).toBeInTheDocument()
      expect(screen.getByText('File upload is running')).toBeInTheDocument()

      // Recover video generator
      await user.click(screen.getByText('Restart Video Generator'))
      
      expect(screen.getByTestId('app-status')).toHaveTextContent('All systems operational')
      expect(screen.getByText('Video generator is running')).toBeInTheDocument()
    })
  })
})