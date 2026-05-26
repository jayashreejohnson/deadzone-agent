"use client";
import { useEffect, useState } from "react";

/**
 * Simple email waitlist capture. No backend wired yet — stores the email in
 * localStorage so we don't lose it, and shows a friendly confirmation.
 *
 * Added based on 30-agent test feedback where multiple reviewers (Hiroshi,
 * Sofia, Linda, Liv, Tom) said "missed opportunity — I'd give you my email
 * right now if you asked." See also: 18-agent earlier round, same point.
 *
 * When a real backend is available, replace _save() with a POST.
 */

const LIST_KEY = "deadzone.waitlist.v1";

function _save(email: string): void {
  try {
    const existing = window.localStorage.getItem(LIST_KEY) || "";
    const next = existing
      ? existing.split(",").filter((e) => e && e !== email).concat([email]).join(",")
      : email;
    window.localStorage.setItem(LIST_KEY, next);
  } catch { /* ignore */ }
}

function _has(email: string): boolean {
  try {
    const existing = window.localStorage.getItem(LIST_KEY) || "";
    return existing.split(",").includes(email);
  } catch { return false; }
}

export default function WaitlistForm({ variant = "default" }: { variant?: "default" | "footer" }) {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // If they've already joined in this browser, show the confirmation state.
  useEffect(() => {
    try {
      const existing = window.localStorage.getItem(LIST_KEY);
      if (existing) setSubmitted(true);
    } catch { /* ignore */ }
  }, []);

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const trimmed = email.trim();
    if (!trimmed || !trimmed.includes("@") || !trimmed.includes(".")) {
      setError("Please enter a valid email.");
      return;
    }
    _save(trimmed);
    setSubmitted(true);
  }

  if (submitted) {
    return (
      <div
        className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium"
        style={{
          background: "rgba(16,185,129,0.08)",
          border:     "1px solid rgba(16,185,129,0.25)",
          color:      "#6ee7b7",
        }}
      >
        <span>✓</span>
        <span>You&apos;re on the list. We&apos;ll let you know when the app ships.</span>
      </div>
    );
  }

  const isFooter = variant === "footer";

  return (
    <form
      onSubmit={onSubmit}
      className="w-full max-w-md"
      style={{ fontFamily: "'Space Grotesk', sans-serif" }}
    >
      <div
        className="flex items-stretch gap-1 p-1 rounded-2xl"
        style={{
          background: "rgba(255,255,255,0.04)",
          border:     `1px solid ${error ? "rgba(239,68,68,0.4)" : "rgba(167,139,250,0.22)"}`,
          boxShadow:  isFooter ? "none" : "0 8px 24px -12px rgba(167,139,250,0.25)",
        }}
      >
        <input
          type="email"
          placeholder="your@email.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-label="Email address"
          className="flex-1 bg-transparent px-4 py-2.5 text-sm outline-none"
          style={{ color: "#e2e8f0" }}
        />
        <button
          type="submit"
          className="px-4 py-2.5 rounded-xl font-semibold text-sm tracking-wide transition-all duration-200 hover:translate-y-[-1px]"
          style={{
            background: "linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)",
            color:      "#fff",
            boxShadow:  "0 4px 14px -4px rgba(167,139,250,0.45)",
          }}
        >
          Notify me
        </button>
      </div>
      {error && (
        <div className="mt-2 text-xs" style={{ color: "#f87171" }}>{error}</div>
      )}
      {!error && (
        <div className="mt-2 text-[11px] tracking-wide" style={{ color: "#475569" }}>
          No spam. One email when the app launches.
        </div>
      )}
    </form>
  );
}
