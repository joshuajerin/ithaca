import React from "react";

interface CompanyLogoProps {
  symbol: string;
  logoUrl?: string | null;
  size?: number;
}

/**
 * Company brand mark. Renders the real logo when a URL is available and falls
 * back to a clean monogram (first letters of the ticker) on error or when no
 * logo is known, so every card shows something recognizable.
 */
export function CompanyLogo({ symbol, logoUrl, size = 20 }: CompanyLogoProps) {
  const [failed, setFailed] = React.useState(false);
  const showImg = !!logoUrl && !failed;
  const initials = (symbol || "?").replace(/[^A-Za-z0-9]/g, "").slice(0, 2) || "?";

  return (
    <span
      className="inline-flex items-center justify-center shrink-0 overflow-hidden rounded-sm border border-border bg-white/5"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      {showImg ? (
        <img
          src={logoUrl!}
          alt=""
          width={size}
          height={size}
          loading="lazy"
          referrerPolicy="no-referrer"
          className="h-full w-full object-contain"
          onError={() => setFailed(true)}
        />
      ) : (
        <span
          className="font-serif text-muted-foreground leading-none"
          style={{ fontSize: Math.round(size * 0.42) }}
        >
          {initials}
        </span>
      )}
    </span>
  );
}
