class OpenTideConstants
    module Predict
        RAD = Math::PI / 180.0
        module_function
        def instant(value)
            raise InvalidArgumentError, "an instant must be a Time" unless value.is_a?(Time)
            value.to_r.floor
        end
        def utc(seconds)
            Time.at(seconds).utc.freeze
        end
        def year_start(year)
            Time.utc(year, 1, 1).to_i
        end
        def angle(value)
            reduced = value - 360.0 * (value / 360.0).floor
            reduced == 360.0 ? 0.0 : reduced
        end
        def number?(value)
            value.is_a?(Numeric) && value.real? && value.to_f.finite?
        end
        def integer?(value)
            number?(value) && value == value.floor
        end
    end
    class AstroTable
        def initialize(raw)
            @raw = Util.deep_freeze(raw)
            ident = raw.fetch("astro_table_id", "")
            first, last = raw.values_at("first_year", "last_year")
            unless Predict.integer?(first) && Predict.integer?(last) && first <= last
                raise InvalidArgumentError, "astro table #{ident} first_year and last_year must be ordered integers"
            end
            @first, @last = first.to_i, last.to_i
            rows = raw["constituents"]
            raise InvalidArgumentError, "astro table #{ident} constituents must be an object" unless rows.is_a?(Hash)
            rows.each do |name, row|
                raise InvalidArgumentError, "astro table #{ident} row #{name} must be an object" unless row.is_a?(Hash)
                %w[v0u_deg f].each do |key|
                    values = row[key]
                    unless values.is_a?(Array) && values.size == @last - @first + 1 && values.all? { |v| Predict.number?(v) }
                        raise InvalidArgumentError, "astro table #{ident} row #{name} #{key} must contain #{@last - @first + 1} numbers"
                    end
                end
                speed = row["speed_deg_per_hour"]
                raise InvalidArgumentError, "astro table #{ident} row #{name} speed must be nonnegative" unless speed.nil? || Predict.number?(speed) && speed >= 0
            end
            freeze
        end
        def valid_range
            [@first, @last].freeze
        end
        def equilibrium_argument(name, at)
            seconds = Predict.instant(at)
            row = row_for(name)
            year = Predict.utc(seconds).year
            Predict.angle(row["v0u_deg"][index_for(year)] + row["speed_deg_per_hour"] * ((seconds - Predict.year_start(year)) / 3600.0))
        end
        def node_factor(name, at)
            row_for(name)["f"][index_for(Predict.utc(Predict.instant(at)).year)]
        end
        def equilibrium_for_year(name, year)
            row_for(name)["v0u_deg"][index_for(year)]
        end
        def node_factor_for_year(name, year)
            row_for(name)["f"][index_for(year)]
        end
        private
        def index_for(year)
            raise InvalidArgumentError, "year must be an integer" unless Predict.integer?(year)
            unless year.between?(@first, @last)
                raise TimeOutOfRangeError.new("year #{year} outside astro table", first_year: @first, last_year: @last)
            end
            year.to_i - @first
        end
        def row_for(name)
            row = name.is_a?(String) && @raw["constituents"][name]
            raise UnsupportedConstituentError.new("unsupported constituent #{name}", constituent: name) unless row && row["speed_deg_per_hour"]
            row
        end
    end
end
