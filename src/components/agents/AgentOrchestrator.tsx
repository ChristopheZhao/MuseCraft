'use client';

import React from 'react';
import { useAppStore } from '@/store/useAppStore';
import { Agent } from '@/types';
import { cn, getStatusColor } from '@/lib/utils';
import { 
  Brain, 
  FileText, 
  Image, 
  Mic, 
  Video, 
  CheckCircle,
  Clock,
  Zap,
  AlertCircle,
  ArrowRight,
  Sparkles
} from 'lucide-react';
import { motion } from 'framer-motion';

const AgentOrchestrator: React.FC = () => {
  const { agents, currentRequest } = useAppStore();

  const getAgentIcon = (type: Agent['type']) => {
    const iconProps = { className: "w-6 h-6" };
    
    switch (type) {
      case 'concept-generator':
        return <Brain {...iconProps} />;
      case 'script-writer':
        return <FileText {...iconProps} />;
      case 'image-generator':
        return <Image {...iconProps} />;
      case 'voice-synthesizer':
        return <Mic {...iconProps} />;
      case 'video-composer':
        return <Video {...iconProps} />;
      case 'quality-controller':
        return <CheckCircle {...iconProps} />;
      default:
        return <Sparkles {...iconProps} />;
    }
  };

  const getStatusIcon = (status: Agent['status']) => {
    const iconProps = { className: "w-4 h-4" };
    
    switch (status) {
      case 'thinking':
        return <Brain {...iconProps} className="w-4 h-4 animate-pulse" />;
      case 'working':
        return <Zap {...iconProps} className="w-4 h-4 animate-bounce" />;
      case 'completed':
        return <CheckCircle {...iconProps} className="w-4 h-4 text-green-500" />;
      case 'error':
        return <AlertCircle {...iconProps} className="w-4 h-4 text-red-500" />;
      case 'waiting':
        return <Clock {...iconProps} className="w-4 h-4 text-yellow-500" />;
      default:
        return <Clock {...iconProps} className="w-4 h-4 text-gray-400" />;
    }
  };

  const getAgentStatusColor = (status: Agent['status']) => {
    switch (status) {
      case 'idle':
        return 'bg-gray-100 border-gray-200';
      case 'thinking':
        return 'bg-blue-50 border-blue-200';
      case 'working':
        return 'bg-green-50 border-green-200';
      case 'completed':
        return 'bg-green-100 border-green-300';
      case 'error':
        return 'bg-red-50 border-red-200';
      case 'waiting':
        return 'bg-yellow-50 border-yellow-200';
      default:
        return 'bg-gray-100 border-gray-200';
    }
  };

  if (!currentRequest) {
    return (
      <div className="p-8 text-center">
        <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <Brain className="w-8 h-8 text-gray-400" />
        </div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">
          AI Agents Ready
        </h3>
        <p className="text-gray-600">
          Submit a video request to see the agents in action
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">
            AI Agent Orchestration
          </h3>
          <p className="text-sm text-gray-600">
            Multi-agent collaboration for {currentRequest.title}
          </p>
        </div>
        <div className="flex items-center space-x-2 px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-medium">
          <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
          <span>Active</span>
        </div>
      </div>

      {/* Agent Flow Visualization */}
      <div className="relative">
        {/* Connection Lines */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-full h-0.5 bg-gray-200">
            <motion.div
              className="h-full bg-gradient-to-r from-primary-500 to-green-500"
              initial={{ width: '0%' }}
              animate={{ width: '100%' }}
              transition={{ duration: 2, repeat: Infinity, repeatType: 'loop' }}
            />
          </div>
        </div>

        {/* Agents */}
        <div className="relative grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {agents.map((agent, index) => (
            <motion.div
              key={agent.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
              className={cn(
                "relative p-4 rounded-xl border-2 transition-all duration-300",
                getAgentStatusColor(agent.status),
                agent.status === 'working' && "shadow-lg transform scale-105"
              )}
            >
              {/* Agent Icon */}
              <div className="flex items-center justify-center w-12 h-12 bg-white rounded-full shadow-sm mb-3 mx-auto">
                <div className={getStatusColor(agent.status)}>
                  {getAgentIcon(agent.type)}
                </div>
              </div>

              {/* Agent Info */}
              <div className="text-center">
                <h4 className="font-medium text-gray-900 text-sm mb-1">
                  {agent.name}
                </h4>
                <div className="flex items-center justify-center space-x-1 mb-2">
                  {getStatusIcon(agent.status)}
                  <span className={cn(
                    "text-xs font-medium capitalize",
                    getStatusColor(agent.status)
                  )}>
                    {agent.status}
                  </span>
                </div>

                {/* Progress Bar */}
                {agent.progress > 0 && (
                  <div className="w-full bg-gray-200 rounded-full h-1.5 mb-2">
                    <motion.div
                      className="bg-primary-500 h-1.5 rounded-full"
                      initial={{ width: 0 }}
                      animate={{ width: `${agent.progress}%` }}
                      transition={{ duration: 0.5 }}
                    />
                  </div>
                )}

                {/* Current Task */}
                {agent.currentTask && (
                  <p className="text-xs text-gray-600 truncate">
                    {agent.currentTask}
                  </p>
                )}

                {/* Estimated Time */}
                {agent.estimatedTime && agent.status === 'working' && (
                  <div className="mt-2 text-xs text-gray-500">
                    ~{agent.estimatedTime}s remaining
                  </div>
                )}
              </div>

              {/* Status Indicator */}
              <div className={cn(
                "absolute -top-1 -right-1 w-3 h-3 rounded-full border-2 border-white",
                {
                  'bg-gray-400': agent.status === 'idle',
                  'bg-blue-500 animate-pulse': agent.status === 'thinking',
                  'bg-green-500 animate-pulse': agent.status === 'working',
                  'bg-green-600': agent.status === 'completed',
                  'bg-red-500': agent.status === 'error',
                  'bg-yellow-500': agent.status === 'waiting',
                }
              )} />

              {/* Connection Arrow */}
              {index < agents.length - 1 && (
                <div className="absolute top-1/2 -right-2 transform -translate-y-1/2 hidden lg:block">
                  <ArrowRight className="w-4 h-4 text-gray-400" />
                </div>
              )}
            </motion.div>
          ))}
        </div>
      </div>

      {/* Agent Details */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.filter(agent => agent.status !== 'idle').map((agent) => (
          <div
            key={`details-${agent.id}`}
            className="p-4 bg-white border border-gray-200 rounded-lg"
          >
            <div className="flex items-center space-x-3 mb-3">
              <div className="flex-shrink-0">
                {getAgentIcon(agent.type)}
              </div>
              <div className="flex-1 min-w-0">
                <h4 className="font-medium text-gray-900">
                  {agent.name}
                </h4>
                <p className={cn(
                  "text-sm capitalize",
                  getStatusColor(agent.status)
                )}>
                  {agent.status}
                </p>
              </div>
            </div>

            <p className="text-sm text-gray-600 mb-3">
              {agent.description}
            </p>

            {agent.currentTask && (
              <div className="mb-3">
                <p className="text-xs font-medium text-gray-700 mb-1">
                  Current Task:
                </p>
                <p className="text-sm text-gray-600">
                  {agent.currentTask}
                </p>
              </div>
            )}

            {agent.progress > 0 && (
              <div className="mb-3">
                <div className="flex justify-between text-xs text-gray-600 mb-1">
                  <span>Progress</span>
                  <span>{agent.progress}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <motion.div
                    className="bg-primary-500 h-2 rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${agent.progress}%` }}
                    transition={{ duration: 0.5 }}
                  />
                </div>
              </div>
            )}

            <div className="flex flex-wrap gap-1">
              {agent.capabilities.slice(0, 3).map((capability) => (
                <span
                  key={capability}
                  className="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded-full"
                >
                  {capability}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AgentOrchestrator;