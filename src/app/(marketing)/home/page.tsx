import Link from 'next/link';
import { Zap, Workflow, PlayCircle, Repeat, BookOpen, TrendingUp } from 'lucide-react';
import HeroMedia from '@/components/marketing/HeroMedia';

export default function MarketingHome() {
  const stats = [
    { k: '生成效率', v: 'x10' },
    { k: '智能体协作', v: '6+' },
    { k: '动漫成片', v: '40s+' },
  ];

  const features = [
    { icon: Workflow, title: 'Multi-Agent 自主化协作', desc: '智能体具备决策与协同能力，基于目标自主分工、互相校验与推进，减少人工编排负担。' },
    { icon: Repeat, title: '经验轨迹复用学习', desc: '沉淀成功项目的关键决策路径，形成可复用“创作 DNA”，相似任务自动套用并自适应调整。' },
    { icon: BookOpen, title: '垂直领域知识注入', desc: '将动漫/视频专业知识以知识图谱形式注入智能体决策，输出更符合行业标准的结果。' },
    { icon: TrendingUp, title: '可适应智能增长设计', desc: '底层模型能力升级即带来系统质效增长，架构随能力扩展，持续获得“越用越强”的复利。' },
  ];

  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden">
        {/* Make background match content height */}
        <HeroMedia height="h-full" />
        <div className="mx-auto max-w-7xl px-4 sm:px-6 py-28 lg:py-40 relative">
          <div className="max-w-4xl lg:max-w-5xl">
            <span className="inline-flex items-center gap-2 text-xs font-medium px-3 py-1 rounded-full bg-white/80 text-primary-700 ring-1 ring-primary-200">
              <Zap className="w-3.5 h-3.5" /> 多智能体编排 · 企业级
            </span>
            <h1 className="mt-4 text-4xl lg:text-6xl font-extrabold tracking-tight lg:whitespace-nowrap">
              用 AI 多智能体，
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary-600 to-accent-600">从概念到成片</span>
            </h1>
            <p className="mt-4 text-lg text-gray-700">
              概念规划、剧本创作、角色与场景、配音音乐、合成与质检，一站式多智能体协作，分钟级产出商业级动漫短片。
            </p>
            <div className="mt-8 flex gap-6 md:gap-8">
              <Link href="/console" className="px-6 py-3 rounded-lg bg-primary-600 text-white hover:bg-primary-700 font-medium shadow">开始创作</Link>
              <Link href="/pricing" className="px-6 py-3 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 font-medium">查看定价</Link>
            </div>
            <div className="mt-10 grid grid-cols-3 gap-5 text-center">
              {stats.map((s) => (
                <div
                  key={s.k}
                  className="rounded-xl p-[1.5px] bg-gradient-to-r from-primary-300/70 to-accent-300/70 shadow-card hover:shadow-card-hover transition-shadow"
                >
                  <div className="rounded-[0.75rem] bg-white/90 backdrop-blur-xs px-4 py-4 ring-1 ring-white/60">
                    <div className="text-2xl font-extrabold text-gray-900 tracking-tight">{s.v}</div>
                    <div className="text-xs text-gray-700 mt-1 font-medium">{s.k}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Product Highlights */}
      <section id="product" className="relative overflow-hidden mx-auto max-w-7xl px-4 sm:px-6 py-12 lg:py-20">
        {/* Subtle backdrop to avoid plain white */}
        <div className="absolute inset-0 -z-10 bg-gradient-to-b from-white via-primary-50/50 to-white" />
        <div className="absolute -top-40 -left-40 -z-10 w-[520px] h-[520px] rounded-full bg-primary-200/40 blur-3xl" />
        <div className="absolute -bottom-40 -right-40 -z-10 w-[520px] h-[520px] rounded-full bg-accent-200/40 blur-3xl" />
        <h2 className="text-2xl font-bold text-gray-900 mb-6">核心能力</h2>
        <div className="grid md:grid-cols-2 gap-6">
          {features.map((f, i) => (
            <div key={i} className="p-6 rounded-xl bg-white/90 backdrop-blur border shadow-card">
              <f.icon className="w-6 h-6 text-primary-600" />
              <h3 className="mt-3 font-semibold text-gray-900">{f.title}</h3>
              <p className="mt-2 text-gray-600 text-sm leading-6">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-7xl px-4 sm:px-6 py-12 lg:py-16">
        <div className="p-8 rounded-2xl bg-gradient-to-br from-primary-600 to-accent-600 text-white flex flex-col md:flex-row items-center justify-between gap-4">
          <div>
            <h3 className="text-2xl font-bold">3 步开启商业级 AI 视频生产</h3>
            <p className="text-white/90 mt-1">创建需求 → AI 生成 → 评审导出</p>
          </div>
          <Link href="/console" className="px-5 py-3 bg-white text-primary-700 rounded-lg font-semibold shadow hover:bg-gray-100 flex items-center gap-2">
            <PlayCircle className="w-5 h-5" /> 立即试用
          </Link>
        </div>
      </section>
    </>
  );
}
