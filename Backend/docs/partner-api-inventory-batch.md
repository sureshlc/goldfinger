# Goldfinger API — Batch Inventory (`POST /inventory/batch`)

Partner-facing reference for the **batched inventory** endpoint. Use this instead of calling the
per-SKU inventory endpoint in a loop.

## Why use it

Fetching inventory one SKU at a time (`GET /inventory/{sku}`) means one HTTP request **per SKU**
— e.g. ~108 requests to sync one customer's ordered items. The batch endpoint takes **all SKUs in
a single request** and resolves them internally in one query, so a 108-SKU sync becomes **1 call**.

Availability is computed identically to the single endpoint (`available = on_hand − committed`,
floored at 0), so results are byte-for-byte the same — just fetched in bulk.

## Endpoint

```
POST /api/v1/inventory/batch
```

### Auth

Same as every other Goldfinger endpoint — send your API key:

```
X-API-Key: <your-api-key>
```

(A JWT `Authorization: Bearer <token>` also works, but partners should use the API key.)

### Request body

```jsonc
{
  "skus": ["QW1564063", "SBUX9080", "STIR901"],  // required, 1..500 per call
  "location_name": null                           // optional; null = all locations
}
```

- `skus` — up to **500 per call**. Duplicates and surrounding whitespace are ignored.
- `location_name` — optional. When set, inventory is filtered to that location; when `null`/omitted,
  quantities are summed across all locations.

> Sending more than 500 SKUs returns `400`. If a customer ever exceeds 500, chunk client-side
> (e.g. 200–500 per call) and merge the `items` arrays.

### Response `200`

```jsonc
{
  "items": [
    {
      "sku": "QW1564063",
      "found": true,
      "item_id": "6170",
      "item_name": "7.75\" PHA Jumbo Natural Unwrapped Straw 4/500 Pack Size",
      "available_quantity": 252.0,
      "on_hand": 252.0,
      "committed": 0.0
    },
    {
      "sku": "SBUX9080",
      "found": true,
      "item_id": "5754",
      "item_name": "...",
      "available_quantity": 8918.0,
      "on_hand": 17444.0,
      "committed": 8526.0
    },
    {
      "sku": "NOTAREAL999",
      "found": false
    }
  ],
  "count": 3,
  "not_found": ["NOTAREAL999"]
}
```

### Field semantics

| Field | Meaning |
|---|---|
| `sku` | Echo of the SKU you sent (order preserved; deduped) |
| `found` | `true` if the SKU resolved to an item, `false` if unknown to NetSuite |
| `item_id` | NetSuite internal id (present when `found`) |
| `item_name` | Item display name (present when `found`) |
| `available_quantity` | `sum(on_hand − committed)`, floored at 0 |
| `on_hand` | Total on-hand |
| `committed` | Total committed |
| `count` | Number of entries in `items` (after dedup) |
| `not_found` | SKUs that didn't resolve (also present as `found: false` entries) |

Two "empty" cases to handle:
- **Unknown SKU** → `found: false`, no quantities. Also listed in `not_found`.
- **Known SKU with no stock** → `found: true` with `available_quantity`/`on_hand`/`committed` = `0`.

## Examples

### curl

```bash
curl -s -X POST https://<goldfinger-host>/api/v1/inventory/batch \
  -H "X-API-Key: $GOLDFINGER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"skus":["QW1564063","SBUX9080","STIR901"]}'
```

### Migration from the per-SKU loop

Before — one request per SKU (chunked concurrency):
```js
// ~108 requests
const results = await mapChunked(skus, 5, sku =>
  fetchGoldfingerInventory(sku)   // GET /inventory/{sku}
);
```

After — one request (chunk only if >500):
```js
async function fetchGoldfingerInventoryBatch(skus) {
  const out = [];
  for (let i = 0; i < skus.length; i += 500) {
    const res = await fetch(`${BASE}/api/v1/inventory/batch`, {
      method: "POST",
      headers: { "X-API-Key": KEY, "Content-Type": "application/json" },
      body: JSON.stringify({ skus: skus.slice(i, i + 500) }),
    });
    const { items } = await res.json();
    out.push(...items);
  }
  return out;   // [{ sku, found, available_quantity, on_hand, committed, ... }]
}
```

## Errors

| Status | When |
|---|---|
| `400` | More than 500 SKUs, or a SKU / `location_name` contains invalid characters |
| `401` | Missing or invalid API key |
| `500` | Unexpected server error |

## Notes / guarantees

- **Same numbers as the single endpoint.** The batch uses the same availability logic; there is no
  separate calculation to drift.
- **Order & dedup.** `items` preserves your input order after removing duplicates/whitespace.
- **Internally chunked.** Goldfinger splits the resolved ids into ≤200-per-query slices to NetSuite,
  so large batches stay well under NetSuite's page limits — transparent to you.
- **Inventory is live**, not cached long — you get current NetSuite quantities each call.
- **Related:** raw-material feasibility already has a batch endpoint,
  `POST /api/v1/production/batch-feasibility` (up to 50 items/call).
