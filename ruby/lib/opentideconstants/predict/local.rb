class OpenTideConstants
    module Predict
        module_function
        def localize(result, tz)
            zone = tz == "station" ? result.timezone : tz
            unless zone.is_a?(String) && zone.size <= 255 && zone.match?(/\A[A-Za-z0-9_+\-]+(?:\/[A-Za-z0-9_+\-]+)*\z/) && !zone.start_with?("posix/", "right/") && !%w[posixrules localtime Factory].include?(zone)
                raise UnknownTimeZoneError.new("unknown time zone #{zone.inspect}", zone: zone)
            end
            begin
                require "tzinfo"
            rescue LoadError
                raise LocalTimeUnavailableError, "install tzinfo for local time"
            end
            begin
                rules = TZInfo::Timezone.get(zone)
            rescue TZInfo::InvalidTimezoneIdentifier
                raise UnknownTimeZoneError.new("unknown time zone #{zone}", zone: zone)
            end
            version = nil
            source = TZInfo::DataSource.get
            if source.is_a?(TZInfo::DataSources::RubyDataSource)
                version = TZInfo::Data::Version::TZDATA if defined?(TZInfo::Data::Version::TZDATA)
            elsif source.respond_to?(:zoneinfo_dir)
                root = source.zoneinfo_dir
                %w[tzdata.zi +VERSION].each do |name|
                    begin
                        first = File.open(File.join(root, name), &:readline).strip
                        version = name == "tzdata.zi" ? first.delete_prefix("# version ") : first
                        break
                    rescue SystemCallError, EOFError
                        next
                    end
                end
            end
            items = result.items.map do |item|
                wall = rules.to_local(item.time)
                offset = wall.utc_offset
                magnitude = offset.abs
                suffix = format("%s%02d:%02d", offset >= 0 ? "+" : "-", magnitude / 3600, magnitude % 3600 / 60)
                suffix += format(":%02d", magnitude % 60) unless (magnitude % 60).zero?
                stamp = wall.strftime("%Y-%m-%dT%H:%M:%S") + suffix
                fields = item.instance_variables.reject { |v| v == :@_local }.to_h { |v| [v.to_s.delete_prefix("@").to_sym, item.instance_variable_get(v)] }
                item.class.new(**fields.merge(local_time: stamp, utc_offset_s: offset, _local: wall.freeze))
            end
            fields = result.instance_variables.reject { |v| v == :@_local }.to_h { |v| [v.to_s.delete_prefix("@").to_sym, result.instance_variable_get(v)] }
            result.class.new(**fields.merge(items: items, tz: zone, tz_version: version))
        end
    end
end
