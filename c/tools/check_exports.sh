#!/usr/bin/env ruby
require 'open3'

abort 'usage: check_exports.sh LIBRARY [LIBRARY...]' if ARGV.empty?
ARGV.each do |path|
    command = RUBY_PLATFORM.include?('darwin') ? ['nm', '-gU', path] : ['nm', '-g', '--defined-only', path]
    output, status = Open3.capture2e(*command)
    abort output unless status.success?
    symbols = output.lines.map do |line|
        match = line.match(/\s[A-Za-z]\s(\S+)\s*$/)
        match && match[1].sub(/\A_/, '')
    end
    symbols = symbols.compact
    bad = symbols.reject { |name| name.start_with?('otc_') }
    abort "#{path}: unprefixed native symbols: #{bad.join(', ')}" unless bad.empty?
    puts "#{path}: #{symbols.size} defined globals, all namespaced OTC"
end
