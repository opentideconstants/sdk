class OpenTideConstants
    VERSION = "0.1.0".freeze

    # Format majors this SDK reads (spec §7.4).
    SUPPORTED_FORMAT_MAJORS = [1].freeze
    # The newest format version this SDK reads (spec §7.4). A release whose
    # release.min_reader_version is newer fails with reader_too_old.
    SUPPORTED_FORMAT_VERSION = "1.0".freeze
    DEFAULT_BASE_URL = "https://data.opentideconstants.org/".freeze
    # The cache root subdirectory (spec §5.4).
    CACHE_LAYOUT_VERSION = "v1".freeze
    # A valid datestamp: the date, then an optional counter of 2 or more, with
    # at most 9 digits (spec §4.2, CR D18).
    DATESTAMP_RE = /\A[0-9]{8}(\.[2-9]|\.[1-9][0-9]{1,8})?\z/.freeze
end
