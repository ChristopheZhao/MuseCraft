'use client';

import React, { useState } from 'react';
import { VideoStyle, StyleCategory } from '@/types';
import { cn } from '@/lib/utils';
import { Check, Sparkles } from 'lucide-react';

interface StyleSelectorProps {
  selectedStyle: VideoStyle | null;
  onStyleSelect: (style: VideoStyle) => void;
}

const StyleSelector: React.FC<StyleSelectorProps> = ({
  selectedStyle,
  onStyleSelect,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<StyleCategory>('corporate');

  const categories: { id: StyleCategory; label: string; description: string }[] = [
    {
      id: 'corporate',
      label: 'Corporate',
      description: 'Professional and business-focused styles',
    },
    {
      id: 'creative',
      label: 'Creative',
      description: 'Artistic and unique visual approaches',
    },
    {
      id: 'educational',
      label: 'Educational',
      description: 'Clear and informative presentation styles',
    },
    {
      id: 'entertainment',
      label: 'Entertainment',
      description: 'Fun and engaging visual styles',
    },
    {
      id: 'marketing',
      label: 'Marketing',
      description: 'Promotional and advertising-focused styles',
    },
    {
      id: 'social',
      label: 'Social Media',
      description: 'Optimized for social platforms',
    },
  ];

  const styles: Record<StyleCategory, VideoStyle[]> = {
    corporate: [
      {
        id: 'corporate-clean',
        name: 'Clean Corporate',
        description: 'Minimalist design with professional typography and subtle animations',
        thumbnail: '/styles/corporate-clean.jpg',
        category: 'corporate',
      },
      {
        id: 'corporate-modern',
        name: 'Modern Business',
        description: 'Contemporary corporate style with dynamic transitions',
        thumbnail: '/styles/corporate-modern.jpg',
        category: 'corporate',
      },
      {
        id: 'corporate-elegant',
        name: 'Executive',
        description: 'Sophisticated and refined visual presentation',
        thumbnail: '/styles/corporate-elegant.jpg',
        category: 'corporate',
      },
    ],
    creative: [
      {
        id: 'creative-artistic',
        name: 'Artistic Vision',
        description: 'Hand-drawn elements with organic transitions',
        thumbnail: '/styles/creative-artistic.jpg',
        category: 'creative',
      },
      {
        id: 'creative-abstract',
        name: 'Abstract Forms',
        description: 'Geometric shapes and abstract visual metaphors',
        thumbnail: '/styles/creative-abstract.jpg',
        category: 'creative',
      },
      {
        id: 'creative-vintage',
        name: 'Retro Charm',
        description: 'Vintage-inspired design with nostalgic elements',
        thumbnail: '/styles/creative-vintage.jpg',
        category: 'creative',
      },
    ],
    educational: [
      {
        id: 'educational-clear',
        name: 'Clear Learning',
        description: 'Simple, focused design that enhances comprehension',
        thumbnail: '/styles/educational-clear.jpg',
        category: 'educational',
      },
      {
        id: 'educational-interactive',
        name: 'Interactive Guide',
        description: 'Engaging elements that encourage active learning',
        thumbnail: '/styles/educational-interactive.jpg',
        category: 'educational',
      },
    ],
    entertainment: [
      {
        id: 'entertainment-dynamic',
        name: 'High Energy',
        description: 'Fast-paced animations with vibrant colors',
        thumbnail: '/styles/entertainment-dynamic.jpg',
        category: 'entertainment',
      },
      {
        id: 'entertainment-playful',
        name: 'Playful Fun',
        description: 'Whimsical design with animated characters',
        thumbnail: '/styles/entertainment-playful.jpg',
        category: 'entertainment',
      },
    ],
    marketing: [
      {
        id: 'marketing-bold',
        name: 'Bold Impact',
        description: 'Eye-catching design that demands attention',
        thumbnail: '/styles/marketing-bold.jpg',
        category: 'marketing',
      },
      {
        id: 'marketing-conversion',
        name: 'Conversion Focus',
        description: 'Optimized for driving action and engagement',
        thumbnail: '/styles/marketing-conversion.jpg',
        category: 'marketing',
      },
    ],
    social: [
      {
        id: 'social-trending',
        name: 'Social Trending',
        description: 'Current social media visual trends',
        thumbnail: '/styles/social-trending.jpg',
        category: 'social',
      },
      {
        id: 'social-story',
        name: 'Story Format',
        description: 'Optimized for story-style content',
        thumbnail: '/styles/social-story.jpg',
        category: 'social',
      },
    ],
  };

  const currentStyles = styles[selectedCategory] || [];

  return (
    <div className="space-y-6">
      {/* Category Selection */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Choose a Category
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {categories.map((category) => (
            <button
              key={category.id}
              onClick={() => setSelectedCategory(category.id)}
              className={cn(
                "p-4 rounded-lg border-2 transition-all text-left",
                selectedCategory === category.id
                  ? "border-primary-500 bg-primary-50"
                  : "border-gray-200 hover:border-gray-300 bg-white"
              )}
            >
              <h4 className="font-medium text-gray-900 mb-1">
                {category.label}
              </h4>
              <p className="text-sm text-gray-600">
                {category.description}
              </p>
            </button>
          ))}
        </div>
      </div>

      {/* Style Selection */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Select a Style
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {currentStyles.map((style) => (
            <div
              key={style.id}
              onClick={() => onStyleSelect(style)}
              className={cn(
                "relative cursor-pointer rounded-lg border-2 transition-all group",
                selectedStyle?.id === style.id
                  ? "border-primary-500 shadow-lg"
                  : "border-gray-200 hover:border-gray-300 hover:shadow-md"
              )}
            >
              {/* Thumbnail */}
              <div className="aspect-video bg-gradient-to-br from-gray-100 to-gray-200 rounded-t-lg relative overflow-hidden">
                <div className="absolute inset-0 flex items-center justify-center">
                  <Sparkles className="w-8 h-8 text-gray-400" />
                </div>
                {/* Placeholder for actual thumbnail */}
                <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/50 to-transparent p-3">
                  <div className="text-white text-sm font-medium">
                    Preview
                  </div>
                </div>
              </div>

              {/* Content */}
              <div className="p-4">
                <div className="flex items-start justify-between mb-2">
                  <h4 className="font-semibold text-gray-900 group-hover:text-primary-600 transition-colors">
                    {style.name}
                  </h4>
                  {selectedStyle?.id === style.id && (
                    <div className="w-6 h-6 bg-primary-500 rounded-full flex items-center justify-center">
                      <Check className="w-4 h-4 text-white" />
                    </div>
                  )}
                </div>
                <p className="text-sm text-gray-600 leading-relaxed">
                  {style.description}
                </p>
              </div>

              {/* Selected Overlay */}
              {selectedStyle?.id === style.id && (
                <div className="absolute inset-0 bg-primary-500 bg-opacity-10 rounded-lg pointer-events-none" />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Custom Style Option */}
      <div className="border-t border-gray-200 pt-6">
        <div className="bg-gray-50 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-2">
            Need a Custom Style?
          </h3>
          <p className="text-gray-600 mb-4">
            Our AI can create unique styles based on your specific requirements. 
            Describe your vision in the main description field, and our agents will adapt accordingly.
          </p>
          <button
            type="button"
            className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
          >
            Request Custom Style
          </button>
        </div>
      </div>
    </div>
  );
};

export default StyleSelector;