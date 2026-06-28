import { PRIVACY_URL, TERMS_URL } from "../lib/links";

export default function Footer() {
  return (
    <footer className="border-t border-line bg-cream/50">
      <div className="mx-auto flex max-w-[1200px] items-center justify-between gap-3 px-5 py-2 text-[0.75rem] text-faint">
        <div className="flex items-center gap-2">
          <span className="relative grid h-4 w-4 place-items-center">
            <span className="absolute h-4 w-4 rotate-45 rounded-[4px] bg-olive" />
            <span className="absolute h-2 w-2 rotate-45 rounded-[2px] bg-leaf" />
          </span>
          <span className="font-600 text-ink">Doomberg</span>
          <span>© {new Date().getFullYear()}</span>
        </div>

        <div className="flex gap-4">
          <a href={TERMS_URL} className="transition-colors hover:text-ink">
            Terms
          </a>
          <a href={PRIVACY_URL} className="transition-colors hover:text-ink">
            Privacy
          </a>
        </div>
      </div>
    </footer>
  );
}
