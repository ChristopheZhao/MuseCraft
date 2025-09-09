import { Check } from 'lucide-react';
import Link from 'next/link';

type Plan = {
  name: string;
  price: string;
  period: string;
  cta: string;
  highlighted?: boolean;
  features: string[];
};

const plans: Plan[] = [
  {
    name: 'Free',
    price: '0',
    period: '元/月',
    cta: '免费开始',
    features: ['单条视频 ≤ 30s', '基础模板与样式', '社区支持'],
  },
  {
    name: 'Pro',
    price: '199',
    period: '元/月',
    cta: '立即升级',
    highlighted: true,
    features: ['视频 ≤ 2 分钟', '批量任务队列', '商用授权与高清导出', '优先计算资源'],
  },
  {
    name: 'Enterprise',
    price: '定制',
    period: '',
    cta: '联系销售',
    features: ['私有化部署', 'SLA 与权限管理', '角色/审计与合规', '定制模型与工作流'],
  },
];

export default function PricingPage() {
  return (
    <section className="mx-auto max-w-7xl px-4 sm:px-6 py-16">
      <div className="text-center max-w-3xl mx-auto">
        <h1 className="text-4xl font-extrabold">定价方案</h1>
        <p className="text-gray-600 mt-3">按需选择合适方案，随时升级，企业版支持私有化与合规扩展。</p>
      </div>

      <div className="grid md:grid-cols-3 gap-6 mt-12">
        {plans.map((p) => (
          <div
            key={p.name}
            className={`rounded-2xl border bg-white/90 backdrop-blur shadow-card p-6 ${
              p.highlighted ? 'ring-2 ring-primary-500' : ''
            }`}
          >
            <div className="flex items-baseline gap-2">
              <h3 className="text-xl font-semibold">{p.name}</h3>
            </div>
            <div className="mt-2 flex items-end gap-1">
              <div className="text-4xl font-extrabold">{p.price}</div>
              <div className="text-gray-600 mb-1">{p.period}</div>
            </div>

            <ul className="mt-6 space-y-2 text-sm">
              {p.features.map((f) => (
                <li key={f} className="flex items-start gap-2">
                  <Check className="w-4 h-4 text-green-600 mt-0.5" />
                  <span className="text-gray-700">{f}</span>
                </li>
              ))}
            </ul>

            <Link
              href={p.name === 'Enterprise' ? '/#contact' : '/'}
              className={`block text-center mt-8 rounded-lg px-4 py-2 font-semibold shadow ${
                p.highlighted
                  ? 'bg-primary-600 text-white hover:bg-primary-700'
                  : 'border border-gray-300 text-gray-700 hover:bg-gray-50'
              }`}
            >
              {p.cta}
            </Link>
          </div>
        ))}
      </div>
    </section>
  );
}

