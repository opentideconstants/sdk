class OpenTideConstants
    module Predict
        Context = Struct.new(:station, :constants, :table, :method, :reference, :reference_bin, :bin_number, :offsets,
                             :total, :minor, :current_bin, :sigma, :datum_name, :datum_kind, :datum_uncertainty, :omitted, keyword_init: true)
        module_function
        def astro_table(release, id = nil)
            release.send(:check_open!)
            raise InvalidArgumentError, "astro table id must be a string" unless id.nil? || id.is_a?(String)
            id ||= release.conventions.find { |c| c.raw["astro_table_id"] }&.raw&.fetch("astro_table_id")
            return nil unless id
            raw = Array(release.instance_variable_get(:@meta)["astro_tables"]).find { |t| t["astro_table_id"] == id }
            raw && AstroTable.new(raw)
        end
        def station_for(release, station)
            release.send(:check_open!)
            return release.require_station(station) if station.is_a?(String)
            raise InvalidArgumentError, "station must be a Station or station id" unless station.is_a?(Station)
            actual = release.station(station.station_id)
            raise InvalidArgumentError, "station is not from this release" unless actual && actual.raw == station.raw
            actual
        end
        def options(set_id, datum = nil, bin_number = nil)
            raise InvalidArgumentError, "set_id must be a string" unless set_id.nil? || set_id.is_a?(String)
            raise InvalidArgumentError, "datum must be a string" unless datum.nil? || datum.is_a?(String)
            unless bin_number.nil? || bin_number.is_a?(Integer) && bin_number.between?(1, 2**53 - 1)
                raise InvalidArgumentError, "bin_number must be an integer from1to2^53-1"
            end
        end
        def window(start, stop, step = nil)
            first, last = instant(start), instant(stop)
            raise InvalidArgumentError, "start must not be after stop" if first > last
            raise InvalidArgumentError, "step_s must be a positive integer" unless step.nil? || step.is_a?(Integer) && step > 0
            [first, last]
        end
        def chosen(release, station, set_id)
            return station.recommended_set if set_id.nil?
            constants = station.constant_set(set_id)
            raise InvalidArgumentError, "set_id #{set_id.inspect} is not a set of #{station.station_id}" unless constants
            if release.instance_variable_get(:@commercial_only) && constants.licence.commercial_use != true
                raise InvalidArgumentError, "commercial_only refuses set_id"
            end
            constants
        end
        def table_for(release, constants)
            convention = constants.convention
            unless convention.v0_model == "schureman_tcd" && convention.nodal_handling == :f_u_at_prediction
                raise UnsupportedConventionError, "unsupported convention #{convention.convention_id}"
            end
            ident = convention.raw["astro_table_id"] || ""
            table = astro_table(release, ident) || (raise NoAstroTableError, "release #{release.datestamp} has no astro table \"#{ident}\" for convention \"#{convention.convention_id}\". Format 1.0 requires astro_tables when a convention uses f_u_at_prediction (since the schema revision of site PR #45); this file was written before that revision or is invalid.")
            raw = table.instance_variable_get(:@raw)
            unless raw["v0_model"] == convention.v0_model && (convention.tables_sha256.nil? || raw["tables_sha256"] == convention.tables_sha256)
                raise UnsupportedConventionError, "astro table #{ident} is incompatible with convention #{convention.convention_id}"
            end
            table
        end
        def unavailable(missing)
            raise DatumUnavailableError.new("datum is missing #{missing}", missing: missing)
        end
        def datum_term(raw, datum, context, published: false)
            datum ||= "mean_level"
            if datum == "mean_level" && !published
                context.datum_name = datum
                return 0.0
            end
            d = raw || {}
            named, basis = d["named"] || {}, d["basis"] || {}
            unavailable("msl_offset_m") if d["msl_offset_m"].nil?
            if datum == "zero" && !published
                context.datum_name = d["zero_name"] || d["zero"] || "unknown"
                return d["msl_offset_m"]
            end
            key = datum == "chart" ? d["chart_datum"] : datum
            unavailable("chart_datum") if datum == "chart" && key.nil?
            unavailable(key) unless named.key?(key)
            b = basis[key] || {}
            unavailable("published chart datum") if published && b["kind"] != "published"
            context.datum_name, context.datum_kind, context.datum_uncertainty = key, b["kind"], b["uncertainty_m"]
            d["msl_offset_m"] - named[key]
        end
        def subordinate_datum(offsets, datum, context)
            d = offsets["datum"] || {}
            named, basis = d["named"] || {}, d["basis"] || {}
            chart = d["chart_datum"]
            key = datum.nil? || datum == "chart" ? chart : datum
            term = if datum.nil? || datum == "chart" then 0.0 elsif named.key?(key) then named.fetch(chart, 0.0) - named[key] else unavailable(datum) end
            b = basis[key] || {}
            context.datum_name, context.datum_kind, context.datum_uncertainty = key, b["kind"], b["uncertainty_m"]
            term
        end
        def reference(release, offsets, quantity, bin_number = nil)
            ident = offsets["reference_station_id"]
            station = release.station(ident)
            constants = station&.constant_sets(include_no_constants: true)&.find do |s|
                s.quantity == quantity.to_sym && %i[ok flagged].include?(s.qc_status) && (quantity == "water_level" ? s.source == "noaa" : Array(s.raw["current_bins"]).any? { |b| b["bin"] == bin_number })
            end
            raise ReferenceUnavailableError.new("reference #{ident} has no usable set", reference_station_id: ident) unless constants
            if release.instance_variable_get(:@commercial_only)
                [offsets["licence_id"], constants.licence.licence_id].compact.each do |id|
                    unless release.licence(id)&.commercial_use == true
                        raise ReferenceUnavailableError.new("commercial_only refuses reference licence #{id}", reference_station_id: ident)
                    end
                end
            end
            [station, constants]
        end
        def current_bin(station, bins, requested)
            selected = requested || station.raw["default_current_bin"] || bins.map { |b| b["bin"] }.min
            bins.find { |b| b["bin"] == selected } || (raise BinNotFoundError, "bin_number #{selected} not available")
        end
        def current_context(context, row)
            context.current_bin = row
            azimuth, flood = row.fetch("azimuth_deg", 0.0), row["mean_flood_dir_deg"]
            context.sigma = flood.nil? || Math.cos((azimuth - flood) * RAD) >= 0 ? 1.0 : -1.0
            context.total = Sum.new(context.table, row["constituents"] || [], amplitude: "major_amplitude_ms", phase: "major_phase_deg", mean: row.fetch("mean_major_ms", 0.0))
            context.minor = Sum.new(context.table, row["constituents"] || [], amplitude: "minor_amplitude_ms", phase: "minor_phase_deg", mean: row.fetch("mean_minor_ms", 0.0))
        end
        def context(release, station, quantity, set_id, datum = nil, bin_number = nil, series: false, offset_id: nil)
            station = station_for(release, station)
            options(set_id, datum, bin_number)
            raise InvalidArgumentError, "offset_id must be a string" unless offset_id.nil? || offset_id.is_a?(String)
            raise InvalidArgumentError, "set_id and offset_id are mutually exclusive" if offset_id && set_id
            constants = chosen(release, station, set_id)
            usable = constants && %i[ok flagged].include?(constants.qc_status)
            tide, currents = station.raw.values_at("subordinate_offsets", "current_offsets")
            historical = tide && tide["offset_id"]
            if offset_id
                raise InvalidArgumentError, "offset_id not a profile of station" unless historical && historical == offset_id
                usable = false
            end
            e = release.instance_variable_get(:@by_id)[station.station_id]
            better = historical && offset_id.nil? && (e.sets.any? { |cs| cs["set_id"] == e.eff_id && %w[ok flagged].include?(cs["qc_status"]) } || !release.send(:eligible_paths, e, false, false, historical: false).empty?)
            if set_id.nil? && !usable && station.type == :subordinate && (tide && !better || currents && !currents.empty?)
                if tide
                    raise QuantityMismatchError, "tide offsets need water_level" unless quantity == "water_level"
                    kind = tide["height_adjusted_type"]
                    raise InvalidArgumentError, "height_adjusted_type #{kind.inspect} must be R or A" unless %w[R A].include?(kind)
                    raise HistoricalOffsetsExcludedError, "historical_offsets_policy=exclude refuses historical prediction" if historical && release.historical_offsets_policy == :exclude
                    ref, constants = reference(release, tide, quantity)
                    require_historical(release, tide, constants) if historical
                    table = table_for(release, constants)
                    c = Context.new(station: station, constants: constants, table: table, method: "harmonic", reference: ref, offsets: tide)
                    Sum.new(table, constants.raw["constituents"] || [])
                    ref_term = datum_term(constants.raw["datum"], "chart", Context.new, published: true)
                    sub_term = subordinate_datum(tide, datum, c)
                    high_t, low_t = %w[high low].map { |k| tide["time_offset_#{k}_min"] || 0.0 }
                    identity = kind == "R" ? 1.0 : 0.0
                    high_h, low_h = %w[high low].map { |k| tide["height_offset_#{k}"].nil? ? identity : tide["height_offset_#{k}"] }
                    raise InvalidArgumentError, "height_offset ratio must be positive" if kind == "R" && (high_h <= 0 || low_h <= 0)
                    if high_t == low_t && high_h == low_h
                        c.method = "folded_offsets"
                        multiplier, add = kind == "R" ? [high_h, 0.0] : [1.0, high_h]
                        c.total = Sum.new(table, constants.raw["constituents"] || [], mean: multiplier * ref_term + add + sub_term, multiplier: multiplier, shift_hours: high_t / 60.0)
                    else
                        c.method = "offsets"
                        c.total = Sum.new(table, constants.raw["constituents"] || [], mean: ref_term)
                        c.offsets = tide.merge("_subterm" => sub_term)
                        raise ExtremesOnlyError, "high and low offsets differ; no exact curve" if series
                    end
                    return c
                end
                raise QuantityMismatchError, "current offsets need current" unless quantity == "current"
                entry = current_bin(station, currents, bin_number)
                ref, constants = reference(release, entry, quantity, entry["reference_bin"])
                c = Context.new(station: station, constants: constants, table: table_for(release, constants), method: "offsets", reference: ref, reference_bin: entry["reference_bin"], bin_number: entry["bin"], offsets: entry)
                current_context(c, current_bin(ref, constants.raw["current_bins"] || [], c.reference_bin))
                raise ExtremesOnlyError, "subordinate currents provide events only" if series
                return c
            end
            raise NoConstantsError, "no usable constants#{release.instance_variable_get(:@commercial_only) ? ' (commercial_only)' : ''}" unless usable
            raise QuantityMismatchError, "#{quantity} requires that quantity" unless constants.quantity == quantity.to_sym
            c = Context.new(station: station, constants: constants, table: table_for(release, constants), method: "harmonic")
            if quantity == "water_level"
                c.total = Sum.new(c.table, constants.raw["constituents"] || [])
                c.total.mean = datum_term(constants.raw["datum"], datum, c)
            else
                row = current_bin(station, constants.raw["current_bins"] || [], bin_number)
                c.bin_number = row["bin"]
                current_context(c, row)
            end
            c
        end
        def require_historical(release, offsets, constants)
            Release.check_historical_offsets!(offsets, "prediction")
            binding = offsets.dig("provenance", "reference_binding")
            eligible = constants.set_id.start_with?(offsets["reference_station_id"] + "/") && constants.source == "noaa" && constants.source_record_id == binding["noaa_id"] && constants.quantity == :water_level && constants.qc_status == :ok && constants.fallback.nil?
            d = constants.raw["datum"] || {}
            eligible &&= constants.convention.v0_model == "schureman_tcd" && constants.convention.nodal_handling == :f_u_at_prediction && d["chart_datum"] == "mllw" && !d["msl_offset_m"].nil? && d.dig("named", "mllw") == 0.0 && d.dig("basis", "mllw", "kind") == "published"
            raise NoConstantsError, "historical offsets ineligible" unless eligible
        end
        def result(release, c, klass, items, datum = nil)
            fields = {items: items, station_id: c.station.station_id, timezone: c.station.timezone, method: c.method.to_sym, set_id: c.constants.set_id, convention_id: c.constants.convention.convention_id, astro_table_id: c.table.instance_variable_get(:@raw)["astro_table_id"], reference_station_id: c.reference&.station_id, reference_bin: c.reference_bin, datum: datum, datum_name: c.datum_name, datum_kind: c.datum_kind, datum_uncertainty_m: c.datum_uncertainty, release: release.datestamp, algorithm: "otc-predict-1"}
            fields[:bin_number] = c.bin_number if [CurrentSeries, CurrentEventList].include?(klass)
            fields[:omitted_event_types] = c.omitted if klass == CurrentEventList
            if [HeightSeries, ExtremeList].include?(klass) && c.offsets && c.offsets["offset_id"]
                o, v = c.offsets, c.offsets["vintage"]
                fields.merge!(set_id: nil, offset_id: o["offset_id"], offset_source: o["source"], offset_source_version: o["source_version"], historical_offsets: true, current_validity: v["current_validity"], current_accuracy: v["current_accuracy"], reference_set_id: c.constants.set_id, reference_source_version: c.constants.source_version, reference_2020_equivalence: v["reference_2020_equivalence"], source_note: "OTC historical-offset calculation using NOAA2020 parameters; retired NOAA profile; current validity unestablished; current accuracy unverified.")
            end
            klass.new(**fields)
        end
    end
end
class OpenTideConstants
    module Predict
        module_function
        def current_events(c, start, stop)
            total = Sum.new(c.table, c.current_bin["constituents"] || [], amplitude: "major_amplitude_ms", phase: "major_phase_deg", multiplier: c.sigma, mean: c.sigma * c.current_bin.fetch("mean_major_ms", 0.0))
            candidates = events(total, start, stop).filter_map do |t, kind, value|
                if kind == "high" && value > 0
                    [t, "max_flood", value, c.current_bin["mean_flood_dir_deg"]]
                elsif kind == "low" && value < 0
                    [t, "max_ebb", value, c.current_bin["mean_ebb_dir_deg"]]
                end
            end
            candidates.concat(events(total, start, stop, slack: true).map { |t, kind, _| [t, kind, 0.0, nil] })
            candidates.sort_by(&:first)
        end
        def datum_info(set_id, raw)
            d = raw || {}
            named, basis = d["named"] || {}, d["basis"] || {}
            chart = named[d["chart_datum"]]
            levels = named.keys.sort.map do |key|
                b = basis[key] || {}
                control = b["control"] || {}
                DatumLevel.new(key: key, value_m: named[key], above_chart_m: chart.nil? ? nil : named[key] - chart, kind: b["kind"], method: b["method"], source_name: b["source_name"], epoch: b["epoch"], data_span: b["data_span"], control_station_id: control["station_id"], control_set_id: control["set_id"], control_source_id: control["source_id"], uncertainty_m: b["uncertainty_m"], uncertainty_basis: b["uncertainty_basis"], flags: b["flags"] || [])
            end
            DatumInfo.new(set_id: set_id, zero: d["zero"], zero_name: d["zero_name"], chart_datum: d["chart_datum"], msl_offset_m: d["msl_offset_m"], levels: levels)
        end
    end
end
