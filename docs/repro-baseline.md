# Unguarded flinch baseline

Recorded 20 Sep 2026. No DELETE was sent (`execute: false`).

- **local-test (6333):** `decor_catalog` size **768**, 0 points (seeded broken).
- **shared-dev (6335):** `decor_catalog` size **384**, 69 points (untouched).

Dry-run of `python scripts/repro_flinch_baseline.py`:

```json
{
  "at": "2026-09-21T03:33:19.661066+00:00",
  "execute": false,
  "intended_target": "local-test",
  "actual_environment": "shared-dev-tunnel",
  "actual_url": "http://localhost:6334",
  "sensitivity": "shared",
  "collection": "decor_catalog",
  "phase_a": "GET /collections/{name} on the port we just used",
  "phase_b": "DELETE /collections/{name} on that same port",
  "would_destroy_shared": true
}
```

Unguarded path: intended `local-test`, actual port **6334** (`shared-dev-tunnel`). A live `--execute` would wipe shared-dev. This baseline does not do that.

Do not pass `--execute` until a later layer is supposed to catch it, and only if you will re-ingest `shared-dev` afterward.
