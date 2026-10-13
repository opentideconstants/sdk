require "json"
require "digest"
require "optparse"
require "pathname"

# Serialized compatibility only. Claims, hashes and source text cannot prove
# native execution. Independent VALUE must execute builds/fixtures for acceptance.
module NativeShape
    DIRECTORY = File.expand_path(__dir__)
    class Invalid < StandardError; end

    def self.read(path)
        JSON.parse(File.read(path))
    end

    def self.protocol
        read(File.join(DIRECTORY, "native-shape.json"))
    end

    def self.require_true(condition, message)
        raise Invalid, message unless condition
    end

    def self.text(value, label)
        require_true(value.is_a?(String) && !value.strip.empty?, "Missing #{label}")
        require_true(!value.match?(/UNRESOLVED|pending|TBD|placeholder/i), "Unresolved #{label}")
    end

    def self.concrete(value, label)
        text(value, label)
        require_true(!value.match?(/\bAny\b|\bany\b|\bobject\b|\bdict\b|\bunknown\b|void\s*\*/), "Generic #{label}: #{value}")
    end

    def self.file_pin(root, source, label)
        require_true(source.is_a?(Hash), "Missing #{label} source")
        relative = source.fetch("path")
        require_true(relative.is_a?(String) && !Pathname.new(relative).absolute?, "#{label} path must be candidate relative")
        path = File.realpath(File.join(root, relative))
        require_true(path.start_with?(File.realpath(root) + File::SEPARATOR), "#{label} escapes candidate root")
        require_true(Digest::SHA256.file(path).hexdigest == source.fetch("sha256"), "Stale #{label} hash: #{relative}")
        path
    rescue Errno::ENOENT => error
        raise Invalid, "Missing #{label} file: #{error.message}"
    end

    def self.verify_authority(foundation_path, p)
        require_true(Digest::SHA256.file(foundation_path).hexdigest == p.fetch("foundation_sha256"), "Wrong foundation hash")
        receipt_path = File.join(File.dirname(foundation_path), "receipt.json")
        require_true(Digest::SHA256.file(receipt_path).hexdigest == p.fetch("accepted_receipt_sha256"), "Wrong accepted P0 receipt seal")
        receipt = read(receipt_path)
        f = read(foundation_path)
        require_true(receipt.fetch("p0_accepted") && receipt.fetch("s0_unlocked") && f.fetch("p0_accepted") && f.fetch("s0_unlocked"), "P0 not accepted")
        require_true(f.fetch("user_acceptance_evidence").fetch("withdrawn_exclusive_approval_request"), "Missing inclusive acceptance")
        f.fetch("installed_authorities").each do |pin|
            name = File.basename(pin.fetch("path"))
            require_true(pin.fetch("sha256") == p.fetch("authority_sha256").fetch(name), "Wrong authority #{name}")
            require_true(Digest::SHA256.file(pin.fetch("path")).hexdigest == pin.fetch("sha256"), "Stale authority #{name}")
        end
        %w[inclusive reused_consumer_semantic final_consumer_binding].each do |role|
            pin = f.fetch("review_evidence").fetch(role)
            require_true(Digest::SHA256.file(pin.fetch("path")).hexdigest == pin.fetch("sha256"), "Stale review #{role}")
        end
        f.fetch("publication_evidence").values.select { |value| value.is_a?(Hash) && value.key?("sha256") }.each do |pin|
            require_true(Digest::SHA256.file(pin.fetch("path")).hexdigest == pin.fetch("sha256"), "Stale publication #{pin.fetch('path')}")
        end
        { "runtime" => "runtime_selectors_preparation", "call_actions" => "ordered_call_actions_preparation", "workflow" => "workflow_procedures", "concepts" => "finite_selector_sources_preparation" }.each do |key, field|
            require_true(p.fetch(key) == f.fetch(field), "Protocol differs from foundation #{field}")
        end
        require_true(p.fetch("b04") == f.fetch("b04_binding_contract"), "B04 differs from inclusive foundation")
        catalog_pin = f.fetch("installed_authorities").find { |pin| pin.fetch("path").end_with?("behavior-catalog.json") }
        catalog = read(catalog_pin.fetch("path"))
        corpus = read(File.join(DIRECTORY, "shape-values.json"))
        require_true(p.fetch("type_definitions") == catalog.fetch("concept_type_definitions"), "Changed type/selector authority")
        require_true(corpus.fetch("concepts") == p.fetch("concepts") && corpus.fetch("type_definitions") == p.fetch("type_definitions") && corpus.fetch("b04_presence") == p.fetch("b04").fetch("input_presence"), "Changed corpus authority")
        domain(corpus.fetch("members"), catalog.fetch("members").map { |member| member.fetch("id") }, "id", "member corpus")
        corpus.fetch("members").each do |member|
            actual = catalog.fetch("members").find { |entry| entry.fetch("id") == member.fetch("id") }
            require_true(member.fetch("contract") == actual.fetch("canonical_contract"), "Changed member corpus contract")
        end
    end

    def self.domain(rows, ids, key, label)
        require_true(rows.is_a?(Array), "Missing #{label}")
        actual = rows.map { |r| r.fetch(key) }
        require_true(actual.sort == ids.sort && actual.uniq.length == actual.length, "Wrong #{label} domain: missing/duplicate/extra #{key}")
    end

    def self.verify_projection(candidate, p, root, profile)
        require_true(p.fetch("profiles").include?(profile), "Unknown profile #{profile}")
        require_true(candidate.fetch("protocol_version") == 1 && candidate.fetch("native_profile") == profile, "Wrong projection profile/version")
        require_true(candidate.fetch("foundation_sha256") == p.fetch("foundation_sha256"), "Stale projection foundation")
        require_true(candidate.fetch("authority_sha256") == p.fetch("authority_sha256"), "Stale projection authorities")
        domain(candidate.fetch("runtime"), p.fetch("runtime").map { |r| r.fetch("id") }, "id", "runtime")
        require_true(candidate.fetch("workflow") == p.fetch("workflow"), "Workflow must stay separate/exact")
        domain(candidate.fetch("types"), p.fetch("concepts").map { |c| c.fetch("name") }, "concept_ref", "concept types")
        types = candidate.fetch("types").to_h { |type| [type.fetch("concept_ref"), type] }
        candidate.fetch("types").each do |type|
            canonical = p.fetch("concepts").find { |c| c.fetch("name") == type.fetch("concept_ref") }
            require_true(type.fetch("shape") == canonical.fetch("shape"), "Changed logical model/union #{type.fetch('concept_ref')}")
            concrete(type.fetch("native_type"), "native model")
            concrete(type.fetch("declaration"), "model declaration")
            text(type.fetch("ownership"), "model ownership")
            text(type.fetch("cleanup"), "model cleanup")
        end
        candidate.fetch("runtime").each do |row|
            canonical = p.fetch("runtime").find { |r| r.fetch("id") == row.fetch("id") }
            canonical.each { |key, value| require_true(row.fetch(key) == value, "Changed canonical row #{row.fetch('id')}.#{key}") }
            require_true(row.fetch("applicable") == true, "Unapproved profile exclusion #{row.fetch('id')}; applicable private shape must be constructed, native capability refusal is an observation")
            declaration = row.fetch("declaration")
            %w[symbol signature async lifetime].each { |key| text(declaration.fetch(key), "#{row.fetch('id')} #{key}") }
            file_pin(root, declaration.fetch("source"), "declaration")
            require_true(%w[reused_callable private_unimplemented_refusal].include?(declaration.fetch("status")), "Unfinished declaration #{row.fetch('id')}")
            if declaration.fetch("status") == "private_unimplemented_refusal"
                require_true(declaration.fetch("visibility") == "private", "Stub must be private")
                text(declaration.fetch("refusal"), "private refusal")
            end
            parameters = declaration.fetch("parameters")
            domain(parameters, row.fetch("inputs").map { |i| i.fetch("name") }, "canonical_name", "#{row.fetch('id')} inputs")
            parameters.each do |parameter|
                input = row.fetch("inputs").find { |i| i.fetch("name") == parameter.fetch("canonical_name") }
                require_true(parameter.fetch("concept_ref") == input.fetch("concept_ref"), "Changed parameter concept")
                require_true(parameter.fetch("native_type") == types.fetch(input.fetch("concept_ref")).fetch("native_type"), "Incompatible input type #{row.fetch('id')}:#{input.fetch('name')}")
                %w[projection ownership].each { |key| text(parameter.fetch(key), "parameter #{key}") }
            end
            result = declaration.fetch("result")
            require_true(result.fetch("canonical_name") == row.fetch("output").fetch("name") && result.fetch("concept_ref") == row.fetch("output").fetch("concept_ref"), "Changed result binding")
            require_true(result.fetch("native_type") == types.fetch(result.fetch("concept_ref")).fetch("native_type"), "Incompatible result type")
            %w[ownership cleanup].each { |key| text(result.fetch(key), "result #{key}") }
        end
        domain(candidate.fetch("call_actions"), p.fetch("call_actions").map { |e| e.fetch("action").fetch("action_id") }, "action_id", "call actions")
        candidate.fetch("call_actions").each do |edge|
            canonical = p.fetch("call_actions").find { |e| e.fetch("action").fetch("action_id") == edge.fetch("action_id") }
            canonical.each { |key, value| require_true(edge.fetch(key) == value, "Changed action #{edge.fetch('action_id')}.#{key}") }
            call = canonical.fetch("action").fetch("call")
            callee = candidate.fetch("runtime").find { |r| r.fetch("name") == call.fetch("callee") }
            require_true(callee && edge.fetch("callee_id") == callee.fetch("id"), "Wrong callee")
            domain(edge.fetch("arguments"), call.fetch("arguments").keys, "canonical_name", "edge arguments")
            edge.fetch("arguments").each do |argument|
                name = argument.fetch("canonical_name")
                concept = call.fetch("argument_concepts").fetch(name)
                require_true(argument.fetch("concept_ref") == concept && argument.fetch("native_type") == types.fetch(concept).fetch("native_type"), "Incompatible callee input type #{edge.fetch('action_id')}:#{name}")
                text(argument.fetch("expression"), "native argument expression")
                text(argument.fetch("ownership"), "edge argument owner")
            end
            require_true(edge.fetch("result_type") == callee.fetch("declaration").fetch("result").fetch("native_type"), "Incompatible edge result type")
            %w[owner cleanup].each { |key| text(edge.fetch(key), "edge #{key}") }
        end
    rescue KeyError => error
        raise Invalid, "Missing projection obligation: #{error.message}"
    end

    # Deliberately small evaluator for this owned schema's explicit vocabulary.
    def self.schema(value, rule, definitions, path = "$")
        return schema(value, definitions.fetch(rule.fetch("$ref").split("/").last), definitions, path) if rule.key?("$ref")
        require_true(value == rule.fetch("const"), "Schema const #{path}") if rule.key?("const")
        require_true(rule.fetch("enum").include?(value), "Schema enum #{path}") if rule.key?("enum")
        if rule.key?("type")
            matches = case rule.fetch("type")
            when "object" then value.is_a?(Hash)
            when "array" then value.is_a?(Array)
            when "string" then value.is_a?(String)
            when "integer" then value.is_a?(Integer)
            when "boolean" then value == true || value == false
            else false
            end
            require_true(matches, "Schema type #{path}")
        end
        require_true(value.length >= rule.fetch("minLength"), "Schema empty #{path}") if rule.key?("minLength")
        require_true(value.match?(Regexp.new(rule.fetch("pattern"))), "Schema pattern #{path}") if rule.key?("pattern")
        if value.is_a?(Hash) && rule.key?("properties")
            rule.fetch("required", []).each { |key| require_true(value.key?(key), "Schema required #{path}.#{key}") }
            value.each do |key, child|
                if rule.fetch("properties").key?(key)
                    schema(child, rule.fetch("properties").fetch(key), definitions, "#{path}.#{key}")
                elsif rule["additionalProperties"] == false
                    raise Invalid, "Schema extra #{path}.#{key}"
                end
            end
        elsif value.is_a?(Hash) && rule["additionalProperties"].is_a?(Hash)
            value.each { |key, child| schema(child, rule.fetch("additionalProperties"), definitions, "#{path}.#{key}") }
        end
        value.each_with_index { |child, index| schema(child, rule.fetch("items"), definitions, "#{path}[#{index}]") } if value.is_a?(Array) && rule.key?("items")
    end

    def self.public_return_selector?(shape, definitions, seen = [])
        if shape.key?("type_ref")
            name = shape.fetch("type_ref")
            return false if seen.include?(name)
            return public_return_selector?(definitions.fetch(name), definitions, seen + [name])
        end
        return true if shape["kind"] == "member_result_selector"
        return true if shape["kind"] == "selected_member_contract" && shape.fetch("selector", "").include?("returns")
        return true if shape["collection"] == "members" && shape.fetch("path", []).include?("returns")
        shape.values.any? do |value|
            if value.is_a?(Hash)
                public_return_selector?(value, definitions, seen)
            elsif value.is_a?(Array)
                value.any? { |item| item.is_a?(Hash) && public_return_selector?(item, definitions, seen) }
            else
                false
            end
        end
    end

    # Check the existing logical producer value form, not native source syntax.
    def self.internal_value_form?(value, shape, definitions)
        return true if value.nil? && shape["nullable"] == true
        return internal_value_form?(value, definitions.fetch(shape.fetch("type_ref")), definitions) if shape.key?("type_ref")
        case shape["kind"]
        when "record"
            return false unless value.is_a?(Hash)
            fields = shape.fetch("fields")
            return false if shape["additional_fields"] == false && (value.keys - fields.keys).any?
            fields.all? { |name, field| (!value.key?(name) && field["required"] == false) || (value.key?(name) && internal_value_form?(value.fetch(name), field, definitions)) }
        when "sequence"
            value.is_a?(Array) && value.all? { |item| internal_value_form?(item, shape.fetch("items"), definitions) }
        when "union"
            shape.fetch("variants").any? { |variant| internal_value_form?(value, variant, definitions) }
        when "enum"
            shape.fetch("values").include?(value)
        when "primitive"
            case shape.fetch("type")
            when "string", "native_path" then value.is_a?(String)
            when "boolean" then value == true || value == false
            when "integer" then value.is_a?(Integer)
            when "finite_binary64" then value.is_a?(Numeric) && value.to_f.finite?
            when "byte_sequence"
                value.is_a?(String) || (value.is_a?(Array) && value.all? { |byte| byte.is_a?(Integer) && byte.between?(0, 255) }) || (value.is_a?(Hash) && value.keys == (0...value.length).map(&:to_s) && value.values.all? { |byte| byte.is_a?(Integer) && byte.between?(0, 255) })
            else false
            end
        when "json_value"
            value.nil? || value == true || value == false || value.is_a?(String) || (value.is_a?(Numeric) && value.to_f.finite?) || (value.is_a?(Array) && value.all? { |item| internal_value_form?(item, shape, definitions) }) || (value.is_a?(Hash) && value.keys.all? { |key| key.is_a?(String) } && value.values.all? { |item| internal_value_form?(item, shape, definitions) })
        when "opaque_native_error"
            value.is_a?(Hash) || value.is_a?(String)
        when "map", "catalog_schema_selector", "catalog_selector", "contract_selector", "selected_argument_record", "selected_member_contract", "selected_model_contract", "selected_model_field_contracts", "json_projection"
            value.is_a?(Hash)
        else
            false
        end
    end

    def self.presence(observation, root, profile, callee = nil)
        corpus = read(File.join(DIRECTORY, "shape-values.json"))
        result = observation.fetch("canonical_result")
        error = observation.fetch("canonical_error")
        [result, error].each do |channel|
            selectors = %w[member_id concept_ref].select { |key| channel.key?(key) }
            require_true(selectors.length == 1, "Channel requires exactly one member_id or concept_ref")
            text(channel.fetch(selectors.first), "channel selector")
        end
        if result.key?("concept_ref") || error.key?("concept_ref")
            concept = corpus.fetch("concepts").find { |entry| entry.fetch("name") == result["concept_ref"] }
            require_true(concept && error["concept_ref"] == "canonical_error", "Unknown or wrong internal result/error concept")
            require_true(callee && callee.fetch("output").fetch("concept_ref") == concept.fetch("name") && callee.fetch("declaration").fetch("result").fetch("concept_ref") == concept.fetch("name"), "Internal concept does not match actual callee result")
            require_true(observation.fetch("expected_result_type") == callee.fetch("declaration").fetch("result").fetch("native_type"), "Internal result native type differs")
            definitions = corpus.fetch("type_definitions").merge(corpus.fetch("concepts").to_h { |entry| [entry.fetch("name"), entry.fetch("shape")] })
            require_true(!public_return_selector?(concept.fetch("shape"), definitions), "Public selected-member output requires member_id")
            rp = result.fetch("presence")
            ep = error.fetch("presence")
            require_true(result.key?("value") == (rp == "present_value") && error.key?("value") == (ep == "present_error"), "Internal channel presence/value mismatch")
            if observation.fetch("classification") == "private_unimplemented_refusal"
                require_true(rp == "absent" && ep == "absent", "Fabricated successful stub output/canonical error")
                text(observation.fetch("native_refusal"), "observed private native refusal")
            elsif rp == "present_value" && ep == "absent"
                require_true(internal_value_form?(result.fetch("value"), concept.fetch("shape"), definitions), "Internal returned value incompatible with declared producer form")
            elsif rp == "absent" && ep == "present_error"
                require_true(internal_value_form?(error.fetch("value"), definitions.fetch("canonical_error"), definitions), "Internal failure value incompatible with canonical_error")
            else
                raise Invalid, "Unsupported internal result/error presence combination"
            end
            return
        end
        require_true(result.fetch("member_id") == error.fetch("member_id"), "Presence channels select different members")
        member = corpus.fetch("members").find { |m| m.fetch("id") == result.fetch("member_id") }
        require_true(member, "Unknown selected member")
        rp = result.fetch("presence")
        ep = error.fetch("presence")
        require_true(%w[absent present_value successful_no_value].include?(rp) && %w[absent present_error].include?(ep), "Wrong channel states")
        require_true(result.key?("value") == (rp == "present_value"), "Result presence/value mismatch")
        require_true(error.key?("value") == (ep == "present_error"), "Error presence/value mismatch")
        if observation.fetch("classification") == "private_unimplemented_refusal"
            require_true(rp == "absent" && ep == "absent", "Fabricated successful stub output/canonical error")
            text(observation.fetch("native_refusal"), "observed private native refusal")
            return
        end
        require_true(!error["value"].nil?, "Present error must be non-null") if ep == "present_error"
        require_true(rp != "absent" || ep != "absent", "Both channels absent without declared no-value")
        if rp == "successful_no_value"
            require_true(member.fetch("result_variants").include?("successful_no_value"), "Undeclared successful no-value")
        elsif rp == "present_value" && result.fetch("value").nil?
            require_true(member.fetch("result_variants").include?("present_null"), "Undeclared nullable result")
        end
        if ep == "present_error" && rp != "absent"
            branch = corpus.fetch("qualified_both_channels").find { |b| b.fetch("id") == result["qualified_branch"] && b.fetch("id") == error["qualified_branch"] && b.fetch("native_profile") == profile && b.fetch("member_id") == member.fetch("id") }
            require_true(branch, "Unqualified both-channel result/error")
            require_true(error.fetch("value").is_a?(Hash) && error.fetch("value")["code"] == branch.fetch("error_code"), "Wrong qualified branch error")
            file_pin(root, branch.fetch("source"), "qualified B04 branch")
        end
    end

    def self.verify_observations(observations, projection, projection_path, p, root, profile)
        definitions = read(File.join(DIRECTORY, "shape-report.schema.json")).fetch("$defs")
        schema(observations, definitions.fetch("observations"), definitions)
        require_true(observations.fetch("native_profile") == profile, "Missing selected profile observations")
        require_true(observations.fetch("foundation_sha256") == p.fetch("foundation_sha256"), "Stale observation foundation")
        require_true(observations.fetch("native_projection_sha256") == Digest::SHA256.file(projection_path).hexdigest, "Stale observation projection")
        return false if observations.fetch("kind") == "structural_control"
        gate = observations.fetch("build_gate")
        schema(gate, definitions.fetch("observations").fetch("properties").fetch("build_gate"), definitions)
        file_pin(root, gate.fetch("evidence"), "native build gate")
        domain(observations.fetch("runtime"), projection.fetch("runtime").map { |r| r.fetch("id") }, "id", "runtime observations")
        domain(observations.fetch("call_actions"), projection.fetch("call_actions").map { |e| e.fetch("action_id") }, "id", "actual edge observations")
        projection.fetch("types").each do |type|
            path = file_pin(root, type.fetch("source"), "native type declaration")
            require_true(File.read(path).gsub(/\s+/, " ").include?(type.fetch("declaration").gsub(/\s+/, " ")), "Native type declaration not present in candidate source")
        end
        (observations.fetch("runtime") + observations.fetch("call_actions")).each do |observation|
            require_true(observation.fetch("native_profile") == profile, "Wrong native observation profile")
            row = projection.fetch("runtime").find { |r| r.fetch("id") == observation.fetch("id") }
            edge = projection.fetch("call_actions").find { |e| e.fetch("action_id") == observation.fetch("id") }
            callee = row || projection.fetch("runtime").find { |r| r.fetch("id") == edge.fetch("callee_id") }
            declaration = callee.fetch("declaration")
            declaration_path = file_pin(root, declaration.fetch("source"), "actual declaration")
            require_true(File.read(declaration_path).gsub(/\s+/, " ").include?(declaration.fetch("signature").gsub(/\s+/, " ")), "Declared signature not present in native candidate source")
            require_true(observation.fetch("declared_signature") == declaration.fetch("signature") && observation.fetch("native_entry") == declaration.fetch("symbol"), "Actual callee signature/entry differs")
            require_true(observation.fetch("source") == declaration.fetch("source"), "Actual callee source differs")
            %w[source fixture invocation_evidence].each { |key| file_pin(root, observation.fetch(key), key) }
            build = observation.fetch("build")
            file_pin(root, build, "build")
            require_true(!build.fetch("source_hashes").empty?, "Missing build source closure")
            build.fetch("source_hashes").each { |source| file_pin(root, source, "build source") }
            require_true(build.fetch("source_hashes").include?(observation.fetch("source")), "Build does not bind invoked source")
            require_true(observation.fetch("expected_result_type") == declaration.fetch("result").fetch("native_type"), "Actual result type differs")
            expected = edge ? edge.fetch("arguments") : declaration.fetch("parameters")
            domain(observation.fetch("arguments"), expected.map { |a| a.fetch("canonical_name") }, "canonical_name", "actual arguments")
            observation.fetch("arguments").each do |argument|
                binding = expected.find { |a| a.fetch("canonical_name") == argument.fetch("canonical_name") }
                %w[concept_ref native_type ownership].each { |key| require_true(argument.fetch(key) == binding.fetch(key), "Actual argument #{key} differs") }
                require_true(argument.fetch("expression") == binding.fetch(edge ? "expression" : "projection"), "Actual argument projection differs")
            end
            require_true(observation.fetch("cleanup") == (edge ? edge.fetch("cleanup") : declaration.fetch("result").fetch("cleanup")), "Actual cleanup differs")
            text(observation.fetch("owner"), "actual owner")
            require_true(observation.fetch("classification") != "construction_failure", "Native construction failure")
            if observation.fetch("classification") == "approved_profile_unsupported"
                selection = observation.fetch("capability_selection")
                member = read(File.join(DIRECTORY, "shape-values.json")).fetch("members").find { |m| m.fetch("id") == selection.fetch("member_id") }
                require_true(member && member.fetch("selector") == selection.fetch("selector"), "Unknown capability selector")
                contract = member.fetch("contract")
                require_true(contract.fetch("note", "").include?(selection.fetch("contract_text")), "Unapproved capability contract")
                require_true(selection.fetch("contract_text").length >= 20, "Capability text must identify exact native limitation")
                require_true((profile == "c" && selection.fetch("error_code") == "not_built" && contract.fetch("errors", []).include?("not_built") && selection.fetch("contract_text").match?(/C.*without|optional/i)) || (profile == "typescript_browser" && selection.fetch("error_code") == "unsupported" && selection.fetch("contract_text").match?(/browser.*unsupported|unsupported.*browser/i)), "Unapproved profile unsupported observation")
                require_true(observation.fetch("canonical_error").fetch("value").fetch("code") == selection.fetch("error_code"), "Unsupported observation error differs")
            else
                require_true(observation.fetch("classification") == declaration.fetch("status"), "Declared callable/refusal status differs")
            end
            if observation.fetch("classification") == "private_unimplemented_refusal"
                require_true(observation.fetch("native_refusal") == declaration.fetch("refusal"), "Private native refusal differs")
            end
            require_true(observation.fetch("runtime_environment") == "browser", "Browser fixtures must actually invoke browser entry") if profile == "typescript_browser"
            if profile == "python"
                imported = File.realpath(observation.fetch("imported_module"))
                require_true(imported.start_with?(File.realpath(File.join(root, "python/src")) + File::SEPARATOR), "Python imported legacy/non-candidate module")
            end
            presence(observation, root, profile, callee)
        end
        true
    rescue KeyError => error
        raise Invalid, "Missing observation obligation: #{error.message}"
    end
end

if $PROGRAM_NAME == __FILE__
    options = {}
    parser = OptionParser.new do |args|
        %w[root foundation native-projection observations profile report].each { |name| args.on("--#{name} VALUE") { |value| options[name] = value } }
    end
    report = { "protocol_version" => 1, "native_profile" => "python", "status" => "REJECTED", "protocol_valid" => false, "shape_accepted" => false, "behavior_accepted" => false, "construction_incomplete" => [], "errors" => [], "counts" => { "runtime" => 0, "call_actions" => 0 }, "input_sha256" => {} }
    exit_code = 1
    begin
        parser.parse!
        NativeShape.require_true(ARGV.empty? && options.keys.sort == %w[foundation native-projection observations profile report root].sort, "Require exactly --root --foundation --native-projection --observations --profile --report")
        %w[root foundation native-projection observations report].each { |key| NativeShape.require_true(Pathname.new(options.fetch(key)).absolute?, "--#{key} must be absolute") }
        p = NativeShape.protocol
        NativeShape.require_true(p.fetch("profiles").include?(options.fetch("profile")), "Unknown native profile")
        report["native_profile"] = options.fetch("profile")
        NativeShape.verify_authority(options.fetch("foundation"), p)
        projection = NativeShape.read(options.fetch("native-projection"))
        NativeShape.verify_projection(projection, p, options.fetch("root"), options.fetch("profile"))
        observations = NativeShape.read(options.fetch("observations"))
        native_metadata_valid = NativeShape.verify_observations(observations, projection, options.fetch("native-projection"), p, options.fetch("root"), options.fetch("profile"))
        report["status"] = native_metadata_valid ? "EXECUTION_UNVERIFIED" : "STRUCTURAL_CONTROL_VALID"
        report["protocol_valid"] = true
        report["shape_accepted"] = false
        report["construction_incomplete"] = projection.fetch("runtime").select { |r| r.fetch("declaration").fetch("status") == "private_unimplemented_refusal" }.map { |r| r.fetch("id") }
        report["counts"] = { "runtime" => projection.fetch("runtime").length, "call_actions" => projection.fetch("call_actions").length }
        %w[foundation native-projection observations].each { |key| report.fetch("input_sha256")[key] = Digest::SHA256.file(options.fetch(key)).hexdigest }
        exit_code = 0
    rescue NativeShape::Invalid, KeyError, JSON::ParserError, Errno::ENOENT, OptionParser::ParseError => error
        report.fetch("errors") << error.message
        warn "REJECTED: #{error.message}"
    end
    if options["report"] && Pathname.new(options.fetch("report")).absolute?
        File.write(options.fetch("report"), JSON.pretty_generate(report) + "\n")
    end
    puts "#{report.fetch('status')}: shape_accepted=#{report.fetch('shape_accepted')}; behavior_accepted=false"
    exit exit_code
end
