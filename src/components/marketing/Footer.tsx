import Link from 'next/link';

export default function Footer() {
  return (
    <footer className="border-t mt-16">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 py-8 text-sm text-gray-600 flex items-center justify-between">
        <div>© {new Date().getFullYear()} MuseCraft AI</div>
        <div className="flex gap-4">
          <Link href="/home#product" className="hover:text-gray-900">架构</Link>
          <Link href="/console" className="hover:text-gray-900">控制台</Link>
        </div>
      </div>
    </footer>
  );
}
