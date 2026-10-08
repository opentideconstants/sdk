# The Ruby API surface check (SDK spec §7.1): turns every name in
# conformance/api.json into its Ruby form by the manifest's naming rules and
# compares it with the gem's public surface. A missing or an extra name fails.
#
#     ruby conformance/runners/ruby/check_api.rb
#
# With OTC_RUBY_USE_INSTALLED=1 it checks the installed gem.
unless ENV["OTC_RUBY_USE_INSTALLED"] == "1"
    $LOAD_PATH.unshift(File.expand_path("../../../ruby/lib", __dir__))
end
require "json"
require "opentideconstants"

MANIFEST = JSON.parse(File.read(File.expand_path("../../api.json", __dir__)))
OTC = OpenTideConstants
# Names every Ruby object has; overriding one (inspect, to_s) is not API.
IGNORED = (Object.public_instance_methods + %i[inspect to_s]).uniq.freeze

$failures = []

def fail!(msg)
    $failures << msg
end

def compare(where, expected, actual)
    (expected - actual).sort.each { |n| fail!("#{where}: missing #{n}") }
    (actual - expected).sort.each { |n| fail!("#{where}: extra #{n}") }
end

# The Ruby name of a manifest member (naming.ruby).
def ruby_names(member)
    name = member["name"]
    base = if member["kind"] == "predicate" then "#{name.delete_prefix('is_')}?"
           elsif member["mutating"] then "#{name}!"
           else name
           end
    [base] + Array(member.dig("aliases", "ruby"))
end

def ruby_member?(member)
    langs = member["languages"]
    langs.nil? || langs.include?("ruby")
end

def public_methods_of(klass)
    (klass.public_instance_methods(true) - IGNORED).map(&:to_s)
end

def keyword_params(method)
    method.parameters.select { |t, _| %i[key keyreq].include?(t) }.map { |_, n| n.to_s }
end

objects = MANIFEST["objects"]

# ---- Client: instance methods, the forwarded Release operations, the constructor.
client = objects["Client"]
expected = []
client["members"].each do |m|
    next unless ruby_member?(m)
    next if m["static"]
    expected.concat(ruby_names(m))
end
objects["Release"]["members"].each do |m|
    expected.concat(ruby_names(m)) if m["forwarded_to_client"] && ruby_member?(m)
end
compare("OpenTideConstants (client)", expected.uniq, public_methods_of(OTC))

open_member = client["members"].find { |m| m["name"] == "open" }
opts = open_member["args"].map { |a| a["name"] }
compare("OpenTideConstants.new options", opts, keyword_params(OTC.instance_method(:initialize)))
compare("OpenTideConstants.open options", [], OTC.method(:open).parameters.map(&:last).map(&:to_s) - ["options", "block"])
fail!("OpenTideConstants.open is missing") unless OTC.respond_to?(:open)
open_member["args"].each do |a|
    next if a["default"].nil?
    default = OTC.instance_method(:initialize).parameters.find { |_, n| n.to_s == a["name"] }
    fail!("option #{a['name']} is missing") unless default
end

# Method arguments: keyword names and positional counts for every method.
check_args = lambda do |klass, m|
    names = ruby_names(m)
    meth = klass.instance_method(names.first.to_sym)
    params = meth.parameters
    pos = params.select { |t, _| %i[req opt].include?(t) }.size
    want_pos = m["args"].count { |a| a["positional"] }
    fail!("#{klass}##{names.first}: #{pos} positional arguments, expected #{want_pos}") if pos != want_pos
    want_kw = m["args"].reject { |a| a["positional"] }.map { |a| a["name"] }
    have_kw = keyword_params(meth)
    compare("#{klass}##{names.first} keywords", want_kw, have_kw)
    if m["filters"] && params.none? { |t, _| t == :keyrest }
        fail!("#{klass}##{names.first}: takes no filters (**filters)")
    end
end

# ---- every other object: its public methods are exactly its members.
class_for = {
    "Release" => OTC::Release, "ReleaseInfo" => OTC::ReleaseInfo, "FileInfo" => OTC::FileInfo,
    "Station" => OTC::Station, "Tombstone" => OTC::Tombstone, "ConstantSet" => OTC::ConstantSet,
    "Constituent" => OTC::Constituent, "Convention" => OTC::Convention, "Licence" => OTC::Licence,
    "Provenance" => OTC::Provenance, "QcFlag" => OTC::QcFlag, "DroppedConstituent" => OTC::DroppedConstituent,
    "Validation" => OTC::Validation, "SubordinateOffsets" => OTC::SubordinateOffsets, "Nearby" => OTC::Nearby,
    "UpdateResult" => OTC::UpdateResult, "RecordSpan" => OTC::RecordSpan, "Datum" => OTC::Datum,
    "Stats" => OTC::Stats
}
(objects.keys - ["Client"] - class_for.keys).each { |k| fail!("no Ruby class for manifest object #{k}") }
class_for.each do |name, klass|
    members = objects[name]["members"].select { |m| ruby_member?(m) }
    compare(name, members.flat_map { |m| ruby_names(m) }.uniq, public_methods_of(klass))
    members.each { |m| check_args.call(klass, m) if m["kind"] == "method" }
end
client["members"].each { |m| check_args.call(OTC, m) if m["kind"] == "method" && !m["static"] && ruby_member?(m) }

# ---- errors: classes, codes, detail fields.
base = OTC::Error
fail!("OpenTideConstants::Error must be a direct subclass of StandardError") unless base.superclass == StandardError
MANIFEST["errors"].each do |e|
    next unless e["languages"].include?("ruby") && e["class"]
    klass = OTC.const_get(e["class"]) if OTC.const_defined?(e["class"], false)
    unless klass
        fail!("error class OpenTideConstants::#{e['class']} is missing")
        next
    end
    fail!("#{klass} must be a direct subclass of #{base}") unless klass.superclass == base
    fail!("#{klass}::CODE is #{klass::CODE.inspect}, expected #{e['code']}") unless klass::CODE == e["code"]
    err = klass.allocate
    fail!("#{klass}#code is not #{e['code']}") unless err.code == e["code"]
    e["fields"].each do |f|
        fail!("#{klass} has no #{f}") unless klass.public_method_defined?(f)
    end
end
ruby_classes = MANIFEST["errors"].select { |e| e["languages"].include?("ruby") && e["class"] }.map { |e| e["class"] }
actual_errors = OTC.constants.map { |c| OTC.const_get(c) }
                   .select { |c| c.is_a?(Class) && c < base }.map { |c| c.name.split("::").last }
compare("error classes", ruby_classes, actual_errors)

# ---- constants and the phase 2 names (must not exist yet).
MANIFEST["constants"].each do |name, spec|
    next if name == "c_only"
    unless OTC.const_defined?(name, false)
        fail!("constant #{name} is missing")
        next
    end
    fail!("constant #{name} is #{OTC.const_get(name).inspect}, expected #{spec['value'].inspect}") unless OTC.const_get(name) == spec["value"]
end
MANIFEST["reserved_phase2"]["operations"].each do |op|
    if op["object"] == "Client" && OTC.public_method_defined?(op["name"])
        fail!("phase 2 operation #{op['name']} must not exist yet")
    end
end
fail!("phase 2 module Astro must not exist yet") if OTC.const_defined?(:Astro, false)

# ---- enums: the values the SDK maps to symbols.
MANIFEST["enums"].each do |name, values|
    known = OTC::ENUMS[name.to_sym]
    next if known.nil?
    compare("enum #{name}", values, known)
end

if $failures.empty?
    puts "API manifest check: OK (suite #{MANIFEST['suite_version']}, gem #{OTC::VERSION})"
    exit 0
end
$failures.each { |f| warn "FAIL #{f}" }
warn "API manifest check: #{$failures.size} problem(s)"
exit 1
