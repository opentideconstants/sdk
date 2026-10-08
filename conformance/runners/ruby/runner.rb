# The Ruby conformance runner (SDK spec §7.1, conformance/README.md).
#
# It speaks the runner protocol on stdin/stdout and calls only the public API
# of the opentideconstants gem.
#
#     uv run conformance/driver.py --runner "ruby conformance/runners/ruby/runner.rb"
#
# By default it loads the gem from ruby/lib in this repository. With
# OTC_RUBY_USE_INSTALLED=1 it loads the installed gem instead.
unless ENV["OTC_RUBY_USE_INSTALLED"] == "1"
    $LOAD_PATH.unshift(File.expand_path("../../../ruby/lib", __dir__))
end
require "json"
require "opentideconstants"

$stdout.sync = true

# The SDK base error class (a stand-in only while the gem has none, so the RED run is clean).
SDK_ERROR = OpenTideConstants.const_defined?(:Error) ? OpenTideConstants::Error : Class.new(StandardError)

class Runner
    FILTERS = %w[country type kind source source_type].freeze

    def initialize
        @client = nil
        @held = {}
    end

    def hello
        version = defined?(OpenTideConstants::VERSION) ? OpenTideConstants::VERSION : "0.0.0"
        { "hello" => { "runner" => "ruby", "version" => version,
                       "features" => %w[fs fetch json eager stream] } }
    end

    def handle(req)
        op = req["op"]
        args = req["args"] || {}
        target = req["on"] ? @held.fetch(req["on"]) : nil
        { "ok" => true, "result" => dispatch(op, args, target) }
    rescue SDK_ERROR => e
        { "ok" => false, "error" => encode_error(e) }
    rescue StandardError, ScriptError => e
        { "ok" => false, "error" => { "code" => "uncaught:#{e.class}", "message" => "#{e.message} #{e.backtrace&.first(3)&.join(' | ')}" } }
    end

    def close
        @client&.close
    rescue StandardError
        nil
    end

    private

    def sym_kw(args, names)
        out = {}
        names.each { |n| out[n.to_sym] = args[n] if args.key?(n) }
        out
    end

    def filters(args)
        sym_kw(args, FILTERS)
    end

    # R: the held release, or the client (which forwards to its current release).
    def rel(target)
        target || @client.release
    end

    def q(target)
        target || @client
    end

    def find_station(args, target)
        rel(target).station(args["station_id"])
    end

    def find_set(args, target)
        st = find_station(args, target)
        st && st.constant_set(args["set_id"])
    end

    def dispatch(op, args, target)
        case op
        when "open"
            @client&.close
            @client = nil
            opts = {}
            args.each { |k, v| opts[k.to_sym] = v }
            @client = OpenTideConstants.new(**opts)
            { "loaded_from" => s(@client.loaded_from), "datestamp" => @client.release.datestamp,
              "format_version" => @client.release.format_version }
        when "close"
            @client&.close
            @client = nil
            {}
        when "hold_release"
            @held[args["name"]] = @client.release
            {}
        when "loaded_from" then { "loaded_from" => s(@client.loaded_from) }
        when "last_error"
            err = @client.last_error
            { "code" => err && err.code.to_s }
        when "release_metadata"
            r = rel(target)
            { "datestamp" => r.datestamp, "created" => time(r.created), "format_version" => r.format_version,
              "doi" => r.doi, "concept_doi" => r.concept_doi, "source_versions" => r.source_versions,
              "build_commit" => r.build_commit, "changelog_url" => r.changelog_url }
        when "release_files"
            { "files" => rel(target).files.map { |f| file_info(f) }.sort_by { |f| f["name"] } }
        when "releases" then { "releases" => @client.releases.map { |i| release_info(i) } }
        when "latest" then { "release" => release_info(@client.latest) }
        when "check_for_update"
            i = @client.check_for_update
            { "release" => i && release_info(i) }
        when "update"
            u = @client.update!
            { "updated" => u.updated, "from" => u.from, "to" => u.to }
        when "download"
            pos = args.key?("release") ? [args["release"]] : []
            paths = @client.download(*pos, **sym_kw(args, %w[to formats overwrite]))
            { "paths" => paths.map { |p| File.basename(p) }.sort }
        when "verify" then { "verified" => @client.verify }
        when "cached_releases" then { "datestamps" => @client.cached_releases }
        when "prune" then { "removed" => @client.prune(**sym_kw(args, %w[keep])) }
        when "station_count" then { "station_count" => rel(target).station_count }
        when "tombstone_count" then { "tombstone_count" => rel(target).tombstone_count }
        when "stats" then { "stats" => stats(rel(target).stats) }
        when "constituent_names" then { "names" => rel(target).constituent_names }
        when "conventions" then { "conventions" => rel(target).conventions.map { |c| convention(c) } }
        when "convention"
            c = rel(target).convention(args["convention_id"])
            { "convention" => c && convention(c) }
        when "licences" then { "licences" => rel(target).licences.map { |l| licence(l) } }
        when "licence"
            l = rel(target).licence(args["licence_id"])
            { "licence" => l && licence(l) }
        when "citation" then { "citation" => rel(target).citation }
        when "attribution"
            if args.key?("station_ids")
                ids = args["station_ids"]
                sts = ids.nil? ? nil : ids.map { |id| rel(target).station(id) }.compact
                { "attribution" => q(target).attribution(sts) }
            else
                { "attribution" => q(target).attribution }
            end
        when "station"
            st = q(target).station(args["station_id"])
            { "station" => st && station(st) }
        when "require_station" then { "station" => station(q(target).require_station(args["station_id"])) }
        when "tombstone"
            t = q(target).tombstone(args["station_id"])
            { "tombstone" => t && tombstone(t) }
        when "station_by_alias"
            st = q(target).station_by_alias(args["system"], args["alias_id"])
            { "station_id" => st && st.station_id }
        when "stations" then { "station_ids" => q(target).stations(**filters(args)).map(&:station_id) }
        when "iter_stations"
            ids = []
            q(target).each_station(**filters(args)) { |st| ids << st.station_id }
            { "station_ids" => ids }
        when "search"
            { "station_ids" => q(target).search(**sym_kw(args, %w[name limit match]), **filters(args)).map(&:station_id) }
        when "near"
            hits = q(target).near(**sym_kw(args, %w[lat lon radius_km limit]), **filters(args))
            { "station_ids" => hits.map { |h| h.station.station_id }, "distance_km" => hits.map(&:distance_km) }
        when "nearest"
            h = q(target).nearest(**sym_kw(args, %w[lat lon max_km]), **filters(args))
            { "station_id" => h && h.station.station_id, "distance_km" => h && h.distance_km }
        when "reference_station"
            st = find_station(args, target)
            ref = st && q(target).reference_station(st)
            { "station_id" => ref && ref.station_id }
        when "subordinates_of"
            st = find_station(args, target)
            { "station_ids" => st ? q(target).subordinates_of(st).map(&:station_id) : [] }
        when "station_validation"
            st = find_station(args, target)
            { "validation" => st ? st.validation.map { |v| validation(v) } : [] }
        when "subordinate_offsets"
            st = find_station(args, target)
            off = st && st.subordinate_offsets
            { "offsets" => off && offsets(off) }
        when "recommended_set"
            st = find_station(args, target)
            set = st && st.recommended_set
            { "set_id" => set && set.set_id }
        when "constant_sets"
            st = find_station(args, target)
            { "set_ids" => st ? st.constant_sets(**sym_kw(args, %w[include_excluded])).map(&:set_id) : [] }
        when "constant_set"
            set = find_set(args, target)
            { "set" => set && constant_set(set) }
        when "constituents"
            set = find_set(args, target)
            { "constituents" => set ? set.constituents.map { |c| constituent(c) } : [] }
        when "constituent"
            set = find_set(args, target)
            c = set && set.constituent(args["name"])
            { "constituent" => c && constituent(c) }
        when "provenance"
            set = find_set(args, target)
            p = set && set.provenance
            { "provenance" => p && provenance(p), "raw" => p && p.raw }
        when "set_validation"
            set = find_set(args, target)
            { "validation" => set ? set.validation.map { |v| validation(v) } : [] }
        when "raw" then { "raw" => raw(args, target) }
        else
            raise ArgumentError, "unknown op #{op}"
        end
    end

    def raw(args, target)
        obj = case args["object"]
              when "station" then find_station(args, target)
              when "tombstone" then rel(target).tombstone(args["station_id"])
              when "set" then find_set(args, target)
              when "constituent"
                  set = find_set(args, target)
                  set && set.constituent(args["name"])
              when "convention" then rel(target).convention(args["convention_id"])
              when "licence" then rel(target).licence(args["licence_id"])
              end
        obj && obj.raw
    end

    # ---- encodings (conformance/README.md "Result encodings")

    def s(v)
        v.nil? ? nil : v.to_s
    end

    def time(t)
        t.nil? ? nil : t.utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    end

    def encode_error(e)
        fields = {}
        %i[url status file expected actual path].each do |f|
            fields[f.to_s] = e.public_send(f) if e.respond_to?(f)
        end
        fields["tombstone"] = tombstone(e.tombstone) if e.respond_to?(:tombstone) && e.tombstone
        { "code" => e.code.to_s, "message" => e.message.to_s, "fields" => fields }
    end

    def file_info(f)
        { "name" => f.name, "url" => f.url, "size" => f.size, "sha256" => f.sha256 }
    end

    def release_info(i)
        { "datestamp" => i.datestamp, "format_version" => i.format_version, "doi" => i.doi,
          "files" => i.files.map { |f| file_info(f) }.sort_by { |f| f["name"] } }
    end

    def stats(st)
        %i[type kind country source qc_status].to_h do |k|
            [k.to_s, (st.public_send(k) || {}).to_h { |v, n| [v.to_s, n] }]
        end
    end

    def station(st)
        set = st.recommended_set
        { "station_id" => st.station_id, "name" => st.name, "country" => st.country, "lat" => st.lat,
          "lon" => st.lon, "type" => s(st.type), "kind" => s(st.kind), "timezone" => st.timezone,
          "aliases" => st.aliases.to_h { |k, v| [k.to_s, v] }, "status" => s(st.status),
          "is_reference" => st.reference?, "is_subordinate" => st.subordinate?, "is_tide" => st.tide?,
          "is_current" => st.current?, "recommended_set_id" => set && set.set_id }
    end

    def tombstone(t)
        { "station_id" => t.station_id, "name" => t.name, "status" => s(t.status),
          "removed_in" => t.removed_in, "removed_reason" => t.removed_reason }
    end

    def constant_set(set)
        span = set.record_span
        datum = set.datum
        { "set_id" => set.set_id, "source" => set.source, "source_type" => s(set.source_type),
          "quantity" => s(set.quantity), "source_record_id" => set.source_record_id,
          "source_version" => set.source_version,
          "record_span" => span && { "start" => time(span.start), "end" => time(span.end), "good_samples" => span.good_samples },
          "datum" => datum && { "msl_offset_m" => datum.msl_offset_m, "named" => datum.named },
          "qc_status" => s(set.qc_status),
          "qc_flags" => set.qc_flags.map { |f| { "flag" => s(f.flag), "verdict" => f.verdict, "values" => f.values } },
          "dropped_constituents" => set.dropped_constituents.map { |d| { "name" => d.name, "dropped_reason" => s(d.dropped_reason), "detail" => d.detail } },
          "is_recommended" => set.recommended?, "convention_id" => set.convention.convention_id,
          "licence_id" => set.licence.licence_id, "constituent_count" => set.constituents.size }
    end

    def constituent(c)
        { "name" => c.name, "source_name" => c.source_name, "doodson" => c.doodson,
          "speed_deg_per_hour" => c.speed_deg_per_hour, "amplitude_m" => c.amplitude_m, "phase_deg" => c.phase_deg,
          "amp_uncertainty_m" => c.amp_uncertainty_m, "phase_uncertainty_deg" => c.phase_uncertainty_deg,
          "kept_reason" => c.kept_reason }
    end

    def convention(c)
        { "convention_id" => c.convention_id, "phase_reference" => s(c.phase_reference),
          "utc_offset_hours" => c.utc_offset_hours, "v0_model" => c.v0_model, "nodal_handling" => s(c.nodal_handling),
          "nodal_formula_ids" => c.nodal_formula_ids, "constituent_table_version" => c.constituent_table_version,
          "tables_sha256" => c.tables_sha256, "canary" => c.canary }
    end

    def licence(l)
        { "licence_id" => l.licence_id, "spdx" => l.spdx, "provider" => l.provider, "citation" => l.citation,
          "attribution" => l.attribution, "url" => l.url }
    end

    def provenance(p)
        { "build_commit" => p.build_commit, "adapter_version" => p.adapter_version, "input_sha256" => p.input_sha256,
          "time_base" => p.time_base, "selection_reason" => p.selection_reason, "decision" => p.decision }
    end

    VALIDATION_NUMS = %w[time_mae_min time_p95_min time_bias_min height_mae_m range_error_m missed_events extra_events].freeze

    def validation(v)
        out = { "set_id" => v.set_id, "reference_source" => v.reference_source, "reference_station" => v.reference_station,
                "reference_distance_km" => v.reference_distance_km, "window" => v.window }
        VALIDATION_NUMS.each { |k| out[k] = v.public_send(k) }
        prev = v.previous_release
        out["previous_release"] = prev && VALIDATION_NUMS.to_h { |k| [k, prev.public_send(k)] }
        out
    end

    def offsets(o)
        { "reference_station_id" => o.reference_station_id, "time_offset_high_min" => o.time_offset_high_min,
          "time_offset_low_min" => o.time_offset_low_min, "height_offset_high" => o.height_offset_high,
          "height_offset_low" => o.height_offset_low, "height_adjusted_type" => s(o.height_adjusted_type),
          "licence_id" => o.licence_id }
    end
end

runner = Runner.new
$stdout.write(JSON.generate(runner.hello) + "\n")
$stdin.each_line do |line|
    next if line.strip.empty?
    reply = runner.handle(JSON.parse(line))
    $stdout.write(JSON.generate(reply) + "\n")
end
runner.close
