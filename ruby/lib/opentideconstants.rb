# The OpenTideConstants SDK for Ruby: download, check, cache and query the
# OpenTideConstants releases of open tidal harmonic constants.
#
#     require "opentideconstants"
#
#     otc = OpenTideConstants.new                      # the latest release (cached)
#     st  = otc.station_by_alias(:noaa, "9414290")
#     st.recommended_set.constituent("M2").amplitude_m
#
# Standard library only. See https://opentideconstants.org
class OpenTideConstants
end

require_relative "opentideconstants/version"
require_relative "opentideconstants/errors"
require_relative "opentideconstants/models"
require_relative "opentideconstants/fold"
require_relative "opentideconstants/release"
require_relative "opentideconstants/reader"
require_relative "opentideconstants/http"
require_relative "opentideconstants/cache"
require_relative "opentideconstants/downloader"
require_relative "opentideconstants/client"
