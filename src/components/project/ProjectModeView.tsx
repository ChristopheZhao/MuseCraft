'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, Play, Save, CheckCircle, RefreshCw, ArrowLeft } from 'lucide-react';

import { useAppStore } from '@/store/useAppStore';
import { useProjectStore } from '@/store/useProjectStore';
import type {
  CreateProjectRequest,
  ProjectEpisodeView,
  ProjectStateResponse,
} from '@/types/project';

const RECOMMENDED_DURATIONS = [180, 240, 300, 480];

interface ProjectFormState {
  title: string;
  description: string;
  targetDuration: number;
  aspectRatio: string;
}

const defaultFormState: ProjectFormState = {
  title: '',
  description: '',
  targetDuration: 180,
  aspectRatio: '16:9',
};

type PlanningStatus = 'queued' | 'in_progress' | 'completed' | 'failed' | string;

interface CharacterAssetRef {
  url?: string;
  kind?: string;
  size?: string;
}

interface CharacterProfileView {
  canonical_id?: string;
  display_name?: string;
  narrative_role?: string;
  description?: string;
  reference_assets?: {
    avatar?: CharacterAssetRef | string;
    full_body?: CharacterAssetRef | string;
    [key: string]: any;
  };
  [key: string]: any;
}

const ProjectModeView: React.FC = () => {
  const { addNotification, setMode } = useAppStore();
  const {
    project,
    loading,
    episodeAction,
    createProject,
    updateEpisodeScript,
    orchestrateProject,
    refreshProject,
    startPollingProject,
    stopPollingProject,
    pollingProjectId,
  } = useProjectStore();

  const [formState, setFormState] = useState<ProjectFormState>(defaultFormState);
  const [scripts, setScripts] = useState<Record<string, string>>({});
  const [selectedEpisode, setSelectedEpisode] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      stopPollingProject();
    };
  }, [stopPollingProject]);

  useEffect(() => {
    if (!project) return;
    const generatingEpisodeIds = project.story_plan.episodes
      .filter((ep) => project.episodes_runtime?.[ep.episode_id]?.status === 'generating')
      .map((ep) => ep.episode_id);

    const planningStatus = project.global_settings?.planning_status as PlanningStatus | undefined;
    const refsStatus = project.global_settings?.character_references_status as string | undefined;
    const planningInProgress = planningStatus === 'queued' || planningStatus === 'in_progress' || refsStatus === 'in_progress';

    if ((planningInProgress || generatingEpisodeIds.length > 0) && pollingProjectId !== project.project_id) {
      startPollingProject(project.project_id, generatingEpisodeIds);
    }
  }, [project, pollingProjectId, startPollingProject]);

  const episodes: ProjectEpisodeView[] = useMemo(() => {
    if (!project) return [];

    return project.story_plan.episodes.map((episode) => {
      const runtime = project.episodes_runtime?.[episode.episode_id];
      const videoUrl = runtime?.video_url || runtime?.output_assets?.final_video_url || runtime?.output_assets?.video_url;
      const runtimeWithExtras = runtime
        ? {
            ...runtime,
            video_url: videoUrl,
          }
        : undefined;

      return {
        ...episode,
        runtime: runtimeWithExtras,
      };
    });
  }, [project]);

  useEffect(() => {
    if (!project) return;
    const nextScripts: Record<string, string> = {};
    project.story_plan.episodes.forEach((episode) => {
      const runtime = project.episodes_runtime?.[episode.episode_id];
      nextScripts[episode.episode_id] = runtime?.approved_script || episode.script_draft || '';
    });
    setScripts(nextScripts);
    if (!selectedEpisode && project.story_plan.episodes.length > 0) {
      setSelectedEpisode(project.story_plan.episodes[0].episode_id);
    }
  }, [project, selectedEpisode]);

  const handleInputChange = (field: keyof ProjectFormState, value: string | number) => {
    setFormState((prev) => ({ ...prev, [field]: value }));
  };

  const handleCreateProject = async () => {
    if (!formState.title.trim() || !formState.description.trim()) {
      addNotification({
        type: 'error',
        title: '缺少信息',
        message: '请填写标题和故事梗概',
        autoClose: 4000,
      });
      return;
    }

    const payload: CreateProjectRequest = {
      user_prompt: `${formState.title}\n\n${formState.description}`,
      target_duration_seconds: formState.targetDuration,
      aspect_ratio: formState.aspectRatio,
      mode: 'project',
    };

    try {
      const created = await createProject(payload);
      startPollingProject(created.project_id);
      addNotification({
        type: 'success',
        title: '项目已创建',
        message: `生成了 ${created.story_plan.episodes.length} 个分集规划`,
        autoClose: 4000,
      });
    } catch (error) {
      addNotification({
        type: 'error',
        title: '创建失败',
        message: error instanceof Error ? error.message : '项目创建失败',
        autoClose: 6000,
      });
    }
  };

  const renderPlanningStatus = (current: ProjectStateResponse) => {
    const planningStatus = (current.global_settings?.planning_status as PlanningStatus | undefined) || 'unknown';
    const refsStatus = (current.global_settings?.character_references_status as string | undefined) || 'unknown';
    const planningError = current.global_settings?.planning_error as string | undefined;
    const refsError = current.global_settings?.character_reference_error as string | undefined;

    const badge = (label: string, value: string, tone: 'gray' | 'blue' | 'green' | 'red' = 'gray') => {
      const toneClass =
        tone === 'green'
          ? 'bg-green-100 text-green-700'
          : tone === 'blue'
          ? 'bg-blue-100 text-blue-700'
          : tone === 'red'
          ? 'bg-red-100 text-red-700'
          : 'bg-gray-100 text-gray-700';
      return (
        <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${toneClass}`}>
          {label}：{value}
        </span>
      );
    };

    const planningTone: 'gray' | 'blue' | 'green' | 'red' =
      planningStatus === 'completed' ? 'green' : planningStatus === 'failed' ? 'red' : planningStatus === 'in_progress' || planningStatus === 'queued' ? 'blue' : 'gray';
    const refsTone: 'gray' | 'blue' | 'green' | 'red' =
      refsStatus === 'completed' ? 'green' : refsStatus === 'in_progress' ? 'blue' : refsStatus === 'failed' ? 'red' : 'gray';

    return (
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-gray-900">规划进度</h3>
            <p className="text-sm text-gray-600 mt-1">项目规划与角色库会异步生成，完成后即可截图展示。</p>
          </div>
          <div className="flex items-center gap-2">
            {(planningStatus === 'queued' || planningStatus === 'in_progress' || refsStatus === 'in_progress') && (
              <span className="inline-flex items-center gap-2 text-sm text-primary-600">
                <Loader2 className="w-4 h-4 animate-spin" /> 进行中
              </span>
            )}
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {badge('planning_status', String(planningStatus), planningTone)}
          {badge('character_refs', String(refsStatus), refsTone)}
        </div>

        {(planningError || refsError) && (
          <div className="mt-4 space-y-2">
            {planningError && (
              <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">
                规划失败：{planningError}
              </div>
            )}
            {refsError && (
              <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">
                角色库生成失败：{refsError}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderCharacterLibrary = (current: ProjectStateResponse) => {
    const rawBible = (current.character_bible || current.story_plan.character_bible || {}) as Record<string, CharacterProfileView>;
    const characters = Object.entries(rawBible)
      .map(([key, value]) => ({ key, profile: value }))
      .filter((item) => item.profile && typeof item.profile === 'object');

    const getAssetUrl = (asset: CharacterAssetRef | string | undefined): string => {
      if (!asset) return '';
      if (typeof asset === 'string') return asset;
      return String(asset.url || '');
    };

    const cards = characters.map(({ key, profile }) => {
      const name = String(profile.display_name || profile.canonical_id || key || '未命名角色');
      const role = String(profile.narrative_role || '').trim();
      const avatarUrl = getAssetUrl(profile.reference_assets?.avatar as any);
      const fullBodyUrl = getAssetUrl(profile.reference_assets?.full_body as any);

      return (
        <div key={key} className="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
          <div className="p-4 border-b border-gray-100">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-semibold text-gray-900 truncate">{name}</div>
                {role && <div className="text-xs text-gray-500 mt-1 truncate">角色定位：{role}</div>}
              </div>
              <div className="text-xs text-gray-400">#{key}</div>
            </div>
          </div>

          <div className="p-4 grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <div className="text-xs font-medium text-gray-600">头像</div>
              <div className="relative w-full aspect-square rounded-lg border border-gray-200 bg-gray-50 overflow-hidden">
                {avatarUrl ? (
                  <img src={avatarUrl} alt={`${name} 头像`} className="w-full h-full object-cover" />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center text-xs text-gray-500">
                    生成中…
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <div className="text-xs font-medium text-gray-600">全身</div>
              <div className="relative w-full aspect-[3/4] rounded-lg border border-gray-200 bg-gray-50 overflow-hidden">
                {fullBodyUrl ? (
                  <img src={fullBodyUrl} alt={`${name} 全身`} className="w-full h-full object-cover" />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center text-xs text-gray-500">
                    生成中…
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      );
    });

    return (
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-gray-900">角色库</h3>
            <p className="text-sm text-gray-600 mt-1">头像与全身参考图将用于跨分集一致性，并可直接截图展示。</p>
          </div>
          <div className="text-sm text-gray-600">共 {characters.length} 个</div>
        </div>

        {characters.length === 0 ? (
          <div className="mt-4 text-sm text-gray-500 border border-dashed border-gray-300 rounded-xl p-6 text-center">
            暂无角色信息（规划生成中或未识别到角色）
          </div>
        ) : (
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {cards}
          </div>
        )}
      </div>
    );
  };

  const handleSaveScript = async (episodeId: string, approve = false) => {
    if (!project) return;
    const scriptText = scripts[episodeId] || '';

    try {
      await updateEpisodeScript(project.project_id, episodeId, {
        script_text: scriptText,
        approve,
      });
      addNotification({
        type: 'success',
        title: approve ? '脚本已确认' : '脚本已保存',
        message: approve ? '该分集可以进入生成阶段' : '脚本草稿已更新',
        autoClose: 3000,
      });
    } catch (error) {
      addNotification({
        type: 'error',
        title: '脚本更新失败',
        message: error instanceof Error ? error.message : '无法更新脚本',
        autoClose: 6000,
      });
    }
  };

  const handleGenerateEpisode = async (episodeId: string) => {
    if (!project) return;

    try {
      await orchestrateProject(project.project_id, {
        episode_ids: [episodeId],
      });
      addNotification({
        type: 'info',
        title: '生成已启动',
        message: '已提交生成任务，请稍候查看状态更新',
        autoClose: 3000,
      });
    } catch (error) {
      addNotification({
        type: 'error',
        title: '生成失败',
        message: error instanceof Error ? error.message : '无法生成该分集',
        autoClose: 6000,
      });
    }
  };

  const handleReset = () => {
    stopPollingProject();
    useProjectStore.getState().setProject(null);
    setFormState(defaultFormState);
    setScripts({});
    setSelectedEpisode(null);
  };

  const handleRefreshProject = async () => {
    if (!project) return;
    try {
      await refreshProject(project.project_id);
      addNotification({
        type: 'success',
        title: '已刷新状态',
        message: '最新分集进度已同步',
        autoClose: 3000,
      });
    } catch (error) {
      addNotification({
        type: 'error',
        title: '刷新失败',
        message: error instanceof Error ? error.message : '无法刷新项目状态',
        autoClose: 5000,
      });
    }
  };

  const renderEpisodeList = () => (
    <div className="flex gap-6 h-full">
      <div className="w-72 space-y-3 overflow-y-auto pr-2">
        {episodes.map((episode) => {
          const isActive = selectedEpisode === episode.episode_id;
          const runtimeStatus = episode.runtime?.status || episode.status;
          const statusLabel = runtimeStatus.replace(/_/g, ' ');

          return (
            <button
              key={episode.episode_id}
              onClick={() => setSelectedEpisode(episode.episode_id)}
              className={`w-full text-left p-4 rounded-lg border transition ${
                isActive ? 'bg-primary-50 border-primary-200' : 'bg-white border-gray-200'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-gray-900">Episode {episode.sequence_index + 1}</span>
                <span className="text-xs uppercase text-primary-600">{statusLabel}</span>
              </div>
              <p className="text-sm text-gray-700 line-clamp-2">{episode.summary || '无摘要'}</p>
              <p className="mt-2 text-xs text-gray-500">目标时长：{episode.target_duration_seconds}s</p>
            </button>
          );
        })}
      </div>

      <div className="flex-1 h-full">
        {selectedEpisode ? renderEpisodeDetail(selectedEpisode) : (
          <div className="h-full border border-dashed border-gray-300 rounded-xl flex items-center justify-center text-gray-500">
            选择左侧分集查看详情与脚本
          </div>
        )}
      </div>
    </div>
  );

  const renderEpisodeDetail = (episodeId: string) => {
    const episode = episodes.find((ep) => ep.episode_id === episodeId);
    if (!episode) return null;

    const runtime = episode.runtime;
    const runtimeStatus = runtime?.status ?? '';
    const isGenerating = runtimeStatus === 'generating';
    const runnableStatuses = new Set(['approved', 'completed', 'generating', 'failed', 'needs_revision']);
    const canGenerateEpisode = runnableStatuses.has(runtimeStatus);

    return (
      <div className="h-full flex flex-col bg-white border border-gray-200 rounded-xl shadow-sm">
        <div className="p-5 border-b border-gray-100">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-gray-900">Episode {episode.sequence_index + 1}</h3>
              <p className="text-sm text-gray-600 mt-1">{episode.summary || '无摘要'}</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleSaveScript(episode.episode_id, false)}
                className="inline-flex items-center gap-1 rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                disabled={episodeAction === episode.episode_id}
              >
                {episodeAction === episode.episode_id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                保存草稿
              </button>
              <button
                onClick={() => handleSaveScript(episode.episode_id, true)}
                className="inline-flex items-center gap-1 rounded-md border border-primary-200 bg-primary-50 px-3 py-2 text-sm text-primary-700 hover:bg-primary-100"
                disabled={episodeAction === episode.episode_id}
              >
                {episodeAction === episode.episode_id ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                确认脚本
              </button>
              <button
                onClick={() => handleGenerateEpisode(episode.episode_id)}
                className="inline-flex items-center gap-1 rounded-md bg-gradient-to-r from-primary-500 to-accent-500 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:from-primary-600 hover:to-accent-600"
                disabled={episodeAction === 'orchestrate' || isGenerating || !canGenerateEpisode}
              >
                {episodeAction === 'orchestrate' && isGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                生成本集
              </button>
            </div>
          </div>
        </div>

        <div className="flex-1 p-5 overflow-auto">
          <label className="block text-sm font-medium text-gray-700 mb-2">脚本内容</label>
          <textarea
            className="w-full h-72 border border-gray-200 rounded-lg p-4 text-sm focus:outline-none focus:ring-2 focus:ring-primary-200"
            value={scripts[episode.episode_id] || ''}
            onChange={(event) => setScripts((prev) => ({ ...prev, [episode.episode_id]: event.target.value }))}
            placeholder="在此调整脚本内容，确认后进入生成"
          />

          <div className="mt-6 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-700">生成状态</span>
                <span
                  className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                    runtime?.status === 'completed'
                      ? 'bg-green-100 text-green-700'
                      : runtime?.status === 'generating'
                      ? 'bg-blue-100 text-blue-700'
                      : runtime?.status === 'failed'
                      ? 'bg-red-100 text-red-700'
                      : 'bg-gray-100 text-gray-600'
                  }`}
                >
                  {(runtime?.status || episode.status).replace(/_/g, ' ')}
                </span>
              </div>
              <span className="text-xs text-gray-500">累计成本：¥{(runtime?.aggregated_cost ?? 0).toFixed(2)}</span>
            </div>

            {runtime?.status === 'generating' && (
              <div className="flex items-center gap-2 text-sm text-primary-600">
                <Loader2 className="w-4 h-4 animate-spin" /> 正在生成，请稍候...
              </div>
            )}

            {runtime?.status === 'failed' && runtime?.error && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">
                生成失败：{runtime.error}
              </div>
            )}

            {runtime?.status === 'completed' && runtime?.video_url && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-gray-700">视频预览</h4>
                <video
                  key={runtime.video_url}
                  controls
                  className="w-full aspect-video rounded-lg border border-gray-200 bg-black"
                  src={runtime.video_url}
                />
                <div className="text-xs text-gray-500">
                  确认本集效果后，可继续生成下一集；若需调整，可修改脚本后重新生成。
                </div>
              </div>
            )}

            {runtime?.status === 'completed' && !runtime?.video_url && (
              <div className="text-sm text-gray-600 bg-gray-50 border border-gray-200 rounded-lg p-3">
                本集已完成，但仍在获取视频链接，请稍候或手动刷新一次状态。
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  const renderForm = () => (
    <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-8 space-y-6">
      <div>
        <p className="text-sm font-medium text-primary-600 mb-1">项目模式</p>
        <h2 className="text-2xl font-semibold text-gray-900">创建 3-5 分钟分集短片</h2>
        <p className="text-gray-600 mt-2">输入项目梗概，系统将规划多个 episode，每集约 45-60 秒，适合连贯剧情与商业案例。</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">项目标题</label>
            <input
              className="w-full border border-gray-200 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary-200"
              value={formState.title}
              onChange={(event) => handleInputChange('title', event.target.value)}
              placeholder="例如：奇幻冒险系列短片"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">剧情梗概</label>
            <textarea
              className="w-full h-40 border border-gray-200 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary-200"
              value={formState.description}
              onChange={(event) => handleInputChange('description', event.target.value)}
              placeholder="描述世界观、主角、冲突与结局走向。"
            />
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-3">推荐时长</label>
            <div className="grid grid-cols-2 gap-3">
              {RECOMMENDED_DURATIONS.map((duration) => {
                const isActive = formState.targetDuration === duration;
                return (
                  <button
                    key={duration}
                    type="button"
                    onClick={() => handleInputChange('targetDuration', duration)}
                    className={`rounded-xl border px-4 py-3 text-left transition ${
                      isActive ? 'border-primary-300 bg-primary-50 text-primary-700' : 'border-gray-200 hover:border-primary-200'
                    }`}
                  >
                    <div className="text-sm font-semibold">{duration / 60} 分钟</div>
                    <p className="text-xs text-gray-500 mt-1">约 {Math.max(3, Math.round(duration / 60))} 集</p>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">画面比例</label>
            <select
              className="w-full border border-gray-200 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary-200"
              value={formState.aspectRatio}
              onChange={(event) => handleInputChange('aspectRatio', event.target.value)}
            >
              <option value="16:9">16:9 横屏</option>
              <option value="9:16">9:16 竖屏</option>
              <option value="1:1">1:1 方形</option>
            </select>
          </div>

          <button
            type="button"
            onClick={handleCreateProject}
            className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-primary-500 to-accent-500 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-primary-200/50 hover:from-primary-600 hover:to-accent-600"
            disabled={loading}
          >
            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5" />}
            创建项目规划
          </button>
        </div>
      </div>
    </div>
  );

  const renderProjectWorkspace = (current: ProjectStateResponse) => (
    <div className="flex flex-col gap-6 h-full">
      <div className="flex items-center justify-between">
        <div>
          <button
            onClick={() => setMode('quick')}
            className="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-primary-600"
          >
            <ArrowLeft className="w-4 h-4" /> 返回快速模式
          </button>
          <h2 className="mt-2 text-2xl font-semibold text-gray-900">项目：{current.story_plan.user_prompt.slice(0, 40)}...</h2>
          <p className="text-sm text-gray-600 mt-1">
            Episodes：{current.story_plan.episodes.length}，已完成 {current.completed_episodes} 个，总成本 ¥{current.total_cost.toFixed(2)}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleRefreshProject}
            className="inline-flex items-center gap-1 rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            <RefreshCw className="w-4 h-4" /> 刷新状态
          </button>
          <button
            onClick={handleReset}
            className="inline-flex items-center gap-1 rounded-md border border-red-200 px-3 py-2 text-sm text-red-600 hover:bg-red-50"
          >
            重置项目
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {renderPlanningStatus(current)}
        {renderCharacterLibrary(current)}
      </div>

      <div className="flex-1">
        {renderEpisodeList()}
      </div>
    </div>
  );

  return (
    <div className="h-full flex flex-col gap-6">
      {!project && renderForm()}
      {project && renderProjectWorkspace(project)}
    </div>
  );
};

export default ProjectModeView;
