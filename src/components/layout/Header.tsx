'use client';

import React from 'react';
import { useAppStore } from '@/store/useAppStore';
import { 
  Menu, 
  X, 
  Settings, 
  Bell, 
  User, 
  Zap,
  Video
} from 'lucide-react';

const Header: React.FC = () => {
  const { ui, setSidebarCollapsed, addNotification } = useAppStore();
  const { sidebarCollapsed, notifications } = ui;

  const unreadCount = notifications.filter(n => n.type === 'info').length;

  const handleToggleSidebar = () => {
    setSidebarCollapsed(!sidebarCollapsed);
  };

  const handleNotificationClick = () => {
    addNotification({
      type: 'info',
      title: 'Notifications',
      message: 'No new notifications',
      autoClose: 3000,
    });
  };

  return (
    <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6 shadow-sm">
      {/* Left Section */}
      <div className="flex items-center space-x-4">
        <button
          onClick={handleToggleSidebar}
          className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
          aria-label="Toggle sidebar"
        >
          {sidebarCollapsed ? (
            <Menu className="w-5 h-5 text-gray-600" />
          ) : (
            <X className="w-5 h-5 text-gray-600" />
          )}
        </button>
        
        <div className="flex items-center space-x-2">
          <div className="p-2 bg-primary-500 rounded-lg">
            <Video className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              VideoMaker AI
            </h1>
            <p className="text-xs text-gray-500">
              Intelligent Video Generation Platform
            </p>
          </div>
        </div>
      </div>

      {/* Center Section - Status Indicator */}
      <div className="hidden lg:flex items-center space-x-2 px-4 py-2 bg-gray-50 rounded-full">
        <Zap className="w-4 h-4 text-green-500" />
        <span className="text-sm font-medium text-gray-700">
          System Ready
        </span>
        <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
      </div>

      {/* Right Section */}
      <div className="flex items-center space-x-3">
        {/* Notifications */}
        <button
          onClick={handleNotificationClick}
          className="relative p-2 rounded-lg hover:bg-gray-100 transition-colors"
          aria-label="Notifications"
        >
          <Bell className="w-5 h-5 text-gray-600" />
          {unreadCount > 0 && (
            <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </button>

        {/* Settings */}
        <button
          className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
          aria-label="Settings"
        >
          <Settings className="w-5 h-5 text-gray-600" />
        </button>

        {/* User Profile */}
        <div className="flex items-center space-x-3 pl-3 border-l border-gray-200">
          <div className="hidden sm:block text-right">
            <p className="text-sm font-medium text-gray-900">John Doe</p>
            <p className="text-xs text-gray-500">Pro Plan</p>
          </div>
          <button className="p-1 rounded-full bg-primary-100 hover:bg-primary-200 transition-colors">
            <User className="w-6 h-6 text-primary-600" />
          </button>
        </div>
      </div>
    </header>
  );
};

export default Header;