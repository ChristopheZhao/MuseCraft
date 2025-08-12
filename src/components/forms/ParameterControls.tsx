'use client';

import React from 'react';
import { VoiceSettings, MusicSettings } from '@/types';
import { cn } from '@/lib/utils';
import { Volume2, Mic, Play, Pause } from 'lucide-react';

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
  if (type === 'voice') {
    const voiceSettings = settings as VoiceSettings;
    
    const voices = [
      { id: 'sarah', name: 'Sarah', description: 'Professional female voice' },
      { id: 'david', name: 'David', description: 'Authoritative male voice' },
      { id: 'emma', name: 'Emma', description: 'Friendly female voice' },
      { id: 'james', name: 'James', description: 'Calm male voice' },
      { id: 'sophia', name: 'Sophia', description: 'Energetic female voice' },
      { id: 'alex', name: 'Alex', description: 'Neutral voice' },
    ];

    const languages = [
      { code: 'en-US', name: 'English (US)' },
      { code: 'en-GB', name: 'English (UK)' },
      { code: 'es-ES', name: 'Spanish' },
      { code: 'fr-FR', name: 'French' },
      { code: 'de-DE', name: 'German' },
      { code: 'it-IT', name: 'Italian' },
      { code: 'pt-BR', name: 'Portuguese' },
      { code: 'ja-JP', name: 'Japanese' },
      { code: 'ko-KR', name: 'Korean' },
      { code: 'zh-CN', name: 'Chinese (Simplified)' },
    ];

    return (
      <div className="space-y-6">
        {/* Enable/Disable Toggle */}
        <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
          <div className="flex items-center space-x-3">
            <Mic className="w-5 h-5 text-gray-600" />
            <div>
              <h3 className="font-medium text-gray-900">Voice Narration</h3>
              <p className="text-sm text-gray-600">
                Add AI-generated voice narration to your video
              </p>
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
            {/* Voice Selection */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-3">
                Voice Selection
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
                Language
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
                  Speech Speed: {voiceSettings.speed.toFixed(1)}x
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
                  <span>Slow</span>
                  <span>Normal</span>
                  <span>Fast</span>
                </div>
              </div>

              {/* Pitch */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Pitch: {voiceSettings.pitch.toFixed(1)}x
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
                  <span>Low</span>
                  <span>Normal</span>
                  <span>High</span>
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
    { id: 'corporate', name: 'Corporate' },
    { id: 'electronic', name: 'Electronic' },
    { id: 'acoustic', name: 'Acoustic' },
    { id: 'orchestral', name: 'Orchestral' },
    { id: 'ambient', name: 'Ambient' },
    { id: 'rock', name: 'Rock' },
    { id: 'jazz', name: 'Jazz' },
    { id: 'classical', name: 'Classical' },
  ];

  const moods = [
    { id: 'upbeat', name: 'Upbeat', description: 'Energetic and positive' },
    { id: 'calm', name: 'Calm', description: 'Peaceful and relaxing' },
    { id: 'dramatic', name: 'Dramatic', description: 'Intense and emotional' },
    { id: 'inspirational', name: 'Inspirational', description: 'Motivating and uplifting' },
    { id: 'mysterious', name: 'Mysterious', description: 'Dark and intriguing' },
    { id: 'playful', name: 'Playful', description: 'Fun and lighthearted' },
  ];

  return (
    <div className="space-y-6">
      {/* Enable/Disable Toggle */}
      <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
        <div className="flex items-center space-x-3">
          <Volume2 className="w-5 h-5 text-gray-600" />
          <div>
            <h3 className="font-medium text-gray-900">Background Music</h3>
            <p className="text-sm text-gray-600">
              Add AI-generated background music to enhance your video
            </p>
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
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Music Genre
            </label>
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
            <label className="block text-sm font-medium text-gray-700 mb-3">
              Mood & Atmosphere
            </label>
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
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Music Volume: {Math.round(musicSettings.volume * 100)}%
            </label>
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
              <span>Silent</span>
              <span>Background</span>
              <span>Prominent</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ParameterControls;