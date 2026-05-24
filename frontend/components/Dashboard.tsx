"use client";
import { useEffect, useState } from "react";

type Summary = {
  packs_built: number;
  packs_sold: number;
  total_paid_usd: number;
  avg_build_ms: number;
  recent_events: { user_id: string; action: string; deadzone_id: string; pack_id: string; ts: string }[];
};

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export default function Dashboard() {
  const [data, setData] = useState<Summary | null>(null);

  useEffect(() => {
    let alive = true;
    const fetchOnce = async () => {
      try {
        const r = await fetch(`${API}/dashboard`);
        const j = await r.json();
        if (alive) setData(j);
      } catch {}
    };
    fetchOnce();
    const id = setInterval(fetchOnce, 3000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const stat = (label: string, value: string | number) => (
    <div className="bg-slate-900 border border-slate-800 rounded-lg px-4 py-3">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="text-2xl font-semibold mt-1 text-slate-100">{value}</div>
    </div>
  );

  return (
    <div className="bg-slate-950 border-t border-slate-800 px-4 py-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        {stat("packs built", data?.packs_built ?? "—")}
        {stat("packs sold",  data?.packs_sold ?? "—")}
        {stat("$ paid",      data ? `$${data.total_paid_usd.toFixed(2)}` : "—")}
        {stat("avg build",   data ? `${Number(data.avg_build_ms).toFixed(0)} ms` : "—")}
      </div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Recent events</div>
      <div className="overflow-x-auto">
        <table className="text-xs w-full">
          <thead>
            <tr className="text-slate-500 text-left">
              <th className="py-1 pr-3">when</th>
              <th className="py-1 pr-3">user</th>
              <th className="py-1 pr-3">action</th>
              <th className="py-1 pr-3">deadzone</th>
              <th className="py-1 pr-3">pack</th>
            </tr>
          </thead>
          <tbody>
            {(data?.recent_events ?? []).map((e, i) => (
              <tr key={i} className="text-slate-300 border-t border-slate-900">
                <td className="py-1 pr-3 text-slate-500">{new Date(e.ts).toLocaleTimeString()}</td>
                <td className="py-1 pr-3">{e.user_id}</td>
                <td className="py-1 pr-3">
                  <span className={
                    e.action === "built" ? "text-emerald-400" :
                    e.action === "bought" ? "text-violet-300" : "text-slate-400"
                  }>{e.action}</span>
                </td>
                <td className="py-1 pr-3">{e.deadzone_id}</td>
                <td className="py-1 pr-3 text-slate-500">{e.pack_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
