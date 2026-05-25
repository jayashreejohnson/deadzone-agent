"use client";

export default function PackModal({
  url, html, cached, onClose,
}: { url: string; html?: string | null; cached: boolean; onClose: () => void }) {
  // Prefer the cached HTML blob (works without network). Fall back to URL.
  const offline = !!html;

  // Guard against non-http(s) URLs before setting iframe src.
  const safeUrl = url.startsWith("http://") || url.startsWith("https://") ? url : "";

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center p-6"
      style={{ background: "rgba(0,0,0,0.82)", backdropFilter: "blur(6px)" }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-4xl h-[88vh] rounded-2xl flex flex-col overflow-hidden"
        style={{
          background: "#050810",
          border: "1px solid rgba(0,212,255,0.18)",
          boxShadow: "0 0 80px rgba(0,212,255,0.08), 0 40px 80px rgba(0,0,0,0.8)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 py-3 shrink-0"
          style={{ borderBottom: "1px solid rgba(0,212,255,0.1)", background: "rgba(0,212,255,0.03)" }}
        >
          <div className="flex items-center gap-2.5">
            <span className="text-sm font-semibold" style={{ color: "#e2e8f0" }}>
              📡 Continuity Pack
            </span>
            {cached ? (
              <span
                className="px-2 py-0.5 text-[10px] font-semibold rounded-full tracking-wide"
                style={{ background: "rgba(139,92,246,0.15)", color: "#c4b5fd", border: "1px solid rgba(139,92,246,0.3)" }}
              >
                ⚡ instant delivery
              </span>
            ) : (
              <span
                className="px-2 py-0.5 text-[10px] font-semibold rounded-full tracking-wide"
                style={{ background: "rgba(16,185,129,0.12)", color: "#6ee7b7", border: "1px solid rgba(16,185,129,0.25)" }}
              >
                ✓ freshly built
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-lg leading-none px-2 py-0.5 rounded-lg transition-colors"
            style={{ color: "#475569" }}
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Pack content */}
        {html ? (
          <iframe
            srcDoc={html}
            className="flex-1 w-full"
            style={{ background: "#050810", border: "none" }}
            sandbox="allow-popups allow-same-origin"
            title="Offline continuity pack"
          />
        ) : safeUrl ? (
          <iframe
            src={safeUrl}
            className="flex-1 w-full"
            style={{ background: "#050810", border: "none" }}
            sandbox="allow-scripts allow-popups allow-same-origin"
            title="Continuity pack"
          />
        ) : (
          <div className="flex-1 flex items-center justify-center text-sm" style={{ color: "#475569" }}>
            Pack URL unavailable.
          </div>
        )}

        {/* Footer — URL + offline badge */}
        <div
          className="px-3 py-2 shrink-0 flex items-center gap-2 text-[10px] font-mono"
          style={{ borderTop: "1px solid rgba(255,255,255,0.05)", color: "#334155" }}
        >
          {offline && (
            <span
              className="px-1.5 py-0.5 rounded font-sans font-medium"
              style={{ background: "rgba(16,185,129,0.1)", color: "#6ee7b7", fontSize: "9px", letterSpacing: "0.1em", textTransform: "uppercase" }}
            >
              offline cache
            </span>
          )}
          <span className="truncate">{url}</span>
        </div>
      </div>
    </div>
  );
}
