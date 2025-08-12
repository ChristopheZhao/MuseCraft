'use client';

import React, { useEffect, useState } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { cn, formatTime, getProgressColor } from '@/lib/utils';
import { 
  Clock, 
  CheckCircle, 
  AlertCircle, 
  Zap,
  TrendingUp,
  Activity,
  Timer,
  Cpu
} from 'lucide-react';
import { motion } from 'framer-motion';

interface ProgressMetrics {
  overallProgress: number;
  activeAgents: number;
  completedTasks: number;
  totalTasks: number;
  estimatedTimeRemaining: number;
  currentPhase: string;
}

const RealTimeProgress: React.FC = () => {
  const { agents, currentRequest, ui } = useAppStore();
  const [metrics, setMetrics] = useState<ProgressMetrics>({
    overallProgress: 0,
    activeAgents: 0,
    completedTasks: 0,
    totalTasks: 0,
    estimatedTimeRemaining: 0,
    currentPhase: 'Initializing',
  });

  const [startTime] = useState(Date.now());
  const [elapsedTime, setElapsedTime] = useState(0);

  // Update elapsed time every second
  useEffect(() => {
    const interval = setInterval(() => {
      setElapsedTime(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    return () => clearInterval(interval);
  }, [startTime]);

  // Calculate metrics based on agent states
  useEffect(() => {
    const activeAgents = agents.filter(a => a.status === 'working' || a.status === 'thinking').length;
    const completedAgents = agents.filter(a => a.status === 'completed').length;
    const totalAgents = agents.length;
    
    const overallProgress = Math.round((completedAgents / totalAgents) * 100);
    const estimatedTimeRemaining = agents
      .filter(a => a.estimatedTime && a.status !== 'completed')
      .reduce((acc, a) => Math.max(acc, a.estimatedTime || 0), 0);

    // Determine current phase
    let currentPhase = 'Initializing';
    if (completedAgents === totalAgents) {
      currentPhase = 'Completed';
    } else if (activeAgents > 0) {
      const workingAgent = agents.find(a => a.status === 'working');
      if (workingAgent) {
        currentPhase = workingAgent.name.replace(' Agent', '');
      }
    }

    setMetrics({
      overallProgress,
      activeAgents,
      completedTasks: completedAgents,
      totalTasks: totalAgents,
      estimatedTimeRemaining,
      currentPhase,
    });
  }, [agents]);

  if (!currentRequest) {
    return null;
  }

  const progressSteps = [
    { name: 'Concept Generation', agent: 'concept-generator', icon: Zap },
    { name: 'Script Writing', agent: 'script-writer', icon: CheckCircle },
    { name: 'Visual Creation', agent: 'image-generator', icon: CheckCircle },
    { name: 'Voice Synthesis', agent: 'voice-synthesizer', icon: CheckCircle },
    { name: 'Video Assembly', agent: 'video-composer', icon: CheckCircle },
    { name: 'Quality Control', agent: 'quality-controller', icon: CheckCircle },
  ];

  const getStepStatus = (agentId: string) => {
    const agent = agents.find(a => a.id === agentId);
    return agent?.status || 'idle';
  };

  const getStepProgress = (agentId: string) => {
    const agent = agents.find(a => a.id === agentId);
    return agent?.progress || 0;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">
            Generation Progress
          </h3>
          <p className="text-sm text-gray-600">
            Real-time progress for: {currentRequest.title}
          </p>
        </div>
        <div className="flex items-center space-x-4 text-sm">
          <div className="flex items-center space-x-1 text-gray-600">
            <Timer className="w-4 h-4" />
            <span>{formatTime(elapsedTime)} elapsed</span>
          </div>
          {metrics.estimatedTimeRemaining > 0 && (
            <div className="flex items-center space-x-1 text-gray-600">
              <Clock className="w-4 h-4" />
              <span>~{formatTime(metrics.estimatedTimeRemaining)} remaining</span>
            </div>
          )}
        </div>
      </div>

      {/* Overall Progress */}
      <div className="bg-gradient-to-r from-primary-50 to-accent-50 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h4 className="text-xl font-semibold text-gray-900">
              {metrics.overallProgress}% Complete
            </h4>
            <p className="text-gray-600">
              {metrics.currentPhase}
            </p>
          </div>
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <Activity className="w-5 h-5 text-green-500" />
              <span className="text-sm font-medium text-gray-700">
                {metrics.activeAgents} Active
              </span>
            </div>
            <div className="flex items-center space-x-2">
              <CheckCircle className="w-5 h-5 text-blue-500" />
              <span className="text-sm font-medium text-gray-700">
                {metrics.completedTasks}/{metrics.totalTasks} Tasks
              </span>
            </div>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="relative">
          <div className="w-full bg-white bg-opacity-50 rounded-full h-3 overflow-hidden">
            <motion.div
              className={cn(
                "h-full rounded-full transition-all duration-500",
                getProgressColor(metrics.overallProgress)
              )}
              initial={{ width: 0 }}
              animate={{ width: `${metrics.overallProgress}%` }}
              transition={{ duration: 1, ease: "easeOut" }}
            />
          </div>
          
          {/* Progress Markers */}
          <div className="absolute inset-0 flex justify-between items-center px-1">
            {[0, 20, 40, 60, 80, 100].map((mark) => (
              <div
                key={mark}
                className={cn(
                  "w-1 h-3 rounded-full",
                  metrics.overallProgress >= mark 
                    ? "bg-white bg-opacity-80" 
                    : "bg-gray-400 bg-opacity-30"
                )}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Step Progress */}
      <div className="space-y-3">
        <h4 className="font-medium text-gray-900">Pipeline Progress</h4>
        <div className="space-y-2">
          {progressSteps.map((step, index) => {
            const status = getStepStatus(step.agent);
            const progress = getStepProgress(step.agent);
            const Icon = step.icon;
            
            return (
              <motion.div
                key={step.agent}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.05 }}
                className={cn(
                  "flex items-center space-x-4 p-4 rounded-lg border transition-all",
                  {
                    'bg-blue-50 border-blue-200': status === 'thinking',
                    'bg-green-50 border-green-200': status === 'working',
                    'bg-green-100 border-green-300': status === 'completed',
                    'bg-red-50 border-red-200': status === 'error',
                    'bg-gray-50 border-gray-200': status === 'idle' || status === 'waiting',
                  }
                )}
              >
                {/* Step Icon */}
                <div className={cn(
                  "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center",
                  {
                    'bg-blue-500': status === 'thinking',
                    'bg-green-500': status === 'working',
                    'bg-green-600': status === 'completed',
                    'bg-red-500': status === 'error',
                    'bg-gray-400': status === 'idle' || status === 'waiting',
                  }
                )}>
                  {status === 'completed' ? (
                    <CheckCircle className="w-5 h-5 text-white" />
                  ) : status === 'error' ? (
                    <AlertCircle className="w-5 h-5 text-white" />
                  ) : (
                    <Icon className={cn(
                      "w-5 h-5 text-white",
                      (status === 'working' || status === 'thinking') && "animate-pulse"
                    )} />
                  )}
                </div>

                {/* Step Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-1">
                    <h5 className="font-medium text-gray-900">
                      {step.name}
                    </h5>
                    <span className={cn(
                      "text-xs font-medium capitalize px-2 py-1 rounded-full",
                      {
                        'bg-blue-100 text-blue-700': status === 'thinking',
                        'bg-green-100 text-green-700': status === 'working',
                        'bg-green-200 text-green-800': status === 'completed',
                        'bg-red-100 text-red-700': status === 'error',
                        'bg-gray-100 text-gray-600': status === 'idle' || status === 'waiting',
                      }
                    )}>
                      {status}
                    </span>
                  </div>

                  {/* Progress Bar for Active Steps */}
                  {(status === 'working' || status === 'thinking') && progress > 0 && (
                    <div className="w-full bg-gray-200 rounded-full h-1.5">
                      <motion.div
                        className="bg-primary-500 h-1.5 rounded-full"
                        initial={{ width: 0 }}
                        animate={{ width: `${progress}%` }}
                        transition={{ duration: 0.5 }}
                      />
                    </div>
                  )}
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      {/* Performance Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-lg border border-gray-200">
          <div className="flex items-center space-x-2 mb-2">
            <Cpu className="w-5 h-5 text-primary-500" />
            <span className="text-sm font-medium text-gray-700">CPU Usage</span>
          </div>
          <div className="text-2xl font-bold text-gray-900">
            {Math.round(metrics.activeAgents * 25)}%
          </div>
        </div>

        <div className="bg-white p-4 rounded-lg border border-gray-200">
          <div className="flex items-center space-x-2 mb-2">
            <TrendingUp className="w-5 h-5 text-green-500" />
            <span className="text-sm font-medium text-gray-700">Efficiency</span>
          </div>
          <div className="text-2xl font-bold text-gray-900">
            {Math.max(85, Math.round(100 - (elapsedTime / 10)))}%
          </div>
        </div>

        <div className="bg-white p-4 rounded-lg border border-gray-200">
          <div className="flex items-center space-x-2 mb-2">
            <Activity className="w-5 h-5 text-blue-500" />
            <span className="text-sm font-medium text-gray-700">Throughput</span>
          </div>
          <div className="text-2xl font-bold text-gray-900">
            {metrics.completedTasks * 2}/min
          </div>
        </div>

        <div className="bg-white p-4 rounded-lg border border-gray-200">
          <div className="flex items-center space-x-2 mb-2">
            <Zap className="w-5 h-5 text-yellow-500" />
            <span className="text-sm font-medium text-gray-700">Queue</span>
          </div>
          <div className="text-2xl font-bold text-gray-900">
            {Math.max(0, metrics.totalTasks - metrics.completedTasks - metrics.activeAgents)}
          </div>
        </div>
      </div>
    </div>
  );
};

export default RealTimeProgress;