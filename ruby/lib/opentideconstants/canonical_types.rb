# Private construction records. No source acquisition or behavior bodies.
class OpenTideConstants
    module CanonicalTypes
        # Native checksum parsing reports the actual sidecar filename. The
        # String remains the original bytes, with only that source context.
        class ChecksumBytes < String
            attr_reader :source
            def initialize(bytes, source:)
                super(bytes)
                @source = source
                freeze
            end
        end

        class Origin
            def initialize()
                freeze
            end
        end

        class AbsentValue
            def initialize()
                freeze
            end
        end

        class NoValue
            def initialize()
                freeze
            end
        end

        class RequiredLink
            attr_reader :source_model, :source_field, :target_model, :target_field
            def initialize(source_model:, source_field:, target_model:, target_field:)
                @source_model = source_model
                @source_field = source_field
                @target_model = target_model
                @target_field = target_field
                freeze
            end
        end

        class FieldContract
            attr_reader :member_id, :native_type, :nullable
            def initialize(member_id:, native_type:, nullable:)
                @member_id = member_id
                @native_type = native_type
                @nullable = nullable
                freeze
            end
        end

        class PreparedClientFields
            attr_reader :requested, :mode, :on_network_error, :offline, :auto_update, :verify_on_open, :commercial_only, :commercial_basis, :historical_offsets_policy, :update_interval, :base_url, :cache_dir, :logger, :http, :lock, :closed, :last_error, :newer_format_major, :file, :loaded, :release, :loaded_from, :last_check, :cache
            def initialize(requested:, mode:, on_network_error:, offline:, auto_update:, verify_on_open:, commercial_only:, commercial_basis:, historical_offsets_policy:, update_interval:, base_url:, cache_dir:, logger:, http:, lock:, closed:, last_error:, newer_format_major:, file:, loaded:, release:, loaded_from:, last_check:, cache: nil)
                @requested = requested
                @mode = mode
                @on_network_error = on_network_error
                @offline = offline
                @auto_update = auto_update
                @verify_on_open = verify_on_open
                @commercial_only = commercial_only
                @commercial_basis = commercial_basis
                @historical_offsets_policy = historical_offsets_policy
                @update_interval = update_interval
                @base_url = base_url
                @cache_dir = cache_dir
                @logger = logger
                @http = http
                @lock = lock
                @closed = closed
                @last_error = last_error
                @newer_format_major = newer_format_major
                @file = file
                @loaded = loaded
                @release = release
                @loaded_from = loaded_from
                @last_check = last_check
                @cache = cache
                freeze
            end
        end

        class PreparedReleaseFields
            attr_reader :mode, :commercial_only, :commercial_basis, :historical_offsets_policy, :meta, :logger, :io, :on_bad_index, :io_lock, :station_cache, :station_cache_lock, :state, :files, :checks, :datestamp, :created, :format_version, :concept_doi, :zenodo_version_doi, :source_versions, :build_commit, :changelog_url, :conventions, :licences, :convention_by_id, :licence_by_id, :set_ids, :set_sources, :set_qc, :aliases, :by_id, :entries, :tombstones, :tomb_pos, :tomb_by_id, :constituent_names, :subordinates, :raws
            def initialize(mode:, commercial_only:, commercial_basis:, historical_offsets_policy:, meta:, logger:, io:, on_bad_index:, io_lock:, station_cache:, station_cache_lock:, state:, files:, checks:, datestamp:, created:, format_version:, concept_doi:, zenodo_version_doi:, source_versions:, build_commit:, changelog_url:, conventions:, licences:, convention_by_id:, licence_by_id:, set_ids:, set_sources:, set_qc:, aliases:, by_id:, entries:, tombstones:, tomb_pos:, tomb_by_id:, constituent_names:, subordinates:, raws:)
                @mode = mode
                @commercial_only = commercial_only
                @commercial_basis = commercial_basis
                @historical_offsets_policy = historical_offsets_policy
                @meta = meta
                @logger = logger
                @io = io
                @on_bad_index = on_bad_index
                @io_lock = io_lock
                @station_cache = station_cache
                @station_cache_lock = station_cache_lock
                @state = state
                @files = files
                @checks = checks
                @datestamp = datestamp
                @created = created
                @format_version = format_version
                @concept_doi = concept_doi
                @zenodo_version_doi = zenodo_version_doi
                @source_versions = source_versions
                @build_commit = build_commit
                @changelog_url = changelog_url
                @conventions = conventions
                @licences = licences
                @convention_by_id = convention_by_id
                @licence_by_id = licence_by_id
                @set_ids = set_ids
                @set_sources = set_sources
                @set_qc = set_qc
                @aliases = aliases
                @by_id = by_id
                @entries = entries
                @tombstones = tombstones
                @tomb_pos = tomb_pos
                @tomb_by_id = tomb_by_id
                @constituent_names = constituent_names
                @subordinates = subordinates
                @raws = raws
                freeze
            end
        end

        class FieldContracts
            attr_reader :model_type, :fields, :native_context
            def initialize(model_type:, fields:, native_context: nil)
                @model_type = model_type
                @fields = fields
                @native_context = native_context
                freeze
            end
        end

        class MemberValidationContext
            attr_reader :member_id, :native_profile, :native_receiver, :prepared_receiver, :prepared_station, :prepared_station_request, :prepared_row, :prepared_row_name, :prepared_attribution_request, :prepared_attribution_steps
            def initialize(member_id:, native_profile:, native_receiver:, prepared_receiver: nil, prepared_station: nil, prepared_station_request: ABSENT, prepared_row: nil, prepared_row_name: ABSENT, prepared_attribution_request: ABSENT, prepared_attribution_steps: [])
                @member_id = member_id
                @native_profile = native_profile
                @native_receiver = native_receiver
                @prepared_receiver = prepared_receiver
                @prepared_station = prepared_station
                @prepared_station_request = prepared_station_request
                @prepared_row = prepared_row
                @prepared_row_name = prepared_row_name
                @prepared_attribution_request = prepared_attribution_request
                @prepared_attribution_steps = prepared_attribution_steps.freeze
                freeze
            end
        end

        class PreparedAttributionStep
            attr_reader :station, :entry, :error
            def initialize(station:, entry:, error:)
                @station = station
                @entry = entry
                @error = error
                freeze
            end
        end

        class StationLookupActive
            attr_reader :station
            def initialize(station:)
                @station = station
                freeze
            end
        end

        class StationLookupRemoved
            attr_reader :tombstone
            def initialize(tombstone:)
                @tombstone = tombstone
                freeze
            end
        end

        class StationLookupAbsent
            def initialize()
                freeze
            end
        end

        class PredictionModel
            attr_reader :station, :release_view, :constant_set, :convention, :astro_table, :required_constituents, :reference_bin, :mean_term, :datum_source, :native_context, :selection_context, :prepared_datum, :prepared_current_request
            def initialize(station:, release_view:, constant_set:, convention:, astro_table:, required_constituents:, reference_bin:, mean_term:, datum_source:, native_context: nil, selection_context: nil, prepared_datum: ABSENT, prepared_current_request: ABSENT)
                @station = station
                @release_view = release_view
                @constant_set = constant_set
                @convention = convention
                @astro_table = astro_table
                @required_constituents = required_constituents
                @reference_bin = reference_bin
                @mean_term = mean_term
                @datum_source = datum_source
                @native_context = native_context
                @selection_context = selection_context
                @prepared_datum = prepared_datum
                @prepared_current_request = prepared_current_request
                freeze
            end
        end

        class PredictionWindow
            attr_reader :start, :stop, :step, :instants
            def initialize(start:, stop:, step:, instants:)
                @start = start
                @stop = stop
                @step = step
                @instants = instants
                freeze
            end
        end

        class ArgsClientOpenSelected
            attr_reader :member_id, :offline, :base_url, :timeout, :proxy, :ca_file, :user_agent
            def initialize(member_id:, offline:, base_url:, timeout:, proxy:, ca_file:, user_agent:)
                @member_id = member_id
                @offline = offline
                @base_url = base_url
                @timeout = timeout
                @proxy = proxy
                @ca_file = ca_file
                @user_agent = user_agent
                freeze
            end
        end

        class ArgsClientOpen
            attr_reader :member_id, :release, :file, :cache_dir, :offline, :mode, :base_url, :timeout, :proxy, :ca_file, :user_agent, :on_network_error, :auto_update, :update_interval, :logger, :verify_on_open, :commercial_only, :commercial_basis, :historical_offsets_policy
            def initialize(member_id:, release:, file:, cache_dir:, offline:, mode:, base_url:, timeout:, proxy:, ca_file:, user_agent:, on_network_error:, auto_update:, update_interval:, logger:, verify_on_open:, commercial_only:, commercial_basis:, historical_offsets_policy:)
                @member_id = member_id
                @release = release
                @file = file
                @cache_dir = cache_dir
                @offline = offline
                @mode = mode
                @base_url = base_url
                @timeout = timeout
                @proxy = proxy
                @ca_file = ca_file
                @user_agent = user_agent
                @on_network_error = on_network_error
                @auto_update = auto_update
                @update_interval = update_interval
                @logger = logger
                @verify_on_open = verify_on_open
                @commercial_only = commercial_only
                @commercial_basis = commercial_basis
                @historical_offsets_policy = historical_offsets_policy
                freeze
            end
        end

        class LockState
            attr_reader :cache_root, :owner, :held_token
            def initialize(cache_root:, owner:, held_token:)
                @cache_root = cache_root
                @owner = owner
                @held_token = held_token
                freeze
            end
        end

        class CacheState
            attr_reader :cache_root, :release_candidates, :pointer_cache, :lock_state
            def initialize(cache_root:, release_candidates:, pointer_cache:, lock_state:)
                @cache_root = cache_root
                @release_candidates = release_candidates
                @pointer_cache = pointer_cache
                @lock_state = lock_state
                freeze
            end
        end

        class ReleaseDescriptor
            attr_reader :datestamp, :files, :checksum_bytes, :pointer_digests, :required_file_request, :metadata
            def initialize(datestamp:, files:, checksum_bytes:, pointer_digests:, required_file_request:, metadata:)
                @datestamp = datestamp
                @files = files
                @checksum_bytes = checksum_bytes
                @pointer_digests = pointer_digests
                @required_file_request = required_file_request
                @metadata = metadata
                freeze
            end
        end

        class ReferencePath
            attr_reader :station, :release_view, :constant_set, :own_offset, :reference_bin
            def initialize(station:, release_view:, constant_set:, own_offset:, reference_bin:)
                @station = station
                @release_view = release_view
                @constant_set = constant_set
                @own_offset = own_offset
                @reference_bin = reference_bin
                freeze
            end
        end

        class CandidatePathDirect
            attr_reader :station, :constant_set, :release_view
            def initialize(station:, constant_set:, release_view:)
                @station = station
                @constant_set = constant_set
                @release_view = release_view
                freeze
            end
        end

        class CandidatePathTideOffset
            attr_reader :reference_path, :own_offset
            def initialize(reference_path:, own_offset:)
                @reference_path = reference_path
                @own_offset = own_offset
                freeze
            end
        end

        class CandidatePathCurrentOffset
            attr_reader :reference_path, :own_current_offset
            def initialize(reference_path:, own_current_offset:)
                @reference_path = reference_path
                @own_current_offset = own_current_offset
                freeze
            end
        end

        class ArgsReleaseHeightsSelected
            attr_reader :member_id, :datum, :set_id, :offset_id
            def initialize(member_id:, datum:, set_id:, offset_id:)
                @member_id = member_id
                @datum = datum
                @set_id = set_id
                @offset_id = offset_id
                freeze
            end
        end

        class ArgsReleaseExtremesSelected
            attr_reader :member_id, :datum, :set_id, :offset_id
            def initialize(member_id:, datum:, set_id:, offset_id:)
                @member_id = member_id
                @datum = datum
                @set_id = set_id
                @offset_id = offset_id
                freeze
            end
        end

        class ArgsReleaseCurrentsSelected
            attr_reader :member_id, :bin_number, :set_id
            def initialize(member_id:, bin_number:, set_id:)
                @member_id = member_id
                @bin_number = bin_number
                @set_id = set_id
                freeze
            end
        end

        class ArgsReleaseCurrentEventsSelected
            attr_reader :member_id, :bin_number, :set_id
            def initialize(member_id:, bin_number:, set_id:)
                @member_id = member_id
                @bin_number = bin_number
                @set_id = set_id
                freeze
            end
        end

        class ArgsReleaseStations
            attr_reader :member_id, :filters
            def initialize(member_id:, filters: nil)
                @member_id = member_id
                @filters = filters
                freeze
            end
        end

        class ArgsReleaseIterStations
            attr_reader :member_id, :filters
            def initialize(member_id:, filters: nil)
                @member_id = member_id
                @filters = filters
                freeze
            end
        end

        class ArgsReleaseSearch
            attr_reader :member_id, :name, :limit, :match, :filters
            def initialize(member_id:, name:, limit:, match:, filters: nil)
                @member_id = member_id
                @name = name
                @limit = limit
                @match = match
                @filters = filters
                freeze
            end
        end

        class ArgsReleaseNear
            attr_reader :member_id, :lat, :lon, :radius_km, :limit, :filters
            def initialize(member_id:, lat:, lon:, radius_km:, limit:, filters: nil)
                @member_id = member_id
                @lat = lat
                @lon = lon
                @radius_km = radius_km
                @limit = limit
                @filters = filters
                freeze
            end
        end

        class ArgsReleaseNearest
            attr_reader :member_id, :lat, :lon, :max_km, :filters
            def initialize(member_id:, lat:, lon:, max_km:, filters: nil)
                @member_id = member_id
                @lat = lat
                @lon = lon
                @max_km = max_km
                @filters = filters
                freeze
            end
        end

        class UnroundedTideEvent
            attr_reader :root_seconds, :event_type, :height_m, :reference_order
            def initialize(root_seconds:, event_type:, height_m:, reference_order:)
                @root_seconds = root_seconds
                @event_type = event_type
                @height_m = height_m
                @reference_order = reference_order
                freeze
            end
        end

        class UnroundedCurrentEvent
            attr_reader :root_seconds, :event_type, :velocity_m_s, :direction_deg, :reference_order
            def initialize(root_seconds:, event_type:, velocity_m_s:, direction_deg:, reference_order:)
                @root_seconds = root_seconds
                @event_type = event_type
                @velocity_m_s = velocity_m_s
                @direction_deg = direction_deg
                @reference_order = reference_order
                freeze
            end
        end

        class AuxiliaryValuesRequiresModel
            attr_reader :station_request, :release_view, :selection_options, :utc_instant
            def initialize(station_request:, release_view:, selection_options:, utc_instant:)
                @station_request = station_request
                @release_view = release_view
                @selection_options = selection_options
                @utc_instant = utc_instant
                freeze
            end
        end

        class AuxiliaryValuesSourceAccess
            attr_reader :raw_source_value, :arguments
            def initialize(raw_source_value:, arguments:)
                @raw_source_value = raw_source_value
                @arguments = arguments
                freeze
            end
        end

        class ResultContext
            attr_reader :station_id, :set_id, :reference_station_id, :bin_number, :datum, :release_datestamp, :algorithm
            def initialize(station_id:, set_id:, reference_station_id:, bin_number:, datum:, release_datestamp:, algorithm:)
                @station_id = station_id
                @set_id = set_id
                @reference_station_id = reference_station_id
                @bin_number = bin_number
                @datum = datum
                @release_datestamp = release_datestamp
                @algorithm = algorithm
                freeze
            end
        end

        class AcceptanceDecision
            attr_reader :accepted, :mandatory_findings
            def initialize(accepted:, mandatory_findings:)
                @accepted = accepted
                @mandatory_findings = mandatory_findings
                freeze
            end
        end

        class ArgsClientReleases
            attr_reader :member_id
            def initialize(member_id:)
                @member_id = member_id
                freeze
            end
        end

        class ArgsClientLatest
            attr_reader :member_id
            def initialize(member_id:)
                @member_id = member_id
                freeze
            end
        end

        class ArgsClientCheckForUpdate
            attr_reader :member_id
            def initialize(member_id:)
                @member_id = member_id
                freeze
            end
        end

        class ArgsClientUpdate
            attr_reader :member_id
            def initialize(member_id:)
                @member_id = member_id
                freeze
            end
        end

        class ArgsClientDownload
            attr_reader :member_id, :release, :to, :formats, :overwrite
            def initialize(member_id:, release:, to:, formats:, overwrite:)
                @member_id = member_id
                @release = release
                @to = to
                @formats = formats
                @overwrite = overwrite
                freeze
            end
        end

        class ArgsClientVerify
            attr_reader :member_id
            def initialize(member_id:)
                @member_id = member_id
                freeze
            end
        end

        class ArgsClientCachedReleases
            attr_reader :member_id
            def initialize(member_id:)
                @member_id = member_id
                freeze
            end
        end

        class ArgsClientPrune
            attr_reader :member_id, :keep
            def initialize(member_id:, keep:)
                @member_id = member_id
                @keep = keep
                freeze
            end
        end

        class ArgsClientClose
            attr_reader :member_id
            def initialize(member_id:)
                @member_id = member_id
                freeze
            end
        end

        class ArgsReleaseConvention
            attr_reader :member_id, :convention_id
            def initialize(member_id:, convention_id:)
                @member_id = member_id
                @convention_id = convention_id
                freeze
            end
        end

        class ArgsReleaseLicence
            attr_reader :member_id, :licence_id
            def initialize(member_id:, licence_id:)
                @member_id = member_id
                @licence_id = licence_id
                freeze
            end
        end

        class ArgsReleaseStation
            attr_reader :member_id, :station_id
            def initialize(member_id:, station_id:)
                @member_id = member_id
                @station_id = station_id
                freeze
            end
        end

        class ArgsReleaseRequireStation
            attr_reader :member_id, :station_id
            def initialize(member_id:, station_id:)
                @member_id = member_id
                @station_id = station_id
                freeze
            end
        end

        class ArgsReleaseTombstone
            attr_reader :member_id, :station_id
            def initialize(member_id:, station_id:)
                @member_id = member_id
                @station_id = station_id
                freeze
            end
        end

        class ArgsReleaseStationByAlias
            attr_reader :member_id, :system, :alias_id
            def initialize(member_id:, system:, alias_id:)
                @member_id = member_id
                @system = system
                @alias_id = alias_id
                freeze
            end
        end

        class ArgsReleaseReferenceStation
            attr_reader :member_id, :station
            def initialize(member_id:, station:)
                @member_id = member_id
                @station = station
                freeze
            end
        end

        class ArgsReleaseSubordinatesOf
            attr_reader :member_id, :station
            def initialize(member_id:, station:)
                @member_id = member_id
                @station = station
                freeze
            end
        end

        class ArgsReleaseAttribution
            attr_reader :member_id, :stations
            def initialize(member_id:, stations:)
                @member_id = member_id
                @stations = stations
                freeze
            end
        end

        class ArgsReleaseHeights
            attr_reader :member_id, :station, :start, :stop, :step_s, :datum, :set_id, :offset_id, :units
            def initialize(member_id:, station:, start:, stop:, step_s:, datum:, set_id:, offset_id:, units: ABSENT)
                @member_id = member_id
                @station = station
                @start = start
                @stop = stop
                @step_s = step_s
                @datum = datum
                @set_id = set_id
                @offset_id = offset_id
                @units = units
                freeze
            end
        end

        class ArgsReleaseHeightsAt
            attr_reader :member_id, :station, :times, :datum, :set_id, :offset_id, :units
            def initialize(member_id:, station:, times:, datum:, set_id:, offset_id:, units: ABSENT)
                @member_id = member_id
                @station = station
                @times = times
                @datum = datum
                @set_id = set_id
                @offset_id = offset_id
                @units = units
                freeze
            end
        end

        class ArgsReleaseExtremes
            attr_reader :member_id, :station, :start, :stop, :datum, :set_id, :offset_id, :units
            def initialize(member_id:, station:, start:, stop:, datum:, set_id:, offset_id:, units: ABSENT)
                @member_id = member_id
                @station = station
                @start = start
                @stop = stop
                @datum = datum
                @set_id = set_id
                @offset_id = offset_id
                @units = units
                freeze
            end
        end

        class ArgsReleaseCurrents
            attr_reader :member_id, :station, :start, :stop, :step_s, :bin_number, :set_id, :units
            def initialize(member_id:, station:, start:, stop:, step_s:, bin_number:, set_id:, units: ABSENT)
                @member_id = member_id
                @station = station
                @start = start
                @stop = stop
                @step_s = step_s
                @bin_number = bin_number
                @set_id = set_id
                @units = units
                freeze
            end
        end

        class ArgsReleaseCurrentEvents
            attr_reader :member_id, :station, :start, :stop, :bin_number, :set_id, :units
            def initialize(member_id:, station:, start:, stop:, bin_number:, set_id:, units: ABSENT)
                @member_id = member_id
                @station = station
                @start = start
                @stop = stop
                @bin_number = bin_number
                @set_id = set_id
                @units = units
                freeze
            end
        end

        class ArgsReleaseDatums
            attr_reader :member_id, :station, :set_id, :all_sets
            def initialize(member_id:, station:, set_id:, all_sets:)
                @member_id = member_id
                @station = station
                @set_id = set_id
                @all_sets = all_sets
                freeze
            end
        end

        class ArgsReleaseRanges
            attr_reader :member_id, :station, :set_id
            def initialize(member_id:, station:, set_id:)
                @member_id = member_id
                @station = station
                @set_id = set_id
                freeze
            end
        end

        class ArgsReleaseAstroTable
            attr_reader :member_id, :id
            def initialize(member_id:, id:)
                @member_id = member_id
                @id = id
                freeze
            end
        end

        class ArgsStationConstantSets
            attr_reader :member_id, :include_no_constants
            def initialize(member_id:, include_no_constants:)
                @member_id = member_id
                @include_no_constants = include_no_constants
                freeze
            end
        end

        class ArgsStationConstantSet
            attr_reader :member_id, :set_id
            def initialize(member_id:, set_id:)
                @member_id = member_id
                @set_id = set_id
                freeze
            end
        end

        class ArgsConstantSetConstituent
            attr_reader :member_id, :name
            def initialize(member_id:, name:)
                @member_id = member_id
                @name = name
                freeze
            end
        end

        class ArgsAstroTableEquilibriumArgument
            attr_reader :member_id, :name, :at
            def initialize(member_id:, name:, at:)
                @member_id = member_id
                @name = name
                @at = at
                freeze
            end
        end

        class ArgsAstroTableNodeFactor
            attr_reader :member_id, :name, :at
            def initialize(member_id:, name:, at:)
                @member_id = member_id
                @name = name
                @at = at
                freeze
            end
        end

        class ArgsAstroTableEquilibriumForYear
            attr_reader :member_id, :name, :year
            def initialize(member_id:, name:, year:)
                @member_id = member_id
                @name = name
                @year = year
                freeze
            end
        end

        class ArgsAstroTableNodeFactorForYear
            attr_reader :member_id, :name, :year
            def initialize(member_id:, name:, year:)
                @member_id = member_id
                @name = name
                @year = year
                freeze
            end
        end

        class ArgsHeightPointLocalDatetime
            attr_reader :member_id
            def initialize(member_id:)
                @member_id = member_id
                freeze
            end
        end

        class ArgsExtremeLocalDatetime
            attr_reader :member_id
            def initialize(member_id:)
                @member_id = member_id
                freeze
            end
        end

        class ArgsCurrentPointLocalDatetime
            attr_reader :member_id
            def initialize(member_id:)
                @member_id = member_id
                freeze
            end
        end

        class ArgsCurrentEventLocalDatetime
            attr_reader :member_id
            def initialize(member_id:)
                @member_id = member_id
                freeze
            end
        end

        class ArgsHeightSeriesToLocal
            attr_reader :member_id, :tz
            def initialize(member_id:, tz:)
                @member_id = member_id
                @tz = tz
                freeze
            end
        end

        class ArgsExtremeListToLocal
            attr_reader :member_id, :tz
            def initialize(member_id:, tz:)
                @member_id = member_id
                @tz = tz
                freeze
            end
        end

        class ArgsCurrentSeriesToLocal
            attr_reader :member_id, :tz
            def initialize(member_id:, tz:)
                @member_id = member_id
                @tz = tz
                freeze
            end
        end

        class ArgsCurrentEventListToLocal
            attr_reader :member_id, :tz
            def initialize(member_id:, tz:)
                @member_id = member_id
                @tz = tz
                freeze
            end
        end

        class AstronomicalTerms
            attr_reader :utc_year, :constituent_terms, :epoch_hours
            def initialize(utc_year:, constituent_terms:, epoch_hours:)
                @utc_year = utc_year
                @constituent_terms = constituent_terms
                @epoch_hours = epoch_hours
                freeze
            end
        end

        class SchemaFallback
            attr_reader :reason, :basis, :otc_finding, :preferred_set_id, :source_extensions
            def initialize(reason:, basis:, otc_finding:, preferred_set_id:, source_extensions:)
                @reason = reason
                @basis = basis
                @otc_finding = otc_finding
                @preferred_set_id = preferred_set_id
                @source_extensions = source_extensions
                freeze
            end
        end

        class AuthenticatedIndexStationsItemSetsItem
            attr_reader :set_id, :source, :source_type, :quantity, :qc_status, :convention_id, :licence_id, :constituents, :fallback, :current_bins
            def initialize(set_id:, source:, source_type:, quantity:, qc_status:, convention_id:, licence_id:, constituents:, fallback:, current_bins:)
                @set_id = set_id
                @source = source
                @source_type = source_type
                @quantity = quantity
                @qc_status = qc_status
                @convention_id = convention_id
                @licence_id = licence_id
                @constituents = constituents
                @fallback = fallback
                @current_bins = current_bins
                freeze
            end
        end

        class SchemaQcFlag
            attr_reader :flag, :reason, :values, :source_extensions
            def initialize(flag:, reason:, values:, source_extensions:)
                @flag = flag
                @reason = reason
                @values = values
                @source_extensions = source_extensions
                freeze
            end
        end

        class SchemaHistoricalOffsetVintageRemovalEventsItem
            attr_reader :source_clock_timestamp, :name, :operation, :source_timezone, :evidence_sha256, :source_extensions
            def initialize(source_clock_timestamp:, name:, operation:, source_timezone:, evidence_sha256:, source_extensions:)
                @source_clock_timestamp = source_clock_timestamp
                @name = name
                @operation = operation
                @source_timezone = source_timezone
                @evidence_sha256 = evidence_sha256
                @source_extensions = source_extensions
                freeze
            end
        end

        class SchemaHistoricalOffsetVintage
            attr_reader :publication_year, :source_lifecycle, :removal_events, :current_validity, :current_accuracy, :reference_2020_equivalence, :reference_2020_equivalence_sha256, :source_extensions
            def initialize(publication_year:, source_lifecycle:, removal_events:, current_validity:, current_accuracy:, reference_2020_equivalence:, reference_2020_equivalence_sha256:, source_extensions:)
                @publication_year = publication_year
                @source_lifecycle = source_lifecycle
                @removal_events = removal_events
                @current_validity = current_validity
                @current_accuracy = current_accuracy
                @reference_2020_equivalence = reference_2020_equivalence
                @reference_2020_equivalence_sha256 = reference_2020_equivalence_sha256
                @source_extensions = source_extensions
                freeze
            end
        end

        class SchemaHistoricalOffsetProvenanceIdCrosswalk
            attr_reader :legacy_id, :status, :modern_alias_verified, :evidence_sha256, :source_extensions
            def initialize(legacy_id:, status:, modern_alias_verified:, evidence_sha256:, source_extensions:)
                @legacy_id = legacy_id
                @status = status
                @modern_alias_verified = modern_alias_verified
                @evidence_sha256 = evidence_sha256
                @source_extensions = source_extensions
                freeze
            end
        end

        class SchemaHistoricalOffsetProvenanceReferenceBinding
            attr_reader :noaa_id, :station_id, :mapping_status, :evidence_sha256, :source_extensions
            def initialize(noaa_id:, station_id:, mapping_status:, evidence_sha256:, source_extensions:)
                @noaa_id = noaa_id
                @station_id = station_id
                @mapping_status = mapping_status
                @evidence_sha256 = evidence_sha256
                @source_extensions = source_extensions
                freeze
            end
        end

        class SchemaHistoricalOffsetProvenance
            attr_reader :source_manifest_sha256, :input_sha256, :book, :annual_table_row, :printed_page, :pdf_page, :raw_row_text, :raw_values_json, :id_crosswalk, :reference_binding, :acceptance_report_sha256, :source_extensions
            def initialize(source_manifest_sha256:, input_sha256:, book:, annual_table_row:, printed_page:, pdf_page:, raw_row_text:, raw_values_json:, id_crosswalk:, reference_binding:, acceptance_report_sha256:, source_extensions:)
                @source_manifest_sha256 = source_manifest_sha256
                @input_sha256 = input_sha256
                @book = book
                @annual_table_row = annual_table_row
                @printed_page = printed_page
                @pdf_page = pdf_page
                @raw_row_text = raw_row_text
                @raw_values_json = raw_values_json
                @id_crosswalk = id_crosswalk
                @reference_binding = reference_binding
                @acceptance_report_sha256 = acceptance_report_sha256
                @source_extensions = source_extensions
                freeze
            end
        end

        class SchemaSubordinateOffsets
            attr_reader :reference_station_id, :time_offset_high_min, :time_offset_low_min, :height_offset_high, :height_offset_low, :height_adjusted_type, :licence_id, :datum, :offset_id, :source, :source_type, :source_version, :source_record_id, :qc_status, :qc_flags, :fallback, :vintage, :provenance, :source_extensions
            def initialize(reference_station_id:, time_offset_high_min:, time_offset_low_min:, height_offset_high:, height_offset_low:, height_adjusted_type:, licence_id:, datum:, offset_id:, source:, source_type:, source_version:, source_record_id:, qc_status:, qc_flags:, fallback:, vintage:, provenance:, source_extensions:)
                @reference_station_id = reference_station_id
                @time_offset_high_min = time_offset_high_min
                @time_offset_low_min = time_offset_low_min
                @height_offset_high = height_offset_high
                @height_offset_low = height_offset_low
                @height_adjusted_type = height_adjusted_type
                @licence_id = licence_id
                @datum = datum
                @offset_id = offset_id
                @source = source
                @source_type = source_type
                @source_version = source_version
                @source_record_id = source_record_id
                @qc_status = qc_status
                @qc_flags = qc_flags
                @fallback = fallback
                @vintage = vintage
                @provenance = provenance
                @source_extensions = source_extensions
                freeze
            end
        end

        class AuthenticatedIndexStationsItemCurrentOffsetsItem
            attr_reader :bin, :reference_bin, :reference_station_id, :licence_id
            def initialize(bin:, reference_bin:, reference_station_id:, licence_id:)
                @bin = bin
                @reference_bin = reference_bin
                @reference_station_id = reference_station_id
                @licence_id = licence_id
                freeze
            end
        end

        class AuthenticatedIndexStationsItem
            attr_reader :station_id, :status, :name, :name_folded, :country, :type, :kind, :reference_station_id, :offsets_licence_id, :recommended_set_id, :lat, :lon, :offset, :length, :aliases, :sets, :subordinate_offsets, :current_offsets
            def initialize(station_id:, status:, name:, name_folded:, country:, type:, kind:, reference_station_id:, offsets_licence_id:, recommended_set_id:, lat:, lon:, offset:, length:, aliases:, sets:, subordinate_offsets:, current_offsets:)
                @station_id = station_id
                @status = status
                @name = name
                @name_folded = name_folded
                @country = country
                @type = type
                @kind = kind
                @reference_station_id = reference_station_id
                @offsets_licence_id = offsets_licence_id
                @recommended_set_id = recommended_set_id
                @lat = lat
                @lon = lon
                @offset = offset
                @length = length
                @aliases = aliases
                @sets = sets
                @subordinate_offsets = subordinate_offsets
                @current_offsets = current_offsets
                freeze
            end
        end

        class AuthenticatedIndex
            attr_reader :index_version, :discovery_index_version, :datestamp, :jsonl, :jsonl_sha256, :jsonl_size, :by, :stations, :native_context, :source_document
            def initialize(index_version:, discovery_index_version:, datestamp:, jsonl:, jsonl_sha256:, jsonl_size:, by:, stations:, native_context: nil, source_document: nil)
                @index_version = index_version
                @discovery_index_version = discovery_index_version
                @datestamp = datestamp
                @jsonl = jsonl
                @jsonl_sha256 = jsonl_sha256
                @jsonl_size = jsonl_size
                @by = by
                @stations = stations
                @native_context = native_context
                @source_document = source_document
                freeze
            end
        end

        class SelectedResult0
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult1
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult2
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult3
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult4
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult5
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult6
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult7
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult8
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult9
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult10
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult11
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult12
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult13
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult14
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult15
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult16
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult17
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult18
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult19
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult20
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult21
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult22
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult23
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult24
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult25
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult26
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult27
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult28
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult29
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult30
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult31
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult32
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult33
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult34
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult35
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult36
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult37
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult38
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult39
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult40
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult41
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult42
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult43
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult44
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult45
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult46
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult47
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult48
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult49
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult50
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult51
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult52
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult53
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult54
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult55
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult56
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult57
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult58
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult59
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult60
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult61
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult62
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult63
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult64
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult65
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult66
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult67
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult68
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult69
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult70
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult71
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult72
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult73
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult74
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult75
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult76
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult77
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult78
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult79
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult80
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult81
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult82
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult83
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult84
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult85
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult86
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult87
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult88
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult89
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult90
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult91
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult92
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult93
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult94
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult95
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult96
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult97
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult98
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult99
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult100
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class SelectedResult101
            attr_reader :member_id, :value
            def initialize(member_id:, value:)
                @member_id = member_id
                @value = value
                freeze
            end
        end

        class CacheDocumentStreamIndexStationsItemSetsItem
            attr_reader :set_id, :source, :source_type, :quantity, :qc_status, :convention_id, :licence_id, :constituents, :fallback, :current_bins
            def initialize(set_id:, source:, source_type:, quantity:, qc_status:, convention_id:, licence_id:, constituents:, fallback:, current_bins:)
                @set_id = set_id
                @source = source
                @source_type = source_type
                @quantity = quantity
                @qc_status = qc_status
                @convention_id = convention_id
                @licence_id = licence_id
                @constituents = constituents
                @fallback = fallback
                @current_bins = current_bins
                freeze
            end
        end

        class CacheDocumentStreamIndexStationsItemCurrentOffsetsItem
            attr_reader :bin, :reference_bin, :reference_station_id, :licence_id
            def initialize(bin:, reference_bin:, reference_station_id:, licence_id:)
                @bin = bin
                @reference_bin = reference_bin
                @reference_station_id = reference_station_id
                @licence_id = licence_id
                freeze
            end
        end

        class CacheDocumentStreamIndexStationsItem
            attr_reader :station_id, :status, :name, :name_folded, :country, :type, :kind, :reference_station_id, :offsets_licence_id, :recommended_set_id, :lat, :lon, :offset, :length, :aliases, :sets, :subordinate_offsets, :current_offsets
            def initialize(station_id:, status:, name:, name_folded:, country:, type:, kind:, reference_station_id:, offsets_licence_id:, recommended_set_id:, lat:, lon:, offset:, length:, aliases:, sets:, subordinate_offsets:, current_offsets:)
                @station_id = station_id
                @status = status
                @name = name
                @name_folded = name_folded
                @country = country
                @type = type
                @kind = kind
                @reference_station_id = reference_station_id
                @offsets_licence_id = offsets_licence_id
                @recommended_set_id = recommended_set_id
                @lat = lat
                @lon = lon
                @offset = offset
                @length = length
                @aliases = aliases
                @sets = sets
                @subordinate_offsets = subordinate_offsets
                @current_offsets = current_offsets
                freeze
            end
        end

        class CacheDocumentStreamIndex
            attr_reader :index_version, :discovery_index_version, :datestamp, :jsonl, :jsonl_sha256, :jsonl_size, :by, :stations
            def initialize(index_version:, discovery_index_version:, datestamp:, jsonl:, jsonl_sha256:, jsonl_size:, by:, stations:)
                @index_version = index_version
                @discovery_index_version = discovery_index_version
                @datestamp = datestamp
                @jsonl = jsonl
                @jsonl_sha256 = jsonl_sha256
                @jsonl_size = jsonl_size
                @by = by
                @stations = stations
                freeze
            end
        end

        class CacheDocumentVerifiedReceiptFilesValue
            attr_reader :sha256, :size, :url
            def initialize(sha256:, size:, url:)
                @sha256 = sha256
                @size = size
                @url = url
                freeze
            end
        end

        class CacheDocumentVerifiedReceipt
            attr_reader :datestamp, :files, :format_version, :min_reader_version, :zenodo_version_doi, :verified_at, :by
            def initialize(datestamp:, files:, format_version:, min_reader_version:, zenodo_version_doi:, verified_at:, by:)
                @datestamp = datestamp
                @files = files
                @format_version = format_version
                @min_reader_version = min_reader_version
                @zenodo_version_doi = zenodo_version_doi
                @verified_at = verified_at
                @by = by
                freeze
            end
        end

        class CanonicalError
            attr_reader :code, :structured_fields, :cause
            def initialize(code:, structured_fields:, cause:)
                @code = code
                @structured_fields = structured_fields
                @cause = cause
                freeze
            end
        end

        class ClientAndRelease
            attr_reader :client_state, :loaded_release
            def initialize(client_state:, loaded_release:)
                @client_state = client_state
                @loaded_release = loaded_release
                freeze
            end
        end

        class ClientState
            attr_reader :current_release, :effective_options, :cache_state, :last_error, :last_update_check, :closed
            def initialize(current_release:, effective_options:, cache_state:, last_error:, last_update_check:, closed:)
                @current_release = current_release
                @effective_options = effective_options
                @cache_state = cache_state
                @last_error = last_error
                @last_update_check = last_update_check
                @closed = closed
                freeze
            end
        end

        class CommercialAdmission
            attr_reader :admitted, :reason
            def initialize(admitted:, reason:)
                @admitted = admitted
                @reason = reason
                freeze
            end
        end

        class EvidenceBundle
            attr_reader :scenario, :expected_result, :actual_profile_results, :red_output, :green_output
            def initialize(scenario:, expected_result:, actual_profile_results:, red_output:, green_output:)
                @scenario = scenario
                @expected_result = expected_result
                @actual_profile_results = actual_profile_results
                @red_output = red_output
                @green_output = green_output
                freeze
            end
        end

        class FormatSelection
            attr_reader :formats, :required_files
            def initialize(formats:, required_files:)
                @formats = formats
                @required_files = required_files
                freeze
            end
        end

        class HistoricalAdmission
            attr_reader :admitted, :reason
            def initialize(admitted:, reason:)
                @admitted = admitted
                @reason = reason
                freeze
            end
        end

        class HttpRequest
            attr_reader :url, :conditional_etag
            def initialize(url:, conditional_etag:)
                @url = url
                @conditional_etag = conditional_etag
                freeze
            end
        end

        class HttpResponse
            attr_reader :status_code, :body, :etag, :request_url
            def initialize(status_code:, body:, etag:, request_url:)
                @status_code = status_code
                @body = body
                @etag = etag
                @request_url = request_url
                freeze
            end
        end

        class IdentityQuery1
            attr_reader :system, :id
            def initialize(system:, id:)
                @system = system
                @id = id
                freeze
            end
        end

        class IndexEntrySetsItem
            attr_reader :set_id, :source, :source_type, :quantity, :qc_status, :convention_id, :licence_id, :constituents, :fallback, :current_bins
            def initialize(set_id:, source:, source_type:, quantity:, qc_status:, convention_id:, licence_id:, constituents:, fallback:, current_bins:)
                @set_id = set_id
                @source = source
                @source_type = source_type
                @quantity = quantity
                @qc_status = qc_status
                @convention_id = convention_id
                @licence_id = licence_id
                @constituents = constituents
                @fallback = fallback
                @current_bins = current_bins
                freeze
            end
        end

        class IndexEntryCurrentOffsetsItem
            attr_reader :bin, :reference_bin, :reference_station_id, :licence_id
            def initialize(bin:, reference_bin:, reference_station_id:, licence_id:)
                @bin = bin
                @reference_bin = reference_bin
                @reference_station_id = reference_station_id
                @licence_id = licence_id
                freeze
            end
        end

        class IndexEntry
            attr_reader :station_id, :status, :name, :name_folded, :country, :type, :kind, :reference_station_id, :offsets_licence_id, :recommended_set_id, :lat, :lon, :offset, :length, :aliases, :sets, :subordinate_offsets, :current_offsets
            def initialize(station_id:, status:, name:, name_folded:, country:, type:, kind:, reference_station_id:, offsets_licence_id:, recommended_set_id:, lat:, lon:, offset:, length:, aliases:, sets:, subordinate_offsets:, current_offsets:)
                @station_id = station_id
                @status = status
                @name = name
                @name_folded = name_folded
                @country = country
                @type = type
                @kind = kind
                @reference_station_id = reference_station_id
                @offsets_licence_id = offsets_licence_id
                @recommended_set_id = recommended_set_id
                @lat = lat
                @lon = lon
                @offset = offset
                @length = length
                @aliases = aliases
                @sets = sets
                @subordinate_offsets = subordinate_offsets
                @current_offsets = current_offsets
                freeze
            end
        end

        class LockOutcome
            attr_reader :acquired, :token, :owned
            def initialize(acquired:, token:, owned:)
                @acquired = acquired
                @token = token
                @owned = owned
                freeze
            end
        end

        class LockRequest
            attr_reader :directory, :operation, :token
            def initialize(directory:, operation:, token:)
                @directory = directory
                @operation = operation
                @token = token
                freeze
            end
        end

        class MergedReceiptFilesValue
            attr_reader :sha256, :size, :url
            def initialize(sha256:, size:, url:)
                @sha256 = sha256
                @size = size
                @url = url
                freeze
            end
        end

        class MergedReceipt
            attr_reader :datestamp, :files, :format_version, :min_reader_version, :zenodo_version_doi, :verified_at, :by
            def initialize(datestamp:, files:, format_version:, min_reader_version:, zenodo_version_doi:, verified_at:, by:)
                @datestamp = datestamp
                @files = files
                @format_version = format_version
                @min_reader_version = min_reader_version
                @zenodo_version_doi = zenodo_version_doi
                @verified_at = verified_at
                @by = by
                freeze
            end
        end

        class MetadataRequest
            attr_reader :request_url, :document_kind
            def initialize(request_url:, document_kind:)
                @request_url = request_url
                @document_kind = document_kind
                freeze
            end
        end

        class ProjectionContract
            attr_reader :scalar_types, :models, :subordinate_offsets, :scope, :fallback
            def initialize(scalar_types:, models:, subordinate_offsets:, scope:, fallback:)
                @scalar_types = scalar_types
                @models = models
                @subordinate_offsets = subordinate_offsets
                @scope = scope
                @fallback = fallback
                freeze
            end
        end

        class PublishedMetadata
            attr_reader :contributors, :year, :concept_doi, :zenodo_version_doi, :dataset_url
            def initialize(contributors:, year:, concept_doi:, zenodo_version_doi:, dataset_url:)
                @contributors = contributors
                @year = year
                @concept_doi = concept_doi
                @zenodo_version_doi = zenodo_version_doi
                @dataset_url = dataset_url
                freeze
            end
        end

        class QualityAdmission
            attr_reader :admitted, :reason
            def initialize(admitted:, reason:)
                @admitted = admitted
                @reason = reason
                freeze
            end
        end

        class ReaderVersion
            attr_reader :major, :minor, :native_context
            def initialize(major:, minor:, native_context: nil)
                @major = major
                @minor = minor
                @native_context = native_context
                freeze
            end
        end

        class Scenario
            attr_reader :behavior_ids, :input, :expected_output, :expected_error, :expected_state
            def initialize(behavior_ids:, input:, expected_output:, expected_error:, expected_state:)
                @behavior_ids = behavior_ids
                @input = input
                @expected_output = expected_output
                @expected_error = expected_error
                @expected_state = expected_state
                freeze
            end
        end

        class ScenarioComparison
            attr_reader :accepted, :mandatory_findings
            def initialize(accepted:, mandatory_findings:)
                @accepted = accepted
                @mandatory_findings = mandatory_findings
                freeze
            end
        end

        class SourceByteSpan
            attr_reader :offset_bytes, :length_bytes
            def initialize(offset_bytes:, length_bytes:)
                @offset_bytes = offset_bytes
                @length_bytes = length_bytes
                freeze
            end
        end

        class SourceFiles
            attr_reader :jsonl, :meta, :jsonl_sha256, :jsonl_size, :meta_sha256, :meta_size
            def initialize(jsonl:, meta:, jsonl_sha256:, jsonl_size:, meta_sha256:, meta_size:)
                @jsonl = jsonl
                @meta = meta
                @jsonl_sha256 = jsonl_sha256
                @jsonl_size = jsonl_size
                @meta_sha256 = meta_sha256
                @meta_size = meta_size
                freeze
            end
        end

        class StationIndexEntrySetsItem
            attr_reader :set_id, :source, :source_type, :quantity, :qc_status, :convention_id, :licence_id, :constituents, :fallback, :current_bins
            def initialize(set_id:, source:, source_type:, quantity:, qc_status:, convention_id:, licence_id:, constituents:, fallback:, current_bins:)
                @set_id = set_id
                @source = source
                @source_type = source_type
                @quantity = quantity
                @qc_status = qc_status
                @convention_id = convention_id
                @licence_id = licence_id
                @constituents = constituents
                @fallback = fallback
                @current_bins = current_bins
                freeze
            end
        end

        class StationIndexEntryCurrentOffsetsItem
            attr_reader :bin, :reference_bin, :reference_station_id, :licence_id
            def initialize(bin:, reference_bin:, reference_station_id:, licence_id:)
                @bin = bin
                @reference_bin = reference_bin
                @reference_station_id = reference_station_id
                @licence_id = licence_id
                freeze
            end
        end

        class StationIndexEntry
            attr_reader :station_id, :status, :name, :name_folded, :country, :type, :kind, :reference_station_id, :offsets_licence_id, :recommended_set_id, :lat, :lon, :offset, :length, :aliases, :sets, :subordinate_offsets, :current_offsets
            def initialize(station_id:, status:, name:, name_folded:, country:, type:, kind:, reference_station_id:, offsets_licence_id:, recommended_set_id:, lat:, lon:, offset:, length:, aliases:, sets:, subordinate_offsets:, current_offsets:)
                @station_id = station_id
                @status = status
                @name = name
                @name_folded = name_folded
                @country = country
                @type = type
                @kind = kind
                @reference_station_id = reference_station_id
                @offsets_licence_id = offsets_licence_id
                @recommended_set_id = recommended_set_id
                @lat = lat
                @lon = lon
                @offset = offset
                @length = length
                @aliases = aliases
                @sets = sets
                @subordinate_offsets = subordinate_offsets
                @current_offsets = current_offsets
                freeze
            end
        end

        class StreamReader
            attr_reader :release_view, :file_descriptor, :index, :index_presence, :station_lru, :closed
            def initialize(release_view:, file_descriptor:, index:, index_presence:, station_lru:, closed:)
                @release_view = release_view
                @file_descriptor = file_descriptor
                @index = index
                @index_presence = index_presence
                @station_lru = station_lru
                @closed = closed
                freeze
            end
        end

        class SummaryOptions
            attr_reader :original_recommendation, :commercial_only, :include_no_constants
            def initialize(original_recommendation:, commercial_only:, include_no_constants:)
                @original_recommendation = original_recommendation
                @commercial_only = commercial_only
                @include_no_constants = include_no_constants
                freeze
            end
        end

        class SuppliedIndexStationsItemSetsItem
            attr_reader :set_id, :source, :source_type, :quantity, :qc_status, :convention_id, :licence_id, :constituents, :fallback, :current_bins
            def initialize(set_id:, source:, source_type:, quantity:, qc_status:, convention_id:, licence_id:, constituents:, fallback:, current_bins:)
                @set_id = set_id
                @source = source
                @source_type = source_type
                @quantity = quantity
                @qc_status = qc_status
                @convention_id = convention_id
                @licence_id = licence_id
                @constituents = constituents
                @fallback = fallback
                @current_bins = current_bins
                freeze
            end
        end

        class SuppliedIndexStationsItemCurrentOffsetsItem
            attr_reader :bin, :reference_bin, :reference_station_id, :licence_id
            def initialize(bin:, reference_bin:, reference_station_id:, licence_id:)
                @bin = bin
                @reference_bin = reference_bin
                @reference_station_id = reference_station_id
                @licence_id = licence_id
                freeze
            end
        end

        class SuppliedIndexStationsItem
            attr_reader :station_id, :status, :name, :name_folded, :country, :type, :kind, :reference_station_id, :offsets_licence_id, :recommended_set_id, :lat, :lon, :offset, :length, :aliases, :sets, :subordinate_offsets, :current_offsets
            def initialize(station_id:, status:, name:, name_folded:, country:, type:, kind:, reference_station_id:, offsets_licence_id:, recommended_set_id:, lat:, lon:, offset:, length:, aliases:, sets:, subordinate_offsets:, current_offsets:)
                @station_id = station_id
                @status = status
                @name = name
                @name_folded = name_folded
                @country = country
                @type = type
                @kind = kind
                @reference_station_id = reference_station_id
                @offsets_licence_id = offsets_licence_id
                @recommended_set_id = recommended_set_id
                @lat = lat
                @lon = lon
                @offset = offset
                @length = length
                @aliases = aliases
                @sets = sets
                @subordinate_offsets = subordinate_offsets
                @current_offsets = current_offsets
                freeze
            end
        end

        class SuppliedIndex
            attr_reader :index_version, :discovery_index_version, :datestamp, :jsonl, :jsonl_sha256, :jsonl_size, :by, :stations
            def initialize(index_version:, discovery_index_version:, datestamp:, jsonl:, jsonl_sha256:, jsonl_size:, by:, stations:)
                @index_version = index_version
                @discovery_index_version = discovery_index_version
                @datestamp = datestamp
                @jsonl = jsonl
                @jsonl_sha256 = jsonl_sha256
                @jsonl_size = jsonl_size
                @by = by
                @stations = stations
                freeze
            end
        end

        class TrustedCachedPointer
            attr_reader :digests
            def initialize(digests:)
                @digests = digests
                freeze
            end
        end

        class ValidatedMetadata
            attr_reader :document, :selected_datestamp, :request_url, :files
            def initialize(document:, selected_datestamp:, request_url:, files:)
                @document = document
                @selected_datestamp = selected_datestamp
                @request_url = request_url
                @files = files
                freeze
            end
        end

        ABSENT = AbsentValue.new.freeze
    end
    private_constant :CanonicalTypes
end
