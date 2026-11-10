// One small stroke icon set (24px grid, 2px stroke) so the UI doesn't lean on unicode glyphs.
const PATHS: Record<string, string> = {
  play: "M7 5v14l11-7z",
  refresh: "M20 11a8 8 0 0 0-14.6-4.5M4 4v4h4M4 13a8 8 0 0 0 14.6 4.5M20 20v-4h-4",
  history: "M3 12a9 9 0 1 0 3-6.7M3 4v4h4M12 7v5l3 2",
  info: "M12 8h.01M11 12h1v5h1",
  decision: "M12 3l9 9-9 9-9-9z",
  warn: "M12 4 2.5 20h19zM12 10v4M12 17h.01",
  llm: "M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18",
  tool: "M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z",
  human: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  progress: "M5 12h.01M12 12h.01M19 12h.01",
  status: "M6 6h12v12H6z",
  check: "M5 12l5 5L20 7",
  cross: "M6 6l12 12M18 6 6 18",
  download: "M12 4v11M7 10l5 5 5-5M5 20h14",
  external: "M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5",
};

export default function Icon({ name, size = 14, className }: { name: keyof typeof PATHS | string; size?: number; className?: string }) {
  const filled = name === "play";
  return (
    <svg className={`icon ${className ?? ""}`} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"
      fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth={filled ? 0 : 2} strokeLinecap="round" strokeLinejoin="round">
      <path d={PATHS[name] ?? PATHS.info} />
    </svg>
  );
}
