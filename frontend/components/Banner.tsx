"use client";

export type BannerState = "idle" | "warning" | "building" | "ready";

export default function Banner({
  state, message, onClick,
}: { state: BannerState; message: string; onClick?: () => void }) {
  if (state === "idle") return null;

  const styles: Record<BannerState, string> = {
    idle: "",
    warning: "bg-orange-500/90 text-white",
    building: "bg-blue-500/90 text-white",
    ready: "bg-emerald-500/90 text-white cursor-pointer hover:bg-emerald-400",
  };
  const icons: Record<BannerState, string> = {
    idle: "", warning: "⚠️", building: "🔄", ready: "✅",
  };

  return (
    <div
      onClick={state === "ready" ? onClick : undefined}
      className={`fixed top-0 left-0 right-0 z-[1100] px-4 py-3 text-center font-medium shadow-lg flex items-center justify-center gap-3 ${styles[state]}`}
    >
      <span className={state === "building" ? "animate-spin inline-block" : ""}>
        {icons[state]}
      </span>
      <span>{message}</span>
      {state === "ready" && <span className="text-xs opacity-80">(click to open pack)</span>}
    </div>
  );
}
