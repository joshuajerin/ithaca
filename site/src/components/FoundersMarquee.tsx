const founders = [
  { name: "Founders Inc", src: "/logos/foundersinc.png", className: "h-9" },
  { name: "Cerebral Valley", src: "/logos/cerebralvalley.svg", className: "h-9" },
  { name: "Stanford", src: "/logos/stanford-wordmark.png", className: "h-5" },
  { name: "Network School", src: "/logos/networkschool.svg", className: "h-4" },
];

export default function FoundersMarquee() {
  return (
    <section className="relative border-y border-ink/15 bg-[#ece5d4]">
      <div className="relative z-10 mx-auto max-w-[1200px] px-6 py-10 md:py-12">
        <div className="flex flex-col items-center gap-8 md:flex-row md:gap-12">
          <p className="shrink-0 text-center font-mono text-[0.82rem] font-500 uppercase tracking-[0.22em] text-faint md:max-w-[150px] md:text-left">
            Founders from
          </p>
          <div className="grid w-full grid-cols-2 items-center gap-x-8 gap-y-10 sm:grid-cols-4">
            {founders.map((f) => (
              <div key={f.name} className="group flex items-center justify-center">
                <img
                  src={f.src}
                  alt={`${f.name} logo`}
                  className={`${f.className} w-auto max-w-full object-contain opacity-55 grayscale transition-all duration-300 group-hover:opacity-90 group-hover:grayscale-0`}
                  loading="lazy"
                />
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
