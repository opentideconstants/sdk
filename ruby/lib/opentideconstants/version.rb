class OpenTideConstants
    VERSION = "0.1.0".freeze

    # Format majors this SDK reads (spec §7.4).
    SUPPORTED_FORMAT_MAJORS = [0].freeze
    DEFAULT_BASE_URL = "https://data.opentideconstants.org/".freeze
    # The cache root subdirectory (spec §5.4).
    CACHE_LAYOUT_VERSION = "v1".freeze
    # A valid datestamp: the date, then an optional counter of 2 or more (spec §4.2).
    DATESTAMP_RE = /\A[0-9]{8}(\.[2-9]|\.[1-9][0-9]+)?\z/.freeze
end
