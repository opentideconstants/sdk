# OpenTideConstants for Swift

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
