# ADR-0016: Wind-energy metrics

- **Status**: Accepted
- **Date**: 2026-11-16

## Context

The mean speed of a bucket says little about the energy in the wind, because the power of the wind grows with the
cube of its speed: speeds of 0 and 10 m/s average 5 m/s, yet the mean of their cubes, (0 + 1000) / 2 = 500, is four
times 5³ = 125. Half the time at 10 m/s carries four times the power of a steady 5 m/s. Analysing a site for wind
energy needs statistics that respect that, plus the air density, which scales the power and depends on temperature
and pressure.

The cache stores, per ten-minute observation, the mean temperature, pressure and speed. AEMET also publishes the
maximum speed within each ten minutes (`velx`, a gust) and the minimum and maximum temperature (`tmn`, `tmx`), which
the cache does not store. The stations measure wind at about 10 m, while turbine hubs stand at 80 to 120 m.

## Options considered

**Source of the maximum speed and the temperature extremes**

1. **The stored ten-minute means**: the highest ten-minute mean speed (the statistic that wind standards use, such
   as the IEC reference speed, a ten-minute mean) and the lowest and highest ten-minute mean temperatures. No change
   to the cache.
2. **AEMET's in-interval values** (`velx`, `tmn`, `tmx`): real gusts, which matter for turbine loads and cut-out,
   and absolute extremes. A second schema version (the cache rebuilds itself on a version change), and changes to
   the parser, `Observation`, the repository and every test fake.

**Shape of the API**

1. **An optional `metrics=extended` parameter**, for aggregated levels only; each metric appears when the
   measurement types it needs are requested. The default output does not change.
2. **Always return every metric**: the cache holds the three measurements anyway, but an absent key would no longer
   mean "not requested".
3. **A 422 when a metric's inputs are missing**: stricter, and clients would have to know what each metric needs.

**Raw ten-minute records with `metrics=extended`**: reject them (a bucket statistic of one value repeats it), or
compute per-record densities.

## Decision

- **Option 1 for the source**: the metrics come from the stored ten-minute means, and the labels say so
  (`Maximum 10-minute speed (m/s)`). Storing `velx`, `tmn` and `tmx` is the next step if gusts are needed.
- **Option 1 for the API**: `metrics=extended` on hourly, daily and monthly levels; a 422 on raw records. Each metric
  is returned when its inputs are among the requested `types`, with its label and unit in `fields`, so the CSV export
  and the front-end table show it without any change.
- **Metrics**, as pure functions in `app/domain/wind.py`:

  | Key | Label | Computation over the bucket |
  |---|---|---|
  | `speed_cubic_mean_ms` | Cubic mean speed (m/s) | ∛(mean of v³) |
  | `speed_max_ms` | Maximum 10-minute speed (m/s) | highest ten-minute mean speed |
  | `temperature_min_c`, `temperature_max_c` | Minimum / Maximum 10-minute temperature (°C) | lowest / highest ten-minute mean |
  | `air_density_kgm3` | Air density (kg/m³) | mean of ρ = p / (R·T) per observation, dry air, R = 287.05 J/(kg·K) |
  | `power_density_wm2` | Wind power density (W/m²) | mean of ½·ρ·v³ per observation with speed, temperature and pressure |

- **Air density and power density are computed per observation, then averaged**: ½·ρ·v³ of the mean speed would
  underestimate the power (2.6 times below the real value in the recorded month of March 2025 at Juan Carlos I).
- **Dry air**: humidity is ignored. Even saturated air at 0 °C and 980 hPa is only about 0.24 % lighter (vapour
  pressure 6.11 hPa; ρ_moist / ρ_dry ≈ 1 − 0.378·e/p), and Antarctic air is drier.
- **Rounding**: two decimals for speeds and temperatures, three for air density (about 1.25 kg/m³), one for power
  density.
- **No height extrapolation**: the metrics describe the site at sensor height. Extrapolating to hub height needs a
  wind shear model (power law or log law) and its parameters, which these data do not provide.

## Consequences

- The default response is unchanged; existing clients see no difference.
- Maximum speed is not a gust: a site's turbine loads cannot be judged from it. The README says so.
- Power density is the power of the wind itself, not of a turbine: converting it into energy produced needs a
  turbine's power curve.
- Power density uses only observations with all three measurements, so it can rest on fewer samples than the means
  of the same bucket.
- Adding a metric is a new entry in `METRIC_FIELDS` and a case in the aggregation; the API, the CSV and the
  front-end table pick it up from `fields`.
