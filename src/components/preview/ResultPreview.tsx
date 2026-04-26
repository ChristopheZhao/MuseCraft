'use client';

import React, { useState } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { GenerationResult, ResultType } from '@/types';
import { cn, formatRelativeTime } from '@/lib/utils';
import { 
  Eye, 
  Download, 
  Edit3, 
  ThumbsUp, 
  ThumbsDown,
  Image,
  FileText,
  Mic,
  Video,
  Lightbulb,
  Grid,
  Layers,
  RefreshCw,
  ExternalLink,
  Clock
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useI18n } from '@/i18n/I18nProvider';

interface ResultPreviewProps {
  className?: string;
}

const ResultPreview: React.FC<ResultPreviewProps> = ({ className }) => {
  const { results } = useAppStore();
  const [selectedType, setSelectedType] = useState<ResultType | 'all'>('all');
  const [, setSelectedResult] = useState<GenerationResult | null>(null);
  const { t } = useI18n();

  const resultTypes: { id: ResultType | 'all'; label: string; icon: React.ElementType; count: number }[] = [
    { 
      id: 'all', 
      label: t('results.all'), 
      icon: Grid, 
      count: results.length 
    },
    { 
      id: 'concept', 
      label: t('results.concepts'), 
      icon: Lightbulb, 
      count: results.filter(r => r.type === 'concept').length 
    },
    { 
      id: 'script', 
      label: t('results.scripts'), 
      icon: FileText, 
      count: results.filter(r => r.type === 'script').length 
    },
    { 
      id: 'storyboard', 
      label: t('results.storyboards'), 
      icon: Layers, 
      count: results.filter(r => r.type === 'storyboard').length 
    },
    { 
      id: 'image', 
      label: t('results.images'), 
      icon: Image, 
      count: results.filter(r => r.type === 'image').length 
    },
    { 
      id: 'voice', 
      label: t('results.voice'), 
      icon: Mic, 
      count: results.filter(r => r.type === 'voice').length 
    },
    { 
      id: 'video', 
      label: t('results.videos'), 
      icon: Video, 
      count: results.filter(r => r.type === 'video').length 
    },
  ];

  const filteredResults = selectedType === 'all' 
    ? results 
    : results.filter(r => r.type === selectedType);

  const getResultIcon = (type: ResultType) => {
    const iconProps = { className: "w-5 h-5" };
    
    switch (type) {
      case 'concept':
        return <Lightbulb {...iconProps} />;
      case 'script':
        return <FileText {...iconProps} />;
      case 'storyboard':
        return <Layers {...iconProps} />;
      case 'image':
        return <Image {...iconProps} />;
      case 'voice':
        return <Mic {...iconProps} />;
      case 'video':
        return <Video {...iconProps} />;
      default:
        return <FileText {...iconProps} />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'text-green-600 bg-green-50 border-green-200';
      case 'processing':
        return 'text-blue-600 bg-blue-50 border-blue-200';
      case 'failed':
        return 'text-red-600 bg-red-50 border-red-200';
      default:
        return 'text-gray-600 bg-gray-50 border-gray-200';
    }
  };

  const renderResultContent = (result: GenerationResult) => {
    switch (result.type) {
      case 'concept':
        return (
          <div className="space-y-3">
            <h4 className="font-medium text-gray-900">
              {result.data?.title || '概念想法'}
            </h4>
            <p className="text-sm text-gray-600 leading-relaxed">
              {result.data?.description || '概念描述将显示在这里…'}
            </p>
            {result.data?.keyPoints && (
              <ul className="text-sm text-gray-600 space-y-1">
                {result.data.keyPoints.map((point: string, index: number) => (
                  <li key={index} className="flex items-start space-x-2">
                    <span className="text-primary-500 mt-1">•</span>
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );

      case 'script':
        return (
          <div className="space-y-3">
            <h4 className="font-medium text-gray-900">
              剧本预览
            </h4>
            <div className="bg-gray-50 rounded-lg p-3 font-mono text-sm">
              <pre className="whitespace-pre-wrap text-gray-700">
                {result.data?.content || '剧本内容将显示在这里…'}
              </pre>
            </div>
            {result.data?.duration && (
              <p className="text-xs text-gray-500">
                预计时长：{result.data.duration}s
              </p>
            )}
          </div>
        );

      case 'image':
        return (
          <div className="space-y-3">
            <h4 className="font-medium text-gray-900">
              生成图片
            </h4>
            <div className="aspect-video bg-gradient-to-br from-gray-100 to-gray-200 rounded-lg flex items-center justify-center">
              <div className="text-center">
                <Image className="w-12 h-12 text-gray-400 mx-auto mb-2" />
                <p className="text-sm text-gray-500">
                  {result.data?.prompt || '图片预览'}
                </p>
              </div>
            </div>
            {result.data?.style && (
              <p className="text-xs text-gray-500">
                风格：{result.data.style}
              </p>
            )}
          </div>
        );

      case 'voice':
        return (
          <div className="space-y-3">
            <h4 className="font-medium text-gray-900">
              配音音频
            </h4>
            <div className="bg-gray-50 rounded-lg p-4 flex items-center space-x-3">
              <Mic className="w-8 h-8 text-primary-500" />
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-900">
                  音轨 {result.data?.trackNumber || 1}
                </p>
                <p className="text-xs text-gray-500">
                  {result.data?.duration || '30'}s • {result.data?.voice || 'Sarah'}
                </p>
              </div>
              <button className="p-2 bg-primary-100 text-primary-600 rounded-lg hover:bg-primary-200 transition-colors">
                <Eye className="w-4 h-4" />
              </button>
            </div>
          </div>
        );

      default:
        return (
          <div className="text-sm text-gray-600">
            {result.data?.preview || '暂无可预览内容'}
          </div>
        );
    }
  };

  if (results.length === 0) {
    return (
      <div className={cn("p-8 text-center", className)}>
        <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <Eye className="w-8 h-8 text-gray-400" />
        </div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">{t('results.none.title')}</h3>
        <p className="text-gray-600">{t('results.none.desc')}</p>
      </div>
    );
  }

  return (
    <div className={cn("space-y-6", className)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">{t('results.title')}</h3>
          <p className="text-sm text-gray-600">{t('results.subtitle')}</p>
        </div>
        <button className="flex items-center space-x-2 px-3 py-2 text-sm bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors">
          <RefreshCw className="w-4 h-4" />
          <span>{t('results.refresh')}</span>
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex space-x-1 bg-gray-100 p-1 rounded-lg overflow-x-auto">
        {resultTypes.map((type) => {
          const Icon = type.icon;
          return (
            <button
              key={type.id}
              onClick={() => setSelectedType(type.id)}
              className={cn(
                "flex items-center space-x-2 px-3 py-2 rounded-md transition-all whitespace-nowrap",
                selectedType === type.id
                  ? "bg-white text-primary-600 shadow-sm"
                  : "text-gray-600 hover:text-gray-900"
              )}
            >
              <Icon className="w-4 h-4" />
              <span className="font-medium">{type.label}</span>
              {type.count > 0 && (
                <span className={cn(
                  "px-1.5 py-0.5 text-xs rounded-full",
                  selectedType === type.id
                    ? "bg-primary-100 text-primary-700"
                    : "bg-gray-200 text-gray-600"
                )}>
                  {type.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Results Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AnimatePresence>
          {filteredResults.map((result) => (
            <motion.div
              key={result.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="bg-white border border-gray-200 rounded-xl p-6 hover:shadow-md transition-shadow"
            >
              {/* Result Header */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-gray-100 rounded-lg">
                    {getResultIcon(result.type)}
                  </div>
                  <div>
                    <h4 className="font-medium text-gray-900 capitalize">
                      {result.type}
                    </h4>
                    <div className="flex items-center space-x-2 text-xs text-gray-500">
                      <span>来自 {result.agent}</span>
                      <span>•</span>
                      <Clock className="w-3 h-3" />
                      <span>{formatRelativeTime(result.createdAt)}</span>
                    </div>
                  </div>
                </div>
                
                <div className="flex items-center space-x-2">
                  <span className={cn(
                    "px-2 py-1 text-xs font-medium rounded-full border",
                    getStatusColor(result.status)
                  )}>
                    {result.status}
                  </span>
                  {result.confidence && (
                    <span className="text-xs text-gray-500">
                      {Math.round(result.confidence * 100)}%
                    </span>
                  )}
                </div>
              </div>

              {/* Result Content */}
              <div className="mb-4">
                {renderResultContent(result)}
              </div>

              {/* Result Actions */}
              <div className="flex items-center justify-between pt-4 border-t border-gray-100">
                <div className="flex items-center space-x-2">
                  <button className="flex items-center space-x-1 px-2 py-1 text-xs text-gray-600 hover:text-green-600 transition-colors">
                    <ThumbsUp className="w-3 h-3" />
                    <span>{t('action.approve')}</span>
                  </button>
                  <button className="flex items-center space-x-1 px-2 py-1 text-xs text-gray-600 hover:text-red-600 transition-colors">
                    <ThumbsDown className="w-3 h-3" />
                    <span>{t('action.reject')}</span>
                  </button>
                </div>
                
                <div className="flex items-center space-x-2">
                  <button className="p-1.5 text-gray-400 hover:text-gray-600 transition-colors">
                    <Edit3 className="w-4 h-4" />
                  </button>
                  <button className="p-1.5 text-gray-400 hover:text-gray-600 transition-colors">
                    <Download className="w-4 h-4" />
                  </button>
                  <button 
                    onClick={() => setSelectedResult(result)}
                    className="p-1.5 text-gray-400 hover:text-primary-600 transition-colors"
                  >
                    <ExternalLink className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Empty State for Filtered Results */}
      {filteredResults.length === 0 && selectedType !== 'all' && (
        <div className="text-center py-12">
          <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
            {getResultIcon(selectedType as ResultType)}
          </div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">
            {t('results.filter.none.title').replace('{type}', String(selectedType))}
          </h3>
          <p className="text-gray-600">
            {t('results.filter.none.desc').replace('{type}', String(selectedType))}
          </p>
        </div>
      )}
    </div>
  );
};

export default ResultPreview;
