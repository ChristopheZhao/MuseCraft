'use client';

import React from 'react';
import { VoiceSettings, MusicSettings } from '@/types';
import { cn } from '@/lib/utils';
import { Volume2, Mic, Play, Pause } from 'lucide-react';
import { useI18n } from '@/i18n/I18nProvider';

interface ParameterControlsProps {
  type: 'voice' | 'music';
  enabled: boolean;
  settings: VoiceSettings | MusicSettings;
  onEnabledChange: (enabled: boolean) => void;
  onSettingsChange: (field: string, value: any) => void;
}

const ParameterControls: React.FC<ParameterControlsProps> = ({
  type,
  enabled,
  settings,
  onEnabledChange,
  onSettingsChange,
}) => {
  const { t } = useI18n();
  if (type === 'voice') {
    const voiceSettings = settings as VoiceSettings;
    
    const voices = [
      { id: 'sarah', name: 'Sarah', description: '专业女声' },
      { id: 'david', name: 'David', description: '浑厚男声' },
      { id: 'emma', name: 'Emma', description: '亲切女声' },
      { id: 'james', name: 'James', description: '沉稳男声' },
      { id: 'sophia', name: 'Sophia', description: '活力女声' },
      { id: 'alex', name: 'Alex', description: '中性声音' },
    ];

    const languages = [
      { code: 'en-US', name: '英语（美国）' },
      { code: 'en-GB', name: '英语（英国）' },
      { code: 'es-ES', name: '西班牙语' },
      { code: 'fr-FR', name: '法语' },
      { code: 'de-DE', name: '德语' },
      { code: 'it-IT', name: '意大利语' },
      { code: 'pt-BR', name: '葡萄牙语' },
      { code: 'ja-JP', name: '日语' },
      { code: 'ko-KR', name: '韩语' },
      { code: 'zh-CN', name: '中文（简体）' },
    ];

    return (
      <div className="space-y-6">
        {/* Enable/Disable Toggle */}
        <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
          <div className="flex items-center space-x-3">
            <Mic className="w-5 h-5 text-gray-600" />
            <div>
              <h3 className="font-medium text-gray-900">{t('voice.title')}</h3>
              <p className="text-sm text-gray-600">{t('voice.subtitle')}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => onEnabledChange(!enabled)}
            className={cn(
              "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
              enabled ? "bg-primary-600" : "bg-gray-200"
            )}
          >
            <span
              className={cn(
                "inline-block h-4 w-4 transform rounded-full bg-white transition-transform",
                enabled ? "translate-x-6" : "translate-x-1"
              )}
            />
          </button>
        </div>

        {enabled && (
          <div className="space-y-6">
            {/* Voice Selection */
            }
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-3">
                {t('voice.selection')}
              </label>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {voices.map((voice) => (
                  <button
                    key={voice.id}
                    type="button"
                    onClick={() => onSettingsChange('voice', voice.id)}
                    className={cn(
                      "p-3 rounded-lg border-2 transition-all text-left",
                      voiceSettings.voice === voice.id
                        ? "border-primary-500 bg-primary-50"
                        : "border-gray-200 hover:border-gray-300"
                    )}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-gray-900">
                        {voice.name}
                      </span>
                      <Play className="w-4 h-4 text-gray-400" />
                    </div>
                    <p className="text-sm text-gray-600">
                      {voice.description}
                    </p>
                  </button>
                ))}
              </div>
            </div>

            {/* Language Selection */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('voice.language')}
              </label>
              <select
                value={voiceSettings.language}
                onChange={(e) => onSettingsChange('language', e.target.value)}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              >
                {languages.map((lang) => (
                  <option key={lang.code} value={lang.code}>
                    {lang.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Voice Parameters */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Speed */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {t('voice.speed')}: {voiceSettings.speed.toFixed(1)}x
                </label>
                <input
                  type="range"
                  min="0.5"
                  max="2.0"
                  step="0.1"
                  value={voiceSettings.speed}
                  onChange={(e) => onSettingsChange('speed', parseFloat(e.target.value))}
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>{t('voice.speed.slow')}</span>
                  <span>{t('voice.speed.normal')}</span>
                  <span>{t('voice.speed.fast')}</span>
                </div>
              </div>

              {/* Pitch */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {t('voice.pitch')}: {voiceSettings.pitch.toFixed(1)}x
                </label>
                <input
                  type="range"
                  min="0.5"
                  max="2.0"
                  step="0.1"
                  value={voiceSettings.pitch}
                  onChange={(e) => onSettingsChange('pitch', parseFloat(e.target.value))}
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>{t('voice.pitch.low')}</span>
                  <span>{t('voice.speed.normal')}</span>
                  <span>{t('voice.pitch.high')}</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // Music controls
  const musicSettings = settings as MusicSettings;
  
  const genres = [
    { id: 'corporate', name: '商务' },
    { id: 'electronic', name: '电子' },
    { id: 'acoustic', name: '原声' },
    { id: 'orchestral', name: '管弦' },
    { id: 'ambient', name: '氛围' },
    { id: 'rock', name: '摇滚' },
    { id: 'jazz', name: '爵士' },
    { id: 'classical', name: '古典' },
  ];

  const moods = [
    { id: 'upbeat', name: '轻快', description: '充满活力与积极性' },
    { id: 'calm', name: '平静', description: '宁静与放松' },
    { id: 'dramatic', name: '戏剧', description: '紧张而富有情绪' },
    { id: 'inspirational', name: '励志', description: '激励与振奋' },
    { id: 'mysterious', name: '神秘', description: '暗黑且耐人寻味' },
    { id: 'playful', name: '俏皮', description: '有趣而轻松' },
  ];

  return (
    <div className="space-y-6">
      {/* Enable/Disable Toggle */}
      <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
          <div className="flex items-center space-x-3">
            <Volume2 className="w-5 h-5 text-gray-600" />
            <div>
            <h3 className="font-medium text-gray-900">{t('music.title')}</h3>
            <p className="text-sm text-gray-600">{t('music.subtitle')}</p>
            </div>
          </div>
        <button
          type="button"
          onClick={() => onEnabledChange(!enabled)}
          className={cn(
            "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
            enabled ? "bg-primary-600" : "bg-gray-200"
          )}
        >
          <span
            className={cn(
              "inline-block h-4 w-4 transform rounded-full bg-white transition-transform",
              enabled ? "translate-x-6" : "translate-x-1"
            )}
          />
        </button>
      </div>

      {enabled && (
        <div className="space-y-6">
          {/* Genre Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('music.genre')}</label>
            <select
              value={musicSettings.genre}
              onChange={(e) => onSettingsChange('genre', e.target.value)}
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            >
              {genres.map((genre) => (
                <option key={genre.id} value={genre.id}>
                  {genre.name}
                </option>
              ))}
            </select>
          </div>

          {/* Mood Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-3">{t('music.mood')}</label>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {moods.map((mood) => (
                <button
                  key={mood.id}
                  type="button"
                  onClick={() => onSettingsChange('mood', mood.id)}
                  className={cn(
                    "p-3 rounded-lg border-2 transition-all text-left",
                    musicSettings.mood === mood.id
                      ? "border-primary-500 bg-primary-50"
                      : "border-gray-200 hover:border-gray-300"
                  )}
                >
                  <div className="font-medium text-gray-900 mb-1">
                    {mood.name}
                  </div>
                  <p className="text-sm text-gray-600">
                    {mood.description}
                  </p>
                </button>
              ))}
            </div>
          </div>

          {/* Volume Control */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('music.volume')}: {Math.round(musicSettings.volume * 100)}%</label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={musicSettings.volume}
              onChange={(e) => onSettingsChange('volume', parseFloat(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>{t('music.volume.silent')}</span>
              <span>{t('music.volume.background')}</span>
              <span>{t('music.volume.prominent')}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ParameterControls;
