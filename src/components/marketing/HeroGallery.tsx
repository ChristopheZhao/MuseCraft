import Image from 'next/image';

export default function HeroGallery() {
  const items = [
    { src: '/marketing/hero-1.jpg', alt: 'neon city', cls: 'row-span-2 h-72' },
    { src: '/marketing/hero-2.jpg', alt: 'abstract', cls: 'h-32' },
    { src: '/marketing/hero-3.jpg', alt: 'creative', cls: 'h-32' },
  ];

  return (
    <div className="hidden md:block">
      <div className="grid grid-cols-2 gap-4">
        {items.map((it, idx) => (
          <div key={idx} className={`relative rounded-xl overflow-hidden shadow-card border ${it.cls}`}>
            <Image src={it.src} alt={it.alt} fill className="object-cover" sizes="(min-width: 768px) 420px, 100vw" />
          </div>
        ))}
      </div>
    </div>
  );
}

