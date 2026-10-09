# A fake opentideconstants gem for the runner self-tests (see README.md).
module OpenTideConstants
    VERSION = "9.9.9-fake" unless ENV["FAKE_SDK_MODE"] == "no-version"
    MODE = ENV.fetch("FAKE_SDK_MODE", "")
    unless MODE == "no-error-class"
        class Error < StandardError
            attr_reader :code, :tombstone
            def initialize(msg, code: :fake, tombstone: nil)
                super(msg)
                @code = code
                @tombstone = tombstone
            end
        end
    end

    Tomb = Struct.new(:station_id, :name, :status, :removed_in, :removed_reason, :merged_into)
    Stats = Struct.new(:type, :kind, :country, :source, :qc_status)

    class Release
        def datestamp = "20991231.2"
        def format_version = "1.0"
        def station_count
            { "inf" => Float::INFINITY, "nan" => Float::NAN }.fetch(MODE, 20)
        end
        def stats = Stats.new({ reference: 1 }, MODE == "stats-nil" ? nil : { tide: 1 }, {}, {}, {})
        def station(_id) = nil
        def require_station(_id)
            raise Error.new("removed", code: :station_removed,
                            tombstone: Tomb.new("OTC-T-0005", "Old Pier", :removed, "20991231", :duplicate, "OTC-T-0001"))
        end
    end

    class Client
        def initialize(**_kw)
            @release = Release.new
        end
        attr_reader :release
        def loaded_from = :file
        def station(id) = @release.station(id)
        def require_station(id) = @release.require_station(id)
        def subordinates_of(_st) = []
        def close
            raise "close failed" if MODE == "close-raises"
        end
    end

    def self.new(**kw) = Client.new(**kw)
end
