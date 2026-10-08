require_relative "lib/opentideconstants/version"

Gem::Specification.new do |s|
    s.name        = "opentideconstants"
    s.version     = OpenTideConstants::VERSION
    s.summary     = "Download, check, cache and query OpenTideConstants releases of tidal harmonic constants"
    s.description = "The Ruby SDK for OpenTideConstants: open tidal harmonic constants with stable station ids, " \
                    "provenance, validation and per-set licences. Pure Ruby, standard library only."
    s.authors     = ["Jordan Ritter"]
    s.homepage    = "https://opentideconstants.org"
    s.license     = "MIT"
    s.files       = ["README.md", "LICENSE", "lib/opentideconstants.rb"] +
                    Dir.glob("lib/opentideconstants/*.{rb,json}", base: __dir__).sort
    s.require_paths = ["lib"]
    s.required_ruby_version = ">= 3.0"
    s.metadata    = {
        "homepage_uri" => "https://opentideconstants.org",
        "source_code_uri" => "https://github.com/opentideconstants/sdk",
        "rubygems_mfa_required" => "true"
    }
end
