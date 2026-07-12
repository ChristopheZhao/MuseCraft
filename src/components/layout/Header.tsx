'use client';

import React from 'react';
import { useAppStore } from '@/store/useAppStore';
import { useI18n } from '@/i18n/I18nProvider';
import { 
  Menu, 
  ChevronLeft,
  Settings, 
  Bell, 
  User, 
  Zap,
  Video
} from 'lucide-react';

const Header: React.FC = () => {
  const { ui, wsConnected, setSidebarCollapsed, addNotification } = useAppStore();
  const { t, lang, setLang } = useI18n();
  const { sidebarCollapsed, notifications } = ui;

  const unreadCount = notifications.filter(n => n.type === 'info').length;

  const handleToggleSidebar = () => {
    setSidebarCollapsed(!sidebarCollapsed);
  };

  const handleNotificationClick = () => {
    addNotification({
      type: 'info',
      title: t('header.notifications'),
      message: t('header.noNotifications'),
      autoClose: 3000,
    });
  };

  return (
    <header className="h-16 bg-white/90 backdrop-blur border-b border-gray-200 flex items-center justify-between px-6 shadow-sm">
      {/* Left Section */}
      <div className="flex items-center space-x-4">
        <button
          onClick={handleToggleSidebar}
          className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
          aria-label={sidebarCollapsed ? t('header.toggleSidebar.expand') : t('header.toggleSidebar.collapse')}
          title={sidebarCollapsed ? t('header.toggleSidebar.expand') : t('header.toggleSidebar.collapse')}
        >
          {sidebarCollapsed ? (
            <Menu className="w-5 h-5 text-gray-600" />
          ) : (
            <ChevronLeft className="w-5 h-5 text-gray-600" />
          )}
        </button>
        
        <div className="flex items-center space-x-2">
          <div className="p-2 bg-gradient-to-br from-primary-500 to-accent-500 rounded-lg shadow-card">
            <Video className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              {t('brand.name')}
            </h1>
            <p className="text-xs text-gray-500">
              {t('brand.tagline')}
            </p>
          </div>
        </div>
      </div>

      {/* Center Section - Status Indicator */}
      <div
        className={[
          'hidden lg:flex items-center space-x-2 px-4 py-2 rounded-full border',
          wsConnected
            ? 'bg-gradient-to-r from-emerald-50 to-green-50 border-green-200'
            : 'bg-gradient-to-r from-amber-50 to-orange-50 border-amber-200',
        ].join(' ')}
      >
        <Zap className={wsConnected ? 'w-4 h-4 text-green-600' : 'w-4 h-4 text-amber-600'} />
        <span className="text-sm font-medium text-gray-700">
          {wsConnected ? t('status.ready') : '服务未连接'}
        </span>
        <div
          className={wsConnected ? 'w-2 h-2 bg-green-500 rounded-full animate-pulse' : 'w-2 h-2 bg-amber-500 rounded-full'}
        ></div>
      </div>

      {/* Right Section */}
      <div className="flex items-center space-x-3">
        {/* Notifications */}
        <button
          onClick={handleNotificationClick}
          className="relative p-2 rounded-lg hover:bg-gray-100 transition-colors"
          aria-label={t('header.notifications')}
          title={t('header.notifications')}
        >
          <Bell className="w-5 h-5 text-gray-600" />
          {unreadCount > 0 && (
            <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </button>

        {/* Language Toggle */}
        <div className="hidden md:flex items-center">
          <button
            onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
            className="px-3 py-1 text-xs rounded-full border border-gray-200 hover:bg-gray-100 text-gray-600"
            aria-label={t('header.language')}
            title={t('header.language')}
          >
            {lang === 'zh' ? '中文' : 'EN'}
          </button>
        </div>

        {/* Settings */}
        <button
          className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
          aria-label={t('header.settings')}
          title={t('header.settings')}
        >
          <Settings className="w-5 h-5 text-gray-600" />
        </button>

        {/* User Profile */}
        <div className="flex items-center space-x-3 pl-3 border-l border-gray-200">
          <div className="hidden sm:block text-right">
            <p className="text-sm font-medium text-gray-900">MuseCraft</p>
            <p className="text-xs text-gray-500">{lang === 'zh' ? '本地工作区' : 'Local workspace'}</p>
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
