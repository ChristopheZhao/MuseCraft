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

const VideoRequestForm: React.FC = () => {
  const { setCurrentRequest, setCurrentStep, addNotification } = useAppStore();
  
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
      language: 'en-US',
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
        title: 'Validation Error',
        message: 'Please provide a title for your video',
        autoClose: 5000,
      });
      return;
    }

    if (!formData.description.trim()) {
      console.log('❌ Validation failed: Missing description');
      addNotification({
        type: 'error',
        title: 'Validation Error',
        message: 'Please provide a description for your video',
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
        title: 'Submission Failed',
        message: error instanceof Error ? error.message : 'Failed to submit request',
        autoClose: 8000,
      });
    }
  };

  const tabs = [
    { id: 'basic', label: 'Basic Info', icon: FileText },
    { id: 'style', label: 'Style', icon: Sparkles },
    { id: 'voice', label: 'Voice', icon: Mic },
    { id: 'music', label: 'Music', icon: Music },
    { id: 'advanced', label: 'Advanced', icon: Settings },
  ];

  return (
    <div className="w-full max-w-4xl mx-auto p-6">
      {/* Header */}
      <div className="mb-8">
        <h2 className="text-3xl font-bold text-gray-900 mb-2">
          Create New Video
        </h2>
        <p className="text-gray-600">
          Provide details about your video requirements and let our AI agents create amazing content for you.
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
                Video Title *
              </label>
              <input
                type="text"
                value={formData.title}
                onChange={(e) => handleInputChange('title', e.target.value)}
                placeholder="Enter a compelling title for your video"
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-colors"
                required
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Description *
              </label>
              <textarea
                value={formData.description}
                onChange={(e) => handleInputChange('description', e.target.value)}
                placeholder="Describe what you want your video to be about. Be as detailed as possible to get the best results."
                rows={4}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-colors resize-none"
                required
              />
              <p className="text-sm text-gray-500 mt-1">
                {formData.description.length}/500 characters
              </p>
            </div>

            {/* File Upload */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Reference Materials (Optional)
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
                  Duration (seconds)
                </label>
                <select
                  value={formData.duration}
                  onChange={(e) => handleInputChange('duration', parseInt(e.target.value))}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                >
                  <option value={15}>15 seconds</option>
                  <option value={30}>30 seconds</option>
                  <option value={60}>1 minute</option>
                  <option value={90}>1.5 minutes</option>
                  <option value={120}>2 minutes</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Aspect Ratio
                </label>
                <select
                  value={formData.aspectRatio}
                  onChange={(e) => handleInputChange('aspectRatio', e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                >
                  <option value="16:9">16:9 (Landscape)</option>
                  <option value="9:16">9:16 (Portrait/Mobile)</option>
                  <option value="1:1">1:1 (Square)</option>
                  <option value="4:3">4:3 (Traditional)</option>
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
                <h3 className="font-medium text-yellow-800">Advanced Settings</h3>
              </div>
              <p className="text-sm text-yellow-700">
                Advanced configuration options will be available in future updates. 
                The current settings provide optimal results for most use cases.
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
            Save Draft
          </button>
          <button
            type="submit"
            className="px-8 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors flex items-center space-x-2 font-medium"
          >
            <Play className="w-4 h-4" />
            <span>Generate Video</span>
          </button>
        </div>
      </form>
    </div>
  );
};

export default VideoRequestForm;