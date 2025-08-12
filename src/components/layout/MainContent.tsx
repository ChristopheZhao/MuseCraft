'use client';

import React from 'react';
import { useAppStore } from '@/store/useAppStore';

interface MainContentProps {
  children: React.ReactNode;
}

const MainContent: React.FC<MainContentProps> = ({ children }) => {
  const { ui } = useAppStore();
  const { isLoading } = ui;

  return (
    <main className="flex-1 flex flex-col overflow-hidden bg-gray-50">
      {/* Loading Overlay */}
      {isLoading && (
        <div className="absolute inset-0 bg-white bg-opacity-75 flex items-center justify-center z-50">
          <div className="flex flex-col items-center space-y-4">
            <div className="w-12 h-12 border-4 border-primary-200 border-t-primary-600 rounded-full animate-spin" />
            <p className="text-sm text-gray-600 font-medium">
              Processing your request...
            </p>
          </div>
        </div>
      )}
      
      {/* Content Area */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        {children}
      </div>
    </main>
  );
};

export default MainContent;