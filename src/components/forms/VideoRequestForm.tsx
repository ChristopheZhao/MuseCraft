'use client';

import React, { useState } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { VideoRequest, VideoStyle, AspectRatio } from '@/types';
import { generateId } from '@/lib/utils';
import { ApiClient } from '@/lib/api';
import { 
  Upload, 
  Image, 
  FileText, 
  Mic, 
  Music,
  Sparkles,
  Play,
  Settings
} from 'lucide-react';
import FileUploadZone from '../ui/FileUploadZone';
import StyleSelector from './StyleSelector';
import ParameterControls from './ParameterControls';
import { useI18n } from '@/i18n/I18nProvider';

const VideoRequestForm: React.FC = () => {
  const { setCurrentRequest, setCurrentStep, addNotification } = useAppStore();
  const { t } = useI18n();
  
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    duration: 30,
    aspectRatio: '16:9' as AspectRatio,
    style: null as VideoStyle | null,
    voiceEnabled: true,
    voiceSettings: {
      voice: 'sarah',
      speed: 1.0,
      pitch: 1.0,
      language: 'zh-CN',
    },
    musicEnabled: true,
    musicSettings: {
      genre: 'corporate',
      mood: 'upbeat',
      volume: 0.3,
    },
  });

  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [currentTab, setCurrentTab] = useState<'basic' | 'style' | 'voice' | 'music' | 'advanced'>('basic');

  const handleInputChange = (field: string, value: any) => {
    setFormData(prev => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleNestedChange = (section: string, field: string, value: any) => {
    setFormData(prev => ({
      ...prev,
      [section]: {
        ...prev[section as keyof typeof prev],
        [field]: value,
      },
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    console.log('🎬 Form submission started');
    console.log('Current API URL:', process.env.NEXT_PUBLIC_API_URL);
    
    if (!formData.title.trim()) {
      console.log('❌ Validation failed: Missing title');
      addNotification({
        type: 'error',
        title: t('validation.error'),
        message: t('validation.titleRequired'),
        autoClose: 5000,
      });
      return;
    }

    if (!formData.description.trim()) {
      console.log('❌ Validation failed: Missing description');
      addNotification({
        type: 'error',
        title: t('validation.error'),
        message: t('validation.descriptionRequired'),
        autoClose: 5000,
      });
      return;
    }

    try {
      console.log('✅ Validation passed, submitting form with data:', formData);
      console.log('📡 About to call ApiClient.createTask...');
      
      // Create task via API
      const taskResponse = await ApiClient.createTask({
        user_prompt: `${formData.title}\n\n${formData.description}`,
        video_style: formData.style?.id || 'professional',
        duration: formData.duration,
        aspect_ratio: formData.aspectRatio,
        session_id: undefined, // Can be used for tracking
      });
      
      console.log('🎉 API call successful, response:', taskResponse);

      const request: VideoRequest = {
        id: taskResponse.task_id,
        title: formData.title,
        description: formData.description,
        style: formData.style || {
          id: 'default',
          name: 'Default',
          description: 'Clean and professional style',
          thumbnail: '',
          category: 'corporate',
        },
        duration: formData.duration,
        aspectRatio: formData.aspectRatio,
        voiceSettings: {
          enabled: formData.voiceEnabled,
          ...formData.voiceSettings,
        },
        musicSettings: {
          enabled: formData.musicEnabled,
          ...formData.musicSettings,
        },
        createdAt: new Date(),
        updatedAt: new Date(),
      };

      setCurrentRequest(request);
      setCurrentStep('processing');
      
      addNotification({
        type: 'success',
        title: 'Request Submitted',
        message: 'Your video generation request has been submitted successfully',
        autoClose: 3000,
      });
    } catch (error) {
      console.error('❌ API call failed:', error);
      console.error('Error details:', {
        message: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
      
      addNotification({
        type: 'error',
        title: t('notify.submitFailed.title'),
        message: error instanceof Error ? error.message : t('notify.submitFailed.msg'),
        autoClose: 8000,
      });
    }
  };

  const tabs = [
    { id: 'basic', label: t('tabs.basic'), icon: FileText },
    { id: 'style', label: t('tabs.style'), icon: Sparkles },
    { id: 'voice', label: t('tabs.voice'), icon: Mic },
    { id: 'music', label: t('tabs.music'), icon: Music },
    { id: 'advanced', label: t('tabs.advanced'), icon: Settings },
  ];

  return (
    <div className="w-full max-w-4xl mx-auto p-6">
      {/* Header */}
      <div className="mb-8">
        <h2 className="text-3xl font-bold text-gray-900 mb-2">
          {t('form.header')}
        </h2>
        <p className="text-gray-600">
          {t('form.subheader')}
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="flex space-x-1 bg-gray-100 p-1 rounded-lg mb-6">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setCurrentTab(tab.id as any)}
              className={`flex-1 flex items-center justify-center space-x-2 px-4 py-2 rounded-md transition-all ${
                currentTab === tab.id
                  ? 'bg-white text-primary-600 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span className="font-medium">{tab.label}</span>
            </button>
          );
        })}
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Basic Information Tab */}
        {currentTab === 'basic' && (
          <div className="space-y-6">
            {/* Title */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('form.title')} *
              </label>
              <input
                type="text"
                value={formData.title}
                onChange={(e) => handleInputChange('title', e.target.value)}
                placeholder={t('form.title.placeholder')}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-colors"
                required
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('form.description')} *
              </label>
              <textarea
                value={formData.description}
                onChange={(e) => handleInputChange('description', e.target.value)}
                placeholder={t('form.description.placeholder')}
                rows={4}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-colors resize-none"
                required
              />
              <p className="text-sm text-gray-500 mt-1">
                {formData.description.length}/500 {t('form.characters')}
              </p>
            </div>

            {/* File Upload */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('form.references')}
              </label>
              <FileUploadZone
                onFilesSelected={setUploadedFiles}
                acceptedTypes={['image/*', 'video/*', '.pdf', '.doc', '.docx']}
                maxFiles={5}
                maxSize={10 * 1024 * 1024} // 10MB
              />
            </div>

            {/* Duration & Aspect Ratio */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {t('form.duration')}
                </label>
                <select
                  value={formData.duration}
                  onChange={(e) => handleInputChange('duration', parseInt(e.target.value))}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                >
                  <option value={15}>{t('duration.15s')}</option>
                  <option value={30}>{t('duration.30s')}</option>
                  <option value={60}>{t('duration.60s')}</option>
                  <option value={90}>{t('duration.90s')}</option>
                  <option value={120}>{t('duration.120s')}</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {t('form.aspect')}
                </label>
                <select
                  value={formData.aspectRatio}
                  onChange={(e) => handleInputChange('aspectRatio', e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                >
                  <option value="16:9">{t('aspect.16_9')}</option>
                  <option value="9:16">{t('aspect.9_16')}</option>
                  <option value="1:1">{t('aspect.1_1')}</option>
                  <option value="4:3">{t('aspect.4_3')}</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {/* Style Tab */}
        {currentTab === 'style' && (
          <StyleSelector
            selectedStyle={formData.style}
            onStyleSelect={(style) => handleInputChange('style', style)}
          />
        )}

        {/* Voice Tab */}
        {currentTab === 'voice' && (
          <ParameterControls
            type="voice"
            enabled={formData.voiceEnabled}
            settings={formData.voiceSettings}
            onEnabledChange={(enabled) => handleInputChange('voiceEnabled', enabled)}
            onSettingsChange={(field, value) => handleNestedChange('voiceSettings', field, value)}
          />
        )}

        {/* Music Tab */}
        {currentTab === 'music' && (
          <ParameterControls
            type="music"
            enabled={formData.musicEnabled}
            settings={formData.musicSettings}
            onEnabledChange={(enabled) => handleInputChange('musicEnabled', enabled)}
            onSettingsChange={(field, value) => handleNestedChange('musicSettings', field, value)}
          />
        )}

        {/* Advanced Tab */}
        {currentTab === 'advanced' && (
          <div className="space-y-6">
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
              <div className="flex items-center space-x-2 mb-2">
                <Settings className="w-5 h-5 text-yellow-600" />
                <h3 className="font-medium text-yellow-800">{t('export.advanced')}</h3>
              </div>
              <p className="text-sm text-yellow-700">
                高级配置项将于后续版本开放；当前设置已针对大多数场景进行优化。
              </p>
            </div>
          </div>
        )}

        {/* Submit Button */}
        <div className="flex justify-end space-x-4 pt-6 border-t border-gray-200">
          <button
            type="button"
            className="px-6 py-3 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
          >
            {t('form.btn.save')}
          </button>
          <button
            type="submit"
            className="px-8 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors flex items-center space-x-2 font-medium"
          >
            <Play className="w-4 h-4" />
            <span>{t('form.btn.generate')}</span>
          </button>
        </div>
      </form>
    </div>
  );
};

export default VideoRequestForm;
