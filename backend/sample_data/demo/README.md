# Demo data

Real AEMET data served by demo mode (`DEMO_MODE=true`), so that the whole application runs without an AEMET API
key.

| File | Station | Content |
|---|---|---|
| `89064_2025-03.json` | Juan Carlos I | March 2025 (UTC), 4,464 ten-minute records |
| `89070_2025-03.json` | Gabriel de Castilla | March 2025 (UTC), 4,464 ten-minute records |

March 2025 includes the Madrid spring DST change of 2025-03-30, and both stations have complete data around it.

## How the files were produced

Recorded on 2026-11-15 with [`scripts/record_demo_data.py`](../../scripts/record_demo_data.py), which fetches
the data through the application's own AEMET client and keeps only the fields the application uses:
`identificacion`, `nombre`, `fhora`, `temp`, `pres`, `vel`, `qdato`, `velx`, `tmn` and `tmx`. Values are not
modified: the demo source parses these files with the same parser and cleaning rule as live responses (for
example, Juan Carlos I has 10 records with every value set to `"NaN"`, which are discarded when parsed).

To record another month with your own API key, from the `backend` folder:

```bash
uv run --env-file .env python -m scripts.record_demo_data --month 2025-02
```

## Attribution

© AEMET. Autorizado el uso de la información y su reproducción citando a AEMET como autora de la misma.
See AEMET's [legal notice](https://www.aemet.es/es/nota_legal).
