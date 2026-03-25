import React from 'react';
import { render, waitFor } from '@testing-library/react';

import { useTaskPolling } from '@/hooks/useTaskPolling';
import { ApiClient, TaskRuntimeEndpointError } from '@/lib/api';
import { useAppStore } from '@/store/useAppStore';

jest.mock('@/store/useAppStore');

const mockUseAppStore = useAppStore as jest.MockedFunction<typeof useAppStore>;

function PollingHarness() {
  useTaskPolling();
  return null;
}

describe('task polling runtime authority', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('does not fall back to coarse status when runtime endpoint fails non-lag reads', async () => {
    const store = {
      currentRequest: {
        id: 'task-123',
        title: '测试任务',
      },
      setCurrentStep: jest.fn(),
      setFinalVideoUrl: jest.fn(),
      setQuickRuntime: jest.fn(),
      addNotification: jest.fn(),
      setModal: jest.fn(),
    };
    mockUseAppStore.mockReturnValue(store as any);

    const runtimeSpy = jest
      .spyOn(ApiClient, 'getTaskRuntime')
      .mockRejectedValue(new TaskRuntimeEndpointError(500, 'runtime endpoint exploded'));
    const coarseSpy = jest.spyOn(ApiClient, 'getTaskCoarseStatus').mockResolvedValue({
      task_id: 'task-123',
      status: 'completed',
      progress_percentage: 100,
      current_step: 'Completed',
      error_message: undefined,
      projection_role: 'compatibility_coarse_task_status',
      runtime_authoritative: false,
      agent_executions: [],
    });

    const view = render(<PollingHarness />);

    await waitFor(() => {
      expect(runtimeSpy).toHaveBeenCalledWith('task-123');
    });

    expect(coarseSpy).not.toHaveBeenCalled();
    expect(store.addNotification).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'error',
        title: '运行时状态不可用',
        message: 'runtime endpoint exploded',
      })
    );

    view.unmount();
  });
});
