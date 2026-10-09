# The Ruby API surface check (SDK spec §7.1): turns every name in
# conformance/api.json into its Ruby form by the manifest's naming rules and
# compares it with the gem's public surface. A missing or an extra name fails,
# and so does a wrong default, a phase 2 name, or a manifest enum the check
# cannot find in the gem. The check never stops at the first problem: a
# missing method, class or CODE is reported, and the rest is still checked.
#
#     ruby conformance/runners/ruby/check_api.rb [--no-self-test]
#
# With OTC_RUBY_USE_INSTALLED=1 it checks the installed gem. After the check it
# runs its own mutation self-test (each mutation of the gem must be caught).
unless ENV["OTC_RUBY_USE_INSTALLED"] == "1"
    $LOAD_PATH.unshift(File.expand_path("../../../ruby/lib", __dir__))
end
require "json"
require "tempfile"
require "opentideconstants"

MANIFEST = JSON.parse(File.read(File.expand_path("../../api.json", __dir__)))
OTC = OpenTideConstants
# Names every Ruby object has; overriding one (inspect, to_s) is not API.
IGNORED = (Object.public_instance_methods + %i[inspect to_s]).uniq.freeze
# base_url defaults to nil, which means OPENTIDECONSTANTS_BASE_URL or DEFAULT_BASE_URL (spec §4.2).
DEFAULT_EXCEPTIONS = [%w[Client open base_url]].freeze
# Where the gem keeps the values of a manifest enum: OpenTideConstants::ENUMS,
# or a client constant (an option's values).
ENUM_CONSTANTS = { "format" => :FORMATS, "mode" => :MODES, "on_network_error" => :ON_NETWORK_ERROR }.freeze
# Manifest enums the gem has no value list for: it returns these values as
# symbols it never compares with a list (loaded_from), or keeps the raw string
# (canary_status, decision_tier, decision_outcome), or takes the one value as
# an argument (match). Every other manifest enum must have a list.
NO_RUBY_LIST = %w[loaded_from canary_status decision_tier decision_outcome match].freeze

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

# A manifest value in the form the comparison uses: symbols are strings.
def norm(value)
    case value
    when Symbol then value.to_s
    when Array then value.map { |v| norm(v) }
    else value
    end
end

# The default values of a method's optional parameters, by name. Ruby cannot
# report them, so this reads the parameter list from the method's source and
# evaluates it as a lambda's parameter list in the class (the defaults are
# literals or constants), calling it with a placeholder for each required one.
def defaults_of(klass, meth)
    return {} if meth.parameters.none? { |t, _| %i[opt key].include?(t) }
    file, line = meth.source_location
    raise "no source location" unless file && File.file?(file)
    src = File.readlines(file)[(line - 1)..].join
    start = src.index(/def\s+(self\.)?#{Regexp.escape(meth.name.to_s)}\s*\(/) or
        raise "no def #{meth.name} with parentheses"
    i = src.index("(", start)
    depth = 0
    j = i
    loop do
        c = src[j]
        raise "unbalanced parameter list" if c.nil?
        depth += 1 if c == "("
        depth -= 1 if c == ")"
        break if depth.zero?
        j += 1
    end
    params = src[(i + 1)...j]
    fn = klass.class_eval("->(#{params}) { binding }", file, line)
    args = meth.parameters.select { |t, _| t == :req }.map { nil }
    kwargs = meth.parameters.select { |t, _| t == :keyreq }.to_h { |_, n| [n, nil] }
    b = fn.call(*args, **kwargs)
    meth.parameters.select { |t, _| %i[opt key].include?(t) }.to_h { |_, n| [n.to_s, b.local_variable_get(n)] }
end

def run_checks
    failures = []
    fail = ->(msg) { failures << msg }
    compare = lambda do |where, expected, actual|
        (expected - actual).sort.each { |n| fail.call("#{where}: missing #{n}") }
        (actual - expected).sort.each { |n| fail.call("#{where}: extra #{n}") }
    end
    objects = MANIFEST["objects"]

    # Optional arguments with a manifest default: the same default in Ruby.
    check_defaults = lambda do |where, obj_name, klass, meth, m|
        defaults = begin
            defaults_of(klass, meth)
        rescue StandardError, SyntaxError => e
            fail.call("#{where}: cannot read the defaults (#{e.class}: #{e.message})")
            return
        end
        (m["args"] || []).each do |a|
            next if a["required"] || !a.key?("default")
            next if DEFAULT_EXCEPTIONS.include?([obj_name, m["name"], a["name"]])
            unless defaults.key?(a["name"])
                fail.call("#{where}(#{a['name']}): must be optional")
                next
            end
            got = defaults[a["name"]]
            fail.call("#{where}(#{a['name']}): default #{got.inspect}, manifest #{a['default'].inspect}") if norm(got) != norm(a["default"])
        end
    end

    # Method arguments: keyword names, positional counts and defaults.
    check_args = lambda do |obj_name, klass, m|
        names = ruby_names(m)
        where = "#{klass}##{names.first}"
        meth = begin
            klass.instance_method(names.first.to_sym)
        rescue NameError
            fail.call("#{where}: missing method")
            next
        end
        params = meth.parameters
        pos = params.count { |t, _| %i[req opt].include?(t) }
        want_pos = (m["args"] || []).count { |a| a["positional"] }
        fail.call("#{where}: #{pos} positional arguments, expected #{want_pos}") if pos != want_pos
        want_kw = (m["args"] || []).reject { |a| a["positional"] }.map { |a| a["name"] }
        compare.call("#{where} keywords", want_kw, keyword_params(meth))
        if m["filters"] && params.none? { |t, _| t == :keyrest }
            fail.call("#{where}: takes no filters (**filters)")
        end
        check_defaults.call(where, obj_name, klass, meth, m)
    end

    # ---- Client: instance methods, the forwarded Release operations, the constructor.
    client = objects["Client"]
    expected = []
    client["members"].each do |m|
        next unless ruby_member?(m)
        next if m["static"]
        expected.concat(ruby_names(m))
    end
    forwarded = objects["Release"]["members"].select { |m| m["forwarded_to_client"] && ruby_member?(m) }
    forwarded.each { |m| expected.concat(ruby_names(m)) }
    compare.call("OpenTideConstants (client)", expected.uniq, public_methods_of(OTC))

    open_member = client["members"].find { |m| m["name"] == "open" }
    opts = open_member["args"].map { |a| a["name"] }
    init = OTC.instance_method(:initialize)
    compare.call("OpenTideConstants.new options", opts, keyword_params(init))
    if OTC.respond_to?(:open)
        compare.call("OpenTideConstants.open options", [], OTC.method(:open).parameters.map(&:last).map(&:to_s) - %w[options block])
    else
        fail.call("OpenTideConstants.open is missing")
    end
    check_defaults.call("OpenTideConstants.new", "Client", OTC, init, open_member)

    # A forwarded operation on the client passes every argument to the Release
    # (whose signature is checked below), or has the Release's signature itself.
    forwarded.each do |m|
        name = ruby_names(m).first.to_sym
        next unless OTC.public_method_defined?(name)
        kinds = OTC.instance_method(name).parameters.map(&:first)
        next if kinds == %i[rest keyrest block]
        check_args.call("Release", OTC, m)
    end

    # ---- every other object: its public methods are exactly its members.
    class_for = {}
    (objects.keys - ["Client"]).each do |k|
        if OTC.const_defined?(k, false) && OTC.const_get(k, false).is_a?(Class)
            class_for[k] = OTC.const_get(k, false)
        else
            fail.call("no Ruby class for manifest object #{k}")
        end
    end
    class_for.each do |name, klass|
        members = objects[name]["members"].select { |m| ruby_member?(m) }
        compare.call(name, members.flat_map { |m| ruby_names(m) }.uniq, public_methods_of(klass))
        members.each { |m| check_args.call(name, klass, m) if m["kind"] == "method" }
    end
    client["members"].each { |m| check_args.call("Client", OTC, m) if m["kind"] == "method" && !m["static"] && ruby_member?(m) }

    # ---- filters: the keys the Release accepts.
    if OTC.const_defined?(:Release, false) && OTC::Release.const_defined?(:FILTER_KEYS, false)
        compare.call("filters (Release::FILTER_KEYS)", MANIFEST["filters"].map { |f| f["name"] }, OTC::Release::FILTER_KEYS.map(&:to_s))
    else
        fail.call("OpenTideConstants::Release::FILTER_KEYS is missing")
    end

    # ---- errors: classes, codes, detail fields.
    base = OTC.const_defined?(:Error, false) ? OTC::Error : nil
    if base.nil?
        fail.call("OpenTideConstants::Error is missing")
    elsif base.superclass != StandardError
        fail.call("OpenTideConstants::Error must be a direct subclass of StandardError")
    end
    base_methods = base ? base.public_instance_methods(true) : []
    MANIFEST["errors"].each do |e|
        next unless e["languages"].include?("ruby") && e["class"]
        klass = OTC.const_get(e["class"], false) if OTC.const_defined?(e["class"], false)
        unless klass.is_a?(Class)
            fail.call("error class OpenTideConstants::#{e['class']} is missing")
            next
        end
        fail.call("#{klass} must be a direct subclass of #{base}") unless base && klass.superclass == base
        if klass.const_defined?(:CODE, false)
            fail.call("#{klass}::CODE is #{klass::CODE.inspect}, expected #{e['code']}") unless klass::CODE == e["code"]
        else
            fail.call("#{klass}::CODE is missing")
        end
        code = begin
            klass.allocate.code
        rescue StandardError => ex
            "#{ex.class}: #{ex.message}"
        end
        fail.call("#{klass}#code is #{code.inspect}, not #{e['code']}") unless code == e["code"]
        # its fields: the public methods it adds to the base class (cause is Exception#cause)
        fields = (klass.public_instance_methods(true) - base_methods).map(&:to_s)
        want = e["fields"] - ["cause"]
        compare.call("#{klass} fields", want, fields)
    end
    ruby_classes = MANIFEST["errors"].select { |e| e["languages"].include?("ruby") && e["class"] }.map { |e| e["class"] }
    if base
        actual_errors = OTC.constants.map { |c| OTC.const_get(c) }
                           .select { |c| c.is_a?(Class) && c < base }.map { |c| c.name.split("::").last }
        compare.call("error classes", ruby_classes, actual_errors)
    end

    # ---- constants and the phase 2 names (must not exist yet).
    MANIFEST["constants"].each do |name, spec|
        next if name == "c_only"
        unless OTC.const_defined?(name, false)
            fail.call("constant #{name} is missing")
            next
        end
        fail.call("constant #{name} is #{OTC.const_get(name).inspect}, expected #{spec['value'].inspect}") unless OTC.const_get(name) == spec["value"]
    end
    public_classes = [OTC] + OTC.constants.map { |c| OTC.const_get(c) }.select { |c| c.is_a?(Class) }
    MANIFEST["reserved_phase2"]["operations"].each do |op|
        fail.call("phase 2 object #{op['object']} must not exist yet") if op["object"] != "Client" && OTC.const_defined?(op["object"], false)
        fail.call("phase 2 operation OpenTideConstants.#{op['name']} must not exist yet") if OTC.respond_to?(op["name"])
        public_classes.each do |klass|
            fail.call("phase 2 operation #{klass}##{op['name']} must not exist yet") if klass.public_method_defined?(op["name"])
        end
    end
    (MANIFEST["reserved_phase2"]["errors"] || []).each do |e|
        fail.call("phase 2 error class #{e['class']} must not exist yet") if OTC.const_defined?(e["class"], false)
    end

    # ---- enums: the values the gem knows.
    enums = OTC.const_defined?(:ENUMS, false) ? OTC::ENUMS : {}
    fail.call("OpenTideConstants::ENUMS is missing") unless OTC.const_defined?(:ENUMS, false)
    MANIFEST["enums"].each do |name, values|
        known = enums[name.to_sym]
        known ||= OTC.const_get(ENUM_CONSTANTS[name], false) if ENUM_CONSTANTS[name] && OTC.const_defined?(ENUM_CONSTANTS[name], false)
        if known.nil?
            fail.call("enum #{name}: no value list in the gem (OpenTideConstants::ENUMS, or a constant the check knows)") unless NO_RUBY_LIST.include?(name)
            next
        end
        compare.call("enum #{name}", values, known.map(&:to_s))
    end
    (enums.keys.map(&:to_s) - MANIFEST["enums"].keys).each { |n| fail.call("ENUMS has #{n}, which is not a manifest enum") }
    failures
rescue StandardError => e
    failures << "the check crashed: #{e.class}: #{e.message} (#{e.backtrace&.first})"
    failures
end

# ---------------------------------------------------------------- self-test

# Defines methods from Ruby source in klass (from a temp file, so that the
# defaults can be read), and returns the undo.
def patch_source(klass, names, source)
    own = ->(n) { klass.instance_methods(false).include?(n) || klass.private_instance_methods(false).include?(n) }
    saved = names.select { |n| own.call(n) }.to_h { |n| [n, klass.instance_method(n)] }
    file = Tempfile.new(["otc_check_api", ".rb"])
    file.write(source)
    file.close
    quietly { klass.class_eval(source, file.path, 1) }
    lambda do
        quietly do
            names.each { |n| klass.send(:remove_method, n) if own.call(n) }
            saved.each { |n, m| klass.send(:define_method, n, m) }
        end
        file.unlink
    end
end

# Runs the block with Ruby's warnings off (redefining initialize warns).
def quietly
    verbose = $VERBOSE
    $VERBOSE = nil
    yield
ensure
    $VERBOSE = verbose
end

def patch_const(owner, name, value)
    had = owner.const_defined?(name, false)
    old = owner.const_get(name, false) if had
    owner.send(:remove_const, name) if had
    owner.const_set(name, value)
    lambda do
        owner.send(:remove_const, name)
        owner.const_set(name, old) if had
    end
end

def remove_const(owner, name)
    old = owner.const_get(name, false)
    owner.send(:remove_const, name)
    -> { owner.const_set(name, old) }
end

MUTATIONS = [
    ["wrong-default (prune keep: 4)", -> { patch_source(OTC, [:prune], "def prune(keep: 4); []; end") },
     "OpenTideConstants#prune(keep): default 4"],
    ["wrong-option-default (mode: :stream)", lambda {
        init = OTC.instance_method(:initialize)
        real = defaults_of(OTC, init)
        params = init.parameters.select { |t, _| t == :key }.map { |_, n| "#{n}: #{n == :mode ? ':stream' : real[n.to_s].inspect}" }.join(", ")
        patch_source(OTC, [:initialize], "def initialize(#{params}); end")
    }, "OpenTideConstants.new(mode): default :stream"],
    ["forwarded-method-with-own-signature", -> { patch_source(OTC, [:station_by_alias], "def station_by_alias(system); end") },
     "OpenTideConstants#station_by_alias: 1 positional arguments, expected 2"],
    ["missing-method", lambda {
        old = OTC::Release.instance_method(:convention)
        OTC::Release.send(:remove_method, :convention)
        -> { OTC::Release.send(:define_method, :convention, old) }
    },
     "Release: missing convention"],
    ["missing-CODE", lambda {
        k = Class.new(OTC::Error) { attr_reader :removed }
        patch_const(OTC, :CacheError, k)
    }, "CacheError::CODE is missing"],
    ["error-extra-field", -> { patch_source(OTC::CacheError, [:path], "attr_reader :path") }, "CacheError fields: extra path"],
    ["error-missing-field", lambda {
        k = Class.new(OTC::Error) { const_set(:CODE, "cache") }
        patch_const(OTC, :CacheError, k)
    }, "CacheError fields: missing removed"],
    ["enum-without-list", -> { remove_const(OTC, :MODES) },
     "enum mode: no value list"],
    ["enum-extra-value", -> { patch_const(OTC, :ENUMS, OTC::ENUMS.merge(kind: %w[tide current tsunami])) }, "enum kind: extra tsunami"],
    ["unchecked-filter", -> { patch_const(OTC::Release, :FILTER_KEYS, %i[country type kind source]) },
     "filters (Release::FILTER_KEYS): missing source_type"],
    ["reserved-op-on-release", -> { patch_source(OTC::Release, [:heights], "def heights(station, from, to, step_s, datum); end") },
     "phase 2 operation OpenTideConstants::Release#heights"],
    ["reserved-astro", -> { patch_const(OTC, :Astro, Class.new) }, "phase 2 object Astro"],
    ["reserved-error-class", -> { patch_const(OTC, :UnsupportedConventionError, Class.new(OTC::Error) { const_set(:CODE, "unsupported_convention") }) },
     "phase 2 error class UnsupportedConventionError"],
    ["no-SUPPORTED_FORMAT_VERSION", -> { remove_const(OTC, :SUPPORTED_FORMAT_VERSION) }, "constant SUPPORTED_FORMAT_VERSION is missing"],
].freeze

def self_test
    base = run_checks
    out = []
    MUTATIONS.each do |name, apply, expect|
        undo = apply.call
        got = begin
            run_checks
        ensure
            undo.call
        end
        new = got - base
        out << "#{name}: not caught (wanted a problem with #{expect.inspect}; new problems #{new.inspect})" unless new.any? { |p| p.include?(expect) }
    end
    after = run_checks
    out << "a mutation was not undone: #{(after - base) + (base - after)}" if after != base
    out
end

exit_with_report = $PROGRAM_NAME == __FILE__
return unless exit_with_report # required by a harness: define the checks and the mutations only

failures = run_checks
failures.each { |f| warn "FAIL #{f}" }
if failures.empty?
    puts "API manifest check: OK (suite #{MANIFEST['suite_version']}, gem #{OTC::VERSION})"
else
    warn "API manifest check: #{failures.size} problem(s)"
end
rc = failures.empty? ? 0 : 1
unless ARGV.include?("--no-self-test")
    bad = self_test
    bad.each { |f| warn "SELF-TEST #{f}" }
    puts "self-test: #{MUTATIONS.size - bad.size} of #{MUTATIONS.size} mutations caught"
    rc = 1 unless bad.empty?
end
exit rc
