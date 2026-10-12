#!/usr/bin/env ruby
require 'json'
require 'digest'
require 'fileutils'

abort 'usage: materialize_vectors.rb OUTPUT_DIRECTORY' unless ARGV.size == 1
bundle = File.expand_path('../../conformance/vectors/1.0', __dir__)
document = JSON.parse(File.read(File.join(bundle, 'vectors.json')))
bytes = File.binread(File.join(bundle, 'vectors-release.json'))
abort 'vector release checksum mismatch' unless Digest::SHA256.hexdigest(bytes) == document.fetch('release_sha256')
release = JSON.parse(bytes)
stations = release.fetch('stations')
abort 'vector stations must be an array' unless stations.is_a?(Array)
destination = File.expand_path(ARGV.fetch(0))
FileUtils.mkdir_p(destination)
base = "OTC_#{release.fetch('release').fetch('datestamp')}"
original = File.join(destination, "#{base}.json")
stream = File.join(destination, "#{base}.jsonl")
metadata = File.join(destination, "#{base}.meta.json")
File.binwrite(original, bytes)
File.write(stream, stations.map { |station| JSON.generate(station) + "\n" }.join)
File.write(metadata, JSON.generate(release.reject { |key, _| key == 'stations' }) + "\n")
reconstructed = JSON.parse(File.read(metadata))
reconstructed['stations'] = File.readlines(stream).map { |line| JSON.parse(line) }
abort 'native vector projection differs from authenticated original' unless reconstructed == release
checksums = [original, stream, metadata].map { |path| "#{Digest::SHA256.file(path).hexdigest}  #{File.basename(path)}\n" }
File.write(File.join(destination, "#{base}.sha256"), checksums.join)
if ENV['GITHUB_ENV']
    File.open(ENV.fetch('GITHUB_ENV'), 'a') { |file| file.puts("OTC_PREDICT_NATIVE_JSONL=#{stream}") }
end
puts stream
