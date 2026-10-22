# frozen_string_literal: true

# Fixed native-data agreement cohort. This is not an independent scientific oracle.
require 'json'
require 'digest'
require 'open3'
require 'optparse'
require 'timeout'
require 'tmpdir'
require 'time'
require 'rbconfig'

$stdout.sync = true

ROOT = File.expand_path('../..', __dir__)
COHORT_PATH = File.join(__dir__, 'cohort.json')
COMMANDS = {
    'python' => ['python3', 'conformance/runners/python/runner.py'],
    'ruby' => [RbConfig.ruby, 'conformance/runners/ruby/runner.rb'],
    'typescript' => ['node', 'conformance/runners/node/runner.mjs'],
    'swift' => ['swift', 'run', '--skip-build', '--configuration', 'release', '--package-path', 'conformance/runners/otc-swift', 'Runner']
}.freeze

def require_equal(want, got, where)
    raise "#{where}: exact value/type differs" unless exact?(want, got)
end

def exact?(want, got)
    case want
    when Hash
        got.is_a?(Hash) && want.keys.sort == got.keys.sort && want.all? { |key, value| exact?(value, got[key]) }
    when Array
        got.is_a?(Array) && want.length == got.length && want.zip(got).all? { |a, b| exact?(a, b) }
    when Numeric
        got.is_a?(Numeric) && got.finite? && want == got
    else
        want.class == got.class && want == got
    end
end

def number?(value)
    value.is_a?(Numeric) && value.finite?
end

# Mechanically follows conformance/tools/run_vectors.py compare_prediction:
# exact metadata, keys, count and order; tolerance only for its named quantities.
def compare_prediction(want, got, op, tolerances)
    raise 'prediction keys differ' unless got.is_a?(Hash) && want.keys.sort == got.keys.sort
    require_equal(want.reject { |key, _| key == 'items' }, got.reject { |key, _| key == 'items' }, 'prediction metadata')
    items = got.fetch('items')
    expected = want.fetch('items')
    raise 'ordered item count differs' unless items.is_a?(Array) && items.length == expected.length
    expected.zip(items).each_with_index do |(a, b), index|
        raise "item #{index} keys differ" unless b.is_a?(Hash) && a.keys.sort == b.keys.sort
        a.each do |key, value|
            observed = b.fetch(key)
            where = "items[#{index}].#{key}"
            case key
            when 'time'
                if %w[extremes current_events].include?(op)
                    pattern = /\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\z/
                    raise "#{where}: invalid event time" unless value.is_a?(String) && observed.is_a?(String) && value.match?(pattern) && observed.match?(pattern)
                    raise "#{where}: paired event time differs" if (Time.iso8601(value) - Time.iso8601(observed)).abs > tolerances.fetch('time_s')
                else
                    require_equal(value, observed, where)
                end
            when 'direction_deg'
                if value.nil?
                    require_equal(nil, observed, where)
                else
                    raise "#{where}: invalid direction" unless number?(observed) && observed >= 0 && observed < 360
                    speed = a.fetch('speed_ms', a.fetch('velocity_ms', 0).abs)
                    if speed >= tolerances.fetch('direction_min_speed_ms') && ((observed - value + 180) % 360 - 180).abs > tolerances.fetch('direction_deg')
                        raise "#{where}: circular angle differs"
                    end
                end
            when 'height_m', 'velocity_major_ms', 'velocity_minor_ms', 'speed_ms', 'velocity_ms'
                tolerance = tolerances.fetch(key == 'height_m' ? 'height_m' : 'velocity_ms')
                raise "#{where}: numeric difference exceeds #{tolerance}" unless number?(observed) && (observed - value).abs <= tolerance
            else
                require_equal(value, observed, where)
            end
        end
    end
end

def compare_reply(row, want, got, tolerances)
    require_equal(want.keys.sort, got.keys.sort, row.fetch('id') + ' reply keys')
    require_equal(want.fetch('ok'), got.fetch('ok'), row.fetch('id') + ' ok')
    if row['expected_error']
        error = got.fetch('error')
        require_equal(want.fetch('error').keys.sort, error.keys.sort, 'error keys')
        require_equal(want.fetch('error').reject { |key, _| key == 'message' }, error.reject { |key, _| key == 'message' }, 'typed refusal')
        raise 'error message missing' unless error['message'].is_a?(String) && !error['message'].empty?
    elsif row.dig('request', 'op') && want.fetch('result').key?('prediction')
        require_equal(['prediction'], got.fetch('result').keys, 'result keys')
        compare_prediction(want.fetch('result').fetch('prediction'), got.fetch('result').fetch('prediction'), row.fetch('request').fetch('op'), tolerances)
    else
        require_equal(want, got, row.fetch('id'))
    end
end

def authenticate(cohort, native)
    raise 'expected test subset label' unless cohort.fetch('kind') == 'test_subset_not_whole_release'
    pins = cohort.fetch('slice').fetch('files')
    pins.each do |name, digest|
        path = File.join(__dir__, name)
        raise "#{name}: not a regular file" unless File.file?(path) && !File.symlink?(path)
        raise "#{name}: SHA-256 mismatch" unless Digest::SHA256.file(path).hexdigest == digest
    end
    sidecar = pins.map { |name, digest| "#{digest}  #{name}\n" }.join
    require_equal(sidecar, File.read(File.join(__dir__, 'OTC_20261011.sha256')), 'subset checksum sidecar')
    selected = cohort.fetch('slice').fetch('stations')
    slice = {}
    File.foreach(File.join(__dir__, 'OTC_20261011.jsonl')) do |line|
        id = JSON.parse(line).fetch('station_id')
        raise 'duplicate slice station' if slice.key?(id)
        slice[id] = {'sha256' => Digest::SHA256.hexdigest(line), 'bytes' => line.bytesize}
    end
    require_equal(selected, slice, 'seven complete raw station identities')
    raise 'expected seven station records' unless slice.length == 7
    return unless native

    source = cohort.fetch('source')
    raise 'full frozen native size mismatch' unless File.size(native) == source.fetch('bytes')
    raise 'full frozen native SHA-256 mismatch' unless Digest::SHA256.file(native).hexdigest == source.fetch('sha256')
    metadata = native.sub(/\.jsonl\z/, '.meta.json')
    raise 'full metadata SHA-256 mismatch' unless Digest::SHA256.file(metadata).hexdigest == source.fetch('metadata_sha256')
    raw = {}
    File.foreach(native) do |line|
        id = JSON.parse(line).fetch('station_id')
        next unless selected.key?(id)
        raise 'duplicate native station' if raw.key?(id)
        raw[id] = {'sha256' => Digest::SHA256.hexdigest(line), 'bytes' => line.bytesize}
    end
    require_equal(selected, raw, 'slice versus full native raw lines')
end

# Six datum cells independently bind source values/labels and actual height shifts.
def value_checks(cohort, replies)
    records = File.foreach(File.join(__dir__, 'OTC_20261011.jsonl')).map { |line| JSON.parse(line) }.to_h { |station| [station.fetch('station_id'), station] }
    rows = cohort.fetch('requests').to_h { |row| [row.fetch('id'), row] }
    %w[noaa ticon belfast].each do |label|
        args = rows.fetch(label + '-datums').fetch('request').fetch('args')
        station = records.fetch(args.fetch('station_id'))
        source = if args['set_id']
            station.fetch('constant_sets').find { |set| set['set_id'] == args['set_id'] }.fetch('datum')
        else
            station.fetch('subordinate_offsets').fetch('datum')
        end
        info = replies.fetch(label + '-datums').fetch('result').fetch('datums')
        %w[lat hat].each do |datum|
            level = info.fetch('levels').find { |entry| entry['key'] == datum }
            basis = source.fetch('basis').fetch(datum)
            require_equal(source.fetch('named').fetch(datum), level.fetch('value_m'), label + ' source value')
            %w[kind method source_name uncertainty_m uncertainty_basis].each { |key| require_equal(basis[key], level[key], label + ' source ' + key) }
            require_equal(basis['fallback'], level['fallback'], label + ' fallback warning')
            op = label == 'belfast' ? 'events' : 'heights'
            baseline = label == 'belfast' ? 'mllw' : 'mean_level'
            original = replies.fetch("#{label}-#{op}-#{baseline}").fetch('result').fetch('prediction')
            shifted = replies.fetch("#{label}-#{op}-#{datum}").fetch('result').fetch('prediction')
            mean = label == 'belfast' ? source.fetch('named').fetch('mllw') : source.fetch('msl_offset_m', 0.0)
            shift = mean - source.fetch('named').fetch(datum)
            raise 'empty datum value check' if original.fetch('items').empty?
            require_equal(original.fetch('items').length, shifted.fetch('items').length, 'datum item count')
            require_equal(datum, shifted.fetch('datum_name'), 'datum label')
            require_equal(basis.fetch('kind'), shifted.fetch('datum_kind'), 'datum kind')
            require_equal(basis['uncertainty_m'], shifted.fetch('datum_uncertainty_m'), 'datum uncertainty')
            original.fetch('items').zip(shifted.fetch('items')).each do |a, b|
                require_equal(a.fetch('time'), b.fetch('time'), 'datum pairing')
                raise 'datum source shift differs' if (b.fetch('height_m') - a.fetch('height_m') - shift).abs > cohort.fetch('tolerances').fetch('height_m')
            end
            puts "VALUE #{label}/#{datum}: source=#{level.fetch('value_m')}m kind=#{level.fetch('kind')} shift=#{shift}m; labels/warnings PASS"
        end
    end
    constituents = replies.fetch('fes-constituents').fetch('result').fetch('constituents')
    raise 'FES full34 constituents missing' unless constituents.length == 34 && %w[MSQM MTM].all? { |name| constituents.any? { |c| c['name'] == name } }
    prediction = replies.fetch('subordinate-events').fetch('result').fetch('prediction')
    {'bin_number' => 1, 'reference_bin' => 13, 'reference_station_id' => 'OTC-0cfcf1db', 'method' => 'offsets'}.each { |key, value| require_equal(value, prediction.fetch(key), 'subordinate ' + key) }
end

def run_sdk(name, command, input, cohort, log_dir, reference)
    replies = {}
    Dir.mktmpdir('otc-current-data-') do |cache|
        env = {'PYTHONDONTWRITEBYTECODE' => '1', 'OPENTIDECONSTANTS_OFFLINE' => '1', 'XDG_CACHE_HOME' => cache}
        Open3.popen3(env, *command, chdir: ROOT, pgroup: true) do |stdin, stdout, stderr, waiter|
            drainer = Thread.new { File.open(File.join(log_dir, name + '.stderr'), 'w') { |file| IO.copy_stream(stderr, file) } }
            begin
                read = lambda { Timeout.timeout(180) { JSON.parse(stdout.gets || raise('runner closed early')) } }
                hello = read.call.fetch('hello')
                raise 'prediction feature absent' unless hello.fetch('features').include?('predict')
                calls = [{'id' => 'open', 'request' => {'op' => 'open', 'args' => {'file' => input, 'mode' => 'stream'}}}] + cohort.fetch('requests') + [{'id' => 'close', 'request' => {'op' => 'close'}}]
                File.open(File.join(log_dir, name + '.jsonl'), 'w') do |log|
                    calls.each do |row|
                        stdin.puts(JSON.generate(row.fetch('request')))
                        stdin.flush
                        reply = read.call
                        log.puts(JSON.generate({'id' => row.fetch('id'), 'reply' => reply}))
                        log.flush
                        if row['expected_error']
                            raise "#{row['id']}: expected typed refusal" unless reply['ok'] == false && reply.dig('error', 'code') == row['expected_error']
                        else
                            raise "#{row['id']}: native operation failed: #{reply.dig('error', 'code')}" unless reply['ok'] == true
                            prediction = reply.dig('result', 'prediction')
                            raise "#{row['id']}: no prediction items" if prediction && prediction.fetch('items').empty?
                        end
                        if row['id'] == 'open'
                            require_equal('20261011', reply.fetch('result').fetch('datestamp'), 'opened release')
                            require_equal('file', reply.fetch('result').fetch('loaded_from'), 'opened source')
                        elsif row['id'] != 'close'
                            compare_reply(row, reference.fetch(row.fetch('id')), reply, cohort.fetch('tolerances')) if reference
                            replies[row.fetch('id')] = reply
                        end
                    end
                end
                stdin.close
                raise 'runner exit timeout' unless waiter.join(30)
                raise "runner #{name} exited unsuccessfully" unless waiter.value.success?
            ensure
                stdin.close unless stdin.closed?
                unless waiter.join(1)
                    Process.kill('KILL', -waiter.pid)
                    waiter.join
                end
                drainer.join
            end
        end
    end
    value_checks(cohort, replies)
    puts "#{name}: #{replies.length}/#{cohort.fetch('requests').length} fixed requests PASS (zero skips)"
    replies
end

# Continue only the interrupted Swift leg of this fixed full-native batch.
# The three retained SDK legs are authenticated and checked, never executed again.
def retained_batch(cohort, directory)
    binding = cohort.fetch('retained_full_native')
    require_equal(cohort.fetch('source').fetch('sha256'), binding.fetch('source_sha256'), 'retained full source')
    require_equal(cohort.fetch('source').fetch('metadata_sha256'), binding.fetch('metadata_sha256'), 'retained metadata')
    require_equal(Digest::SHA256.hexdigest(JSON.generate(cohort.fetch('requests'))), binding.fetch('requests_sha256'), 'retained fixed requests')
    require_equal(Digest::SHA256.hexdigest(JSON.generate(cohort.fetch('python_reference'))), binding.fetch('reference_sha256'), 'retained Python reference')
    require_equal(cohort.fetch('sdk_base'), binding.fetch('sdk_base'), 'retained SDK source base')
    _, error, status = Open3.capture3('git', 'diff', '--quiet', binding.fetch('sdk_base'), '--', 'python', 'ruby', 'js', 'swift', 'conformance/runners', chdir: ROOT)
    raise "retained SDK source changed: #{error}" unless status.success?
    expected_ids = ['open'] + cohort.fetch('requests').map { |row| row.fetch('id') } + ['close']
    require_equal(%w[python ruby typescript], binding.fetch('outputs').keys, 'retained SDK legs')
    binding.fetch('outputs').each do |name, digest|
        path = File.join(directory, name + '.jsonl')
        raise 'retained output must be a regular file' unless File.file?(path) && !File.symlink?(path)
        require_equal(digest, Digest::SHA256.file(path).hexdigest, name + ' retained output bytes')
        records = File.foreach(path).map { |line| JSON.parse(line) }
        require_equal(expected_ids, records.map { |row| row.fetch('id') }, name + ' retained request order/count')
        records.each { |row| require_equal(%w[id reply], row.keys.sort, 'retained record keys') }
        opened = records.first.fetch('reply')
        require_equal(true, opened.fetch('ok'), name + ' retained open')
        require_equal('file', opened.fetch('result').fetch('loaded_from'), name + ' retained source')
        require_equal('20261011', opened.fetch('result').fetch('datestamp'), name + ' retained release')
        require_equal(true, records.last.fetch('reply').fetch('ok'), name + ' retained close')
        cohort.fetch('requests').zip(records[1...-1]).each do |row, record|
            want = cohort.fetch('python_reference').fetch(row.fetch('id'))
            require_equal(want, record.fetch('reply'), 'retained captured Python reply') if name == 'python'
            compare_reply(row, want, record.fetch('reply'), cohort.fetch('tolerances'))
        end
        value_checks(cohort, records[1...-1].to_h { |row| [row.fetch('id'), row.fetch('reply')] })
        puts "REUSE #{name}: 25/25 retained full-native requests and output bindings PASS (not rerun)"
    end
end

options = {}
OptionParser.new do |parser|
    parser.on('--native PATH') { |value| options[:native] = File.expand_path(value) }
    parser.on('--capture-reference') { options[:capture] = true }
    parser.on('--report PATH') { |value| options[:report] = value }
    parser.on('--logs PATH') { |value| options[:logs] = File.expand_path(value) }
    parser.on('--continue-swift PATH') { |value| options[:continuation] = File.expand_path(value) }
end.parse!
raise 'unexpected arguments' unless ARGV.empty?
raise 'reference capture requires full frozen native' if options[:capture] && !options[:native]
raise 'Swift continuation requires native input and retained reference' if options[:continuation] && (!options[:native] || options[:capture])
cohort = JSON.parse(File.read(COHORT_PATH))
authenticate(cohort, options[:native])
puts 'BINDING: frozen source pins and seven complete test-subset station records PASS'
input = options[:native] || File.join(__dir__, 'OTC_20261011.jsonl')
reference = options[:capture] ? nil : cohort.fetch('python_reference')
retained_batch(cohort, options[:continuation]) if options[:continuation]
Dir.mktmpdir('otc-current-logs-') do |temporary|
    logs = options[:logs] || temporary
    Dir.mkdir(logs) unless Dir.exist?(logs)
    commands = options[:continuation] ? COMMANDS.slice('swift') : COMMANDS
    commands.each do |name, command|
        replies = run_sdk(name, command, input, cohort, logs, reference)
        if name == 'python' && options[:capture]
            reference = replies
            cohort['python_reference'] = replies
            File.write(COHORT_PATH, JSON.pretty_generate(cohort) + "\n")
        end
    end
end
report = {'status' => 'PASS', 'sdk_count' => COMMANDS.length, 'requests_per_sdk' => cohort.fetch('requests').length, 'skips' => 0, 'input' => options[:native] ? 'full_frozen_native' : 'test_subset', 'scientific_accuracy_claim' => false}
File.write(options[:report], JSON.pretty_generate(report) + "\n") if options[:report]
puts 'GREEN: four SDKs agree with captured full-native Python replies; fixed current-data CI binding PASS'
