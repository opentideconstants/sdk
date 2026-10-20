require 'json'
require 'open3'
require 'fileutils'
require 'digest'
require 'socket'

# Real SDK/CLI comparison. Supply a native JSONL plus its metadata and checksum companions.
root = File.expand_path('../..', __dir__)
file = File.expand_path(ENV.fetch('OTC_CLI_NATIVE_JSONL'))
evidence = File.expand_path(ENV.fetch('OTC_CLI_EVIDENCE'))
FileUtils.mkdir_p(evidence)
command = ENV['OTC_CLI_BIN'] ? [File.expand_path(ENV['OTC_CLI_BIN'])] : ['node', File.join(root, 'js/bin/otc.js')]
query = 'SAN FRANCISCO'

def check(condition, label)
    raise "FAIL: #{label}" unless condition
    puts "PASS: #{label}"
end

def runner(root, requests)
    input = requests.map { |request| JSON.generate(request) }.join("\n") + "\n"
    stdout, stderr, status = Open3.capture3('node', File.join(root, 'conformance/runners/node/runner.mjs'), stdin_data: input)
    raise "native runner failed: #{stderr}" unless status.success?
    replies = stdout.lines.map { |line| JSON.parse(line) }
    raise 'native runner handshake absent' unless replies.shift.key?('hello')
    raise "native runner operation failed: #{replies.inspect}" unless replies.all? { |reply| reply['ok'] }
    replies.map { |reply| reply.fetch('result') }
end

def cli(command, evidence, label, args, success: true)
    stdout, stderr, status = Open3.capture3(*command, *args)
    File.write(File.join(evidence, "#{label}.stdout"), stdout)
    File.write(File.join(evidence, "#{label}.stderr"), stderr)
    check(status.success? == success, "#{label} exit #{status.exitstatus}")
    check(stdout.empty?, "#{label} no success output on error") unless success
    stdout
end

reference = runner(root, [
    { op: 'open', args: { file: file, mode: 'stream' } },
    { op: 'search', args: { name: query } },
    { op: 'stations', args: {} },
    { op: 'search', args: { name: query, limit: 3 } }
])
File.write(File.join(evidence, 'native-reference.json'), JSON.pretty_generate(reference) + "\n")
expected = reference[1].fetch('station_ids')
check(!expected.empty?, 'actual native name search has results')
search_args = ['--file', file, '--query', query]
json = JSON.parse(cli(command, evidence, 'stations-green', ['stations', *search_args, '--json']))
check(json.fetch('stations').map { |station| station.fetch('station_id') } == expected, 'stations query equals native SDK ordered IDs')
alias_json = JSON.parse(cli(command, evidence, 'search-green', ['search', query, '--file', file, '--json']))
check(alias_json == json, 'search alias equals stations query JSON')
text = cli(command, evidence, 'text-green', ['stations', *search_args])
check(text.lines.drop(1).map { |line| line.split("\t", 2).first } == expected, 'text and JSON identify the same ordered stations')
listed = JSON.parse(cli(command, evidence, 'list-green', ['stations', '--file', file, '--mode', 'stream', '--json']))
check(listed.fetch('stations').map { |station| station.fetch('station_id') } == reference[2]['station_ids'], 'list equals native SDK stations')
limited = JSON.parse(cli(command, evidence, 'limit-green', ['search', query, '--file', file, '--limit', '3', '--json']))
check(limited.fetch('stations').map { |station| station.fetch('station_id') } == reference[3]['station_ids'], 'limit delegates to native search')
cli(command, evidence, 'unknown-option', ['stations', '--unknown'], success: false)
cli(command, evidence, 'missing-name', ['search'], success: false)
cli(command, evidence, 'missing-option-value', ['stations', '--file'], success: false)
check(cli(command, evidence, 'help', ['--help']).include?('otc search'), 'help describes the search alias')

# Prime a real cache through the SDK from the unchanged native bytes. The HTTP
# listener then becomes a tripwire: offline execution must make zero requests.
metadata = JSON.parse(File.read(file.sub(/\.jsonl\z/, '.meta.json')))
stamp = metadata.fetch('release').fetch('datestamp')
files = [file, file.sub(/\.jsonl\z/, '.meta.json'), file.sub(/\.jsonl\z/, '.sha256')]
rows = files.map do |path|
    { name: File.basename(path), url: File.basename(path), size: File.size(path), sha256: Digest::SHA256.file(path).hexdigest }
end
pointer = { datestamp: stamp, format_version: metadata.fetch('format_version'), files: rows }
index = JSON.generate(releases: [pointer])
server = TCPServer.new('127.0.0.1', 0)
base_url = "http://127.0.0.1:#{server.addr[1]}/"
requests = Queue.new
thread = Thread.new do
    loop do
        socket = server.accept
        begin
            line = socket.gets
            next unless line
            path = line.split[1]
            requests << path
            while (header = socket.gets) && header != "\r\n"; end
            selected = files.find { |candidate| path == "/#{File.basename(candidate)}" }
            body = path == '/OTC_index.json' ? index : nil
            if selected || body
                size = selected ? File.size(selected) : body.bytesize
                socket.write("HTTP/1.1 200 OK\r\nContent-Length: #{size}\r\nConnection: close\r\n\r\n")
                selected ? File.open(selected, 'rb') { |source| IO.copy_stream(source, socket) } : socket.write(body)
            else
                socket.write("HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            end
        ensure
            socket.close
        end
    end
rescue IOError, Errno::EBADF
    raise unless server.closed?
end
begin
    cache = File.join(evidence, 'cache')
    runner(root, [{ op: 'open', args: { release: stamp, cache_dir: cache, base_url: base_url, mode: 'stream' } }])
    before = requests.size
    offline = JSON.parse(cli(command, evidence, 'offline-green', [
        'search', query, '--release', stamp, '--cache-dir', cache, '--base-url', base_url, '--mode', 'stream', '--offline', '--json'
    ]))
    check(offline == json, 'pinned cached offline search equals direct file search')
    check(requests.size == before, 'offline command made zero HTTP requests')
    File.write(File.join(evidence, 'offline-proof.json'), JSON.pretty_generate({
        release: stamp, priming_http_requests: before, offline_http_requests: requests.size - before,
        station_ids: expected, source_sha256: Digest::SHA256.file(file).hexdigest
    }) + "\n")
ensure
    server.close
    thread.join
end
puts "PASS: stations command family; #{expected.length} actual search results; #{reference[2]['station_ids'].length} listed stations"
