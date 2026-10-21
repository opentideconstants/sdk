# frozen_string_literal: true

require 'json'
require 'open3'

def selected_paths(files)
    shared = files.any? do |path|
        path == '.gitattributes' || path == '.github/ci_paths.rb' ||
            (path.start_with?('conformance/') && !path.match?(%r{\Aconformance/runners/(python|ruby|node|otc-swift|c)/}))
    end
    prefixes = {'python' => %w[python/ conformance/runners/python/],
        'ruby' => %w[ruby/ conformance/runners/ruby/],
        'typescript' => %w[js/ conformance/runners/node/],
        'swift' => %w[swift/ conformance/runners/otc-swift/]}
    selected = prefixes.to_h do |name, paths|
        [name, shared || files.any? { |path| paths.any? { |prefix| path.start_with?(prefix) } || path == ".github/workflows/#{name}.yml" }]
    end
    # The cross workflow owns Swift native qualification as well as interop.
    selected['swift'] ||= files.include?('.github/workflows/cross.yml')
    selected['cross'] = selected.values.any? || files.include?('.github/workflows/cross.yml')
    selected
end

if $PROGRAM_NAME == __FILE__
    event = JSON.parse(File.read(ENV.fetch('GITHUB_EVENT_PATH')))
    range = case ENV.fetch('GITHUB_EVENT_NAME')
    when 'pull_request'
        pr = event.fetch('pull_request')
        "#{pr.fetch('base').fetch('sha')}...#{pr.fetch('head').fetch('sha')}"
    when 'push'
        before = event.fetch('before')
        default_branch = event.fetch('repository').fetch('default_branch')
        if event.fetch('ref') == "refs/heads/#{default_branch}"
            "#{before}..#{event.fetch('after')}" unless before == '0' * 40
        else
            # A push can replace the PR run: cover the whole branch, not just its last commit.
            "origin/#{default_branch}...#{event.fetch('after')}"
        end
    end
    files = nil
    if range
        output, error, status = Open3.capture3('git', 'diff', '--name-only', '--no-renames', '-z', range, '--')
        if status.success?
            files = output.split("\0")
        else
            warn "Changed-path comparison unavailable; run all active SDK checks: #{error.strip}"
        end
    end
    # Manual runs and unavailable history run all checks safely.
    selected = files ? selected_paths(files) : %w[python ruby typescript swift cross].to_h { |name| [name, true] }
    result = selected.map { |name, value| "#{name}=#{value}\n" }.join
    File.open(ENV.fetch('GITHUB_OUTPUT'), 'a') { |file| file.write(result) }
    print result
end
