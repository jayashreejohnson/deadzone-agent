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


def _render_html(title: str, route_id: str, sections: list[dict]) -> str:
    parts = [f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; max-width: 720px;
         margin: 2rem auto; padding: 0 1rem; line-height: 1.55; color: #1a1a1a; }}
  h1 {{ font-size: 1.6rem; margin-bottom: 0.25rem; }}
  .meta {{ color: #666; font-size: 0.85rem; margin-bottom: 2rem; }}
  h2 {{ font-size: 1.15rem; margin-top: 2rem; padding-bottom: 0.25rem; border-bottom: 1px solid #eee; }}
  .summary {{ margin: 0.75rem 0; }}
  .sources {{ margin-top: 0.5rem; padding-left: 1.25rem; font-size: 0.9rem; color: #444; }}
  .sources li {{ margin-bottom: 0.4rem; }}
  .sources a {{ color: #1d4ed8; text-decoration: none; }}
  .badge {{ display: inline-block; padding: 2px 8px; background: #eef2ff; color: #4338ca;
            border-radius: 999px; font-size: 0.75rem; margin-left: 0.5rem; }}
</style>
</head><body>
<h1>{html.escape(title)} <span class="badge">offline pack</span></h1>
<div class="meta">Route: <code>{html.escape(route_id)}</code> · auto-generated, citations preserved</div>
"""]
    for s in sections:
        parts.append(f"<h2>{html.escape(s.get('heading', 'Section'))}</h2>")
        parts.append(f"<div class='summary'>{html.escape(s.get('summary', ''))}</div>")
        srcs = s.get("sources") or []
        if srcs:
            parts.append("<ul class='sources'>")
            for src in srcs:
                url = html.escape(src.get("url", ""))
                t = html.escape(src.get("title", url))
                snip = html.escape(src.get("snippet", ""))
                parts.append(f"<li><a href='{url}' target='_blank'>{t}</a> — {snip}</li>")
            parts.append("</ul>")
    parts.append("</body></html>")
    return "\n".join(parts)


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
                LLMObs.annotate(
                    input_data={"title": title, "route_id": route_id, "section_count": len(sections)},
                    output_data=url,
                    metadata={"backend": "senso", "destination": "cited.md"},
                    tags={"tool": "senso_publish"},
                )
                return url
        except Exception as e:
            await emit({"type": "log", "level": "warn",
                        "msg": f"senso failed ({e!s}); using local static fallback"})
            backend = "static_fallback_after_error"
    fname = f"{uuid.uuid4().hex[:10]}.html"
    fpath = os.path.join(_PACKS_DIR, fname)
    with open(fpath, "w") as f:
        f.write(_render_html(title, route_id, sections))
    url = f"{_PUBLIC_BASE}/static/packs/{fname}"
    LLMObs.annotate(
        input_data={"title": title, "route_id": route_id, "section_count": len(sections)},
        output_data=url,
        metadata={"backend": backend, "file": fname},
        tags={"tool": "senso_publish"},
    )
    return url
