"""Senso publish wrapper. Falls back to a self-hosted static HTML file so demo always returns a URL.

A finished pack contains:
  1. A curated, offline-readable SUMMARY for each section (the gist , 
     mile markers, phone numbers, procedures).
  2. CACHED SNAPSHOTS of each source URL, fetched at build time and
     embedded inline so the user can actually READ the underlying
     page when there's no signal. This is the whole DeadZone value
     prop: the pack IS the offline copy, not a link to it.
"""
from __future__ import annotations
import os
import re
import uuid
import html
import asyncio
import httpx
from bus import emit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

SENSO_URL = "https://api.senso.ai/v1/publish"  # TODO: confirm shape with docs
_API_KEY = os.getenv("SENSO_API_KEY", "").strip()
_PUBLIC_BASE = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
_PACKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "packs")
os.makedirs(_PACKS_DIR, exist_ok=True)

# Snapshot fetcher knobs.
_SNAPSHOT_TIMEOUT = float(os.getenv("PACK_SNAPSHOT_TIMEOUT_SEC", "6"))
_SNAPSHOT_MAX_CHARS = int(os.getenv("PACK_SNAPSHOT_MAX_CHARS", "6000"))
_SNAPSHOT_UA = (
    "Mozilla/5.0 (compatible; DeadZonePackBuilder/1.0; "
    "+https://deadzone.example/about)"
)

# Phone-number pattern for auto-linking. Matches US-style (XXX) XXX-XXXX
# and XXX-XXX-XXXX, plus *NHP / 911 short codes.
_PHONE_RE = re.compile(
    r"\b(?:\(\d{3}\)\s*\d{3}-\d{4}|\d{3}-\d{3}-\d{4}|\*\d{2,4})\b"
)


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


def _linkify_phones(escaped_text: str) -> str:
    """Wrap phone-number-like substrings in tel: links so they're tappable.

    Operates on already-html-escaped text. Phones work even when offline
    (cellular voice doesn't need data), so this makes the pack actionable
    inside a dead zone.
    """
    def repl(m: re.Match) -> str:
        raw = m.group(0)
        # tel: needs digits only (preserve a leading * for short codes)
        digits = re.sub(r"[^\d*]", "", raw)
        return f'<a class="tel" href="tel:{digits}">{raw}</a>'
    return _PHONE_RE.sub(repl, escaped_text)


def _render_summary(summary: str) -> str:
    """Convert a plain-text summary to readable HTML.

    Preserves paragraph breaks (blank lines), bullet markers (lines
    starting with "• ", "- ", "* "), and bolded headings (all-caps
    or terminated with a colon) that appear at the start of paragraphs.
    Auto-links phone numbers as tel: links.
    """
    if not summary:
        return ""
    s = summary.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p.strip("\n") for p in s.split("\n\n") if p.strip()]
    out_parts: list[str] = []
    for para in paragraphs:
        lines = para.split("\n")
        # Detect bullet-list paragraphs.
        if all(l.lstrip().startswith(("• ", "- ", "* ")) for l in lines if l.strip()):
            items = []
            for l in lines:
                stripped = l.lstrip()
                if not stripped:
                    continue
                for marker in ("• ", "- ", "* "):
                    if stripped.startswith(marker):
                        stripped = stripped[len(marker):]
                        break
                items.append(f"<li>{_linkify_phones(html.escape(stripped))}</li>")
            out_parts.append(f'<ul class="sec-ul">{"".join(items)}</ul>')
            continue
        # Mixed paragraph: render with <br> for line breaks, and emphasize
        # a leading ALL-CAPS / "Heading:" line as a strong tag.
        rendered_lines = []
        for i, l in enumerate(lines):
            esc = _linkify_phones(html.escape(l))
            if i == 0 and (l.isupper() or l.endswith(":")):
                esc = f"<strong>{esc}</strong>"
            elif l.lstrip().startswith(("• ", "- ", "* ")):
                content = l.lstrip()[2:]
                esc = f"&nbsp;&nbsp;&bull;&nbsp;{_linkify_phones(html.escape(content))}"
            rendered_lines.append(esc)
        out_parts.append("<p>" + "<br>".join(rendered_lines) + "</p>")
    return "".join(out_parts)


# ── Cached webpage snapshots ─────────────────────────────────────

# Tags allowed inside an embedded cached snapshot. Everything else is
# stripped to keep the pack lightweight, safe, and visually consistent.
_ALLOWED_TAGS = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "blockquote",
    "strong", "em", "b", "i", "u", "a", "br", "hr",
    "table", "thead", "tbody", "tr", "td", "th",
    "figure", "figcaption",
}
# Tags to wholesale drop along with their contents.
_DROP_TAGS = {
    "script", "style", "iframe", "noscript", "form", "input", "button",
    "select", "textarea", "nav", "header", "footer", "aside",
    "svg", "canvas", "video", "audio", "object", "embed", "link", "meta",
}


def _extract_main_content(html_text: str) -> str:
    """Best-effort 'reader mode' extraction.

    Strategy:
      1. Parse the HTML with BeautifulSoup.
      2. Drop all _DROP_TAGS (script/style/nav/footer/ads/etc).
      3. Pick the densest <article>/<main>/<div> block by text length.
      4. Whitelist a small set of tags; strip everything else but keep text.
      5. Truncate to _SNAPSHOT_MAX_CHARS so packs stay small.

    Returns sanitized HTML (a fragment, no <html>/<body>).
    """
    try:
        from bs4 import BeautifulSoup, NavigableString
    except Exception:
        return ""
    try:
        soup = BeautifulSoup(html_text, "html.parser")
    except Exception:
        return ""
    # Drop unwanted tags entirely.
    for t in soup(list(_DROP_TAGS)):
        t.decompose()
    # Pick the best content container.
    candidates = soup.find_all(["article", "main"])
    if not candidates:
        candidates = soup.find_all("div")
    if not candidates:
        candidates = [soup.body or soup]
    best = max(candidates, key=lambda el: len(el.get_text(strip=True)) if el else 0)

    # Walk and emit only whitelisted tags.
    def emit(el) -> str:
        if isinstance(el, NavigableString):
            return html.escape(str(el))
        name = (el.name or "").lower()
        inner = "".join(emit(c) for c in el.children)
        if name == "a":
            href = el.get("href") or ""
            if href.startswith("http"):
                return f'<a href="{html.escape(href)}" target="_blank" rel="noopener">{inner}</a>'
            return inner
        if name in _ALLOWED_TAGS:
            return f"<{name}>{inner}</{name}>"
        return inner

    out = emit(best).strip()
    if len(out) > _SNAPSHOT_MAX_CHARS:
        out = out[:_SNAPSHOT_MAX_CHARS] + "<p><em>… (truncated for pack size)</em></p>"
    return out


# Bot-block / WAF / paywall patterns. If any of these show up in the first
# few KB of a response body, we treat the page as unreadable and skip
# caching it, otherwise the pack would just embed a Cloudflare challenge
# page next to a "Read cached page" button, which is the bug the user
# is seeing right now.
_BLOCKED_BODY_PATTERNS = (
    # Cloudflare challenge / managed-challenge pages
    "just a moment", "checking your browser", "checking if the site connection",
    "cf-browser-verification", "cf-challenge-running", "challenge-platform",
    "challenge-form", "cf-mitigated", "cf-please-wait",
    "performance & security by cloudflare", "ray id:",
    "attention required", "ddos protection by cloudflare",
    # Generic JS-required / Are-you-human
    "enable javascript", "please enable javascript", "javascript is required",
    "please verify you are human", "please verify you are a human",
    "verify you are a human", "verify that you are not a robot",
    "are you a robot", "are you human", "complete the security check",
    "please complete the security check",
    # Access denied / WAF blocks
    "access denied", "access to this page has been denied",
    "access to this resource", "you don't have permission",
    "you do not have permission", "forbidden", "403 forbidden", "error 403",
    "sorry, you have been blocked", "your access has been blocked",
    "your ip has been blocked", "why have i been blocked",
    "this website is using a security service",
    "we are sorry, you are not allowed",
    # CAPTCHA
    "captcha", "recaptcha", "hcaptcha", "turnstile",
    # Commercial WAF / bot mitigation vendors
    "perimeterx", "datadome", "sucuri website firewall",
    "incapsula incident id", "request unsuccessful. incapsula",
    "akamai reference", "akamai bot manager",
    "imperva incident", "f5 networks",
    # Paywall / login walls
    "subscribe to continue", "subscribe to keep reading",
    "sign in to continue", "log in to continue", "login to view",
    "create a free account to continue", "create a free account to read",
    "you've reached your monthly limit", "you've reached your free article limit",
    "register to continue reading", "to continue reading, log in",
    # Generic error / maintenance
    "site maintenance", "service unavailable",
    "we'll be right back", "we are currently performing maintenance",
)


def _looks_blocked(html_text: str) -> bool:
    if not html_text:
        return True
    sample = html_text[:4096].lower()
    return any(p in sample for p in _BLOCKED_BODY_PATTERNS)


async def _fetch_snapshot(url: str) -> tuple[str | None, str | None]:
    """Fetch a URL and return (sanitized_inner_html, fetched_title) or (None, None).

    Returns (None, None) for:
      - non-http(s) URLs
      - network errors / timeouts
      - non-html responses
      - non-2xx status
      - bot-block / WAF / paywall pages (so we don't bake a Cloudflare
        challenge into the pack)
      - extracted content too short to be useful (< 200 chars)
    """
    if not url or not url.startswith("http"):
        return None, None
    try:
        async with httpx.AsyncClient(
            timeout=_SNAPSHOT_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _SNAPSHOT_UA, "Accept": "text/html,*/*;q=0.5"},
        ) as client:
            r = await client.get(url)
            if r.status_code >= 400 or "html" not in (r.headers.get("content-type") or ""):
                return None, None
            text = r.text
    except Exception:
        return None, None

    if _looks_blocked(text):
        return None, None

    # Pull <title> for fallback display.
    title = None
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, "html.parser")
        if soup.title and soup.title.string:
            title = soup.title.string.strip()[:140]
    except Exception:
        pass

    sanitized = _extract_main_content(text)
    # Reject snapshots with so little extracted content that the accordion
    # would look broken (often happens on JS-only sites where bs4 sees the
    # shell page with no article body). 500 chars is roughly a couple of
    # paragraphs, enough to be useful and to weed out empty shells.
    if not sanitized or len(sanitized.strip()) < 500:
        return None, None
    # Final scan of the extracted content itself, just in case a block
    # phrase only shows up in the article block (not the page shell).
    if _looks_blocked(sanitized):
        return None, None
    return sanitized, title


async def _fetch_all_snapshots(sources: list[dict]) -> dict[str, dict]:
    """Fetch snapshots for all source URLs in parallel.

    Skips sources marked `reachable: False` (nimble's reachability check
    already flagged them as bot-blocked / 404 / dead, so we save the
    network round-trip). Returns {url: {"html": "...", "title": "..."}}
    for each that succeeded.
    """
    urls = [
        s.get("url", "") for s in sources
        if s.get("url", "").startswith("http") and s.get("reachable", True)
    ]
    if not urls:
        return {}
    results = await asyncio.gather(*(_fetch_snapshot(u) for u in urls), return_exceptions=False)
    out: dict[str, dict] = {}
    for url, (snippet_html, title) in zip(urls, results):
        if snippet_html:
            out[url] = {"html": snippet_html, "title": title}
    return out


def _render_html(title: str, route_id: str, sections: list[dict], snapshots: dict[str, dict] | None = None) -> str:
    from datetime import datetime, timezone
    snapshots = snapshots or {}
    ts = datetime.now(timezone.utc).strftime("%b %d, %Y at %H:%M UTC")

    # Strict source filter: only keep sources where we actually have a
    # successful cached snapshot. If our scraper got a clean read, the
    # user's browser will too. If we couldn't get clean content (block
    # page, JS-only shell, paywall, timeout), hide the source entirely
    # so the user never taps into a Cloudflare challenge.
    #
    # The curated summary at the top of each section already carries the
    # actionable offline content (mile markers, phone numbers, procedures).
    # An empty source list is fine for sections where every source got
    # filtered out, the summary is the real value.
    for s in sections:
        srcs = s.get("sources") or []
        s["sources"] = [
            src for src in srcs
            if src.get("reachable", True) and snapshots.get(src.get("url", ""))
        ]

    total_sources = sum(len(s.get("sources") or []) for s in sections)
    total_cached  = total_sources  # all kept sources are cached by definition now

    sections_html_parts = []
    for sec_idx, s in enumerate(sections):
        heading = s.get("heading", "Section")
        summary = s.get("summary", "")
        srcs = s.get("sources") or []
        icon = _section_icon(heading)

        sources_inner = ""
        for src_idx, src in enumerate(srcs):
            url       = src.get("url", "")
            reachable = src.get("reachable", True)
            t         = html.escape(src.get("title") or url or "Source")
            snip      = html.escape(src.get("snippet", ""))
            snap      = snapshots.get(url)  # cached page content if we got one
            row_id    = f"s{sec_idx}-{src_idx}"

            # If we have a cached snapshot, show it inline (accordion).
            snap_html = ""
            if snap:
                snap_title = html.escape(snap.get("title") or src.get("title") or "Cached page")
                inner_html = snap.get("html", "")
                snap_html = (
                    f'<details class="snap"><summary class="snap-toggle">'
                    f'<span class="snap-icon">📄</span>'
                    f'<span class="snap-lbl">Read cached page</span>'
                    f'<span class="snap-meta">{snap_title}</span>'
                    f'<span class="snap-chev">▾</span>'
                    f'</summary>'
                    f'<div class="snap-body">{inner_html}</div>'
                    f'</details>'
                )

            snip_html = f'<div class="src-snip">{snip}</div>' if snip else ""
            badge = ' <span class="src-cached">cached</span>' if snap else ''
            if url and reachable:
                sources_inner += (
                    f'<div class="src-block">'
                    f'<a href="{html.escape(url)}" target="_blank" rel="noopener" class="src-row">'
                    f'<span class="src-dot"></span>'
                    f'<span class="src-body"><span class="src-title">{t}{badge}</span>{snip_html}</span>'
                    f'<span class="src-arrow">&#8599;</span></a>'
                    f'{snap_html}'
                    f'</div>'
                )
            else:
                sources_inner += (
                    f'<div class="src-block">'
                    f'<div class="src-row src-dead">'
                    f'<span class="src-dot dead"></span>'
                    f'<span class="src-body"><span class="src-title dead">{t}</span>{snip_html}</span>'
                    f'</div>'
                    f'{snap_html}'
                    f'</div>'
                )

        sources_block = (
            f'<div class="src-lbl">Sources, readable offline when cached</div>'
            f'<div class="sources">{sources_inner}</div>'
        ) if srcs else ""
        # Preserve newlines and basic bullet formatting from the summary.
        # The curated content uses \n for paragraph breaks and "• " for
        # bullets, we render those as proper HTML so the pack is
        # readable as a document, not a wall of text.
        summary_html = _render_summary(summary)
        sections_html_parts.append(
            f'<div class="sec">'
            f'<div class="sec-head"><span class="sec-icon">{icon}</span>'
            f'<span>{html.escape(heading)}</span></div>'
            f'<div class="sec-summary">{summary_html}</div>'
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
.sec-summary{{font-size:.86rem;color:#cbd5e1;line-height:1.65;margin-bottom:.55rem}}
.sec-summary p{{margin-bottom:.6rem}}
.sec-summary p:last-child{{margin-bottom:0}}
.sec-summary strong{{display:block;
                     font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;
                     color:#7dd3fc;font-weight:700;margin-bottom:.45rem;
                     padding-bottom:.4rem;border-bottom:1px solid rgba(125,211,252,.12)}}
.sec-summary ul.sec-ul{{list-style:none;padding-left:0;margin:.3rem 0 .6rem 0}}
.sec-summary ul.sec-ul li{{padding-left:1.1rem;position:relative;margin-bottom:.32rem;color:#cbd5e1}}
.sec-summary ul.sec-ul li::before{{content:"";position:absolute;left:.15rem;top:.55rem;
                                    width:5px;height:5px;border-radius:50%;
                                    background:#00d4ff;box-shadow:0 0 6px rgba(0,212,255,.5)}}

/* tel: links, call-from-deadzone affordance */
.sec-summary a.tel{{color:#6ee7b7;font-weight:600;text-decoration:none;
                    border-bottom:1px dotted rgba(110,231,183,.4);
                    padding:0 1px}}
.sec-summary a.tel:hover{{color:#a7f3d0;border-bottom-style:solid}}
.sec-summary a.tel::before{{content:"☎ ";font-size:.85em;opacity:.7}}

.src-lbl{{font-size:.55rem;text-transform:uppercase;letter-spacing:.16em;
          color:#475569;margin:1rem 0 .4rem 0;font-weight:600;
          padding-top:.55rem;border-top:1px dashed rgba(255,255,255,.05)}}

.sources{{display:flex;flex-direction:column;gap:.5rem;margin-top:.1rem}}
.src-block{{background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.05);
            border-radius:8px;overflow:hidden}}
.src-block .src-row{{background:transparent;border:none;border-radius:0}}
.src-block .src-row:hover{{background:rgba(0,212,255,.05)}}

.src-cached{{display:inline-block;font-size:.55rem;font-weight:700;
             text-transform:uppercase;letter-spacing:.1em;
             background:rgba(16,185,129,.12);color:#6ee7b7;
             border:1px solid rgba(16,185,129,.25);
             padding:1px 6px;border-radius:999px;margin-left:.4rem;
             vertical-align:middle}}

/* Cached snapshot accordion */
.snap{{border-top:1px solid rgba(255,255,255,.05);background:rgba(0,212,255,.02)}}
.snap-toggle{{display:flex;align-items:center;gap:.5rem;padding:.55rem .65rem;
              font-size:.7rem;color:#7dd3fc;cursor:pointer;list-style:none;
              user-select:none;font-weight:500}}
.snap-toggle::-webkit-details-marker{{display:none}}
.snap-icon{{font-size:.85rem}}
.snap-lbl{{text-transform:uppercase;letter-spacing:.1em;font-size:.6rem;
           font-weight:700;color:#7dd3fc;flex-shrink:0}}
.snap-meta{{flex:1;min-width:0;color:#64748b;font-size:.65rem;font-weight:400;
            white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.snap-chev{{color:#475569;transition:transform .15s;flex-shrink:0}}
details[open] .snap-chev{{transform:rotate(180deg)}}
.snap-body{{padding:.7rem 1rem 1rem 1rem;font-size:.78rem;line-height:1.55;
            color:#cbd5e1;background:rgba(5,8,16,.6);
            max-height:60vh;overflow-y:auto}}
.snap-body h1,.snap-body h2{{font-size:.95rem;color:#e2e8f0;margin:.6rem 0 .35rem}}
.snap-body h3,.snap-body h4{{font-size:.85rem;color:#e2e8f0;margin:.5rem 0 .25rem}}
.snap-body p{{margin-bottom:.5rem}}
.snap-body ul,.snap-body ol{{padding-left:1.2rem;margin-bottom:.5rem}}
.snap-body li{{margin-bottom:.25rem}}
.snap-body a{{color:#7dd3fc;text-decoration:underline}}
.snap-body table{{font-size:.72rem;border-collapse:collapse;margin:.5rem 0}}
.snap-body th,.snap-body td{{padding:.3rem .5rem;border:1px solid rgba(255,255,255,.08)}}
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
    <div class="hdr-meta">Generated {ts} &middot; {total_sources} sources cached for offline reading</div>
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
    # Fetch cached snapshots in parallel for every source URL.
    # This is what makes the pack actually usable offline, the source
    # content is baked into the HTML, not just linked.
    all_sources: list[dict] = []
    for s in sections:
        all_sources.extend(s.get("sources") or [])
    snapshots = await _fetch_all_snapshots(all_sources) if all_sources else {}
    cached_n = len(snapshots)
    total_n  = sum(1 for s in all_sources if s.get("url", "").startswith("http"))
    await emit({"type": "log", "level": "info",
                "msg": f"Cached {cached_n}/{total_n} source pages into pack"})

    fname = f"{uuid.uuid4().hex[:10]}.html"
    fpath = os.path.join(_PACKS_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(_render_html(title, route_id, sections, snapshots))
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
