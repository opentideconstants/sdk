class OpenTideConstants
    module Predict
        class Sum
            attr_accessor :mean
            attr_reader :table
            def initialize(table, constituents, amplitude: "amplitude_m", phase: "phase_deg", mean: 0.0, multiplier: 1.0, shift_hours: 0.0)
                @table, @mean, @years = table, mean, {}
                @terms = constituents.map do |constituent|
                    row = table.send(:row_for, constituent["name"])
                    speed = row["speed_deg_per_hour"]
                    [row, speed, multiplier * constituent.fetch(amplitude, 0.0), Predict.angle(constituent.fetch(phase, 0.0) + speed * shift_hours)]
                end
            end
            def year_data(year)
                @years[year] ||= begin
                    index = @table.send(:index_for, year)
                    [Predict.year_start(year), @terms.map { |row, speed, amplitude, phase| [speed, row["f"][index] * amplitude, row["v0u_deg"][index] - phase, speed * RAD] }]
                end
            end
            def value(seconds, year = nil, derivative = false)
                origin, terms = year_data(year || Predict.utc(seconds).year)
                delta = (seconds - origin) / 3600.0
                value = 0.0
                terms.each do |speed, amplitude, argument, omega|
                    phase = Predict.angle(speed * delta + argument) * RAD
                    value += derivative ? -amplitude * omega * Math.sin(phase) : amplitude * Math.cos(phase)
                end
                derivative ? value : value + @mean
            end
            def bound(year, derivative)
                year_data(year)[1].sum { |_, amplitude, _, omega| amplitude.abs * omega**(derivative ? 2 : 1) }
            end
            def error(year, a, b, derivative)
                origin, terms = year_data(year)
                delta_max = [(a - origin).abs, (b - origin).abs].max / 3600.0
                4.0 * 2.0**-52 * terms.sum { |_, amplitude, _, omega| amplitude.abs * (derivative ? omega : 1.0) * ((omega * delta_max).abs + 2.0 * Math::PI) }
            end
        end
        module_function
        def survivor(cluster, slack)
            return nil if cluster.size.even?
            return cluster[2 * ((cluster.size - 1) / 4)] if slack
            wanted = cluster[0][1]
            candidates = cluster.select { |c| c[1] == wanted }
            wanted == "high" ? candidates.max_by { |c| [c[2], -c[0]] } : candidates.min_by { |c| [c[2], c[0]] }
        end
        def events(total, start, stop, slack: false)
            unrounded_events(total, start, stop, slack: slack).select { |c| start <= (c[0] + 0.5).floor && (c[0] + 0.5).floor < stop }
        end
        def unrounded_events(total, start, stop, slack: false)
            return [] if start == stop
            first = (start / 360.0).floor * 360 - 3600
            last = ((stop + 3600 - first) / 360.0).ceil * 360 + first
            first.step(last, 360) { |point| total.table.send(:index_for, utc(point).year) }
            derivative = !slack
            roots = []
            first.step(last - 1, 360) do |left|
                year = utc(left).year
                bound = total.bound(year, derivative)
                value = ->(t) { total.value(t, year, derivative) }
                subdivide = nil
                subdivide = lambda do |a, b, fa, fb, depth|
                    margin = bound * ((b - a) / 3600.0) * (1.0 + 1e-9) + 2.0 * total.error(year, a, b, derivative) + 1e-12 * [1.0, bound].max
                    next if fa.abs + fb.abs > margin
                    if depth < 9
                        middle = (a + b) / 2.0
                        fm = value.call(middle)
                        subdivide.call(a, middle, fa, fm, depth + 1)
                        subdivide.call(middle, b, fm, fb, depth + 1)
                        next
                    end
                    falling = fa > 0 && fb <= 0
                    rising = fa < 0 && fb >= 0
                    next unless falling || rising
                    while b - a > 0.01
                        middle = (a + b) / 2.0
                        fm = value.call(middle)
                        if falling && fm > 0 || rising && fm < 0
                            a = middle
                        else
                            b = middle
                        end
                    end
                    root = (a + b) / 2.0
                    kind = slack ? (falling ? "slack_before_ebb" : "slack_before_flood") : (falling ? "high" : "low")
                    roots << [root, kind, slack ? 0.0 : total.value(root, year)]
                end
                subdivide.call(left, left + 360, value.call(left), value.call(left + 360), 0)
            end
            (utc(first).year + 1).upto(utc(last).year) do |new_year|
                boundary = year_start(new_year)
                next unless first < boundary && boundary < last
                old = total.value(boundary, new_year - 1, derivative)
                new_value = total.value(boundary, new_year, derivative)
                next if old == 0 || new_value == 0 || (old > 0) == (new_value > 0)
                left = roots.select { |c| c[0] <= boundary }.last
                right = roots.find { |c| c[0] > boundary }
                if left && right && right[0] - left[0] < 3600
                    loser = if slack then right else survivor([left, right, left], false) == left ? right : left end
                    roots.delete_at(roots.index(loser))
                else
                    kind = slack ? (new_value > 0 ? "slack_before_flood" : "slack_before_ebb") : (old > 0 ? "high" : "low")
                    roots << [boundary, kind, slack ? 0.0 : total.value(boundary, new_year)]
                end
                roots.sort_by!(&:first)
            end
            kept, cluster = [], []
            roots.each do |candidate|
                if !cluster.empty? && candidate[0] - cluster[-1][0] >= 1.0
                    found = survivor(cluster, slack)
                    kept << found if found
                    cluster = []
                end
                cluster << candidate
            end
            found = survivor(cluster, slack)
            kept << found if found
            kept
        end
        private_class_method :unrounded_events
    end
end
