'use client';

import React from 'react';
import { MusicSettings } from '@/types';
import { cn } from '@/lib/utils';
import { Volume2 } from 'lucide-react';
import { useI18n } from '@/i18n/I18nProvider';

interface ParameterControlsProps {
  enabled: boolean;
  settings: MusicSettings;
  onEnabledChange: (enabled: boolean) => void;
  onSettingsChange: (field: string, value: any) => void;
}

const ParameterControls: React.FC<ParameterControlsProps> = ({
  enabled,
  settings,
  onEnabledChange,
  onSettingsChange,
}) => {
  const { t } = useI18n();
  const musicSettings = settings;
  
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
