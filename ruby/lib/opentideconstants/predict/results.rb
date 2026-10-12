class OpenTideConstants
    class HeightPoint
        attr_reader :time, :height_m, :local_time, :utc_offset_s
        def initialize(time: nil, height_m: nil, local_time: nil, utc_offset_s: nil, _local: nil)
            @time = Util.deep_freeze(time)
            @height_m = Util.deep_freeze(height_m)
            @local_time = Util.deep_freeze(local_time)
            @utc_offset_s = Util.deep_freeze(utc_offset_s)
            @_local = _local
            freeze
        end
        def local_time_object
            @_local
        end
    end
    class Extreme
        attr_reader :time, :type, :height_m, :local_time, :utc_offset_s
        def initialize(time: nil, type: nil, height_m: nil, local_time: nil, utc_offset_s: nil, _local: nil)
            @time = Util.deep_freeze(time)
            @type = Util.deep_freeze(type)
            @height_m = Util.deep_freeze(height_m)
            @local_time = Util.deep_freeze(local_time)
            @utc_offset_s = Util.deep_freeze(utc_offset_s)
            @_local = _local
            freeze
        end
        def local_time_object
            @_local
        end
    end
    class CurrentPoint
        attr_reader :time, :velocity_major_ms, :velocity_minor_ms, :speed_ms, :direction_deg, :local_time, :utc_offset_s
        def initialize(time: nil, velocity_major_ms: nil, velocity_minor_ms: nil, speed_ms: nil, direction_deg: nil, local_time: nil, utc_offset_s: nil, _local: nil)
            @time = Util.deep_freeze(time)
            @velocity_major_ms = Util.deep_freeze(velocity_major_ms)
            @velocity_minor_ms = Util.deep_freeze(velocity_minor_ms)
            @speed_ms = Util.deep_freeze(speed_ms)
            @direction_deg = Util.deep_freeze(direction_deg)
            @local_time = Util.deep_freeze(local_time)
            @utc_offset_s = Util.deep_freeze(utc_offset_s)
            @_local = _local
            freeze
        end
        def local_time_object
            @_local
        end
    end
    class CurrentEvent
        attr_reader :time, :type, :velocity_ms, :direction_deg, :local_time, :utc_offset_s
        def initialize(time: nil, type: nil, velocity_ms: nil, direction_deg: nil, local_time: nil, utc_offset_s: nil, _local: nil)
            @time = Util.deep_freeze(time)
            @type = Util.deep_freeze(type)
            @velocity_ms = Util.deep_freeze(velocity_ms)
            @direction_deg = Util.deep_freeze(direction_deg)
            @local_time = Util.deep_freeze(local_time)
            @utc_offset_s = Util.deep_freeze(utc_offset_s)
            @_local = _local
            freeze
        end
        def local_time_object
            @_local
        end
    end
    class HeightSeries
        attr_reader :items, :station_id, :timezone, :method, :set_id, :convention_id, :astro_table_id, :reference_station_id, :reference_bin, :datum, :datum_name, :datum_kind, :datum_uncertainty_m, :tz, :tz_version, :release, :algorithm, :offset_id, :offset_source, :offset_source_version, :historical_offsets, :current_validity, :current_accuracy, :reference_set_id, :reference_source_version, :reference_2020_equivalence, :source_note
        def initialize(items: [], station_id: nil, timezone: nil, method: nil, set_id: nil, convention_id: nil, astro_table_id: nil, reference_station_id: nil, reference_bin: nil, datum: nil, datum_name: nil, datum_kind: nil, datum_uncertainty_m: nil, tz: nil, tz_version: nil, release: nil, algorithm: nil, offset_id: nil, offset_source: nil, offset_source_version: nil, historical_offsets: false, current_validity: nil, current_accuracy: nil, reference_set_id: nil, reference_source_version: nil, reference_2020_equivalence: nil, source_note: nil, _local: nil)
            @items = Util.deep_freeze(items)
            @station_id = Util.deep_freeze(station_id)
            @timezone = Util.deep_freeze(timezone)
            @method = Util.deep_freeze(method)
            @set_id = Util.deep_freeze(set_id)
            @convention_id = Util.deep_freeze(convention_id)
            @astro_table_id = Util.deep_freeze(astro_table_id)
            @reference_station_id = Util.deep_freeze(reference_station_id)
            @reference_bin = Util.deep_freeze(reference_bin)
            @datum = Util.deep_freeze(datum)
            @datum_name = Util.deep_freeze(datum_name)
            @datum_kind = Util.deep_freeze(datum_kind)
            @datum_uncertainty_m = Util.deep_freeze(datum_uncertainty_m)
            @tz = Util.deep_freeze(tz)
            @tz_version = Util.deep_freeze(tz_version)
            @release = Util.deep_freeze(release)
            @algorithm = Util.deep_freeze(algorithm)
            @offset_id = Util.deep_freeze(offset_id)
            @offset_source = Util.deep_freeze(offset_source)
            @offset_source_version = Util.deep_freeze(offset_source_version)
            @historical_offsets = Util.deep_freeze(historical_offsets)
            @current_validity = Util.deep_freeze(current_validity)
            @current_accuracy = Util.deep_freeze(current_accuracy)
            @reference_set_id = Util.deep_freeze(reference_set_id)
            @reference_source_version = Util.deep_freeze(reference_source_version)
            @reference_2020_equivalence = Util.deep_freeze(reference_2020_equivalence)
            @source_note = Util.deep_freeze(source_note)
            @_local = _local
            freeze
        end
        def to_local(tz = 'station')
            Predict.localize(self, tz)
        end
    end
    class ExtremeList
        attr_reader :items, :station_id, :timezone, :method, :set_id, :convention_id, :astro_table_id, :reference_station_id, :reference_bin, :datum, :datum_name, :datum_kind, :datum_uncertainty_m, :tz, :tz_version, :release, :algorithm, :offset_id, :offset_source, :offset_source_version, :historical_offsets, :current_validity, :current_accuracy, :reference_set_id, :reference_source_version, :reference_2020_equivalence, :source_note
        def initialize(items: [], station_id: nil, timezone: nil, method: nil, set_id: nil, convention_id: nil, astro_table_id: nil, reference_station_id: nil, reference_bin: nil, datum: nil, datum_name: nil, datum_kind: nil, datum_uncertainty_m: nil, tz: nil, tz_version: nil, release: nil, algorithm: nil, offset_id: nil, offset_source: nil, offset_source_version: nil, historical_offsets: false, current_validity: nil, current_accuracy: nil, reference_set_id: nil, reference_source_version: nil, reference_2020_equivalence: nil, source_note: nil, _local: nil)
            @items = Util.deep_freeze(items)
            @station_id = Util.deep_freeze(station_id)
            @timezone = Util.deep_freeze(timezone)
            @method = Util.deep_freeze(method)
            @set_id = Util.deep_freeze(set_id)
            @convention_id = Util.deep_freeze(convention_id)
            @astro_table_id = Util.deep_freeze(astro_table_id)
            @reference_station_id = Util.deep_freeze(reference_station_id)
            @reference_bin = Util.deep_freeze(reference_bin)
            @datum = Util.deep_freeze(datum)
            @datum_name = Util.deep_freeze(datum_name)
            @datum_kind = Util.deep_freeze(datum_kind)
            @datum_uncertainty_m = Util.deep_freeze(datum_uncertainty_m)
            @tz = Util.deep_freeze(tz)
            @tz_version = Util.deep_freeze(tz_version)
            @release = Util.deep_freeze(release)
            @algorithm = Util.deep_freeze(algorithm)
            @offset_id = Util.deep_freeze(offset_id)
            @offset_source = Util.deep_freeze(offset_source)
            @offset_source_version = Util.deep_freeze(offset_source_version)
            @historical_offsets = Util.deep_freeze(historical_offsets)
            @current_validity = Util.deep_freeze(current_validity)
            @current_accuracy = Util.deep_freeze(current_accuracy)
            @reference_set_id = Util.deep_freeze(reference_set_id)
            @reference_source_version = Util.deep_freeze(reference_source_version)
            @reference_2020_equivalence = Util.deep_freeze(reference_2020_equivalence)
            @source_note = Util.deep_freeze(source_note)
            @_local = _local
            freeze
        end
        def to_local(tz = 'station')
            Predict.localize(self, tz)
        end
    end
    class CurrentSeries
        attr_reader :items, :station_id, :timezone, :method, :set_id, :convention_id, :astro_table_id, :reference_station_id, :reference_bin, :datum, :datum_name, :datum_kind, :datum_uncertainty_m, :bin_number, :tz, :tz_version, :release, :algorithm
        def initialize(items: [], station_id: nil, timezone: nil, method: nil, set_id: nil, convention_id: nil, astro_table_id: nil, reference_station_id: nil, reference_bin: nil, datum: nil, datum_name: nil, datum_kind: nil, datum_uncertainty_m: nil, bin_number: nil, tz: nil, tz_version: nil, release: nil, algorithm: nil, _local: nil)
            @items = Util.deep_freeze(items)
            @station_id = Util.deep_freeze(station_id)
            @timezone = Util.deep_freeze(timezone)
            @method = Util.deep_freeze(method)
            @set_id = Util.deep_freeze(set_id)
            @convention_id = Util.deep_freeze(convention_id)
            @astro_table_id = Util.deep_freeze(astro_table_id)
            @reference_station_id = Util.deep_freeze(reference_station_id)
            @reference_bin = Util.deep_freeze(reference_bin)
            @datum = Util.deep_freeze(datum)
            @datum_name = Util.deep_freeze(datum_name)
            @datum_kind = Util.deep_freeze(datum_kind)
            @datum_uncertainty_m = Util.deep_freeze(datum_uncertainty_m)
            @bin_number = Util.deep_freeze(bin_number)
            @tz = Util.deep_freeze(tz)
            @tz_version = Util.deep_freeze(tz_version)
            @release = Util.deep_freeze(release)
            @algorithm = Util.deep_freeze(algorithm)
            @_local = _local
            freeze
        end
        def to_local(tz = 'station')
            Predict.localize(self, tz)
        end
    end
    class CurrentEventList
        attr_reader :items, :station_id, :timezone, :method, :set_id, :convention_id, :astro_table_id, :reference_station_id, :reference_bin, :datum, :datum_name, :datum_kind, :datum_uncertainty_m, :bin_number, :omitted_event_types, :tz, :tz_version, :release, :algorithm
        def initialize(items: [], station_id: nil, timezone: nil, method: nil, set_id: nil, convention_id: nil, astro_table_id: nil, reference_station_id: nil, reference_bin: nil, datum: nil, datum_name: nil, datum_kind: nil, datum_uncertainty_m: nil, bin_number: nil, omitted_event_types: nil, tz: nil, tz_version: nil, release: nil, algorithm: nil, _local: nil)
            @items = Util.deep_freeze(items)
            @station_id = Util.deep_freeze(station_id)
            @timezone = Util.deep_freeze(timezone)
            @method = Util.deep_freeze(method)
            @set_id = Util.deep_freeze(set_id)
            @convention_id = Util.deep_freeze(convention_id)
            @astro_table_id = Util.deep_freeze(astro_table_id)
            @reference_station_id = Util.deep_freeze(reference_station_id)
            @reference_bin = Util.deep_freeze(reference_bin)
            @datum = Util.deep_freeze(datum)
            @datum_name = Util.deep_freeze(datum_name)
            @datum_kind = Util.deep_freeze(datum_kind)
            @datum_uncertainty_m = Util.deep_freeze(datum_uncertainty_m)
            @bin_number = Util.deep_freeze(bin_number)
            @omitted_event_types = Util.deep_freeze(omitted_event_types)
            @tz = Util.deep_freeze(tz)
            @tz_version = Util.deep_freeze(tz_version)
            @release = Util.deep_freeze(release)
            @algorithm = Util.deep_freeze(algorithm)
            @_local = _local
            freeze
        end
        def to_local(tz = 'station')
            Predict.localize(self, tz)
        end
    end
    class DatumInfo
        attr_reader :set_id, :zero, :zero_name, :chart_datum, :msl_offset_m, :levels
        def initialize(set_id: nil, zero: nil, zero_name: nil, chart_datum: nil, msl_offset_m: nil, levels: [], _local: nil)
            @set_id = Util.deep_freeze(set_id)
            @zero = Util.deep_freeze(zero)
            @zero_name = Util.deep_freeze(zero_name)
            @chart_datum = Util.deep_freeze(chart_datum)
            @msl_offset_m = Util.deep_freeze(msl_offset_m)
            @levels = Util.deep_freeze(levels)
            @_local = _local
            freeze
        end
    end
    class DatumLevel
        attr_reader :key, :value_m, :above_chart_m, :kind, :method, :source_name, :epoch, :data_span, :control_station_id, :control_set_id, :control_source_id, :uncertainty_m, :uncertainty_basis, :flags
        def initialize(key: nil, value_m: nil, above_chart_m: nil, kind: nil, method: nil, source_name: nil, epoch: nil, data_span: nil, control_station_id: nil, control_set_id: nil, control_source_id: nil, uncertainty_m: nil, uncertainty_basis: nil, flags: [], _local: nil)
            @key = Util.deep_freeze(key)
            @value_m = Util.deep_freeze(value_m)
            @above_chart_m = Util.deep_freeze(above_chart_m)
            @kind = Util.deep_freeze(kind)
            @method = Util.deep_freeze(method)
            @source_name = Util.deep_freeze(source_name)
            @epoch = Util.deep_freeze(epoch)
            @data_span = Util.deep_freeze(data_span)
            @control_station_id = Util.deep_freeze(control_station_id)
            @control_set_id = Util.deep_freeze(control_set_id)
            @control_source_id = Util.deep_freeze(control_source_id)
            @uncertainty_m = Util.deep_freeze(uncertainty_m)
            @uncertainty_basis = Util.deep_freeze(uncertainty_basis)
            @flags = Util.deep_freeze(flags)
            @_local = _local
            freeze
        end
    end
    class Ranges
        attr_reader :mn, :gt, :dhq, :dlq
        def initialize(mn: nil, gt: nil, dhq: nil, dlq: nil, _local: nil)
            @mn = Util.deep_freeze(mn)
            @gt = Util.deep_freeze(gt)
            @dhq = Util.deep_freeze(dhq)
            @dlq = Util.deep_freeze(dlq)
            @_local = _local
            freeze
        end
    end
end
