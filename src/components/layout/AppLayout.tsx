'use client';

import React from 'react';
import { useAppStore } from '@/store/useAppStore';
import { cn } from '@/lib/utils';
import Header from './Header';
import Sidebar from './Sidebar';
import MainContent from './MainContent';
import NotificationContainer from '../ui/NotificationContainer';
import Modal from '../ui/Modal';

interface AppLayoutProps {
  children: React.ReactNode;
}

const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  const { ui } = useAppStore();
  const { sidebarCollapsed, modal } = ui;

  return (
    <div className="h-screen flex flex-col bg-gradient-to-br from-[#0ea5e912] via-white to-[#d946ef12]">
      {/* Header */}
      <Header />
      
      {/* Main Layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <Sidebar />
        
        {/* Main Content Area */}
        <div 
          className={cn(
            "flex-1 flex flex-col transition-all duration-300",
            sidebarCollapsed ? "ml-16" : "ml-64"
          )}
        >
          <MainContent>
            {children}
          </MainContent>
        </div>
      </div>
      
      {/* Notifications */}
      <NotificationContainer />
      
      {/* Modal */}
      {modal && <Modal />}
    </div>
  );
};

export default AppLayout;
