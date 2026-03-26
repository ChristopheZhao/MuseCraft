/**
 * Real-time Communication Integration Tests
 *
 * Verifies the first-party client consumes the canonical runtime/read-model
 * websocket contract instead of retired compat vocabulary.
 */
import React from 'react'
import { act, render, waitFor } from '@testing-library/react'

import { useAppStore } from '../../src/store/useAppStore'
import { useWebSocket } from '../../src/hooks/useWebSocket'
import { ApiClient } from '../../src/lib/api'
import { mockWebSocketTestUtils } from '../setup'

jest.mock('../../src/store/useAppStore')
jest.mock('../../src/lib/api', () => ({
  ApiClient: {
    getTaskRuntime: jest.fn(),
  },
}))

const mockUseAppStore = useAppStore as jest.MockedFunction<typeof useAppStore>
const mockGetTaskRuntime = ApiClient.getTaskRuntime as jest.MockedFunction<typeof ApiClient.getTaskRuntime>

const WS_URL = 'ws://localhost:8000/api/v1/ws/connect'

const runtimeView = {
  session_id: 1,
  task_db_id: 1,
  mode: 'quick',
  status: 'running',
  summary_output: {},
  nodes: [],
}

const HookHarness: React.FC = () => {
  useWebSocket({
    url: WS_URL,
    reconnectInterval: 10,
    maxReconnectAttempts: 1,
  })
  return null
}

describe('Real-time Communication Integration Tests', () => {
  let mockStore: any

  beforeEach(() => {
    mockWebSocketTestUtils.reset()

    mockStore = {
      currentRequest: {
        id: 'test-request-123',
        title: 'Test Video Generation',
        description: 'Test description',
      },
      wsConnected: false,
      agents: [],
      results: [],
      quickRuntime: null,
      setWSConnected: jest.fn(),
      updateAgent: jest.fn(),
      addResult: jest.fn(),
      updateResult: jest.fn(),
      addNotification: jest.fn(),
      setQuickRuntime: jest.fn(),
    }

    mockUseAppStore.mockReturnValue(mockStore)
    mockGetTaskRuntime.mockResolvedValue(runtimeView as any)
  })

  afterEach(() => {
    jest.clearAllMocks()
    mockWebSocketTestUtils.reset()
  })

  const renderHarness = async () => {
    render(<HookHarness />)
    await waitFor(() => {
      expect(mockStore.setWSConnected).toHaveBeenCalledWith(true)
    })

    const socket = mockWebSocketTestUtils.getLastSocket()
    expect(socket).not.toBeNull()
    return socket!
  }

  it('subscribes to the current task and applies canonical event.progress telemetry', async () => {
    const socket = await renderHarness()

    expect(socket.sentMessages).toHaveLength(1)
    expect(JSON.parse(String(socket.sentMessages[0]))).toMatchObject({
      type: 'subscribe_task',
      task_id: 'test-request-123',
    })

    act(() => {
      socket.simulateMessage({
        type: 'event.progress',
        agent_type: 'concept_planner',
        payload: {
          progress: 45,
          current_step: 'Analyzing user requirements',
        },
      })
    })

    await waitFor(() => {
      expect(mockStore.updateAgent).toHaveBeenCalledWith('concept-generator', {
        progress: 45,
        currentTask: 'Analyzing user requirements',
      })
    })
  })

  it('maps canonical event.state payload.status into agent status and refreshes runtime', async () => {
    const socket = await renderHarness()

    act(() => {
      socket.simulateMessage({
        type: 'event.state',
        agent_name: 'script_writer',
        payload: {
          status: 'completed',
        },
      })
    })

    await waitFor(() => {
      expect(mockStore.updateAgent).toHaveBeenCalledWith('script-writer', {
        status: 'completed',
      })
      expect(mockStore.setQuickRuntime).toHaveBeenCalledWith(runtimeView)
    })
  })

  it('surfaces terminal workflow events through notifications and runtime refresh', async () => {
    const socket = await renderHarness()

    act(() => {
      socket.simulateMessage({
        type: 'event.state',
        payload: {
          state: 'workflow_completed',
          results: [],
        },
      })
    })

    await waitFor(() => {
      expect(mockStore.addNotification).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'success',
          title: '生成完成通知',
        })
      )
      expect(mockStore.setQuickRuntime).toHaveBeenCalledWith(runtimeView)
    })
  })

  it('still consumes direct transport notices without reviving compat handlers', async () => {
    const socket = await renderHarness()

    act(() => {
      socket.simulateMessage({
        type: 'task_notification',
        message: 'Queue paused for gate review',
        level: 'warning',
      })
    })

    await waitFor(() => {
      expect(mockStore.addNotification).toHaveBeenCalledWith({
        type: 'warning',
        title: 'System Message',
        message: 'Queue paused for gate review',
        autoClose: 5000,
      })
    })
  })
})
