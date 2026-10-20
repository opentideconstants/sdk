require_relative "lib/opentideconstants/version"

# `gem build` reads s.files relative to the working folder, so
# `gem build ruby/opentideconstants.gemspec` from the repository root would
# not find lib/ (or would take the root's README.md): build from this folder.
# __dir__ is relative when the gemspec is given by a relative path. The
# paths are compared as real paths: under a symlinked folder (macOS /tmp)
# RubyGems' and Bundler's own chdir into this folder would otherwise look
# different and get a second, conflicting chdir.
gem_dir = File.expand_path(__dir__)
Dir.chdir(gem_dir) unless File.realpath(Dir.pwd) == File.realpath(gem_dir)

Gem::Specification.new do |s|
    s.name        = "opentideconstants"
    s.version     = OpenTideConstants::VERSION
    s.summary     = "Download, check, cache and query OpenTideConstants releases of tidal harmonic constants"
    s.description = "The Ruby SDK for OpenTideConstants: open tidal harmonic constants with stable station ids, " \
                    "provenance, validation and per-set licences. Native Ruby prediction; standard library core, optional tzinfo local time."
    s.authors     = ["Jordan Ritter"]
    s.homepage    = "https://opentideconstants.org"
    s.license     = "MIT"
    s.files       = ["README.md", "LICENSE", "supported-formats.json", "lib/opentideconstants.rb"] +
                    Dir.glob("lib/opentideconstants/**/*.{rb,json}", base: gem_dir).sort
    s.require_paths = ["lib"]
    s.required_ruby_version = ">= 3.3"
    s.metadata    = {
        "homepage_uri" => "https://opentideconstants.org",
        "source_code_uri" => "https://github.com/opentideconstants/sdk",
        "rubygems_mfa_required" => "true"
    }
end
