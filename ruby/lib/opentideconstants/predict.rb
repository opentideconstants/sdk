require_relative "predict/astro"
require_relative "predict/harmonic"
require_relative "predict/results"
require_relative "predict/engine"
require_relative "predict/local"

class OpenTideConstants
    class Release
        def astro_table(id = nil)
            check_open!
            Predict.astro_table(self, id)
        end
        def heights(station, start:, stop:, step_s: 600, datum: nil, set_id: nil, offset_id: nil)
            check_open!
            first, last = Predict.window(start, stop, step_s)
            raise InvalidArgumentError, "step_s must be a positive integer" unless step_s.is_a?(Integer) && step_s > 0
            c = Predict.context(self, station, "water_level", set_id, datum, series: true, offset_id: offset_id)
            items = []
            first.step(last - 1, step_s) { |t| items << HeightPoint.new(time: Predict.utc(t), height_m: c.total.value(t)) } if first < last
            Predict.result(self, c, HeightSeries, items, datum)
        end
        def heights_at(station, times, datum: nil, set_id: nil, offset_id: nil)
            check_open!
            raise InvalidArgumentError, "times must be an Array of Time" unless times.is_a?(Array)
            seconds = times.map { |t| Predict.instant(t) }
            c = Predict.context(self, station, "water_level", set_id, datum, series: true, offset_id: offset_id)
            Predict.result(self, c, HeightSeries, seconds.map { |t| HeightPoint.new(time: Predict.utc(t), height_m: c.total.value(t)) }, datum)
        end
        def extremes(station, start:, stop:, datum: nil, set_id: nil, offset_id: nil)
            check_open!
            first, last = Predict.window(start, stop)
            c = Predict.context(self, station, "water_level", set_id, datum, offset_id: offset_id)
            if c.method == "offsets" && first != last
                off = c.offsets
                margin = [120.0, [(off["time_offset_high_min"] || 0).abs, (off["time_offset_low_min"] || 0).abs].max + 60.0].max * 60.0
                candidates = Predict.events(c.total, first - margin, last + margin).map do |root, kind, value|
                    t = root + (off["time_offset_#{kind}_min"] || 0) * 60.0
                    adjustment = off["height_offset_#{kind}"]
                    height = off["height_adjusted_type"] == "R" ? value * (adjustment.nil? ? 1.0 : adjustment) : value + (adjustment || 0.0)
                    [t, kind, height + off["_subterm"]]
                end.sort_by { |row| (row[0] + 0.5).floor }
            else
                candidates = Predict.events(c.total, first, last)
            end
            items = candidates.filter_map do |t, kind, value|
                whole = (t + 0.5).floor
                Extreme.new(time: Predict.utc(whole), type: kind.to_sym, height_m: value) if first <= whole && whole < last
            end
            Predict.result(self, c, ExtremeList, items, datum)
        end
        def currents(station, start:, stop:, step_s: 600, bin_number: nil, set_id: nil)
            check_open!
            first, last = Predict.window(start, stop, step_s)
            raise InvalidArgumentError, "step_s must be a positive integer" unless step_s.is_a?(Integer) && step_s > 0
            c = Predict.context(self, station, "current", set_id, nil, bin_number, series: true)
            theta = c.current_bin.fetch("azimuth_deg", 0.0) * Predict::RAD
            items = []
            if first < last
                first.step(last - 1, step_s) do |t|
                    major, minor = c.total.value(t), c.minor.value(t)
                    east = major * Math.sin(theta) + minor * Math.sin(theta + Math::PI / 2.0)
                    north = major * Math.cos(theta) + minor * Math.cos(theta + Math::PI / 2.0)
                    speed = Math.hypot(east, north)
                    direction = speed < 1e-9 ? nil : Predict.angle(Math.atan2(east, north) / Predict::RAD)
                    items << CurrentPoint.new(time: Predict.utc(t), velocity_major_ms: c.sigma * major, velocity_minor_ms: c.sigma * minor, speed_ms: speed, direction_deg: direction)
                end
            end
            Predict.result(self, c, CurrentSeries, items)
        end
        def current_events(station, start:, stop:, bin_number: nil, set_id: nil)
            check_open!
            first, last = Predict.window(start, stop)
            c = Predict.context(self, station, "current", set_id, nil, bin_number)
            if c.method == "offsets"
                entry = c.offsets
                kinds = %w[max_flood max_ebb slack_before_flood slack_before_ebb]
                kept = kinds.select { |k| !entry["time_adj_#{k}_min"].nil? && (k.start_with?("slack") || !entry[k == "max_flood" ? "flood_amp_ratio" : "ebb_amp_ratio"].nil?) }
                c.omitted = (kinds - kept).map(&:to_sym)
                margin = [120.0, (kept.map { |k| entry["time_adj_#{k}_min"].abs }.max || 0.0) + 60.0].max * 60.0
                candidates = first == last ? [] : Predict.current_events(c, first - margin, last + margin)
                candidates = candidates.filter_map do |t, k, value, direction|
                    next unless kept.include?(k)
                    t += entry["time_adj_#{k}_min"] * 60.0
                    if %w[max_flood max_ebb].include?(k)
                        value *= entry[k == "max_flood" ? "flood_amp_ratio" : "ebb_amp_ratio"]
                        direction = entry[k == "max_flood" ? "mean_flood_dir_deg" : "mean_ebb_dir_deg"]
                    end
                    [t, k, value, direction]
                end.sort_by { |row| (row[0] + 0.5).floor }
            else
                candidates = Predict.current_events(c, first, last)
            end
            items = candidates.filter_map do |t, k, value, direction|
                whole = (t + 0.5).floor
                CurrentEvent.new(time: Predict.utc(whole), type: k.to_sym, velocity_ms: value, direction_deg: direction) if first <= whole && whole < last
            end
            Predict.result(self, c, CurrentEventList, items)
        end
        def datums(station, set_id: nil, all_sets: false)
            check_open!
            station = Predict.station_for(self, station)
            Predict.options(set_id)
            raise InvalidArgumentError, "all_sets must be a boolean" unless all_sets == true || all_sets == false
            return station.constant_sets(include_no_constants: true).map { |s| Predict.datum_info(s.set_id, s.raw["datum"]) }.freeze if all_sets
            constants = Predict.chosen(self, station, set_id)
            return Predict.datum_info(constants.set_id, constants.raw["datum"]) if constants
            offsets = station.raw["subordinate_offsets"]
            offsets && Predict.datum_info(nil, offsets["datum"])
        end
        def ranges(station, set_id: nil)
            check_open!
            info = datums(station, set_id: set_id)
            levels = info.is_a?(DatumInfo) ? info.levels.to_h { |l| [l.key, l] } : {}
            difference = lambda do |a, b|
                high, low = levels[a], levels[b]
                next nil unless high && low && high.value_m && low.value_m && high.kind && high.kind == low.kind && high.epoch == low.epoch
                high.value_m - low.value_m
            end
            Ranges.new(mn: difference.call("mhw", "mlw"), gt: difference.call("mhhw", "mllw"), dhq: difference.call("mhhw", "mhw"), dlq: difference.call("mlw", "mllw"))
        end
    end
    %i[heights heights_at extremes currents current_events datums ranges].each do |name|
        define_method(name) do |*args, **kw, &blk|
            check_open!
            maybe_auto_update
            @release.public_send(name, *args, **kw, &blk)
        end
    end
    private_constant :Predict
end
