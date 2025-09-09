import NavBar from '@/components/marketing/NavBar';
import Footer from '@/components/marketing/Footer';

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-br from-[#0ea5e90d] via-white to-[#d946ef0d]">
      <NavBar />
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  );
}

