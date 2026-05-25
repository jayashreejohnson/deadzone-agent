"""Senso publish wrapper. Falls back to a self-hosted static HTML file so demo always returns a URL."""
from __future__ import annotations
import os
import uuid
import html
import httpx
from bus import emit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

SENSO_URL = "https://api.senso.ai/v1/publish"  # TODO: confirm shape with docs
_API_KEY = os.getenv("SENSO_API_KEY", "").strip()
_PUBLIC_BASE = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
_PACKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "packs")
os.makedirs(_PACKS_DIR, exist_ok=True)


def _section_icon(heading: str) -> str:
    h = heading.lower()
    if any(w in h for w in ["weather", "forecast", "storm", "rain", "wind", "elevation", "mountain weather"]):
        return "🌦"
    if any(w in h for w in ["transit", "delay", "alert", "subway", "train", "bart", "metro", "service alert"]):
        return "🚇"
    if any(w in h for w in ["emergency", "rescue", "sheriff", "sar", "hospital", "contact"]):
        return "🆘"
    if any(w in h for w in ["fuel", "gas", "service before", "rest stop"]):
        return "⛽"
    if any(w in h for w in ["road", "traffic", "closure", "construction", "highway", "condition", "avalanche"]):
        return "🛣"
    if any(w in h for w in ["news", "local", "update"]):
        return "📰"
    if any(w in h for w in ["nearby", "poi", "exit", "services"]):
        return "📍"
    return "📋"


def _render_html(title: str, route_id: str, sections: list[dict]) -> str:
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%b %d, %Y at %H:%M UTC")
    total_sources = sum(len(s.get("sources") or []) for s in sections)

    sections_html_parts = []
    for s in sections:
        heading = s.get("heading", "Section")
        summary = s.get("summary", "")
        srcs = s.get("sources") or []
        icon = _section_icon(heading)

        sources_inner = ""
        for src in srcs:
            url       = src.get("url", "")
            reachable = src.get("reachable", True)
            t         = html.escape(src.get("title") or url or "Source")
            snip      = html.escape(src.get("snippet", ""))
            snip_html = f'<div class="src-snip">{snip}</div>' if snip else ""
            if url and reachable:
                sources_inner += (
                    f'<a href="{html.escape(url)}" target="_blank" class="src-row">'
                    f'<span class="src-dot"></span>'
                    f'<span class="src-body"><span class="src-title">{t}</span>{snip_html}</span>'
                    f'<span class="src-arrow">&#8599;</span></a>'
                )
            else:
                sources_inner += (
                    f'<div class="src-row src-dead">'
                    f'<span class="src-dot dead"></span>'
                    f'<span class="src-body"><span class="src-title dead">{t}</span>{snip_html}</span>'
                    f'</div>'
                )

        sources_block = f'<div class="sources">{sources_inner}</div>' if srcs else ""
        sections_html_parts.append(
            f'<div class="sec">'
            f'<div class="sec-head"><span class="sec-icon">{icon}</span>'
            f'<span>{html.escape(heading)}</span></div>'
            f'<div class="sec-summary">{html.escape(summary)}</div>'
            f'{sources_block}</div>'
        )

    sections_html = "\n".join(sections_html_parts)

    tags_html = "".join(
        f'<span class="tag">{_section_icon(s.get("heading",""))} {html.escape(s.get("heading","Section"))}</span>'
        for s in sections
    )

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,sans-serif;
      background:#050810;color:#e2e8f0;min-height:100vh;padding-bottom:3rem}}
a{{color:inherit;text-decoration:none}}

.hdr{{background:rgba(0,212,255,.04);border-bottom:1px solid rgba(0,212,255,.12);
      padding:.9rem 1.1rem;display:flex;align-items:center;gap:.7rem;
      position:sticky;top:0;backdrop-filter:blur(18px);z-index:10}}
.logo{{font-size:.65rem;font-weight:700;color:#00d4ff;letter-spacing:.14em;
       text-transform:uppercase;white-space:nowrap}}
.hdr-body{{flex:1;min-width:0}}
.hdr-title{{font-size:.9rem;font-weight:600;color:#e2e8f0;
            white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.hdr-meta{{font-size:.62rem;color:#475569;margin-top:.12rem}}
.badge{{font-size:.58rem;font-weight:600;text-transform:uppercase;letter-spacing:.14em;
        padding:2px 8px;border-radius:999px;white-space:nowrap;flex-shrink:0;
        background:rgba(16,185,129,.1);color:#6ee7b7;border:1px solid rgba(16,185,129,.22)}}

.wrap{{max-width:640px;margin:0 auto;padding:1.1rem .9rem}}

.sec{{background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.07);
      border-radius:12px;padding:1rem 1.1rem;margin-bottom:.8rem}}
.sec-head{{display:flex;align-items:center;gap:.45rem;font-size:.62rem;font-weight:600;
           text-transform:uppercase;letter-spacing:.18em;color:#00d4ff;margin-bottom:.6rem}}
.sec-icon{{font-size:.95rem;line-height:1}}
.sec-summary{{font-size:.855rem;color:#94a3b8;line-height:1.68;margin-bottom:.55rem}}

.sources{{display:flex;flex-direction:column;gap:.3rem;margin-top:.45rem}}
.src-row{{display:flex;align-items:flex-start;gap:.55rem;padding:.5rem .65rem;
          border-radius:8px;background:rgba(255,255,255,.02);
          border:1px solid rgba(255,255,255,.05);transition:border-color .15s,background .15s}}
a.src-row:hover{{border-color:rgba(0,212,255,.28);background:rgba(0,212,255,.05);cursor:pointer}}
.src-dead{{cursor:default}}
.src-dot{{width:5px;height:5px;border-radius:50%;background:#00d4ff;
          margin-top:5px;flex-shrink:0}}
.src-dot.dead{{background:#334155}}
.src-body{{flex:1;min-width:0}}
.src-title{{font-size:.76rem;font-weight:500;color:#7dd3fc;
            display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.src-title.dead{{color:#475569}}
.src-snip{{font-size:.68rem;color:#475569;margin-top:2px;line-height:1.4}}
.src-arrow{{font-size:.65rem;color:#334155;flex-shrink:0;margin-top:2px}}

.cov{{margin-top:1.1rem;padding:.9rem 1rem;
      background:rgba(16,185,129,.04);border:1px solid rgba(16,185,129,.12);border-radius:10px}}
.cov-lbl{{font-size:.58rem;text-transform:uppercase;letter-spacing:.18em;
          color:#334155;margin-bottom:.45rem}}
.tags{{display:flex;flex-wrap:wrap;gap:.3rem}}
.tag{{font-size:.62rem;padding:2px 9px;border-radius:999px;
      background:rgba(16,185,129,.08);color:#6ee7b7;border:1px solid rgba(16,185,129,.18)}}

.foot{{text-align:center;padding:1.5rem .75rem .75rem;font-size:.62rem;
       color:#1e293b;border-top:1px solid rgba(255,255,255,.04);margin-top:.75rem}}
</style>
</head><body>
<div class="hdr">
  <span class="logo">📡&nbsp;DeadZone</span>
  <div class="hdr-body">
    <div class="hdr-title">{html.escape(title)}</div>
    <div class="hdr-meta">Generated {ts} &middot; {total_sources} cited sources &middot; works without signal</div>
  </div>
  <span class="badge">&#10003; offline ready</span>
</div>
<div class="wrap">
{sections_html}
  <div class="cov">
    <div class="cov-lbl">Pack includes</div>
    <div class="tags">{tags_html}</div>
  </div>
</div>
<div class="foot">Generated by DeadZone Agent &middot; Citations preserved &middot; No signal required</div>
</body></html>"""


@tool(name="senso_publish")
async def publish(title: str, route_id: str, sections: list[dict]) -> str:
    """Publish pack and return public URL. Falls back to local static file on failure."""
    await emit({"type": "tool", "name": "senso", "msg": f"Publishing pack: {title}"})
    backend = "static_fallback"
    if _API_KEY:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    SENSO_URL,
                    headers={"X-API-Key": _API_KEY, "Content-Type": "application/json"},
                    json={"title": title, "route_id": route_id, "sections": sections,
                          "destination": "cited.md", "preserve_citations": True},
                )
                resp.raise_for_status()
                data = resp.json()
            url = data.get("url") or data.get("public_url")
            if url:
                try:
                    LLMObs.annotate(
                        input_data={"title": title, "route_id": route_id, "section_count": len(sections)},
                        output_data=url,
                        metadata={"backend": "senso", "destination": "cited.md"},
                        tags={"tool": "senso_publish"},
                    )
                except Exception:
                    pass  # LLMObs disabled or no active span
                return url
        except Exception as e:
            await emit({"type": "log", "level": "warn",
                        "msg": f"senso failed ({e!s}); using local static fallback"})
            backend = "static_fallback_after_error"
    fname = f"{uuid.uuid4().hex[:10]}.html"
    fpath = os.path.join(_PACKS_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(_render_html(title, route_id, sections))
    url = f"{_PUBLIC_BASE}/static/packs/{fname}"
    try:
        LLMObs.annotate(
            input_data={"title": title, "route_id": route_id, "section_count": len(sections)},
            output_data=url,
            metadata={"backend": backend, "file": fname},
            tags={"tool": "senso_publish"},
        )
    except Exception:
        pass  # LLMObs disabled or no active span
    return url
