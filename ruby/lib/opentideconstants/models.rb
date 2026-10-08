require "time"

class OpenTideConstants
    # Helpers shared by the data objects. Every object is frozen and keeps the
    # parsed JSON object as #raw (a deep-frozen Hash), so a caller can read
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

        def time(value)
            return nil if value.nil?
            Time.iso8601(value).utc.freeze
        rescue ArgumentError
            raise InvalidReleaseError, "bad time: #{value.inspect}"
        end
    end

    ENUMS = {
        kind: %w[tide current],
        station_type: %w[reference subordinate],
        station_status: %w[active removed],
        source_type: %w[official gauge model],
        quantity: %w[water_level current],
        qc_status: %w[accepted fallback excluded],
        phase_reference: %w[greenwich_utc local],
        nodal_handling: %w[f_u_at_prediction none],
        height_adjusted_type: %w[R A],
        dropped_reason: %w[rayleigh noise long_period_rule non_tidal_rule convention other],
        qc_flag: %w[time_base broken_record microtidal non_tidal_signal short_record sibling_disagreement],
        alias_system: %w[noaa gesla ticon xtide kartverket slackwater webcaltides]
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
        attr_reader :datestamp, :format_version, :doi, :files

        def initialize(raw, files)
            Util.deep_freeze(raw)
            @datestamp = raw["datestamp"]
            @format_version = raw["format_version"]
            @doi = raw["doi"]
            @files = files.freeze
            freeze
        end
    end

    class Licence
        attr_reader :licence_id, :spdx, :provider, :citation, :attribution, :url, :raw

        def initialize(raw)
            @raw = Util.deep_freeze(raw)
            @licence_id = raw["licence_id"]
            @spdx = raw["spdx"]
            @provider = raw["provider"]
            @citation = raw["citation"]
            @attribution = raw["attribution"]
            @url = raw["url"]
            freeze
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

    class Provenance
        attr_reader :build_commit, :adapter_version, :input_sha256, :time_base, :selection_reason, :decision, :raw

        def initialize(raw)
            raw ||= {}
            @raw = Util.deep_freeze(raw)
            @build_commit = raw["build_commit"]
            @adapter_version = raw["adapter_version"]
            @input_sha256 = raw["input_sha256"]
            @time_base = raw["time_base"]
            @selection_reason = raw["selection_reason"]
            @decision = raw["decision"]
            freeze
        end
    end

    class QcFlag
        attr_reader :flag, :verdict, :values

        def initialize(raw)
            Util.deep_freeze(raw)
            @flag = Util.enum(raw["flag"], ENUMS[:qc_flag])
            @verdict = raw["verdict"]
            @values = raw["values"]
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
            NUMBERS.each { |k| instance_variable_set("@#{k}", raw[k]) }
            freeze
        end
    end

    class SubordinateOffsets
        attr_reader :reference_station_id, :time_offset_high_min, :time_offset_low_min, :height_offset_high,
                    :height_offset_low, :height_adjusted_type, :licence_id

        def initialize(raw)
            Util.deep_freeze(raw)
            @reference_station_id = raw["reference_station_id"]
            @time_offset_high_min = raw["time_offset_high_min"]
            @time_offset_low_min = raw["time_offset_low_min"]
            @height_offset_high = raw["height_offset_high"]
            @height_offset_low = raw["height_offset_low"]
            @height_adjusted_type = Util.enum(raw["height_adjusted_type"], ENUMS[:height_adjusted_type])
            @licence_id = raw["licence_id"]
            freeze
        end
    end

    # The constants from one source record (spec §4.5).
    class ConstantSet
        attr_reader :set_id, :source, :source_type, :quantity, :source_record_id, :source_version, :record_span,
                    :datum, :qc_status, :qc_flags, :dropped_constituents, :convention, :licence, :provenance,
                    :validation, :constituents, :raw

        def initialize(raw, convention:, licence:, validation:, recommended:)
            @raw = Util.deep_freeze(raw)
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
                    :recommended_set, :subordinate_offsets, :validation, :raw

        def initialize(raw, sets:, kind:, validation:)
            @raw = Util.deep_freeze(raw)
            @station_id = raw["station_id"]
            @name = raw["name"]
            @country = raw["country"]
            @lat = raw["lat"]
            @lon = raw["lon"]
            @type = Util.enum(raw["type"], ENUMS[:station_type])
            @kind = kind
            @timezone = raw["timezone"]
            @status = Util.enum(raw["status"], ENUMS[:station_status])
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
        # qc_status excluded are left out unless include_excluded is true.
        def constant_sets(include_excluded: false)
            unless include_excluded == true || include_excluded == false
                raise InvalidArgumentError, "include_excluded must be true or false"
            end
            list = include_excluded ? @sets : @sets.reject { |s| s.qc_status == :excluded }
            rec = list.select(&:recommended?)
            (rec + (list - rec).sort_by(&:set_id)).freeze
        end

        def constant_set(set_id)
            @sets.find { |s| s.set_id == set_id }
        end
    end

    # A removed station.
    class Tombstone
        attr_reader :station_id, :name, :status, :removed_in, :removed_reason, :raw

        def initialize(raw)
            @raw = Util.deep_freeze(raw)
            @station_id = raw["station_id"]
            @name = raw["name"]
            @status = Util.enum(raw["status"], ENUMS[:station_status])
            @removed_in = raw["removed_in"]
            @removed_reason = raw["removed_reason"]
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
