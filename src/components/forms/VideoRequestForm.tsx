'use client';

import React, { useEffect, useState } from 'react';
import type { Accept } from 'react-dropzone';
import { useAppStore } from '@/store/useAppStore';
import { VideoRequest, VideoStyle, AspectRatio } from '@/types';
import { ApiClient, type QuickCurrentRunResponse } from '@/lib/api';
import { getOrCreateQuickWorkspaceSessionId } from '@/lib/utils';
import {
  AlertCircle,
  FileText,
  Loader2,
  Music,
  Sparkles,
  Play,
  Settings
} from 'lucide-react';
import FileUploadZone from '../ui/FileUploadZone';
import StyleSelector from './StyleSelector';
import ParameterControls from './ParameterControls';
import { useI18n } from '@/i18n/I18nProvider';

const referenceUploadAccept: Accept = {
  'image/*': [],
  'video/*': [],
  'application/pdf': ['.pdf'],
  'application/msword': ['.doc'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
};

const VideoRequestForm: React.FC = () => {
  const {
    setCurrentRequest,
    setCurrentStep,
    setQuickRuntime,
    setQuickProcessingContext,
    addNotification,
  } = useAppStore();
  const { t } = useI18n();
  const [workspaceSessionId, setWorkspaceSessionId] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [resumingExistingRun, setResumingExistingRun] = useState(false);
  const [loadingExistingRun, setLoadingExistingRun] = useState(true);
  const [existingRun, setExistingRun] = useState<QuickCurrentRunResponse | null>(null);
  const [existingRunDismissed, setExistingRunDismissed] = useState(false);
  
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    duration: 30,
    resolution: '720p',
    aspectRatio: '16:9' as AspectRatio,
    style: null as VideoStyle | null,
    musicEnabled: true,
    musicSettings: {
      genre: 'corporate',
      mood: 'upbeat',
      volume: 0.3,
    },
  });

  const [, setUploadedFiles] = useState<File[]>([]);
  const [currentTab, setCurrentTab] = useState<'basic' | 'style' | 'music' | 'advanced'>('basic');
  const hasPendingRunChoice = !loadingExistingRun && !!existingRun?.task && !existingRunDismissed;
  const existingRunResumeControl = existingRun?.runtime?.resume_control;

  useEffect(() => {
    const currentSessionId = getOrCreateQuickWorkspaceSessionId();
    setWorkspaceSessionId(currentSessionId);

    let cancelled = false;

    const loadExistingRun = async () => {
      setLoadingExistingRun(true);
      try {
        const result = await ApiClient.getCurrentQuickRun(currentSessionId);
        if (!cancelled) {
          setExistingRun(result);
          setExistingRunDismissed(false);
        }
      } catch (error) {
        if (!cancelled) {
          console.error('Failed to discover current quick run:', error);
        }
      } finally {
        if (!cancelled) {
          setLoadingExistingRun(false);
        }
      }
    };

    void loadExistingRun();

    return () => {
      cancelled = true;
    };
  }, []);

  const mapQuickRunToRequest = (run: QuickCurrentRunResponse): VideoRequest | null => {
    if (!run.task) {
      return null;
    }

    const inputParameters = run.task.input_parameters || {};
    const rawPrompt = String(
      inputParameters.user_prompt ||
        run.task.description ||
        run.task.title ||
        ''
    );
    const lines = rawPrompt
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
    const title = lines[0] || run.task.title || '未命名任务';
    const description = lines.slice(1).join('\n\n') || rawPrompt || title;

    return {
      id: run.task.task_id,
      sessionId: run.task.session_id || workspaceSessionId,
      title,
      description,
      style: formData.style || {
        id: 'default',
        name: 'Default',
        description: 'Clean and professional style',
        thumbnail: '',
        category: 'corporate',
      },
      duration: Number(inputParameters.duration || 30),
      resolution: String(inputParameters.resolution || '720p'),
      aspectRatio: (String(inputParameters.aspect_ratio || '16:9') as AspectRatio),
      musicSettings: {
        enabled: true,
        genre: 'corporate',
        mood: 'upbeat',
        volume: 0.3,
      },
      createdAt: new Date(run.task.created_at),
      updatedAt: new Date(run.task.updated_at),
    };
  };

  const attachExistingRunToWorkspace = (
    run: QuickCurrentRunResponse,
    notification?: {
      type: 'success' | 'error' | 'warning' | 'info';
      title: string;
      message: string;
      autoClose?: number;
    } | null
  ) => {
    const request = mapQuickRunToRequest(run);
    if (!request) return;

    setExistingRunDismissed(true);
    setCurrentRequest(request);
    setQuickRuntime(run.runtime);
    setQuickProcessingContext('attached_runtime');
    setCurrentStep('processing');
    if (notification) {
      addNotification(notification);
    }
  };

  const handleViewExistingRun = () => {
    if (!existingRun) return;

    console.info('ATTACH_EXISTING_RUN_VIEW selected', { taskId: existingRun.task.task_id });
    attachExistingRunToWorkspace(existingRun, {
      type: 'info',
      title: '已恢复工作台视图',
      message: `当前正在查看任务 ${existingRun.task.task_id}；如需恢复后端执行，请使用明确的“恢复执行”按钮。`,
      autoClose: 4000,
    });
  };

  const handleResumeExistingRun = async () => {
    if (!existingRun) return;

    console.info('RESUME_EXISTING_RUN selected', { taskId: existingRun.task.task_id });
    attachExistingRunToWorkspace(existingRun, null);
    try {
      setResumingExistingRun(true);
      const result = await ApiClient.resumeTaskRuntime(existingRun.task.task_id);
      setQuickRuntime(result.runtime);
      setExistingRun(null);
      addNotification({
        type: 'success',
        title: '已请求恢复执行',
        message: `任务 ${existingRun.task.task_id} 已重新进入执行流程。`,
        autoClose: 3000,
      });
    } catch (error) {
      addNotification({
        type: 'error',
        title: '恢复执行失败',
        message: error instanceof Error ? error.message : '恢复执行失败，请稍后重试',
        autoClose: 6000,
      });
    } finally {
      setResumingExistingRun(false);
    }
  };

  const handleCreateNewRun = () => {
    console.info('CREATE_NEW_RUN selected', { sessionId: workspaceSessionId || existingRun?.task?.session_id || 'unknown' });
    setExistingRunDismissed(true);
    setQuickRuntime(null);
    setQuickProcessingContext(null);
    setCurrentRequest(null);
  };

  const handleInputChange = (field: string, value: any) => {
    setFormData(prev => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleNestedChange = (section: string, field: string, value: any) => {
    const sectionValue = (formData[section as keyof typeof formData] as Record<string, any>) || {};
    setFormData(prev => ({
      ...prev,
      [section]: {
        ...sectionValue,
        [field]: value,
      },
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;
    if (hasPendingRunChoice) {
      addNotification({
        type: 'warning',
        title: '请先选择任务操作',
        message: '请先选择查看当前任务、恢复执行，或点击“新建运行”后再提交新的测试 run。',
        autoClose: 5000,
      });
      return;
    }
    
    if (!formData.title.trim()) {
      addNotification({
        type: 'error',
        title: t('validation.error'),
        message: t('validation.titleRequired'),
        autoClose: 5000,
      });
      return;
    }

    if (!formData.description.trim()) {
      addNotification({
        type: 'error',
        title: t('validation.error'),
        message: t('validation.descriptionRequired'),
        autoClose: 5000,
      });
      return;
    }

    try {
      setIsSubmitting(true);
      setExistingRunDismissed(true);
      setQuickRuntime(null);
      setQuickProcessingContext(null);
      console.info('FORM_SUBMIT creating new quick task', {
        sessionId: workspaceSessionId || getOrCreateQuickWorkspaceSessionId(),
        title: formData.title,
      });
      // Create task via API
      const taskResponse = await ApiClient.createTask({
        user_prompt: `${formData.title}\n\n${formData.description}`,
        video_style: formData.style?.id || 'professional',
        duration: formData.duration,
        resolution: formData.resolution,
        aspect_ratio: formData.aspectRatio,
        session_id: workspaceSessionId || getOrCreateQuickWorkspaceSessionId(),
      });
      
      const request: VideoRequest = {
        id: taskResponse.task_id,
        sessionId: workspaceSessionId || getOrCreateQuickWorkspaceSessionId(),
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
        resolution: formData.resolution,
        aspectRatio: formData.aspectRatio,
        musicSettings: {
          enabled: formData.musicEnabled,
          ...formData.musicSettings,
        },
        createdAt: new Date(),
        updatedAt: new Date(),
      };

      setCurrentRequest(request);
      setQuickProcessingContext('fresh_submit');
      setCurrentStep('processing');
      setExistingRun(null);
      
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
      setQuickProcessingContext(null);
      setCurrentStep('input');
    } finally {
      setIsSubmitting(false);
    }
  };

  const tabs = [
    { id: 'basic', label: t('tabs.basic'), icon: FileText },
    { id: 'style', label: t('tabs.style'), icon: Sparkles },
    { id: 'music', label: t('tabs.music'), icon: Music },
    { id: 'advanced', label: t('tabs.advanced'), icon: Settings },
  ];

  return (
    <div className="w-full p-6">
      {/* Header */}
      <div className="mb-8">
        <h2 className="text-3xl font-bold text-gray-900 mb-2">
          {t('form.header')}
        </h2>
        <p className="text-gray-600">
          {t('form.subheader')}
        </p>
      </div>

      {hasPendingRunChoice && (
        <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-5 py-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-amber-700 mt-0.5" />
            <div className="flex-1">
              <div className="text-sm font-semibold text-amber-900">检测到未完成任务</div>
              <p className="mt-1 text-sm text-amber-800">
                当前 workspace 下存在一条未终态 run：`{existingRun.task.task_id}`。你可以先恢复工作台视图，再决定是否显式恢复后端执行；或者保留当前输入并启动一条新的测试 run。
              </p>
              {existingRunResumeControl?.state === 'resume_available' && (
                <p className="mt-2 text-xs text-amber-700">
                  检测结果：当前 run 存在合法 continuation checkpoint，control-plane 允许显式恢复执行。
                </p>
              )}
              {existingRunResumeControl?.state === 'resume_blocked' && (
                <p className="mt-2 text-xs text-amber-700">
                  检测结果：当前 run 缺少可消费的 continuation checkpoint，不能把“查看当前任务”当成恢复执行。
                </p>
              )}
              {existingRunResumeControl?.state === 'view_only_running' && (
                <p className="mt-2 text-xs text-amber-700">
                  检测结果：当前 run 仍被 control-plane 视为活跃，或恢复已进入调度中；“查看当前任务”只会重新附着工作台视图，不会触发新的后端执行。
                </p>
              )}
              <div className="mt-3 flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={handleViewExistingRun}
                  disabled={resumingExistingRun}
                  className="inline-flex items-center gap-2 rounded-lg bg-amber-700 px-4 py-2 text-sm font-medium text-white hover:bg-amber-800"
                >
                  查看当前任务
                </button>
                {existingRunResumeControl?.can_resume && (
                  <button
                    type="button"
                    onClick={() => void handleResumeExistingRun()}
                    disabled={resumingExistingRun}
                    className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-950 disabled:opacity-60"
                  >
                    {resumingExistingRun ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                    恢复执行
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleCreateNewRun}
                  disabled={resumingExistingRun}
                  className="inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-white px-4 py-2 text-sm font-medium text-amber-900 hover:bg-amber-100"
                >
                  新建运行
                </button>
              </div>
              <p className="mt-3 text-xs text-amber-700">
                在做出选择前，新的测试表单已被锁定，避免误触发表单提交创建额外 run。
              </p>
            </div>
          </div>
        </div>
      )}

      {!hasPendingRunChoice && (
        <>
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
                acceptedTypes={referenceUploadAccept}
                maxFiles={5}
                maxSize={10 * 1024 * 1024} // 10MB
              />
            </div>

            {/* Duration & Aspect Ratio */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
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
                  <option value={45}>{t('duration.45s')}</option>
                  <option value={60}>{t('duration.60s')}</option>
                  <option value={80}>{t('duration.80s')}</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {t('form.resolution')}
                </label>
                <select
                  value={formData.resolution}
                  onChange={(e) => handleInputChange('resolution', e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                >
                  <option value="720p">{t('resolution.720p')}</option>
                  <option value="1080p">{t('resolution.1080p')}</option>
                </select>
                <p className="text-xs text-gray-500 mt-1">{t('resolution.hint')}</p>
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

        {/* Music Tab */}
        {currentTab === 'music' && (
          <ParameterControls
            enabled={formData.musicEnabled}
            settings={{
              enabled: formData.musicEnabled,
              ...formData.musicSettings,
            }}
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
            disabled={isSubmitting}
            className="px-8 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors flex items-center space-x-2 font-medium disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            <span>{isSubmitting ? '提交中…' : t('form.btn.generate')}</span>
          </button>
        </div>
      </form>
        </>
      )}
    </div>
  );
};

export default VideoRequestForm;
