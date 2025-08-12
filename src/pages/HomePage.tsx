'use client';

import React from 'react';
import { useAppStore } from '@/store/useAppStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import VideoRequestForm from '@/components/forms/VideoRequestForm';
import AgentOrchestrator from '@/components/agents/AgentOrchestrator';
import RealTimeProgress from '@/components/progress/RealTimeProgress';
import ResultPreview from '@/components/preview/ResultPreview';
import VideoPlayer from '@/components/video/VideoPlayer';
import ExportInterface from '@/components/video/ExportInterface';

const HomePage: React.FC = () => {
  const { ui, currentRequest } = useAppStore();
  const { currentStep } = ui;

  // Initialize WebSocket connection
  useWebSocket({
    url: process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/api/v1/ws/connect',
  });

  const renderMainContent = () => {
    switch (currentStep) {
      case 'input':
        return (
          <div className="flex-1 overflow-auto">
            <VideoRequestForm />
          </div>
        );

      case 'processing':
        return (
          <div className="flex-1 flex flex-col lg:flex-row gap-6 overflow-hidden">
            {/* Left Column - Agent Status & Progress */}
            <div className="lg:w-1/2 space-y-6 overflow-auto">
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <AgentOrchestrator />
              </div>
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <RealTimeProgress />
              </div>
            </div>

            {/* Right Column - Results Preview */}
            <div className="lg:w-1/2 overflow-auto">
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 h-full">
                <ResultPreview />
              </div>
            </div>
          </div>
        );

      case 'review':
        return (
          <div className="flex-1 flex flex-col lg:flex-row gap-6 overflow-hidden">
            {/* Left Column - Video Player */}
            <div className="lg:w-2/3 space-y-6">
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <VideoPlayer
                  src="/api/video/sample.mp4" // This would be the actual generated video URL
                  title={currentRequest?.title}
                  className="aspect-video"
                />
              </div>
              
              {/* Final Results Summary */}
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <ResultPreview />
              </div>
            </div>

            {/* Right Column - Export Interface */}
            <div className="lg:w-1/3">
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 h-full">
                <ExportInterface 
                  videoUrl="/api/video/sample.mp4"
                />
              </div>
            </div>
          </div>
        );

      case 'export':
        return (
          <div className="flex-1 flex flex-col gap-6 overflow-hidden">
            {/* Video Player */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <VideoPlayer
                src="/api/video/sample.mp4"
                title={currentRequest?.title}
                className="aspect-video max-w-4xl mx-auto"
              />
            </div>

            {/* Export Interface */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <ExportInterface 
                videoUrl="/api/video/sample.mp4"
              />
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

  return (
    <div className="h-full flex flex-col p-6 gap-6">
      {/* Step Indicator */}
      <div className="flex items-center justify-center">
        <div className="flex items-center space-x-8">
          {[
            { id: 'input', label: 'Create Request', number: 1 },
            { id: 'processing', label: 'AI Generation', number: 2 },
            { id: 'review', label: 'Review Results', number: 3 },
            { id: 'export', label: 'Export & Share', number: 4 },
          ].map((step, index) => {
            const isActive = currentStep === step.id;
            const isCompleted = ['input', 'processing', 'review'].indexOf(currentStep) > ['input', 'processing', 'review'].indexOf(step.id);
            
            return (
              <div key={step.id} className="flex items-center">
                <div className={`
                  flex items-center space-x-3
                  ${isActive ? 'text-primary-600' : isCompleted ? 'text-green-600' : 'text-gray-400'}
                `}>
                  <div className={`
                    w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium
                    ${isActive 
                      ? 'bg-primary-100 text-primary-600 ring-2 ring-primary-200' 
                      : isCompleted 
                        ? 'bg-green-100 text-green-600'
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
                    w-16 h-0.5 mx-4
                    ${isCompleted ? 'bg-green-300' : 'bg-gray-200'}
                  `} />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Content */}
      {renderMainContent()}
    </div>
  );
};

export default HomePage;