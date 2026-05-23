"use client";

export default function PackModal({
  url, cached, paidAmount, onClose,
}: { url: string; cached: boolean; paidAmount?: number; onClose: () => void }) {
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
        <iframe src={url} className="flex-1 w-full bg-white" />
        <div className="p-2 border-t bg-slate-50 text-xs text-slate-500 truncate shrink-0">
          <span className="font-mono">{url}</span>
        </div>
      </div>
    </div>
  );
}
