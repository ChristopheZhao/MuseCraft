export type Language = 'zh' | 'en';

type Dict = Record<string, string>;

export const zh: Dict = {
  'brand.name': 'MuseCraft AI',
  'brand.tagline': '企业级多智能体动漫生成平台',

  'status.ready': '系统就绪',
  'actions.upgrade': '升级套餐',

  // Header
  'header.notifications': '通知',
  'header.noNotifications': '暂无新通知',
  'header.language': '语言',
  'header.settings': '设置',
  'header.toggleSidebar.expand': '展开侧边栏',
  'header.toggleSidebar.collapse': '收起侧边栏',
  'user.plan.pro': '专业版',

  // Sidebar
  'nav.dashboard': '控制台',
  'nav.projects': '我的项目',
  'nav.templates': '模板中心',
  'nav.media': '媒体素材库',
  'nav.videos': '已生成视频',
  'nav.analytics': '分析报表',
  'nav.history': '历史记录',
  'nav.help': '帮助与支持',
  'nav.settings': '设置',

  'sidebar.aiAgents': 'AI 智能体',
  'sidebar.agent.concept': '概念规划',
  'sidebar.agent.script': '剧本创作',
  'sidebar.agent.visual': '视觉创作',
  'usage.credits': '用量统计',

  // Steps
  'step.create': '创建需求',
  'step.generation': 'AI生成',
  'step.review': '结果评审',
  'step.export': '导出与分享',

  // Orchestrator
  'orch.title': 'AI智能体编排',
  'orch.subtitle': '多智能体协作：',
  'orch.active': '运行中',
  'orch.mode': '选择模式',
  'orch.mode.pipeline': 'Pipeline模式',
  'orch.mode.react': 'ReAct模式',
  'orch.mode.multi': '多智能体模式',
  'orch.memory': '共享记忆',
  'orch.empty': '提交视频需求以查看智能体协作',
  'orch.currentTask': '当前任务',

  // Progress
  'progress.title': '生成进度',
  'progress.subtitle': '实时进度：',
  'progress.elapsed': '已用时',
  'progress.remaining': '预计剩余',
  'progress.overall': '总体完成度',
  'progress.activeAgents': '活跃智能体',
  'progress.tasks': '任务数',
  'progress.tasks_unit': '任务',
  'progress.pipeline': '多智能体进度',
  'progress.phase.initializing': '初始化',
  'progress.phase.completed': '已完成',
  'progress.step.concept': '概念生成',
  'progress.step.script': '剧本撰写',
  'progress.step.visual': '视觉生成',
  'progress.step.voice': '配音合成',
  'progress.step.video': '视频合成',
  'progress.step.quality': '质检',

  // Metrics
  'metrics.cpu': 'CPU 占用',
  'metrics.efficiency': '效率',
  'metrics.throughput': '吞吐',
  'metrics.queue': '队列',

  // Common
  'common.progress': '进度',

  // Form
  'form.title': '视频标题',
  'form.title.placeholder': '例如：新品发布会预热视频',
  'form.description': '创意与内容描述',
  'form.description.placeholder': '请输入目标受众、核心信息、场景风格等…',
  'form.references': '参考素材（可选）',
  'form.duration': '时长（秒）',
  'form.resolution': '输出分辨率',
  'form.aspect': '画幅比例',
  'form.header': '创建新视频',
  'form.subheader': '填写关键信息，MuseCraft 多智能体将为你自动完成从概念到成片的全流程生成。',
  'form.btn.save': '保存草稿',
  'form.btn.generate': '开始生成',

  // Generic statuses
  'status.idle': '空闲',
  'status.thinking': '思考中',
  'status.working': '生成中',
  'status.completed': '完成',
  'status.error': '错误',
  'status.waiting': '排队中',

  // Tabs & UI labels
  'tabs.basic': '基本信息',
  'tabs.style': '风格',
  'tabs.voice': '配音',
  'tabs.music': '音乐',
  'tabs.advanced': '高级',

  // Form extras
  'form.characters': '字符',
  'duration.15s': '15 秒',
  'duration.30s': '30 秒',
  'duration.45s': '45 秒',
  'duration.60s': '1 分钟',
  'duration.80s': '80 秒',
  // 旧选项（暂不在前端使用）
  'duration.90s': '1.5 分钟',
  'resolution.720p': '720p（高清）',
  'resolution.1080p': '1080p（全高清）',
  'resolution.hint': '动漫场景推荐 720p，兼顾画质与生成速度。',
  'duration.120s': '2 分钟',
  'aspect.16_9': '16:9（横屏）',
  'aspect.9_16': '9:16（竖屏/移动端）',
  'aspect.1_1': '1:1（正方形）',
  'aspect.4_3': '4:3（传统）',

  // Validation
  'validation.error': '校验错误',
  'validation.titleRequired': '请填写视频标题',
  'validation.descriptionRequired': '请填写视频描述',

  // Upload
  'upload.dropHere': '将文件拖到此处…',
  'upload.dragDrop': '拖拽文件到此处，或点击选择',
  'upload.supports.prefix': '支持图片、视频和文档（每个文件最大 ',
  'upload.supports.suffix': '）',
  'upload.rejected': '部分文件被拒绝：',
  'upload.selectedFiles': '已选择文件',
  'upload.remove': '移除',
  'upload.limits': '• 最多 {max} 个文件，每个不超过 {size}',
  'upload.formats': '• 支持格式：图片（JPG、PNG、GIF）、视频（MP4、MOV）、文档（PDF、DOC）',

  // Voice/Music controls
  'voice.title': '语音旁白',
  'voice.subtitle': '为视频添加 AI 生成的语音旁白',
  'voice.selection': '声音选择',
  'voice.language': '语言',
  'voice.speed': '语速',
  'voice.pitch': '音调',
  'voice.speed.slow': '慢',
  'voice.speed.normal': '正常',
  'voice.speed.fast': '快',
  'voice.pitch.low': '低',
  'voice.pitch.high': '高',

  'music.title': '背景音乐',
  'music.subtitle': '添加 AI 生成的背景音乐以增强视频效果',
  'music.genre': '音乐风格',
  'music.mood': '情绪与氛围',
  'music.volume': '音乐音量',
  'music.volume.silent': '静音',
  'music.volume.background': '背景',
  'music.volume.prominent': '突出',

  // Style selector
  'style.chooseCategory': '选择分类',
  'style.selectStyle': '选择风格',
  'style.preview': '预览',
  'style.custom.title': '需要自定义风格？',
  'style.custom.desc1': '我们的 AI 可根据你的具体需求创建独特风格。',
  'style.custom.desc2': '请在主描述中阐述你的想法，智能体将自动适配。',
  'style.custom.request': '申请自定义风格',

  // Result preview
  'results.title': '中间结果',
  'results.subtitle': '来自 AI 智能体的实时输出',
  'results.refresh': '刷新',
  'results.all': '全部结果',
  'results.concepts': '概念',
  'results.scripts': '剧本',
  'results.storyboards': '分镜',
  'results.images': '图片',
  'results.voice': '配音',
  'results.videos': '视频',
  'results.none.title': '暂无结果',
  'results.none.desc': '当智能体完成任务后，结果将显示在这里',
  'results.filter.none.title': '暂无 {type} 结果',
  'results.filter.none.desc': '{type} 智能体完成后将显示在这里',

  // Export interface
  'export.advanced': '高级设置',
  'export.qualityPreset': '质量预设',
  'export.frameRate': '帧率',
  'export.exporting': '正在导出…',
  'export.export': '导出',
  'export.copyLink': '复制链接',
  'export.share': '分享至社交媒体',
  'export.notReady.title': '视频尚未就绪',
  'export.notReady.desc': '视频仍在生成中，完成后即可进行导出。',
  'export.header': '导出与分享',
  'export.headerDesc': '下载你的视频，或直接分享至社交平台',
  'export.ready': '可导出',
  'export.progress.title': '正在导出视频',
  'export.progress.processing': '正在处理 {name}…',
  'export.progress.percent': '已完成 {percent}%',
  'export.format.choose': '选择导出格式',
  'export.notify.complete.title': '导出完成',
  'export.notify.complete.msg': '视频已成功导出',
  'export.notify.share.title': '分享功能',
  'export.notify.share.msg': '即将支持分享至 {platform}',
  'export.notify.copied.title': '已复制链接',
  'export.notify.copied.msg': '分享链接已复制到剪贴板',

  // Player
  'player.noVideoTitle': '暂无视频',
  'player.noVideoDesc': '生成完成后，视频将显示在这里',
  'player.defaultTitle': '生成视频',

  // Actions
  'action.approve': '通过',
  'action.reject': '驳回',

  // Loading
  'loading.processing': '正在处理你的请求…',
  'notify.submitFailed.title': '提交失败',
  'notify.submitFailed.msg': '请求提交失败',
};

export const en: Dict = {
  'brand.name': 'MuseCraft AI',
  'brand.tagline': 'Enterprise Multi‑Agent Anime Generation',

  'status.ready': 'System Ready',
  'actions.upgrade': 'Upgrade Plan',

  // Header
  'header.notifications': 'Notifications',
  'header.noNotifications': 'No new notifications',
  'header.language': 'Language',
  'header.settings': 'Settings',
  'header.toggleSidebar.expand': 'Expand sidebar',
  'header.toggleSidebar.collapse': 'Collapse sidebar',
  'user.plan.pro': 'Pro Plan',

  'nav.dashboard': 'Dashboard',
  'nav.projects': 'My Projects',
  'nav.templates': 'Templates',
  'nav.media': 'Media Library',
  'nav.videos': 'Generated Videos',
  'nav.analytics': 'Analytics',
  'nav.history': 'History',
  'nav.help': 'Help & Support',
  'nav.settings': 'Settings',

  'sidebar.aiAgents': 'AI Agents',
  'sidebar.agent.concept': 'Concept Generator',
  'sidebar.agent.script': 'Script Writer',
  'sidebar.agent.visual': 'Visual Creator',
  'usage.credits': 'Credits Used',

  'step.create': 'Create Request',
  'step.generation': 'AI Generation',
  'step.review': 'Review Results',
  'step.export': 'Export & Share',

  'orch.title': 'AI Agent Orchestration',
  'orch.subtitle': 'Multi‑agent collaboration: ',
  'orch.active': 'Active',
  'orch.mode': 'Mode',
  'orch.mode.pipeline': 'Pipeline',
  'orch.mode.react': 'ReAct',
  'orch.mode.multi': 'Multi‑Agent',
  'orch.memory': 'Shared Memory',
  'orch.empty': 'Submit a video request to see the agents in action',
  'orch.currentTask': 'Current Task',

  'progress.title': 'Generation Progress',
  'progress.subtitle': 'Real‑time for: ',
  'progress.elapsed': 'elapsed',
  'progress.remaining': 'remaining',
  'progress.overall': 'Overall',
  'progress.activeAgents': 'Active agents',
  'progress.tasks': 'Tasks',
  'progress.tasks_unit': 'tasks',
  'progress.pipeline': 'Multi‑Agent Progress',
  'progress.phase.initializing': 'Initializing',
  'progress.phase.completed': 'Completed',
  'progress.step.concept': 'Concept Generation',
  'progress.step.script': 'Script Writing',
  'progress.step.visual': 'Visual Creation',
  'progress.step.voice': 'Voice Synthesis',
  'progress.step.video': 'Video Assembly',
  'progress.step.quality': 'Quality Control',

  'metrics.cpu': 'CPU Usage',
  'metrics.efficiency': 'Efficiency',
  'metrics.throughput': 'Throughput',
  'metrics.queue': 'Queue',

  'common.progress': 'Progress',

  'form.title': 'Video Title',
  'form.title.placeholder': 'e.g., Product launch teaser',
  'form.description': 'Creative Brief',
  'form.description.placeholder': 'Audience, key message, style…',
  'form.references': 'Reference Materials (optional)',
  'form.duration': 'Duration (seconds)',
  'form.resolution': 'Output Resolution',
  'form.aspect': 'Aspect Ratio',
  'form.header': 'Create New Video',
  'form.subheader': 'Provide key details and let multi‑agent orchestration generate a production‑ready video.',
  'form.btn.save': 'Save Draft',
  'form.btn.generate': 'Generate',
  
  // Duration options
  'duration.15s': '15 seconds',
  'duration.30s': '30 seconds',
  'duration.45s': '45 seconds',
  'duration.60s': '60 seconds',
  'duration.80s': '80 seconds',
  'resolution.720p': '720p (HD)',
  'resolution.1080p': '1080p (Full HD)',
  'resolution.hint': '720p balances quality and speed for animation drafts; choose 1080p for polished promos.',

  'status.idle': 'Idle',
  'status.thinking': 'Thinking',
  'status.working': 'Working',
  'status.completed': 'Completed',
  'status.error': 'Error',
  'status.waiting': 'Waiting',

  // Export interface
  'export.advanced': 'Advanced Settings',
  'export.qualityPreset': 'Quality Preset',
  'export.frameRate': 'Frame Rate',
  'export.exporting': 'Exporting…',
  'export.export': 'Export',
  'export.copyLink': 'Copy Link',
  'export.share': 'Share to Social Media',
  'export.notReady.title': 'Video Not Ready',
  'export.notReady.desc': 'Your video is still being generated. Export options will be available once complete.',
  'export.header': 'Export & Share',
  'export.headerDesc': 'Download your video or share it to social platforms',
  'export.ready': 'Ready to Export',
  'export.progress.title': 'Exporting Video',
  'export.progress.processing': 'Processing {name}…',
  'export.progress.percent': '{percent}% complete',
  'export.format.choose': 'Choose Export Format',
  'export.notify.complete.title': 'Export Complete',
  'export.notify.complete.msg': 'Your video has been exported successfully',
  'export.notify.share.title': 'Share Feature',
  'export.notify.share.msg': 'Sharing to {platform} will be available soon',
  'export.notify.copied.title': 'Link Copied',
  'export.notify.copied.msg': 'Share link copied to clipboard',

  // Player
  'player.noVideoTitle': 'No Video Available',
  'player.noVideoDesc': 'Video will appear here once generation is complete',
  'player.defaultTitle': 'Generated Video',

  // Actions
  'action.approve': 'Approve',
  'action.reject': 'Reject',

  // Loading
  'loading.processing': 'Processing your request…',
  'notify.submitFailed.title': 'Submission Failed',
  'notify.submitFailed.msg': 'Failed to submit request',
};

export const dictionaries: Record<Language, Dict> = { zh, en };
