'use client';

import React from 'react';
import { useAppStore } from '@/store/useAppStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import VideoRequestForm from '@/components/forms/VideoRequestForm';
import VideoPlayer from '@/components/video/VideoPlayer';
import ExportInterface from '@/components/video/ExportInterface';
import { useI18n } from '@/i18n/I18nProvider';
import { useTaskPolling } from '@/hooks/useTaskPolling';
import ResultOverlay from '@/components/video/ResultOverlay';
import ProjectModeView from '@/components/project/ProjectModeView';
import QuickModeWorkspace from '@/components/preview/QuickModeWorkspace';
import RoleContinuityDiagnosticsPanel from '@/components/quality/RoleContinuityDiagnosticsPanel';
import { cn } from '@/lib/utils';

const HomePage: React.FC = () => {
  const { ui, currentRequest, finalVideoUrl, mode, quickRuntime, setMode, setCurrentStep } = useAppStore();
  const { currentStep } = ui;
  const { t } = useI18n();
  const isProcessingWorkspace = mode === 'quick' && currentStep === 'processing';

  // Initialize WebSocket connection (URL auto-resolved inside hook)
  useWebSocket();
  // Polling fallback when WS is unavailable
  useTaskPolling();

  const renderMainContent = () => {
    switch (currentStep) {
      case 'input':
        return (
          <div className="flex-1 w-full overflow-auto">
            <VideoRequestForm />
          </div>
        );

      case 'processing':
        return <QuickModeWorkspace />;

      case 'review':
        return (
          <div className="flex-1 flex flex-col lg:flex-row gap-6 overflow-hidden">
            {/* Left Column - Video Player */}
            <div className="lg:w-2/3 space-y-6">
              <div className="bg-white/90 backdrop-blur rounded-xl shadow-card border border-gray-200 p-6">
                <VideoPlayer
                  src={finalVideoUrl}
                  title={currentRequest?.title}
                  className="aspect-video"
                />
              </div>
            </div>

            {/* Right Column - Export Interface */}
            <div className="lg:w-1/3 space-y-4">
              <RoleContinuityDiagnosticsPanel summaryOutput={quickRuntime?.summary_output} />
              <div className="bg-white/90 backdrop-blur rounded-xl shadow-card border border-gray-200 p-6 h-full">
                <ExportInterface 
                  videoUrl={finalVideoUrl}
                />
              </div>
            </div>
          </div>
        );

      case 'export':
        return (
          <div className="flex-1 flex flex-col gap-6 overflow-hidden">
            {/* Video Player */}
            <div className="bg-white/90 backdrop-blur rounded-xl shadow-card border border-gray-200 p-6">
              <VideoPlayer
                src={finalVideoUrl}
                title={currentRequest?.title}
                className="aspect-video max-w-4xl mx-auto"
              />
            </div>

            {/* Export Interface */}
            <RoleContinuityDiagnosticsPanel summaryOutput={quickRuntime?.summary_output} />
            <div className="bg-white/90 backdrop-blur rounded-xl shadow-card border border-gray-200 p-6">
              <ExportInterface videoUrl={finalVideoUrl} />
            </div>
          </div>
        );

      default:
        return (
          <div className="flex-1 overflow-auto">
            <VideoRequestForm />
          </div>
        );
    }
  };

  const handleModeChange = (nextMode: 'quick' | 'project') => {
    setMode(nextMode);
    if (nextMode === 'quick') {
      setCurrentStep('input');
    }
  };

  const renderModeTabs = () => (
    <div className="flex items-center justify-center">
      <div className="inline-flex rounded-full bg-gray-100 p-1">
        <button
          className={`px-4 py-2 text-sm font-medium rounded-full transition ${
            mode === 'quick' ? 'bg-white shadow text-primary-600' : 'text-gray-600 hover:text-gray-900'
          }`}
          onClick={() => handleModeChange('quick')}
        >
          快速创作
        </button>
        <button
          className={`px-4 py-2 text-sm font-medium rounded-full transition ${
            mode === 'project' ? 'bg-white shadow text-primary-600' : 'text-gray-600 hover:text-gray-900'
          }`}
          onClick={() => handleModeChange('project')}
        >
          项目模式
        </button>
      </div>
    </div>
  );

  if (mode === 'project') {
    return (
      <div className="h-full flex-1 w-full flex flex-col p-6 gap-6 relative">
        {renderModeTabs()}
        <ProjectModeView />
      </div>
    );
  }

  return (
    <div
      className={cn(
        'h-full flex-1 w-full flex flex-col relative',
        isProcessingWorkspace ? 'gap-4 p-4 lg:gap-5 lg:p-5' : 'gap-6 p-6'
      )}
    >
      {renderModeTabs()}

      <div className="flex items-center justify-center">
        <div
          className={cn(
            'inline-flex flex-col items-center border border-white/70 bg-white/70 shadow-sm backdrop-blur',
            isProcessingWorkspace ? 'gap-2 rounded-[24px] px-4 py-3' : 'gap-3 rounded-[28px] px-5 py-4'
          )}
        >
          <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">
            产品步骤
          </div>
          <div className="flex flex-wrap items-center justify-center gap-2 sm:gap-3">
          {[
            { id: 'input', label: t('step.create'), number: 1 },
            { id: 'processing', label: t('step.generation'), number: 2 },
            { id: 'review', label: t('step.review'), number: 3 },
            { id: 'export', label: t('step.export'), number: 4 },
          ].map((step, index) => {
            const isActive = currentStep === step.id;
            const stepOrder = ['input', 'processing', 'review', 'export'];
            const isCompleted = stepOrder.indexOf(currentStep) > stepOrder.indexOf(step.id);

            return (
              <div key={step.id} className="flex items-center gap-2">
                <div className={`
                  inline-flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-medium transition
                  ${isActive
                    ? 'border-primary-200 bg-primary-50 text-primary-700'
                    : isCompleted
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                      : 'border-slate-200 bg-white text-slate-500'}
                `}>
                  <div className={`
                    flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold
                    ${isActive
                      ? 'bg-primary-100 text-primary-700'
                      : isCompleted
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-slate-100 text-slate-500'
                    }
                  `}>
                    {step.number}
                  </div>
                  <span>{step.label}</span>
                </div>

                {index < 3 && (
                  <div className={`
                    hidden h-px w-5 rounded-full sm:block
                    ${isCompleted ? 'bg-emerald-300' : 'bg-slate-200'}
                  `} />
                )}
              </div>
            );
          })}
          </div>
        </div>
      </div>

      {renderMainContent()}

      <ResultOverlay />
    </div>
  );
};

export default HomePage;
