class OpenTideConstants
    # The user and password of a URL never go into an error message or a log
    # line: they are replaced by "***" (spec §5.7, CR2 DR21).
    module Redact
        # "scheme://" and then the authority up to its last "@". The authority
        # ends at "/", "?", "#", white space or a quote.
        USERINFO = %r{([A-Za-z][A-Za-z0-9+.\-]*://)[^/?#\s'"<>]*@}.freeze

        module_function

        # text with the userinfo of every URL in it redacted.
        def text(text)
            text.gsub(USERINFO, '\1***@')
        end

        # One URL (a proxy may have no scheme) with its userinfo redacted.
        def url(url)
            s = url.to_s
            return text(s) if s.include?("://")

            head, at, tail = s.rpartition("@")
            at.empty? || head.include?("/") ? s : "***@#{tail}"
        end
    end
    private_constant :Redact

    # The base class of every SDK error (spec §4.8). Every error has a stable
    # string #code; every error class is a direct subclass of this one. A URL
    # in the message never carries its user and password (CR2 DR21).
    class Error < StandardError
        CODE = "error".freeze

        def initialize(message = nil)
            super(message.is_a?(String) ? Redact.text(message) : message)
        end

        def code
            self.class::CODE
        end
    end

    class NetworkError < Error
        CODE = "network".freeze
        attr_reader :url, :status

        def initialize(message = "network error", url: nil, status: nil)
            super(message)
            # Callers print the url too: it never carries the user and password (CR2 DR21b).
            @url = url.is_a?(String) ? Redact.url(url) : url
            @status = status
        end
    end

    class ReleaseNotFoundError < Error
        CODE = "release_not_found".freeze
    end

    class OfflineError < Error
        CODE = "offline_unavailable".freeze
    end

    class ChecksumError < Error
        CODE = "checksum_mismatch".freeze
        attr_reader :file, :expected, :actual

        def initialize(message = "checksum mismatch", file: nil, expected: nil, actual: nil)
            super(message)
            @file = file
            @expected = expected
            @actual = actual
        end
    end

    class UnsupportedFormatError < Error
        CODE = "unsupported_format".freeze
    end

    # The release's release.min_reader_version is newer than SUPPORTED_FORMAT_VERSION.
    class ReaderTooOldError < Error
        CODE = "reader_too_old".freeze
    end

    class InvalidReleaseError < Error
        CODE = "invalid_release".freeze
    end

    class StationNotFoundError < Error
        CODE = "station_not_found".freeze
    end

    class StationRemovedError < Error
        CODE = "station_removed".freeze
        attr_reader :tombstone

        def initialize(message = "station removed", tombstone: nil)
            super(message)
            @tombstone = tombstone
        end
    end

    class PinnedReleaseError < Error
        CODE = "pinned_release".freeze
    end

    # The cache cannot be written. #removed lists the datestamps that prune
    # removed before the failure, newest first; it is empty for every other
    # operation (spec §4.3, CR2 DR18).
    class CacheError < Error
        CODE = "cache".freeze
        attr_reader :removed

        def initialize(message = "cache error", removed: [])
            super(message)
            @removed = removed.dup.freeze
        end
    end

    class FileExistsError < Error
        CODE = "file_exists".freeze
        attr_reader :path

        def initialize(message = "file exists", path: nil)
            super(message)
            @path = path
        end
    end

    # A local file cannot be opened or read. The system error is #cause.
    class FileError < Error
        CODE = "io".freeze
        attr_reader :path

        def initialize(message = "file error", path: nil)
            super(message)
            @path = path
        end
    end

    class InvalidArgumentError < Error
        CODE = "invalid_argument".freeze
    end
    class NoConstantsError < Error
        CODE = "no_constants".freeze
    end
    class QuantityMismatchError < Error
        CODE = "quantity_mismatch".freeze
    end
    class UnsupportedConventionError < Error
        CODE = "unsupported_convention".freeze
    end
    class NoAstroTableError < Error
        CODE = "no_astro_table".freeze
    end
    class UnsupportedConstituentError < Error
        CODE = "unsupported_constituent".freeze
        attr_reader :constituent
        def initialize(message = nil, constituent: nil)
            super(message)
            @constituent = constituent
        end
    end
    class TimeOutOfRangeError < Error
        CODE = "time_out_of_range".freeze
        attr_reader :first_year, :last_year
        def initialize(message = nil, first_year: nil, last_year: nil)
            super(message)
            @first_year = first_year
            @last_year = last_year
        end
    end
    class DatumUnavailableError < Error
        CODE = "datum_unavailable".freeze
        attr_reader :missing
        def initialize(message = nil, missing: nil)
            super(message)
            @missing = missing
        end
    end
    class BinNotFoundError < Error
        CODE = "bin_not_found".freeze
    end
    class ExtremesOnlyError < Error
        CODE = "extremes_only".freeze
    end
    class LocalTimeUnavailableError < Error
        CODE = "local_time_unavailable".freeze
    end
    class UnknownTimeZoneError < Error
        CODE = "unknown_time_zone".freeze
        attr_reader :zone
        def initialize(message = nil, zone: nil)
            super(message)
            @zone = zone
        end
    end
    class ReferenceUnavailableError < Error
        CODE = "reference_unavailable".freeze
        attr_reader :reference_station_id
        def initialize(message = nil, reference_station_id: nil)
            super(message)
            @reference_station_id = reference_station_id
        end
    end
    class HistoricalOffsetsExcludedError < Error
        CODE = "historical_offsets_excluded".freeze
    end
end
