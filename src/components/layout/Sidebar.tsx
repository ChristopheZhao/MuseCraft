'use client';

import React from 'react';
import { useAppStore } from '@/store/useAppStore';
import { useI18n } from '@/i18n/I18nProvider';
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
  const { t } = useI18n();
  const { sidebarCollapsed, currentStep } = ui;

  const navigationItems: NavigationItem[] = [
    {
      id: 'dashboard',
      label: t('nav.dashboard'),
      icon: Home,
      active: currentStep === 'input',
    },
    {
      id: 'projects',
      label: t('nav.projects'),
      icon: FileText,
    },
    {
      id: 'templates',
      label: t('nav.templates'),
      icon: Sparkles,
    },
    {
      id: 'media',
      label: t('nav.media'),
      icon: Image,
    },
    {
      id: 'videos',
      label: t('nav.videos'),
      icon: Video,
    },
    {
      id: 'analytics',
      label: t('nav.analytics'),
      icon: BarChart3,
    },
    {
      id: 'history',
      label: t('nav.history'),
      icon: History,
    },
  ];

  const bottomItems: NavigationItem[] = [
    {
      id: 'help',
      label: t('nav.help'),
      icon: HelpCircle,
    },
    {
      id: 'settings',
      label: t('nav.settings'),
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
          
        </nav>

        {/* Bottom Navigation */}
        <div className="border-t border-gray-200 p-3 space-y-1">
          {bottomItems.map(renderNavigationItem)}
        </div>

      </div>
    </aside>
  );
};

export default Sidebar;
