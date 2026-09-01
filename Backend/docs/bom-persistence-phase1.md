# BOM DB Persistence — Phase 1 Design (schema + read-through)

Status: **Draft** · Owner: platform · Scope: Phase 1 only (schema + lazy read-through). Phases 2–3 outlined at the end.

## 1. Problem

Every feasibility / BOM query resolves the **full multi-level BOM from NetSuite** on demand:
per-level SuiteQL (legacy) or REST record calls (native), plus a `resolve_sku_or_id` per component
(which itself verifies against NetSuite). This is the bulk of our NetSuite API consumption.

Key insight: **BOMs (formulas) change rarely and in controlled ways; inventory changes constantly.**
So BOMs are an ideal candidate for a persistent cache; inventory is not.

## 2. Goal

Persist BOM "formulas" in Postgres as a **read-through cache**, lazily populated on first query and
refreshed **weekly + on-demand (admin)**. A cached feasibility becomes:

> **DB formula (free) + live inventory (one batched query)**

eliminating the per-request BOM-resolution and per-component-resolution NetSuite calls.

## 3. Scope

- **Phase 1 (this doc):** schema + read-through lazy-populate + expose formula freshness.
- **Phase 2:** admin refresh endpoint + manual "Refresh formulas" button.
- **Phase 3:** weekly cron (Saturday morning), paced.

**Inventory stays LIVE** — never persisted in the weekly refresh (5-min cache stays as-is).

## 4. What we cache vs keep live

| Data | Source after Phase 1 | Why |
|---|---|---|
| BOM formula (components, qty, unit, `is_phantom`, `is_manufacturing`, revision) | **DB** (weekly + manual refresh) | Stable, expensive to fetch |
| Component inventory (leaf on-hand) | **Live NetSuite** (short cache) | Volatile |
| Item search / id↔sku | existing `items` table + NetSuite fallback | Already local |

## 5. Schema — normalized per-assembly

Store each assembly's **direct** BOM once (not exploded trees), and reconstruct the multi-level tree
by recursing over the tables **in the DB** (all local, no NetSuite). A shared sub-assembly's formula
lives in exactly one row, so a single formula change refreshes one item.

```sql
-- one row per assembly item that has a resolved formula
bom_formula (
  assembly_item_id   BIGINT       PRIMARY KEY,   -- NetSuite internal id (matches items.id)
  revision_id        VARCHAR(64)  NULL,           -- current bomRevision id (native) / null (legacy)
  source             VARCHAR(16)  NOT NULL,       -- 'legacy' | 'native'
  is_manufacturing   BOOLEAN      NOT NULL,       -- false => no BOM (negative cache)
  refreshed_at       TIMESTAMPTZ  NOT NULL,
  last_error         VARCHAR(512) NULL
)

-- direct children of an assembly (its recipe, one level)
bom_component (
  id                 BIGSERIAL    PRIMARY KEY,
  assembly_item_id   BIGINT       NOT NULL REFERENCES bom_formula(assembly_item_id) ON DELETE CASCADE,
  component_item_id  BIGINT       NOT NULL,
  component_sku      VARCHAR(255) NOT NULL,
  component_name     VARCHAR(512) NULL,
  quantity           NUMERIC      NOT NULL,
  unit               VARCHAR(32)  NULL,
  is_phantom         BOOLEAN      NOT NULL DEFAULT false,
  is_manufacturing   BOOLEAN      NOT NULL DEFAULT false,
  ordinal            INTEGER      NOT NULL DEFAULT 0
)
CREATE INDEX ix_bom_component_assembly ON bom_component (assembly_item_id);
```

- Store the **full** formula including `is_phantom` — feasibility still runs on the full tree; we
  collapse for display as we do today. Nothing about the collapse/limiting/material-summary logic
  changes; it just reads the same component dicts, now sourced from the DB.
- Added via an Alembic migration alongside the existing `items` table.

## 6. Read-through (where it hooks in)

The read-through lives in **`bom_service.get_item_bom(item_id)`** (per-assembly direct BOM), NOT in
`get_full_bom`. `get_full_bom` keeps its current recursion — each level's `get_item_bom` is simply
DB-backed now, so the whole tree reconstructs from the DB on a warm cache.

Lookup order: **in-memory cache (L1) → DB (L2) → NetSuite (L3, write-back).**

```
get_item_bom(item_id):
  row = bom_formula[item_id]
  if row exists:                       # L2 hit — no NetSuite
      return components from bom_component[item_id]   # mapped to the current dict shape
  # L3 miss:
  components = <existing legacy-first / native resolution>   # NetSuite
  upsert bom_formula(item_id, revision_id, source, is_manufacturing, refreshed_at=now)
  replace bom_component[item_id] = components
  return components
```

- **Negative cache:** non-manufacturing / no-BOM items get a `bom_formula` row with
  `is_manufacturing=false` and zero components, so we don't re-hit NetSuite for them.
- **Sub-assemblies populate naturally:** as `get_full_bom` recurses, each visited sub-assembly's
  `get_item_bom` writes its own rows — the normalized store fills in over time.
- **Component dict shape is unchanged**, so `get_full_bom`, the phantom-collapse, `limiting_component`
  remap, `material_summary`, and shortage drilling all keep working untouched.

## 7. Freshness model

- The DB is **authoritative** between refreshes (weekly + manual). No per-read TTL by default.
- **Safety fallback:** if `refreshed_at` is older than `BOM_MAX_AGE` (e.g. 14 days) → treat as a miss
  and re-fetch on read. Guards against a skipped cron.

## 8. Formula freshness — admin-only (decision)

Do **NOT** surface freshness in the user-facing API or UI. The only place it appears is the
**admin items listing**, as a "Formula as of" column:
- Source value is `bom_formula.refreshed_at`, joined into the admin `GET /admin/items` response
  on `items.id = bom_formula.assembly_item_id` (shown as `formula_refreshed_at`).
- Stored in `bom_formula` (keyed by item id), NOT on the `items` table — the `items.sku` unique
  index can't hold duplicate-SKU items (e.g. CK42011's Assembly + InvtPart), so keying formula
  metadata by item id avoids that trap. Displayed as a column in admin regardless.
- No `formula_as_of` anywhere in `/feasibility`, `/item`, or the customer UI.

## 9. Invalidation

- Extend the existing `invalidate_item_cache(item_id)` to also delete (or mark stale) the
  `bom_formula` + `bom_component` rows for that item, in addition to the in-memory caches.
- An admin item/formula edit invalidates that item so the next query re-populates.

## 10. Cron (Phase 3) — job runner choice

**DECIDED & SHIPPED:** none of the HTTP options — a **standalone systemd timer** running the
job in-process (`app/scripts/refresh_boms.py`) directly against DB+NetSuite. This drops the auth
surface entirely (API keys are `role='service'` and can't reach the admin endpoint; we didn't want
to weaken that). Cross-process safety vs. a manual admin run is handled by a Postgres advisory lock
(`BOM_REFRESH_LOCK_KEY`) inside `refresh_all_bom_formulas()`. See `deploy/systemd/README.md`.
L1 (1h TTL) trails the freshly-written L2 by ≤1h on its own, exactly as it already does hourly.

Original options considered for the Saturday-morning refresh (pg-boss is Node/Postgres and can't
run in-process in this Python/FastAPI backend):

| Option | Notes |
|---|---|
| **(a) OS crontab → `POST /admin/refresh-boms`** | Simplest, visible, survives PM2 restarts. **Recommended.** |
| **(b) APScheduler (in-app, Postgres jobstore)** | In-process; one more dependency; scheduler dies if the app is down. |
| **(c) `procrastinate`** | Postgres-backed async task queue for Python — the closest analog to pg-boss. |
| pg-boss in the Node MES app → calls our admin endpoint | Only if you want it there; couples two services. |

Refresh must be **paced** (respect NetSuite rate limits; Saturday AM is low-traffic). The refresh set =
**all assemblies currently in `bom_formula`** (the cache that grew organically from user queries) —
we do **not** pull all 993 BOMs upfront.

## 11. Rollout / risk

- **Additive & low-risk:** new tables + read-through; the NetSuite path stays as the fallback, so a
  cold/missing/errored DB row degrades gracefully to today's behavior.
- Optional **feature flag** `USE_BOM_DB` for a safe staged rollout.
- **No API response-shape change** except the additive `formula_as_of`.
- The savings are realized progressively: first query of an item still hits NetSuite (and populates);
  every subsequent query (and the whole tree) is served from the DB until the next refresh.

## 12. Open decisions

1. `BOM_MAX_AGE` safety re-fetch — enable? value (e.g. 14d)?
2. Cron mechanism — (a) crontab→endpoint (recommended) / (b) APScheduler / (c) procrastinate.
3. `formula_as_of` — feasibility response, item-details, or both.
4. Feature flag for rollout — yes/no.

## 13. Phase 1 deliverables

- Alembic migration: `bom_formula`, `bom_component` (+ index).
- SQLAlchemy models.
- Read-through + write-back in `bom_service.get_item_bom` (with negative caching).
- `formula_as_of` surfaced in the API + UI caption.
- Extend `invalidate_item_cache` to clear DB rows.
