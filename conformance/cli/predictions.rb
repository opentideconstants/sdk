require 'json'
require 'open3'
require 'fileutils'
require 'socket'
require 'time'

root = File.expand_path('../..', __dir__)
file = File.expand_path(ENV.fetch('OTC_CLI_NATIVE_JSONL'))
evidence = File.expand_path(ENV.fetch('OTC_CLI_EVIDENCE'))
cache = File.expand_path(ENV.fetch('OTC_CLI_CACHE'))
FileUtils.mkdir_p(evidence)
window = ['--from', '2010-02-28T16:00:00-08:00', '--to', '2010-03-31T17:00:00-07:00']
cases = [
    ['extremes', 'OTC-873d5222', ['--datum', 'mean_level', '--units', 'meters'], 'extremes', { datum: 'mean_level', units: 'meters' }],
    ['timeline', 'OTC-873d5222', ['--step', '10800', '--datum', 'mean_level', '--units', 'feet'], 'heights', { step_s: 10800, datum: 'mean_level', units: 'feet' }],
    ['currents', 'OTC-f2ecceab', ['--step', '10800', '--bin', '15', '--units', 'knots'], 'currents', { step_s: 10800, bin_number: 15, units: 'knots' }]
]

def check(condition, label)
    raise "FAIL: #{label}" unless condition
    puts "PASS: #{label}"
end

def cli(root, evidence, label, args)
    stdout, stderr, status = Open3.capture3('node', File.join(root, 'js/bin/otc.js'), *args)
    File.write(File.join(evidence, "#{label}.stdout"), stdout)
    File.write(File.join(evidence, "#{label}.stderr"), stderr)
    check(status.success?, "#{label} exit #{status.exitstatus}")
    stdout
end

requests = [{ op: 'open', args: { file: file, mode: 'stream' } }]
cases.each do |_, station, _, operation, options|
    requests << { op: operation, args: options.merge(station_id: station, start: window[1], stop: window[3]) }
end
requests << { op: 'search', args: { name: 'SAN FRANCISCO' } }
stdout, stderr, status = Open3.capture3('node', File.join(root, 'conformance/runners/node/runner.mjs'),
    stdin_data: requests.map { |request| JSON.generate(request) }.join("\n") + "\n")
File.write(File.join(evidence, 'native-green.jsonl'), stdout)
File.write(File.join(evidence, 'native-green.stderr'), stderr)
check(status.success?, 'native runner succeeds')
replies = stdout.lines.map { |line| JSON.parse(line) }
check(replies.shift.key?('hello'), 'native runner handshake')
check(replies.all? { |reply| reply['ok'] }, 'native prerequisites succeed')
expected = replies.drop(1).take(3).map { |reply| reply.fetch('result').fetch('prediction') }
expected.each { |prediction| check(prediction && !prediction.fetch('items').empty?, 'native prediction is nonempty') }

cases.each_with_index do |(command, station, flags, _, _), index|
    args = [command, station, '--file', file, *window, *flags, '--json']
    actual = JSON.parse(cli(root, evidence, "#{command}-green", args)).fetch('prediction')
    check(actual == expected[index], "#{command} equals native values, order, metadata and units (#{actual['items'].length} items)")
end

# Direct consumer regression after the shared parser changes.
station_args = ['--file', file, '--query', 'SAN FRANCISCO', '--json']
stations = JSON.parse(cli(root, evidence, 'stations-regression', ['stations', *station_args]))
search = JSON.parse(cli(root, evidence, 'search-regression', ['search', 'SAN FRANCISCO', '--file', file, '--json']))
check(search == stations, 'station query and alias remain identical')
check(stations.fetch('stations').map { |station| station.fetch('station_id') } == replies.last.fetch('result').fetch('station_ids'), 'station search still equals native SDK')

# Text retains all JSON metadata and values; its timestamps display system-local time.
text = cli(root, evidence, 'timeline-text', ['timeline', 'OTC-873d5222', '--file', file, *window, *cases[1][2]])
lines = text.lines.map(&:chomp)
metadata = {}
while lines.first&.start_with?('# ')
    key, value = lines.shift.delete_prefix('# ').split("\t", 2)
    metadata[key] = JSON.parse(value)
end
lines.shift if lines.first == ''
keys = lines.shift.split("\t")
items = lines.map do |line|
    row = keys.zip(line.split("\t").map { |value| JSON.parse(value) }).to_h
    row['time'] = Time.strptime(row.fetch('time'), '%m/%d/%Y, %I:%M:%S %p %Z').utc.iso8601
    row
end
check(metadata.merge('items' => items) == expected[1], 'timeline text equals all JSON values and metadata')

# The cache was produced by the existing SDK. This listener only counts network attempts.
server = TCPServer.new('127.0.0.1', 0)
requests_seen = Queue.new
thread = Thread.new do
    loop do
        socket = server.accept
        requests_seen << true
        socket.close
    end
rescue IOError, Errno::EBADF
    raise unless server.closed?
end
begin
    offline = JSON.parse(cli(root, evidence, 'timeline-offline', [
        'timeline', 'OTC-873d5222', '--release', expected[1].fetch('release'), '--cache-dir', cache,
        '--base-url', "http://127.0.0.1:#{server.addr[1]}/", '--offline', '--mode', 'stream', *window, *cases[1][2], '--json'
    ])).fetch('prediction')
    check(offline == expected[1], 'cached offline timeline equals native prediction')
    check(requests_seen.empty?, 'offline timeline made zero network requests')
    File.write(File.join(evidence, 'offline-proof.json'), JSON.pretty_generate({ offline_network_requests: requests_seen.size, items: offline['items'].length }) + "\n")
ensure
    server.close
    thread.join
end
puts 'PASS: three local prediction commands; station regression, text and offline checks'
