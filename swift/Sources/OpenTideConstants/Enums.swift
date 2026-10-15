import Foundation

public enum Kind: String, Codable, Sendable, CaseIterable {
    case `tide` = "tide"
    case `current` = "current"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum StationType: String, Codable, Sendable, CaseIterable {
    case `reference` = "reference"
    case `subordinate` = "subordinate"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum StationStatus: String, Codable, Sendable, CaseIterable {
    case `active` = "active"
    case `removed` = "removed"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum RemovedReason: String, Codable, Sendable, CaseIterable {
    case `merged` = "merged"
    case `duplicate` = "duplicate"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum SourceType: String, Codable, Sendable, CaseIterable {
    case `official` = "official"
    case `gauge` = "gauge"
    case `model` = "model"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum Quantity: String, Codable, Sendable, CaseIterable {
    case `waterLevel` = "water_level"
    case `current` = "current"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum QcStatus: String, Codable, Sendable, CaseIterable {
    case `ok` = "ok"
    case `flagged` = "flagged"
    case `noConstants` = "no_constants"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum LoadedFrom: String, Codable, Sendable, CaseIterable {
    case `download` = "download"
    case `cache` = "cache"
    case `cacheAfterError` = "cache_after_error"
    case `file` = "file"
    case `fileUnverified` = "file_unverified"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum PhaseReference: String, Codable, Sendable, CaseIterable {
    case `greenwichUtc` = "greenwich_utc"
    case `local` = "local"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum NodalHandling: String, Codable, Sendable, CaseIterable {
    case `fUAtPrediction` = "f_u_at_prediction"
    case `none` = "none"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum CanaryStatus: String, Codable, Sendable, CaseIterable {
    case `pass` = "pass"
    case `fail` = "fail"
    case `notApplicable` = "not_applicable"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum HeightAdjustedType: String, Codable, Sendable, CaseIterable {
    case `r` = "R"
    case `a` = "A"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum DroppedReason: String, Codable, Sendable, CaseIterable {
    case `rayleigh` = "rayleigh"
    case `noise` = "noise"
    case `longPeriodRule` = "long_period_rule"
    case `nonTidalRule` = "non_tidal_rule"
    case `convention` = "convention"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum QcFlagName: String, Codable, Sendable, CaseIterable {
    case `timeBase` = "time_base"
    case `brokenRecord` = "broken_record"
    case `microtidal` = "microtidal"
    case `nonTidalSignal` = "non_tidal_signal"
    case `shortRecord` = "short_record"
    case `siblingDisagreement` = "sibling_disagreement"
    case `carriedOver` = "carried_over"
    case `fallbackTimeBaseDisputed` = "fallback:time_base_disputed"
    case `fallbackTimeBaseUnresolved` = "fallback:time_base_unresolved"
    case `fallbackRefusedFit` = "fallback:refused_fit"
    case `fallbackShortRecordUncalibrated` = "fallback:short_record_uncalibrated"
    case `fallbackShortRecordLongPeriod` = "fallback:short_record_long_period"
    case `fallbackPublishedFullList` = "fallback:published_full_list"
    case `fallbackReliabilityWithheld` = "fallback:reliability_withheld"
    case `fallbackLicenceReading` = "fallback:licence_reading"
    case `fallbackDatumGateFailed` = "fallback:datum_gate_failed"
    case `fallbackNotInOtcInput` = "fallback:not_in_otc_input"
    case `fallbackHistoricalOffsets` = "fallback:historical_offsets"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum TimeBaseCode: String, Codable, Sendable, CaseIterable {
    case `verified` = "verified"
    case `corrected` = "corrected"
    case `unverified` = "unverified"
    case `disputed` = "disputed"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum DecisionTier: String, Codable, Sendable, CaseIterable {
    case `rule` = "rule"
    case `review` = "review"
    case `fallback` = "fallback"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum DecisionOutcome: String, Codable, Sendable, CaseIterable {
    case `accept` = "accept"
    case `fallback` = "fallback"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum AliasSystem: String, Codable, Sendable, CaseIterable {
    case `noaa` = "noaa"
    case `gesla` = "gesla"
    case `ticon` = "ticon"
    case `xtide` = "xtide"
    case `kartverket` = "kartverket"
    case `slackwater` = "slackwater"
    case `webcaltides` = "webcaltides"
    case `linz` = "linz"
    case `shom` = "shom"
    case `pegelonline` = "pegelonline"
    case `rws` = "rws"
    case `mi` = "mi"
    case `dmi` = "dmi"
    case `smhi` = "smhi"
    case `fmi` = "fmi"
    case `uhslc` = "uhslc"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum Mode: String, Codable, Sendable, CaseIterable {
    case `eager` = "eager"
    case `stream` = "stream"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum OnNetworkError: String, Codable, Sendable, CaseIterable {
    case `useCache` = "use_cache"
    case `raise` = "raise"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum Format: String, Codable, Sendable, CaseIterable {
    case `json` = "json"
    case `jsonGz` = "json.gz"
    case `jsonl` = "jsonl"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum Match: String, Codable, Sendable, CaseIterable {
    case `exact` = "exact"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum ExtremeType: String, Codable, Sendable, CaseIterable {
    case `high` = "high"
    case `low` = "low"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum CurrentEventType: String, Codable, Sendable, CaseIterable {
    case `maxFlood` = "max_flood"
    case `maxEbb` = "max_ebb"
    case `slackBeforeFlood` = "slack_before_flood"
    case `slackBeforeEbb` = "slack_before_ebb"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum PredictionMethod: String, Codable, Sendable, CaseIterable {
    case `harmonic` = "harmonic"
    case `foldedOffsets` = "folded_offsets"
    case `offsets` = "offsets"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum FallbackReason: String, Codable, Sendable, CaseIterable {
    case `timeBaseDisputed` = "time_base_disputed"
    case `timeBaseUnresolved` = "time_base_unresolved"
    case `refusedFit` = "refused_fit"
    case `shortRecordUncalibrated` = "short_record_uncalibrated"
    case `shortRecordLongPeriod` = "short_record_long_period"
    case `publishedFullList` = "published_full_list"
    case `reliabilityWithheld` = "reliability_withheld"
    case `licenceReading` = "licence_reading"
    case `datumGateFailed` = "datum_gate_failed"
    case `notInOtcInput` = "not_in_otc_input"
    case `historicalOffsets` = "historical_offsets"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum SourceRole: String, Codable, Sendable, CaseIterable {
    case `gaugeStation` = "gauge_station"
    case `publishedHarmonicRecord` = "published_harmonic_record"
    case `model` = "model"
    case `reference` = "reference"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

public enum SourceDisposition: String, Codable, Sendable, CaseIterable {
    case `metadataOnly` = "metadata_only"
    case `notFitted` = "not_fitted"
    case `licenceRestricted` = "licence_restricted"
    case `unavailable` = "unavailable"
    case `retained` = "retained"
    case `other` = "other"
    internal init(value: JSONValue) { self = Self(rawValue: value.string ?? "") ?? .other }
}

