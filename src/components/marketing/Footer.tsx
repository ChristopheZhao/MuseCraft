import Link from 'next/link';

export default function Footer() {
  return (
    <footer className="border-t mt-16">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 py-8 text-sm text-gray-600 flex items-center justify-between">
        <div>© {new Date().getFullYear()} MuseCraft AI</div>
        <div className="flex gap-4">
          <Link href="/(marketing)#product" className="hover:text-gray-900">产品</Link>
          <Link href="/(marketing)/pricing" className="hover:text-gray-900">定价</Link>
          <a href="#" className="hover:text-gray-900">隐私</a>
        </div>
      </div>
    </footer>
  );
}

