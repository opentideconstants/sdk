# Prediction reference vectors

The `1.0` bundle contains 60 Tier A vectors for 14 stations.
It contains 13 real NOAA stations and one labelled synthetic Boston station.
The synthetic station includes MA2 and MB2.

The vectors come from the independent strict engine.
The input release uses OTC's own `otc-tcd-20251228-ma2mb2` table.
The bundle retains the original vectors, input release, source provenance, and SHA-256 checksums.
The source commit is `7fb382e946155fc2097c6c5a570627e8bd4a3199`.

## Check the bundle

Run these commands from the repository root:

```sh
uv run conformance/tools/run_vectors.py --check
uv run conformance/tools/run_vectors.py \
  --runner "uv run conformance/runners/python/runner.py" \
  --report vectors-python.json
```

The consumer checks the checksum manifest before it reads the expectations.
It also checks the exact vector count, station coverage, input hash, source provenance, and scientific checks.
A changed byte causes exit status 2.

The consumer opens an authenticated copy named `OTC_<datestamp>.json` with its checksum sidecar.
It sends the original vector arguments through the existing runner protocol.
It checks every vector, in its original order.

## Comparison rules

Metadata, item keys, counts, event order, and event types must match exactly.
Event times must use whole-second UTC timestamps and differ by at most one second.
Series sample times must match exactly.

| Quantity | Maximum difference |
| --- | --- |
| Height | `1e-5` m |
| Current components, speed, and event velocity | `1e-5` m/s |
| Current direction at speed ≥ `0.01` m/s | `0.01` degrees, using the shortest circular difference |

Numeric directions must remain in `[0,360)`.
Null directions, including slack-event directions, must remain null.
Local-time fields remain null because these vectors use UTC.
These rules implement prediction specification §6.1.
They do not change the separate prediction-case tolerances.

## Pending ports and acceptance

`1.0/expected-failures.json` names the prediction ports that remain pending.
A missing prediction feature produces XFAIL for a listed port.
A successful listed port produces XPASS and exit status 1.
Release-reader failures and protocol faults do not become XFAIL.

For an unfiltered RED check, add `--no-expected-failures`.
The null runner must produce 60 FAIL results and no PASS results.

Before accepting a port, remove only that port's pending entries.
Require all 60 vectors to pass against the real SDK.
Require SDK mutations 1–7 and 8a to fail against these vectors.
Other ports remain pending until their own acceptance checks finish.

Exit status 0 permits PASS or declared XFAIL results.
Exit status 1 reports FAIL or XPASS results.
Exit status 2 reports invalid input, configuration, or runner protocol failures.
An XFAIL result does not prove prediction accuracy.

The input release passes the current SDK's format-1.0 schema.
When the schema pin changes, check this release against the new schema before acceptance.
Keep the original producer hashes intact; a schema pin update is a separate change.
