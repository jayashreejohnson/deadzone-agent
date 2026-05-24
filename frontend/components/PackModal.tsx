"use client";

export default function PackModal({
  url, html, cached, paidAmount, onClose,
}: { url: string; html?: string | null; cached: boolean; paidAmount?: number; onClose: () => void }) {
  // Prefer the cached HTML blob (works without network). Fall back to URL.
  const offline = !!html;

  // Guard against non-http(s) URLs before setting iframe src.
  const safeUrl = url.startsWith("http://") || url.startsWith("https://") ? url : "";

  return (
    <div
      className="fixed inset-0 z-[9999] bg-black/85 backdrop-blur-sm flex items-center justify-center p-6"
      onClick={onClose}
    >
      <div
        className="bg-white text-black w-full max-w-4xl h-[88vh] rounded-xl shadow-2xl flex flex-col overflow-hidden ring-1 ring-slate-700"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b bg-slate-50 shrink-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold">Offline pack</span>
            {cached ? (
              <span className="px-2 py-0.5 text-xs rounded-full bg-violet-100 text-violet-800">
                bought from agent_a · ${paidAmount?.toFixed(2) ?? "0.02"}
              </span>
            ) : (
              <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-100 text-emerald-800">
                freshly built
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-900 text-xl leading-none px-2"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        {html ? (
          <iframe
            srcDoc={html}
            className="flex-1 w-full bg-white"
            sandbox="allow-popups allow-same-origin"
            title="Offline continuity pack"
          />
        ) : safeUrl ? (
          <iframe
            src={safeUrl}
            className="flex-1 w-full bg-white"
            sandbox="allow-scripts allow-popups allow-same-origin"
            title="Continuity pack"
          />
        ) : (
          <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
            Pack URL unavailable.
          </div>
        )}
        <div className="p-2 border-t bg-slate-50 text-xs text-slate-500 truncate shrink-0 flex items-center gap-2">
          {offline && (
            <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 text-[10px] font-medium">
              served from offline cache
            </span>
          )}
          <span className="font-mono truncate">{url}</span>
        </div>
      </div>
    </div>
  );
}
