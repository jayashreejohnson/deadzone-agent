"""Pre-seed historical packs/events so the dashboard isn't empty at demo start.

Also inserts ONE recent pack for route=nyc_to_burlington, deadzone=adk_north_42 owned by
user_a — this is what user_b's agent will buy during the demo.
"""
from __future__ import annotations
import time
from datetime import datetime, timedelta
from tools import clickhouse_db as db


def seed_signal_history() -> None:
    """Insert ~20 synthetic signal quality data points for the Manhattan-to-Newark route.

    Signal quality varies to create realistic dead zones around Lincoln Tunnel coordinates.
    signal_dbm values: strong signal = -60 to -75, weak = -85 to -95, dead zone = -100 to -113.
    """
    route_id = "manhattan_to_newark@17:00"

    # Waypoints along Manhattan → Lincoln Tunnel → Newark
    # Each tuple: (lat, lng, signal_dbm, offset_minutes)
    waypoints = [
        # Manhattan — good signal
        (40.7580, -73.9855, -62, -20),   # Times Square area
        (40.7558, -73.9990, -65, -18),   # 9th Ave / 40th St
        (40.7540, -74.0020, -68, -16),   # 10th Ave approach
        (40.7530, -74.0070, -72, -14),   # Lincoln Tunnel entrance approach
        # Lincoln Tunnel — dead zone begins
        (40.7621, -74.0185, -88, -12),   # Tunnel entrance (signal degrading)
        (40.7621, -74.0245, -97, -10),   # Tunnel mid-entry
        (40.7621, -74.0312, -110, -8),   # Lincoln Tunnel Mid (deep dead zone)
        (40.7621, -74.0370, -108, -6),   # Tunnel mid-exit
        (40.7621, -74.0430, -95, -4),    # Tunnel exit (signal recovering)
        # NJ Turnpike / Weehawken — signal recovering
        (40.7600, -74.0500, -82, -2),    # NJ Turnpike approach
        (40.7545, -74.0620, -75, 0),     # Weehawken
        (40.7490, -74.0750, -70, 2),     # North Bergen
        # Route 3 toward Newark — mixed signal
        (40.7430, -74.0900, -73, 4),     # Secaucus area
        (40.7380, -74.1050, -78, 6),     # Rutherford approach
        (40.7357, -74.1200, -85, 8),     # McCarter Hwy approach (signal dips)
        (40.7357, -74.1500, -102, 10),   # Newark McCarter Hwy (second dead zone)
        (40.7357, -74.1724, -105, 12),   # Newark McCarter Hwy Mid
        (40.7357, -74.1900, -97, 14),    # McCarter exit
        # Newark downtown — recovering
        (40.7357, -74.2050, -76, 16),    # Newark Penn Station area
        (40.7282, -74.1724, -68, 18),    # Newark downtown
    ]

    for lat, lng, dbm, offset_min in waypoints:
        ts = datetime.utcnow() - timedelta(minutes=abs(offset_min) + 30)
        db.save_signal_quality(route_id, lat, lng, dbm, ts)


def seed_if_empty() -> None:
    if db.has_any_events():
        print("[seed] events table not empty — skipping seed.")
        seed_signal_history()  # always seed signal history (in-memory, idempotent)
        return

    print("[seed] seeding historical events + demo cache pack.")
    seed_signal_history()

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
    import os as _os
    _pub_base = _os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    for i in range(3):
        db.save_pack(
            route_id="nyc_to_burlington",
            deadzone_id=f"hist_zone_{i}",
            url=f"{_pub_base}/static/packs/hist_{i}.html",
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
    with open(fpath, "w", encoding="utf-8") as f:
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
