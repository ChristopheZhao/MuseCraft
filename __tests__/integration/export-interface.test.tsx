import '@testing-library/jest-dom';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import ExportInterface from '@/components/video/ExportInterface';
import { I18nProvider } from '@/i18n/I18nProvider';
import { useAppStore } from '@/store/useAppStore';

jest.mock('@/store/useAppStore');

const mockUseAppStore = useAppStore as jest.MockedFunction<typeof useAppStore>;

describe('ExportInterface', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      blob: jest.fn().mockResolvedValue(new Blob(['video'], { type: 'video/mp4' })),
    });
  });

  it('downloads the current finished render through a browser download flow', async () => {
    const addNotification = jest.fn();
    mockUseAppStore.mockReturnValue({
      currentRequest: {
        id: 'task-123',
        title: 'Spring Story',
      },
      addNotification,
    } as any);

    const appendChildSpy = jest.spyOn(document.body, 'appendChild');
    const user = userEvent.setup();

    render(
      <I18nProvider defaultLang="zh">
        <ExportInterface videoUrl="http://127.0.0.1:8005/files/outputs/videos/final_story_1.mp4" />
      </I18nProvider>
    );

    await user.click(screen.getByRole('button', { name: '下载当前成片' }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        'http://127.0.0.1:8005/files/outputs/videos/final_story_1.mp4'
      );
      expect(global.URL.createObjectURL).toHaveBeenCalled();
      expect(addNotification).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'success',
          title: '下载已开始',
        })
      );
    });

    const anchor = appendChildSpy.mock.calls[0][0] as HTMLAnchorElement;
    expect(anchor.download).toBe('final_story_1.mp4');

    appendChildSpy.mockRestore();
  });
});
