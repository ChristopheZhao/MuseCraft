import '@testing-library/jest-dom';
import React from 'react';
import { cleanup, render, waitFor } from '@testing-library/react';

import { useTaskPolling } from '@/hooks/useTaskPolling';
import { ApiClient } from '@/lib/api';
import { useAppStore } from '@/store/useAppStore';
import type { TaskRuntimeView } from '@/types';

jest.mock('@/store/useAppStore');
jest.mock('@/lib/api', () => ({
  ApiClient: {
    getTaskRuntime: jest.fn(),
    getTaskDetail: jest.fn(),
    getTaskResources: jest.fn(),
  },
}));

const mockUseAppStore = useAppStore as jest.MockedFunction<typeof useAppStore>;
const mockGetTaskRuntime = ApiClient.getTaskRuntime as jest.MockedFunction<
  typeof ApiClient.getTaskRuntime
>;
const mockGetTaskDetail = ApiClient.getTaskDetail as jest.MockedFunction<
  typeof ApiClient.getTaskDetail
>;
const mockGetTaskResources = ApiClient.getTaskResources as jest.MockedFunction<
  typeof ApiClient.getTaskResources
>;

const HookHarness = () => {
  useTaskPolling();
  return null;
};

const buildRuntime = (overrides: Partial<TaskRuntimeView> = {}): TaskRuntimeView => ({
  session_id: 10,
  task_db_id: 20,
  mode: 'quick',
  status: 'completed',
  current_node_key: 'quality',
  current_attempt_id: 30,
  active_gate: null,
  error_message: null,
  summary_output: {},
  resume_control: null,
  nodes: [],
  created_at: '2026-04-07T08:00:00Z',
  updated_at: '2026-04-07T08:10:00Z',
  ...overrides,
});

describe('useTaskPolling completed finalization', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    process.env.NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8005/api/v1';
  });

  afterEach(() => {
    cleanup();
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  it('keeps the workspace in processing when completed runtime has no fresh final video url', async () => {
    const store = {
      currentRequest: {
        id: 'task-123',
        title: 'Current task',
      },
      setCurrentStep: jest.fn(),
      setFinalVideoUrl: jest.fn(),
      setQuickRuntime: jest.fn(),
      addNotification: jest.fn(),
      setModal: jest.fn(),
    };
    mockUseAppStore.mockReturnValue(store as any);
    mockGetTaskRuntime.mockResolvedValue(buildRuntime());
    mockGetTaskDetail.mockResolvedValue({
      output_metadata: {},
    } as any);
    mockGetTaskResources.mockResolvedValue([]);

    const { unmount } = render(<HookHarness />);

    await waitFor(() => {
      expect(mockGetTaskRuntime).toHaveBeenCalledWith('task-123');
      expect(store.setQuickRuntime).toHaveBeenCalledWith(buildRuntime());
    });

    expect(store.setFinalVideoUrl).not.toHaveBeenCalled();
    expect(store.setModal).not.toHaveBeenCalled();
    expect(store.setCurrentStep).not.toHaveBeenCalledWith('review');

    unmount();
  });

  it('opens the completed result only after a browser-safe final video url is resolved', async () => {
    const store = {
      currentRequest: {
        id: 'task-123',
        title: 'Current task',
      },
      setCurrentStep: jest.fn(),
      setFinalVideoUrl: jest.fn(),
      setQuickRuntime: jest.fn(),
      addNotification: jest.fn(),
      setModal: jest.fn(),
    };
    mockUseAppStore.mockReturnValue(store as any);
    mockGetTaskRuntime.mockResolvedValue(
      buildRuntime({
        summary_output: {
          final_video_url: '/files/outputs/videos/final_story_1.mp4',
        },
      })
    );
    mockGetTaskDetail.mockResolvedValue({
      output_metadata: {},
    } as any);
    mockGetTaskResources.mockResolvedValue([]);

    const { unmount } = render(<HookHarness />);

    await waitFor(() => {
      expect(store.setFinalVideoUrl).toHaveBeenCalledWith(
        'http://127.0.0.1:8005/files/outputs/videos/final_story_1.mp4'
      );
      expect(store.setModal).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'result-ready',
        })
      );
    });

    unmount();
  });
});
