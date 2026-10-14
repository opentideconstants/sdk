require "date"
require "time"

class OpenTideConstants
    # Helpers shared by the data objects. Every object is frozen and keeps the
    # parsed JSON object as #raw (a deep-frozen Hash) where the API manifest
    # lists one, so a caller can read
    # fields that a newer minor format adds (spec §3, §7.3).
    module Util
        module_function

        def deep_freeze(v)
            case v
            when Hash then v.each_value { |x| deep_freeze(x) }
            when Array then v.each { |x| deep_freeze(x) }
            end
            v.freeze
        end

        # An enum value as a symbol; a value this SDK does not know is :other.
        def enum(value, known)
            return nil if value.nil?
            known.include?(value) ? value.to_sym : :other
        end

        TIME_FIELDS = /\A(\d{4})-(\d{2})-(\d{2})[Tt ](\d{2}):(\d{2}):(\d{2})/

        # An RFC 3339 time in UTC. Impossible calendar fields, hour 24, a leap
        # second :60 and a time out of years 1 to 9999 in UTC are malformed
        # (CR2 DR6): Time.iso8601 would roll them over into another date.
        def time(value)
            return nil if value.nil?
            raise InvalidReleaseError, "bad time: #{value.inspect}" unless value.is_a?(String)
            y, mo, d, h, mi, s = TIME_FIELDS.match(value)&.captures&.map(&:to_i)
            unless y && Date.valid_date?(y, mo, d, Date::GREGORIAN) && h <= 23 && mi <= 59 && s <= 59
                raise InvalidReleaseError, "bad time: #{value.inspect}"
            end
            t = Time.iso8601(value).utc
            raise InvalidReleaseError, "bad time: #{value.inspect}" unless (1..9999).cover?(t.year)
            t.freeze
        rescue ArgumentError
            raise InvalidReleaseError, "bad time: #{value.inspect}"
        end

        SURROGATE_ESCAPE = /\\u[dD][89a-fA-F]/.freeze
        # One escape of a JSON text: a surrogate pair, a lone surrogate (group
        # 1), another \u escape, or any other escaped character (so an escaped
        # backslash before "ud800" is not read as an escape).
        ESCAPE = /\\(?:u[dD][89abAB]\h{2}\\u[dD][c-fC-F]\h{2}|(u[dD][89a-fA-F]\h{2})|u\h{4}|.)/m.freeze

        # invalid_release when a \u escape of a JSON text makes an unpaired
        # UTF-16 surrogate (spec §7.3, CR D17). Checked on the text, before
        # JSON.parse: some versions of the json gem replace a lone surrogate
        # with "?" (and drop the next character) instead of raising.
        def no_lone_surrogate!(text)
            return unless SURROGATE_ESCAPE.match?(text)
            text.scan(ESCAPE) do |lone|
                raise InvalidReleaseError, "a string with an unpaired surrogate (\\#{lone[0]})" if lone[0]
            end
            nil
        end

        # A build-only time (provenance.build): a malformed one is nil, not a
        # failed station (spec §4.6, §7.3).
        def time_or_nil(value)
            time(value)
        rescue InvalidReleaseError
            nil
        end
    end

    ENUMS = {
        fallback_reason: ["time_base_disputed", "time_base_unresolved", "refused_fit", "short_record_uncalibrated", "short_record_long_period", "published_full_list", "reliability_withheld", "licence_reading", "datum_gate_failed", "not_in_otc_input", "historical_offsets"],
        source_role: ["gauge_station", "published_harmonic_record", "model", "reference"],
        source_disposition: ["metadata_only", "not_fitted", "licence_restricted", "unavailable", "retained"],
        extreme_type: ["high", "low"],
        current_event_type: ["max_flood", "max_ebb", "slack_before_flood", "slack_before_ebb"],
        prediction_method: ["harmonic", "folded_offsets", "offsets"],
        kind: %w[tide current],
        station_type: %w[reference subordinate],
        station_status: %w[active removed],
        source_type: %w[official gauge model],
        quantity: %w[water_level current],
        removed_reason: %w[merged duplicate],
        qc_status: %w[ok flagged no_constants],
        phase_reference: %w[greenwich_utc local],
        nodal_handling: %w[f_u_at_prediction none],
        height_adjusted_type: %w[R A],
        dropped_reason: %w[rayleigh noise long_period_rule non_tidal_rule convention other],
        qc_flag: ["time_base", "broken_record", "microtidal", "non_tidal_signal", "short_record", "sibling_disagreement", "carried_over", "fallback:time_base_disputed", "fallback:time_base_unresolved", "fallback:refused_fit", "fallback:short_record_uncalibrated", "fallback:short_record_long_period", "fallback:published_full_list", "fallback:reliability_withheld", "fallback:licence_reading", "fallback:datum_gate_failed", "fallback:not_in_otc_input", "fallback:historical_offsets"],
        time_base_code: %w[verified corrected unverified disputed],
        alias_system: %w[noaa gesla ticon xtide kartverket slackwater webcaltides linz shom pegelonline rws mi dmi smhi fmi
                          uhslc]
    }.freeze

    # One file of a release: name, url, size and sha256 (spec §4.3.1).
    class FileInfo
        attr_reader :name, :url, :size, :sha256

        def initialize(name:, url: nil, size: nil, sha256: nil)
            @name = name.freeze
            @url = url&.freeze
            @size = size
            @sha256 = sha256&.freeze
            freeze
        end
    end

    # An entry of the latest pointer or the release index; no station data.
    class ReleaseInfo
        attr_reader :datestamp, :format_version, :concept_doi, :zenodo_version_doi, :content_sha256, :files

        def initialize(raw, files)
            Util.deep_freeze(raw)
            @datestamp = raw["datestamp"]
            @format_version = raw["format_version"]
            @concept_doi = raw["concept_doi"]
            @zenodo_version_doi = raw["zenodo_version_doi"]
            @content_sha256 = raw["content_sha256"]
            @files = files.freeze
            freeze
        end
    end

    class Licence
        attr_reader :licence_id, :spdx, :provider, :citation, :attribution, :url, :commercial_use, :restriction,
                    :terms_url, :raw

        def initialize(raw)
            @raw = Util.deep_freeze(raw)
            @licence_id = raw["licence_id"]
            @spdx = raw["spdx"]
            @provider = raw["provider"]
            @citation = raw["citation"]
            @attribution = raw["attribution"]
            @url = raw["url"]
            @commercial_use = raw["commercial_use"]
            @restriction = raw["restriction"]
            @terms_url = raw["terms_url"]
            freeze
        end

        # The load rules of the licence fields (spec §4.6, K-NC DR104):
        # commercial_use is true or false (absent or null is invalid);
        # restriction and terms_url, when present, are Strings (a JSON null is
        # not one, CR3 DR71); a non-commercial licence has both, and an spdx,
        # which the non-commercial notice prints.
        def self.check!(raw)
            lid = raw["licence_id"]
            cu = raw["commercial_use"]
            raise InvalidReleaseError, "licence #{lid}: commercial_use must be true or false" unless cu == true || cu == false
            %w[restriction terms_url].each do |k|
                raise InvalidReleaseError, "licence #{lid}: #{k} must be a String" if raw.key?(k) && !raw[k].is_a?(String)
            end
            return if cu
            %w[restriction terms_url spdx].each do |k|
                raise InvalidReleaseError, "licence #{lid}: a licence with commercial_use false needs #{k}" unless raw[k].is_a?(String)
            end
        end
    end

    class Convention
        attr_reader :convention_id, :phase_reference, :utc_offset_hours, :v0_model, :nodal_handling,
                    :nodal_formula_ids, :constituent_table_version, :tables_sha256, :canary, :raw

        def initialize(raw)
            @raw = Util.deep_freeze(raw)
            @convention_id = raw["convention_id"]
            @phase_reference = Util.enum(raw["phase_reference"], ENUMS[:phase_reference])
            @utc_offset_hours = raw["utc_offset_hours"]
            @v0_model = raw["v0_model"]
            @nodal_handling = Util.enum(raw["nodal_handling"], ENUMS[:nodal_handling])
            @nodal_formula_ids = raw["nodal_formula_ids"]
            @constituent_table_version = raw["constituent_table_version"]
            @tables_sha256 = raw["tables_sha256"]
            @canary = raw["canary"]
            freeze
        end
    end

    class Constituent
        attr_reader :name, :source_name, :doodson, :speed_deg_per_hour, :amplitude_m, :phase_deg,
                    :amp_uncertainty_m, :phase_uncertainty_deg, :kept_reason, :raw

        def initialize(raw)
            @raw = Util.deep_freeze(raw)
            @name = raw["name"]
            @source_name = raw["source_name"]
            @doodson = raw["doodson"]
            @speed_deg_per_hour = raw["speed_deg_per_hour"]
            @amplitude_m = raw["amplitude_m"]
            @phase_deg = raw["phase_deg"]
            @amp_uncertainty_m = raw["amp_uncertainty_m"]
            @phase_uncertainty_deg = raw["phase_uncertainty_deg"]
            @kept_reason = raw["kept_reason"]
            freeze
        end
    end

    # The build metadata of a set (provenance.build).
    class ProvenanceBuild
        attr_reader :build_commit, :built_at, :fetched_at, :run_id, :tool_versions

        def initialize(raw)
            Util.deep_freeze(raw)
            @build_commit = raw["build_commit"]
            @built_at = Util.time_or_nil(raw["built_at"])
            @fetched_at = Util.time_or_nil(raw["fetched_at"])
            @run_id = raw["run_id"]
            @tool_versions = raw["tool_versions"].is_a?(Hash) ? raw["tool_versions"] : nil
            freeze
        end
    end

    # How a set was made and chosen. The schema allows more fields than the
    # typed ones; they stay in #raw.
    class Provenance
        attr_reader :build, :adapter_version, :input_sha256, :carried_from_release, :selection_reason, :decision, :raw

        def initialize(raw)
            raw = {} if raw.nil? # a set with no provenance (a non-object fails the load: Release.check_station!)
            @raw = Util.deep_freeze(raw)
            # A missing build happens only in malformed input: nil, and the load goes on (spec §4.6).
            @build = raw["build"].is_a?(Hash) ? ProvenanceBuild.new(raw["build"]) : nil
            @adapter_version = raw["adapter_version"]
            @input_sha256 = raw["input_sha256"]
            @carried_from_release = raw["carried_from_release"]
            @selection_reason = raw["selection_reason"]
            @decision = raw["decision"]
            freeze
        end
    end

    # The time-base annotation of a gauge set's record (spec §4.5). correction
    # is a frozen Hash {"from", "to"} or nil; each evidence entry is a frozen
    # Hash with the keys comparator_kind, comparator_id, distance_km, lag_min
    # and detail (nil when the file leaves one out).
    class TimeBase
        EVIDENCE_KEYS = %w[comparator_kind comparator_id distance_km lag_min detail].freeze

        attr_reader :code, :reason, :declared, :published, :correction, :months_dropped, :decided_in,
                    :decided_build_commit, :evidence

        def initialize(raw)
            Util.deep_freeze(raw)
            @code = Util.enum(raw["code"], ENUMS[:time_base_code])
            @reason = raw["reason"]
            @declared = raw["declared"]
            @published = raw["published"]
            corr = raw["correction"]
            @correction = corr.is_a?(Hash) ? { "from" => corr["from"], "to" => corr["to"] }.freeze : nil
            @months_dropped = Array(raw["months_dropped"]).freeze
            @decided_in = raw["decided_in"]
            @decided_build_commit = raw["decided_build_commit"]
            @evidence = Array(raw["evidence"]).select { |e| e.is_a?(Hash) }
                                              .map { |e| EVIDENCE_KEYS.to_h { |k| [k, e[k]] }.freeze }.freeze
            freeze
        end
    end

    # One QC flag of a set: the flag, a one-line reason, and numbers by name (or nil).
    class QcFlag
        attr_reader :flag, :reason, :values

        def initialize(raw)
            Util.deep_freeze(raw)
            @flag = Util.enum(raw["flag"], ENUMS[:qc_flag])
            @reason = raw["reason"]
            @values = raw["values"].is_a?(Hash) ? raw["values"] : nil
            freeze
        end
    end

    class DroppedConstituent
        attr_reader :name, :dropped_reason, :detail

        def initialize(raw)
            Util.deep_freeze(raw)
            @name = raw["name"]
            @dropped_reason = Util.enum(raw["dropped_reason"], ENUMS[:dropped_reason])
            @detail = raw["detail"]
            freeze
        end
    end

    class RecordSpan
        attr_reader :start, :end, :good_samples

        def initialize(raw)
            Util.deep_freeze(raw)
            @start = Util.time(raw["start"])
            @end = Util.time(raw["end"])
            @good_samples = raw["good_samples"]
            freeze
        end
    end

    class Datum
        attr_reader :msl_offset_m, :named

        def initialize(raw)
            Util.deep_freeze(raw)
            @msl_offset_m = raw["msl_offset_m"]
            @named = raw["named"] || {}.freeze
            freeze
        end
    end

    # The accuracy of one set against an official reference, for one window.
    class Validation
        NUMBERS = %w[time_mae_min time_p95_min time_bias_min height_mae_m range_error_m missed_events extra_events].freeze
        attr_reader :set_id, :reference_source, :reference_station, :reference_distance_km, :window,
                    :time_mae_min, :time_p95_min, :time_bias_min, :height_mae_m, :range_error_m,
                    :missed_events, :extra_events, :previous_release

        def initialize(raw, previous: false)
            Util.deep_freeze(raw)
            unless previous
                @set_id = raw["set_id"]
                @reference_source = raw["reference_source"]
                @reference_station = raw["reference_station"]
                @reference_distance_km = raw["reference_distance_km"]
                @window = raw["window"]
                prev = raw["previous_release"]
                @previous_release = prev.is_a?(Hash) ? Validation.new(prev, previous: true) : nil
            end
            # In previous_release a value that is not a number is nil, as in every SDK (spec §4.6).
            NUMBERS.each { |k| instance_variable_set("@#{k}", previous && !Release.real?(raw[k]) ? nil : raw[k]) }
            freeze
        end
    end

    class Fallback
        attr_reader :reason, :basis, :otc_finding, :preferred_set_id, :raw
        def initialize(raw)
            @raw = Util.deep_freeze(raw)
            @reason = Util.enum(raw["reason"], ENUMS[:fallback_reason])
            @basis = raw["basis"]
            @otc_finding = raw["otc_finding"]
            @preferred_set_id = raw["preferred_set_id"]
            freeze
        end
    end

    class SourceRecord
        attr_reader :source, :source_version, :source_record_id, :role, :disposition, :detail,
                    :licence_id, :upstream_licence_id, :published_set_ids, :provenance, :original_metadata,
                    :original_harmonics, :licence, :upstream_licence, :raw
        def initialize(raw, licences:)
            @raw = Util.deep_freeze(raw)
            %w[source source_version source_record_id detail licence_id upstream_licence_id provenance original_harmonics].each do |key|
                instance_variable_set("@#{key}", raw[key])
            end
            @role = Util.enum(raw["role"], ENUMS[:source_role])
            @disposition = Util.enum(raw["disposition"], ENUMS[:source_disposition])
            @published_set_ids = raw["published_set_ids"].freeze
            @original_metadata = raw.fetch("original_metadata", {}.freeze)
            @licence = licences[@licence_id]
            @upstream_licence = licences[@upstream_licence_id]
            [@licence_id, @upstream_licence_id].compact.each do |id|
                raise InvalidReleaseError, "source record #{@source_record_id}: licence #{id} does not resolve" unless licences.key?(id)
            end
            freeze
        end
    end

    class HistoricalOffsetVintage
        attr_reader :publication_year, :source_lifecycle, :removal_events, :current_validity, :current_accuracy,
                    :reference_2020_equivalence, :reference_2020_equivalence_sha256
        def initialize(raw)
            Util.deep_freeze(raw)
            %w[publication_year source_lifecycle removal_events current_validity current_accuracy reference_2020_equivalence reference_2020_equivalence_sha256].each do |key|
                instance_variable_set("@#{key}", raw[key])
            end
            freeze
        end
    end

    class HistoricalOffsetProvenance
        attr_reader :source_manifest_sha256, :input_sha256, :book, :annual_table_row, :printed_page, :pdf_page,
                    :raw_row_text, :raw_values_json, :id_crosswalk, :reference_binding, :acceptance_report_sha256
        def initialize(raw)
            Util.deep_freeze(raw)
            %w[source_manifest_sha256 input_sha256 book annual_table_row printed_page pdf_page raw_row_text raw_values_json id_crosswalk reference_binding acceptance_report_sha256].each do |key|
                instance_variable_set("@#{key}", raw[key])
            end
            freeze
        end
    end

    class SubordinateOffsets
        attr_reader :reference_station_id, :time_offset_high_min, :time_offset_low_min, :height_offset_high,
                    :height_offset_low, :height_adjusted_type, :licence_id, :offset_id, :source, :source_type,
                    :source_version, :source_record_id, :qc_status, :qc_flags, :fallback, :vintage, :provenance

        def initialize(raw)
            Util.deep_freeze(raw)
            @reference_station_id = raw["reference_station_id"]
            @time_offset_high_min = raw["time_offset_high_min"]
            @time_offset_low_min = raw["time_offset_low_min"]
            @height_offset_high = raw["height_offset_high"]
            @height_offset_low = raw["height_offset_low"]
            @height_adjusted_type = Util.enum(raw["height_adjusted_type"], ENUMS[:height_adjusted_type])
            @licence_id = raw["licence_id"]
            %w[offset_id source source_version source_record_id].each { |key| instance_variable_set("@#{key}", raw[key]) }
            @source_type = Util.enum(raw["source_type"], ENUMS[:source_type])
            @qc_status = Util.enum(raw["qc_status"], ENUMS[:qc_status])
            @qc_flags = Array(raw["qc_flags"]).map { |f| QcFlag.new(f) }.freeze
            @fallback = raw["fallback"] && Fallback.new(raw["fallback"])
            @vintage = raw["vintage"] && HistoricalOffsetVintage.new(raw["vintage"])
            @provenance = raw["provenance"] && HistoricalOffsetProvenance.new(raw["provenance"])
            freeze
        end
    end

    # The constants from one source record (spec §4.5).
    class ConstantSet
        attr_reader :set_id, :source, :source_type, :quantity, :source_record_id, :source_version, :record_span,
                    :datum, :qc_status, :qc_flags, :dropped_constituents, :time_base, :convention, :licence, :provenance,
                    :validation, :constituents, :fallback, :raw

        def initialize(raw, convention:, licence:, validation:, recommended:)
            @raw = Util.deep_freeze(raw)
            @fallback = raw["fallback"] && Fallback.new(raw["fallback"])
            @set_id = raw["set_id"]
            @source = raw["source"]
            @source_type = Util.enum(raw["source_type"], ENUMS[:source_type])
            @quantity = Util.enum(raw["quantity"], ENUMS[:quantity])
            @source_record_id = raw["source_record_id"]
            @source_version = raw["source_version"]
            @record_span = raw["record_span"].is_a?(Hash) ? RecordSpan.new(raw["record_span"]) : nil
            @datum = raw["datum"].is_a?(Hash) ? Datum.new(raw["datum"]) : nil
            @qc_status = Util.enum(raw["qc_status"], ENUMS[:qc_status])
            @qc_flags = (raw["qc_flags"] || []).map { |f| QcFlag.new(f) }.freeze
            @dropped_constituents = (raw["dropped_constituents"] || []).map { |d| DroppedConstituent.new(d) }.freeze
            @time_base = raw["time_base"].is_a?(Hash) ? TimeBase.new(raw["time_base"]) : nil
            @convention = convention
            @licence = licence
            @provenance = Provenance.new(raw["provenance"])
            @validation = validation.freeze
            @constituents = (raw["constituents"] || []).map { |c| Constituent.new(c) }.freeze
            @by_name = @constituents.to_h { |c| [c.name, c] }.freeze
            @recommended = recommended
            freeze
        end

        def recommended?
            @recommended
        end

        # Looked up by OTC canonical name, case-sensitive.
        def constituent(name)
            @by_name[name]
        end
    end

    # An active station (spec §4.4).
    class Station
        attr_reader :station_id, :name, :country, :lat, :lon, :type, :kind, :timezone, :aliases, :status,
                    :recommended_set, :subordinate_offsets, :validation, :recommended_is_fallback, :source_records, :raw

        # origin: the producing Release's private token; it retains no Release
        # or reader descriptor (attribution still checks identity, spec §4.6).
        def initialize(raw, sets:, kind:, validation:, origin: nil, licences: {})
            @raw = Util.deep_freeze(raw)
            @recommended_is_fallback = raw["recommended_is_fallback"]
            @source_records = Array(raw["source_records"]).map { |r| SourceRecord.new(r, licences: licences) }.freeze
            @origin = origin.is_a?(Release) ? origin.__send__(:station_origin) : origin
            @station_id = raw["station_id"]
            @name = raw["name"]
            @country = raw["country"]
            @lat = raw["lat"]
            @lon = raw["lon"]
            @type = Util.enum(raw["type"], ENUMS[:station_type])
            @kind = kind
            @timezone = raw["timezone"]
            # a line with no status is an active station (CR2 DR28)
            @status = Util.enum(raw["status"].nil? ? "active" : raw["status"], ENUMS[:station_status])
            @aliases = (raw["aliases"] || {}).to_h do |system, ids|
                [system.to_sym, (ids.is_a?(Array) ? ids : [ids]).freeze]
            end.freeze
            @sets = sets.freeze
            @recommended_set = sets.find(&:recommended?)
            off = raw["subordinate_offsets"]
            @subordinate_offsets = off.is_a?(Hash) ? SubordinateOffsets.new(off) : nil
            @validation = validation.freeze
            freeze
        end

        def reference?
            @type == :reference
        end

        def subordinate?
            @type == :subordinate
        end

        def tide?
            @kind == :tide
        end

        def current?
            @kind == :current
        end

        # The recommended set first, then the others by set_id. Sets with
        # qc_status no_constants (listed, with no fitted constants) are left
        # out unless include_no_constants is true.
        def constant_sets(include_no_constants: false)
            unless include_no_constants == true || include_no_constants == false
                raise InvalidArgumentError, "include_no_constants must be true or false"
            end
            list = include_no_constants ? @sets : @sets.reject { |s| s.qc_status == :no_constants }
            rec = list.select(&:recommended?)
            (rec + (list - rec).sort_by(&:set_id)).freeze
        end

        def constant_set(set_id)
            @sets.find { |s| s.set_id == set_id }
        end
    end

    # A removed station id: why it was removed and, when merged, the station
    # that holds its records.
    class Tombstone
        attr_reader :station_id, :name, :status, :removed_in, :removed_reason, :merged_into, :detail, :raw

        def initialize(raw)
            @raw = Util.deep_freeze(raw)
            @station_id = raw["station_id"]
            @name = raw["name"]
            @status = Util.enum(raw["status"], ENUMS[:station_status])
            @removed_in = raw["removed_in"]
            @removed_reason = Util.enum(raw["removed_reason"], ENUMS[:removed_reason])
            @merged_into = raw["merged_into"]
            @detail = raw["detail"]
            freeze
        end
    end

    # Counts by type, kind and country (active stations) and by source and
    # qc_status (constant sets). Each is a frozen Hash {value => count}.
    class Stats
        attr_reader :type, :kind, :country, :source, :qc_status

        def initialize(type:, kind:, country:, source:, qc_status:)
            @type = type
            @kind = kind
            @country = country
            @source = source
            @qc_status = qc_status
            freeze
        end
    end

    # A station and its great-circle distance from the query point.
    class Nearby
        attr_reader :station, :distance_km

        def initialize(station, distance_km)
            @station = station
            @distance_km = distance_km
            freeze
        end
    end

    class UpdateResult
        attr_reader :updated, :from, :to

        def initialize(updated, from, to)
            @updated = updated
            @from = from
            @to = to
            freeze
        end
    end
end
