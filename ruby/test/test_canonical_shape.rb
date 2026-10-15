require "minitest/autorun"
require "json"
require "digest"
require "fileutils"
require "logger"
require "time"
require "weakref"
require "rbs"
require "rbs/test"
require "opentideconstants"
require "opentideconstants/canonical"
require_relative "support"

class CanonicalShapeTest < Minitest::Test
    include TestSupport
    ROOT = File.expand_path("../..", __dir__)
    T = OpenTideConstants.const_get(:CanonicalTypes, false)
    C = OpenTideConstants.const_get(:Canonical, false)
    PROTOCOL = JSON.parse(File.read(File.join(ROOT, "conformance/canonical/native-shape.json")))
    LEDGER_PATH = File.join(ROOT, "conformance/canonical/native-ruby-shape.json")
    LEDGER = JSON.parse(File.read(LEDGER_PATH)) if File.file?(LEDGER_PATH)
    EVENTS = []
    PREDICT = OpenTideConstants.const_get(:Predict, false)
    M1 = %w[B01 B02 B03 B04 B07 B08.raw B24 B39 B41 B42 B43.roots B44.roots].freeze
    M2 = %w[B05 B06 B08 B08.origin B15 B16 B20 B25 B26 B27].freeze

    def setup
        @subject = C.new
        loader = RBS::EnvironmentLoader.new
        loader.add(path: Pathname.new(File.join(ROOT, "ruby/sig")))
        @environment = RBS::Environment.from_loader(loader).resolve_type_names
        @builder = RBS::DefinitionBuilder.new(env: @environment)
        @checker = RBS::Test::TypeCheck.new(self_class: C, builder: @builder, sample_size: nil, unchecked_classes: [])
    end

    def inert(klass)
        klass.allocate.freeze
    end

    def describe(value, seen = {})
        return { "native_reference" => value.class.name } if seen[value.object_id]
        seen[value.object_id] = true unless value.nil? || value == true || value == false || value.is_a?(Numeric) || value.is_a?(String)
        case value
        when nil, true, false, String, Integer, Float then value
        when Array then value.map { |item| describe(item, seen) }
        when Hash then value.transform_values { |item| describe(item, seen) }
        when Time then { "native_class" => "Time", "utc_seconds" => value.to_f }
        when Exception then { "native_class" => value.class.name, "message" => value.message }
        else
            fields = value.instance_variables.to_h do |variable|
                [variable.to_s.delete_prefix("@"), describe(value.instance_variable_get(variable), seen)]
            end
            { "native_class" => value.class.name, "construction_fields" => fields, "frozen" => value.frozen? }
        end
    end

    def open_arguments(**overrides)
        values = { member_id: "Client.open", release: :latest, file: nil, cache_dir: nil, offline: false, mode: :eager, base_url: nil, timeout: nil, proxy: nil, ca_file: nil, user_agent: nil, on_network_error: :use_cache, auto_update: false, update_interval: 86_400, logger: nil, verify_on_open: false, commercial_only: false, commercial_basis: "strict", historical_offsets_policy: "fallback" }
        T::ArgsClientOpen.new(**values.merge(overrides))
    end

    def prediction_model(context, release, datum: nil, current_request: T::ABSENT)
        fields = { station: context.station, release_view: release, constant_set: context.constants, convention: context.constants.convention, astro_table: context.table.instance_variable_get(:@raw), required_constituents: context.constants.raw.fetch("constituents", []), reference_bin: context.reference_bin, mean_term: context.total.mean, datum_source: context.constants.raw["datum"] }
        fields[:native_context] = context if T::PredictionModel.instance_method(:initialize).parameters.any? { |_kind, name| name == :native_context }
        fields.merge!(selection_context: context, prepared_datum: datum, prepared_current_request: current_request)
        T::PredictionModel.new(**fields)
    end

    def native_arguments
        return @native_leafs if @native_leafs
        good_file = File.join(ROOT, "conformance/fixtures/good/OTC_20991231.2.json")
        client = OpenTideConstants.new(file: good_file)
        release = client.release
        station = release.require_station("OTC-T-0001")
        predict_file = File.join(ROOT, "conformance/fixtures/predict/OTC_20991231.7.json")
        predict = OpenTideConstants.new(file: predict_file)
        context = PREDICT.context(predict.release, "OTC-P-0001", "water_level", nil)
        vector_doc = JSON.parse(File.read(File.join(ROOT, "conformance/vectors/1.0/vectors-release.json")))
        vectors = OpenTideConstants::Reader.eager_from_doc(vector_doc, files: [], checks: {})
        vector_context = PREDICT.context(vectors, "OTC-V-NOAA-1820000", "water_level", nil)

        bad_open = open_arguments(file: good_file, offline: true)
        native_error = begin
            OpenTideConstants.new(file: good_file, offline: true)
        rescue OpenTideConstants::InvalidArgumentError => error
            error
        end
        raise "Missing genuine invalid_argument control" unless native_error
        failure = T::CanonicalError.new(code: native_error.code, structured_fields: { "message" => native_error.message }, cause: native_error)
        contracts = T::FieldContracts.new(model_type: "Station", fields: [])
        if contracts.respond_to?(:native_context)
            contracts = T::FieldContracts.new(model_type: "Station", fields: [], native_context: station)
        end
        offset = 0
        span = nil
        source_row = nil
        File.open(File.join(ROOT, "conformance/fixtures/good/OTC_20991231.2.jsonl"), "rb") do |file|
            file.each_line do |line|
                body = line.delete_suffix("\n").delete_suffix("\r")
                raw = JSON.parse(body)
                if raw["station_id"] == station.station_id
                    source_row = raw
                    span = T::SourceByteSpan.new(offset_bytes: offset, length_bytes: body.bytesize)
                    break
                end
                offset += line.bytesize
            end
        end
        raise "Actual station JSONL span absent" unless source_row && span
        projection = T::ProjectionContract.new(
            scalar_types: "Exact original canonical field table attached per member; known wrong type is invalid_release, absent nullable is null, missing arrays use each attached contract default. Raw fields preserve source JSON without computed fields.",
            models: "Model IDs refer to B07, source/ownership objects also B08, historical fields B36, prediction/local/datum results B48. These are value projection behaviors, not an assertion that every getter has an independent algorithm.",
            subordinate_offsets: "Complete source object, including all unknown nested fields, represented by tolerant cache-specific definitions derived from accepted schema33a760ad. Known primitive types, required historical fields, source binding conditions and raw values remain unchanged.",
            scope: "25 scenario families enumerate required shared branches. They are not 25 executed passes or exhaustive binary-branch verification. Each family expands to its incorporated original case table and required additional guard-reaching witnesses.",
            fallback: "Complete actual fallback object, including unknown nested fields. String reasons remain source strings in cache/raw and become typed other when unknown. Cache-source comparison includes every preserved field, not only current known keys."
        )
        window_args = T::ArgsReleaseExtremes.new(member_id: "Release.extremes", station: context.station, start: Time.utc(2010, 3, 1), stop: Time.utc(2010, 3, 1), datum: nil, set_id: nil, offset_id: nil)
        local = T::ArgsHeightSeriesToLocal.new(member_id: "HeightSeries.to_local", tz: "station")
        vector = JSON.parse(File.read(File.join(ROOT, "conformance/vectors/1.0/vectors.json"))).fetch("vectors").find { |entry| entry.fetch("id") == "OTC-V-NOAA-1820000/heights" }
        instants = vector.fetch("args").fetch("times").first(3).map { |text| Time.iso8601(text).to_i }
        leafs = {
            "B01" => [:validate_operation_arguments, { operation: "open", arguments: bad_open, member_contract: bad_open }],
            "B02" => [:resolve_effective_options, { explicit_options: open_arguments, environment: { "OPENTIDECONSTANTS_OFFLINE" => "On" }, platform_defaults: open_arguments }],
            "B03" => [:select_canonical_error, { operation: "open", ordered_failures: [failure], cause: native_error }],
            "B04" => [:translate_native_binding, { canonical_result: T::SelectedResult0.new(member_id: "Client.open", value: client), canonical_error: T::ABSENT, native_profile: "ruby" }],
            "B07" => [:materialize_typed_model, { raw_fields: station.raw, field_contract: contracts, origin: release, model_type: "Station" }],
            "B08.raw" => [:retain_raw_source_record, { source_record: station.raw, native_profile: "ruby" }],
            "B24" => [:project_station_index, { station_source_row: source_row, source_byte_span: span, projection_contract: projection }],
            "B39" => [:parse_prediction_window, { time_inputs: window_args, window_inputs: window_args, step: nil, local_time_profile: local }],
            "B41" => [:evaluate_astronomy, { selected_prediction_model: prediction_model(context, predict.release), utc_instant: Time.utc(2015, 6, 1, 12, 34, 56).to_i }],
            "B42" => [:evaluate_harmonic_height, { selected_prediction_model: prediction_model(vector_context, vectors), prediction_instants: instants, requested_datum: "mean_level" }],
            "B43.roots" => [:find_unrounded_tide_events, { selected_prediction_model: prediction_model(vector_context, vectors), prediction_window: T::PredictionWindow.new(start: Time.utc(2010, 6, 15).to_i, stop: Time.utc(2010, 6, 16).to_i, step: nil, instants: nil) }]
        }
        current_context = PREDICT.context(vectors, "OTC-V-NOAA-ACT1591", "current", nil, nil, 1)
        current_args = T::ArgsReleaseCurrentEvents.new(member_id: "Release.current_events", station: current_context.station, start: Time.utc(2010, 6, 15), stop: Time.utc(2010, 6, 16), bin_number: 1, set_id: nil)
        leafs["B44.roots"] = [:find_unrounded_current_events, { selected_prediction_model: prediction_model(current_context, vectors, current_request: current_args), prediction_window: T::PredictionWindow.new(start: Time.utc(2010, 6, 15).to_i, stop: Time.utc(2010, 6, 16).to_i, step: nil, instants: nil), current_request: current_args }]
        @native_error = native_error
        @native_client = client
        @native_predict = predict
        @native_vectors = vectors
        @native_leafs = leafs.transform_values(&:last)
    end

    def teardown
        @native_client&.close
        @native_predict&.close
        @native_vectors&.__send__(:close)
        @native_stream_client&.close
        @native_source_graph&.__send__(:close)
        super
    end

    def native_source_arguments(callee)
        native_arguments
        release = @native_client.release
        station = release.require_station("OTC-T-0001")
        version = OpenTideConstants::SUPPORTED_FORMAT_VERSION.split(".").map(&:to_i)
        arguments = {
            "B05" => { source_bytes: File.binread(File.join(ROOT, "conformance/fixtures/good/OTC_20991231.2.json")), reader_version: T::ReaderVersion.new(major: version.first, minor: version.last), document_kind: "release" },
            "B06" => { parsed_document: OpenTideConstants::Reader.parse_json(File.read(File.join(ROOT, "conformance/fixtures/good/OTC_20991231.2.json"))), required_links: [] },
            "B08" => { access_kind: "raw_record", source_record: station.raw, station: station, release_origin: release, native_profile: "ruby" },
            "B08.origin" => { station: station, release_origin: release },
            "B15" => { resource_state: @native_client, lifetime_action: "close" },
            "B16" => { checksum_bytes: File.binread(File.join(ROOT, "conformance/fixtures/good/OTC_20991231.2.sha256")), pointer_digests: {}, required_files: [File.join(ROOT, "conformance/fixtures/good/OTC_20991231.2.json")] },
            "B20" => { release_files: @native_client, trusted_cached_pointer: T::TrustedCachedPointer.new(digests: {}) }
        }
        if %w[B25 B26 B27].include?(callee)
            server = serve
            cache_root = tmpdir
            OpenTideConstants.new(release: "20991231.2", base_url: server.url("/"), cache_dir: cache_root, mode: :stream).close
            @native_stream_client = OpenTideConstants.new(release: "20991231.2", cache_dir: cache_root, mode: :stream, offline: true)
            stream = @native_stream_client.release
            entry = stream.instance_variable_get(:@by_id).fetch("OTC-T-0001")
            arguments["B26"] = { index_entry: entry, station_source_row: stream.__send__(:materialize, entry).raw, index_presence: stream }
            arguments["B27"] = { stream_reader: stream, station_id: entry.station_id, release_origin: stream, reader_version: T::ReaderVersion.new(major: version.first, minor: version.last) }
            index = JSON.parse(File.read(File.join(@native_stream_client.__send__(:cache).release_dir("20991231.2"), "index-v1.json")))
            arguments["B25"] = { source_files: @native_stream_client, supplied_index: index, index_presence: index.to_h { |key, _| [key, true] }, reader_version: T::ReaderVersion.new(major: version.first, minor: version.last) }
        end
        arguments
    end

    def assert_native_value(callee, result, arguments)
        case callee
        when "B02"
            assert result.offline
            assert_equal :eager, result.mode
            assert_equal "https://data.opentideconstants.org/", result.base_url
        when "B03"
            assert_same arguments.fetch(:ordered_failures).first, result
            assert_same @native_error, result.cause
        when "B04"
            assert_same @native_client, result
        when "B07"
            original = arguments.fetch(:field_contract).native_context
            assert_equal original.station_id, result.station_id
            assert_equal original.raw, result.raw
            assert_same arguments.fetch(:origin).__send__(:station_origin), result.instance_variable_get(:@origin)
            assert_same original.instance_variable_get(:@sets), result.instance_variable_get(:@sets)
            assert_equal original.constant_sets.map(&:set_id), result.constant_sets.map(&:set_id)
        when "B08.raw"
            assert_same arguments.fetch(:source_record), result
            assert result.frozen?
        when "B24"
            source = arguments.fetch(:station_source_row)
            span = arguments.fetch(:source_byte_span)
            assert_equal source.fetch("station_id"), result.fetch("station_id")
            assert_equal span.offset_bytes, result.fetch("offset")
            assert_equal span.length_bytes, result.fetch("length")
            assert_equal OpenTideConstants::Reader.index_entry(source, span.offset_bytes, span.length_bytes), result
        when "B39"
            assert_equal arguments.fetch(:window_inputs).start.to_i, result.start
            assert_equal result.start, result.stop
            assert_nil result.step
            assert_nil result.instants
        when "B41"
            instant = arguments.fetch(:utc_instant)
            context = arguments.fetch(:selected_prediction_model).native_context
            origin, terms = context.total.year_data(Time.at(instant).utc.year)
            assert_equal Time.at(instant).utc.year, result.utc_year
            assert_equal origin / 3600.0, result.epoch_hours
            assert_equal terms, result.constituent_terms
            assert result.constituent_terms.frozen?
        when "B42"
            vector = JSON.parse(File.read(File.join(ROOT, "conformance/vectors/1.0/vectors.json"))).fetch("vectors").find { |row| row.fetch("id") == "OTC-V-NOAA-1820000/heights" }
            expected = vector.fetch("expect").fetch("prediction").fetch("items").first(3)
            assert_equal 3, result.length
            expected.zip(result).each { |row, height| assert_in_delta row.fetch("height_m"), height, 0.00001 }
        when "B43.roots", "B44.roots"
            window = arguments.fetch(:prediction_window)
            context = arguments.fetch(:selected_prediction_model).native_context
            tuples = result.select { |event| window.start <= (event.root_seconds + 0.5).floor && (event.root_seconds + 0.5).floor < window.stop }.map do |event|
                if callee == "B43.roots"
                    [event.root_seconds, event.event_type, event.height_m]
                else
                    [event.root_seconds, event.event_type, event.velocity_m_s, event.direction_deg]
                end
            end
            expected = callee == "B43.roots" ? PREDICT.events(context.total, window.start, window.stop) : PREDICT.current_events(context, window.start, window.stop)
            assert_equal expected, tuples
            assert_equal (0...result.length).to_a, result.map(&:reference_order)
            refute_empty result
        when "B05"
            assert_equal OpenTideConstants::Reader.parse_json(arguments.fetch(:source_bytes).dup.force_encoding(Encoding::UTF_8)), result
        when "B06"
            assert_same arguments.fetch(:parsed_document), result
        when "B25"
            @native_source_graph = result.native_context
            assert_equal arguments.fetch(:supplied_index), result.source_document
            assert_equal @native_client.release.station_count, result.native_context.station_count
        when "B08"
            assert_same arguments.fetch(:source_record), result
            assert result.frozen?
        when "B08.origin"
            assert_same arguments.fetch(:station), result
        when "B15"
            assert_same arguments.fetch(:resource_state), result
            assert_raises(OpenTideConstants::FileError) { result.station("OTC-T-0001") }
        when "B16"
            assert_equal OpenTideConstants::Reader.parse_sha256(arguments.fetch(:checksum_bytes)), result
        when "B20"
            assert_equal true, result
        when "B26"
            assert_same arguments.fetch(:station_source_row), result
        when "B27"
            assert_equal arguments.fetch(:station_id), result.fetch("station_id")
        end
    end

    def observe(id, callee, arguments)
        arguments.replace(native_arguments.fetch(callee)) if M1.include?(callee)
        arguments.replace(native_source_arguments(callee).fetch(callee)) if M2.include?(callee)
        row = LEDGER.fetch("runtime").find { |entry| entry.fetch("id") == callee }
        declaration = row.fetch("declaration")
        method = callee == "B28" ? OpenTideConstants::Cache.method(:encode_cache_json) : @subject.method(row.fetch("name"))
        parameters = method.parameters
        expected = row.fetch("inputs").map do |input|
            [callee == "B28" ? :req : (input["required"] == false ? :key : :keyreq), input.fetch("name").to_sym]
        end
        assert_equal expected.sort_by(&:last), parameters.sort_by(&:last)
        declaration.fetch("parameters").each do |parameter|
            native = "::OpenTideConstants::CanonicalTypes::#{parameter.fetch('concept_ref')}"
            value = arguments.fetch(parameter.fetch("canonical_name").to_sym)
            optional = row.fetch("inputs").find { |input| input.fetch("name") == parameter.fetch("canonical_name") }["required"] == false
            assert optional || !value.equal?(T::ABSENT)
            assert @checker.value(value, RBS::Parser.parse_type(native)), "#{id} #{parameter.fetch('canonical_name')}: #{value.class} is not #{native}" unless optional && value.equal?(T::ABSENT)
        end
        if callee == "B28"
            result = yield
            assert_instance_of String, result
            assert_equal "{}", result
            refusal = nil
        elsif M1.include?(callee) || M2.include?(callee)
            if callee == "B01"
                error = assert_raises(OpenTideConstants::InvalidArgumentError) { yield }
                assert_equal @native_error.code, error.code
                assert_equal @native_error.message, error.message
                result = error
            else
                result = yield
                assert_native_value(callee, result, arguments)
                native = "::OpenTideConstants::CanonicalTypes::#{row.fetch('output').fetch('concept_ref')}"
                assert @checker.value(result, RBS::Parser.parse_type(native)), "#{id} #{result.class} is not #{native}"
            end
            refusal = nil
        else
            assert @subject.private_methods.include?(row.fetch("name").to_sym)
            error = assert_raises(C::Unimplemented) { yield }
            assert_equal declaration.fetch("refusal"), error.message
            assert_equal callee, error.behavior_id
            refusal = error.message
        end
        EVENTS << { "id" => id, "callee_id" => callee, "method_owner" => method.owner.name, "parameters" => method.parameters, "actual_argument_classes" => arguments.transform_values { |value| value.class.name }, "actual_argument_values" => arguments.transform_values { |value| describe(value) }, "actual_native_result" => describe(result), "native_refusal" => refusal, "source_location" => method.source_location, "cleanup_observed" => true }
    end

    def test_b01
        arguments = { operation: "astro_table", arguments: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), member_contract: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: "") }
        observe("B01", "B01", arguments) do
            @subject.__send__(:validate_operation_arguments, operation: arguments.fetch(:operation), arguments: arguments.fetch(:arguments), member_contract: arguments.fetch(:member_contract))
        end
    end

    def test_b02
        arguments = { explicit_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), environment: {}, platform_defaults: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: "") }
        observe("B02", "B02", arguments) do
            @subject.__send__(:resolve_effective_options, explicit_options: arguments.fetch(:explicit_options), environment: arguments.fetch(:environment), platform_defaults: arguments.fetch(:platform_defaults))
        end
    end

    def test_b03
        arguments = { operation: "astro_table", ordered_failures: [], cause: RuntimeError.new("native construction cause") }
        observe("B03", "B03", arguments) do
            @subject.__send__(:select_canonical_error, operation: arguments.fetch(:operation), ordered_failures: arguments.fetch(:ordered_failures), cause: arguments.fetch(:cause))
        end
    end

    def test_b04
        arguments = { canonical_result: T::SelectedResult0.new(member_id: "Client.open", value: inert(::OpenTideConstants)), canonical_error: T::CanonicalError.new(code: "invalid_argument", structured_fields: nil, cause: RuntimeError.new("native construction cause")), native_profile: "python" }
        observe("B04", "B04", arguments) do
            @subject.__send__(:translate_native_binding, canonical_result: arguments.fetch(:canonical_result), canonical_error: arguments.fetch(:canonical_error), native_profile: arguments.fetch(:native_profile))
        end
    end

    def test_b05
        arguments = { source_bytes: "", reader_version: T::ReaderVersion.new(major: 1, minor: 1), document_kind: "release" }
        observe("B05", "B05", arguments) do
            @subject.__send__(:decode_release_document, source_bytes: arguments.fetch(:source_bytes), reader_version: arguments.fetch(:reader_version), document_kind: arguments.fetch(:document_kind))
        end
    end

    def test_b06
        arguments = { parsed_document: nil, required_links: [] }
        observe("B06", "B06", arguments) do
            @subject.__send__(:validate_release_links, parsed_document: arguments.fetch(:parsed_document), required_links: arguments.fetch(:required_links))
        end
    end

    def test_b07
        arguments = { raw_fields: nil, field_contract: T::FieldContracts.new(model_type: "Client", fields: []), origin: T::Origin.new(), model_type: "Client" }
        observe("B07", "B07", arguments) do
            @subject.__send__(:materialize_typed_model, raw_fields: arguments.fetch(:raw_fields), field_contract: arguments.fetch(:field_contract), origin: arguments.fetch(:origin), model_type: arguments.fetch(:model_type))
        end
    end

    def test_b08
        arguments = { access_kind: "raw_record", source_record: {}, station: inert(::OpenTideConstants::Station), release_origin: T::Origin.new(), native_profile: "python" }
        observe("B08", "B08", arguments) do
            @subject.__send__(:access_raw_record, access_kind: arguments.fetch(:access_kind), source_record: arguments.fetch(:source_record), station: arguments.fetch(:station), release_origin: arguments.fetch(:release_origin), native_profile: arguments.fetch(:native_profile))
        end
    end

    def test_b09
        arguments = { arguments: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), environment: {}, platform_defaults: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), clock: 0.0, native_profile: "python", reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B09", "B09", arguments) do
            @subject.__send__(:open_client_release, arguments: arguments.fetch(:arguments), environment: arguments.fetch(:environment), platform_defaults: arguments.fetch(:platform_defaults), cache_state: arguments.fetch(:cache_state), clock: arguments.fetch(:clock), native_profile: arguments.fetch(:native_profile), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b10
        arguments = { release_request: "latest", effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), clock: 0.0, reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B10", "B10", arguments) do
            @subject.__send__(:resolve_release_request, release_request: arguments.fetch(:release_request), effective_options: arguments.fetch(:effective_options), cache_state: arguments.fetch(:cache_state), clock: arguments.fetch(:clock), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b11
        arguments = { metadata_request: T::MetadataRequest.new(request_url: "", document_kind: ""), trusted_cache: nil, transport_options: T::ArgsClientOpenSelected.new(member_id: "Client.open", offline: false, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), clock: 0.0, reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B11", "B11", arguments) do
            @subject.__send__(:exchange_release_metadata, metadata_request: arguments.fetch(:metadata_request), trusted_cache: arguments.fetch(:trusted_cache), transport_options: arguments.fetch(:transport_options), cache_state: arguments.fetch(:cache_state), clock: arguments.fetch(:clock), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b12
        arguments = { client_state: T::ClientState.new(current_release: inert(::OpenTideConstants::Release), effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), last_error: nil, last_update_check: 0.0, closed: false), update_request: T::MetadataRequest.new(request_url: "", document_kind: ""), clock: 0.0, reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B12", "B12", arguments) do
            @subject.__send__(:update_client_release, client_state: arguments.fetch(:client_state), update_request: arguments.fetch(:update_request), clock: arguments.fetch(:clock), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b13
        arguments = { client_state: T::ClientState.new(current_release: inert(::OpenTideConstants::Release), effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), last_error: nil, last_update_check: 0.0, closed: false), query_kind: "stations", clock: 0.0, reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B13", "B13", arguments) do
            @subject.__send__(:refresh_client_if_due, client_state: arguments.fetch(:client_state), query_kind: arguments.fetch(:query_kind), clock: arguments.fetch(:clock), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b14
        arguments = { held_release: inert(::OpenTideConstants::Release), query_arguments: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: "") }
        observe("B14", "B14", arguments) do
            @subject.__send__(:forward_held_release, held_release: arguments.fetch(:held_release), query_arguments: arguments.fetch(:query_arguments))
        end
    end

    def test_b15
        arguments = { resource_state: T::ClientState.new(current_release: inert(::OpenTideConstants::Release), effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), last_error: nil, last_update_check: 0.0, closed: false), lifetime_action: "" }
        observe("B15", "B15", arguments) do
            @subject.__send__(:enforce_resource_lifetime, resource_state: arguments.fetch(:resource_state), lifetime_action: arguments.fetch(:lifetime_action))
        end
    end

    def test_b16
        arguments = { checksum_bytes: "", pointer_digests: {}, required_files: [] }
        observe("B16", "B16", arguments) do
            @subject.__send__(:bind_checksum_manifest, checksum_bytes: arguments.fetch(:checksum_bytes), pointer_digests: arguments.fetch(:pointer_digests), required_files: arguments.fetch(:required_files))
        end
    end

    def test_b17
        arguments = { acquisition_descriptor: T::ReleaseDescriptor.new(datestamp: "", files: [], checksum_bytes: "", pointer_digests: {}, required_file_request: nil, metadata: nil), effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), load_mode: "eager", cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), clock: 0.0, reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B17", "B17", arguments) do
            @subject.__send__(:acquire_release_files, acquisition_descriptor: arguments.fetch(:acquisition_descriptor), effective_options: arguments.fetch(:effective_options), load_mode: arguments.fetch(:load_mode), cache_state: arguments.fetch(:cache_state), clock: arguments.fetch(:clock), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b18
        arguments = { locked_cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), verified_file_rows: [], release_metadata: nil }
        observe("B18", "B18", arguments) do
            @subject.__send__(:merge_cache_receipt, locked_cache_state: arguments.fetch(:locked_cache_state), verified_file_rows: arguments.fetch(:verified_file_rows), release_metadata: arguments.fetch(:release_metadata))
        end
    end

    def test_b19
        arguments = { release_candidates: [], effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), clock: 0.0 }
        observe("B19", "B19", arguments) do
            @subject.__send__(:select_cached_release, release_candidates: arguments.fetch(:release_candidates), effective_options: arguments.fetch(:effective_options), cache_state: arguments.fetch(:cache_state), clock: arguments.fetch(:clock))
        end
    end

    def test_b20
        arguments = { release_files: [], trusted_cached_pointer: T::TrustedCachedPointer.new(digests: {}) }
        observe("B20", "B20", arguments) do
            @subject.__send__(:verify_release_files, release_files: arguments.fetch(:release_files), trusted_cached_pointer: arguments.fetch(:trusted_cached_pointer))
        end
    end

    def test_b21
        arguments = { destination: "", format_selection: T::FormatSelection.new(formats: [], required_files: []), overwrite_policy: [], release_files: [], checksum_bytes: "", pointer_digests: {} }
        observe("B21", "B21", arguments) do
            @subject.__send__(:publish_download, destination: arguments.fetch(:destination), format_selection: arguments.fetch(:format_selection), overwrite_policy: arguments.fetch(:overwrite_policy), release_files: arguments.fetch(:release_files), checksum_bytes: arguments.fetch(:checksum_bytes), pointer_digests: arguments.fetch(:pointer_digests))
        end
    end

    def test_b22
        arguments = { inventory_action: "list", cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), keep: 1, current_cache_directory: "", clock: 0.0 }
        observe("B22", "B22", arguments) do
            @subject.__send__(:manage_cache_inventory, inventory_action: arguments.fetch(:inventory_action), cache_state: arguments.fetch(:cache_state), keep: arguments.fetch(:keep), current_cache_directory: arguments.fetch(:current_cache_directory), clock: arguments.fetch(:clock))
        end
    end

    def test_b23
        arguments = { io_kind: "lock", io_request: T::LockRequest.new(directory: "", operation: "take", token: ""), io_options: T::LockState.new(cache_root: "", owner: nil, held_token: ""), clock: 0.0 }
        observe("B23", "B23", arguments) do
            @subject.__send__(:perform_guarded_io, io_kind: arguments.fetch(:io_kind), io_request: arguments.fetch(:io_request), io_options: arguments.fetch(:io_options), clock: arguments.fetch(:clock))
        end
    end

    def test_b24
        arguments = { station_source_row: nil, source_byte_span: T::SourceByteSpan.new(offset_bytes: 1, length_bytes: 1), projection_contract: T::ProjectionContract.new(scalar_types: "", models: "", subordinate_offsets: "", scope: "", fallback: "") }
        observe("B24", "B24", arguments) do
            @subject.__send__(:project_station_index, station_source_row: arguments.fetch(:station_source_row), source_byte_span: arguments.fetch(:source_byte_span), projection_contract: arguments.fetch(:projection_contract))
        end
    end

    def test_b25
        arguments = { source_files: T::SourceFiles.new(jsonl: "", meta: "", jsonl_sha256: "", jsonl_size: 1, meta_sha256: "", meta_size: 1), supplied_index: T::SuppliedIndex.new(index_version: 1, discovery_index_version: 1, datestamp: "", jsonl: "", jsonl_sha256: "", jsonl_size: 1, by: "", stations: []), index_presence: {}, reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B25", "B25", arguments) do
            @subject.__send__(:authenticate_station_index, source_files: arguments.fetch(:source_files), supplied_index: arguments.fetch(:supplied_index), index_presence: arguments.fetch(:index_presence), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b26
        arguments = { index_entry: T::IndexEntry.new(station_id: "", status: "", name: "", name_folded: "", country: "", type: "", kind: "", reference_station_id: "", offsets_licence_id: "", recommended_set_id: "", lat: 0.0, lon: 0.0, offset: 1, length: 1, aliases: {}, sets: [], subordinate_offsets: T::SchemaSubordinateOffsets.new(reference_station_id: "", time_offset_high_min: 0.0, time_offset_low_min: 0.0, height_offset_high: 0.0, height_offset_low: 0.0, height_adjusted_type: "", licence_id: "", datum: {}, offset_id: "", source: "", source_type: "", source_version: "", source_record_id: "", qc_status: "", qc_flags: [], fallback: T::SchemaFallback.new(reason: "", basis: "", otc_finding: "", preferred_set_id: "", source_extensions: {}), vintage: T::SchemaHistoricalOffsetVintage.new(publication_year: 2020, source_lifecycle: "retired", removal_events: [], current_validity: "unestablished", current_accuracy: "unverified", reference_2020_equivalence: "", reference_2020_equivalence_sha256: "", source_extensions: {}), provenance: T::SchemaHistoricalOffsetProvenance.new(source_manifest_sha256: "667eec5b3fd25f99d46f24864766726094961d7db5fa104ca12450f3ecd0fdf7", input_sha256: [], book: "", annual_table_row: 1, printed_page: 1, pdf_page: 1, raw_row_text: "", raw_values_json: "", id_crosswalk: T::SchemaHistoricalOffsetProvenanceIdCrosswalk.new(legacy_id: "", status: "inferred", modern_alias_verified: false, evidence_sha256: [], source_extensions: {}), reference_binding: T::SchemaHistoricalOffsetProvenanceReferenceBinding.new(noaa_id: "", station_id: "", mapping_status: "primary_name_position", evidence_sha256: [], source_extensions: {}), acceptance_report_sha256: "", source_extensions: {}), source_extensions: {}), current_offsets: []), station_source_row: nil, index_presence: {} }
        observe("B26", "B26", arguments) do
            @subject.__send__(:compare_station_source, index_entry: arguments.fetch(:index_entry), station_source_row: arguments.fetch(:station_source_row), index_presence: arguments.fetch(:index_presence))
        end
    end

    def test_b27
        arguments = { stream_reader: T::StreamReader.new(release_view: inert(::OpenTideConstants::Release), file_descriptor: 1, index: nil, index_presence: nil, station_lru: nil, closed: false), station_id: "", release_origin: T::Origin.new(), reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B27", "B27", arguments) do
            @subject.__send__(:read_station_lazily, stream_reader: arguments.fetch(:stream_reader), station_id: arguments.fetch(:station_id), release_origin: arguments.fetch(:release_origin), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b28
        arguments = { cache_document: {} }
        observe("B28", "B28", arguments) do
            OpenTideConstants::Cache.encode_cache_json(arguments.fetch(:cache_document))
        end
    end

    def test_b29
        arguments = { release_view: inert(::OpenTideConstants::Release), identity_query: "", reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B29", "B29", arguments) do
            @subject.__send__(:lookup_station_identity, release_view: arguments.fetch(:release_view), identity_query: arguments.fetch(:identity_query), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b30
        arguments = { station_sets: [], original_recommendation: inert(::OpenTideConstants::ConstantSet), commercial_only: false }
        observe("B30", "B30", arguments) do
            @subject.__send__(:select_effective_recommendation, station_sets: arguments.fetch(:station_sets), original_recommendation: arguments.fetch(:original_recommendation), commercial_only: arguments.fetch(:commercial_only))
        end
    end

    def test_b31
        arguments = { candidate_path: T::CandidatePathDirect.new(station: inert(::OpenTideConstants::Station), constant_set: inert(::OpenTideConstants::ConstantSet), release_view: inert(::OpenTideConstants::Release)), include_flagged: false, include_fallback: false }
        observe("B31", "B31", arguments) do
            @subject.__send__(:admit_quality_path, candidate_path: arguments.fetch(:candidate_path), include_flagged: arguments.fetch(:include_flagged), include_fallback: arguments.fetch(:include_fallback))
        end
    end

    def test_b32
        arguments = { candidate_path: T::CandidatePathDirect.new(station: inert(::OpenTideConstants::Station), constant_set: inert(::OpenTideConstants::ConstantSet), release_view: inert(::OpenTideConstants::Release)), commercial_only: false, commercial_basis: "strict" }
        observe("B32", "B32", arguments) do
            @subject.__send__(:admit_commercial_path, candidate_path: arguments.fetch(:candidate_path), commercial_only: arguments.fetch(:commercial_only), commercial_basis: arguments.fetch(:commercial_basis))
        end
    end

    def test_b33
        arguments = { station_source_row: nil, path_request: "", release_view: inert(::OpenTideConstants::Release) }
        observe("B33", "B33", arguments) do
            @subject.__send__(:resolve_reference_path, station_source_row: arguments.fetch(:station_source_row), path_request: arguments.fetch(:path_request), release_view: arguments.fetch(:release_view))
        end
    end

    def test_b34
        arguments = { release_view: inert(::OpenTideConstants::Release), query_kind: "stations", query_options: T::ArgsReleaseStations.new(member_id: "Release.stations"), reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B34", "B34", arguments) do
            @subject.__send__(:execute_discovery_query, release_view: arguments.fetch(:release_view), query_kind: arguments.fetch(:query_kind), query_options: arguments.fetch(:query_options), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b35
        arguments = { summary_kind: "stats", release_view: inert(::OpenTideConstants::Release), station_sets: [], summary_options: T::SummaryOptions.new(original_recommendation: inert(::OpenTideConstants::ConstantSet), commercial_only: false, include_no_constants: false) }
        observe("B35", "B35", arguments) do
            @subject.__send__(:summarize_station_sets, summary_kind: arguments.fetch(:summary_kind), release_view: arguments.fetch(:release_view), station_sets: arguments.fetch(:station_sets), summary_options: arguments.fetch(:summary_options))
        end
    end

    def test_b36
        arguments = { own_offset: inert(::OpenTideConstants::SubordinateOffsets), reference_path: T::ReferencePath.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), own_offset: nil, reference_bin: 1), historical_policy: "fallback", selection_kind: "discovery", reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B36", "B36", arguments) do
            @subject.__send__(:admit_historical_offset, own_offset: arguments.fetch(:own_offset), reference_path: arguments.fetch(:reference_path), historical_policy: arguments.fetch(:historical_policy), selection_kind: arguments.fetch(:selection_kind), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b37
        arguments = { station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), commercial_only: false }
        observe("B37", "B37", arguments) do
            @subject.__send__(:format_attribution, station: arguments.fetch(:station), release_view: arguments.fetch(:release_view), commercial_only: arguments.fetch(:commercial_only))
        end
    end

    def test_b38
        arguments = { published_metadata: T::PublishedMetadata.new(contributors: nil, year: 1, concept_doi: "", zenodo_version_doi: "", dataset_url: ""), citation_style: "" }
        observe("B38", "B38", arguments) do
            @subject.__send__(:format_citation, published_metadata: arguments.fetch(:published_metadata), citation_style: arguments.fetch(:citation_style))
        end
    end

    def test_b39
        arguments = { time_inputs: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), window_inputs: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), step: 0.0, local_time_profile: T::ArgsHeightSeriesToLocal.new(member_id: "HeightSeries.to_local", tz: "") }
        observe("B39", "B39", arguments) do
            @subject.__send__(:parse_prediction_window, time_inputs: arguments.fetch(:time_inputs), window_inputs: arguments.fetch(:window_inputs), step: arguments.fetch(:step), local_time_profile: arguments.fetch(:local_time_profile))
        end
    end

    def test_b40
        arguments = { station_request: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), selection_options: T::ArgsReleaseHeightsSelected.new(member_id: "Release.heights", datum: "", set_id: "", offset_id: ""), reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B40", "B40", arguments) do
            @subject.__send__(:select_prediction_model, station_request: arguments.fetch(:station_request), release_view: arguments.fetch(:release_view), selection_options: arguments.fetch(:selection_options), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b41
        arguments = { selected_prediction_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), utc_instant: 0.0 }
        observe("B41", "B41", arguments) do
            @subject.__send__(:evaluate_astronomy, selected_prediction_model: arguments.fetch(:selected_prediction_model), utc_instant: arguments.fetch(:utc_instant))
        end
    end

    def test_b42
        arguments = { selected_prediction_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), prediction_instants: [], requested_datum: "" }
        observe("B42", "B42", arguments) do
            @subject.__send__(:evaluate_harmonic_height, selected_prediction_model: arguments.fetch(:selected_prediction_model), prediction_instants: arguments.fetch(:prediction_instants), requested_datum: arguments.fetch(:requested_datum))
        end
    end

    def test_b43
        arguments = { selected_prediction_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), prediction_window: T::PredictionWindow.new(start: 0.0, stop: 0.0, step: 0.0, instants: nil) }
        observe("B43", "B43", arguments) do
            @subject.__send__(:find_tide_events, selected_prediction_model: arguments.fetch(:selected_prediction_model), prediction_window: arguments.fetch(:prediction_window))
        end
    end

    def test_b44
        arguments = { selected_prediction_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), prediction_window: T::PredictionWindow.new(start: 0.0, stop: 0.0, step: 0.0, instants: nil), current_request: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), current_operation: "currents" }
        observe("B44", "B44", arguments) do
            @subject.__send__(:evaluate_direct_current, selected_prediction_model: arguments.fetch(:selected_prediction_model), prediction_window: arguments.fetch(:prediction_window), current_request: arguments.fetch(:current_request), current_operation: arguments.fetch(:current_operation))
        end
    end

    def test_b45
        arguments = { own_offset: inert(::OpenTideConstants::SubordinateOffsets), reference_path: T::ReferencePath.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), own_offset: nil, reference_bin: 1), prediction_window: T::PredictionWindow.new(start: 0.0, stop: 0.0, step: 0.0, instants: nil), tide_request: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B45", "B45", arguments) do
            @subject.__send__(:evaluate_tide_offset, own_offset: arguments.fetch(:own_offset), reference_path: arguments.fetch(:reference_path), prediction_window: arguments.fetch(:prediction_window), tide_request: arguments.fetch(:tide_request), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b46
        arguments = { own_offset: inert(::OpenTideConstants::SubordinateOffsets), reference_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), prediction_instants: [], requested_datum: "" }
        observe("B46", "B46", arguments) do
            @subject.__send__(:fold_equal_tide_offset, own_offset: arguments.fetch(:own_offset), reference_model: arguments.fetch(:reference_model), prediction_instants: arguments.fetch(:prediction_instants), requested_datum: arguments.fetch(:requested_datum))
        end
    end

    def test_b47
        arguments = { own_current_offsets: {}, reference_path: T::ReferencePath.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), own_offset: nil, reference_bin: 1), prediction_window: T::PredictionWindow.new(start: 0.0, stop: 0.0, step: 0.0, instants: nil), current_request: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B47", "B47", arguments) do
            @subject.__send__(:evaluate_current_offset, own_current_offsets: arguments.fetch(:own_current_offsets), reference_path: arguments.fetch(:reference_path), prediction_window: arguments.fetch(:prediction_window), current_request: arguments.fetch(:current_request), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b48
        arguments = { auxiliary_kind: "model_access", auxiliary_operation: "astro_table", source_values: T::AuxiliaryValuesRequiresModel.new(station_request: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), selection_options: T::ArgsReleaseHeightsSelected.new(member_id: "Release.heights", datum: "", set_id: "", offset_id: ""), utc_instant: 0.0), result_context: T::ResultContext.new(station_id: "", set_id: "", reference_station_id: "", bin_number: 1, datum: "", release_datestamp: "", algorithm: ""), local_time_profile: T::ArgsHeightSeriesToLocal.new(member_id: "HeightSeries.to_local", tz: ""), result_values: T::SelectedResult0.new(member_id: "Client.open", value: inert(::OpenTideConstants)), utc_result: T::SelectedResult0.new(member_id: "Client.open", value: inert(::OpenTideConstants)), selection_options: T::ArgsReleaseHeightsSelected.new(member_id: "Release.heights", datum: "", set_id: "", offset_id: ""), reader_version: T::ReaderVersion.new(major: 1, minor: 1), auxiliary_member_id: "Client.open" }
        observe("B48", "B48", arguments) do
            @subject.__send__(:dispatch_auxiliary_result, auxiliary_kind: arguments.fetch(:auxiliary_kind), auxiliary_operation: arguments.fetch(:auxiliary_operation), source_values: arguments.fetch(:source_values), result_context: arguments.fetch(:result_context), local_time_profile: arguments.fetch(:local_time_profile), result_values: arguments.fetch(:result_values), utc_result: arguments.fetch(:utc_result), selection_options: arguments.fetch(:selection_options), reader_version: arguments.fetch(:reader_version), auxiliary_member_id: arguments.fetch(:auxiliary_member_id))
        end
    end

    def test_b08_raw
        arguments = { source_record: {}, native_profile: "python" }
        observe("B08.raw", "B08.raw", arguments) do
            @subject.__send__(:retain_raw_source_record, source_record: arguments.fetch(:source_record), native_profile: arguments.fetch(:native_profile))
        end
    end

    def test_b08_origin
        arguments = { station: inert(::OpenTideConstants::Station), release_origin: T::Origin.new() }
        observe("B08.origin", "B08.origin", arguments) do
            @subject.__send__(:check_station_origin, station: arguments.fetch(:station), release_origin: arguments.fetch(:release_origin))
        end
    end

    def test_b23_lock
        arguments = { lock_request: T::LockRequest.new(directory: "", operation: "take", token: ""), lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: ""), clock: 0.0 }
        observe("B23.lock", "B23.lock", arguments) do
            @subject.__send__(:manage_cache_lock, lock_request: arguments.fetch(:lock_request), lock_state: arguments.fetch(:lock_state), clock: arguments.fetch(:clock))
        end
    end

    def test_b23_http
        arguments = { http_request: T::HttpRequest.new(url: "", conditional_etag: ""), transport_options: T::ArgsClientOpenSelected.new(member_id: "Client.open", offline: false, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "") }
        observe("B23.http", "B23.http", arguments) do
            @subject.__send__(:request_http_resource, http_request: arguments.fetch(:http_request), transport_options: arguments.fetch(:transport_options))
        end
    end

    def test_b35_stats
        arguments = { release_view: inert(::OpenTideConstants::Release) }
        observe("B35.stats", "B35.stats", arguments) do
            @subject.__send__(:count_release_statistics, release_view: arguments.fetch(:release_view))
        end
    end

    def test_b35_sets
        arguments = { station_sets: [], original_recommendation: inert(::OpenTideConstants::ConstantSet), commercial_only: false, include_no_constants: false }
        observe("B35.sets", "B35.sets", arguments) do
            @subject.__send__(:order_constant_sets, station_sets: arguments.fetch(:station_sets), original_recommendation: arguments.fetch(:original_recommendation), commercial_only: arguments.fetch(:commercial_only), include_no_constants: arguments.fetch(:include_no_constants))
        end
    end

    def test_b48_aux
        arguments = { auxiliary_operation: "astro_table", source_values: T::AuxiliaryValuesRequiresModel.new(station_request: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), selection_options: T::ArgsReleaseHeightsSelected.new(member_id: "Release.heights", datum: "", set_id: "", offset_id: ""), utc_instant: 0.0), selection_options: T::ArgsReleaseHeightsSelected.new(member_id: "Release.heights", datum: "", set_id: "", offset_id: ""), reader_version: T::ReaderVersion.new(major: 1, minor: 1), auxiliary_member_id: "Client.open" }
        observe("B48.aux", "B48.aux", arguments) do
            @subject.__send__(:read_auxiliary_model_value, auxiliary_operation: arguments.fetch(:auxiliary_operation), source_values: arguments.fetch(:source_values), selection_options: arguments.fetch(:selection_options), reader_version: arguments.fetch(:reader_version), auxiliary_member_id: arguments.fetch(:auxiliary_member_id))
        end
    end

    def test_b48_context
        arguments = { result_values: T::SelectedResult0.new(member_id: "Client.open", value: inert(::OpenTideConstants)), result_context: T::ResultContext.new(station_id: "", set_id: "", reference_station_id: "", bin_number: 1, datum: "", release_datestamp: "", algorithm: "") }
        observe("B48.context", "B48.context", arguments) do
            @subject.__send__(:construct_prediction_result, result_values: arguments.fetch(:result_values), result_context: arguments.fetch(:result_context))
        end
    end

    def test_b48_local
        arguments = { utc_result: T::SelectedResult0.new(member_id: "Client.open", value: inert(::OpenTideConstants)), local_time_profile: T::ArgsHeightSeriesToLocal.new(member_id: "HeightSeries.to_local", tz: "") }
        observe("B48.local", "B48.local", arguments) do
            @subject.__send__(:convert_result_to_local_time, utc_result: arguments.fetch(:utc_result), local_time_profile: arguments.fetch(:local_time_profile))
        end
    end

    def test_b43_roots
        arguments = { selected_prediction_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), prediction_window: T::PredictionWindow.new(start: 0.0, stop: 0.0, step: 0.0, instants: nil) }
        observe("B43.roots", "B43.roots", arguments) do
            @subject.__send__(:find_unrounded_tide_events, selected_prediction_model: arguments.fetch(:selected_prediction_model), prediction_window: arguments.fetch(:prediction_window))
        end
    end

    def test_b44_roots
        arguments = { selected_prediction_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), prediction_window: T::PredictionWindow.new(start: 0.0, stop: 0.0, step: 0.0, instants: nil), current_request: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: "") }
        observe("B44.roots", "B44.roots", arguments) do
            @subject.__send__(:find_unrounded_current_events, selected_prediction_model: arguments.fetch(:selected_prediction_model), prediction_window: arguments.fetch(:prediction_window), current_request: arguments.fetch(:current_request))
        end
    end

    def test_b17_sidecar
        arguments = { acquisition_descriptor: T::ReleaseDescriptor.new(datestamp: "", files: [], checksum_bytes: "", pointer_digests: {}, required_file_request: nil, metadata: nil), effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: "") }
        observe("B17.sidecar", "B17.sidecar", arguments) do
            @subject.__send__(:acquire_checksum_sidecar, acquisition_descriptor: arguments.fetch(:acquisition_descriptor), effective_options: arguments.fetch(:effective_options))
        end
    end

    def test_b08_s1_a1
        arguments = { source_record: {}, native_profile: "python" }
        observe("B08.S1.A1", "B08.raw", arguments) do
            @subject.__send__(:retain_raw_source_record, source_record: arguments.fetch(:source_record), native_profile: arguments.fetch(:native_profile))
        end
    end

    def test_b08_s1_a2
        arguments = { station: inert(::OpenTideConstants::Station), release_origin: T::Origin.new() }
        observe("B08.S1.A2", "B08.origin", arguments) do
            @subject.__send__(:check_station_origin, station: arguments.fetch(:station), release_origin: arguments.fetch(:release_origin))
        end
    end

    def test_b09_s1_a3
        arguments = { operation: "astro_table", arguments: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), member_contract: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: "") }
        observe("B09.S1.A3", "B01", arguments) do
            @subject.__send__(:validate_operation_arguments, operation: arguments.fetch(:operation), arguments: arguments.fetch(:arguments), member_contract: arguments.fetch(:member_contract))
        end
    end

    def test_b09_s1_a4
        arguments = { explicit_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), environment: {}, platform_defaults: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: "") }
        observe("B09.S1.A4", "B02", arguments) do
            @subject.__send__(:resolve_effective_options, explicit_options: arguments.fetch(:explicit_options), environment: arguments.fetch(:environment), platform_defaults: arguments.fetch(:platform_defaults))
        end
    end

    def test_b09_s1_a5
        arguments = { release_request: "latest", effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), clock: 0.0, reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B09.S1.A5", "B10", arguments) do
            @subject.__send__(:resolve_release_request, release_request: arguments.fetch(:release_request), effective_options: arguments.fetch(:effective_options), cache_state: arguments.fetch(:cache_state), clock: arguments.fetch(:clock), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b09_s2_a4
        arguments = { checksum_bytes: "", pointer_digests: {}, required_files: [] }
        observe("B09.S2.A4", "B16", arguments) do
            @subject.__send__(:bind_checksum_manifest, checksum_bytes: arguments.fetch(:checksum_bytes), pointer_digests: arguments.fetch(:pointer_digests), required_files: arguments.fetch(:required_files))
        end
    end

    def test_b09_s2_a9
        arguments = { source_bytes: "", reader_version: T::ReaderVersion.new(major: 1, minor: 1), document_kind: "release" }
        observe("B09.S2.A9", "B05", arguments) do
            @subject.__send__(:decode_release_document, source_bytes: arguments.fetch(:source_bytes), reader_version: arguments.fetch(:reader_version), document_kind: arguments.fetch(:document_kind))
        end
    end

    def test_b09_s2_a11
        arguments = { parsed_document: nil, required_links: [] }
        observe("B09.S2.A11", "B06", arguments) do
            @subject.__send__(:validate_release_links, parsed_document: arguments.fetch(:parsed_document), required_links: arguments.fetch(:required_links))
        end
    end

    def test_b10_s1_a2
        arguments = { release_candidates: [], effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), clock: 0.0 }
        observe("B10.S1.A2", "B19", arguments) do
            @subject.__send__(:select_cached_release, release_candidates: arguments.fetch(:release_candidates), effective_options: arguments.fetch(:effective_options), cache_state: arguments.fetch(:cache_state), clock: arguments.fetch(:clock))
        end
    end

    def test_b10_s1_a5
        arguments = { acquisition_descriptor: T::ReleaseDescriptor.new(datestamp: "", files: [], checksum_bytes: "", pointer_digests: {}, required_file_request: nil, metadata: nil), effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), load_mode: "eager", cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), clock: 0.0, reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B10.S1.A5", "B17", arguments) do
            @subject.__send__(:acquire_release_files, acquisition_descriptor: arguments.fetch(:acquisition_descriptor), effective_options: arguments.fetch(:effective_options), load_mode: arguments.fetch(:load_mode), cache_state: arguments.fetch(:cache_state), clock: arguments.fetch(:clock), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b10_s2_a1
        arguments = { release_candidates: [], effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), clock: 0.0 }
        observe("B10.S2.A1", "B19", arguments) do
            @subject.__send__(:select_cached_release, release_candidates: arguments.fetch(:release_candidates), effective_options: arguments.fetch(:effective_options), cache_state: arguments.fetch(:cache_state), clock: arguments.fetch(:clock))
        end
    end

    def test_b10_s3_a4
        arguments = { metadata_request: T::MetadataRequest.new(request_url: "", document_kind: ""), trusted_cache: nil, transport_options: T::ArgsClientOpenSelected.new(member_id: "Client.open", offline: false, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), clock: 0.0, reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B10.S3.A4", "B11", arguments) do
            @subject.__send__(:exchange_release_metadata, metadata_request: arguments.fetch(:metadata_request), trusted_cache: arguments.fetch(:trusted_cache), transport_options: arguments.fetch(:transport_options), cache_state: arguments.fetch(:cache_state), clock: arguments.fetch(:clock), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b10_s3_a6
        arguments = { acquisition_descriptor: T::ReleaseDescriptor.new(datestamp: "", files: [], checksum_bytes: "", pointer_digests: {}, required_file_request: nil, metadata: nil), effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), load_mode: "eager", cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), clock: 0.0, reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B10.S3.A6", "B17", arguments) do
            @subject.__send__(:acquire_release_files, acquisition_descriptor: arguments.fetch(:acquisition_descriptor), effective_options: arguments.fetch(:effective_options), load_mode: arguments.fetch(:load_mode), cache_state: arguments.fetch(:cache_state), clock: arguments.fetch(:clock), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b10_s4_a1
        arguments = { release_candidates: [], effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), clock: 0.0 }
        observe("B10.S4.A1", "B19", arguments) do
            @subject.__send__(:select_cached_release, release_candidates: arguments.fetch(:release_candidates), effective_options: arguments.fetch(:effective_options), cache_state: arguments.fetch(:cache_state), clock: arguments.fetch(:clock))
        end
    end

    def test_b11_s2_a2
        arguments = { http_request: T::HttpRequest.new(url: "", conditional_etag: ""), transport_options: T::ArgsClientOpenSelected.new(member_id: "Client.open", offline: false, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "") }
        observe("B11.S2.A2", "B23.http", arguments) do
            @subject.__send__(:request_http_resource, http_request: arguments.fetch(:http_request), transport_options: arguments.fetch(:transport_options))
        end
    end

    def test_b11_s3_a5
        arguments = { source_bytes: "", reader_version: T::ReaderVersion.new(major: 1, minor: 1), document_kind: "release" }
        observe("B11.S3.A5", "B05", arguments) do
            @subject.__send__(:decode_release_document, source_bytes: arguments.fetch(:source_bytes), reader_version: arguments.fetch(:reader_version), document_kind: arguments.fetch(:document_kind))
        end
    end

    def test_b11_s5_a2
        arguments = { lock_request: T::LockRequest.new(directory: "", operation: "take", token: ""), lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: ""), clock: 0.0 }
        observe("B11.S5.A2", "B23.lock", arguments) do
            @subject.__send__(:manage_cache_lock, lock_request: arguments.fetch(:lock_request), lock_state: arguments.fetch(:lock_state), clock: arguments.fetch(:clock))
        end
    end

    def test_b11_s5_a4
        arguments = { cache_document: {} }
        observe("B11.S5.A4", "B28", arguments) do
            OpenTideConstants::Cache.encode_cache_json(arguments.fetch(:cache_document))
        end
    end

    def test_b12_s1_a3
        arguments = { resource_state: T::ClientState.new(current_release: inert(::OpenTideConstants::Release), effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), last_error: nil, last_update_check: 0.0, closed: false), lifetime_action: "" }
        observe("B12.S1.A3", "B15", arguments) do
            @subject.__send__(:enforce_resource_lifetime, resource_state: arguments.fetch(:resource_state), lifetime_action: arguments.fetch(:lifetime_action))
        end
    end

    def test_b12_s1_a7
        arguments = { metadata_request: T::MetadataRequest.new(request_url: "", document_kind: ""), trusted_cache: nil, transport_options: T::ArgsClientOpenSelected.new(member_id: "Client.open", offline: false, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), clock: 0.0, reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B12.S1.A7", "B11", arguments) do
            @subject.__send__(:exchange_release_metadata, metadata_request: arguments.fetch(:metadata_request), trusted_cache: arguments.fetch(:trusted_cache), transport_options: arguments.fetch(:transport_options), cache_state: arguments.fetch(:cache_state), clock: arguments.fetch(:clock), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b12_s2_a2
        arguments = { release_request: "latest", effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), clock: 0.0, reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B12.S2.A2", "B10", arguments) do
            @subject.__send__(:resolve_release_request, release_request: arguments.fetch(:release_request), effective_options: arguments.fetch(:effective_options), cache_state: arguments.fetch(:cache_state), clock: arguments.fetch(:clock), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b13_s3_a2
        arguments = { client_state: T::ClientState.new(current_release: inert(::OpenTideConstants::Release), effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), last_error: nil, last_update_check: 0.0, closed: false), update_request: T::MetadataRequest.new(request_url: "", document_kind: ""), clock: 0.0, reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B13.S3.A2", "B12", arguments) do
            @subject.__send__(:update_client_release, client_state: arguments.fetch(:client_state), update_request: arguments.fetch(:update_request), clock: arguments.fetch(:clock), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b14_s2_a2
        arguments = { resource_state: T::ClientState.new(current_release: inert(::OpenTideConstants::Release), effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), last_error: nil, last_update_check: 0.0, closed: false), lifetime_action: "" }
        observe("B14.S2.A2", "B15", arguments) do
            @subject.__send__(:enforce_resource_lifetime, resource_state: arguments.fetch(:resource_state), lifetime_action: arguments.fetch(:lifetime_action))
        end
    end

    def test_b17_s1_a2
        arguments = { lock_request: T::LockRequest.new(directory: "", operation: "take", token: ""), lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: ""), clock: 0.0 }
        observe("B17.S1.A2", "B23.lock", arguments) do
            @subject.__send__(:manage_cache_lock, lock_request: arguments.fetch(:lock_request), lock_state: arguments.fetch(:lock_state), clock: arguments.fetch(:clock))
        end
    end

    def test_b17_s1_a3
        arguments = { release_candidates: [], effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), clock: 0.0 }
        observe("B17.S1.A3", "B19", arguments) do
            @subject.__send__(:select_cached_release, release_candidates: arguments.fetch(:release_candidates), effective_options: arguments.fetch(:effective_options), cache_state: arguments.fetch(:cache_state), clock: arguments.fetch(:clock))
        end
    end

    def test_b17_s2_a1
        arguments = { acquisition_descriptor: T::ReleaseDescriptor.new(datestamp: "", files: [], checksum_bytes: "", pointer_digests: {}, required_file_request: nil, metadata: nil), effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: "") }
        observe("B17.S2.A1", "B17.sidecar", arguments) do
            @subject.__send__(:acquire_checksum_sidecar, acquisition_descriptor: arguments.fetch(:acquisition_descriptor), effective_options: arguments.fetch(:effective_options))
        end
    end

    def test_b17_s2_a3
        arguments = { checksum_bytes: "", pointer_digests: {}, required_files: [] }
        observe("B17.S2.A3", "B16", arguments) do
            @subject.__send__(:bind_checksum_manifest, checksum_bytes: arguments.fetch(:checksum_bytes), pointer_digests: arguments.fetch(:pointer_digests), required_files: arguments.fetch(:required_files))
        end
    end

    def test_b17_s2_a6
        arguments = { http_request: T::HttpRequest.new(url: "", conditional_etag: ""), transport_options: T::ArgsClientOpenSelected.new(member_id: "Client.open", offline: false, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "") }
        observe("B17.S2.A6", "B23.http", arguments) do
            @subject.__send__(:request_http_resource, http_request: arguments.fetch(:http_request), transport_options: arguments.fetch(:transport_options))
        end
    end

    def test_b17_s4_a2
        arguments = { locked_cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), verified_file_rows: [], release_metadata: nil }
        observe("B17.S4.A2", "B18", arguments) do
            @subject.__send__(:merge_cache_receipt, locked_cache_state: arguments.fetch(:locked_cache_state), verified_file_rows: arguments.fetch(:verified_file_rows), release_metadata: arguments.fetch(:release_metadata))
        end
    end

    def test_b17_s5_a4
        arguments = { source_files: T::SourceFiles.new(jsonl: "", meta: "", jsonl_sha256: "", jsonl_size: 1, meta_sha256: "", meta_size: 1), supplied_index: T::SuppliedIndex.new(index_version: 1, discovery_index_version: 1, datestamp: "", jsonl: "", jsonl_sha256: "", jsonl_size: 1, by: "", stations: []), index_presence: {}, reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B17.S5.A4", "B25", arguments) do
            @subject.__send__(:authenticate_station_index, source_files: arguments.fetch(:source_files), supplied_index: arguments.fetch(:supplied_index), index_presence: arguments.fetch(:index_presence), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b18_s4_a2
        arguments = { cache_document: {} }
        observe("B18.S4.A2", "B28", arguments) do
            OpenTideConstants::Cache.encode_cache_json(arguments.fetch(:cache_document))
        end
    end

    def test_b19_s3_a2
        arguments = { lock_request: T::LockRequest.new(directory: "", operation: "take", token: ""), lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: ""), clock: 0.0 }
        observe("B19.S3.A2", "B23.lock", arguments) do
            @subject.__send__(:manage_cache_lock, lock_request: arguments.fetch(:lock_request), lock_state: arguments.fetch(:lock_state), clock: arguments.fetch(:clock))
        end
    end

    def test_b20_s2_a2
        arguments = { checksum_bytes: "", pointer_digests: {}, required_files: [] }
        observe("B20.S2.A2", "B16", arguments) do
            @subject.__send__(:bind_checksum_manifest, checksum_bytes: arguments.fetch(:checksum_bytes), pointer_digests: arguments.fetch(:pointer_digests), required_files: arguments.fetch(:required_files))
        end
    end

    def test_b21_s2_a1
        arguments = { checksum_bytes: "", pointer_digests: {}, required_files: [] }
        observe("B21.S2.A1", "B16", arguments) do
            @subject.__send__(:bind_checksum_manifest, checksum_bytes: arguments.fetch(:checksum_bytes), pointer_digests: arguments.fetch(:pointer_digests), required_files: arguments.fetch(:required_files))
        end
    end

    def test_b22_s4_a2
        arguments = { lock_request: T::LockRequest.new(directory: "", operation: "take", token: ""), lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: ""), clock: 0.0 }
        observe("B22.S4.A2", "B23.lock", arguments) do
            @subject.__send__(:manage_cache_lock, lock_request: arguments.fetch(:lock_request), lock_state: arguments.fetch(:lock_state), clock: arguments.fetch(:clock))
        end
    end

    def test_b23_s1_a5
        arguments = { lock_request: T::LockRequest.new(directory: "", operation: "take", token: ""), lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: ""), clock: 0.0 }
        observe("B23.S1.A5", "B23.lock", arguments) do
            @subject.__send__(:manage_cache_lock, lock_request: arguments.fetch(:lock_request), lock_state: arguments.fetch(:lock_state), clock: arguments.fetch(:clock))
        end
    end

    def test_b23_s1_a7
        arguments = { http_request: T::HttpRequest.new(url: "", conditional_etag: ""), transport_options: T::ArgsClientOpenSelected.new(member_id: "Client.open", offline: false, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "") }
        observe("B23.S1.A7", "B23.http", arguments) do
            @subject.__send__(:request_http_resource, http_request: arguments.fetch(:http_request), transport_options: arguments.fetch(:transport_options))
        end
    end

    def test_b25_s4_a4
        arguments = { station_source_row: nil, source_byte_span: T::SourceByteSpan.new(offset_bytes: 1, length_bytes: 1), projection_contract: T::ProjectionContract.new(scalar_types: "", models: "", subordinate_offsets: "", scope: "", fallback: "") }
        observe("B25.S4.A4", "B24", arguments) do
            @subject.__send__(:project_station_index, station_source_row: arguments.fetch(:station_source_row), source_byte_span: arguments.fetch(:source_byte_span), projection_contract: arguments.fetch(:projection_contract))
        end
    end

    def test_b25_s4_a6
        arguments = { cache_document: {} }
        observe("B25.S4.A6", "B28", arguments) do
            OpenTideConstants::Cache.encode_cache_json(arguments.fetch(:cache_document))
        end
    end

    def test_b27_s1_a1
        arguments = { resource_state: T::ClientState.new(current_release: inert(::OpenTideConstants::Release), effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), last_error: nil, last_update_check: 0.0, closed: false), lifetime_action: "" }
        observe("B27.S1.A1", "B15", arguments) do
            @subject.__send__(:enforce_resource_lifetime, resource_state: arguments.fetch(:resource_state), lifetime_action: arguments.fetch(:lifetime_action))
        end
    end

    def test_b27_s4_a3
        arguments = { source_bytes: "", reader_version: T::ReaderVersion.new(major: 1, minor: 1), document_kind: "release" }
        observe("B27.S4.A3", "B05", arguments) do
            @subject.__send__(:decode_release_document, source_bytes: arguments.fetch(:source_bytes), reader_version: arguments.fetch(:reader_version), document_kind: arguments.fetch(:document_kind))
        end
    end

    def test_b27_s4_a7
        arguments = { index_entry: T::IndexEntry.new(station_id: "", status: "", name: "", name_folded: "", country: "", type: "", kind: "", reference_station_id: "", offsets_licence_id: "", recommended_set_id: "", lat: 0.0, lon: 0.0, offset: 1, length: 1, aliases: {}, sets: [], subordinate_offsets: T::SchemaSubordinateOffsets.new(reference_station_id: "", time_offset_high_min: 0.0, time_offset_low_min: 0.0, height_offset_high: 0.0, height_offset_low: 0.0, height_adjusted_type: "", licence_id: "", datum: {}, offset_id: "", source: "", source_type: "", source_version: "", source_record_id: "", qc_status: "", qc_flags: [], fallback: T::SchemaFallback.new(reason: "", basis: "", otc_finding: "", preferred_set_id: "", source_extensions: {}), vintage: T::SchemaHistoricalOffsetVintage.new(publication_year: 2020, source_lifecycle: "retired", removal_events: [], current_validity: "unestablished", current_accuracy: "unverified", reference_2020_equivalence: "", reference_2020_equivalence_sha256: "", source_extensions: {}), provenance: T::SchemaHistoricalOffsetProvenance.new(source_manifest_sha256: "667eec5b3fd25f99d46f24864766726094961d7db5fa104ca12450f3ecd0fdf7", input_sha256: [], book: "", annual_table_row: 1, printed_page: 1, pdf_page: 1, raw_row_text: "", raw_values_json: "", id_crosswalk: T::SchemaHistoricalOffsetProvenanceIdCrosswalk.new(legacy_id: "", status: "inferred", modern_alias_verified: false, evidence_sha256: [], source_extensions: {}), reference_binding: T::SchemaHistoricalOffsetProvenanceReferenceBinding.new(noaa_id: "", station_id: "", mapping_status: "primary_name_position", evidence_sha256: [], source_extensions: {}), acceptance_report_sha256: "", source_extensions: {}), source_extensions: {}), current_offsets: []), station_source_row: nil, index_presence: {} }
        observe("B27.S4.A7", "B26", arguments) do
            @subject.__send__(:compare_station_source, index_entry: arguments.fetch(:index_entry), station_source_row: arguments.fetch(:station_source_row), index_presence: arguments.fetch(:index_presence))
        end
    end

    def test_b29_s4_a4
        arguments = { stream_reader: T::StreamReader.new(release_view: inert(::OpenTideConstants::Release), file_descriptor: 1, index: nil, index_presence: nil, station_lru: nil, closed: false), station_id: "", release_origin: T::Origin.new(), reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B29.S4.A4", "B27", arguments) do
            @subject.__send__(:read_station_lazily, stream_reader: arguments.fetch(:stream_reader), station_id: arguments.fetch(:station_id), release_origin: arguments.fetch(:release_origin), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b29_s4_a8
        arguments = { raw_fields: nil, field_contract: T::FieldContracts.new(model_type: "Client", fields: []), origin: T::Origin.new(), model_type: "Client" }
        observe("B29.S4.A8", "B07", arguments) do
            @subject.__send__(:materialize_typed_model, raw_fields: arguments.fetch(:raw_fields), field_contract: arguments.fetch(:field_contract), origin: arguments.fetch(:origin), model_type: arguments.fetch(:model_type))
        end
    end

    def test_b34_s1_a1
        arguments = { resource_state: T::ClientState.new(current_release: inert(::OpenTideConstants::Release), effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), last_error: nil, last_update_check: 0.0, closed: false), lifetime_action: "" }
        observe("B34.S1.A1", "B15", arguments) do
            @subject.__send__(:enforce_resource_lifetime, resource_state: arguments.fetch(:resource_state), lifetime_action: arguments.fetch(:lifetime_action))
        end
    end

    def test_b34_s2_a4
        arguments = { station_sets: [], original_recommendation: inert(::OpenTideConstants::ConstantSet), commercial_only: false }
        observe("B34.S2.A4", "B30", arguments) do
            @subject.__send__(:select_effective_recommendation, station_sets: arguments.fetch(:station_sets), original_recommendation: arguments.fetch(:original_recommendation), commercial_only: arguments.fetch(:commercial_only))
        end
    end

    def test_b34_s2_a6
        arguments = { station_source_row: nil, path_request: "", release_view: inert(::OpenTideConstants::Release) }
        observe("B34.S2.A6", "B33", arguments) do
            @subject.__send__(:resolve_reference_path, station_source_row: arguments.fetch(:station_source_row), path_request: arguments.fetch(:path_request), release_view: arguments.fetch(:release_view))
        end
    end

    def test_b34_s3_a3
        arguments = { candidate_path: T::CandidatePathDirect.new(station: inert(::OpenTideConstants::Station), constant_set: inert(::OpenTideConstants::ConstantSet), release_view: inert(::OpenTideConstants::Release)), include_flagged: false, include_fallback: false }
        observe("B34.S3.A3", "B31", arguments) do
            @subject.__send__(:admit_quality_path, candidate_path: arguments.fetch(:candidate_path), include_flagged: arguments.fetch(:include_flagged), include_fallback: arguments.fetch(:include_fallback))
        end
    end

    def test_b34_s3_a4
        arguments = { candidate_path: T::CandidatePathDirect.new(station: inert(::OpenTideConstants::Station), constant_set: inert(::OpenTideConstants::ConstantSet), release_view: inert(::OpenTideConstants::Release)), commercial_only: false, commercial_basis: "strict" }
        observe("B34.S3.A4", "B32", arguments) do
            @subject.__send__(:admit_commercial_path, candidate_path: arguments.fetch(:candidate_path), commercial_only: arguments.fetch(:commercial_only), commercial_basis: arguments.fetch(:commercial_basis))
        end
    end

    def test_b34_s3_a8
        arguments = { own_offset: inert(::OpenTideConstants::SubordinateOffsets), reference_path: T::ReferencePath.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), own_offset: nil, reference_bin: 1), historical_policy: "fallback", selection_kind: "discovery", reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B34.S3.A8", "B36", arguments) do
            @subject.__send__(:admit_historical_offset, own_offset: arguments.fetch(:own_offset), reference_path: arguments.fetch(:reference_path), historical_policy: arguments.fetch(:historical_policy), selection_kind: arguments.fetch(:selection_kind), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b35_s1_a1
        arguments = { release_view: inert(::OpenTideConstants::Release) }
        observe("B35.S1.A1", "B35.stats", arguments) do
            @subject.__send__(:count_release_statistics, release_view: arguments.fetch(:release_view))
        end
    end

    def test_b35_s1_a2
        arguments = { station_sets: [], original_recommendation: inert(::OpenTideConstants::ConstantSet), commercial_only: false, include_no_constants: false }
        observe("B35.S1.A2", "B35.sets", arguments) do
            @subject.__send__(:order_constant_sets, station_sets: arguments.fetch(:station_sets), original_recommendation: arguments.fetch(:original_recommendation), commercial_only: arguments.fetch(:commercial_only), include_no_constants: arguments.fetch(:include_no_constants))
        end
    end

    def test_b36_s7_a2
        arguments = { station_request: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), selection_options: T::ArgsReleaseHeightsSelected.new(member_id: "Release.heights", datum: "", set_id: "", offset_id: ""), reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B36.S7.A2", "B40", arguments) do
            @subject.__send__(:select_prediction_model, station_request: arguments.fetch(:station_request), release_view: arguments.fetch(:release_view), selection_options: arguments.fetch(:selection_options), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b37_s1_a2
        arguments = { station: inert(::OpenTideConstants::Station), release_origin: T::Origin.new() }
        observe("B37.S1.A2", "B08.origin", arguments) do
            @subject.__send__(:check_station_origin, station: arguments.fetch(:station), release_origin: arguments.fetch(:release_origin))
        end
    end

    def test_b37_s2_a3
        arguments = { station_sets: [], original_recommendation: inert(::OpenTideConstants::ConstantSet), commercial_only: false }
        observe("B37.S2.A3", "B30", arguments) do
            @subject.__send__(:select_effective_recommendation, station_sets: arguments.fetch(:station_sets), original_recommendation: arguments.fetch(:original_recommendation), commercial_only: arguments.fetch(:commercial_only))
        end
    end

    def test_b37_s2_a5
        arguments = { station_source_row: nil, path_request: "", release_view: inert(::OpenTideConstants::Release) }
        observe("B37.S2.A5", "B33", arguments) do
            @subject.__send__(:resolve_reference_path, station_source_row: arguments.fetch(:station_source_row), path_request: arguments.fetch(:path_request), release_view: arguments.fetch(:release_view))
        end
    end

    def test_b40_s1_a2
        arguments = { station: inert(::OpenTideConstants::Station), release_origin: T::Origin.new() }
        observe("B40.S1.A2", "B08.origin", arguments) do
            @subject.__send__(:check_station_origin, station: arguments.fetch(:station), release_origin: arguments.fetch(:release_origin))
        end
    end

    def test_b40_s1_a3
        arguments = { release_view: inert(::OpenTideConstants::Release), identity_query: "", reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B40.S1.A3", "B29", arguments) do
            @subject.__send__(:lookup_station_identity, release_view: arguments.fetch(:release_view), identity_query: arguments.fetch(:identity_query), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b40_s2_a4
        arguments = { station_sets: [], original_recommendation: inert(::OpenTideConstants::ConstantSet), commercial_only: false }
        observe("B40.S2.A4", "B30", arguments) do
            @subject.__send__(:select_effective_recommendation, station_sets: arguments.fetch(:station_sets), original_recommendation: arguments.fetch(:original_recommendation), commercial_only: arguments.fetch(:commercial_only))
        end
    end

    def test_b42_s1_a2
        arguments = { selected_prediction_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), utc_instant: 0.0 }
        observe("B42.S1.A2", "B41", arguments) do
            @subject.__send__(:evaluate_astronomy, selected_prediction_model: arguments.fetch(:selected_prediction_model), utc_instant: arguments.fetch(:utc_instant))
        end
    end

    def test_b43_s1_a1
        arguments = { selected_prediction_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), prediction_window: T::PredictionWindow.new(start: 0.0, stop: 0.0, step: 0.0, instants: nil) }
        observe("B43.S1.A1", "B43.roots", arguments) do
            @subject.__send__(:find_unrounded_tide_events, selected_prediction_model: arguments.fetch(:selected_prediction_model), prediction_window: arguments.fetch(:prediction_window))
        end
    end

    def test_b44_s1_a1
        arguments = { selected_prediction_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), prediction_window: T::PredictionWindow.new(start: 0.0, stop: 0.0, step: 0.0, instants: nil), current_request: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: "") }
        observe("B44.S1.A1", "B44.roots", arguments) do
            @subject.__send__(:find_unrounded_current_events, selected_prediction_model: arguments.fetch(:selected_prediction_model), prediction_window: arguments.fetch(:prediction_window), current_request: arguments.fetch(:current_request))
        end
    end

    def test_b45_s2_a3
        arguments = { own_offset: inert(::OpenTideConstants::SubordinateOffsets), reference_path: T::ReferencePath.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), own_offset: nil, reference_bin: 1), historical_policy: "fallback", selection_kind: "discovery", reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B45.S2.A3", "B36", arguments) do
            @subject.__send__(:admit_historical_offset, own_offset: arguments.fetch(:own_offset), reference_path: arguments.fetch(:reference_path), historical_policy: arguments.fetch(:historical_policy), selection_kind: arguments.fetch(:selection_kind), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b45_s3_a2
        arguments = { station_request: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), selection_options: T::ArgsReleaseHeightsSelected.new(member_id: "Release.heights", datum: "", set_id: "", offset_id: ""), reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B45.S3.A2", "B40", arguments) do
            @subject.__send__(:select_prediction_model, station_request: arguments.fetch(:station_request), release_view: arguments.fetch(:release_view), selection_options: arguments.fetch(:selection_options), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b45_s6_a2
        arguments = { selected_prediction_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), prediction_window: T::PredictionWindow.new(start: 0.0, stop: 0.0, step: 0.0, instants: nil) }
        observe("B45.S6.A2", "B43.roots", arguments) do
            @subject.__send__(:find_unrounded_tide_events, selected_prediction_model: arguments.fetch(:selected_prediction_model), prediction_window: arguments.fetch(:prediction_window))
        end
    end

    def test_b45_s7_a3
        arguments = { own_offset: inert(::OpenTideConstants::SubordinateOffsets), reference_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), prediction_instants: [], requested_datum: "" }
        observe("B45.S7.A3", "B46", arguments) do
            @subject.__send__(:fold_equal_tide_offset, own_offset: arguments.fetch(:own_offset), reference_model: arguments.fetch(:reference_model), prediction_instants: arguments.fetch(:prediction_instants), requested_datum: arguments.fetch(:requested_datum))
        end
    end

    def test_b46_s3_a2
        arguments = { selected_prediction_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), prediction_instants: [], requested_datum: "" }
        observe("B46.S3.A2", "B42", arguments) do
            @subject.__send__(:evaluate_harmonic_height, selected_prediction_model: arguments.fetch(:selected_prediction_model), prediction_instants: arguments.fetch(:prediction_instants), requested_datum: arguments.fetch(:requested_datum))
        end
    end

    def test_b47_s2_a2
        arguments = { station_request: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), selection_options: T::ArgsReleaseHeightsSelected.new(member_id: "Release.heights", datum: "", set_id: "", offset_id: ""), reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B47.S2.A2", "B40", arguments) do
            @subject.__send__(:select_prediction_model, station_request: arguments.fetch(:station_request), release_view: arguments.fetch(:release_view), selection_options: arguments.fetch(:selection_options), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b47_s4_a3
        arguments = { selected_prediction_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), prediction_window: T::PredictionWindow.new(start: 0.0, stop: 0.0, step: 0.0, instants: nil), current_request: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: "") }
        observe("B47.S4.A3", "B44.roots", arguments) do
            @subject.__send__(:find_unrounded_current_events, selected_prediction_model: arguments.fetch(:selected_prediction_model), prediction_window: arguments.fetch(:prediction_window), current_request: arguments.fetch(:current_request))
        end
    end

    def test_b48_s1_a1
        arguments = { auxiliary_operation: "astro_table", source_values: T::AuxiliaryValuesRequiresModel.new(station_request: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), selection_options: T::ArgsReleaseHeightsSelected.new(member_id: "Release.heights", datum: "", set_id: "", offset_id: ""), utc_instant: 0.0), selection_options: T::ArgsReleaseHeightsSelected.new(member_id: "Release.heights", datum: "", set_id: "", offset_id: ""), reader_version: T::ReaderVersion.new(major: 1, minor: 1), auxiliary_member_id: "Client.open" }
        observe("B48.S1.A1", "B48.aux", arguments) do
            @subject.__send__(:read_auxiliary_model_value, auxiliary_operation: arguments.fetch(:auxiliary_operation), source_values: arguments.fetch(:source_values), selection_options: arguments.fetch(:selection_options), reader_version: arguments.fetch(:reader_version), auxiliary_member_id: arguments.fetch(:auxiliary_member_id))
        end
    end

    def test_b48_s1_a2
        arguments = { result_values: T::SelectedResult0.new(member_id: "Client.open", value: inert(::OpenTideConstants)), result_context: T::ResultContext.new(station_id: "", set_id: "", reference_station_id: "", bin_number: 1, datum: "", release_datestamp: "", algorithm: "") }
        observe("B48.S1.A2", "B48.context", arguments) do
            @subject.__send__(:construct_prediction_result, result_values: arguments.fetch(:result_values), result_context: arguments.fetch(:result_context))
        end
    end

    def test_b48_s1_a3
        arguments = { utc_result: T::SelectedResult0.new(member_id: "Client.open", value: inert(::OpenTideConstants)), local_time_profile: T::ArgsHeightSeriesToLocal.new(member_id: "HeightSeries.to_local", tz: "") }
        observe("B48.S1.A3", "B48.local", arguments) do
            @subject.__send__(:convert_result_to_local_time, utc_result: arguments.fetch(:utc_result), local_time_profile: arguments.fetch(:local_time_profile))
        end
    end

    def test_b35_sets_s1_a1
        arguments = { station_sets: [], original_recommendation: inert(::OpenTideConstants::ConstantSet), commercial_only: false }
        observe("B35.sets.S1.A1", "B30", arguments) do
            @subject.__send__(:select_effective_recommendation, station_sets: arguments.fetch(:station_sets), original_recommendation: arguments.fetch(:original_recommendation), commercial_only: arguments.fetch(:commercial_only))
        end
    end

    def test_b48_aux_s2_a1
        arguments = { station_request: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), selection_options: T::ArgsReleaseHeightsSelected.new(member_id: "Release.heights", datum: "", set_id: "", offset_id: ""), reader_version: T::ReaderVersion.new(major: 1, minor: 1) }
        observe("B48.aux.S2.A1", "B40", arguments) do
            @subject.__send__(:select_prediction_model, station_request: arguments.fetch(:station_request), release_view: arguments.fetch(:release_view), selection_options: arguments.fetch(:selection_options), reader_version: arguments.fetch(:reader_version))
        end
    end

    def test_b48_aux_s2_a2
        arguments = { selected_prediction_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), utc_instant: 0.0 }
        observe("B48.aux.S2.A2", "B41", arguments) do
            @subject.__send__(:evaluate_astronomy, selected_prediction_model: arguments.fetch(:selected_prediction_model), utc_instant: arguments.fetch(:utc_instant))
        end
    end

    def test_b43_roots_s1_a2
        arguments = { selected_prediction_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), utc_instant: 0.0 }
        observe("B43.roots.S1.A2", "B41", arguments) do
            @subject.__send__(:evaluate_astronomy, selected_prediction_model: arguments.fetch(:selected_prediction_model), utc_instant: arguments.fetch(:utc_instant))
        end
    end

    def test_b44_roots_s2_a2
        arguments = { selected_prediction_model: T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil), utc_instant: 0.0 }
        observe("B44.roots.S2.A2", "B41", arguments) do
            @subject.__send__(:evaluate_astronomy, selected_prediction_model: arguments.fetch(:selected_prediction_model), utc_instant: arguments.fetch(:utc_instant))
        end
    end

    def test_b17_sidecar_s1_a3
        arguments = { http_request: T::HttpRequest.new(url: "", conditional_etag: ""), transport_options: T::ArgsClientOpenSelected.new(member_id: "Client.open", offline: false, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "") }
        observe("B17.sidecar.S1.A3", "B23.http", arguments) do
            @subject.__send__(:request_http_resource, http_request: arguments.fetch(:http_request), transport_options: arguments.fetch(:transport_options))
        end
    end

    def test_b04_omitted_nullable_no_value_and_native_exception_inputs
        nullable = T::SelectedResult23.new(member_id: 'Release.station', value: nil)
        no_value = T::SelectedResult11.new(member_id: 'Client.close', value: T::NoValue.new)
        type = RBS::Parser.parse_type("::OpenTideConstants::CanonicalTypes::canonical_result")
        assert @checker.value(nullable, type)
        assert @checker.value(no_value, type)
        refute_equal T::ABSENT, nullable
        refute_equal T::ABSENT, no_value
        assert_raises(C::Unimplemented) { @subject.__send__(:translate_native_binding, native_profile: "ruby") }
        assert_nil @subject.__send__(:translate_native_binding, canonical_result: nullable, native_profile: "ruby")
        assert_nil @subject.__send__(:translate_native_binding, canonical_result: no_value, native_profile: "ruby")
        assert_raises(C::Unimplemented) { @subject.__send__(:translate_native_binding, canonical_error: T::CanonicalError.new(code: "invalid_argument", structured_fields: {}, cause: ArgumentError.new("source")), native_profile: "ruby") }
        native_arguments
        failure = T::CanonicalError.new(code: @native_error.code, structured_fields: { "message" => @native_error.message }, cause: @native_error)
        assert_same @native_error, assert_raises(OpenTideConstants::InvalidArgumentError) { @subject.__send__(:translate_native_binding, canonical_error: failure, native_profile: "ruby") }
    end

    def test_b43_retains_real_survivor_discarded_by_public_rounding_window
        model = native_arguments.fetch("B43.roots").fetch(:selected_prediction_model)
        window = T::PredictionWindow.new(start: 1267419336, stop: 1267419337, step: nil, instants: nil)
        public_roots = PREDICT.events(model.native_context.total, window.start, window.stop)
        roots = @subject.__send__(:find_unrounded_tide_events, selected_prediction_model: model, prediction_window: window)
        assert_empty public_roots
        assert_equal 1, roots.length
        assert_equal "41d2e2d2323a7100", [roots.first.root_seconds].pack("G").unpack1("H*")
        assert_equal "high", roots.first.event_type
        assert_equal 1.0260600148575794, roots.first.height_m
        assert_equal 0, roots.first.reference_order
    end

    def test_b04_genuine_cached_client_retains_its_error_channel
        overrides = {}
        server = TestSupport.file_server(File.join(ROOT, "conformance/fixtures/good"), overrides)
        Dir.mktmpdir("otc-canonical-cache") do |cache|
            OpenTideConstants.new(base_url: server.url, cache_dir: cache).close
            overrides["OTC_latest-f1.json"] = [200, { "ETag" => '"portal"', "Content-Type" => "text/html" }, "<html>captive portal</html>"]
            client = OpenTideConstants.new(base_url: server.url, cache_dir: cache)
            begin
                assert_equal :cache_after_error, client.loaded_from
                error = client.last_error
                assert_kind_of OpenTideConstants::NetworkError, error
                failure = T::CanonicalError.new(code: error.code, structured_fields: { "message" => error.message, "url" => error.url, "status" => error.status }, cause: error)
                result = T::SelectedResult0.new(member_id: "Client.open", value: client)
                assert_same client, @subject.__send__(:translate_native_binding, canonical_result: result, canonical_error: failure, native_profile: "ruby")
                assert_same error, client.last_error
                assert_equal "20991231.2", client.release.datestamp
                assert_equal "OTC-T-0001", client.release.require_station("OTC-T-0001").station_id
                fields = CLIENT_FIELDS.to_h { |name| [name.to_sym, client.instance_variable_get("@#{name}")] }
                native_cache = client.__send__(:cache)
                context = T::PreparedClientFields.new(**fields, cache: native_cache)
                check_record(context)
                contract = T::FieldContracts.new(model_type: "Client", fields: [], native_context: context)
                different_error = assert_raises(OpenTideConstants::InvalidArgumentError) { OpenTideConstants.new(file: File.join(ROOT, "conformance/fixtures/good/OTC_20991231.2.json"), offline: true) }
                assert_raises(C::Unimplemented) do
                    @subject.__send__(:materialize_typed_model, raw_fields: { "loaded_from" => client.loaded_from.to_s, "last_error" => { "code" => different_error.code, "message" => different_error.message }, "newer_format_major" => nil }, field_contract: contract, origin: client.release, model_type: "Client")
                end
                materialized = @subject.__send__(:materialize_typed_model, raw_fields: { "loaded_from" => client.loaded_from.to_s, "last_error" => { "code" => error.code, "message" => error.message }, "newer_format_major" => nil }, field_contract: contract, origin: client.release, model_type: "Client")
                refute_same client, materialized
                assert_same native_cache, materialized.__send__(:cache)
                assert_same error, materialized.last_error
                assert_equal client.cached_releases, materialized.cached_releases
            ensure
                materialized&.close
                client.close
            end
        end
    ensure
        server&.stop
        assert server.errors.empty? if server
    end

    def test_b07_result_raw_nullable_scalars_and_borrowed_native_dependencies
        native_arguments
        release = @native_vectors
        types = T
        subject = @subject
        first, last = Time.utc(2010, 3, 1), Time.utc(2010, 3, 2)
        heights = release.heights_at("OTC-V-NOAA-1820000", [first, first + 3600])
        extremes = release.extremes("OTC-V-NOAA-1820000", start: first, stop: last)
        currents = release.currents("OTC-V-NOAA-ACT1616", start: first, stop: first + 600, bin_number: 1)
        events = release.current_events("OTC-V-NOAA-ACT1591", start: first, stop: last, bin_number: 1)
        datums = release.datums("OTC-V-NOAA-1820000")
        ranges = release.ranges("OTC-V-NOAA-1820000")
        raise "Authentic datum fixture absent" unless datums && !datums.levels.empty?
        contexts = [extremes.items.first, currents.items.first, events.items.first, heights, extremes, currents, events, datums, datums.levels.first, ranges]
        contexts.each do |context|
            klass = context.class
            tag = klass.name.split("::").last
            fields = klass.instance_method(:initialize).parameters.filter_map { |kind, name| name if %i[key keyreq].include?(kind) && name != :_local }
            raw = fields.to_h do |field|
                value = context.public_send(field)
                value = value.iso8601 if value.is_a?(Time)
                value = value.map { |item| item.class.instance_method(:initialize).parameters.filter_map { |kind, name| [name.to_s, item.public_send(name).is_a?(Time) ? item.public_send(name).iso8601 : item.public_send(name)] if %i[key keyreq].include?(kind) && name != :_local }.to_h } if %i[items levels].include?(field)
                [field.to_s, value]
            end
            raw = JSON.parse(JSON.generate(raw))
            field = fields.find { |name| !%i[time items levels _local].include?(name) && !context.public_send(name).nil? }
            raise "No genuine nonnull scalar #{tag}" unless field
            raw[field.to_s] = nil
            contract = types::FieldContracts.new(model_type: tag, fields: [], native_context: context)
            value = subject.__send__(:materialize_typed_model, raw_fields: raw, field_contract: contract, origin: release, model_type: tag)
            reference_keywords = fields.to_h { |name| [name, %i[time items levels].include?(name) ? context.public_send(name) : raw[name.to_s]] }
            reference_keywords[:method] = OpenTideConstants::Util.enum(reference_keywords[:method], OpenTideConstants::ENUMS[:prediction_method]) if %w[HeightSeries ExtremeList CurrentSeries CurrentEventList].include?(tag)
            reference = klass.new(**reference_keywords, _local: context.instance_variable_get(:@_local))
            fields.each do |name|
                expected = reference.public_send(name)
                expected.nil? ? assert_nil(value.public_send(name), "#{tag}.#{name}") : assert_equal(expected, value.public_send(name), "#{tag}.#{name}")
            end
            %i[time items levels].select { |name| fields.include?(name) }.each { |name| assert_same context.public_send(name), value.public_send(name), "#{tag}.#{name} ownership" }
        end
    end

    def test_b01_closed_native_receiver_contract_preserves_validated_arguments
        arguments = native_arguments.fetch("B39").fetch(:window_inputs)
        contract = @subject.__send__(:prepare_member_validation_context, arguments: arguments, native_receiver: @native_predict.release)
        check_record(contract)
        assert @checker.value(contract, RBS::Parser.parse_type("::OpenTideConstants::CanonicalTypes::member_contract"))
        assert_same arguments, @subject.__send__(:validate_operation_arguments, operation: "extremes", arguments: arguments, member_contract: contract)
        assert_same @native_predict.release, contract.native_receiver
    end

    def test_b01_prepared_station_row_and_attribution_guard_order
        native_arguments
        release = @native_predict.release
        station = release.require_station("OTC-P-0001")
        instant = Time.utc(2015, 6, 1)
        arguments = T::ArgsReleaseHeights.new(member_id: "Release.heights", station: station, start: instant, stop: instant, step_s: 600, datum: "chart", set_id: nil, offset_id: nil)
        contract = @subject.__send__(:prepare_member_validation_context, arguments: arguments, native_receiver: release)
        check_record(contract)
        assert_same arguments, @subject.__send__(:validate_operation_arguments, operation: "heights", arguments: arguments, member_contract: contract)
        assert_same station, contract.prepared_station
        assert_same station, contract.prepared_station_request
        missing = T::MemberValidationContext.new(member_id: arguments.member_id, native_profile: "ruby", native_receiver: release)
        assert_raises(C::Unimplemented) { @subject.__send__(:validate_operation_arguments, operation: "heights", arguments: arguments, member_contract: missing) }
        earlier = T::ArgsReleaseHeights.new(member_id: "Release.heights", station: station, start: 7, stop: instant, step_s: 600, datum: nil, set_id: nil, offset_id: nil)
        assert_raises(OpenTideConstants::InvalidArgumentError) { @subject.__send__(:validate_operation_arguments, operation: "heights", arguments: earlier, member_contract: missing) }
        table = release.astro_table("otc-test-predict-a")
        year_args = T::ArgsAstroTableNodeFactorForYear.new(member_id: "AstroTable.node_factor_for_year", name: "M2", year: 2015)
        row_contract = @subject.__send__(:prepare_member_validation_context, arguments: year_args, native_receiver: table)
        check_record(row_contract)
        assert_same table.__send__(:row_for, "M2"), row_contract.prepared_row
        assert_same year_args, @subject.__send__(:validate_operation_arguments, operation: "node_factor_for_year", arguments: year_args, member_contract: row_contract)
        assert_raises(OpenTideConstants::TimeOutOfRangeError) { table.node_factor_for_year("M2", 1900) }
        foreign = @native_client.release.require_station("OTC-T-0001")
        [[foreign, nil], [station, nil], [nil, foreign]].each do |items|
            attribution = T::ArgsReleaseAttribution.new(member_id: "Release.attribution", stations: items)
            prepared = @subject.__send__(:prepare_member_validation_context, arguments: attribution, native_receiver: release)
            check_record(prepared)
            expected = assert_raises(OpenTideConstants::InvalidArgumentError) { release.attribution(items) }
            actual = assert_raises(OpenTideConstants::InvalidArgumentError) { @subject.__send__(:validate_operation_arguments, operation: "attribution", arguments: attribution, member_contract: prepared) }
            assert_equal expected.message, actual.message
            assert_same prepared.prepared_attribution_steps.first.error, actual if prepared.prepared_attribution_steps.first&.error
        end
        valid = T::ArgsReleaseAttribution.new(member_id: "Release.attribution", stations: [station])
        expected_attribution = release.attribution([station])
        valid_context = @subject.__send__(:prepare_member_validation_context, arguments: valid, native_receiver: release)
        check_record(valid_context)
        assert_same release.instance_variable_get(:@by_id).fetch(station.station_id), valid_context.prepared_attribution_steps.first.entry
        assert_same valid, @subject.__send__(:validate_operation_arguments, operation: "attribution", arguments: valid, member_contract: valid_context)
        assert_equal expected_attribution, release.attribution([station])
    end

    def test_b01_native_proxy_guard_precedes_unchanged_ca_file_io
        file = File.join(ROOT, "conformance/fixtures/good/OTC_20991231.2.json")
        ["local", "https://127.0.0.1:1/"].each do |proxy|
            args = open_arguments(file: file, proxy: proxy, ca_file: File.join(ROOT, "missing-ca-control"))
            expected = assert_raises(OpenTideConstants::InvalidArgumentError) { OpenTideConstants.new(file: file, proxy: proxy, ca_file: args.ca_file) }
            actual = assert_raises(OpenTideConstants::InvalidArgumentError) { @subject.__send__(:validate_operation_arguments, operation: "open", arguments: args, member_contract: args) }
            assert_equal expected.message, actual.message
        end
        [nil, "http://127.0.0.1:1/"].each do |proxy|
            args = open_arguments(file: file, proxy: proxy)
            assert_same args, @subject.__send__(:validate_operation_arguments, operation: "open", arguments: args, member_contract: args)
            client = OpenTideConstants.new(file: file, proxy: proxy)
            assert_equal "20991231.2", client.release.datestamp
            client.close
        end
        error = assert_raises(OpenTideConstants::FileError) { OpenTideConstants.new(file: file, ca_file: File.join(ROOT, "missing-ca-control")) }
        assert_equal File.join(ROOT, "missing-ca-control"), error.path
    end

    def test_b39_actual_ruby_time_floor_order_duplicates_and_empty_window
        station = native_arguments.fetch("B39").fetch(:window_inputs).station
        times = [Time.at(1267419336.75).utc, Time.at(1267419336.25).utc, Time.at(1267419336.75).utc]
        arguments = T::ArgsReleaseHeightsAt.new(member_id: "Release.heights_at", station: station, times: times, datum: nil, set_id: nil, offset_id: nil)
        result = @subject.__send__(:parse_prediction_window, time_inputs: arguments, window_inputs: arguments, step: nil, local_time_profile: T::ArgsHeightSeriesToLocal.new(member_id: "HeightSeries.to_local", tz: "station"))
        assert_equal times.map { |time| PREDICT.instant(time) }, result.instants
        assert_equal [1267419336, 1267419336, 1267419336], result.instants
        assert_nil result.start
        assert_nil result.stop
        assert_nil result.step
        empty = native_arguments.fetch("B39")
        result = @subject.__send__(:parse_prediction_window, **empty)
        assert_equal result.start, result.stop
        assert_equal [result.start, result.stop], PREDICT.window(empty.fetch(:window_inputs).start, empty.fetch(:window_inputs).stop)
    end

    CLIENT_FIELDS = %w[requested mode on_network_error offline auto_update verify_on_open commercial_only commercial_basis historical_offsets_policy update_interval base_url cache_dir logger http lock closed last_error newer_format_major file loaded release loaded_from last_check].freeze

    def prepare_release(source)
        fields = %w[mode commercial_only commercial_basis historical_offsets_policy meta logger io on_bad_index io_lock station_cache station_cache_lock state files checks datestamp created format_version concept_doi zenodo_version_doi source_versions build_commit changelog_url conventions licences convention_by_id licence_by_id set_ids set_sources set_qc aliases by_id entries tombstones tomb_pos tomb_by_id constituent_names subordinates].to_h { |name| [name.to_sym, source.instance_variable_get("@#{name}")] }
        entries = fields.fetch(:entries).map { |entry| entry.dup.tap { |copy| copy.station = nil } }
        nodes = entries.to_h { |entry| [entry.station_id, entry] }
        fields[:entries] = entries
        fields[:by_id] = nodes
        fields[:subordinates] = fields.fetch(:subordinates).transform_values { |values| values.map { |entry| nodes.fetch(entry.station_id) }.freeze }.freeze
        fields[:state] = { closed: false }
        fields[:io_lock] = Mutex.new
        fields[:station_cache_lock] = Mutex.new
        fields[:station_cache] = {}
        old_io = fields.fetch(:io)
        fields[:io] = old_io ? File.open(old_io.path, "rb") : nil
        fields[:raws] = source.instance_variable_get(:@entries).to_h { |entry| [entry.station_id, source.require_station(entry.station_id).raw] }
        T::PreparedReleaseFields.new(**fields)
    end

    def test_b07_prepared_native_owner_fields_origin_and_close
        native_arguments
        original = @native_client.release
        held = original.require_station("OTC-T-0001")
        before = JSON.generate(held.raw)
        prepared = prepare_release(original)
        check_record(prepared)
        contract = T::FieldContracts.new(model_type: "Release", fields: [], native_context: prepared)
        receiver = @subject.__send__(:materialize_typed_model, raw_fields: original.instance_variable_get(:@meta), field_contract: contract, origin: original, model_type: "Release")
        refute_same original, receiver
        assert receiver.frozen?
        assert_equal original.station_count, receiver.station_count
        assert_equal original.stations.map(&:station_id), receiver.stations.map(&:station_id)
        station = receiver.require_station(held.station_id)
        assert_same receiver.__send__(:station_origin), station.instance_variable_get(:@origin)
        assert_same original.__send__(:station_origin), held.instance_variable_get(:@origin)
        assert_equal before, JSON.generate(station.raw)
        assert_equal original.attribution([held]), receiver.attribution([station])
        assert_raises(OpenTideConstants::InvalidArgumentError) { receiver.attribution([held]) }
        assert_raises(OpenTideConstants::InvalidArgumentError) { original.attribution([station]) }
        assert_same prepared.by_id.fetch(station.station_id), prepared.entries.find { |entry| entry.station_id == station.station_id }
        receiver.__send__(:close)
        assert_raises(OpenTideConstants::FileError) { receiver.station(station.station_id) }
        assert_same held, original.require_station(held.station_id)
        assert_equal before, JSON.generate(held.raw)
        client_values = CLIENT_FIELDS.to_h { |name| [name.to_sym, @native_client.instance_variable_get("@#{name}")] }
        client_context = T::PreparedClientFields.new(**client_values)
        check_record(client_context)
        client_contract = T::FieldContracts.new(model_type: "Client", fields: [], native_context: client_context)
        client = @subject.__send__(:materialize_typed_model, raw_fields: { "loaded_from" => @native_client.loaded_from.to_s, "last_error" => nil, "newer_format_major" => nil }, field_contract: client_contract, origin: original, model_type: "Client")
        refute_same @native_client, client
        assert_same original, client.release
        assert_equal @native_client.loaded_from, client.loaded_from
        assert_same client_context.http, client.instance_variable_get(:@http)
        assert_same client_context.lock, client.instance_variable_get(:@lock)
        assert_same client_context.loaded, client.instance_variable_get(:@loaded)
        assert_nil client.close
        assert_raises(OpenTideConstants::FileError) { client.station(held.station_id) }
        assert_equal before, JSON.generate(held.raw)
        assert_equal original.datestamp, client.release.datestamp
    ensure
        receiver&.__send__(:close)
        client&.close
    end

    def test_b07_stats_json_enum_keys_preserve_native_counts_and_domains
        native_arguments
        expected = @native_client.release.stats
        fields = %i[type kind country source qc_status]
        raw = JSON.parse(JSON.generate(fields.to_h { |field| [field, expected.public_send(field)] }))
        contract = T::FieldContracts.new(model_type: "Stats", fields: [], native_context: expected)
        actual = @subject.__send__(:materialize_typed_model, raw_fields: raw, field_contract: contract, origin: @native_client.release, model_type: "Stats")
        fields.each do |field|
            assert_equal expected.public_send(field), actual.public_send(field)
            assert_equal expected.public_send(field).keys, actual.public_send(field).keys
            assert actual.public_send(field).frozen?
        end
        assert actual.frozen?
    end

    def test_b07_station_and_constant_set_closed_dependencies_match_source_fields
        native_arguments
        release = @native_client.release
        station = release.require_station("OTC-T-0001")
        other = release.require_station("OTC-T-0002")
        sets = station.constant_sets(include_no_constants: true)
        [["Station", other, station], ["ConstantSet", sets[1], sets[0]]].each do |tag, expected, wrong|
            contract = T::FieldContracts.new(model_type: tag, fields: [], native_context: wrong)
            assert_raises(C::Unimplemented) { @subject.__send__(:materialize_typed_model, raw_fields: expected.raw, field_contract: contract, origin: release, model_type: tag) }
            matched = T::FieldContracts.new(model_type: tag, fields: [], native_context: expected)
            actual = @subject.__send__(:materialize_typed_model, raw_fields: expected.raw, field_contract: matched, origin: release, model_type: tag)
            assert_same expected.raw, actual.raw
            assert actual.raw.frozen?
            assert actual.frozen?
            if tag == "Station"
                assert_same expected.instance_variable_get(:@sets), actual.instance_variable_get(:@sets)
                assert_same expected.validation, actual.validation
                assert_same release.__send__(:station_origin), actual.instance_variable_get(:@origin)
                assert_equal expected.station_id, actual.station_id
            else
                assert_same expected.convention, actual.convention
                assert_same expected.licence, actual.licence
                assert_same expected.validation, actual.validation
                assert_equal expected.constituents.map(&:raw), actual.constituents.map(&:raw)
                assert_equal expected.set_id, actual.set_id
            end
        end
    end

    def test_b07_genuine_omitted_current_event_types_preserve_domains_and_items
        native_arguments
        context = @native_predict.current_events("OTC-P-0051", start: Time.utc(2015, 6, 1), stop: Time.utc(2015, 6, 2), bin_number: 1)
        fields = context.class.instance_method(:initialize).parameters.filter_map { |kind, name| name if %i[key keyreq].include?(kind) && name != :_local }
        raw = fields.to_h do |field|
            value = context.public_send(field)
            if field == :items
                value = value.map do |item|
                    { "time" => item.time.iso8601, "type" => item.type, "velocity_ms" => item.velocity_ms, "direction_deg" => item.direction_deg, "local_time" => item.local_time, "utc_offset_s" => item.utc_offset_s }
                end
            end
            [field.to_s, value]
        end
        raw = JSON.parse(JSON.generate(raw))
        contract = T::FieldContracts.new(model_type: "CurrentEventList", fields: [], native_context: context)
        actual = @subject.__send__(:materialize_typed_model, raw_fields: raw, field_contract: contract, origin: @native_predict.release, model_type: "CurrentEventList")
        fields.each { |field| assert_equal context.public_send(field), actual.public_send(field) unless context.public_send(field).nil? }
        assert_equal [:max_ebb, :slack_before_ebb], actual.omitted_event_types
        assert_same context.items, actual.items
        assert actual.omitted_event_types.frozen?
        [nil, []].each do |omitted|
            value = @subject.__send__(:materialize_typed_model, raw_fields: raw.merge("omitted_event_types" => omitted), field_contract: contract, origin: @native_predict.release, model_type: "CurrentEventList")
            omitted.nil? ? assert_nil(value.omitted_event_types) : assert_empty(value.omitted_event_types)
        end
    end

    def test_prepared_prediction_binding_preserves_requested_datum_and_current_station
        native_arguments
        release = @native_vectors
        first, last = Time.utc(2010, 3, 1), Time.utc(2010, 3, 2)
        instants = [first.to_i, first.to_i + 3600, first.to_i + 7200]
        mean = PREDICT.context(release, "OTC-V-NOAA-1820000", "water_level", nil, nil)
        assert_raises(C::Unimplemented) do
            @subject.__send__(:evaluate_harmonic_height, selected_prediction_model: prediction_model(mean, release), prediction_instants: instants, requested_datum: "chart")
        end
        %w[mean_level chart zero].each do |datum|
            context = PREDICT.context(release, "OTC-V-NOAA-1820000", "water_level", nil, datum)
            model = prediction_model(context, release, datum: datum)
            check_record(model)
            values = @subject.__send__(:evaluate_harmonic_height, selected_prediction_model: model, prediction_instants: instants, requested_datum: datum)
            expected = release.heights_at(context.station, instants.map { |instant| Time.at(instant).utc }, datum: datum).items.map(&:height_m)
            assert_equal expected, values
            assert_same context, model.selection_context
        end
        current = PREDICT.context(release, "OTC-V-NOAA-ACT1591", "current", nil, nil, 1)
        bound = T::ArgsReleaseCurrentEvents.new(member_id: "Release.current_events", station: current.station, start: first, stop: last, bin_number: 1, set_id: nil)
        foreign = T::ArgsReleaseCurrentEvents.new(member_id: "Release.current_events", station: release.require_station("OTC-V-NOAA-ACT1616"), start: first, stop: last, bin_number: 1, set_id: nil)
        model = prediction_model(current, release, current_request: bound)
        check_record(model)
        window = T::PredictionWindow.new(start: first.to_i, stop: last.to_i, step: nil, instants: nil)
        assert_raises(C::Unimplemented) { @subject.__send__(:find_unrounded_current_events, selected_prediction_model: model, prediction_window: window, current_request: foreign) }
        roots = @subject.__send__(:find_unrounded_current_events, selected_prediction_model: model, prediction_window: window, current_request: bound)
        assert_equal 9, roots.length
        assert_same bound, model.prepared_current_request
    end

    def check_record(value)
        name = RBS::Parser.parse_type("::#{value.class.name}").name
        definition = @builder.build_instance(name)
        value.instance_variables.each do |variable|
            field = variable.to_s.delete_prefix("@").to_sym
            actual = value.public_send(field)
            type = definition.methods.fetch(field).method_types.first.type.return_type
            assert @checker.value(actual, type), "#{value.class}##{field}: #{actual.class} is not #{type}"
            assert actual.finite? if actual.is_a?(Float)
        end
        assert value.frozen?
    end

    def test_private_record_constructors_and_typed_fields
        check_record(T::Origin.new())
        check_record(T::AbsentValue.new())
        check_record(T::NoValue.new())
        check_record(T::RequiredLink.new(source_model: "", source_field: "", target_model: "", target_field: ""))
        check_record(T::FieldContract.new(member_id: "Client.open", native_type: "", nullable: false))
        check_record(T::FieldContracts.new(model_type: "Client", fields: []))
        check_record(T::StationLookupActive.new(station: inert(::OpenTideConstants::Station)))
        check_record(T::StationLookupRemoved.new(tombstone: inert(::OpenTideConstants::Tombstone)))
        check_record(T::StationLookupAbsent.new())
        check_record(T::PredictionModel.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), convention: inert(::OpenTideConstants::Convention), astro_table: nil, required_constituents: [], reference_bin: 1, mean_term: 0.0, datum_source: nil))
        check_record(T::PredictionWindow.new(start: 0.0, stop: 0.0, step: 0.0, instants: nil))
        check_record(T::ArgsClientOpenSelected.new(member_id: "Client.open", offline: false, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: ""))
        check_record(T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""))
        check_record(T::LockState.new(cache_root: "", owner: nil, held_token: ""))
        check_record(T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")))
        check_record(T::ReleaseDescriptor.new(datestamp: "", files: [], checksum_bytes: "", pointer_digests: {}, required_file_request: nil, metadata: nil))
        check_record(T::ReferencePath.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), own_offset: nil, reference_bin: 1))
        check_record(T::CandidatePathDirect.new(station: inert(::OpenTideConstants::Station), constant_set: inert(::OpenTideConstants::ConstantSet), release_view: inert(::OpenTideConstants::Release)))
        check_record(T::CandidatePathTideOffset.new(reference_path: T::ReferencePath.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), own_offset: nil, reference_bin: 1), own_offset: nil))
        check_record(T::CandidatePathCurrentOffset.new(reference_path: T::ReferencePath.new(station: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), constant_set: inert(::OpenTideConstants::ConstantSet), own_offset: nil, reference_bin: 1), own_current_offset: nil))
        check_record(T::ArgsReleaseHeightsSelected.new(member_id: "Release.heights", datum: "", set_id: "", offset_id: ""))
        check_record(T::ArgsReleaseExtremesSelected.new(member_id: "Release.extremes", datum: "", set_id: "", offset_id: ""))
        check_record(T::ArgsReleaseCurrentsSelected.new(member_id: "Release.currents", bin_number: 1, set_id: ""))
        check_record(T::ArgsReleaseCurrentEventsSelected.new(member_id: "Release.current_events", bin_number: 1, set_id: ""))
        check_record(T::ArgsReleaseStations.new(member_id: "Release.stations"))
        check_record(T::ArgsReleaseIterStations.new(member_id: "Release.iter_stations"))
        check_record(T::ArgsReleaseSearch.new(member_id: "Release.search", name: "", limit: 1, match: :exact))
        check_record(T::ArgsReleaseNear.new(member_id: "Release.near", lat: 0.0, lon: 0.0, radius_km: 0.0, limit: 1))
        check_record(T::ArgsReleaseNearest.new(member_id: "Release.nearest", lat: 0.0, lon: 0.0, max_km: 0.0))
        check_record(T::UnroundedTideEvent.new(root_seconds: 0.0, event_type: "high", height_m: 0.0, reference_order: 1))
        check_record(T::UnroundedCurrentEvent.new(root_seconds: 0.0, event_type: "max_flood", velocity_m_s: 0.0, direction_deg: 0.0, reference_order: 1))
        check_record(T::AuxiliaryValuesRequiresModel.new(station_request: inert(::OpenTideConstants::Station), release_view: inert(::OpenTideConstants::Release), selection_options: T::ArgsReleaseHeightsSelected.new(member_id: "Release.heights", datum: "", set_id: "", offset_id: ""), utc_instant: 0.0))
        check_record(T::AuxiliaryValuesSourceAccess.new(raw_source_value: nil, arguments: nil))
        check_record(T::ResultContext.new(station_id: "", set_id: "", reference_station_id: "", bin_number: 1, datum: "", release_datestamp: "", algorithm: ""))
        check_record(T::AcceptanceDecision.new(accepted: false, mandatory_findings: []))
        check_record(T::ArgsClientReleases.new(member_id: "Client.releases"))
        check_record(T::ArgsClientLatest.new(member_id: "Client.latest"))
        check_record(T::ArgsClientCheckForUpdate.new(member_id: "Client.check_for_update"))
        check_record(T::ArgsClientUpdate.new(member_id: "Client.update"))
        check_record(T::ArgsClientDownload.new(member_id: "Client.download", release: "", to: "", formats: [], overwrite: false))
        check_record(T::ArgsClientVerify.new(member_id: "Client.verify"))
        check_record(T::ArgsClientCachedReleases.new(member_id: "Client.cached_releases"))
        check_record(T::ArgsClientPrune.new(member_id: "Client.prune", keep: 1))
        check_record(T::ArgsClientClose.new(member_id: "Client.close"))
        check_record(T::ArgsReleaseConvention.new(member_id: "Release.convention", convention_id: ""))
        check_record(T::ArgsReleaseLicence.new(member_id: "Release.licence", licence_id: ""))
        check_record(T::ArgsReleaseStation.new(member_id: "Release.station", station_id: ""))
        check_record(T::ArgsReleaseRequireStation.new(member_id: "Release.require_station", station_id: ""))
        check_record(T::ArgsReleaseTombstone.new(member_id: "Release.tombstone", station_id: ""))
        check_record(T::ArgsReleaseStationByAlias.new(member_id: "Release.station_by_alias", system: :noaa, alias_id: ""))
        check_record(T::ArgsReleaseReferenceStation.new(member_id: "Release.reference_station", station: inert(::OpenTideConstants::Station)))
        check_record(T::ArgsReleaseSubordinatesOf.new(member_id: "Release.subordinates_of", station: inert(::OpenTideConstants::Station)))
        check_record(T::ArgsReleaseAttribution.new(member_id: "Release.attribution", stations: []))
        check_record(T::ArgsReleaseHeights.new(member_id: "Release.heights", station: inert(::OpenTideConstants::Station), start: Time.at(0).utc, stop: Time.at(0).utc, step_s: 1, datum: "", set_id: "", offset_id: ""))
        check_record(T::ArgsReleaseHeightsAt.new(member_id: "Release.heights_at", station: inert(::OpenTideConstants::Station), times: [], datum: "", set_id: "", offset_id: ""))
        check_record(T::ArgsReleaseExtremes.new(member_id: "Release.extremes", station: inert(::OpenTideConstants::Station), start: Time.at(0).utc, stop: Time.at(0).utc, datum: "", set_id: "", offset_id: ""))
        check_record(T::ArgsReleaseCurrents.new(member_id: "Release.currents", station: inert(::OpenTideConstants::Station), start: Time.at(0).utc, stop: Time.at(0).utc, step_s: 1, bin_number: 1, set_id: ""))
        check_record(T::ArgsReleaseCurrentEvents.new(member_id: "Release.current_events", station: inert(::OpenTideConstants::Station), start: Time.at(0).utc, stop: Time.at(0).utc, bin_number: 1, set_id: ""))
        check_record(T::ArgsReleaseDatums.new(member_id: "Release.datums", station: inert(::OpenTideConstants::Station), set_id: "", all_sets: false))
        check_record(T::ArgsReleaseRanges.new(member_id: "Release.ranges", station: inert(::OpenTideConstants::Station), set_id: ""))
        check_record(T::ArgsReleaseAstroTable.new(member_id: "Release.astro_table", id: ""))
        check_record(T::ArgsStationConstantSets.new(member_id: "Station.constant_sets", include_no_constants: false))
        check_record(T::ArgsStationConstantSet.new(member_id: "Station.constant_set", set_id: ""))
        check_record(T::ArgsConstantSetConstituent.new(member_id: "ConstantSet.constituent", name: ""))
        check_record(T::ArgsAstroTableEquilibriumArgument.new(member_id: "AstroTable.equilibrium_argument", name: "", at: Time.at(0).utc))
        check_record(T::ArgsAstroTableNodeFactor.new(member_id: "AstroTable.node_factor", name: "", at: Time.at(0).utc))
        check_record(T::ArgsAstroTableEquilibriumForYear.new(member_id: "AstroTable.equilibrium_for_year", name: "", year: 1))
        check_record(T::ArgsAstroTableNodeFactorForYear.new(member_id: "AstroTable.node_factor_for_year", name: "", year: 1))
        check_record(T::ArgsHeightPointLocalDatetime.new(member_id: "HeightPoint.local_datetime"))
        check_record(T::ArgsExtremeLocalDatetime.new(member_id: "Extreme.local_datetime"))
        check_record(T::ArgsCurrentPointLocalDatetime.new(member_id: "CurrentPoint.local_datetime"))
        check_record(T::ArgsCurrentEventLocalDatetime.new(member_id: "CurrentEvent.local_datetime"))
        check_record(T::ArgsHeightSeriesToLocal.new(member_id: "HeightSeries.to_local", tz: ""))
        check_record(T::ArgsExtremeListToLocal.new(member_id: "ExtremeList.to_local", tz: ""))
        check_record(T::ArgsCurrentSeriesToLocal.new(member_id: "CurrentSeries.to_local", tz: ""))
        check_record(T::ArgsCurrentEventListToLocal.new(member_id: "CurrentEventList.to_local", tz: ""))
        check_record(T::AstronomicalTerms.new(utc_year: 1, constituent_terms: [], epoch_hours: 0.0))
        check_record(T::SchemaFallback.new(reason: "", basis: "", otc_finding: "", preferred_set_id: "", source_extensions: {}))
        check_record(T::AuthenticatedIndexStationsItemSetsItem.new(set_id: "", source: "", source_type: "", quantity: "", qc_status: "", convention_id: "", licence_id: "", constituents: [], fallback: T::SchemaFallback.new(reason: "", basis: "", otc_finding: "", preferred_set_id: "", source_extensions: {}), current_bins: []))
        check_record(T::SchemaQcFlag.new(flag: "", reason: "", values: {}, source_extensions: {}))
        check_record(T::SchemaHistoricalOffsetVintageRemovalEventsItem.new(source_clock_timestamp: "", name: "", operation: "Removed", source_timezone: nil, evidence_sha256: "", source_extensions: {}))
        check_record(T::SchemaHistoricalOffsetVintage.new(publication_year: 2020, source_lifecycle: "retired", removal_events: [], current_validity: "unestablished", current_accuracy: "unverified", reference_2020_equivalence: "", reference_2020_equivalence_sha256: "", source_extensions: {}))
        check_record(T::SchemaHistoricalOffsetProvenanceIdCrosswalk.new(legacy_id: "", status: "inferred", modern_alias_verified: false, evidence_sha256: [], source_extensions: {}))
        check_record(T::SchemaHistoricalOffsetProvenanceReferenceBinding.new(noaa_id: "", station_id: "", mapping_status: "primary_name_position", evidence_sha256: [], source_extensions: {}))
        check_record(T::SchemaHistoricalOffsetProvenance.new(source_manifest_sha256: "667eec5b3fd25f99d46f24864766726094961d7db5fa104ca12450f3ecd0fdf7", input_sha256: [], book: "", annual_table_row: 1, printed_page: 1, pdf_page: 1, raw_row_text: "", raw_values_json: "", id_crosswalk: T::SchemaHistoricalOffsetProvenanceIdCrosswalk.new(legacy_id: "", status: "inferred", modern_alias_verified: false, evidence_sha256: [], source_extensions: {}), reference_binding: T::SchemaHistoricalOffsetProvenanceReferenceBinding.new(noaa_id: "", station_id: "", mapping_status: "primary_name_position", evidence_sha256: [], source_extensions: {}), acceptance_report_sha256: "", source_extensions: {}))
        check_record(T::SchemaSubordinateOffsets.new(reference_station_id: "", time_offset_high_min: 0.0, time_offset_low_min: 0.0, height_offset_high: 0.0, height_offset_low: 0.0, height_adjusted_type: "", licence_id: "", datum: {}, offset_id: "", source: "", source_type: "", source_version: "", source_record_id: "", qc_status: "", qc_flags: [], fallback: T::SchemaFallback.new(reason: "", basis: "", otc_finding: "", preferred_set_id: "", source_extensions: {}), vintage: T::SchemaHistoricalOffsetVintage.new(publication_year: 2020, source_lifecycle: "retired", removal_events: [], current_validity: "unestablished", current_accuracy: "unverified", reference_2020_equivalence: "", reference_2020_equivalence_sha256: "", source_extensions: {}), provenance: T::SchemaHistoricalOffsetProvenance.new(source_manifest_sha256: "667eec5b3fd25f99d46f24864766726094961d7db5fa104ca12450f3ecd0fdf7", input_sha256: [], book: "", annual_table_row: 1, printed_page: 1, pdf_page: 1, raw_row_text: "", raw_values_json: "", id_crosswalk: T::SchemaHistoricalOffsetProvenanceIdCrosswalk.new(legacy_id: "", status: "inferred", modern_alias_verified: false, evidence_sha256: [], source_extensions: {}), reference_binding: T::SchemaHistoricalOffsetProvenanceReferenceBinding.new(noaa_id: "", station_id: "", mapping_status: "primary_name_position", evidence_sha256: [], source_extensions: {}), acceptance_report_sha256: "", source_extensions: {}), source_extensions: {}))
        check_record(T::AuthenticatedIndexStationsItemCurrentOffsetsItem.new(bin: 1, reference_bin: 1, reference_station_id: "", licence_id: ""))
        check_record(T::AuthenticatedIndexStationsItem.new(station_id: "", status: "", name: "", name_folded: "", country: "", type: "", kind: "", reference_station_id: "", offsets_licence_id: "", recommended_set_id: "", lat: 0.0, lon: 0.0, offset: 1, length: 1, aliases: {}, sets: [], subordinate_offsets: T::SchemaSubordinateOffsets.new(reference_station_id: "", time_offset_high_min: 0.0, time_offset_low_min: 0.0, height_offset_high: 0.0, height_offset_low: 0.0, height_adjusted_type: "", licence_id: "", datum: {}, offset_id: "", source: "", source_type: "", source_version: "", source_record_id: "", qc_status: "", qc_flags: [], fallback: T::SchemaFallback.new(reason: "", basis: "", otc_finding: "", preferred_set_id: "", source_extensions: {}), vintage: T::SchemaHistoricalOffsetVintage.new(publication_year: 2020, source_lifecycle: "retired", removal_events: [], current_validity: "unestablished", current_accuracy: "unverified", reference_2020_equivalence: "", reference_2020_equivalence_sha256: "", source_extensions: {}), provenance: T::SchemaHistoricalOffsetProvenance.new(source_manifest_sha256: "667eec5b3fd25f99d46f24864766726094961d7db5fa104ca12450f3ecd0fdf7", input_sha256: [], book: "", annual_table_row: 1, printed_page: 1, pdf_page: 1, raw_row_text: "", raw_values_json: "", id_crosswalk: T::SchemaHistoricalOffsetProvenanceIdCrosswalk.new(legacy_id: "", status: "inferred", modern_alias_verified: false, evidence_sha256: [], source_extensions: {}), reference_binding: T::SchemaHistoricalOffsetProvenanceReferenceBinding.new(noaa_id: "", station_id: "", mapping_status: "primary_name_position", evidence_sha256: [], source_extensions: {}), acceptance_report_sha256: "", source_extensions: {}), source_extensions: {}), current_offsets: []))
        check_record(T::AuthenticatedIndex.new(index_version: 1, discovery_index_version: 1, datestamp: "", jsonl: "", jsonl_sha256: "", jsonl_size: 1, by: "", stations: []))
        check_record(T::SelectedResult0.new(member_id: "Client.open", value: inert(::OpenTideConstants)))
        check_record(T::SelectedResult1.new(member_id: "Client.release", value: inert(::OpenTideConstants::Release)))
        check_record(T::SelectedResult2.new(member_id: "Client.loaded_from", value: :download))
        check_record(T::SelectedResult3.new(member_id: "Client.last_error", value: inert(::OpenTideConstants::Error)))
        check_record(T::SelectedResult4.new(member_id: "Client.releases", value: []))
        check_record(T::SelectedResult5.new(member_id: "Client.latest", value: inert(::OpenTideConstants::ReleaseInfo)))
        check_record(T::SelectedResult6.new(member_id: "Client.check_for_update", value: inert(::OpenTideConstants::ReleaseInfo)))
        check_record(T::SelectedResult7.new(member_id: "Client.newer_format_major", value: 1))
        check_record(T::SelectedResult8.new(member_id: "Client.update", value: inert(::OpenTideConstants::UpdateResult)))
        check_record(T::SelectedResult9.new(member_id: "Client.download", value: []))
        check_record(T::SelectedResult10.new(member_id: "Client.verify", value: false))
        check_record(T::SelectedResult11.new(member_id: "Client.close", value: T::NoValue.new()))
        check_record(T::SelectedResult12.new(member_id: "Release.datestamp", value: ""))
        check_record(T::SelectedResult13.new(member_id: "Release.created", value: Time.at(0).utc))
        check_record(T::SelectedResult14.new(member_id: "Release.zenodo_version_doi", value: ""))
        check_record(T::SelectedResult15.new(member_id: "Release.source_versions", value: {}))
        check_record(T::SelectedResult16.new(member_id: "Release.files", value: []))
        check_record(T::SelectedResult17.new(member_id: "Release.conventions", value: []))
        check_record(T::SelectedResult18.new(member_id: "Release.convention", value: inert(::OpenTideConstants::Convention)))
        check_record(T::SelectedResult19.new(member_id: "Release.licences", value: []))
        check_record(T::SelectedResult20.new(member_id: "Release.licence", value: inert(::OpenTideConstants::Licence)))
        check_record(T::SelectedResult21.new(member_id: "Release.stats", value: inert(::OpenTideConstants::Stats)))
        check_record(T::SelectedResult22.new(member_id: "Release.station_count", value: 1))
        check_record(T::SelectedResult23.new(member_id: "Release.station", value: inert(::OpenTideConstants::Station)))
        check_record(T::SelectedResult24.new(member_id: "Release.require_station", value: inert(::OpenTideConstants::Station)))
        check_record(T::SelectedResult25.new(member_id: "Release.tombstone", value: inert(::OpenTideConstants::Tombstone)))
        check_record(T::SelectedResult26.new(member_id: "Release.stations", value: []))
        check_record(T::SelectedResult27.new(member_id: "Release.iter_stations", value: [].each))
        check_record(T::SelectedResult28.new(member_id: "Release.near", value: []))
        check_record(T::SelectedResult29.new(member_id: "Release.nearest", value: inert(::OpenTideConstants::Nearby)))
        check_record(T::SelectedResult30.new(member_id: "Release.heights", value: inert(::OpenTideConstants::HeightSeries)))
        check_record(T::SelectedResult31.new(member_id: "Release.extremes", value: inert(::OpenTideConstants::ExtremeList)))
        check_record(T::SelectedResult32.new(member_id: "Release.currents", value: inert(::OpenTideConstants::CurrentSeries)))
        check_record(T::SelectedResult33.new(member_id: "Release.current_events", value: inert(::OpenTideConstants::CurrentEventList)))
        check_record(T::SelectedResult34.new(member_id: "Release.datums", value: inert(::OpenTideConstants::DatumInfo)))
        check_record(T::SelectedResult35.new(member_id: "Release.ranges", value: inert(::OpenTideConstants::Ranges)))
        check_record(T::SelectedResult36.new(member_id: "Release.astro_table", value: inert(::OpenTideConstants::AstroTable)))
        check_record(T::SelectedResult37.new(member_id: "Station.lat", value: 0.0))
        check_record(T::SelectedResult38.new(member_id: "Station.type", value: :reference))
        check_record(T::SelectedResult39.new(member_id: "Station.kind", value: :tide))
        check_record(T::SelectedResult40.new(member_id: "Station.aliases", value: {}))
        check_record(T::SelectedResult41.new(member_id: "Station.status", value: :active))
        check_record(T::SelectedResult42.new(member_id: "Station.recommended_set", value: inert(::OpenTideConstants::ConstantSet)))
        check_record(T::SelectedResult43.new(member_id: "Station.constant_sets", value: []))
        check_record(T::SelectedResult44.new(member_id: "Station.subordinate_offsets", value: inert(::OpenTideConstants::SubordinateOffsets)))
        check_record(T::SelectedResult45.new(member_id: "Station.validation", value: []))
        check_record(T::SelectedResult46.new(member_id: "Station.raw", value: nil))
        check_record(T::SelectedResult47.new(member_id: "Station.recommended_is_fallback", value: false))
        check_record(T::SelectedResult48.new(member_id: "Station.source_records", value: []))
        check_record(T::SelectedResult49.new(member_id: "Tombstone.removed_reason", value: :merged))
        check_record(T::SelectedResult50.new(member_id: "ConstantSet.source_type", value: :official))
        check_record(T::SelectedResult51.new(member_id: "ConstantSet.quantity", value: :water_level))
        check_record(T::SelectedResult52.new(member_id: "ConstantSet.record_span", value: inert(::OpenTideConstants::RecordSpan)))
        check_record(T::SelectedResult53.new(member_id: "ConstantSet.datum", value: inert(::OpenTideConstants::Datum)))
        check_record(T::SelectedResult54.new(member_id: "ConstantSet.qc_status", value: :ok))
        check_record(T::SelectedResult55.new(member_id: "ConstantSet.qc_flags", value: []))
        check_record(T::SelectedResult56.new(member_id: "ConstantSet.dropped_constituents", value: []))
        check_record(T::SelectedResult57.new(member_id: "ConstantSet.time_base", value: inert(::OpenTideConstants::TimeBase)))
        check_record(T::SelectedResult58.new(member_id: "ConstantSet.convention", value: inert(::OpenTideConstants::Convention)))
        check_record(T::SelectedResult59.new(member_id: "ConstantSet.licence", value: inert(::OpenTideConstants::Licence)))
        check_record(T::SelectedResult60.new(member_id: "ConstantSet.provenance", value: inert(::OpenTideConstants::Provenance)))
        check_record(T::SelectedResult61.new(member_id: "ConstantSet.constituents", value: []))
        check_record(T::SelectedResult62.new(member_id: "ConstantSet.constituent", value: inert(::OpenTideConstants::Constituent)))
        check_record(T::SelectedResult63.new(member_id: "ConstantSet.fallback", value: inert(::OpenTideConstants::Fallback)))
        check_record(T::SelectedResult64.new(member_id: "Constituent.amp_uncertainty_m", value: 0.0))
        check_record(T::SelectedResult65.new(member_id: "Convention.phase_reference", value: :greenwich_utc))
        check_record(T::SelectedResult66.new(member_id: "Convention.nodal_handling", value: :f_u_at_prediction))
        check_record(T::SelectedResult67.new(member_id: "Convention.nodal_formula_ids", value: {}))
        check_record(T::SelectedResult68.new(member_id: "Convention.canary", value: nil))
        check_record(T::SelectedResult69.new(member_id: "Provenance.input_sha256", value: []))
        check_record(T::SelectedResult70.new(member_id: "Provenance.build", value: inert(::OpenTideConstants::ProvenanceBuild)))
        check_record(T::SelectedResult71.new(member_id: "ProvenanceBuild.built_at", value: Time.at(0).utc))
        check_record(T::SelectedResult72.new(member_id: "ProvenanceBuild.tool_versions", value: {}))
        check_record(T::SelectedResult73.new(member_id: "TimeBase.code", value: :verified))
        check_record(T::SelectedResult74.new(member_id: "TimeBase.evidence", value: []))
        check_record(T::SelectedResult75.new(member_id: "QcFlag.flag", value: :time_base))
        check_record(T::SelectedResult76.new(member_id: "QcFlag.values", value: {}))
        check_record(T::SelectedResult77.new(member_id: "DroppedConstituent.dropped_reason", value: :rayleigh))
        check_record(T::SelectedResult78.new(member_id: "SubordinateOffsets.height_adjusted_type", value: :R))
        check_record(T::SelectedResult79.new(member_id: "SubordinateOffsets.source_type", value: :official))
        check_record(T::SelectedResult80.new(member_id: "SubordinateOffsets.qc_status", value: :ok))
        check_record(T::SelectedResult81.new(member_id: "SubordinateOffsets.vintage", value: inert(::OpenTideConstants::HistoricalOffsetVintage)))
        check_record(T::SelectedResult82.new(member_id: "SubordinateOffsets.provenance", value: inert(::OpenTideConstants::HistoricalOffsetProvenance)))
        check_record(T::SelectedResult83.new(member_id: "Datum.named", value: {}))
        check_record(T::SelectedResult84.new(member_id: "Stats.type", value: {}))
        check_record(T::SelectedResult85.new(member_id: "AstroTable.valid_range", value: [1, 1]))
        check_record(T::SelectedResult86.new(member_id: "HeightPoint.time", value: Time.at(0).utc))
        check_record(T::SelectedResult87.new(member_id: "Extreme.type", value: :high))
        check_record(T::SelectedResult88.new(member_id: "CurrentEvent.type", value: :max_flood))
        check_record(T::SelectedResult89.new(member_id: "HeightSeries.items", value: []))
        check_record(T::SelectedResult90.new(member_id: "HeightSeries.method", value: :harmonic))
        check_record(T::SelectedResult91.new(member_id: "ExtremeList.items", value: []))
        check_record(T::SelectedResult92.new(member_id: "CurrentSeries.items", value: []))
        check_record(T::SelectedResult93.new(member_id: "CurrentEventList.items", value: []))
        check_record(T::SelectedResult94.new(member_id: "CurrentEventList.omitted_event_types", value: []))
        check_record(T::SelectedResult95.new(member_id: "DatumInfo.levels", value: []))
        check_record(T::SelectedResult96.new(member_id: "Fallback.reason", value: :time_base_disputed))
        check_record(T::SelectedResult97.new(member_id: "Fallback.raw", value: {}))
        check_record(T::SelectedResult98.new(member_id: "SourceRecord.role", value: :gauge_station))
        check_record(T::SelectedResult99.new(member_id: "SourceRecord.disposition", value: :metadata_only))
        check_record(T::SelectedResult100.new(member_id: "SourceRecord.original_harmonics", value: {}))
        check_record(T::SelectedResult101.new(member_id: "HistoricalOffsetVintage.removal_events", value: []))
        check_record(T::CacheDocumentStreamIndexStationsItemSetsItem.new(set_id: "", source: "", source_type: "", quantity: "", qc_status: "", convention_id: "", licence_id: "", constituents: [], fallback: T::SchemaFallback.new(reason: "", basis: "", otc_finding: "", preferred_set_id: "", source_extensions: {}), current_bins: []))
        check_record(T::CacheDocumentStreamIndexStationsItemCurrentOffsetsItem.new(bin: 1, reference_bin: 1, reference_station_id: "", licence_id: ""))
        check_record(T::CacheDocumentStreamIndexStationsItem.new(station_id: "", status: "", name: "", name_folded: "", country: "", type: "", kind: "", reference_station_id: "", offsets_licence_id: "", recommended_set_id: "", lat: 0.0, lon: 0.0, offset: 1, length: 1, aliases: {}, sets: [], subordinate_offsets: T::SchemaSubordinateOffsets.new(reference_station_id: "", time_offset_high_min: 0.0, time_offset_low_min: 0.0, height_offset_high: 0.0, height_offset_low: 0.0, height_adjusted_type: "", licence_id: "", datum: {}, offset_id: "", source: "", source_type: "", source_version: "", source_record_id: "", qc_status: "", qc_flags: [], fallback: T::SchemaFallback.new(reason: "", basis: "", otc_finding: "", preferred_set_id: "", source_extensions: {}), vintage: T::SchemaHistoricalOffsetVintage.new(publication_year: 2020, source_lifecycle: "retired", removal_events: [], current_validity: "unestablished", current_accuracy: "unverified", reference_2020_equivalence: "", reference_2020_equivalence_sha256: "", source_extensions: {}), provenance: T::SchemaHistoricalOffsetProvenance.new(source_manifest_sha256: "667eec5b3fd25f99d46f24864766726094961d7db5fa104ca12450f3ecd0fdf7", input_sha256: [], book: "", annual_table_row: 1, printed_page: 1, pdf_page: 1, raw_row_text: "", raw_values_json: "", id_crosswalk: T::SchemaHistoricalOffsetProvenanceIdCrosswalk.new(legacy_id: "", status: "inferred", modern_alias_verified: false, evidence_sha256: [], source_extensions: {}), reference_binding: T::SchemaHistoricalOffsetProvenanceReferenceBinding.new(noaa_id: "", station_id: "", mapping_status: "primary_name_position", evidence_sha256: [], source_extensions: {}), acceptance_report_sha256: "", source_extensions: {}), source_extensions: {}), current_offsets: []))
        check_record(T::CacheDocumentStreamIndex.new(index_version: 1, discovery_index_version: 1, datestamp: "", jsonl: "", jsonl_sha256: "", jsonl_size: 1, by: "", stations: []))
        check_record(T::CacheDocumentVerifiedReceiptFilesValue.new(sha256: "", size: 1, url: ""))
        check_record(T::CacheDocumentVerifiedReceipt.new(datestamp: "", files: {}, format_version: "", min_reader_version: "", zenodo_version_doi: "", verified_at: "", by: ""))
        check_record(T::CanonicalError.new(code: "invalid_argument", structured_fields: nil, cause: RuntimeError.new("native construction cause")))
        check_record(T::ClientAndRelease.new(client_state: T::ClientState.new(current_release: inert(::OpenTideConstants::Release), effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), last_error: nil, last_update_check: 0.0, closed: false), loaded_release: inert(::OpenTideConstants::Release)))
        check_record(T::ClientState.new(current_release: inert(::OpenTideConstants::Release), effective_options: T::ArgsClientOpen.new(member_id: "Client.open", release: "", file: "", cache_dir: "", offline: false, mode: :eager, base_url: "", timeout: 0.0, proxy: "", ca_file: "", user_agent: "", on_network_error: :use_cache, auto_update: false, update_interval: 0.0, logger: Logger.new(File::NULL), verify_on_open: false, commercial_only: false, commercial_basis: "", historical_offsets_policy: ""), cache_state: T::CacheState.new(cache_root: "", release_candidates: [], pointer_cache: nil, lock_state: T::LockState.new(cache_root: "", owner: nil, held_token: "")), last_error: nil, last_update_check: 0.0, closed: false))
        check_record(T::CommercialAdmission.new(admitted: false, reason: ""))
        check_record(T::EvidenceBundle.new(scenario: T::Scenario.new(behavior_ids: [], input: nil, expected_output: nil, expected_error: T::CanonicalError.new(code: "invalid_argument", structured_fields: nil, cause: RuntimeError.new("native construction cause")), expected_state: nil), expected_result: nil, actual_profile_results: nil, red_output: "", green_output: ""))
        check_record(T::FormatSelection.new(formats: [], required_files: []))
        check_record(T::HistoricalAdmission.new(admitted: false, reason: ""))
        check_record(T::HttpRequest.new(url: "", conditional_etag: ""))
        check_record(T::HttpResponse.new(status_code: 1, body: "", etag: "", request_url: ""))
        check_record(T::IdentityQuery1.new(system: "", id: ""))
        check_record(T::IndexEntrySetsItem.new(set_id: "", source: "", source_type: "", quantity: "", qc_status: "", convention_id: "", licence_id: "", constituents: [], fallback: T::SchemaFallback.new(reason: "", basis: "", otc_finding: "", preferred_set_id: "", source_extensions: {}), current_bins: []))
        check_record(T::IndexEntryCurrentOffsetsItem.new(bin: 1, reference_bin: 1, reference_station_id: "", licence_id: ""))
        check_record(T::IndexEntry.new(station_id: "", status: "", name: "", name_folded: "", country: "", type: "", kind: "", reference_station_id: "", offsets_licence_id: "", recommended_set_id: "", lat: 0.0, lon: 0.0, offset: 1, length: 1, aliases: {}, sets: [], subordinate_offsets: T::SchemaSubordinateOffsets.new(reference_station_id: "", time_offset_high_min: 0.0, time_offset_low_min: 0.0, height_offset_high: 0.0, height_offset_low: 0.0, height_adjusted_type: "", licence_id: "", datum: {}, offset_id: "", source: "", source_type: "", source_version: "", source_record_id: "", qc_status: "", qc_flags: [], fallback: T::SchemaFallback.new(reason: "", basis: "", otc_finding: "", preferred_set_id: "", source_extensions: {}), vintage: T::SchemaHistoricalOffsetVintage.new(publication_year: 2020, source_lifecycle: "retired", removal_events: [], current_validity: "unestablished", current_accuracy: "unverified", reference_2020_equivalence: "", reference_2020_equivalence_sha256: "", source_extensions: {}), provenance: T::SchemaHistoricalOffsetProvenance.new(source_manifest_sha256: "667eec5b3fd25f99d46f24864766726094961d7db5fa104ca12450f3ecd0fdf7", input_sha256: [], book: "", annual_table_row: 1, printed_page: 1, pdf_page: 1, raw_row_text: "", raw_values_json: "", id_crosswalk: T::SchemaHistoricalOffsetProvenanceIdCrosswalk.new(legacy_id: "", status: "inferred", modern_alias_verified: false, evidence_sha256: [], source_extensions: {}), reference_binding: T::SchemaHistoricalOffsetProvenanceReferenceBinding.new(noaa_id: "", station_id: "", mapping_status: "primary_name_position", evidence_sha256: [], source_extensions: {}), acceptance_report_sha256: "", source_extensions: {}), source_extensions: {}), current_offsets: []))
        check_record(T::LockOutcome.new(acquired: false, token: "", owned: false))
        check_record(T::LockRequest.new(directory: "", operation: "take", token: ""))
        check_record(T::MergedReceiptFilesValue.new(sha256: "", size: 1, url: ""))
        check_record(T::MergedReceipt.new(datestamp: "", files: {}, format_version: "", min_reader_version: "", zenodo_version_doi: "", verified_at: "", by: ""))
        check_record(T::MetadataRequest.new(request_url: "", document_kind: ""))
        check_record(T::ProjectionContract.new(scalar_types: "", models: "", subordinate_offsets: "", scope: "", fallback: ""))
        check_record(T::PublishedMetadata.new(contributors: nil, year: 1, concept_doi: "", zenodo_version_doi: "", dataset_url: ""))
        check_record(T::QualityAdmission.new(admitted: false, reason: ""))
        check_record(T::ReaderVersion.new(major: 1, minor: 1))
        check_record(T::Scenario.new(behavior_ids: [], input: nil, expected_output: nil, expected_error: T::CanonicalError.new(code: "invalid_argument", structured_fields: nil, cause: RuntimeError.new("native construction cause")), expected_state: nil))
        check_record(T::ScenarioComparison.new(accepted: false, mandatory_findings: []))
        check_record(T::SourceByteSpan.new(offset_bytes: 1, length_bytes: 1))
        check_record(T::SourceFiles.new(jsonl: "", meta: "", jsonl_sha256: "", jsonl_size: 1, meta_sha256: "", meta_size: 1))
        check_record(T::StationIndexEntrySetsItem.new(set_id: "", source: "", source_type: "", quantity: "", qc_status: "", convention_id: "", licence_id: "", constituents: [], fallback: T::SchemaFallback.new(reason: "", basis: "", otc_finding: "", preferred_set_id: "", source_extensions: {}), current_bins: []))
        check_record(T::StationIndexEntryCurrentOffsetsItem.new(bin: 1, reference_bin: 1, reference_station_id: "", licence_id: ""))
        check_record(T::StationIndexEntry.new(station_id: "", status: "", name: "", name_folded: "", country: "", type: "", kind: "", reference_station_id: "", offsets_licence_id: "", recommended_set_id: "", lat: 0.0, lon: 0.0, offset: 1, length: 1, aliases: {}, sets: [], subordinate_offsets: T::SchemaSubordinateOffsets.new(reference_station_id: "", time_offset_high_min: 0.0, time_offset_low_min: 0.0, height_offset_high: 0.0, height_offset_low: 0.0, height_adjusted_type: "", licence_id: "", datum: {}, offset_id: "", source: "", source_type: "", source_version: "", source_record_id: "", qc_status: "", qc_flags: [], fallback: T::SchemaFallback.new(reason: "", basis: "", otc_finding: "", preferred_set_id: "", source_extensions: {}), vintage: T::SchemaHistoricalOffsetVintage.new(publication_year: 2020, source_lifecycle: "retired", removal_events: [], current_validity: "unestablished", current_accuracy: "unverified", reference_2020_equivalence: "", reference_2020_equivalence_sha256: "", source_extensions: {}), provenance: T::SchemaHistoricalOffsetProvenance.new(source_manifest_sha256: "667eec5b3fd25f99d46f24864766726094961d7db5fa104ca12450f3ecd0fdf7", input_sha256: [], book: "", annual_table_row: 1, printed_page: 1, pdf_page: 1, raw_row_text: "", raw_values_json: "", id_crosswalk: T::SchemaHistoricalOffsetProvenanceIdCrosswalk.new(legacy_id: "", status: "inferred", modern_alias_verified: false, evidence_sha256: [], source_extensions: {}), reference_binding: T::SchemaHistoricalOffsetProvenanceReferenceBinding.new(noaa_id: "", station_id: "", mapping_status: "primary_name_position", evidence_sha256: [], source_extensions: {}), acceptance_report_sha256: "", source_extensions: {}), source_extensions: {}), current_offsets: []))
        check_record(T::StreamReader.new(release_view: inert(::OpenTideConstants::Release), file_descriptor: 1, index: nil, index_presence: nil, station_lru: nil, closed: false))
        check_record(T::SummaryOptions.new(original_recommendation: inert(::OpenTideConstants::ConstantSet), commercial_only: false, include_no_constants: false))
        check_record(T::SuppliedIndexStationsItemSetsItem.new(set_id: "", source: "", source_type: "", quantity: "", qc_status: "", convention_id: "", licence_id: "", constituents: [], fallback: T::SchemaFallback.new(reason: "", basis: "", otc_finding: "", preferred_set_id: "", source_extensions: {}), current_bins: []))
        check_record(T::SuppliedIndexStationsItemCurrentOffsetsItem.new(bin: 1, reference_bin: 1, reference_station_id: "", licence_id: ""))
        check_record(T::SuppliedIndexStationsItem.new(station_id: "", status: "", name: "", name_folded: "", country: "", type: "", kind: "", reference_station_id: "", offsets_licence_id: "", recommended_set_id: "", lat: 0.0, lon: 0.0, offset: 1, length: 1, aliases: {}, sets: [], subordinate_offsets: T::SchemaSubordinateOffsets.new(reference_station_id: "", time_offset_high_min: 0.0, time_offset_low_min: 0.0, height_offset_high: 0.0, height_offset_low: 0.0, height_adjusted_type: "", licence_id: "", datum: {}, offset_id: "", source: "", source_type: "", source_version: "", source_record_id: "", qc_status: "", qc_flags: [], fallback: T::SchemaFallback.new(reason: "", basis: "", otc_finding: "", preferred_set_id: "", source_extensions: {}), vintage: T::SchemaHistoricalOffsetVintage.new(publication_year: 2020, source_lifecycle: "retired", removal_events: [], current_validity: "unestablished", current_accuracy: "unverified", reference_2020_equivalence: "", reference_2020_equivalence_sha256: "", source_extensions: {}), provenance: T::SchemaHistoricalOffsetProvenance.new(source_manifest_sha256: "667eec5b3fd25f99d46f24864766726094961d7db5fa104ca12450f3ecd0fdf7", input_sha256: [], book: "", annual_table_row: 1, printed_page: 1, pdf_page: 1, raw_row_text: "", raw_values_json: "", id_crosswalk: T::SchemaHistoricalOffsetProvenanceIdCrosswalk.new(legacy_id: "", status: "inferred", modern_alias_verified: false, evidence_sha256: [], source_extensions: {}), reference_binding: T::SchemaHistoricalOffsetProvenanceReferenceBinding.new(noaa_id: "", station_id: "", mapping_status: "primary_name_position", evidence_sha256: [], source_extensions: {}), acceptance_report_sha256: "", source_extensions: {}), source_extensions: {}), current_offsets: []))
        check_record(T::SuppliedIndex.new(index_version: 1, discovery_index_version: 1, datestamp: "", jsonl: "", jsonl_sha256: "", jsonl_size: 1, by: "", stations: []))
        check_record(T::TrustedCachedPointer.new(digests: {}))
        check_record(T::ValidatedMetadata.new(document: nil, selected_datestamp: "", request_url: "", files: []))
    end

    Minitest.after_run do
        directory = File.join(ROOT, "ruby/dist/canonical-shape")
        FileUtils.mkdir_p(directory)
        # Some recorded values are binary (ASCII-8BIT) strings of UTF-8 bytes. The json gem in Ruby 3.0 refuses
        # to generate those, and newer ones warn, so they are written as the UTF-8 text they hold.
        text = lambda do |value|
            case value
            when Hash then value.to_h { |key, item| [text.call(key), text.call(item)] }
            when Array then value.map { |item| text.call(item) }
            when String
                next value unless value.encoding == Encoding::BINARY
                utf8 = value.dup.force_encoding(Encoding::UTF_8)
                utf8.valid_encoding? ? utf8 : "hex:#{value.unpack1('H*')}"
            else value
            end
        end
        File.write(File.join(directory, "invocations.json"), JSON.pretty_generate(text.call(EVENTS.sort_by { |event| event.fetch("id") })) + "\n")
        puts "ACTUAL_NATIVE_INVOCATIONS runtime=#{EVENTS.count { |event| !event.fetch('id').include?('.S') }} actions=#{EVENTS.count { |event| event.fetch('id').include?('.S') }}"
    end
end

# These consumers exercise the installed source and actual owned files. They
# deliberately share the existing native fixtures and socket/cache helpers.
class CanonicalSourceNativeTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants
    T = OTC.const_get(:CanonicalTypes, false)
    C = OTC.const_get(:Canonical, false)
    D = "20991231.2".freeze

    def setup
        @canonical = C.new
        @clients = []
        @releases = []
    end

    def teardown
        @clients.each(&:close)
        @releases.each { |release| release.__send__(:close) }
        super
    end

    def native_client(mode: :eager, cached: false)
        client = if cached
            server = serve
            cache_root = tmpdir
            OTC.new(release: D, base_url: server.url("/"), cache_dir: cache_root, mode: mode).close
            OTC.new(release: D, cache_dir: cache_root, mode: mode, offline: true)
        else
            OTC.new(file: fixture("good", "OTC_#{D}.#{mode == :stream ? 'jsonl' : 'json'}"), mode: mode)
        end
        @clients << client
        client
    end

    def reader_version
        major, minor = OTC::SUPPORTED_FORMAT_VERSION.split(".").map(&:to_i)
        T::ReaderVersion.new(major: major, minor: minor)
    end

    def call_native(id, method, **arguments)
        value = @canonical.__send__(method, **arguments)
        puts "M2_NATIVE #{id} #{value.class}"
        value
    rescue C::Unimplemented => error
        puts "M2_NATIVE_RED #{id} #{error.message}"
        raise
    end

    def native_phase_trace
        calls = []
        trace = TracePoint.new(:call) do |point|
            next unless point.path.include?("/opentideconstants/")
            calls << point.method_id if %i[decode_release_document compare_station_source enforce_resource_lifetime materialize project_station_index write_stream_index drop_stream_index].include?(point.method_id)
        end
        trace.enable
        result = yield
        [result, calls]
    ensure
        trace&.disable
    end

    def same_native_error(expected, actual)
        assert_equal expected.class, actual.class
        assert_equal expected.code, actual.code
        assert_equal expected.message, actual.message
        %i[file expected actual path].each do |field|
            next unless expected.respond_to?(field)
            value = expected.public_send(field)
            value.nil? ? assert_nil(actual.public_send(field)) : assert_equal(value, actual.public_send(field))
        end
    end

    def test_m2_B05_native_release_decode
        bytes = File.binread(fixture("good", "OTC_#{D}.json"))
        document = call_native("B05", :decode_release_document, source_bytes: bytes, reader_version: reader_version, document_kind: "release")
        assert_equal OTC::Reader.parse_json(bytes.force_encoding(Encoding::UTF_8)), document
    end

    def test_m2_B06_native_release_links
        document = OTC::Reader.parse_json(File.read(fixture("good", "OTC_#{D}.json")))
        graph = call_native("B06", :validate_release_links, parsed_document: document, required_links: [])
        assert_same document, graph
    end

    def test_m2_B06_returns_the_actual_validated_source_graph
        document = OTC::Reader.parse_json(File.read(fixture("good", "OTC_#{D}.json")))
        result = @canonical.__send__(:validate_release_links, parsed_document: document, required_links: [])
        @releases << result if result.is_a?(OTC::Release)
        assert_same document, result
    end

    def test_m2_B06_native_identity_and_link_error_matrix
        cases = %w[duplicate-station-id tombstone-twice duplicate-alias duplicate-set-id set-id-across-stations duplicate-convention-id duplicate-licence-id constituent-name-twice unresolved-convention unresolved-licence unresolved-recommended unresolved-reference-station unresolved-offsets-licence]
        cases.each do |name|
            path = fixture("bad/#{name}", "OTC_20991231.json")
            document = OTC::Reader.parse_json(File.read(path))
            expected = assert_raises(OTC::InvalidReleaseError) { OTC::Reader.eager_from_doc(document, files: [], checks: {}) }
            actual = assert_raises(OTC::InvalidReleaseError) { @canonical.__send__(:validate_release_links, parsed_document: document, required_links: []) }
            same_native_error(expected, actual)
        end
        document = OTC::Reader.parse_json(File.read(fixture("good", "OTC_#{D}.json")))
        row = document.fetch("stations").first
        row["current_offsets"] = [{ "reference_station_id" => "absent", "reference_bin" => 1, "bin" => 1 }]
        native = OTC::Reader.eager_from_doc(document, files: [], checks: {})
        graph = @canonical.__send__(:validate_release_links, parsed_document: document, required_links: [])
        @releases << native
        assert_equal native.require_station(row.fetch("station_id")).raw, graph.fetch("stations").find { |station| station["station_id"] == row["station_id"] }
    end

    def test_m2_B08_native_raw_access
        release = native_client.release
        station = release.require_station("OTC-T-0001")
        result = call_native("B08", :access_raw_record, access_kind: "raw_record", source_record: station.raw, station: station, release_origin: release, native_profile: "ruby")
        assert_same station.raw, result
        assert result.frozen?
    end

    def test_m2_B08_origin_native_same_release
        release = native_client.release
        station = release.require_station("OTC-T-0001")
        assert_same station, call_native("B08.origin", :check_station_origin, station: station, release_origin: release)
    end

    def test_m2_B08_native_station_dispatch
        release = native_client.release
        station = release.require_station("OTC-T-0001")
        assert_same station, call_native("B08", :access_raw_record, access_kind: "station_object", source_record: station.raw, station: station, release_origin: release, native_profile: "ruby")
    end

    def test_m2_B15_native_owned_lifetime
        client = native_client(mode: :stream)
        io = client.release.instance_variable_get(:@io)
        assert_same client, call_native("B15", :enforce_resource_lifetime, resource_state: client, lifetime_action: "close")
        assert io.closed?
        assert_raises(OTC::FileError) { client.require_station("OTC-T-0001") }
    end

    def test_m2_B16_native_checksum_manifest
        path = fixture("good", "OTC_#{D}.sha256")
        bytes = File.binread(path)
        rows = call_native("B16", :bind_checksum_manifest, checksum_bytes: bytes, pointer_digests: {}, required_files: [fixture("good", "OTC_#{D}.jsonl"), fixture("good", "OTC_#{D}.meta.json")])
        assert_equal OTC::Reader.parse_sha256(bytes), rows
    end

    def test_m2_B20_native_file_verification
        client = native_client
        assert_equal true, call_native("B20", :verify_release_files, release_files: client, trusted_cached_pointer: T::TrustedCachedPointer.new(digests: {}))
        assert_equal true, client.verify
    end

    def test_m2_B20_malformed_sidecar_keeps_native_filename_error
        directory = tmpdir
        FileUtils.cp_r(Dir[File.join(FIXTURES, "good", "*")], directory)
        client = OTC.new(file: File.join(directory, "OTC_#{D}.json"))
        @clients << client
        File.binwrite(File.join(directory, "OTC_#{D}.sha256"), "bad row\n")
        expected = assert_raises(OTC::InvalidReleaseError) { client.verify }
        actual = assert_raises(OTC::InvalidReleaseError) { @canonical.__send__(:verify_release_files, release_files: client, trusted_cached_pointer: T::TrustedCachedPointer.new(digests: {})) }
        assert_equal expected.message, actual.message
    end

    def test_m2_B20_actual_tamper_missing_and_cached_pointer_fail_before_healing
        client = native_client(mode: :stream, cached: true)
        directory = client.__send__(:cache).release_dir(D)
        path = File.join(directory, "OTC_#{D}.jsonl")
        original = File.binread(path)
        changed = original.sub('"country":"USA"', '"country":"ZZZ"')
        refute_equal original, changed
        File.binwrite(path, changed)
        request_count = @servers.sum { |server| server.requests.size }
        expected = assert_raises(OTC::ChecksumError) { client.verify }
        actual = assert_raises(OTC::ChecksumError) { @canonical.__send__(:verify_release_files, release_files: client, trusted_cached_pointer: T::TrustedCachedPointer.new(digests: {})) }
        same_native_error(expected, actual)
        assert_equal changed, File.binread(path)
        assert_equal request_count, @servers.sum { |server| server.requests.size }
        File.binwrite(path, original)
        sums = File.join(directory, "OTC_#{D}.sha256")
        pointer = JSON.parse(File.read(fixture("good", "OTC_latest-f1.json")))
        client.__send__(:cache).write_pointer("OTC_latest-f1.json", JSON.generate(pointer), nil)
        File.open(sums, "ab") { |file| file.write("\n") }
        expected = assert_raises(OTC::ChecksumError) { client.verify }
        actual = assert_raises(OTC::ChecksumError) { @canonical.__send__(:verify_release_files, release_files: client, trusted_cached_pointer: T::TrustedCachedPointer.new(digests: {})) }
        same_native_error(expected, actual)
        assert File.file?(sums)
        File.unlink(sums)
        expected = assert_raises(OTC::ChecksumError) { client.verify }
        actual = assert_raises(OTC::ChecksumError) { @canonical.__send__(:verify_release_files, release_files: client, trusted_cached_pointer: T::TrustedCachedPointer.new(digests: {})) }
        same_native_error(expected, actual)
        assert_equal request_count, @servers.sum { |server| server.requests.size }
        File.binwrite(sums, File.binread(fixture("good", "OTC_#{D}.sha256")))
        # Windows cannot remove a file that the open stream client keeps open.
        skip "Windows cannot remove the file that the stream client keeps open" if Gem.win_platform?
        File.unlink(path)
        expected = assert_raises(OTC::FileError) { client.verify }
        actual = assert_raises(OTC::FileError) { @canonical.__send__(:verify_release_files, release_files: client, trusted_cached_pointer: T::TrustedCachedPointer.new(digests: {})) }
        same_native_error(expected, actual)
        assert_equal request_count, @servers.sum { |server| server.requests.size }
    end

    def test_m2_B25_native_authenticated_index
        client = native_client(mode: :stream, cached: true)
        path = File.join(client.__send__(:cache).release_dir(D), "index-v1.json")
        doc = JSON.parse(File.read(path))
        result = call_native("B25", :authenticate_station_index, source_files: client, supplied_index: doc, index_presence: doc.to_h { |key, _| [key, true] }, reader_version: reader_version)
        @releases << result.native_context
        assert_equal client.release.station_count, result.native_context.station_count
        assert_equal doc, JSON.parse(File.read(path))
    end

    def test_m2_B25_returns_actual_authenticated_index_fields_and_owner
        client = native_client(mode: :stream, cached: true)
        path = File.join(client.__send__(:cache).release_dir(D), "index-v1.json")
        document = JSON.parse(File.read(path))
        result = authenticated_native_index(client)
        assert_respond_to result, :jsonl_sha256
        assert_equal document.fetch("jsonl_sha256"), result.jsonl_sha256
        assert_equal document.fetch("stations"), result.stations
        assert_equal document, result.source_document
        assert_instance_of OTC::Release, result.native_context
    end

    def test_m2_B25_actual_legacy_presence_and_unknown_fields_are_retained
        client = native_client(mode: :stream, cached: true)
        path = File.join(client.__send__(:cache).release_dir(D), "index-v1.json")
        original = JSON.parse(File.read(path))
        [false, true].each do |sparse|
            document = Marshal.load(Marshal.dump(original))
            document.delete("discovery_index_version")
            document.delete("by")
            document["unknown"] = { "ordered" => [false, nil, "e\u0301", { "z" => 2, "a" => 1 }] }
            document["stations"].each do |row|
                row["sets"].each do |set|
                    set.delete("fallback") if sparse && set["fallback"].nil?
                    set.delete("current_bins") if sparse
                end
                row.delete("subordinate_offsets") if sparse && row["subordinate_offsets"].nil?
                row.delete("current_offsets") if sparse && row["current_offsets"].empty?
            end
            File.binwrite(path, JSON.generate(document))
            before = File.binread(path)
            result, calls = native_phase_trace { authenticated_native_index(client) }
            assert_equal before, File.binread(path)
            assert_equal document, result.source_document
            assert_same T::ABSENT, result.discovery_index_version
            assert_same T::ABSENT, result.by
            refute_includes calls, :project_station_index
            assert_equal client.release.require_station("OTC-T-0001").raw, result.native_context.require_station("OTC-T-0001").raw
            assert result.source_document.frozen?
        end
    end

    def authenticated_native_index(client)
        path = File.join(client.__send__(:cache).release_dir(D), "index-v1.json")
        document = File.file?(path) ? JSON.parse(File.read(path)) : nil
        presence = document.is_a?(Hash) ? document.to_h { |key, _| [key, true] } : {}
        result = @canonical.__send__(:authenticate_station_index, source_files: client, supplied_index: document, index_presence: presence, reader_version: reader_version)
        @releases << result.native_context
        result
    end

    def test_m2_B25_stale_index_rebuilds_native_source_once
        client = native_client(mode: :stream, cached: true)
        path = File.join(client.__send__(:cache).release_dir(D), "index-v1.json")
        original = JSON.parse(File.read(path))
        invalid = Marshal.load(Marshal.dump(original))
        invalid["discovery_index_version"] = 2
        File.binwrite(path, JSON.generate(invalid))
        result = authenticated_native_index(client)
        assert_equal original, JSON.parse(File.read(path))
        assert_equal client.release.station_count, result.native_context.station_count
    end

    def test_m2_B25_valid_stale_absent_and_index_fault_ordered_effects
        client = native_client(mode: :stream, cached: true)
        path = File.join(client.__send__(:cache).release_dir(D), "index-v1.json")
        original = File.binread(path)
        before = File.stat(path).ino
        result, calls = native_phase_trace { authenticated_native_index(client) }
        assert_equal before, File.stat(path).ino
        refute_includes calls, :project_station_index
        refute_includes calls, :write_stream_index
        refute_includes calls, :drop_stream_index
        assert_empty result.native_context.instance_variable_get(:@station_cache)
        mutations = [
            ->(index) { index["discovery_index_version"] = nil },
            ->(index) { index["stations"].first["offset"] = -1 },
            ->(index) { index["stations"].reject! { |row| row["station_id"] == "OTC-T-0011" } },
            ->(index) { index["stations"].first["kind"] = "current" }
        ]
        source_rows = File.readlines(File.join(client.__send__(:cache).release_dir(D), "OTC_#{D}.jsonl")).count { |line| !OTC::Reader.blank?(line) }
        mutations.each do |mutate|
            index = JSON.parse(original.dup) # an older json gem re-tags the string it parses as UTF-8
            mutate.call(index)
            File.binwrite(path, JSON.generate(index))
            _result, calls = native_phase_trace { authenticated_native_index(client) }
            assert_equal 1, calls.count(:drop_stream_index)
            assert_equal source_rows, calls.count(:project_station_index)
            assert_equal 1, calls.count(:write_stream_index)
            assert_operator calls.index(:drop_stream_index), :<, calls.index(:project_station_index)
            assert_operator calls.rindex(:project_station_index), :<, calls.index(:write_stream_index)
            assert_equal original, File.binread(path)
        end
        File.unlink(path)
        _result, calls = native_phase_trace { authenticated_native_index(client) }
        assert_equal 0, calls.count(:drop_stream_index)
        assert_equal source_rows, calls.count(:project_station_index)
        assert_equal original, File.binread(path)
    end

    def test_m2_B25_authentication_failure_precedes_index_read_or_delete
        client = native_client(mode: :stream, cached: true)
        directory = client.__send__(:cache).release_dir(D)
        index_path = File.join(directory, "index-v1.json")
        index_bytes = File.binread(index_path)
        %w[jsonl meta.json].each do |extension|
            path = File.join(directory, "OTC_#{D}.#{extension}")
            original = File.binread(path)
            File.binwrite(path, "X" + original.byteslice(1..))
            _result, calls = native_phase_trace do
                assert_raises(OTC::ChecksumError) { authenticated_native_index(client) }
            end
            refute_includes calls, :drop_stream_index
            refute_includes calls, :project_station_index
            assert_equal index_bytes, File.binread(index_path)
            File.binwrite(path, original)
        end
    end

    def test_m2_B26_native_source_comparison
        client = native_client(mode: :stream, cached: true)
        release = client.release
        station = release.require_station("OTC-T-0001")
        entry = release.instance_variable_get(:@by_id).fetch(station.station_id)
        assert_same station.raw, call_native("B26", :compare_station_source, index_entry: entry, station_source_row: station.raw, index_presence: release)
    end

    def test_m2_B27_native_lazy_read
        release = native_client(mode: :stream).release
        assert_empty release.instance_variable_get(:@station_cache)
        row = call_native("B27", :read_station_lazily, stream_reader: release, station_id: "OTC-T-0001", release_origin: release, reader_version: reader_version)
        assert_equal "OTC-T-0001", row.fetch("station_id")
        assert_same row, release.require_station("OTC-T-0001").raw
        assert_equal 1, release.instance_variable_get(:@station_cache).size
    end

    def test_m2_B27_closed_borrowed_reader_checks_lifetime_first
        release = native_client(mode: :stream).release
        io = release.instance_variable_get(:@io)
        reader = T::StreamReader.new(release_view: release, file_descriptor: io.fileno, index: nil, index_presence: nil, station_lru: release.instance_variable_get(:@station_cache), closed: false)
        release.__send__(:close)
        error = assert_raises(OTC::FileError) { @canonical.__send__(:read_station_lazily, stream_reader: reader, station_id: "OTC-T-0001", release_origin: release, reader_version: reader_version) }
        assert_equal "io", error.code
        assert_equal io.path, error.path
    end

    def test_m2_B27_nonobject_row_keeps_native_first_error
        client = native_client(mode: :stream, cached: true)
        release = client.release
        entry = release.instance_variable_get(:@by_id).fetch("OTC-T-0001")
        io = release.instance_variable_get(:@io)
        File.open(io.path, "r+b") do |file|
            file.seek(entry.pos)
            file.write("null" + " " * (entry.len - 4))
        end
        expected = assert_raises(OTC::InvalidReleaseError) { release.require_station(entry.station_id) }
        actual = assert_raises(OTC::InvalidReleaseError) { @canonical.__send__(:read_station_lazily, stream_reader: release, station_id: entry.station_id, release_origin: release, reader_version: reader_version) }
        assert_equal expected.message, actual.message
    end

    def test_m2_B26_B27_lazy_presence_mismatch_and_exact_cache_actions
        client = native_client(mode: :stream, cached: true)
        release = client.release
        arguments = { stream_reader: release, station_id: "OTC-T-0001", release_origin: release, reader_version: reader_version }
        first, calls = native_phase_trace { @canonical.__send__(:read_station_lazily, **arguments) }
        assert_operator calls.index(:enforce_resource_lifetime), :<, calls.index(:decode_release_document)
        assert_operator calls.index(:decode_release_document), :<, calls.index(:compare_station_source)
        assert_equal 1, calls.count(:decode_release_document)
        assert_equal 1, calls.count(:compare_station_source)
        again, calls = native_phase_trace { @canonical.__send__(:read_station_lazily, **arguments) }
        assert_same first, again
        refute_includes calls, :decode_release_document
        refute_includes calls, :compare_station_source
        entry = release.instance_variable_get(:@by_id).fetch("OTC-T-0001")
        tampered = Marshal.load(Marshal.dump(first))
        tampered["country"] = "ZZ"
        expected = assert_raises(OTC::InvalidReleaseError) { release.__send__(:check_line!, tampered, entry) }
        actual = assert_raises(OTC::InvalidReleaseError) { @canonical.__send__(:compare_station_source, index_entry: entry, station_source_row: tampered, index_presence: release) }
        same_native_error(expected, actual)
        refute File.file?(File.join(client.__send__(:cache).release_dir(D), "index-v1.json"))
        assert_equal 1, release.instance_variable_get(:@station_cache).size
    end

    def test_m2_B08_B27_real_native_lru_eviction_preserves_token_and_raw
        path = release_file("jsonl") do |document|
            original = document.fetch("stations").first
            document["stations"] = 257.times.map do |index|
                row = Marshal.load(Marshal.dump(original))
                row["station_id"] = "LRU-#{index}"
                row["aliases"] = {}
                row["constant_sets"].each { |set| set["set_id"] = "LRU-#{index}/#{set.fetch('source')}" }
                row["recommended_set_id"] = row["constant_sets"].first.fetch("set_id")
                row
            end
        end
        client = OTC.new(file: path, mode: :stream)
        @clients << client
        release = client.release
        first = release.require_station("LRU-0")
        (1..256).each { |index| @canonical.__send__(:read_station_lazily, stream_reader: release, station_id: "LRU-#{index}", release_origin: release, reader_version: reader_version) }
        cache = release.instance_variable_get(:@station_cache)
        assert_equal 256, cache.size
        refute cache.key?("LRU-0")
        raw = @canonical.__send__(:read_station_lazily, stream_reader: release, station_id: "LRU-0", release_origin: release, reader_version: reader_version)
        again = release.require_station("LRU-0")
        refute_same first, again
        assert_equal first.raw, raw
        assert_same first.instance_variable_get(:@origin), again.instance_variable_get(:@origin)
        assert_same first, @canonical.__send__(:check_station_origin, station: first, release_origin: release)
        assert_same again, @canonical.__send__(:check_station_origin, station: again, release_origin: release)
        client.close
        assert_empty cache
        assert_equal first.raw, raw
    end

    def test_m2_B05_native_decode_errors_and_document_kinds
        release = native_client.release
        row = release.require_station("OTC-T-0001").raw
        decoded = call_native("B05", :decode_release_document, source_bytes: JSON.generate(row).b, reader_version: reader_version, document_kind: "station_row")
        assert_equal row, decoded
        cases = ["\xff".b, '{"format_version":', '{"format_version":"99.0"}', '{"format_version":"1.0","release":{"min_reader_version":"99.0"}}']
        cases.each do |bytes|
            expected = begin
                doc = OTC::Reader.parse_json(bytes.dup.force_encoding(Encoding::UTF_8))
                OTC::Release.check_format!(doc)
            rescue OTC::Error => error
                error
            end
            actual = assert_raises(expected.class) { @canonical.__send__(:decode_release_document, source_bytes: bytes.b, reader_version: reader_version, document_kind: "release") }
            assert_equal expected.code, actual.code
            assert_equal expected.message, actual.message
        end
        pointer = { "datestamp" => D, "files" => [] }
        assert_equal pointer, @canonical.__send__(:decode_release_document, source_bytes: JSON.generate(pointer).b, reader_version: reader_version, document_kind: "pointer")
        catalogue = { "releases" => [pointer] }
        assert_equal catalogue, @canonical.__send__(:decode_release_document, source_bytes: JSON.generate(catalogue).b, reader_version: reader_version, document_kind: "catalogue")
        cache = '{"unknown":[1,null,"e\\u0301"],"duplicate":1,"duplicate":2}'
        assert_equal OTC::Reader.parse_json(cache), @canonical.__send__(:decode_release_document, source_bytes: cache.b, reader_version: reader_version, document_kind: "cache")
    end

    def test_m2_B08_foreign_release_and_raw_provenance
        first, second = native_client.release, native_client.release
        station = first.require_station("OTC-T-0001")
        foreign = second.require_station(station.station_id)
        assert_equal first.datestamp, second.datestamp
        assert_equal station.raw, foreign.raw
        error = assert_raises(OTC::InvalidArgumentError) { @canonical.__send__(:check_station_origin, station: foreign, release_origin: first) }
        assert_equal "invalid_argument", error.code
        raw = station.raw.fetch("constant_sets").first
        assert_same raw, @canonical.__send__(:access_raw_record, access_kind: "raw_record", source_record: raw, station: station, release_origin: first, native_profile: "ruby")
        assert_same station, @canonical.__send__(:check_station_origin, station: station, release_origin: first)
        first.__send__(:close)
        assert_equal station.raw, @canonical.__send__(:access_raw_record, access_kind: "raw_record", source_record: station.raw, station: station, release_origin: first, native_profile: "ruby")
    end

    def retained_native_station
        client = OTC.new(file: fixture("good", "OTC_#{D}.json"))
        station = client.release.require_station("OTC-T-0001")
        reference = WeakRef.new(client.release)
        client.close
        client = nil
        [station, reference]
    end

    def test_m2_B08_origin_retained_station_has_lightweight_token
        # A completed native thread releases its conservative VM stack roots.
        # The only retained values are the Station and the actual WeakRef.
        station, release_reference = Thread.new { retained_native_station }.value
        3.times { GC.start(full_mark: true, immediate_sweep: true) }
        refute release_reference.weakref_alive?, "retained Station keeps its entire producing Release alive"
        assert_equal "OTC-T-0001", station.station_id
        assert station.raw.frozen?
    end

    def test_m2_B15_closed_query_retained_metadata_and_idempotent_close
        client = native_client(mode: :stream)
        release = client.release
        station = release.require_station("OTC-T-0001")
        iterator = release.iter_stations
        iterator.next
        original_raw = station.raw
        @canonical.__send__(:enforce_resource_lifetime, resource_state: client, lifetime_action: "close")
        assert_empty release.instance_variable_get(:@station_cache)
        assert_same release, @canonical.__send__(:enforce_resource_lifetime, resource_state: release, lifetime_action: "release_metadata")
        assert_same original_raw, station.raw
        assert_equal D, release.datestamp
        assert_raises(OTC::FileError) { @canonical.__send__(:enforce_resource_lifetime, resource_state: release, lifetime_action: "station_read") }
        assert_raises(OTC::FileError) { iterator.next }
        assert_same client, @canonical.__send__(:enforce_resource_lifetime, resource_state: client, lifetime_action: "close")
    end

    def test_m2_B16_real_manifest_binding_and_controlled_faults
        bytes = File.binread(fixture("good", "OTC_#{D}.sha256"))
        parsed = OTC::Reader.parse_sha256(bytes)
        source_pointer = JSON.parse(File.read(fixture("good", "OTC_latest-f1.json")))
        pointer = source_pointer.fetch("files").to_h { |file| [file.fetch("name"), file.fetch("sha256")] }
        required = [fixture("good", "OTC_#{D}.jsonl"), fixture("good", "OTC_#{D}.meta.json")]
        assert_equal parsed, @canonical.__send__(:bind_checksum_manifest, checksum_bytes: bytes, pointer_digests: pointer, required_files: required)
        duplicates = bytes + bytes.lines.first
        assert_raises(OTC::InvalidReleaseError) { @canonical.__send__(:bind_checksum_manifest, checksum_bytes: duplicates, pointer_digests: {}, required_files: required) }
        missing = bytes.lines.reject { |line| line.end_with?("  OTC_#{D}.meta.json\n") }.join
        error = assert_raises(OTC::ChecksumError) { @canonical.__send__(:bind_checksum_manifest, checksum_bytes: missing, pointer_digests: {}, required_files: required) }
        assert_equal required.last, error.file
        assert_nil error.expected
        mismatch = pointer.merge("OTC_#{D}.sha256" => "0" * 64)
        assert_raises(OTC::ChecksumError) { @canonical.__send__(:bind_checksum_manifest, checksum_bytes: bytes, pointer_digests: mismatch, required_files: required) }
        mismatch = parsed.merge("OTC_#{D}.jsonl" => "0" * 64)
        error = assert_raises(OTC::ChecksumError) { @canonical.__send__(:bind_checksum_manifest, checksum_bytes: bytes, pointer_digests: mismatch, required_files: required) }
        assert_equal "OTC_#{D}.jsonl", error.file
        assert_equal "0" * 64, error.expected
    end
end
