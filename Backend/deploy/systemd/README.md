# Phase 3 — Weekly BOM formula refresh (systemd timer)

Refreshes every assembly already in the `bom_formula` cache from NetSuite, weekly, so warm
feasibility stays "DB formula (free) + live inventory". Runs the **same** paced
`refresh_all_bom_formulas()` the admin "Refresh formulas" button uses — no HTTP, no auth: a
standalone process reusing the app's `.env` (DB + NetSuite creds) via `WorkingDirectory`.

A Postgres **advisory lock** (`BOM_REFRESH_LOCK_KEY` in `bom_service.py`) makes this mutually
exclusive with a manual admin-triggered run even though they live in different processes — a
second concurrent trigger returns immediately as `skipped`.

Inventory is never touched here; only the persisted formulas.

## Files
- `app/scripts/refresh_boms.py` — entrypoint (`python -m app.scripts.refresh_boms`).
- `goldfinger-bom-refresh.service` — oneshot unit (absolute venv Python, `WorkingDirectory`).
- `goldfinger-bom-refresh.timer` — `Sat 10:00 UTC` (~6am US-Eastern), `Persistent=true`.

## Install (on the prod box, as a sudo user)
```bash
sudo cp /opt/goldfinger/Backend/deploy/systemd/goldfinger-bom-refresh.service /etc/systemd/system/
sudo cp /opt/goldfinger/Backend/deploy/systemd/goldfinger-bom-refresh.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now goldfinger-bom-refresh.timer
```

## Verify
```bash
systemctl list-timers goldfinger-bom-refresh.timer   # next scheduled run
systemctl status goldfinger-bom-refresh.timer

# Dry-run the job immediately (does a real refresh, paced):
sudo systemctl start goldfinger-bom-refresh.service
journalctl -u goldfinger-bom-refresh -n 50 --no-pager

# Authoritative success signal (same as we verify by hand):
#   bom_formula.refreshed_at timestamps jump to the run time.
```

## Change the schedule
Edit `OnCalendar=` in the `.timer`, then:
```bash
sudo cp .../goldfinger-bom-refresh.timer /etc/systemd/system/ && sudo systemctl daemon-reload
sudo systemctl restart goldfinger-bom-refresh.timer
```

## Notes
- The standalone run updates `bom_formula`/`bom_component` (L2) directly. The live API's
  in-memory L1 (1h TTL) reloads from the fresh L2 within the hour on its own — the same way
  L1 already trails L2 every hour in normal operation.
- Because the cron runs in a separate process, its progress is **not** reflected in the admin
  UI's `/boms/refresh/status` panel (that shows the live app's in-memory state). Use
  `journalctl -u goldfinger-bom-refresh` and the `refreshed_at` timestamps instead.
