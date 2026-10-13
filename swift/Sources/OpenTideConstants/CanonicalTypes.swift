import Foundation

// Internal construction only. Public methods retain their original bodies.
// JSONValue appears only in approved source/raw JSON domains.

internal enum CanonicalMemberID: String, CaseIterable {
    case ClientOpen = "Client.open"
    case ClientRelease = "Client.release"
    case ClientLoadedFrom = "Client.loaded_from"
    case ClientLastError = "Client.last_error"
    case ClientReleases = "Client.releases"
    case ClientLatest = "Client.latest"
    case ClientCheckForUpdate = "Client.check_for_update"
    case ClientNewerFormatMajor = "Client.newer_format_major"
    case ClientUpdate = "Client.update"
    case ClientDownload = "Client.download"
    case ClientVerify = "Client.verify"
    case ClientCachedReleases = "Client.cached_releases"
    case ClientPrune = "Client.prune"
    case ClientClose = "Client.close"
    case ReleaseDatestamp = "Release.datestamp"
    case ReleaseCreated = "Release.created"
    case ReleaseFormatVersion = "Release.format_version"
    case ReleaseZenodoVersionDoi = "Release.zenodo_version_doi"
    case ReleaseConceptDoi = "Release.concept_doi"
    case ReleaseSourceVersions = "Release.source_versions"
    case ReleaseBuildCommit = "Release.build_commit"
    case ReleaseChangelogUrl = "Release.changelog_url"
    case ReleaseFiles = "Release.files"
    case ReleaseConventions = "Release.conventions"
    case ReleaseConvention = "Release.convention"
    case ReleaseLicences = "Release.licences"
    case ReleaseLicence = "Release.licence"
    case ReleaseConstituentNames = "Release.constituent_names"
    case ReleaseStats = "Release.stats"
    case ReleaseStationCount = "Release.station_count"
    case ReleaseTombstoneCount = "Release.tombstone_count"
    case ReleaseCitation = "Release.citation"
    case ReleaseStation = "Release.station"
    case ReleaseRequireStation = "Release.require_station"
    case ReleaseTombstone = "Release.tombstone"
    case ReleaseStationByAlias = "Release.station_by_alias"
    case ReleaseStations = "Release.stations"
    case ReleaseIterStations = "Release.iter_stations"
    case ReleaseSearch = "Release.search"
    case ReleaseNear = "Release.near"
    case ReleaseNearest = "Release.nearest"
    case ReleaseReferenceStation = "Release.reference_station"
    case ReleaseSubordinatesOf = "Release.subordinates_of"
    case ReleaseAttribution = "Release.attribution"
    case ReleaseHeights = "Release.heights"
    case ReleaseHeightsAt = "Release.heights_at"
    case ReleaseExtremes = "Release.extremes"
    case ReleaseCurrents = "Release.currents"
    case ReleaseCurrentEvents = "Release.current_events"
    case ReleaseDatums = "Release.datums"
    case ReleaseRanges = "Release.ranges"
    case ReleaseAstroTable = "Release.astro_table"
    case ReleaseHistoricalOffsetsPolicy = "Release.historical_offsets_policy"
    case ReleaseInfoDatestamp = "ReleaseInfo.datestamp"
    case ReleaseInfoFormatVersion = "ReleaseInfo.format_version"
    case ReleaseInfoConceptDoi = "ReleaseInfo.concept_doi"
    case ReleaseInfoZenodoVersionDoi = "ReleaseInfo.zenodo_version_doi"
    case ReleaseInfoContentSha256 = "ReleaseInfo.content_sha256"
    case ReleaseInfoFiles = "ReleaseInfo.files"
    case FileInfoName = "FileInfo.name"
    case FileInfoUrl = "FileInfo.url"
    case FileInfoSize = "FileInfo.size"
    case FileInfoSha256 = "FileInfo.sha256"
    case StationStationId = "Station.station_id"
    case StationName = "Station.name"
    case StationCountry = "Station.country"
    case StationLat = "Station.lat"
    case StationLon = "Station.lon"
    case StationType = "Station.type"
    case StationKind = "Station.kind"
    case StationTimezone = "Station.timezone"
    case StationAliases = "Station.aliases"
    case StationStatus = "Station.status"
    case StationIsReference = "Station.is_reference"
    case StationIsSubordinate = "Station.is_subordinate"
    case StationIsTide = "Station.is_tide"
    case StationIsCurrent = "Station.is_current"
    case StationRecommendedSet = "Station.recommended_set"
    case StationConstantSets = "Station.constant_sets"
    case StationConstantSet = "Station.constant_set"
    case StationSubordinateOffsets = "Station.subordinate_offsets"
    case StationValidation = "Station.validation"
    case StationRaw = "Station.raw"
    case StationRecommendedIsFallback = "Station.recommended_is_fallback"
    case StationSourceRecords = "Station.source_records"
    case TombstoneStationId = "Tombstone.station_id"
    case TombstoneName = "Tombstone.name"
    case TombstoneStatus = "Tombstone.status"
    case TombstoneRemovedIn = "Tombstone.removed_in"
    case TombstoneRemovedReason = "Tombstone.removed_reason"
    case TombstoneMergedInto = "Tombstone.merged_into"
    case TombstoneDetail = "Tombstone.detail"
    case TombstoneRaw = "Tombstone.raw"
    case ConstantSetSetId = "ConstantSet.set_id"
    case ConstantSetSource = "ConstantSet.source"
    case ConstantSetSourceType = "ConstantSet.source_type"
    case ConstantSetQuantity = "ConstantSet.quantity"
    case ConstantSetSourceRecordId = "ConstantSet.source_record_id"
    case ConstantSetSourceVersion = "ConstantSet.source_version"
    case ConstantSetRecordSpan = "ConstantSet.record_span"
    case ConstantSetDatum = "ConstantSet.datum"
    case ConstantSetQcStatus = "ConstantSet.qc_status"
    case ConstantSetQcFlags = "ConstantSet.qc_flags"
    case ConstantSetDroppedConstituents = "ConstantSet.dropped_constituents"
    case ConstantSetTimeBase = "ConstantSet.time_base"
    case ConstantSetIsRecommended = "ConstantSet.is_recommended"
    case ConstantSetConvention = "ConstantSet.convention"
    case ConstantSetLicence = "ConstantSet.licence"
    case ConstantSetProvenance = "ConstantSet.provenance"
    case ConstantSetValidation = "ConstantSet.validation"
    case ConstantSetConstituents = "ConstantSet.constituents"
    case ConstantSetConstituent = "ConstantSet.constituent"
    case ConstantSetRaw = "ConstantSet.raw"
    case ConstantSetFallback = "ConstantSet.fallback"
    case ConstituentName = "Constituent.name"
    case ConstituentSourceName = "Constituent.source_name"
    case ConstituentDoodson = "Constituent.doodson"
    case ConstituentSpeedDegPerHour = "Constituent.speed_deg_per_hour"
    case ConstituentAmplitudeM = "Constituent.amplitude_m"
    case ConstituentPhaseDeg = "Constituent.phase_deg"
    case ConstituentAmpUncertaintyM = "Constituent.amp_uncertainty_m"
    case ConstituentPhaseUncertaintyDeg = "Constituent.phase_uncertainty_deg"
    case ConstituentKeptReason = "Constituent.kept_reason"
    case ConstituentRaw = "Constituent.raw"
    case ConventionConventionId = "Convention.convention_id"
    case ConventionPhaseReference = "Convention.phase_reference"
    case ConventionUtcOffsetHours = "Convention.utc_offset_hours"
    case ConventionV0Model = "Convention.v0_model"
    case ConventionNodalHandling = "Convention.nodal_handling"
    case ConventionNodalFormulaIds = "Convention.nodal_formula_ids"
    case ConventionConstituentTableVersion = "Convention.constituent_table_version"
    case ConventionTablesSha256 = "Convention.tables_sha256"
    case ConventionCanary = "Convention.canary"
    case ConventionRaw = "Convention.raw"
    case LicenceLicenceId = "Licence.licence_id"
    case LicenceSpdx = "Licence.spdx"
    case LicenceProvider = "Licence.provider"
    case LicenceCitation = "Licence.citation"
    case LicenceAttribution = "Licence.attribution"
    case LicenceUrl = "Licence.url"
    case LicenceCommercialUse = "Licence.commercial_use"
    case LicenceRestriction = "Licence.restriction"
    case LicenceTermsUrl = "Licence.terms_url"
    case LicenceRaw = "Licence.raw"
    case ProvenanceAdapterVersion = "Provenance.adapter_version"
    case ProvenanceInputSha256 = "Provenance.input_sha256"
    case ProvenanceSelectionReason = "Provenance.selection_reason"
    case ProvenanceDecision = "Provenance.decision"
    case ProvenanceBuild = "Provenance.build"
    case ProvenanceCarriedFromRelease = "Provenance.carried_from_release"
    case ProvenanceRaw = "Provenance.raw"
    case ProvenanceBuildBuildCommit = "ProvenanceBuild.build_commit"
    case ProvenanceBuildBuiltAt = "ProvenanceBuild.built_at"
    case ProvenanceBuildFetchedAt = "ProvenanceBuild.fetched_at"
    case ProvenanceBuildRunId = "ProvenanceBuild.run_id"
    case ProvenanceBuildToolVersions = "ProvenanceBuild.tool_versions"
    case TimeBaseCode = "TimeBase.code"
    case TimeBaseReason = "TimeBase.reason"
    case TimeBaseDeclared = "TimeBase.declared"
    case TimeBasePublished = "TimeBase.published"
    case TimeBaseCorrection = "TimeBase.correction"
    case TimeBaseMonthsDropped = "TimeBase.months_dropped"
    case TimeBaseDecidedIn = "TimeBase.decided_in"
    case TimeBaseDecidedBuildCommit = "TimeBase.decided_build_commit"
    case TimeBaseEvidence = "TimeBase.evidence"
    case QcFlagFlag = "QcFlag.flag"
    case QcFlagReason = "QcFlag.reason"
    case QcFlagValues = "QcFlag.values"
    case DroppedConstituentName = "DroppedConstituent.name"
    case DroppedConstituentDroppedReason = "DroppedConstituent.dropped_reason"
    case DroppedConstituentDetail = "DroppedConstituent.detail"
    case ValidationSetId = "Validation.set_id"
    case ValidationReferenceSource = "Validation.reference_source"
    case ValidationReferenceStation = "Validation.reference_station"
    case ValidationReferenceDistanceKm = "Validation.reference_distance_km"
    case ValidationWindow = "Validation.window"
    case ValidationTimeMaeMin = "Validation.time_mae_min"
    case ValidationTimeP95Min = "Validation.time_p95_min"
    case ValidationTimeBiasMin = "Validation.time_bias_min"
    case ValidationHeightMaeM = "Validation.height_mae_m"
    case ValidationRangeErrorM = "Validation.range_error_m"
    case ValidationMissedEvents = "Validation.missed_events"
    case ValidationExtraEvents = "Validation.extra_events"
    case ValidationPreviousRelease = "Validation.previous_release"
    case SubordinateOffsetsReferenceStationId = "SubordinateOffsets.reference_station_id"
    case SubordinateOffsetsTimeOffsetHighMin = "SubordinateOffsets.time_offset_high_min"
    case SubordinateOffsetsTimeOffsetLowMin = "SubordinateOffsets.time_offset_low_min"
    case SubordinateOffsetsHeightOffsetHigh = "SubordinateOffsets.height_offset_high"
    case SubordinateOffsetsHeightOffsetLow = "SubordinateOffsets.height_offset_low"
    case SubordinateOffsetsHeightAdjustedType = "SubordinateOffsets.height_adjusted_type"
    case SubordinateOffsetsLicenceId = "SubordinateOffsets.licence_id"
    case SubordinateOffsetsOffsetId = "SubordinateOffsets.offset_id"
    case SubordinateOffsetsSource = "SubordinateOffsets.source"
    case SubordinateOffsetsSourceType = "SubordinateOffsets.source_type"
    case SubordinateOffsetsSourceVersion = "SubordinateOffsets.source_version"
    case SubordinateOffsetsSourceRecordId = "SubordinateOffsets.source_record_id"
    case SubordinateOffsetsQcStatus = "SubordinateOffsets.qc_status"
    case SubordinateOffsetsQcFlags = "SubordinateOffsets.qc_flags"
    case SubordinateOffsetsFallback = "SubordinateOffsets.fallback"
    case SubordinateOffsetsVintage = "SubordinateOffsets.vintage"
    case SubordinateOffsetsProvenance = "SubordinateOffsets.provenance"
    case NearbyStation = "Nearby.station"
    case NearbyDistanceKm = "Nearby.distance_km"
    case UpdateResultUpdated = "UpdateResult.updated"
    case UpdateResultFrom = "UpdateResult.from"
    case UpdateResultTo = "UpdateResult.to"
    case RecordSpanStart = "RecordSpan.start"
    case RecordSpanEnd = "RecordSpan.end"
    case RecordSpanGoodSamples = "RecordSpan.good_samples"
    case DatumMslOffsetM = "Datum.msl_offset_m"
    case DatumNamed = "Datum.named"
    case StatsType = "Stats.type"
    case StatsKind = "Stats.kind"
    case StatsCountry = "Stats.country"
    case StatsSource = "Stats.source"
    case StatsQcStatus = "Stats.qc_status"
    case AstroTableEquilibriumArgument = "AstroTable.equilibrium_argument"
    case AstroTableNodeFactor = "AstroTable.node_factor"
    case AstroTableEquilibriumForYear = "AstroTable.equilibrium_for_year"
    case AstroTableNodeFactorForYear = "AstroTable.node_factor_for_year"
    case AstroTableValidRange = "AstroTable.valid_range"
    case HeightPointTime = "HeightPoint.time"
    case HeightPointHeightM = "HeightPoint.height_m"
    case HeightPointLocalTime = "HeightPoint.local_time"
    case HeightPointUtcOffsetS = "HeightPoint.utc_offset_s"
    case HeightPointLocalDatetime = "HeightPoint.local_datetime"
    case HeightPointLocalTimeObject = "HeightPoint.local_time_object"
    case ExtremeTime = "Extreme.time"
    case ExtremeType = "Extreme.type"
    case ExtremeHeightM = "Extreme.height_m"
    case ExtremeLocalTime = "Extreme.local_time"
    case ExtremeUtcOffsetS = "Extreme.utc_offset_s"
    case ExtremeLocalDatetime = "Extreme.local_datetime"
    case ExtremeLocalTimeObject = "Extreme.local_time_object"
    case CurrentPointTime = "CurrentPoint.time"
    case CurrentPointVelocityMajorMs = "CurrentPoint.velocity_major_ms"
    case CurrentPointVelocityMinorMs = "CurrentPoint.velocity_minor_ms"
    case CurrentPointSpeedMs = "CurrentPoint.speed_ms"
    case CurrentPointDirectionDeg = "CurrentPoint.direction_deg"
    case CurrentPointLocalTime = "CurrentPoint.local_time"
    case CurrentPointUtcOffsetS = "CurrentPoint.utc_offset_s"
    case CurrentPointLocalDatetime = "CurrentPoint.local_datetime"
    case CurrentPointLocalTimeObject = "CurrentPoint.local_time_object"
    case CurrentEventTime = "CurrentEvent.time"
    case CurrentEventType = "CurrentEvent.type"
    case CurrentEventVelocityMs = "CurrentEvent.velocity_ms"
    case CurrentEventDirectionDeg = "CurrentEvent.direction_deg"
    case CurrentEventLocalTime = "CurrentEvent.local_time"
    case CurrentEventUtcOffsetS = "CurrentEvent.utc_offset_s"
    case CurrentEventLocalDatetime = "CurrentEvent.local_datetime"
    case CurrentEventLocalTimeObject = "CurrentEvent.local_time_object"
    case HeightSeriesItems = "HeightSeries.items"
    case HeightSeriesStationId = "HeightSeries.station_id"
    case HeightSeriesTimezone = "HeightSeries.timezone"
    case HeightSeriesMethod = "HeightSeries.method"
    case HeightSeriesSetId = "HeightSeries.set_id"
    case HeightSeriesConventionId = "HeightSeries.convention_id"
    case HeightSeriesAstroTableId = "HeightSeries.astro_table_id"
    case HeightSeriesReferenceStationId = "HeightSeries.reference_station_id"
    case HeightSeriesReferenceBin = "HeightSeries.reference_bin"
    case HeightSeriesDatum = "HeightSeries.datum"
    case HeightSeriesDatumName = "HeightSeries.datum_name"
    case HeightSeriesDatumKind = "HeightSeries.datum_kind"
    case HeightSeriesDatumUncertaintyM = "HeightSeries.datum_uncertainty_m"
    case HeightSeriesTz = "HeightSeries.tz"
    case HeightSeriesTzVersion = "HeightSeries.tz_version"
    case HeightSeriesRelease = "HeightSeries.release"
    case HeightSeriesAlgorithm = "HeightSeries.algorithm"
    case HeightSeriesToLocal = "HeightSeries.to_local"
    case HeightSeriesOffsetId = "HeightSeries.offset_id"
    case HeightSeriesOffsetSource = "HeightSeries.offset_source"
    case HeightSeriesOffsetSourceVersion = "HeightSeries.offset_source_version"
    case HeightSeriesHistoricalOffsets = "HeightSeries.historical_offsets"
    case HeightSeriesCurrentValidity = "HeightSeries.current_validity"
    case HeightSeriesCurrentAccuracy = "HeightSeries.current_accuracy"
    case HeightSeriesReferenceSetId = "HeightSeries.reference_set_id"
    case HeightSeriesReferenceSourceVersion = "HeightSeries.reference_source_version"
    case HeightSeriesReference2020Equivalence = "HeightSeries.reference_2020_equivalence"
    case HeightSeriesSourceNote = "HeightSeries.source_note"
    case ExtremeListItems = "ExtremeList.items"
    case ExtremeListStationId = "ExtremeList.station_id"
    case ExtremeListTimezone = "ExtremeList.timezone"
    case ExtremeListMethod = "ExtremeList.method"
    case ExtremeListSetId = "ExtremeList.set_id"
    case ExtremeListConventionId = "ExtremeList.convention_id"
    case ExtremeListAstroTableId = "ExtremeList.astro_table_id"
    case ExtremeListReferenceStationId = "ExtremeList.reference_station_id"
    case ExtremeListReferenceBin = "ExtremeList.reference_bin"
    case ExtremeListDatum = "ExtremeList.datum"
    case ExtremeListDatumName = "ExtremeList.datum_name"
    case ExtremeListDatumKind = "ExtremeList.datum_kind"
    case ExtremeListDatumUncertaintyM = "ExtremeList.datum_uncertainty_m"
    case ExtremeListTz = "ExtremeList.tz"
    case ExtremeListTzVersion = "ExtremeList.tz_version"
    case ExtremeListRelease = "ExtremeList.release"
    case ExtremeListAlgorithm = "ExtremeList.algorithm"
    case ExtremeListToLocal = "ExtremeList.to_local"
    case ExtremeListOffsetId = "ExtremeList.offset_id"
    case ExtremeListOffsetSource = "ExtremeList.offset_source"
    case ExtremeListOffsetSourceVersion = "ExtremeList.offset_source_version"
    case ExtremeListHistoricalOffsets = "ExtremeList.historical_offsets"
    case ExtremeListCurrentValidity = "ExtremeList.current_validity"
    case ExtremeListCurrentAccuracy = "ExtremeList.current_accuracy"
    case ExtremeListReferenceSetId = "ExtremeList.reference_set_id"
    case ExtremeListReferenceSourceVersion = "ExtremeList.reference_source_version"
    case ExtremeListReference2020Equivalence = "ExtremeList.reference_2020_equivalence"
    case ExtremeListSourceNote = "ExtremeList.source_note"
    case CurrentSeriesItems = "CurrentSeries.items"
    case CurrentSeriesStationId = "CurrentSeries.station_id"
    case CurrentSeriesTimezone = "CurrentSeries.timezone"
    case CurrentSeriesMethod = "CurrentSeries.method"
    case CurrentSeriesSetId = "CurrentSeries.set_id"
    case CurrentSeriesConventionId = "CurrentSeries.convention_id"
    case CurrentSeriesAstroTableId = "CurrentSeries.astro_table_id"
    case CurrentSeriesReferenceStationId = "CurrentSeries.reference_station_id"
    case CurrentSeriesReferenceBin = "CurrentSeries.reference_bin"
    case CurrentSeriesDatum = "CurrentSeries.datum"
    case CurrentSeriesDatumName = "CurrentSeries.datum_name"
    case CurrentSeriesDatumKind = "CurrentSeries.datum_kind"
    case CurrentSeriesDatumUncertaintyM = "CurrentSeries.datum_uncertainty_m"
    case CurrentSeriesBinNumber = "CurrentSeries.bin_number"
    case CurrentSeriesTz = "CurrentSeries.tz"
    case CurrentSeriesTzVersion = "CurrentSeries.tz_version"
    case CurrentSeriesRelease = "CurrentSeries.release"
    case CurrentSeriesAlgorithm = "CurrentSeries.algorithm"
    case CurrentSeriesToLocal = "CurrentSeries.to_local"
    case CurrentEventListItems = "CurrentEventList.items"
    case CurrentEventListStationId = "CurrentEventList.station_id"
    case CurrentEventListTimezone = "CurrentEventList.timezone"
    case CurrentEventListMethod = "CurrentEventList.method"
    case CurrentEventListSetId = "CurrentEventList.set_id"
    case CurrentEventListConventionId = "CurrentEventList.convention_id"
    case CurrentEventListAstroTableId = "CurrentEventList.astro_table_id"
    case CurrentEventListReferenceStationId = "CurrentEventList.reference_station_id"
    case CurrentEventListReferenceBin = "CurrentEventList.reference_bin"
    case CurrentEventListDatum = "CurrentEventList.datum"
    case CurrentEventListDatumName = "CurrentEventList.datum_name"
    case CurrentEventListDatumKind = "CurrentEventList.datum_kind"
    case CurrentEventListDatumUncertaintyM = "CurrentEventList.datum_uncertainty_m"
    case CurrentEventListBinNumber = "CurrentEventList.bin_number"
    case CurrentEventListOmittedEventTypes = "CurrentEventList.omitted_event_types"
    case CurrentEventListTz = "CurrentEventList.tz"
    case CurrentEventListTzVersion = "CurrentEventList.tz_version"
    case CurrentEventListRelease = "CurrentEventList.release"
    case CurrentEventListAlgorithm = "CurrentEventList.algorithm"
    case CurrentEventListToLocal = "CurrentEventList.to_local"
    case DatumInfoSetId = "DatumInfo.set_id"
    case DatumInfoZero = "DatumInfo.zero"
    case DatumInfoZeroName = "DatumInfo.zero_name"
    case DatumInfoChartDatum = "DatumInfo.chart_datum"
    case DatumInfoMslOffsetM = "DatumInfo.msl_offset_m"
    case DatumInfoLevels = "DatumInfo.levels"
    case DatumLevelKey = "DatumLevel.key"
    case DatumLevelValueM = "DatumLevel.value_m"
    case DatumLevelAboveChartM = "DatumLevel.above_chart_m"
    case DatumLevelKind = "DatumLevel.kind"
    case DatumLevelMethod = "DatumLevel.method"
    case DatumLevelSourceName = "DatumLevel.source_name"
    case DatumLevelEpoch = "DatumLevel.epoch"
    case DatumLevelDataSpan = "DatumLevel.data_span"
    case DatumLevelControlStationId = "DatumLevel.control_station_id"
    case DatumLevelControlSetId = "DatumLevel.control_set_id"
    case DatumLevelControlSourceId = "DatumLevel.control_source_id"
    case DatumLevelUncertaintyM = "DatumLevel.uncertainty_m"
    case DatumLevelUncertaintyBasis = "DatumLevel.uncertainty_basis"
    case DatumLevelFlags = "DatumLevel.flags"
    case RangesMn = "Ranges.mn"
    case RangesGt = "Ranges.gt"
    case RangesDhq = "Ranges.dhq"
    case RangesDlq = "Ranges.dlq"
    case FallbackReason = "Fallback.reason"
    case FallbackBasis = "Fallback.basis"
    case FallbackOtcFinding = "Fallback.otc_finding"
    case FallbackPreferredSetId = "Fallback.preferred_set_id"
    case FallbackRaw = "Fallback.raw"
    case SourceRecordSource = "SourceRecord.source"
    case SourceRecordSourceVersion = "SourceRecord.source_version"
    case SourceRecordSourceRecordId = "SourceRecord.source_record_id"
    case SourceRecordRole = "SourceRecord.role"
    case SourceRecordDisposition = "SourceRecord.disposition"
    case SourceRecordDetail = "SourceRecord.detail"
    case SourceRecordLicenceId = "SourceRecord.licence_id"
    case SourceRecordUpstreamLicenceId = "SourceRecord.upstream_licence_id"
    case SourceRecordPublishedSetIds = "SourceRecord.published_set_ids"
    case SourceRecordProvenance = "SourceRecord.provenance"
    case SourceRecordOriginalMetadata = "SourceRecord.original_metadata"
    case SourceRecordOriginalHarmonics = "SourceRecord.original_harmonics"
    case SourceRecordLicence = "SourceRecord.licence"
    case SourceRecordUpstreamLicence = "SourceRecord.upstream_licence"
    case SourceRecordRaw = "SourceRecord.raw"
    case HistoricalOffsetVintagePublicationYear = "HistoricalOffsetVintage.publication_year"
    case HistoricalOffsetVintageSourceLifecycle = "HistoricalOffsetVintage.source_lifecycle"
    case HistoricalOffsetVintageRemovalEvents = "HistoricalOffsetVintage.removal_events"
    case HistoricalOffsetVintageCurrentValidity = "HistoricalOffsetVintage.current_validity"
    case HistoricalOffsetVintageCurrentAccuracy = "HistoricalOffsetVintage.current_accuracy"
    case HistoricalOffsetVintageReference2020Equivalence = "HistoricalOffsetVintage.reference_2020_equivalence"
    case HistoricalOffsetVintageReference2020EquivalenceSha256 = "HistoricalOffsetVintage.reference_2020_equivalence_sha256"
    case HistoricalOffsetProvenanceSourceManifestSha256 = "HistoricalOffsetProvenance.source_manifest_sha256"
    case HistoricalOffsetProvenanceInputSha256 = "HistoricalOffsetProvenance.input_sha256"
    case HistoricalOffsetProvenanceBook = "HistoricalOffsetProvenance.book"
    case HistoricalOffsetProvenanceAnnualTableRow = "HistoricalOffsetProvenance.annual_table_row"
    case HistoricalOffsetProvenancePrintedPage = "HistoricalOffsetProvenance.printed_page"
    case HistoricalOffsetProvenancePdfPage = "HistoricalOffsetProvenance.pdf_page"
    case HistoricalOffsetProvenanceRawRowText = "HistoricalOffsetProvenance.raw_row_text"
    case HistoricalOffsetProvenanceRawValuesJson = "HistoricalOffsetProvenance.raw_values_json"
    case HistoricalOffsetProvenanceIdCrosswalk = "HistoricalOffsetProvenance.id_crosswalk"
    case HistoricalOffsetProvenanceReferenceBinding = "HistoricalOffsetProvenance.reference_binding"
    case HistoricalOffsetProvenanceAcceptanceReportSha256 = "HistoricalOffsetProvenance.acceptance_report_sha256"
}

internal enum CanonicalMemberResult {
    case ClientOpen(OpenTideConstants)
    case ClientRelease(Release)
    case ClientLoadedFrom(LoadedFrom)
    case ClientLastError(OpenTideConstantsError?)
    case ClientReleases([ReleaseInfo])
    case ClientLatest(ReleaseInfo)
    case ClientCheckForUpdate(ReleaseInfo?)
    case ClientNewerFormatMajor(Int64?)
    case ClientUpdate(UpdateResult)
    case ClientDownload([String])
    case ClientVerify(Bool)
    case ClientCachedReleases([String])
    case ClientPrune([String])
    case ClientClose
    case ReleaseDatestamp(String)
    case ReleaseCreated(Date?)
    case ReleaseFormatVersion(String)
    case ReleaseZenodoVersionDoi(String?)
    case ReleaseConceptDoi(String?)
    case ReleaseSourceVersions([String : String])
    case ReleaseBuildCommit(String?)
    case ReleaseChangelogUrl(String?)
    case ReleaseFiles([FileInfo])
    case ReleaseConventions([Convention])
    case ReleaseConvention(Convention?)
    case ReleaseLicences([Licence])
    case ReleaseLicence(Licence?)
    case ReleaseConstituentNames([String])
    case ReleaseStats(Stats)
    case ReleaseStationCount(Int)
    case ReleaseTombstoneCount(Int)
    case ReleaseCitation(String)
    case ReleaseStation(Station?)
    case ReleaseRequireStation(Station)
    case ReleaseTombstone(Tombstone?)
    case ReleaseStationByAlias(Station?)
    case ReleaseStations([Station])
    case ReleaseIterStations((() throws -> Station?))
    case ReleaseSearch([Station])
    case ReleaseNear([Nearby])
    case ReleaseNearest(Nearby?)
    case ReleaseReferenceStation(Station?)
    case ReleaseSubordinatesOf([Station])
    case ReleaseAttribution(String)
    case ReleaseHeights(HeightSeries)
    case ReleaseHeightsAt(HeightSeries)
    case ReleaseExtremes(ExtremeList)
    case ReleaseCurrents(CurrentSeries)
    case ReleaseCurrentEvents(CurrentEventList)
    case ReleaseDatums(DatumsResult)
    case ReleaseRanges(Ranges)
    case ReleaseAstroTable(AstroTable?)
    case ReleaseHistoricalOffsetsPolicy(String)
    case ReleaseInfoDatestamp(String)
    case ReleaseInfoFormatVersion(String)
    case ReleaseInfoConceptDoi(String?)
    case ReleaseInfoZenodoVersionDoi(String?)
    case ReleaseInfoContentSha256(String)
    case ReleaseInfoFiles([FileInfo])
    case FileInfoName(String)
    case FileInfoUrl(String?)
    case FileInfoSize(Int64?)
    case FileInfoSha256(String?)
    case StationStationId(String)
    case StationName(String?)
    case StationCountry(String?)
    case StationLat(Double)
    case StationLon(Double)
    case StationType(StationType)
    case StationKind(Kind?)
    case StationTimezone(String?)
    case StationAliases([String : [String]])
    case StationStatus(StationStatus)
    case StationIsReference(Bool)
    case StationIsSubordinate(Bool)
    case StationIsTide(Bool)
    case StationIsCurrent(Bool)
    case StationRecommendedSet(ConstantSet?)
    case StationConstantSets([ConstantSet])
    case StationConstantSet(ConstantSet?)
    case StationSubordinateOffsets(SubordinateOffsets?)
    case StationValidation([Validation])
    case StationRaw(JSONValue)
    case StationRecommendedIsFallback(Bool?)
    case StationSourceRecords([SourceRecord])
    case TombstoneStationId(String)
    case TombstoneName(String?)
    case TombstoneStatus(StationStatus)
    case TombstoneRemovedIn(String)
    case TombstoneRemovedReason(RemovedReason)
    case TombstoneMergedInto(String)
    case TombstoneDetail(String?)
    case TombstoneRaw(JSONValue)
    case ConstantSetSetId(String)
    case ConstantSetSource(String?)
    case ConstantSetSourceType(SourceType)
    case ConstantSetQuantity(Quantity)
    case ConstantSetSourceRecordId(String?)
    case ConstantSetSourceVersion(String?)
    case ConstantSetRecordSpan(RecordSpan?)
    case ConstantSetDatum(Datum?)
    case ConstantSetQcStatus(QcStatus)
    case ConstantSetQcFlags([QcFlag])
    case ConstantSetDroppedConstituents([DroppedConstituent])
    case ConstantSetTimeBase(TimeBase?)
    case ConstantSetIsRecommended(Bool)
    case ConstantSetConvention(Convention)
    case ConstantSetLicence(Licence)
    case ConstantSetProvenance(Provenance)
    case ConstantSetValidation([Validation])
    case ConstantSetConstituents([Constituent])
    case ConstantSetConstituent(Constituent?)
    case ConstantSetRaw(JSONValue)
    case ConstantSetFallback(Fallback?)
    case ConstituentName(String)
    case ConstituentSourceName(String?)
    case ConstituentDoodson(String?)
    case ConstituentSpeedDegPerHour(Double)
    case ConstituentAmplitudeM(Double)
    case ConstituentPhaseDeg(Double)
    case ConstituentAmpUncertaintyM(Double?)
    case ConstituentPhaseUncertaintyDeg(Double?)
    case ConstituentKeptReason(String?)
    case ConstituentRaw(JSONValue)
    case ConventionConventionId(String)
    case ConventionPhaseReference(PhaseReference)
    case ConventionUtcOffsetHours(Double?)
    case ConventionV0Model(String)
    case ConventionNodalHandling(NodalHandling)
    case ConventionNodalFormulaIds(JSONValue?)
    case ConventionConstituentTableVersion(String)
    case ConventionTablesSha256(String?)
    case ConventionCanary(JSONValue?)
    case ConventionRaw(JSONValue)
    case LicenceLicenceId(String)
    case LicenceSpdx(String)
    case LicenceProvider(String)
    case LicenceCitation(String?)
    case LicenceAttribution(String)
    case LicenceUrl(String?)
    case LicenceCommercialUse(Bool)
    case LicenceRestriction(String?)
    case LicenceTermsUrl(String?)
    case LicenceRaw(JSONValue)
    case ProvenanceAdapterVersion(String?)
    case ProvenanceInputSha256([String]?)
    case ProvenanceSelectionReason(String?)
    case ProvenanceDecision(JSONValue?)
    case ProvenanceBuild(ProvenanceBuild?)
    case ProvenanceCarriedFromRelease(String?)
    case ProvenanceRaw(JSONValue)
    case ProvenanceBuildBuildCommit(String)
    case ProvenanceBuildBuiltAt(Date?)
    case ProvenanceBuildFetchedAt(Date?)
    case ProvenanceBuildRunId(String?)
    case ProvenanceBuildToolVersions(JSONValue?)
    case TimeBaseCode(TimeBaseCode)
    case TimeBaseReason(String)
    case TimeBaseDeclared(String)
    case TimeBasePublished(String)
    case TimeBaseCorrection(JSONValue?)
    case TimeBaseMonthsDropped([String])
    case TimeBaseDecidedIn(String)
    case TimeBaseDecidedBuildCommit(String?)
    case TimeBaseEvidence(JSONValue)
    case QcFlagFlag(QcFlagName)
    case QcFlagReason(String)
    case QcFlagValues(JSONValue?)
    case DroppedConstituentName(String)
    case DroppedConstituentDroppedReason(DroppedReason)
    case DroppedConstituentDetail(String?)
    case ValidationSetId(String)
    case ValidationReferenceSource(String)
    case ValidationReferenceStation(String?)
    case ValidationReferenceDistanceKm(Double?)
    case ValidationWindow(String)
    case ValidationTimeMaeMin(Double)
    case ValidationTimeP95Min(Double?)
    case ValidationTimeBiasMin(Double?)
    case ValidationHeightMaeM(Double)
    case ValidationRangeErrorM(Double?)
    case ValidationMissedEvents(Int64?)
    case ValidationExtraEvents(Int64?)
    case ValidationPreviousRelease(JSONValue?)
    case SubordinateOffsetsReferenceStationId(String)
    case SubordinateOffsetsTimeOffsetHighMin(Double?)
    case SubordinateOffsetsTimeOffsetLowMin(Double?)
    case SubordinateOffsetsHeightOffsetHigh(Double?)
    case SubordinateOffsetsHeightOffsetLow(Double?)
    case SubordinateOffsetsHeightAdjustedType(HeightAdjustedType)
    case SubordinateOffsetsLicenceId(String?)
    case SubordinateOffsetsOffsetId(String?)
    case SubordinateOffsetsSource(String?)
    case SubordinateOffsetsSourceType(SourceType?)
    case SubordinateOffsetsSourceVersion(String?)
    case SubordinateOffsetsSourceRecordId(String?)
    case SubordinateOffsetsQcStatus(QcStatus?)
    case SubordinateOffsetsQcFlags([QcFlag])
    case SubordinateOffsetsFallback(Fallback?)
    case SubordinateOffsetsVintage(HistoricalOffsetVintage?)
    case SubordinateOffsetsProvenance(HistoricalOffsetProvenance?)
    case NearbyStation(Station)
    case NearbyDistanceKm(Double)
    case UpdateResultUpdated(Bool)
    case UpdateResultFrom(String?)
    case UpdateResultTo(String?)
    case RecordSpanStart(Date?)
    case RecordSpanEnd(Date?)
    case RecordSpanGoodSamples(Int64?)
    case DatumMslOffsetM(Double?)
    case DatumNamed(JSONValue?)
    case StatsType([String : Int64])
    case StatsKind([String : Int64])
    case StatsCountry([String : Int64])
    case StatsSource([String : Int64])
    case StatsQcStatus([String : Int64])
    case AstroTableEquilibriumArgument(Double)
    case AstroTableNodeFactor(Double)
    case AstroTableEquilibriumForYear(Double)
    case AstroTableNodeFactorForYear(Double)
    case AstroTableValidRange([Int64])
    case HeightPointTime(Date)
    case HeightPointHeightM(Double)
    case HeightPointLocalTime(String?)
    case HeightPointUtcOffsetS(Int64?)
    case HeightPointLocalDatetime(Date?)
    case HeightPointLocalTimeObject(Date?)
    case ExtremeTime(Date)
    case ExtremeType(ExtremeType)
    case ExtremeHeightM(Double)
    case ExtremeLocalTime(String?)
    case ExtremeUtcOffsetS(Int64?)
    case ExtremeLocalDatetime(Date?)
    case ExtremeLocalTimeObject(Date?)
    case CurrentPointTime(Date)
    case CurrentPointVelocityMajorMs(Double)
    case CurrentPointVelocityMinorMs(Double)
    case CurrentPointSpeedMs(Double)
    case CurrentPointDirectionDeg(Double?)
    case CurrentPointLocalTime(String?)
    case CurrentPointUtcOffsetS(Int64?)
    case CurrentPointLocalDatetime(Date?)
    case CurrentPointLocalTimeObject(Date?)
    case CurrentEventTime(Date)
    case CurrentEventType(CurrentEventType)
    case CurrentEventVelocityMs(Double)
    case CurrentEventDirectionDeg(Double?)
    case CurrentEventLocalTime(String?)
    case CurrentEventUtcOffsetS(Int64?)
    case CurrentEventLocalDatetime(Date?)
    case CurrentEventLocalTimeObject(Date?)
    case HeightSeriesItems([HeightPoint])
    case HeightSeriesStationId(String?)
    case HeightSeriesTimezone(String?)
    case HeightSeriesMethod(PredictionMethod?)
    case HeightSeriesSetId(String?)
    case HeightSeriesConventionId(String?)
    case HeightSeriesAstroTableId(String?)
    case HeightSeriesReferenceStationId(String?)
    case HeightSeriesReferenceBin(Int64?)
    case HeightSeriesDatum(String?)
    case HeightSeriesDatumName(String?)
    case HeightSeriesDatumKind(String?)
    case HeightSeriesDatumUncertaintyM(Double?)
    case HeightSeriesTz(String?)
    case HeightSeriesTzVersion(String?)
    case HeightSeriesRelease(String?)
    case HeightSeriesAlgorithm(String?)
    case HeightSeriesToLocal(HeightSeries)
    case HeightSeriesOffsetId(String?)
    case HeightSeriesOffsetSource(String?)
    case HeightSeriesOffsetSourceVersion(String?)
    case HeightSeriesHistoricalOffsets(Bool)
    case HeightSeriesCurrentValidity(String?)
    case HeightSeriesCurrentAccuracy(String?)
    case HeightSeriesReferenceSetId(String?)
    case HeightSeriesReferenceSourceVersion(String?)
    case HeightSeriesReference2020Equivalence(String?)
    case HeightSeriesSourceNote(String?)
    case ExtremeListItems([Extreme])
    case ExtremeListStationId(String?)
    case ExtremeListTimezone(String?)
    case ExtremeListMethod(PredictionMethod?)
    case ExtremeListSetId(String?)
    case ExtremeListConventionId(String?)
    case ExtremeListAstroTableId(String?)
    case ExtremeListReferenceStationId(String?)
    case ExtremeListReferenceBin(Int64?)
    case ExtremeListDatum(String?)
    case ExtremeListDatumName(String?)
    case ExtremeListDatumKind(String?)
    case ExtremeListDatumUncertaintyM(Double?)
    case ExtremeListTz(String?)
    case ExtremeListTzVersion(String?)
    case ExtremeListRelease(String?)
    case ExtremeListAlgorithm(String?)
    case ExtremeListToLocal(ExtremeList)
    case ExtremeListOffsetId(String?)
    case ExtremeListOffsetSource(String?)
    case ExtremeListOffsetSourceVersion(String?)
    case ExtremeListHistoricalOffsets(Bool)
    case ExtremeListCurrentValidity(String?)
    case ExtremeListCurrentAccuracy(String?)
    case ExtremeListReferenceSetId(String?)
    case ExtremeListReferenceSourceVersion(String?)
    case ExtremeListReference2020Equivalence(String?)
    case ExtremeListSourceNote(String?)
    case CurrentSeriesItems([CurrentPoint])
    case CurrentSeriesStationId(String?)
    case CurrentSeriesTimezone(String?)
    case CurrentSeriesMethod(PredictionMethod?)
    case CurrentSeriesSetId(String?)
    case CurrentSeriesConventionId(String?)
    case CurrentSeriesAstroTableId(String?)
    case CurrentSeriesReferenceStationId(String?)
    case CurrentSeriesReferenceBin(Int64?)
    case CurrentSeriesDatum(String?)
    case CurrentSeriesDatumName(String?)
    case CurrentSeriesDatumKind(String?)
    case CurrentSeriesDatumUncertaintyM(Double?)
    case CurrentSeriesBinNumber(Int64?)
    case CurrentSeriesTz(String?)
    case CurrentSeriesTzVersion(String?)
    case CurrentSeriesRelease(String?)
    case CurrentSeriesAlgorithm(String?)
    case CurrentSeriesToLocal(CurrentSeries)
    case CurrentEventListItems([CurrentEvent])
    case CurrentEventListStationId(String?)
    case CurrentEventListTimezone(String?)
    case CurrentEventListMethod(PredictionMethod?)
    case CurrentEventListSetId(String?)
    case CurrentEventListConventionId(String?)
    case CurrentEventListAstroTableId(String?)
    case CurrentEventListReferenceStationId(String?)
    case CurrentEventListReferenceBin(Int64?)
    case CurrentEventListDatum(String?)
    case CurrentEventListDatumName(String?)
    case CurrentEventListDatumKind(String?)
    case CurrentEventListDatumUncertaintyM(Double?)
    case CurrentEventListBinNumber(Int64?)
    case CurrentEventListOmittedEventTypes([CurrentEventType]?)
    case CurrentEventListTz(String?)
    case CurrentEventListTzVersion(String?)
    case CurrentEventListRelease(String?)
    case CurrentEventListAlgorithm(String?)
    case CurrentEventListToLocal(CurrentEventList)
    case DatumInfoSetId(String?)
    case DatumInfoZero(String?)
    case DatumInfoZeroName(String?)
    case DatumInfoChartDatum(String?)
    case DatumInfoMslOffsetM(Double?)
    case DatumInfoLevels([DatumLevel])
    case DatumLevelKey(String?)
    case DatumLevelValueM(Double)
    case DatumLevelAboveChartM(Double?)
    case DatumLevelKind(String?)
    case DatumLevelMethod(String?)
    case DatumLevelSourceName(String?)
    case DatumLevelEpoch(JSONValue)
    case DatumLevelDataSpan(JSONValue)
    case DatumLevelControlStationId(String?)
    case DatumLevelControlSetId(String?)
    case DatumLevelControlSourceId(String?)
    case DatumLevelUncertaintyM(Double?)
    case DatumLevelUncertaintyBasis(String?)
    case DatumLevelFlags([String])
    case RangesMn(Double?)
    case RangesGt(Double?)
    case RangesDhq(Double?)
    case RangesDlq(Double?)
    case FallbackReason(FallbackReason)
    case FallbackBasis(String)
    case FallbackOtcFinding(String)
    case FallbackPreferredSetId(String?)
    case FallbackRaw(JSONValue)
    case SourceRecordSource(String)
    case SourceRecordSourceVersion(String)
    case SourceRecordSourceRecordId(String)
    case SourceRecordRole(SourceRole)
    case SourceRecordDisposition(SourceDisposition)
    case SourceRecordDetail(String)
    case SourceRecordLicenceId(String?)
    case SourceRecordUpstreamLicenceId(String?)
    case SourceRecordPublishedSetIds([String])
    case SourceRecordProvenance(JSONValue)
    case SourceRecordOriginalMetadata(JSONValue)
    case SourceRecordOriginalHarmonics(JSONValue?)
    case SourceRecordLicence(Licence?)
    case SourceRecordUpstreamLicence(Licence?)
    case SourceRecordRaw(JSONValue)
    case HistoricalOffsetVintagePublicationYear(Double)
    case HistoricalOffsetVintageSourceLifecycle(String)
    case HistoricalOffsetVintageRemovalEvents(JSONValue)
    case HistoricalOffsetVintageCurrentValidity(String)
    case HistoricalOffsetVintageCurrentAccuracy(String)
    case HistoricalOffsetVintageReference2020Equivalence(String)
    case HistoricalOffsetVintageReference2020EquivalenceSha256(String?)
    case HistoricalOffsetProvenanceSourceManifestSha256(String)
    case HistoricalOffsetProvenanceInputSha256([String])
    case HistoricalOffsetProvenanceBook(String)
    case HistoricalOffsetProvenanceAnnualTableRow(Double)
    case HistoricalOffsetProvenancePrintedPage(Double)
    case HistoricalOffsetProvenancePdfPage(Double)
    case HistoricalOffsetProvenanceRawRowText(String)
    case HistoricalOffsetProvenanceRawValuesJson(String)
    case HistoricalOffsetProvenanceIdCrosswalk(JSONValue)
    case HistoricalOffsetProvenanceReferenceBinding(JSONValue)
    case HistoricalOffsetProvenanceAcceptanceReportSha256(String)
}

internal enum CanonicalTypedModel {
    case Client(OpenTideConstants)
    case Release(Release)
    case ReleaseInfo(ReleaseInfo)
    case FileInfo(FileInfo)
    case Station(Station)
    case Tombstone(Tombstone)
    case ConstantSet(ConstantSet)
    case Constituent(Constituent)
    case Convention(Convention)
    case Licence(Licence)
    case Provenance(Provenance)
    case ProvenanceBuild(ProvenanceBuild)
    case TimeBase(TimeBase)
    case QcFlag(QcFlag)
    case DroppedConstituent(DroppedConstituent)
    case Validation(Validation)
    case SubordinateOffsets(SubordinateOffsets)
    case Nearby(Nearby)
    case UpdateResult(UpdateResult)
    case RecordSpan(RecordSpan)
    case Datum(Datum)
    case Stats(Stats)
    case AstroTable(AstroTable)
    case HeightPoint(HeightPoint)
    case Extreme(Extreme)
    case CurrentPoint(CurrentPoint)
    case CurrentEvent(CurrentEvent)
    case HeightSeries(HeightSeries)
    case ExtremeList(ExtremeList)
    case CurrentSeries(CurrentSeries)
    case CurrentEventList(CurrentEventList)
    case DatumInfo(DatumInfo)
    case DatumLevel(DatumLevel)
    case Ranges(Ranges)
    case Fallback(Fallback)
    case SourceRecord(SourceRecord)
    case HistoricalOffsetVintage(HistoricalOffsetVintage)
    case HistoricalOffsetProvenance(HistoricalOffsetProvenance)
}

internal struct CanonicalFieldContract {
    let modelType: CanonicalModelType
    let members: [CanonicalMemberID]
}

internal enum CanonicalStationRequest {
    case object(Station)
    case id(String)
}

internal struct CanonicalClientOpenArguments {
    let release: String?
    let file: String?
    let cacheDir: String?
    let offline: Bool?
    let mode: Mode
    let baseUrl: String?
    let timeout: Double?
    let proxy: String?
    let caFile: String?
    let userAgent: String?
    let onNetworkError: OnNetworkError?
    let autoUpdate: Bool
    let updateInterval: Double
    let logger: ((String) -> Void)?
    let verifyOnOpen: Bool
    let commercialOnly: Bool
    let commercialBasis: String
    let historicalOffsetsPolicy: String
}

internal struct CanonicalClientReleasesArguments {
}

internal struct CanonicalClientLatestArguments {
}

internal struct CanonicalClientCheckForUpdateArguments {
}

internal struct CanonicalClientUpdateArguments {
}

internal struct CanonicalClientDownloadArguments {
    let release: String
    let to: String
    let formats: [Format]
    let overwrite: Bool
}

internal struct CanonicalClientVerifyArguments {
}

internal struct CanonicalClientCachedReleasesArguments {
}

internal struct CanonicalClientPruneArguments {
    let keep: Int64
}

internal struct CanonicalClientCloseArguments {
}

internal struct CanonicalReleaseConventionArguments {
    let conventionId: String
}

internal struct CanonicalReleaseLicenceArguments {
    let licenceId: String
}

internal struct CanonicalReleaseStationArguments {
    let stationId: String
}

internal struct CanonicalReleaseRequireStationArguments {
    let stationId: String
}

internal struct CanonicalReleaseTombstoneArguments {
    let stationId: String
}

internal struct CanonicalReleaseStationByAliasArguments {
    let system: String
    let aliasId: String
}

internal struct CanonicalReleaseStationsArguments {
    let country: String?
    let type: String?
    let kind: String?
    let source: String?
    let sourceType: String?
    let includeFlagged: Bool
    let includeFallback: Bool
}

internal struct CanonicalReleaseIterStationsArguments {
    let country: String?
    let type: String?
    let kind: String?
    let source: String?
    let sourceType: String?
    let includeFlagged: Bool
    let includeFallback: Bool
}

internal struct CanonicalReleaseSearchArguments {
    let name: String
    let limit: Int64?
    let match: String?
    let country: String?
    let type: String?
    let kind: String?
    let source: String?
    let sourceType: String?
    let includeFlagged: Bool
    let includeFallback: Bool
}

internal struct CanonicalReleaseNearArguments {
    let lat: Double
    let lon: Double
    let radiusKm: Double
    let limit: Int64?
    let country: String?
    let type: String?
    let kind: String?
    let source: String?
    let sourceType: String?
    let includeFlagged: Bool
    let includeFallback: Bool
}

internal struct CanonicalReleaseNearestArguments {
    let lat: Double
    let lon: Double
    let maxKm: Double?
    let country: String?
    let type: String?
    let kind: String?
    let source: String?
    let sourceType: String?
    let includeFlagged: Bool
    let includeFallback: Bool
}

internal struct CanonicalReleaseReferenceStationArguments {
    let station: CanonicalStationRequest
}

internal struct CanonicalReleaseSubordinatesOfArguments {
    let station: CanonicalStationRequest
}

internal struct CanonicalReleaseAttributionArguments {
    let stations: [Station]?
}

internal struct CanonicalReleaseHeightsArguments {
    let station: CanonicalStationRequest
    let start: Date
    let stop: Date
    let stepS: Int64
    let datum: String?
    let setId: String?
    let offsetId: String?
}

internal struct CanonicalReleaseHeightsAtArguments {
    let station: CanonicalStationRequest
    let times: [Date]
    let datum: String?
    let setId: String?
    let offsetId: String?
}

internal struct CanonicalReleaseExtremesArguments {
    let station: CanonicalStationRequest
    let start: Date
    let stop: Date
    let datum: String?
    let setId: String?
    let offsetId: String?
}

internal struct CanonicalReleaseCurrentsArguments {
    let station: CanonicalStationRequest
    let start: Date
    let stop: Date
    let stepS: Int64
    let binNumber: Int64?
    let setId: String?
}

internal struct CanonicalReleaseCurrentEventsArguments {
    let station: CanonicalStationRequest
    let start: Date
    let stop: Date
    let binNumber: Int64?
    let setId: String?
}

internal struct CanonicalReleaseDatumsArguments {
    let station: CanonicalStationRequest
    let setId: String?
    let allSets: Bool
}

internal struct CanonicalReleaseRangesArguments {
    let station: CanonicalStationRequest
    let setId: String?
}

internal struct CanonicalReleaseAstroTableArguments {
    let id: String?
}

internal struct CanonicalStationConstantSetsArguments {
    let includeNoConstants: Bool
}

internal struct CanonicalStationConstantSetArguments {
    let setId: String
}

internal struct CanonicalConstantSetConstituentArguments {
    let name: String
}

internal struct CanonicalAstroTableEquilibriumArgumentArguments {
    let name: String
    let at: Date
}

internal struct CanonicalAstroTableNodeFactorArguments {
    let name: String
    let at: Date
}

internal struct CanonicalAstroTableEquilibriumForYearArguments {
    let name: String
    let year: Int64
}

internal struct CanonicalAstroTableNodeFactorForYearArguments {
    let name: String
    let year: Int64
}

internal struct CanonicalHeightPointLocalDatetimeArguments {
}

internal struct CanonicalExtremeLocalDatetimeArguments {
}

internal struct CanonicalCurrentPointLocalDatetimeArguments {
}

internal struct CanonicalCurrentEventLocalDatetimeArguments {
}

internal struct CanonicalHeightSeriesToLocalArguments {
    let tz: String
}

internal struct CanonicalExtremeListToLocalArguments {
    let tz: String
}

internal struct CanonicalCurrentSeriesToLocalArguments {
    let tz: String
}

internal struct CanonicalCurrentEventListToLocalArguments {
    let tz: String
}

internal enum CanonicalArguments {
    case ClientOpen(CanonicalClientOpenArguments)
    case ClientReleases(CanonicalClientReleasesArguments)
    case ClientLatest(CanonicalClientLatestArguments)
    case ClientCheckForUpdate(CanonicalClientCheckForUpdateArguments)
    case ClientUpdate(CanonicalClientUpdateArguments)
    case ClientDownload(CanonicalClientDownloadArguments)
    case ClientVerify(CanonicalClientVerifyArguments)
    case ClientCachedReleases(CanonicalClientCachedReleasesArguments)
    case ClientPrune(CanonicalClientPruneArguments)
    case ClientClose(CanonicalClientCloseArguments)
    case ReleaseConvention(CanonicalReleaseConventionArguments)
    case ReleaseLicence(CanonicalReleaseLicenceArguments)
    case ReleaseStation(CanonicalReleaseStationArguments)
    case ReleaseRequireStation(CanonicalReleaseRequireStationArguments)
    case ReleaseTombstone(CanonicalReleaseTombstoneArguments)
    case ReleaseStationByAlias(CanonicalReleaseStationByAliasArguments)
    case ReleaseStations(CanonicalReleaseStationsArguments)
    case ReleaseIterStations(CanonicalReleaseIterStationsArguments)
    case ReleaseSearch(CanonicalReleaseSearchArguments)
    case ReleaseNear(CanonicalReleaseNearArguments)
    case ReleaseNearest(CanonicalReleaseNearestArguments)
    case ReleaseReferenceStation(CanonicalReleaseReferenceStationArguments)
    case ReleaseSubordinatesOf(CanonicalReleaseSubordinatesOfArguments)
    case ReleaseAttribution(CanonicalReleaseAttributionArguments)
    case ReleaseHeights(CanonicalReleaseHeightsArguments)
    case ReleaseHeightsAt(CanonicalReleaseHeightsAtArguments)
    case ReleaseExtremes(CanonicalReleaseExtremesArguments)
    case ReleaseCurrents(CanonicalReleaseCurrentsArguments)
    case ReleaseCurrentEvents(CanonicalReleaseCurrentEventsArguments)
    case ReleaseDatums(CanonicalReleaseDatumsArguments)
    case ReleaseRanges(CanonicalReleaseRangesArguments)
    case ReleaseAstroTable(CanonicalReleaseAstroTableArguments)
    case StationConstantSets(CanonicalStationConstantSetsArguments)
    case StationConstantSet(CanonicalStationConstantSetArguments)
    case ConstantSetConstituent(CanonicalConstantSetConstituentArguments)
    case AstroTableEquilibriumArgument(CanonicalAstroTableEquilibriumArgumentArguments)
    case AstroTableNodeFactor(CanonicalAstroTableNodeFactorArguments)
    case AstroTableEquilibriumForYear(CanonicalAstroTableEquilibriumForYearArguments)
    case AstroTableNodeFactorForYear(CanonicalAstroTableNodeFactorForYearArguments)
    case HeightPointLocalDatetime(CanonicalHeightPointLocalDatetimeArguments)
    case ExtremeLocalDatetime(CanonicalExtremeLocalDatetimeArguments)
    case CurrentPointLocalDatetime(CanonicalCurrentPointLocalDatetimeArguments)
    case CurrentEventLocalDatetime(CanonicalCurrentEventLocalDatetimeArguments)
    case HeightSeriesToLocal(CanonicalHeightSeriesToLocalArguments)
    case ExtremeListToLocal(CanonicalExtremeListToLocalArguments)
    case CurrentSeriesToLocal(CanonicalCurrentSeriesToLocalArguments)
    case CurrentEventListToLocal(CanonicalCurrentEventListToLocalArguments)
}

internal enum CanonicalCurrentRequest {
    case ReleaseCurrents(CanonicalReleaseCurrentsArguments)
    case ReleaseCurrentEvents(CanonicalReleaseCurrentEventsArguments)
}

internal enum CanonicalTideRequest {
    case ReleaseHeights(CanonicalReleaseHeightsArguments)
    case ReleaseHeightsAt(CanonicalReleaseHeightsAtArguments)
    case ReleaseExtremes(CanonicalReleaseExtremesArguments)
}

internal enum CanonicalQueryArguments {
    case ReleaseStations(CanonicalReleaseStationsArguments)
    case ReleaseIterStations(CanonicalReleaseIterStationsArguments)
    case ReleaseSearch(CanonicalReleaseSearchArguments)
    case ReleaseNear(CanonicalReleaseNearArguments)
    case ReleaseNearest(CanonicalReleaseNearestArguments)
}

internal struct CanonicalEffectiveOptions {
    let release: String?
    let file: String?
    let cacheDir: String?
    let offline: Bool?
    let mode: Mode
    let baseUrl: String?
    let timeout: Double?
    let proxy: String?
    let caFile: String?
    let userAgent: String?
    let onNetworkError: OnNetworkError?
    let autoUpdate: Bool
    let updateInterval: Double
    let logger: ((String) -> Void)?
    let verifyOnOpen: Bool
    let commercialOnly: Bool
    let commercialBasis: String
    let historicalOffsetsPolicy: String
}

internal struct CanonicalTransportOptions {
    let offline: Bool?
    let baseUrl: String?
    let timeout: Double?
    let proxy: String?
    let caFile: String?
    let userAgent: String?
}

internal struct CanonicalSelectionOptions {
    let setId: String?
    let binNumber: Int64?
    let commercialOnly: Bool
    let offsetId: String?
    let datum: String?
}

internal typealias CanonicalQueryOptions = CanonicalQueryArguments

internal struct CanonicalProjectionRules {
    let scalarMembers: [CanonicalMemberID]
    let modelType: CanonicalModelType
    let preserveUnknownSourceFields: Bool
}

internal struct CanonicalLinkTable {
    let stationIds: Set<String>
    let constantSetIds: Set<String>
    let conventionIds: Set<String>
    let licenceIds: Set<String>
    let astroTableIds: Set<String>
    let sourceRecordIds: Set<String>
}

internal struct CanonicalStreamIndexSet {
    let setId: String?
    let source: String?
    let sourceType: String?
    let quantity: String?
    let qcStatus: String?
    let conventionId: String?
    let licenceId: String?
    let constituents: [String]
    let fallback: Fallback?
    let currentBins: [Int64]
}

internal struct CanonicalStreamIndexCurrentOffset {
    let bin: Int64
    let referenceBin: Int64
    let referenceStationId: String?
    let licenceId: String?
}

internal struct CanonicalStreamIndexStation {
    let stationId: String
    let status: String
    let name: String?
    let nameFolded: String?
    let country: String?
    let type: String?
    let kind: String?
    let referenceStationId: String?
    let offsetsLicenceId: String?
    let recommendedSetId: String?
    let lat: Double?
    let lon: Double?
    let offset: Int64
    let length: Int64
    let aliases: [String: [String]]
    let sets: [CanonicalStreamIndexSet]
    let subordinateOffsets: SubordinateOffsets?
    let currentOffsets: [CanonicalStreamIndexCurrentOffset]
}

internal struct CanonicalStreamIndex {
    let indexVersion: Int64
    let discoveryIndexVersion: Int64
    let datestamp: String
    let jsonl: String
    let jsonlSha256: String
    let jsonlSize: Int64
    let by: String
    let stations: [CanonicalStreamIndexStation]
}

internal struct CanonicalVerifiedFile {
    let sha256: String
    let size: Int64
    let url: String?
}

internal struct CanonicalVerifiedReceipt {
    let datestamp: String
    let files: [String: CanonicalVerifiedFile]
    let formatVersion: String
    let minReaderVersion: String
    let zenodoVersionDoi: String?
    let verifiedAt: String
    let by: String
}

internal struct CanonicalStationLookupActive {
    let station: Station
}

internal struct CanonicalStationLookupRemoved {
    let tombstone: Tombstone
}

internal struct CanonicalStationLookupAbsent {
}

internal enum CanonicalStationLookup {
    case active(CanonicalStationLookupActive)
    case removed(CanonicalStationLookupRemoved)
    case absent(CanonicalStationLookupAbsent)
}

internal struct CanonicalPredictionModel {
    let station: Station
    let releaseView: Release
    let constantSet: ConstantSet
    let convention: Convention
    let astroTable: JSONValue
    let requiredConstituents: [JSONValue]
    let referenceBin: Int64?
    let meanTerm: Double
    let datumSource: JSONValue?
}

internal struct CanonicalPredictionWindow {
    let start: Double
    let stop: Double
    let step: Double?
    let instants: JSONValue?
}

internal typealias CanonicalFileRows = [JSONValue]

internal typealias CanonicalDigestMap = [String: String]

internal struct CanonicalLockState {
    let cacheRoot: URL
    let owner: JSONValue?
    let heldToken: String?
}

internal struct CanonicalCacheState {
    let cacheRoot: URL
    let releaseCandidates: [String]
    let pointerCache: JSONValue?
    let lockState: CanonicalLockState
}

internal struct CanonicalReleaseDescriptor {
    let datestamp: String
    let files: CanonicalFileRows
    let checksumBytes: Data?
    let pointerDigests: CanonicalDigestMap
    let requiredFileRequest: JSONValue?
    let metadata: JSONValue
}

internal struct CanonicalReferencePath {
    let station: Station
    let releaseView: Release
    let constantSet: ConstantSet?
    let ownOffset: JSONValue?
    let referenceBin: Int64?
}

internal struct CanonicalCandidatePathDirect {
    let station: Station
    let constantSet: ConstantSet
    let releaseView: Release
}

internal struct CanonicalCandidatePathTideOffset {
    let referencePath: CanonicalReferencePath
    let ownOffset: JSONValue
}

internal struct CanonicalCandidatePathCurrentOffset {
    let referencePath: CanonicalReferencePath
    let ownCurrentOffset: JSONValue
}

internal enum CanonicalCandidatePath {
    case direct(CanonicalCandidatePathDirect)
    case tideOffset(CanonicalCandidatePathTideOffset)
    case currentOffset(CanonicalCandidatePathCurrentOffset)
}

internal enum CanonicalUnroundedTideEventEventType: String, CaseIterable {
    case high = "high"
    case low = "low"
}

internal struct CanonicalUnroundedTideEvent {
    let rootSeconds: Double
    let eventType: CanonicalUnroundedTideEventEventType
    let heightM: Double
    let referenceOrder: Int64
}

internal enum CanonicalUnroundedCurrentEventEventType: String, CaseIterable {
    case maxFlood = "max_flood"
    case maxEbb = "max_ebb"
    case slackBeforeFlood = "slack_before_flood"
    case slackBeforeEbb = "slack_before_ebb"
}

internal struct CanonicalUnroundedCurrentEvent {
    let rootSeconds: Double
    let eventType: CanonicalUnroundedCurrentEventEventType
    let velocityMS: Double
    let directionDeg: Double?
    let referenceOrder: Int64
}

internal enum CanonicalAuxiliaryValuesRequiresModelStationRequest {
    case Station(Station)
    case String(String)
}

internal struct CanonicalAuxiliaryValuesRequiresModel {
    let stationRequest: CanonicalAuxiliaryValuesRequiresModelStationRequest
    let releaseView: Release
    let selectionOptions: CanonicalSelectionOptions
    let utcInstant: Double?
}

internal struct CanonicalAuxiliaryValuesSourceAccess {
    let rawSourceValue: JSONValue
    let arguments: JSONValue
}

internal enum CanonicalAuxiliaryValues {
    case requiresModel(CanonicalAuxiliaryValuesRequiresModel)
    case sourceAccess(CanonicalAuxiliaryValuesSourceAccess)
}

internal struct CanonicalResultContext {
    let stationId: String
    let setId: String?
    let referenceStationId: String?
    let binNumber: Int64?
    let datum: String?
    let releaseDatestamp: String
    let algorithm: String
}

internal struct CanonicalAcceptanceDecision {
    let accepted: Bool
    let mandatoryFindings: [String]
}

internal enum CanonicalAccessKind: String, CaseIterable {
    case rawRecord = "raw_record"
    case stationObject = "station_object"
}

internal typealias CanonicalAcquisitionDescriptor = CanonicalReleaseDescriptor

internal typealias CanonicalActualProfileResults = [String: JSONValue]

internal struct CanonicalAstronomicalTerms {
    let utcYear: Int64
    let constituentTerms: [JSONValue]
    let epochHours: Double
}

internal typealias CanonicalAttributionText = String

internal typealias CanonicalAuthenticatedIndex = CanonicalStreamIndex

internal enum CanonicalAuxiliaryKind: String, CaseIterable {
    case modelAccess = "model_access"
    case resultContext = "result_context"
    case localTime = "local_time"
}

internal typealias CanonicalAuxiliaryModelValue = CanonicalMemberResult

internal enum CanonicalAuxiliaryOperation: String, CaseIterable {
    case astroTable = "astro_table"
    case datums = "datums"
    case ranges = "ranges"
    case constituent = "constituent"
    case constituents = "constituents"
    case constituentNames = "constituent_names"
    case convention = "convention"
    case conventions = "conventions"
    case licence = "licence"
    case licences = "licences"
    case provenance = "provenance"
    case setValidation = "set_validation"
    case stationValidation = "station_validation"
    case validRange = "valid_range"
    case equilibriumArgument = "equilibrium_argument"
    case equilibriumForYear = "equilibrium_for_year"
    case nodeFactor = "node_factor"
    case nodeFactorForYear = "node_factor_for_year"
    case raw = "raw"
    case releaseFiles = "release_files"
    case releaseMetadata = "release_metadata"
    case stationCount = "station_count"
    case tombstoneCount = "tombstone_count"
    case subordinateOffsets = "subordinate_offsets"
}

internal enum CanonicalAuxiliaryResult {
    case modelAccess(CanonicalMemberResult)
    case resultContext(CanonicalPredictionResult)
    case localTime(CanonicalLocalTimeResult)
}

internal typealias CanonicalBoundChecksums = CanonicalDigestMap

internal typealias CanonicalCacheBytes = Data

internal enum CanonicalCacheDocument {
    case streamIndex(CanonicalStreamIndex)
    case verifiedReceipt(CanonicalVerifiedReceipt)
    case pointerOrCatalogue(JSONValue)
}

internal enum CanonicalCacheInventoryResult {
    case cachedReleases([String])
    case prune([String])
}

internal enum CanonicalCanonicalErrorCode: String, CaseIterable {
    case invalidArgument = "invalid_argument"
    case network = "network"
    case releaseNotFound = "release_not_found"
    case offlineUnavailable = "offline_unavailable"
    case checksumMismatch = "checksum_mismatch"
    case unsupportedFormat = "unsupported_format"
    case readerTooOld = "reader_too_old"
    case invalidRelease = "invalid_release"
    case cache = "cache"
    case io = "io"
    case unsupported = "unsupported"
    case pinnedRelease = "pinned_release"
    case bufferTooSmall = "buffer_too_small"
    case fileExists = "file_exists"
    case notBuilt = "not_built"
    case stationNotFound = "station_not_found"
    case stationRemoved = "station_removed"
    case noConstants = "no_constants"
    case quantityMismatch = "quantity_mismatch"
    case unsupportedConvention = "unsupported_convention"
    case noAstroTable = "no_astro_table"
    case unsupportedConstituent = "unsupported_constituent"
    case timeOutOfRange = "time_out_of_range"
    case datumUnavailable = "datum_unavailable"
    case referenceUnavailable = "reference_unavailable"
    case extremesOnly = "extremes_only"
    case historicalOffsetsExcluded = "historical_offsets_excluded"
    case binNotFound = "bin_not_found"
    case localTimeUnavailable = "local_time_unavailable"
    case unknownTimeZone = "unknown_time_zone"
}

internal struct CanonicalCanonicalError {
    let code: CanonicalCanonicalErrorCode
    let structuredFields: JSONValue
    let cause: Error?
}

internal typealias CanonicalCanonicalResult = CanonicalMemberResult

internal typealias CanonicalCause = Error?

internal typealias CanonicalChangedBehaviors = [String]

internal typealias CanonicalChecksumBytes = Data

internal typealias CanonicalCitationStyle = String

internal typealias CanonicalCitationText = String

internal struct CanonicalClientAndRelease {
    let clientState: CanonicalClientState
    let loadedRelease: Release
}

internal struct CanonicalClientState {
    let currentRelease: Release
    let effectiveOptions: CanonicalEffectiveOptions
    let cacheState: CanonicalCacheState
    let lastError: JSONValue?
    let lastUpdateCheck: Double?
    let closed: Bool
}

internal typealias CanonicalClock = Double

internal struct CanonicalCommercialAdmission {
    let admitted: Bool
    let reason: String?
}

internal enum CanonicalCommercialBasis: String, CaseIterable {
    case strict = "strict"
    case asPublishedUpstream = "as_published_upstream"
}

internal typealias CanonicalCommercialOnly = Bool

internal typealias CanonicalComparedStationRow = JSONValue

internal typealias CanonicalCurrentCacheDirectory = URL

internal typealias CanonicalDestination = URL

internal enum CanonicalDirectCurrentResult {
    case currents(CurrentSeries)
    case currentEvents(CurrentEventList)
}

internal enum CanonicalDocumentKind: String, CaseIterable {
    case release = "release"
    case stationRow = "station_row"
    case pointer = "pointer"
    case catalogue = "catalogue"
    case cache = "cache"
}

internal typealias CanonicalDownloadResult = [String]

internal typealias CanonicalEffectiveRecommendation = ConstantSet?

internal typealias CanonicalEnvironment = [String: String]

internal struct CanonicalEvidenceBundle {
    let scenario: CanonicalScenario
    let expectedResult: JSONValue
    let actualProfileResults: JSONValue
    let redOutput: String
    let greenOutput: String
}

internal typealias CanonicalExpectedResult = JSONValue

internal typealias CanonicalExplicitOptions = CanonicalEffectiveOptions

internal typealias CanonicalFoldedHeightValues = HeightSeries

internal struct CanonicalFormatSelection {
    let formats: [String]
    let requiredFiles: CanonicalFileRows
}

internal typealias CanonicalHeightValues = HeightSeries

internal typealias CanonicalHeldRelease = Release

internal typealias CanonicalHeldReleaseResult = CanonicalMemberResult

internal struct CanonicalHistoricalAdmission {
    let admitted: Bool
    let reason: String?
}

internal enum CanonicalHistoricalPolicy: String, CaseIterable {
    case fallback = "fallback"
    case exclude = "exclude"
}

internal struct CanonicalHttpRequest {
    let url: String
    let conditionalEtag: String?
}

internal struct CanonicalHttpResponse {
    let statusCode: Int64
    let body: Data
    let etag: String?
    let requestUrl: String
}

internal struct CanonicalIdentityQueryVariant2 {
    let system: String
    let id: String
}

internal enum CanonicalIdentityQuery {
    case String(String)
    case variant2(CanonicalIdentityQueryVariant2)
}

internal typealias CanonicalIncludeFallback = Bool

internal typealias CanonicalIncludeFlagged = Bool

internal typealias CanonicalIncludeNoConstants = Bool

internal typealias CanonicalIndexEntry = CanonicalStreamIndexStation

internal typealias CanonicalIndexPresence = [String: Bool]

internal enum CanonicalInventoryAction: String, CaseIterable {
    case list = "list"
    case prune = "prune"
}

internal enum CanonicalIoKind: String, CaseIterable {
    case lock = "lock"
    case http = "http"
}

internal enum CanonicalIoOptions {
    case lock(CanonicalLockState)
    case http(CanonicalTransportOptions)
}

internal enum CanonicalIoRequest {
    case lock(CanonicalLockRequest)
    case http(CanonicalHttpRequest)
}

internal enum CanonicalIoResult {
    case lockOutcome(CanonicalLockOutcome)
    case httpResponse(CanonicalHttpResponse)
}

internal typealias CanonicalKeep = Int64

internal typealias CanonicalLifetimeAction = String

internal enum CanonicalLoadMode: String, CaseIterable {
    case eager = "eager"
    case stream = "stream"
}

internal typealias CanonicalLoadedRelease = Release

internal typealias CanonicalLocalTimeProfile = CanonicalHeightSeriesToLocalArguments

internal typealias CanonicalLocalTimeResult = CanonicalMemberResult

internal struct CanonicalLockOutcome {
    let acquired: Bool
    let token: String?
    let owned: Bool
}

internal enum CanonicalLockRequestOperation: String, CaseIterable {
    case take = "take"
    case nonblockingTake = "nonblocking_take"
    case release = "release"
    case delete = "delete"
    case heartbeat = "heartbeat"
    case ownershipCheck = "ownership_check"
}

internal struct CanonicalLockRequest {
    let directory: URL
    let operation: CanonicalLockRequestOperation
    let token: String?
}

internal typealias CanonicalLockedCacheState = CanonicalCacheState

internal typealias CanonicalMemberContract = CanonicalMemberID

internal typealias CanonicalMergedReceipt = CanonicalVerifiedReceipt

internal struct CanonicalMetadataRequest {
    let requestUrl: String
    let documentKind: String
}

internal enum CanonicalNativeProfile: String, CaseIterable {
    case python = "python"
    case ruby = "ruby"
    case typescriptNode = "typescript_node"
    case typescriptBrowser = "typescript_browser"
    case c = "c"
    case swift = "swift"
}

internal typealias CanonicalNativeResult = CanonicalMemberResult

internal typealias CanonicalOffsetCurrentResult = CurrentEventList

internal enum CanonicalOffsetTideResult {
    case heights(HeightSeries)
    case extremes(ExtremeList)
}

internal enum CanonicalOperation: String, CaseIterable {
    case astroTable = "astro_table"
    case attribution = "attribution"
    case cachedReleases = "cached_releases"
    case checkForUpdate = "check_for_update"
    case citation = "citation"
    case close = "close"
    case constantSet = "constant_set"
    case constantSets = "constant_sets"
    case constituent = "constituent"
    case constituentNames = "constituent_names"
    case constituents = "constituents"
    case convention = "convention"
    case conventions = "conventions"
    case currentEvents = "current_events"
    case currents = "currents"
    case datums = "datums"
    case download = "download"
    case equilibriumArgument = "equilibrium_argument"
    case equilibriumForYear = "equilibrium_for_year"
    case extremes = "extremes"
    case heights = "heights"
    case heightsAt = "heights_at"
    case holdRelease = "hold_release"
    case iterStations = "iter_stations"
    case lastError = "last_error"
    case latest = "latest"
    case licence = "licence"
    case licences = "licences"
    case loadedFrom = "loaded_from"
    case near = "near"
    case nearest = "nearest"
    case newerFormatMajor = "newer_format_major"
    case nodeFactor = "node_factor"
    case nodeFactorForYear = "node_factor_for_year"
    case open = "open"
    case provenance = "provenance"
    case prune = "prune"
    case ranges = "ranges"
    case raw = "raw"
    case recommendedSet = "recommended_set"
    case referenceStation = "reference_station"
    case releaseFiles = "release_files"
    case releaseMetadata = "release_metadata"
    case releases = "releases"
    case requireStation = "require_station"
    case search = "search"
    case setValidation = "set_validation"
    case station = "station"
    case stationByAlias = "station_by_alias"
    case stationCount = "station_count"
    case stationValidation = "station_validation"
    case stations = "stations"
    case stats = "stats"
    case subordinateOffsets = "subordinate_offsets"
    case subordinatesOf = "subordinates_of"
    case toLocal = "to_local"
    case tombstone = "tombstone"
    case tombstoneCount = "tombstone_count"
    case update = "update"
    case validRange = "valid_range"
    case verify = "verify"
}

internal typealias CanonicalOrderedConstantSets = [ConstantSet]

internal typealias CanonicalOrderedFailures = [CanonicalCanonicalError]

internal typealias CanonicalOrderedStationResults = [Station]

internal typealias CanonicalOrigin = UUID

internal typealias CanonicalOriginalRecommendation = ConstantSet?

internal typealias CanonicalOverwritePolicy = CanonicalClientDownloadArguments

internal typealias CanonicalOwnCurrentOffsets = JSONValue?

internal typealias CanonicalOwnOffset = SubordinateOffsets?

internal enum CanonicalParsedDocument {
    case stationRow(JSONValue)
    case release(JSONValue)
    case pointer(JSONValue)
    case catalogue(JSONValue)
    case cache(JSONValue)
}

internal typealias CanonicalPathRequest = String

internal typealias CanonicalPlatformDefaults = CanonicalEffectiveOptions

internal typealias CanonicalPointerDigests = CanonicalDigestMap

internal typealias CanonicalPredictionInstants = [Double]

internal enum CanonicalPredictionResult {
    case heights(HeightSeries)
    case extremes(ExtremeList)
    case currents(CurrentSeries)
    case currentEvents(CurrentEventList)
}

internal typealias CanonicalProjectionContract = CanonicalProjectionRules

internal struct CanonicalPublishedMetadata {
    let contributors: JSONValue
    let year: Int64
    let conceptDoi: String?
    let zenodoVersionDoi: String?
    let datasetUrl: String
}

internal struct CanonicalQualityAdmission {
    let admitted: Bool
    let reason: String?
}

internal typealias CanonicalQueryClientState = CanonicalClientState

internal enum CanonicalQueryKind: String, CaseIterable {
    case stations = "stations"
    case iterStations = "iter_stations"
    case search = "search"
    case near = "near"
    case nearest = "nearest"
}

internal typealias CanonicalRawFields = JSONValue

internal typealias CanonicalRawRecord = JSONValue

internal enum CanonicalRawRecordOrValidStation {
    case JsonValue(JSONValue)
    case Station(Station)
}

internal struct CanonicalReaderVersion {
    let major: Int64
    let minor: Int64
}

internal typealias CanonicalReferenceModel = CanonicalPredictionModel

internal typealias CanonicalReleaseCandidates = [String]

internal typealias CanonicalReleaseFiles = [FileInfo]

internal typealias CanonicalReleaseMetadata = JSONValue

internal typealias CanonicalReleaseOrigin = UUID

internal enum CanonicalReleaseRequestLatest: String, CaseIterable {
    case latest = "latest"
}

internal enum CanonicalReleaseRequest {
    case latest(CanonicalReleaseRequestLatest)
    case variant2(String)
}

internal typealias CanonicalReleaseStatistics = Stats

internal typealias CanonicalReleaseView = Release

internal typealias CanonicalRequestedDatum = String

internal typealias CanonicalRequiredFiles = CanonicalFileRows

internal typealias CanonicalRequiredLinks = CanonicalLinkTable

internal enum CanonicalResourceState {
    case clientState(CanonicalClientState)
    case Release(Release)
    case streamReader(CanonicalStreamReader)
}

internal enum CanonicalResourceStateOrError {
    case clientState(CanonicalClientState)
    case Release(Release)
    case streamReader(CanonicalStreamReader)
}

internal typealias CanonicalResultValues = CanonicalMemberResult

internal typealias CanonicalReviewReports = [String]

internal struct CanonicalScenario {
    let behaviorIds: [String]
    let input: JSONValue
    let expectedOutput: JSONValue
    let expectedError: CanonicalCanonicalError?
    let expectedState: JSONValue
}

internal struct CanonicalScenarioComparison {
    let accepted: Bool
    let mandatoryFindings: [String]
}

internal typealias CanonicalSelectedPredictionModel = CanonicalPredictionModel

internal typealias CanonicalSelectedReferencePath = CanonicalReferencePath

internal enum CanonicalSelectionKind: String, CaseIterable {
    case discovery = "discovery"
    case explicitPrediction = "explicit_prediction"
    case defaultPrediction = "default_prediction"
}

internal struct CanonicalSourceByteSpan {
    let offsetBytes: Int64
    let lengthBytes: Int64
}

internal typealias CanonicalSourceBytes = Data

internal struct CanonicalSourceFiles {
    let jsonl: URL
    let meta: URL
    let jsonlSha256: String
    let jsonlSize: Int64
    let metaSha256: String
    let metaSize: Int64
}

internal typealias CanonicalSourceRecord = JSONValue

internal typealias CanonicalSourceValues = CanonicalAuxiliaryValues

internal typealias CanonicalStation = Station

internal typealias CanonicalStationId = String

internal typealias CanonicalStationIndexEntry = CanonicalStreamIndexStation

internal typealias CanonicalStationOrTombstoneOrNull = CanonicalStationLookup

internal typealias CanonicalStationSets = [ConstantSet]

internal typealias CanonicalStationSourceRow = JSONValue

internal enum CanonicalStationSummary {
    case releaseStatistics(CanonicalReleaseStatistics)
    case orderedConstantSets(CanonicalOrderedConstantSets)
}

internal typealias CanonicalStep = Double

internal struct CanonicalStreamReader {
    let releaseView: Release
    let fileDescriptor: Int64
    let index: JSONValue
    let indexPresence: JSONValue
    let stationLru: JSONValue
    let closed: Bool
}

internal enum CanonicalSummaryKind: String, CaseIterable {
    case stats = "stats"
    case constantSets = "constant_sets"
}

internal struct CanonicalSummaryOptions {
    let originalRecommendation: ConstantSet?
    let commercialOnly: Bool
    let includeNoConstants: Bool
}

internal typealias CanonicalSuppliedIndex = CanonicalStreamIndex?

internal typealias CanonicalTideEvents = ExtremeList

internal typealias CanonicalTimeInputs = CanonicalArguments

internal typealias CanonicalTrustedCache = JSONValue?

internal struct CanonicalTrustedCachedPointerValue {
    let digests: CanonicalDigestMap
}

internal typealias CanonicalTrustedCachedPointer = CanonicalTrustedCachedPointerValue?

internal typealias CanonicalUnroundedCurrentEvents = [CanonicalUnroundedCurrentEvent]

internal typealias CanonicalUnroundedTideEvents = [CanonicalUnroundedTideEvent]

internal typealias CanonicalUpdateRequest = CanonicalMetadataRequest

internal typealias CanonicalUpdatedClientState = CanonicalClientState

internal enum CanonicalUsableCachedReleaseOrError {
    case usable(Release)
    case unavailable(CanonicalCanonicalError)
}

internal typealias CanonicalUtcInstant = Double

internal typealias CanonicalUtcResult = CanonicalMemberResult

internal typealias CanonicalValidStation = Station

internal typealias CanonicalValidatedArguments = CanonicalArguments

internal struct CanonicalValidatedMetadata {
    let document: JSONValue
    let selectedDatestamp: String
    let requestUrl: String
    let files: CanonicalFileRows
}

internal typealias CanonicalValidatedReleaseGraph = JSONValue

internal typealias CanonicalVerificationResult = Bool

internal typealias CanonicalVerifiedFileRows = CanonicalFileRows

internal typealias CanonicalWindowInputs = CanonicalArguments

internal enum CanonicalAuxiliaryMemberId: String, CaseIterable {
    case ClientOpen = "Client.open"
    case ClientRelease = "Client.release"
    case ClientLoadedFrom = "Client.loaded_from"
    case ClientLastError = "Client.last_error"
    case ClientReleases = "Client.releases"
    case ClientLatest = "Client.latest"
    case ClientCheckForUpdate = "Client.check_for_update"
    case ClientNewerFormatMajor = "Client.newer_format_major"
    case ClientUpdate = "Client.update"
    case ClientDownload = "Client.download"
    case ClientVerify = "Client.verify"
    case ClientCachedReleases = "Client.cached_releases"
    case ClientPrune = "Client.prune"
    case ReleaseDatestamp = "Release.datestamp"
    case ReleaseCreated = "Release.created"
    case ReleaseFormatVersion = "Release.format_version"
    case ReleaseZenodoVersionDoi = "Release.zenodo_version_doi"
    case ReleaseConceptDoi = "Release.concept_doi"
    case ReleaseSourceVersions = "Release.source_versions"
    case ReleaseBuildCommit = "Release.build_commit"
    case ReleaseChangelogUrl = "Release.changelog_url"
    case ReleaseFiles = "Release.files"
    case ReleaseConventions = "Release.conventions"
    case ReleaseConvention = "Release.convention"
    case ReleaseLicences = "Release.licences"
    case ReleaseLicence = "Release.licence"
    case ReleaseConstituentNames = "Release.constituent_names"
    case ReleaseStats = "Release.stats"
    case ReleaseStationCount = "Release.station_count"
    case ReleaseTombstoneCount = "Release.tombstone_count"
    case ReleaseCitation = "Release.citation"
    case ReleaseStation = "Release.station"
    case ReleaseRequireStation = "Release.require_station"
    case ReleaseTombstone = "Release.tombstone"
    case ReleaseStationByAlias = "Release.station_by_alias"
    case ReleaseStations = "Release.stations"
    case ReleaseIterStations = "Release.iter_stations"
    case ReleaseSearch = "Release.search"
    case ReleaseNear = "Release.near"
    case ReleaseNearest = "Release.nearest"
    case ReleaseReferenceStation = "Release.reference_station"
    case ReleaseSubordinatesOf = "Release.subordinates_of"
    case ReleaseAttribution = "Release.attribution"
    case ReleaseHeights = "Release.heights"
    case ReleaseHeightsAt = "Release.heights_at"
    case ReleaseExtremes = "Release.extremes"
    case ReleaseCurrents = "Release.currents"
    case ReleaseCurrentEvents = "Release.current_events"
    case ReleaseDatums = "Release.datums"
    case ReleaseRanges = "Release.ranges"
    case ReleaseAstroTable = "Release.astro_table"
    case ReleaseHistoricalOffsetsPolicy = "Release.historical_offsets_policy"
    case ReleaseInfoDatestamp = "ReleaseInfo.datestamp"
    case ReleaseInfoFormatVersion = "ReleaseInfo.format_version"
    case ReleaseInfoConceptDoi = "ReleaseInfo.concept_doi"
    case ReleaseInfoZenodoVersionDoi = "ReleaseInfo.zenodo_version_doi"
    case ReleaseInfoContentSha256 = "ReleaseInfo.content_sha256"
    case ReleaseInfoFiles = "ReleaseInfo.files"
    case FileInfoName = "FileInfo.name"
    case FileInfoUrl = "FileInfo.url"
    case FileInfoSize = "FileInfo.size"
    case FileInfoSha256 = "FileInfo.sha256"
    case StationStationId = "Station.station_id"
    case StationName = "Station.name"
    case StationCountry = "Station.country"
    case StationLat = "Station.lat"
    case StationLon = "Station.lon"
    case StationType = "Station.type"
    case StationKind = "Station.kind"
    case StationTimezone = "Station.timezone"
    case StationAliases = "Station.aliases"
    case StationStatus = "Station.status"
    case StationIsReference = "Station.is_reference"
    case StationIsSubordinate = "Station.is_subordinate"
    case StationIsTide = "Station.is_tide"
    case StationIsCurrent = "Station.is_current"
    case StationRecommendedSet = "Station.recommended_set"
    case StationConstantSets = "Station.constant_sets"
    case StationConstantSet = "Station.constant_set"
    case StationSubordinateOffsets = "Station.subordinate_offsets"
    case StationValidation = "Station.validation"
    case StationRaw = "Station.raw"
    case StationRecommendedIsFallback = "Station.recommended_is_fallback"
    case StationSourceRecords = "Station.source_records"
    case TombstoneStationId = "Tombstone.station_id"
    case TombstoneName = "Tombstone.name"
    case TombstoneStatus = "Tombstone.status"
    case TombstoneRemovedIn = "Tombstone.removed_in"
    case TombstoneRemovedReason = "Tombstone.removed_reason"
    case TombstoneMergedInto = "Tombstone.merged_into"
    case TombstoneDetail = "Tombstone.detail"
    case TombstoneRaw = "Tombstone.raw"
    case ConstantSetSetId = "ConstantSet.set_id"
    case ConstantSetSource = "ConstantSet.source"
    case ConstantSetSourceType = "ConstantSet.source_type"
    case ConstantSetQuantity = "ConstantSet.quantity"
    case ConstantSetSourceRecordId = "ConstantSet.source_record_id"
    case ConstantSetSourceVersion = "ConstantSet.source_version"
    case ConstantSetRecordSpan = "ConstantSet.record_span"
    case ConstantSetDatum = "ConstantSet.datum"
    case ConstantSetQcStatus = "ConstantSet.qc_status"
    case ConstantSetQcFlags = "ConstantSet.qc_flags"
    case ConstantSetDroppedConstituents = "ConstantSet.dropped_constituents"
    case ConstantSetTimeBase = "ConstantSet.time_base"
    case ConstantSetIsRecommended = "ConstantSet.is_recommended"
    case ConstantSetConvention = "ConstantSet.convention"
    case ConstantSetLicence = "ConstantSet.licence"
    case ConstantSetProvenance = "ConstantSet.provenance"
    case ConstantSetValidation = "ConstantSet.validation"
    case ConstantSetConstituents = "ConstantSet.constituents"
    case ConstantSetConstituent = "ConstantSet.constituent"
    case ConstantSetRaw = "ConstantSet.raw"
    case ConstantSetFallback = "ConstantSet.fallback"
    case ConstituentName = "Constituent.name"
    case ConstituentSourceName = "Constituent.source_name"
    case ConstituentDoodson = "Constituent.doodson"
    case ConstituentSpeedDegPerHour = "Constituent.speed_deg_per_hour"
    case ConstituentAmplitudeM = "Constituent.amplitude_m"
    case ConstituentPhaseDeg = "Constituent.phase_deg"
    case ConstituentAmpUncertaintyM = "Constituent.amp_uncertainty_m"
    case ConstituentPhaseUncertaintyDeg = "Constituent.phase_uncertainty_deg"
    case ConstituentKeptReason = "Constituent.kept_reason"
    case ConstituentRaw = "Constituent.raw"
    case ConventionConventionId = "Convention.convention_id"
    case ConventionPhaseReference = "Convention.phase_reference"
    case ConventionUtcOffsetHours = "Convention.utc_offset_hours"
    case ConventionV0Model = "Convention.v0_model"
    case ConventionNodalHandling = "Convention.nodal_handling"
    case ConventionNodalFormulaIds = "Convention.nodal_formula_ids"
    case ConventionConstituentTableVersion = "Convention.constituent_table_version"
    case ConventionTablesSha256 = "Convention.tables_sha256"
    case ConventionCanary = "Convention.canary"
    case ConventionRaw = "Convention.raw"
    case LicenceLicenceId = "Licence.licence_id"
    case LicenceSpdx = "Licence.spdx"
    case LicenceProvider = "Licence.provider"
    case LicenceCitation = "Licence.citation"
    case LicenceAttribution = "Licence.attribution"
    case LicenceUrl = "Licence.url"
    case LicenceCommercialUse = "Licence.commercial_use"
    case LicenceRestriction = "Licence.restriction"
    case LicenceTermsUrl = "Licence.terms_url"
    case LicenceRaw = "Licence.raw"
    case ProvenanceAdapterVersion = "Provenance.adapter_version"
    case ProvenanceInputSha256 = "Provenance.input_sha256"
    case ProvenanceSelectionReason = "Provenance.selection_reason"
    case ProvenanceDecision = "Provenance.decision"
    case ProvenanceBuild = "Provenance.build"
    case ProvenanceCarriedFromRelease = "Provenance.carried_from_release"
    case ProvenanceRaw = "Provenance.raw"
    case ProvenanceBuildBuildCommit = "ProvenanceBuild.build_commit"
    case ProvenanceBuildBuiltAt = "ProvenanceBuild.built_at"
    case ProvenanceBuildFetchedAt = "ProvenanceBuild.fetched_at"
    case ProvenanceBuildRunId = "ProvenanceBuild.run_id"
    case ProvenanceBuildToolVersions = "ProvenanceBuild.tool_versions"
    case TimeBaseCode = "TimeBase.code"
    case TimeBaseReason = "TimeBase.reason"
    case TimeBaseDeclared = "TimeBase.declared"
    case TimeBasePublished = "TimeBase.published"
    case TimeBaseCorrection = "TimeBase.correction"
    case TimeBaseMonthsDropped = "TimeBase.months_dropped"
    case TimeBaseDecidedIn = "TimeBase.decided_in"
    case TimeBaseDecidedBuildCommit = "TimeBase.decided_build_commit"
    case TimeBaseEvidence = "TimeBase.evidence"
    case QcFlagFlag = "QcFlag.flag"
    case QcFlagReason = "QcFlag.reason"
    case QcFlagValues = "QcFlag.values"
    case DroppedConstituentName = "DroppedConstituent.name"
    case DroppedConstituentDroppedReason = "DroppedConstituent.dropped_reason"
    case DroppedConstituentDetail = "DroppedConstituent.detail"
    case ValidationSetId = "Validation.set_id"
    case ValidationReferenceSource = "Validation.reference_source"
    case ValidationReferenceStation = "Validation.reference_station"
    case ValidationReferenceDistanceKm = "Validation.reference_distance_km"
    case ValidationWindow = "Validation.window"
    case ValidationTimeMaeMin = "Validation.time_mae_min"
    case ValidationTimeP95Min = "Validation.time_p95_min"
    case ValidationTimeBiasMin = "Validation.time_bias_min"
    case ValidationHeightMaeM = "Validation.height_mae_m"
    case ValidationRangeErrorM = "Validation.range_error_m"
    case ValidationMissedEvents = "Validation.missed_events"
    case ValidationExtraEvents = "Validation.extra_events"
    case ValidationPreviousRelease = "Validation.previous_release"
    case SubordinateOffsetsReferenceStationId = "SubordinateOffsets.reference_station_id"
    case SubordinateOffsetsTimeOffsetHighMin = "SubordinateOffsets.time_offset_high_min"
    case SubordinateOffsetsTimeOffsetLowMin = "SubordinateOffsets.time_offset_low_min"
    case SubordinateOffsetsHeightOffsetHigh = "SubordinateOffsets.height_offset_high"
    case SubordinateOffsetsHeightOffsetLow = "SubordinateOffsets.height_offset_low"
    case SubordinateOffsetsHeightAdjustedType = "SubordinateOffsets.height_adjusted_type"
    case SubordinateOffsetsLicenceId = "SubordinateOffsets.licence_id"
    case SubordinateOffsetsOffsetId = "SubordinateOffsets.offset_id"
    case SubordinateOffsetsSource = "SubordinateOffsets.source"
    case SubordinateOffsetsSourceType = "SubordinateOffsets.source_type"
    case SubordinateOffsetsSourceVersion = "SubordinateOffsets.source_version"
    case SubordinateOffsetsSourceRecordId = "SubordinateOffsets.source_record_id"
    case SubordinateOffsetsQcStatus = "SubordinateOffsets.qc_status"
    case SubordinateOffsetsQcFlags = "SubordinateOffsets.qc_flags"
    case SubordinateOffsetsFallback = "SubordinateOffsets.fallback"
    case SubordinateOffsetsVintage = "SubordinateOffsets.vintage"
    case SubordinateOffsetsProvenance = "SubordinateOffsets.provenance"
    case NearbyStation = "Nearby.station"
    case NearbyDistanceKm = "Nearby.distance_km"
    case UpdateResultUpdated = "UpdateResult.updated"
    case UpdateResultFrom = "UpdateResult.from"
    case UpdateResultTo = "UpdateResult.to"
    case RecordSpanStart = "RecordSpan.start"
    case RecordSpanEnd = "RecordSpan.end"
    case RecordSpanGoodSamples = "RecordSpan.good_samples"
    case DatumMslOffsetM = "Datum.msl_offset_m"
    case DatumNamed = "Datum.named"
    case StatsType = "Stats.type"
    case StatsKind = "Stats.kind"
    case StatsCountry = "Stats.country"
    case StatsSource = "Stats.source"
    case StatsQcStatus = "Stats.qc_status"
    case AstroTableEquilibriumArgument = "AstroTable.equilibrium_argument"
    case AstroTableNodeFactor = "AstroTable.node_factor"
    case AstroTableEquilibriumForYear = "AstroTable.equilibrium_for_year"
    case AstroTableNodeFactorForYear = "AstroTable.node_factor_for_year"
    case AstroTableValidRange = "AstroTable.valid_range"
    case HeightPointTime = "HeightPoint.time"
    case HeightPointHeightM = "HeightPoint.height_m"
    case HeightPointLocalTime = "HeightPoint.local_time"
    case HeightPointUtcOffsetS = "HeightPoint.utc_offset_s"
    case HeightPointLocalDatetime = "HeightPoint.local_datetime"
    case HeightPointLocalTimeObject = "HeightPoint.local_time_object"
    case ExtremeTime = "Extreme.time"
    case ExtremeType = "Extreme.type"
    case ExtremeHeightM = "Extreme.height_m"
    case ExtremeLocalTime = "Extreme.local_time"
    case ExtremeUtcOffsetS = "Extreme.utc_offset_s"
    case ExtremeLocalDatetime = "Extreme.local_datetime"
    case ExtremeLocalTimeObject = "Extreme.local_time_object"
    case CurrentPointTime = "CurrentPoint.time"
    case CurrentPointVelocityMajorMs = "CurrentPoint.velocity_major_ms"
    case CurrentPointVelocityMinorMs = "CurrentPoint.velocity_minor_ms"
    case CurrentPointSpeedMs = "CurrentPoint.speed_ms"
    case CurrentPointDirectionDeg = "CurrentPoint.direction_deg"
    case CurrentPointLocalTime = "CurrentPoint.local_time"
    case CurrentPointUtcOffsetS = "CurrentPoint.utc_offset_s"
    case CurrentPointLocalDatetime = "CurrentPoint.local_datetime"
    case CurrentPointLocalTimeObject = "CurrentPoint.local_time_object"
    case CurrentEventTime = "CurrentEvent.time"
    case CurrentEventType = "CurrentEvent.type"
    case CurrentEventVelocityMs = "CurrentEvent.velocity_ms"
    case CurrentEventDirectionDeg = "CurrentEvent.direction_deg"
    case CurrentEventLocalTime = "CurrentEvent.local_time"
    case CurrentEventUtcOffsetS = "CurrentEvent.utc_offset_s"
    case CurrentEventLocalDatetime = "CurrentEvent.local_datetime"
    case CurrentEventLocalTimeObject = "CurrentEvent.local_time_object"
    case HeightSeriesItems = "HeightSeries.items"
    case HeightSeriesStationId = "HeightSeries.station_id"
    case HeightSeriesTimezone = "HeightSeries.timezone"
    case HeightSeriesMethod = "HeightSeries.method"
    case HeightSeriesSetId = "HeightSeries.set_id"
    case HeightSeriesConventionId = "HeightSeries.convention_id"
    case HeightSeriesAstroTableId = "HeightSeries.astro_table_id"
    case HeightSeriesReferenceStationId = "HeightSeries.reference_station_id"
    case HeightSeriesReferenceBin = "HeightSeries.reference_bin"
    case HeightSeriesDatum = "HeightSeries.datum"
    case HeightSeriesDatumName = "HeightSeries.datum_name"
    case HeightSeriesDatumKind = "HeightSeries.datum_kind"
    case HeightSeriesDatumUncertaintyM = "HeightSeries.datum_uncertainty_m"
    case HeightSeriesTz = "HeightSeries.tz"
    case HeightSeriesTzVersion = "HeightSeries.tz_version"
    case HeightSeriesRelease = "HeightSeries.release"
    case HeightSeriesAlgorithm = "HeightSeries.algorithm"
    case HeightSeriesToLocal = "HeightSeries.to_local"
    case HeightSeriesOffsetId = "HeightSeries.offset_id"
    case HeightSeriesOffsetSource = "HeightSeries.offset_source"
    case HeightSeriesOffsetSourceVersion = "HeightSeries.offset_source_version"
    case HeightSeriesHistoricalOffsets = "HeightSeries.historical_offsets"
    case HeightSeriesCurrentValidity = "HeightSeries.current_validity"
    case HeightSeriesCurrentAccuracy = "HeightSeries.current_accuracy"
    case HeightSeriesReferenceSetId = "HeightSeries.reference_set_id"
    case HeightSeriesReferenceSourceVersion = "HeightSeries.reference_source_version"
    case HeightSeriesReference2020Equivalence = "HeightSeries.reference_2020_equivalence"
    case HeightSeriesSourceNote = "HeightSeries.source_note"
    case ExtremeListItems = "ExtremeList.items"
    case ExtremeListStationId = "ExtremeList.station_id"
    case ExtremeListTimezone = "ExtremeList.timezone"
    case ExtremeListMethod = "ExtremeList.method"
    case ExtremeListSetId = "ExtremeList.set_id"
    case ExtremeListConventionId = "ExtremeList.convention_id"
    case ExtremeListAstroTableId = "ExtremeList.astro_table_id"
    case ExtremeListReferenceStationId = "ExtremeList.reference_station_id"
    case ExtremeListReferenceBin = "ExtremeList.reference_bin"
    case ExtremeListDatum = "ExtremeList.datum"
    case ExtremeListDatumName = "ExtremeList.datum_name"
    case ExtremeListDatumKind = "ExtremeList.datum_kind"
    case ExtremeListDatumUncertaintyM = "ExtremeList.datum_uncertainty_m"
    case ExtremeListTz = "ExtremeList.tz"
    case ExtremeListTzVersion = "ExtremeList.tz_version"
    case ExtremeListRelease = "ExtremeList.release"
    case ExtremeListAlgorithm = "ExtremeList.algorithm"
    case ExtremeListToLocal = "ExtremeList.to_local"
    case ExtremeListOffsetId = "ExtremeList.offset_id"
    case ExtremeListOffsetSource = "ExtremeList.offset_source"
    case ExtremeListOffsetSourceVersion = "ExtremeList.offset_source_version"
    case ExtremeListHistoricalOffsets = "ExtremeList.historical_offsets"
    case ExtremeListCurrentValidity = "ExtremeList.current_validity"
    case ExtremeListCurrentAccuracy = "ExtremeList.current_accuracy"
    case ExtremeListReferenceSetId = "ExtremeList.reference_set_id"
    case ExtremeListReferenceSourceVersion = "ExtremeList.reference_source_version"
    case ExtremeListReference2020Equivalence = "ExtremeList.reference_2020_equivalence"
    case ExtremeListSourceNote = "ExtremeList.source_note"
    case CurrentSeriesItems = "CurrentSeries.items"
    case CurrentSeriesStationId = "CurrentSeries.station_id"
    case CurrentSeriesTimezone = "CurrentSeries.timezone"
    case CurrentSeriesMethod = "CurrentSeries.method"
    case CurrentSeriesSetId = "CurrentSeries.set_id"
    case CurrentSeriesConventionId = "CurrentSeries.convention_id"
    case CurrentSeriesAstroTableId = "CurrentSeries.astro_table_id"
    case CurrentSeriesReferenceStationId = "CurrentSeries.reference_station_id"
    case CurrentSeriesReferenceBin = "CurrentSeries.reference_bin"
    case CurrentSeriesDatum = "CurrentSeries.datum"
    case CurrentSeriesDatumName = "CurrentSeries.datum_name"
    case CurrentSeriesDatumKind = "CurrentSeries.datum_kind"
    case CurrentSeriesDatumUncertaintyM = "CurrentSeries.datum_uncertainty_m"
    case CurrentSeriesBinNumber = "CurrentSeries.bin_number"
    case CurrentSeriesTz = "CurrentSeries.tz"
    case CurrentSeriesTzVersion = "CurrentSeries.tz_version"
    case CurrentSeriesRelease = "CurrentSeries.release"
    case CurrentSeriesAlgorithm = "CurrentSeries.algorithm"
    case CurrentSeriesToLocal = "CurrentSeries.to_local"
    case CurrentEventListItems = "CurrentEventList.items"
    case CurrentEventListStationId = "CurrentEventList.station_id"
    case CurrentEventListTimezone = "CurrentEventList.timezone"
    case CurrentEventListMethod = "CurrentEventList.method"
    case CurrentEventListSetId = "CurrentEventList.set_id"
    case CurrentEventListConventionId = "CurrentEventList.convention_id"
    case CurrentEventListAstroTableId = "CurrentEventList.astro_table_id"
    case CurrentEventListReferenceStationId = "CurrentEventList.reference_station_id"
    case CurrentEventListReferenceBin = "CurrentEventList.reference_bin"
    case CurrentEventListDatum = "CurrentEventList.datum"
    case CurrentEventListDatumName = "CurrentEventList.datum_name"
    case CurrentEventListDatumKind = "CurrentEventList.datum_kind"
    case CurrentEventListDatumUncertaintyM = "CurrentEventList.datum_uncertainty_m"
    case CurrentEventListBinNumber = "CurrentEventList.bin_number"
    case CurrentEventListOmittedEventTypes = "CurrentEventList.omitted_event_types"
    case CurrentEventListTz = "CurrentEventList.tz"
    case CurrentEventListTzVersion = "CurrentEventList.tz_version"
    case CurrentEventListRelease = "CurrentEventList.release"
    case CurrentEventListAlgorithm = "CurrentEventList.algorithm"
    case CurrentEventListToLocal = "CurrentEventList.to_local"
    case DatumInfoSetId = "DatumInfo.set_id"
    case DatumInfoZero = "DatumInfo.zero"
    case DatumInfoZeroName = "DatumInfo.zero_name"
    case DatumInfoChartDatum = "DatumInfo.chart_datum"
    case DatumInfoMslOffsetM = "DatumInfo.msl_offset_m"
    case DatumInfoLevels = "DatumInfo.levels"
    case DatumLevelKey = "DatumLevel.key"
    case DatumLevelValueM = "DatumLevel.value_m"
    case DatumLevelAboveChartM = "DatumLevel.above_chart_m"
    case DatumLevelKind = "DatumLevel.kind"
    case DatumLevelMethod = "DatumLevel.method"
    case DatumLevelSourceName = "DatumLevel.source_name"
    case DatumLevelEpoch = "DatumLevel.epoch"
    case DatumLevelDataSpan = "DatumLevel.data_span"
    case DatumLevelControlStationId = "DatumLevel.control_station_id"
    case DatumLevelControlSetId = "DatumLevel.control_set_id"
    case DatumLevelControlSourceId = "DatumLevel.control_source_id"
    case DatumLevelUncertaintyM = "DatumLevel.uncertainty_m"
    case DatumLevelUncertaintyBasis = "DatumLevel.uncertainty_basis"
    case DatumLevelFlags = "DatumLevel.flags"
    case RangesMn = "Ranges.mn"
    case RangesGt = "Ranges.gt"
    case RangesDhq = "Ranges.dhq"
    case RangesDlq = "Ranges.dlq"
    case FallbackReason = "Fallback.reason"
    case FallbackBasis = "Fallback.basis"
    case FallbackOtcFinding = "Fallback.otc_finding"
    case FallbackPreferredSetId = "Fallback.preferred_set_id"
    case FallbackRaw = "Fallback.raw"
    case SourceRecordSource = "SourceRecord.source"
    case SourceRecordSourceVersion = "SourceRecord.source_version"
    case SourceRecordSourceRecordId = "SourceRecord.source_record_id"
    case SourceRecordRole = "SourceRecord.role"
    case SourceRecordDisposition = "SourceRecord.disposition"
    case SourceRecordDetail = "SourceRecord.detail"
    case SourceRecordLicenceId = "SourceRecord.licence_id"
    case SourceRecordUpstreamLicenceId = "SourceRecord.upstream_licence_id"
    case SourceRecordPublishedSetIds = "SourceRecord.published_set_ids"
    case SourceRecordProvenance = "SourceRecord.provenance"
    case SourceRecordOriginalMetadata = "SourceRecord.original_metadata"
    case SourceRecordOriginalHarmonics = "SourceRecord.original_harmonics"
    case SourceRecordLicence = "SourceRecord.licence"
    case SourceRecordUpstreamLicence = "SourceRecord.upstream_licence"
    case SourceRecordRaw = "SourceRecord.raw"
    case HistoricalOffsetVintagePublicationYear = "HistoricalOffsetVintage.publication_year"
    case HistoricalOffsetVintageSourceLifecycle = "HistoricalOffsetVintage.source_lifecycle"
    case HistoricalOffsetVintageRemovalEvents = "HistoricalOffsetVintage.removal_events"
    case HistoricalOffsetVintageCurrentValidity = "HistoricalOffsetVintage.current_validity"
    case HistoricalOffsetVintageCurrentAccuracy = "HistoricalOffsetVintage.current_accuracy"
    case HistoricalOffsetVintageReference2020Equivalence = "HistoricalOffsetVintage.reference_2020_equivalence"
    case HistoricalOffsetVintageReference2020EquivalenceSha256 = "HistoricalOffsetVintage.reference_2020_equivalence_sha256"
    case HistoricalOffsetProvenanceSourceManifestSha256 = "HistoricalOffsetProvenance.source_manifest_sha256"
    case HistoricalOffsetProvenanceInputSha256 = "HistoricalOffsetProvenance.input_sha256"
    case HistoricalOffsetProvenanceBook = "HistoricalOffsetProvenance.book"
    case HistoricalOffsetProvenanceAnnualTableRow = "HistoricalOffsetProvenance.annual_table_row"
    case HistoricalOffsetProvenancePrintedPage = "HistoricalOffsetProvenance.printed_page"
    case HistoricalOffsetProvenancePdfPage = "HistoricalOffsetProvenance.pdf_page"
    case HistoricalOffsetProvenanceRawRowText = "HistoricalOffsetProvenance.raw_row_text"
    case HistoricalOffsetProvenanceRawValuesJson = "HistoricalOffsetProvenance.raw_values_json"
    case HistoricalOffsetProvenanceIdCrosswalk = "HistoricalOffsetProvenance.id_crosswalk"
    case HistoricalOffsetProvenanceReferenceBinding = "HistoricalOffsetProvenance.reference_binding"
    case HistoricalOffsetProvenanceAcceptanceReportSha256 = "HistoricalOffsetProvenance.acceptance_report_sha256"
}

internal enum CanonicalModelType: String, CaseIterable {
    case Client = "Client"
    case Release = "Release"
    case ReleaseInfo = "ReleaseInfo"
    case FileInfo = "FileInfo"
    case Station = "Station"
    case Tombstone = "Tombstone"
    case ConstantSet = "ConstantSet"
    case Constituent = "Constituent"
    case Convention = "Convention"
    case Licence = "Licence"
    case Provenance = "Provenance"
    case ProvenanceBuild = "ProvenanceBuild"
    case TimeBase = "TimeBase"
    case QcFlag = "QcFlag"
    case DroppedConstituent = "DroppedConstituent"
    case Validation = "Validation"
    case SubordinateOffsets = "SubordinateOffsets"
    case Nearby = "Nearby"
    case UpdateResult = "UpdateResult"
    case RecordSpan = "RecordSpan"
    case Datum = "Datum"
    case Stats = "Stats"
    case AstroTable = "AstroTable"
    case HeightPoint = "HeightPoint"
    case Extreme = "Extreme"
    case CurrentPoint = "CurrentPoint"
    case CurrentEvent = "CurrentEvent"
    case HeightSeries = "HeightSeries"
    case ExtremeList = "ExtremeList"
    case CurrentSeries = "CurrentSeries"
    case CurrentEventList = "CurrentEventList"
    case DatumInfo = "DatumInfo"
    case DatumLevel = "DatumLevel"
    case Ranges = "Ranges"
    case Fallback = "Fallback"
    case SourceRecord = "SourceRecord"
    case HistoricalOffsetVintage = "HistoricalOffsetVintage"
    case HistoricalOffsetProvenance = "HistoricalOffsetProvenance"
}

internal enum CanonicalCurrentOperation: String, CaseIterable {
    case currents = "currents"
    case currentEvents = "current_events"
}
