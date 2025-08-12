'use client';

import React from 'react';
import { useAppStore } from '@/store/useAppStore';
import { cn } from '@/lib/utils';
import { 
  Home,
  FileText,
  Image,
  Video,
  Settings,
  History,
  BarChart3,
  HelpCircle,
  Sparkles
} from 'lucide-react';

interface NavigationItem {
  id: string;
  label: string;
  icon: React.ElementType;
  badge?: string;
  active?: boolean;
}

const Sidebar: React.FC = () => {
  const { ui } = useAppStore();
  const { sidebarCollapsed, currentStep } = ui;

  const navigationItems: NavigationItem[] = [
    {
      id: 'dashboard',
      label: 'Dashboard',
      icon: Home,
      active: currentStep === 'input',
    },
    {
      id: 'projects',
      label: 'My Projects',
      icon: FileText,
      badge: '3',
    },
    {
      id: 'templates',
      label: 'Templates',
      icon: Sparkles,
    },
    {
      id: 'media',
      label: 'Media Library',
      icon: Image,
    },
    {
      id: 'videos',
      label: 'Generated Videos',
      icon: Video,
      badge: '12',
    },
    {
      id: 'analytics',
      label: 'Analytics',
      icon: BarChart3,
    },
    {
      id: 'history',
      label: 'History',
      icon: History,
    },
  ];

  const bottomItems: NavigationItem[] = [
    {
      id: 'help',
      label: 'Help & Support',
      icon: HelpCircle,
    },
    {
      id: 'settings',
      label: 'Settings',
      icon: Settings,
    },
  ];

  const renderNavigationItem = (item: NavigationItem) => {
    const Icon = item.icon;
    
    return (
      <button
        key={item.id}
        className={cn(
          "w-full flex items-center space-x-3 px-3 py-2.5 rounded-lg transition-all duration-200",
          "hover:bg-primary-50 hover:text-primary-700 group",
          item.active 
            ? "bg-primary-100 text-primary-700 shadow-sm" 
            : "text-gray-600 hover:text-gray-900",
          sidebarCollapsed && "justify-center px-2"
        )}
        title={sidebarCollapsed ? item.label : undefined}
      >
        <Icon className={cn(
          "flex-shrink-0 transition-colors",
          item.active ? "text-primary-600" : "text-gray-500 group-hover:text-primary-600",
          sidebarCollapsed ? "w-6 h-6" : "w-5 h-5"
        )} />
        
        {!sidebarCollapsed && (
          <>
            <span className="flex-1 text-left font-medium">
              {item.label}
            </span>
            {item.badge && (
              <span className="px-2 py-0.5 text-xs font-medium bg-primary-100 text-primary-700 rounded-full">
                {item.badge}
              </span>
            )}
          </>
        )}
      </button>
    );
  };

  return (
    <aside 
      className={cn(
        "fixed left-0 top-16 h-[calc(100vh-4rem)] bg-white border-r border-gray-200 transition-all duration-300 z-10",
        sidebarCollapsed ? "w-16" : "w-64"
      )}
    >
      <div className="flex flex-col h-full">
        {/* Main Navigation */}
        <nav className="flex-1 px-3 py-6 space-y-1">
          {navigationItems.map(renderNavigationItem)}
          
          {/* Divider */}
          <div className="my-6 border-t border-gray-200" />
          
          {/* AI Agents Status - Collapsed View */}
          {sidebarCollapsed && (
            <div className="px-2">
              <div className="w-full flex flex-col items-center space-y-2 p-2 bg-gray-50 rounded-lg">
                <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse" />
                <div className="w-3 h-3 bg-blue-500 rounded-full animate-pulse" />
                <div className="w-3 h-3 bg-yellow-500 rounded-full animate-pulse" />
              </div>
            </div>
          )}
          
          {/* AI Agents Status - Expanded View */}
          {!sidebarCollapsed && (
            <div className="space-y-2">
              <h3 className="px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                AI Agents
              </h3>
              <div className="space-y-1">
                <div className="flex items-center space-x-2 px-3 py-2">
                  <div className="w-2 h-2 bg-green-500 rounded-full" />
                  <span className="text-sm text-gray-600">Concept Generator</span>
                </div>
                <div className="flex items-center space-x-2 px-3 py-2">
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
                  <span className="text-sm text-gray-600">Script Writer</span>
                </div>
                <div className="flex items-center space-x-2 px-3 py-2">
                  <div className="w-2 h-2 bg-gray-300 rounded-full" />
                  <span className="text-sm text-gray-400">Visual Creator</span>
                </div>
              </div>
            </div>
          )}
        </nav>

        {/* Bottom Navigation */}
        <div className="border-t border-gray-200 p-3 space-y-1">
          {bottomItems.map(renderNavigationItem)}
        </div>

        {/* Usage Stats - Only show when expanded */}
        {!sidebarCollapsed && (
          <div className="p-4 bg-gradient-to-r from-primary-50 to-accent-50 m-3 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-gray-600">
                Credits Used
              </span>
              <span className="text-xs text-gray-500">
                1,240 / 2,000
              </span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div 
                className="bg-gradient-to-r from-primary-500 to-accent-500 h-2 rounded-full" 
                style={{ width: '62%' }}
              />
            </div>
            <button className="w-full mt-3 text-xs text-primary-600 hover:text-primary-700 font-medium">
              Upgrade Plan
            </button>
          </div>
        )}
      </div>
    </aside>
  );
};

export default Sidebar;