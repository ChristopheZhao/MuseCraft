import Link from 'next/link';
import { Zap, Workflow, PlayCircle, Repeat, BookOpen, TrendingUp } from 'lucide-react';
import HeroMedia from '@/components/marketing/HeroMedia';

export default function MarketingHome() {
  const stats = [
    { k: '运行状态', v: 'SoT' },
    { k: '人工审核', v: 'Gate' },
    { k: '外部能力', v: 'Tools' },
  ];

  const features = [
    { icon: Workflow, title: 'Control-plane runtime', desc: 'session、node、attempt、gate 与 decision 由 MAS control plane 统一持有，队列只负责传输与执行。' },
    { icon: Repeat, title: 'ReAct 与工具边界', desc: 'Native agent 在显式能力集合内观察、计划、调用工具并反思；外部 I/O 不直接耦合供应商 SDK。' },
    { icon: BookOpen, title: 'Contract-first 验收', desc: '模型、工具和媒体输出在边界完成规范化与诊断，成片进度以 scene-output acceptance facts 为准。' },
    { icon: TrendingUp, title: 'Read-model 分离', desc: '前端消费明确的 runtime 投影，不从 Redis、worker 或非空媒体 URL 推断业务状态。' },
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
              <Zap className="w-3.5 h-3.5" /> 多智能体编排 · 可观测运行时
            </span>
            <h1 className="mt-4 text-4xl lg:text-6xl font-extrabold tracking-tight lg:whitespace-nowrap">
              用 AI 多智能体，
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary-600 to-accent-600">从概念到成片</span>
            </h1>
            <p className="mt-4 text-lg text-gray-700">
              在一个工作区组织概念、剧本、角色与场景、配音、合成和质检，并通过显式运行状态与人工 gate 推进生成。
            </p>
            <div className="mt-8 flex gap-6 md:gap-8">
              <Link href="/console" className="px-6 py-3 rounded-lg bg-primary-600 text-white hover:bg-primary-700 font-medium shadow">开始创作</Link>
              <Link href="/home#product" className="px-6 py-3 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 font-medium">查看架构</Link>
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
            <h3 className="text-2xl font-bold">从需求到可审查的生成结果</h3>
            <p className="text-white/90 mt-1">创建需求 → Agent 执行 → Gate 评审 → 导出</p>
          </div>
          <Link href="/console" className="px-5 py-3 bg-white text-primary-700 rounded-lg font-semibold shadow hover:bg-gray-100 flex items-center gap-2">
            <PlayCircle className="w-5 h-5" /> 立即试用
          </Link>
        </div>
      </section>
    </>
  );
}
