'use client';

import React from 'react';
import { useAppStore } from '@/store/useAppStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import VideoRequestForm from '@/components/forms/VideoRequestForm';
import AgentOrchestrator from '@/components/agents/AgentOrchestrator';
import RealTimeProgress from '@/components/progress/RealTimeProgress';
import VideoPlayer from '@/components/video/VideoPlayer';
import ExportInterface from '@/components/video/ExportInterface';
import { useI18n } from '@/i18n/I18nProvider';
import { useTaskPolling } from '@/hooks/useTaskPolling';
import ResultOverlay from '@/components/video/ResultOverlay';
import ProjectModeView from '@/components/project/ProjectModeView';

const HomePage: React.FC = () => {
  const { ui, currentRequest, finalVideoUrl, mode, setMode, setCurrentStep } = useAppStore();
  const { currentStep } = ui;
  const { t } = useI18n();

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
        return (
          <div className="flex-1 flex flex-col gap-6 overflow-auto">
            {/* Agent Status & Progress (full width) */}
            <div className="bg-white/90 backdrop-blur rounded-xl shadow-card border border-gray-200 p-6 mt-2">
              <AgentOrchestrator />
            </div>
            <div className="bg-white/90 backdrop-blur rounded-xl shadow-card border border-gray-200 p-6">
              <RealTimeProgress />
            </div>
          </div>
        );

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
            <div className="lg:w-1/3">
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
    <div className="h-full flex-1 w-full flex flex-col p-6 gap-6 relative">
      {renderModeTabs()}

      <div className="flex items-center justify-center">
        <div className="flex items-center space-x-8">
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
              <div key={step.id} className="flex items-center">
                <div className={`
                  flex items-center space-x-3
                  ${isActive ? 'text-primary-600' : isCompleted ? 'text-green-600' : 'text-gray-400'}
                `}>
                  <div className={`
                    w-9 h-9 rounded-full flex items-center justify-center text-sm font-semibold shadow-card
                    ${isActive 
                      ? 'bg-gradient-to-br from-primary-100 to-accent-100 text-primary-700 ring-2 ring-primary-200' 
                      : isCompleted 
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-400'
                    }
                  `}>
                    {step.number}
                  </div>
                  <span className="font-medium hidden sm:block">
                    {step.label}
                  </span>
                </div>

                {index < 3 && (
                  <div className={`
                    w-16 h-1 mx-4 rounded-full
                    ${isCompleted ? 'bg-gradient-to-r from-green-300 to-emerald-400' : 'bg-gray-200'}
                  `} />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {renderMainContent()}

      <ResultOverlay />
    </div>
  );
};

export default HomePage;
