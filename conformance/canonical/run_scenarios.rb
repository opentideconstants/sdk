#!/usr/bin/env ruby
require "json"
require "digest"
require "optparse"
require "open3"
require "shellwords"
require "fileutils"
require "time"

# Thin invocation binding over the existing real SDK driver. Its PASS channel
# covers selected public expectations only; it never accepts a private stub.
options = { scenarios: [], cases: [] }
parser = OptionParser.new do |o|
    o.banner = "run_scenarios.rb --root ABS --driver-python ABS --runner-json JSON --native-pins JSON --profile PROFILE --scenario SC01 --report ABS [--case ID]"
    o.on("--root PATH") { |v| options[:root] = v }
    o.on("--driver-python PATH") { |v| options[:python] = v }
    o.on("--runner-json JSON", "Exact absolute native runner argv array") { |v| options[:runner] = JSON.parse(v) }
    o.on("--native-pins JSON", "Array of exact native runner/module/library path and sha256 pins") { |v| options[:pins] = JSON.parse(v) }
    o.on("--profile PROFILE") { |v| options[:profile] = v }
    o.on("--scenario ID") { |v| options[:scenarios] << v }
    o.on("--case ID") { |v| options[:cases] << v }
    o.on("--report PATH") { |v| options[:report] = v }
end

def absolute_existing(path)
    raise "absolute existing file required: #{path.inspect}" unless path.is_a?(String) && path.start_with?("/") && File.file?(path)
    File.realpath(path)
end

def verify_pin(pin, root = nil)
    path = pin.fetch("path")
    path = File.join(root, path) if root && !path.start_with?("/")
    path = absolute_existing(path)
    actual = Digest::SHA256.file(path).hexdigest
    raise "stale source/fixture/artifact #{path}" unless actual == pin.fetch("sha256")
    { "path" => path, "sha256" => actual, "bytes" => File.size(path) }
end

begin
    parser.parse!
    raise "unexpected arguments" unless ARGV.empty?
    %i[root python runner pins profile report].each { |key| raise "missing --#{key}" unless options.key?(key) }
    raise "absolute candidate root required" unless options[:root].start_with?("/")
    root = File.realpath(options[:root])
    raise "absolute report required" unless options[:report].start_with?("/")
    raise "select at least one scenario" if options[:scenarios].empty?
    corpus_path = File.join(root, "conformance/canonical/scenarios.json")
    corpus = JSON.parse(File.read(corpus_path))
    raise "unsupported corpus version" unless corpus.fetch("corpus_version") == 1
    profile = options[:profile]
    profile_map = { "typescript" => "typescript_node", "typescript-browser" => "typescript_browser", "c-fetch" => "c", "c-no-predict" => "c", "c-no-localtime" => "c", "python-no-tz" => "python", "ruby-no-tz" => "ruby" }
    shape_profile = profile_map.fetch(profile, profile)
    raise "unknown required profile #{profile}" unless corpus.fetch("profiles").include?(shape_profile)
    families = options[:scenarios].uniq.map do |id|
        corpus.fetch("scenario_families").find { |family| family.fetch("id") == id } || raise("unbound scenario #{id}")
    end
    bound = families.flat_map { |family| family.fetch("cases") }.uniq { |entry| entry.fetch("id") }
    unless options[:cases].empty?
        missing = options[:cases] - bound.map { |entry| entry.fetch("id") }
        raise "case not bound to selected scenario: #{missing.join(', ')}" unless missing.empty?
        bound.select! { |entry| options[:cases].include?(entry.fetch("id")) }
    end
    raise "zero selected native cases; obligation remains INCOMPLETE" if bound.empty?
    raise "foreign writer/reader pair requires the existing --cross driver/FORMAT gate; remains INCOMPLETE" if bound.any? { |entry| entry.fetch("kind") == "cross" }

    checked = []
    bound.each do |entry|
        source = verify_pin(entry.fetch("source"), root)
        current = JSON.parse(File.read(source.fetch("path"))).fetch("cases").find { |item| item.fetch("id") == entry.fetch("id") }
        raise "changed case object #{entry.fetch('id')}" unless current && Digest::SHA256.hexdigest(JSON.generate(current)) == entry.fetch("source").fetch("case_sha256")
        checked << source
        entry.fetch("fixture_pins").each { |pin| checked << verify_pin(pin, root) }
    end
    runner = options[:runner]
    raise "nonempty exact native argv required" unless runner.is_a?(Array) && !runner.empty? && runner.all? { |part| part.is_a?(String) }
    absolute_existing(runner.first)
    runner.each do |part|
        absolute_existing(part) if part.match?(/\.(rb|py|mjs|js)$/)
        raise "relative module/library argument #{part}" if part.start_with?("-I") && !part.delete_prefix("-I").start_with?("/")
    end
    pins = options[:pins]
    raise "explicit native source and artifact pins required" unless pins.is_a?(Array) && !pins.empty?
    checked_native = pins.map { |pin| verify_pin(pin) }
    raise "candidate native source attribution required" unless checked_native.any? { |pin| pin.fetch("path").start_with?(root + "/") && pin.fetch("path").match?(%r{/(python/src|ruby/lib|js/src|c/src|swift/Sources)/}) }
    native_files = runner.filter_map { |part| File.realpath(part) if part.start_with?("/") && File.file?(part) }.drop(1)
    native_files << File.realpath(runner.first) if native_files.empty?
    raise "native runner artifact/source not pinned" unless native_files.all? { |path| checked_native.any? { |pin| pin.fetch("path") == path } }
    driver = File.join(root, "conformance/driver.py")
    python = absolute_existing(options[:python])
    pattern = "^(?:#{bound.map { |entry| Regexp.escape(entry.fetch('id')) }.join('|')})(?:@[^\\[]+)?$"
    report = File.expand_path(options[:report])
    FileUtils.mkdir_p(File.dirname(report))
    raw_path = report + ".driver.json"
    argv = [python, absolute_existing(driver), "--runner", Shellwords.join(runner), "--profile", profile, "--cases", File.join(root, "conformance/cases"), "--only", pattern, "--all-steps", "--no-expected-failures", "--report", raw_path]
    started = Time.now.utc.iso8601
    stdout, stderr, process = Open3.capture3(*argv, chdir: root)
    File.write(report + ".stdout.log", stdout)
    File.write(report + ".stderr.log", stderr)
    raise "native driver produced no report (exit #{process.exitstatus}): #{stderr}" unless File.file?(raw_path)
    native_report = JSON.parse(File.read(raw_path))
    results = native_report.fetch("cases")
    raise "zero matched actual cases" if results.empty?
    missing_ids = bound.map { |entry| entry.fetch("id") }.reject { |id| results.any? { |result| result.fetch("id").split("@", 2).first == id } }
    raise "selected case never matched actual driver: #{missing_ids.join(', ')}" unless missing_ids.empty?
    unexpected = results.reject { |result| result.fetch("status") == "PASS" }
    outcome = process.success? && unexpected.empty? ? "SELECTED_NATIVE_PUBLIC_EXPECTATIONS_GREEN" : "INCOMPLETE_OR_NATIVE_FAILURE"
    output = {
        "corpus_version" => 1, "status" => outcome, "profile" => profile, "shape_profile" => shape_profile,
        "scenarios" => options[:scenarios].uniq, "selected_case_ids" => bound.map { |entry| entry.fetch("id") },
        "candidate_root" => root, "candidate_head" => Open3.capture3("git", "rev-parse", "HEAD", chdir: root).first.strip,
        "corpus_sha256" => Digest::SHA256.file(corpus_path).hexdigest,
        "native_source_artifact_pins" => checked_native, "case_fixture_pins" => checked.uniq,
        "argv" => argv, "cwd" => root, "started_utc" => started, "finished_utc" => Time.now.utc.iso8601,
        "exit" => process.exitstatus, "driver_sha256" => Digest::SHA256.file(driver).hexdigest,
        "python_sha256" => Digest::SHA256.file(python).hexdigest,
        "stdout" => { "path" => report + ".stdout.log", "sha256" => Digest::SHA256.hexdigest(stdout) },
        "stderr" => { "path" => report + ".stderr.log", "sha256" => Digest::SHA256.hexdigest(stderr) },
        "actual_results" => results, "unaccepted_results" => unexpected,
        "private_body_status" => "INCOMPLETE; no actual callee body trace supplied by public protocol",
        "full_family_or_profile_accepted" => false, "body_migration_unlocked" => false,
        "qualification" => "Actual selected native public expectations only. Missing branches, skipped cases, cross/profile/platform and private-body obligations remain INCOMPLETE. No SDK bug repair or N-cell flip claimed."
    }
    File.write(report, JSON.pretty_generate(output) + "\n")
    puts stdout
    warn stderr unless stderr.empty?
    puts JSON.generate({ "status" => outcome, "actual_cases" => results.length, "report" => report, "private_body_status" => "INCOMPLETE" })
    exit(outcome == "SELECTED_NATIVE_PUBLIC_EXPECTATIONS_GREEN" ? 0 : 1)
rescue StandardError => error
    warn "CORPUS INCOMPLETE: #{error.message}"
    warn error.backtrace.first
    exit 2
end
