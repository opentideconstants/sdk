require "json"
require "digest"
require "fileutils"
require "open3"
require "time"

# Fresh native producers first; both consumer phases replay the sealed emitted files.
tree, proof, phase = ARGV
abort "usage: ruby assertion-consumer-proof.rb TREE PROOF emit|red|green|controls" unless tree && proof && %w[emit red green controls].include?(phase)
tree = File.realpath(tree)
proof = File.expand_path(proof)
FileUtils.mkdir_p(proof)
ruby = "/usr/local/rbenv/versions/3.2.2/bin/ruby"
runner = File.join(tree, "conformance/runners/ruby/runner.rb")
driver = File.join(tree, "conformance/driver.py")
manifest_path = File.join(proof, "native.json")

def digest(path)
    Digest::SHA256.file(path).hexdigest
end

def assertion_case(id, index, jsonl, datestamp)
    { "id" => "assertion-consumer/#{id}", "steps" => [
        { "driver" => "assert_index", "path" => index, "jsonl" => jsonl, "datestamp" => datestamp }
    ] }
end

if phase == "emit"
    abort "native files already sealed" if File.exist?(manifest_path)
    require File.join(tree, "ruby/test/support")
    require File.join(tree, "conformance/canonical/check_cache")
    sources = {
        "tide" => File.join(tree, "conformance/fixtures/good"),
        "current" => File.join(tree, "conformance/fixtures/predict"),
        "history" => File.expand_path("../FMT/authentic-subset", proof)
    }
    manifest = { "time" => Time.now.utc.iso8601, "ruby" => RUBY_DESCRIPTION, "runner" => runner,
        "runner_sha256" => digest(runner), "driver_before_sha256" => digest(driver),
        "runtime" => ruby, "runtime_sha256" => digest(ruby), "environment" => { "GEM_PATH" => ENV["GEM_PATH"] },
        "producer_sources" => Dir[File.join(tree, "ruby/lib/**/*.rb")].to_h { |path| [path, digest(path)] }, "cells" => [] }
    sources.each do |name, source|
        server = TestSupport.file_server(source)
        begin
            datestamp = JSON.parse(File.read(Dir[File.join(source, "*.meta.json")].first)).fetch("release").fetch("datestamp")
            cache = File.join(proof, "native", name)
            path = File.join(cache, "v1/releases", datestamp, "index-v1.json")
            jsonl = File.join(File.dirname(path), "OTC_#{datestamp}.jsonl")
            source_jsonl = File.join(source, File.basename(jsonl))
            rows = File.binread(source_jsonl).lines.map { |line| JSON.parse(line) }
            station = rows.find { |row| row["status"] != "removed" && row["recommended_set_id"] && !row["subordinate_offsets"] }.fetch("station_id")
            requests = [
                { "op" => "open", "args" => { "release" => datestamp, "base_url" => server.url, "cache_dir" => cache, "mode" => "stream" } },
                { "op" => "station", "args" => { "station_id" => station } },
                { "op" => "close", "args" => {} }
            ]
            stdout, stderr, status = Open3.capture3(ruby, runner, stdin_data: requests.each_with_index.map { |request, i| JSON.generate(request.merge("case" => name, "step" => i)) + "\n" }.join, chdir: tree)
            File.write(File.join(proof, "#{name}-producer.stdout.log"), stdout)
            File.write(File.join(proof, "#{name}-producer.stderr.log"), stderr)
            replies = stdout.lines.map { |line| JSON.parse(line) }
            abort "native #{name} failed: #{stderr}" unless status.success? && replies.drop(1).length == requests.length && replies.drop(1).all? { |reply| reply["ok"] }
            abort "download altered source" unless digest(source_jsonl) == digest(jsonl)
            meta = jsonl.sub(/\.jsonl\z/, ".meta.json")
            fold = File.join(tree, "conformance/name_fold.json")
            pins = [jsonl, meta, fold].to_h { |file| [file, digest(file)] }
            witness = { "kind" => "stream_index", "cache_path" => path, "source_jsonl" => jsonl, "source_meta" => meta,
                "name_fold" => fold, "source_pins" => pins, "bindings" => { "by" => JSON.parse(File.read(path)).fetch("by") } }
            errors = CanonicalCache.check(witness)
            File.write(File.join(cache, "witness.json"), JSON.pretty_generate(witness))
            abort "native canonical checker #{name}: #{errors.inspect}" unless errors.empty?
            abort "server errors" unless server.errors.empty?
            cell = { "name" => name, "path" => path, "jsonl" => jsonl, "datestamp" => datestamp, "station_id" => station,
                "source" => source, "source_pins" => pins, "index_sha256" => digest(path), "producer_argv" => [ruby, runner],
                "producer_requests" => requests, "producer_exit" => status.exitstatus, "stdout_sha256" => digest(File.join(proof, "#{name}-producer.stdout.log")) }
            manifest["cells"] << cell
            puts JSON.generate(cell)
        ensure
            server.stop
        end
    end
    File.write(manifest_path, JSON.pretty_generate(manifest))
    exit 0
end

manifest = JSON.parse(File.read(manifest_path))
manifest.fetch("producer_sources").each { |path, pin| abort "producer changed: #{path}" unless digest(path) == pin }
manifest.fetch("cells").each do |cell|
    abort "emitted index changed" unless digest(cell.fetch("path")) == cell.fetch("index_sha256")
    cell.fetch("source_pins").each { |path, pin| abort "source changed: #{path}" unless digest(path) == pin }
end
if phase == "green"
    require File.join(tree, "ruby/test/support")
    manifest.fetch("cells").each do |cell|
        server = TestSupport.file_server(cell.fetch("source"))
        begin
            requests = Marshal.load(Marshal.dump(cell.fetch("producer_requests")))
            requests[0]["args"]["base_url"] = server.url
            stdout, stderr, status = Open3.capture3(ruby, runner, stdin_data: requests.each_with_index.map { |request, i| JSON.generate(request.merge("case" => cell.fetch("name"), "step" => i)) + "\n" }.join, chdir: tree)
            prefix = File.join(proof, "#{cell.fetch('name')}-producer-green")
            File.write("#{prefix}.stdout.log", stdout)
            File.write("#{prefix}.stderr.log", stderr)
            replies = stdout.lines.map { |line| JSON.parse(line) }
            original = File.readlines(File.join(proof, "#{cell.fetch('name')}-producer.stdout.log")).map { |line| JSON.parse(line) }
            abort "same native calls failed" unless status.success? && replies.drop(1).length == requests.length && replies.drop(1).all? { |reply| reply["ok"] }
            abort "public station values changed" unless replies[2].fetch("result") == original[2].fetch("result")
            abort "same native index changed" unless digest(cell.fetch("path")) == cell.fetch("index_sha256")
            abort "server errors" unless server.errors.empty?
            File.write("#{prefix}.json", JSON.pretty_generate({ "argv" => [ruby, runner], "requests" => requests,
                "exit" => status.exitstatus, "index_sha256" => digest(cell.fetch("path")), "same_public_station" => true }))
        ensure
            server.stop
        end
    end
end
cases = manifest.fetch("cells").map { |cell| assertion_case(cell.fetch("name"), cell.fetch("path"), cell.fetch("jsonl"), cell.fetch("datestamp")) }
expected_refusals = []
if phase == "controls"
    cell = manifest.fetch("cells").find { |row| row["name"] == "current" }
    source_doc = JSON.parse(File.read(cell.fetch("path")))
    directory = File.join(proof, "controls")
    FileUtils.mkdir_p(directory)
    controls = {
        "country" => ->(doc) { doc["stations"][0]["country"] = "ZZ" },
        "discovery-boolean" => ->(doc) { doc["discovery_index_version"] = true },
        "missing-discovery" => ->(doc) { doc.delete("discovery_index_version") },
        "station-unknown" => ->(doc) { doc["stations"][0]["unknown"] = 1 },
        "set-private" => ->(doc) { doc["stations"].find { |row| !row["sets"].empty? }["sets"][0]["datum"] = nil },
        "set-unknown" => ->(doc) { doc["stations"].find { |row| !row["sets"].empty? }["sets"][0]["unknown"] = 1 },
        "offset-unknown" => ->(doc) { doc["stations"].find { |row| !row["current_offsets"].empty? }["current_offsets"][0]["depth"] = 99 },
        "offset-primitive" => ->(doc) { doc["stations"].find { |row| !row["current_offsets"].empty? }["current_offsets"][0]["bin"] = true },
        "subordinate-unknown" => ->(doc) { doc["stations"].find { |row| row["subordinate_offsets"].is_a?(Hash) }["subordinate_offsets"]["unknown"] = 1 },
        "sparse-offset" => ->(doc) { doc["stations"][0].delete("subordinate_offsets") },
        "offset-span" => ->(doc) { doc["stations"][0]["offset"] += 1 },
        "length-span" => ->(doc) { doc["stations"][0]["length"] += 1 },
        "station-order" => ->(doc) { doc["stations"].reverse! },
        "source-digest" => ->(doc) { doc["jsonl_sha256"] = "0" * 64 },
        "invalid-by" => ->(doc) { doc["by"] = "invalid" }
    }
    controls.each do |name, change|
        doc = Marshal.load(Marshal.dump(source_doc))
        change.call(doc)
        path = File.join(directory, "#{name}.json")
        File.write(path, JSON.generate(doc))
        cases << assertion_case(name, path, cell.fetch("jsonl"), cell.fetch("datestamp"))
        expected_refusals << "assertion-consumer/#{name}"
    end
    history = manifest.fetch("cells").find { |row| row["name"] == "history" }
    {
        "fallback-unknown" => ->(doc) { doc["stations"].flat_map { |row| row["sets"] }.find { |set| set["fallback"].is_a?(Hash) }["fallback"]["unknown"] = 1 },
        "nested-source-value" => ->(doc) { doc["stations"].find { |row| row.dig("subordinate_offsets", "provenance").is_a?(Hash) }["subordinate_offsets"]["provenance"]["unknown"] = "tampered" }
    }.each do |name, change|
        doc = JSON.parse(File.read(history.fetch("path")))
        change.call(doc)
        path = File.join(directory, "#{name}.json")
        File.write(path, JSON.generate(doc))
        cases << assertion_case(name, path, history.fetch("jsonl"), history.fetch("datestamp"))
        expected_refusals << "assertion-consumer/#{name}"
    end
    %w[python ruby js c swift unfamiliar].each do |language|
        doc = Marshal.load(Marshal.dump(source_doc))
        doc["by"] = "opentideconstants-#{language}/0.1.0"
        path = File.join(directory, "by-#{language}.json")
        File.write(path, JSON.generate(doc))
        cases << assertion_case("by-#{language}", path, cell.fetch("jsonl"), cell.fetch("datestamp"))
    end
    { "invalid-json" => "{", "nonobject" => "[]" }.each do |name, contents|
        path = File.join(directory, "#{name}.json")
        File.write(path, contents)
        cases << assertion_case(name, path, cell.fetch("jsonl"), cell.fetch("datestamp"))
        expected_refusals << "assertion-consumer/#{name}"
    end
    cases << assertion_case("missing-index", File.join(directory, "absent.json"), cell.fetch("jsonl"), cell.fetch("datestamp"))
    cases << assertion_case("missing-source", cell.fetch("path"), File.join(directory, "absent.jsonl"), cell.fetch("datestamp"))
    bad_source = File.join(directory, "bad-source.jsonl")
    File.write(bad_source, "{}\n")
    cases << assertion_case("bad-source", cell.fetch("path"), bad_source, cell.fetch("datestamp"))
    expected_refusals.concat(%w[missing-index missing-source bad-source].map { |name| "assertion-consumer/#{name}" })
end
case_directory = File.join(proof, "#{phase}-cases")
FileUtils.mkdir_p(case_directory)
File.write(File.join(case_directory, "assertions.json"), JSON.pretty_generate({ "suite_version" => "1.0", "group" => "assertion-consumer", "cases" => cases }))
report_path = File.join(proof, "#{phase}-driver-report.json")
argv = ["python3", driver, "--runner", [ruby, runner].join(" "), "--cases", case_directory, "--all-steps", "--report", report_path]
stdout, stderr, status = Open3.capture3(*argv, chdir: tree)
File.write(File.join(proof, "#{phase}.stdout.log"), stdout)
File.write(File.join(proof, "#{phase}.stderr.log"), stderr)
report = JSON.parse(File.read(report_path))
observations = report.fetch("cases").map do |row|
    refusal = phase == "red" || expected_refusals.include?(row.fetch("id"))
    { "id" => row.fetch("id"), "expected_refusal" => refusal, "pass" => row.fetch("status") == (refusal ? "FAIL" : "PASS"), "status" => row.fetch("status"), "failures" => row["failures"] }
end
receipt = { "phase" => phase, "argv" => argv, "cwd" => tree, "time" => Time.now.utc.iso8601, "exit" => status.exitstatus,
    "driver_sha256" => digest(driver), "runner_sha256" => digest(runner), "native_manifest_sha256" => digest(manifest_path),
    "harness_errors" => report.fetch("steps").fetch("harness_errors"), "observations" => observations }
File.write(File.join(proof, "#{phase}.json"), JSON.pretty_generate(receipt))
puts stdout
warn stderr unless stderr.empty?
abort "unexpected assertion result" unless receipt.fetch("harness_errors").zero? && observations.all? { |row| row.fetch("pass") }
puts JSON.generate({ "phase" => phase, "accepted_observations" => observations.length, "driver_sha256" => receipt["driver_sha256"] })
