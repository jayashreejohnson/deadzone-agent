"""Pre-seed historical packs/events so the dashboard isn't empty at demo start.

Also inserts ONE recent pack for route=nyc_to_burlington, deadzone=adk_north_42 owned by
user_a — this is what user_b's agent will buy during the demo.
"""
from __future__ import annotations
import time
from datetime import datetime, timedelta
from tools import clickhouse_db as db


def seed_if_empty() -> None:
    if db.has_any_events():
        print("[seed] events table not empty — skipping seed.")
        return

    print("[seed] seeding historical events + demo cache pack.")

    # Historical built/bought events
    for i in range(6):
        db.log_event(
            user_id=f"user_demo_{i}",
            route_id="nyc_to_burlington" if i % 2 == 0 else "boston_to_acadia",
            deadzone_id=f"hist_zone_{i}",
            action="built",
            pack_id=f"pk_hist_{i:03d}",
            build_ms=6500 + (i * 700),
        )
    for i in range(4):
        db.log_event(
            user_id=f"user_demo_{i + 10}",
            route_id="nyc_to_burlington",
            deadzone_id=f"hist_zone_{i}",
            action="bought",
            pack_id=f"pk_hist_{i:03d}",
            build_ms=0,
        )

    # Historical packs row entries
    for i in range(3):
        db.save_pack(
            route_id="nyc_to_burlington",
            deadzone_id=f"hist_zone_{i}",
            url=f"http://localhost:8000/static/packs/hist_{i}.html",
            owner_user_id=f"user_demo_{i}",
            source_count=8,
        )

    # Historical payments (sold packs)
    for i in range(4):
        db.log_payment(
            tx_id=f"0xsim_hist_{i:08x}",
            from_user=f"user_demo_{i + 10}",
            to_user=f"user_demo_{i}",
            amount_usd=0.02,
            pack_id=f"pk_hist_{i:03d}",
        )

    # Demo: pre-built pack for user_a's route. user_b will buy this during the demo.
    # NOTE: this pack URL points at the static-fallback HTML format. We write a real file
    # so the modal can iframe it even before user_a triggers a fresh build.
    import os, uuid, html
    here = os.path.dirname(os.path.abspath(__file__))
    packs_dir = os.path.join(here, "static", "packs")
    os.makedirs(packs_dir, exist_ok=True)
    fname = f"seed_{uuid.uuid4().hex[:8]}.html"
    fpath = os.path.join(packs_dir, fname)
    with open(fpath, "w") as f:
        f.write(f"""<!doctype html><html><head><meta charset='utf-8'>
<title>Offline pack: nyc_to_burlington (seeded)</title>
<style>body{{font-family:system-ui;max-width:720px;margin:2rem auto;padding:0 1rem;line-height:1.55}}</style>
</head><body>
<h1>Offline pack: nyc_to_burlington <span style='background:#eef;padding:2px 8px;border-radius:8px;font-size:0.75rem;color:#44c'>seeded</span></h1>
<p>Pre-seeded pack used by the cache-hit demo path. Once user_a triggers a real build,
this seed is superseded by the freshly-published pack.</p>
</body></html>""")

    # Place this seed pack OUTSIDE the cache window so user_a still builds fresh on
    # their first signal, then user_b gets a cache-hit on user_a's NEW pack.
    pub_base = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    db.save_pack(
        route_id="nyc_to_burlington",
        deadzone_id="adk_north_42",
        url=f"{pub_base}/static/packs/{fname}",
        owner_user_id="user_a",
        source_count=8,
        created_at=datetime.utcnow() - timedelta(minutes=20),
    )
    print("[seed] done.")
