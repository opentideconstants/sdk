# OpenTideConstants for Swift

Find stations inside inclusive latitude and longitude bounds with `bbox` on
`OpenTideConstants` or a held `Release`. Results use station-ID order and the
existing discovery filters. Apply `limit` after filtering; omit it for all matches.
Flagged and fallback stations remain excluded unless explicitly included.

```swift
let boston = try client.bbox(
    south: 42.2, west: -71.2, north: 42.5, east: -70.7, limit: 3
)
let pacific = try client.release.bbox(
    south: -25, west: 170, north: -10, east: -170
)
```

When `west > east`, the box crosses the date line. Bounds must be finite,
latitudes within -90...90, longitudes within -180...180, and `south <= north`.
A supplied limit must be positive. Invalid bounds or limits throw `invalid_argument`.

Prediction calls accept a final, optional `units` argument on both `Station` and
station ID overloads, through `Release` or `OpenTideConstants`:

- `heights`, `heightsAt`, and `extremes`: `"meters"` (default) or `"feet"`.
- `currents` and `currentEvents`: `"m/s"` (default) or `"knots"`.

Height points and extremes expose `height`. Current points expose
`velocityMajor`, `velocityMinor`, and `speed`; current events expose `velocity`.
Each item and containing result has a read-only `units` label for these values.

Existing `heightM`, `velocityMajorMs`, `velocityMinorMs`, `speedMs`, and
`velocityMs` fields always retain SI values. Datum uncertainty stays in meters.
Feet use the final height divided by `0.3048`; knots use the final current value
divided by `1852.0 / 3600.0`. Conversion leaves event times, directions, datum
shifts, and model selection unchanged. `toLocal()` preserves units and values.
Unsupported selectors throw `invalid_argument`.

```swift
let series = try client.heights(
    stationId: stationId, start: start, stop: stop, units: "feet"
)
for point in series.items {
    print(point.height, point.units, point.heightM)
}
```

Existing calls and result constructors remain valid with their SI defaults.
