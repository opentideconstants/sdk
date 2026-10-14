require_relative '../opentideconstants'
require_relative 'canonical_types'

class OpenTideConstants
    # Every unfinished seam refuses before acquisition or mathematical decisions.
    class Canonical
        include OpenTideConstants.const_get(:ConstructorArguments, false)
        include OpenTideConstants::Release.const_get(:QueryArguments, false)
        class Unimplemented < StandardError
            attr_reader :behavior_id

            def initialize(behavior_id)
                @behavior_id = behavior_id.freeze
                super("Private canonical construction only: #{behavior_id} body is unimplemented")
            end
        end

        private

        def prepare_member_validation_context(arguments:, native_receiver:)
            fields = { member_id: arguments.member_id, native_profile: "ruby", native_receiver: native_receiver, prepared_receiver: native_receiver }
            validate_native_receiver(arguments, CanonicalTypes::MemberValidationContext.new(**fields))
            if %w[Release.heights Release.heights_at Release.extremes Release.currents Release.current_events Release.datums Release.ranges].include?(arguments.member_id)
                native_receiver.__send__(:check_open!)
                validate_prediction_times(arguments)
                fields[:prepared_station] = Predict.station_for(native_receiver, arguments.station)
                fields[:prepared_station_request] = arguments.station
            elsif arguments.member_id.start_with?("AstroTable.")
                Predict.instant(arguments.at) if arguments.member_id == "AstroTable.equilibrium_argument"
                fields[:prepared_row] = native_receiver.__send__(:row_for, arguments.name)
                fields[:prepared_row_name] = arguments.name
            elsif arguments.member_id == "Release.attribution"
                stations = argument_value(arguments, :stations, nil)
                if stations.is_a?(Array)
                    fields[:prepared_attribution_request] = stations
                    fields[:prepared_attribution_steps] = []
                    stations.each do |station|
                        break unless station.is_a?(Station)
                        begin
                            entry = native_receiver.__send__(:validate_attribution_station_owner, station)
                            fields[:prepared_attribution_steps] << CanonicalTypes::PreparedAttributionStep.new(station: station, entry: entry, error: nil)
                        rescue Error => error
                            fields[:prepared_attribution_steps] << CanonicalTypes::PreparedAttributionStep.new(station: station, entry: nil, error: error)
                            break
                        end
                    end
                end
            end
            CanonicalTypes::MemberValidationContext.new(**fields)
        end

        def validate_native_receiver(arguments, context)
            guarded_client = %w[Client.releases Client.latest Client.check_for_update Client.update Client.download Client.verify Client.cached_releases Client.prune].include?(arguments.member_id)
            guarded_release = arguments.member_id.start_with?("Release.")
            return unless guarded_client || guarded_release
            expected = guarded_client ? OpenTideConstants : Release
            unless context.is_a?(CanonicalTypes::MemberValidationContext) && context.native_profile == "ruby" && context.native_receiver.is_a?(expected)
                raise Unimplemented.new("B01 requires genuine native receiver prerequisite")
            end
            context.native_receiver.__send__(:check_open!)
        end

        def validate_prediction_times(arguments)
            if arguments.member_id == "Release.heights_at"
                raise InvalidArgumentError, "times must be an Array of Time" unless arguments.times.is_a?(Array)
                arguments.times.each { |time| Predict.instant(time) }
            elsif %w[Release.heights Release.extremes Release.currents Release.current_events].include?(arguments.member_id)
                cadence = %w[Release.heights Release.currents].include?(arguments.member_id) ? argument_value(arguments, :step_s, 600) : nil
                Predict.window(arguments.start, arguments.stop, cadence)
                if %w[Release.heights Release.currents].include?(arguments.member_id)
                    raise InvalidArgumentError, "step_s must be a positive integer" unless cadence.is_a?(Integer) && cadence > 0
                end
            end
        end

        def require_prepared_station(arguments, context)
            unless context.is_a?(CanonicalTypes::MemberValidationContext) && context.prepared_receiver.equal?(context.native_receiver) && context.prepared_station.is_a?(Station)
                raise Unimplemented.new("B01 requires genuine B29/B08 station resolution")
            end
            request = context.prepared_station_request
            matches = arguments.station.is_a?(Station) ? request.equal?(arguments.station) : request == arguments.station
            unless matches && context.prepared_station.instance_variable_get(:@origin).equal?(context.native_receiver) && context.prepared_station.station_id == (request.is_a?(Station) ? request.station_id : request)
                raise Unimplemented.new("B01 mismatched prepared B29/B08 station binding")
            end
        end

        def require_prepared_astro_row(arguments, context)
            unless context.is_a?(CanonicalTypes::MemberValidationContext) && context.native_receiver.is_a?(AstroTable) && context.prepared_receiver.equal?(context.native_receiver) && context.prepared_row_name == arguments.name && context.prepared_row && context.native_receiver.instance_variable_get(:@raw).fetch("constituents")[arguments.name].equal?(context.prepared_row)
                raise Unimplemented.new("B01 requires genuine B41 row resolution")
            end
        end

        def validate_operation_arguments(operation:, arguments:, member_contract:)
            unless member_contract.member_id == arguments.member_id
                raise Unimplemented.new("B01 mismatched native member #{arguments.member_id}")
            end
            validate_native_receiver(arguments, member_contract)
            case arguments.member_id
            when "Client.open"
                constructor_options(**client_option_keywords(arguments), environment: {})
                HTTP.validate_proxy_argument(argument_value(arguments, :proxy, nil))
            when "Client.download"
                check_release_arg(arguments.release)
                destination = arguments.to
                raise InvalidArgumentError, "to must be a String path" unless destination.is_a?(String) && !destination.empty?
                formats = argument_value(arguments, :formats, [:jsonl])
                raise InvalidArgumentError, "formats must be an Array" unless formats.is_a?(Array) && !formats.empty?
                formats.map { |format| check_enum(format, FORMATS, "format") }.uniq
                check_bool(argument_value(arguments, :overwrite, false), "overwrite")
            when "Client.prune"
                keep = argument_value(arguments, :keep, 3)
                raise InvalidArgumentError, "keep must be an Integer >= 0" unless keep.is_a?(Integer) && keep >= 0
            when "Release.station", "Release.require_station", "Release.tombstone"
                check_id!(arguments.station_id)
            when "Release.station_by_alias"
                validate_alias_arguments(arguments.system, arguments.alias_id)
            when "Release.search"
                validate_search_arguments(arguments.name, argument_value(arguments, :limit, nil), argument_value(arguments, :match, nil))
                validate_filter_arguments(argument_value(arguments, :filters, {}))
            when "Release.near"
                validate_near_arguments(arguments.lat, arguments.lon, arguments.radius_km, argument_value(arguments, :limit, nil))
                validate_filter_arguments(argument_value(arguments, :filters, {}))
            when "Release.nearest"
                validate_nearest_arguments(arguments.lat, arguments.lon, argument_value(arguments, :max_km, nil))
                validate_filter_arguments(argument_value(arguments, :filters, {}))
            when "Release.stations", "Release.iter_stations"
                validate_filter_arguments(argument_value(arguments, :filters, {}))
            when "Station.constant_sets"
                check_bool(argument_value(arguments, :include_no_constants, false), "include_no_constants")
            when "Release.attribution"
                stations = argument_value(arguments, :stations, nil)
                raise InvalidArgumentError, "stations must be an Array of Station" unless stations.nil? || stations.is_a?(Array)
                Array(stations).each_with_index do |station, index|
                    raise InvalidArgumentError, "stations must be an Array of Station" unless station.is_a?(Station)
                    step = member_contract.prepared_attribution_steps[index]
                    unless member_contract.prepared_receiver.equal?(member_contract.native_receiver) && member_contract.prepared_attribution_request.equal?(stations) && step && step.station.equal?(station)
                        raise Unimplemented.new("B01 requires genuine staged B08 attribution owner outcome")
                    end
                    raise step.error if step.error
                    raise Unimplemented.new("B01 missing genuine staged B08 Entry") unless step.entry
                end
            when "Release.reference_station", "Release.subordinates_of"
                raise InvalidArgumentError, "#{operation}: station must be a Station" unless arguments.station.is_a?(Station)
            when "Release.heights", "Release.currents", "Release.extremes", "Release.current_events"
                validate_prediction_times(arguments)
                require_prepared_station(arguments, member_contract)
                if %w[Release.currents Release.current_events].include?(arguments.member_id)
                    Predict.options(argument_value(arguments, :set_id, nil), nil, argument_value(arguments, :bin_number, nil))
                else
                    Predict.options(argument_value(arguments, :set_id, nil), argument_value(arguments, :datum, nil))
                    offset_id = argument_value(arguments, :offset_id, nil)
                    raise InvalidArgumentError, "offset_id must be a string" unless offset_id.nil? || offset_id.is_a?(String)
                    raise InvalidArgumentError, "set_id and offset_id are mutually exclusive" if offset_id && argument_value(arguments, :set_id, nil)
                end
            when "Release.heights_at"
                validate_prediction_times(arguments)
                require_prepared_station(arguments, member_contract)
                Predict.options(argument_value(arguments, :set_id, nil), argument_value(arguments, :datum, nil))
                offset_id = argument_value(arguments, :offset_id, nil)
                raise InvalidArgumentError, "offset_id must be a string" unless offset_id.nil? || offset_id.is_a?(String)
                raise InvalidArgumentError, "set_id and offset_id are mutually exclusive" if offset_id && argument_value(arguments, :set_id, nil)
            when "Release.datums", "Release.ranges"
                require_prepared_station(arguments, member_contract)
                Predict.options(argument_value(arguments, :set_id, nil))
                if arguments.member_id == "Release.datums"
                    all_sets = argument_value(arguments, :all_sets, false)
                    raise InvalidArgumentError, "all_sets must be a boolean" unless all_sets == true || all_sets == false
                end
            when "Release.astro_table"
                id = argument_value(arguments, :id, nil)
                raise InvalidArgumentError, "astro table id must be a string" unless id.nil? || id.is_a?(String)
            when "AstroTable.equilibrium_argument"
                Predict.instant(arguments.at)
                require_prepared_astro_row(arguments, member_contract)
            when "AstroTable.node_factor"
                require_prepared_astro_row(arguments, member_contract)
                Predict.instant(arguments.at)
            when "AstroTable.equilibrium_for_year", "AstroTable.node_factor_for_year"
                require_prepared_astro_row(arguments, member_contract)
                member_contract.native_receiver.__send__(:validate_year_argument, arguments.year)
            end
            arguments
        end

        def resolve_effective_options(explicit_options:, environment:, platform_defaults:)
            options = client_option_keywords(explicit_options, platform_defaults)
            resolved = constructor_options(**options, environment: environment)
            CanonicalTypes::ArgsClientOpen.new(
                member_id: "Client.open", release: resolved.requested, file: options.fetch(:file, nil),
                cache_dir: resolved.cache_dir, offline: resolved.offline, mode: resolved.mode,
                base_url: resolved.base_url, timeout: options.fetch(:timeout, nil), proxy: options.fetch(:proxy, nil),
                ca_file: options.fetch(:ca_file, nil), user_agent: options.fetch(:user_agent, nil),
                on_network_error: resolved.on_network_error, auto_update: resolved.auto_update,
                update_interval: resolved.update_interval, logger: resolved.logger,
                verify_on_open: resolved.verify_on_open, commercial_only: resolved.commercial_only,
                commercial_basis: resolved.commercial_basis.to_s, historical_offsets_policy: resolved.historical_offsets_policy.to_s
            )
        end

        def select_canonical_error(operation:, ordered_failures:, cause:)
            failure = ordered_failures.first || (raise Unimplemented.new("B03 no selected failure for #{operation}"))
            return failure if failure.cause || cause.nil?
            CanonicalTypes::CanonicalError.new(code: failure.code, structured_fields: failure.structured_fields, cause: cause)
        end

        def translate_native_binding(canonical_result: CanonicalTypes::ABSENT, canonical_error: CanonicalTypes::ABSENT, native_profile:)
            raise Unimplemented.new("B04 #{native_profile}") unless native_profile == "ruby"
            present = !canonical_result.equal?(CanonicalTypes::ABSENT)
            if !canonical_error.equal?(CanonicalTypes::ABSENT)
                error = canonical_error.cause
                if present && canonical_result.value.is_a?(OpenTideConstants) && canonical_result.value.last_error.equal?(error)
                    return canonical_result.value
                end
                raise error if error.is_a?(OpenTideConstants::Error)
                raise Unimplemented.new("B04 missing original native error")
            end
            raise Unimplemented.new("B04 absent result and error") unless present
            canonical_result.value.is_a?(CanonicalTypes::NoValue) ? nil : canonical_result.value
        end

        def decode_release_document(source_bytes:, reader_version:, document_kind:)
            raise Unimplemented.new("B05")
        end

        def validate_release_links(parsed_document:, required_links:)
            raise Unimplemented.new("B06")
        end

        def materialize_typed_model(raw_fields:, field_contract:, origin:, model_type:)
            context = field_contract.native_context
            case model_type
            when "Station"
                unless context.is_a?(Station) && raw_fields["station_id"] == context.station_id && raw_fields.fetch("constant_sets", []) == context.instance_variable_get(:@sets).map(&:raw) && raw_fields["validation"] == context.raw["validation"]
                    raise Unimplemented.new("B07 Station raw fields disagree with prepared native dependencies")
                end
                Station.new(raw_fields, sets: context.instance_variable_get(:@sets), kind: context.kind,
                            validation: context.validation, origin: origin, licences: origin.licences.to_h { |licence| [licence.licence_id, licence] })
            when "ConstantSet"
                unless context.is_a?(ConstantSet) && raw_fields["set_id"] == context.set_id && raw_fields["convention_id"] == context.convention&.convention_id && raw_fields["licence_id"] == context.licence&.licence_id
                    raise Unimplemented.new("B07 ConstantSet raw fields disagree with prepared native dependencies")
                end
                ConstantSet.new(raw_fields, convention: context.convention, licence: context.licence,
                                validation: context.validation, recommended: context.recommended?)
            when "SourceRecord"
                SourceRecord.new(raw_fields, licences: origin.licences.to_h { |licence| [licence.licence_id, licence] })
            when "ReleaseInfo"
                ReleaseInfo.new(raw_fields, context.files)
            when "FileInfo"
                FileInfo.new(name: raw_fields.fetch("name"), url: raw_fields["url"], size: raw_fields["size"], sha256: raw_fields["sha256"])
            when "Nearby"
                Nearby.new(context.station, raw_fields.fetch("distance_km"))
            when "UpdateResult"
                UpdateResult.new(raw_fields.fetch("updated"), raw_fields.fetch("from"), raw_fields.fetch("to"))
            when "Stats"
                Stats.new(type: raw_fields.fetch("type").transform_keys { |key| Util.enum(key, ENUMS[:station_type]) }.freeze,
                          kind: raw_fields.fetch("kind").transform_keys { |key| Util.enum(key, ENUMS[:kind]) }.freeze,
                          country: raw_fields.fetch("country").freeze, source: raw_fields.fetch("source").freeze,
                          qc_status: raw_fields.fetch("qc_status").transform_keys { |key| Util.enum(key, ENUMS[:qc_status]) }.freeze)
            when "Client"
                raise Unimplemented.new("B07 Client requires closed prepared owner fields") unless context.is_a?(CanonicalTypes::PreparedClientFields)
                if raw_fields.key?("loaded_from") && raw_fields["loaded_from"] != context.loaded_from.to_s
                    raise Unimplemented.new("B07 Client raw loaded_from disagrees with prepared owner")
                end
                if raw_fields.key?("newer_format_major") && raw_fields["newer_format_major"] != context.newer_format_major
                    raise Unimplemented.new("B07 Client raw newer_format_major disagrees with prepared owner")
                end
                if raw_fields.key?("last_error") && raw_fields["last_error"].nil? && context.last_error
                    raise Unimplemented.new("B07 Client raw last_error disagrees with prepared owner")
                end
                if raw_fields["last_error"]
                    raw_error = raw_fields["last_error"]
                    unless context.last_error && raw_error.is_a?(Hash) && raw_error["code"] == context.last_error.code && raw_error["message"] == context.last_error.message
                        raise Unimplemented.new("B07 Client raw last_error fields disagree with prepared owner")
                    end
                end
                receiver = OpenTideConstants.allocate
                receiver.__send__(:bind_prepared_client_fields, context)
                receiver
            when "Release"
                raise Unimplemented.new("B07 Release requires independent prepared owner fields") unless context.is_a?(CanonicalTypes::PreparedReleaseFields)
                raise Unimplemented.new("B07 Release raw metadata disagrees with prepared fields") unless raw_fields == context.meta
                if origin.is_a?(Release)
                    unless !context.state.equal?(origin.instance_variable_get(:@state)) && !context.station_cache.equal?(origin.instance_variable_get(:@station_cache)) && !context.io_lock.equal?(origin.instance_variable_get(:@io_lock)) && !context.station_cache_lock.equal?(origin.instance_variable_get(:@station_cache_lock)) && (context.io.nil? || !context.io.equal?(origin.instance_variable_get(:@io)))
                        raise Unimplemented.new("B07 Release requires independent state/cache/locks/IO")
                    end
                end
                unless context.entries.all? { |entry| context.by_id[entry.station_id].equal?(entry) } && context.subordinates.values.flatten.all? { |entry| context.by_id[entry.station_id].equal?(entry) }
                    raise Unimplemented.new("B07 Release prepared indexes disagree on Entry owners")
                end
                receiver = Release.allocate
                receiver.__send__(:bind_prepared_release_fields, context)
                receiver.__send__(:bind_eager_station_owners, context.entries, context.raws)
                context.entries.freeze
                context.by_id.freeze
                receiver.freeze
            when "Licence", "Convention", "Constituent", "Provenance", "ProvenanceBuild", "TimeBase", "QcFlag",
                 "DroppedConstituent", "Validation", "SubordinateOffsets", "RecordSpan", "Datum", "AstroTable", "Fallback",
                 "HistoricalOffsetVintage", "HistoricalOffsetProvenance", "Tombstone"
                OpenTideConstants.const_get(model_type, false).new(raw_fields)
            when "HeightPoint"
                HeightPoint.new(**result_field_inputs(raw_fields, context, %w[height_m local_time utc_offset_s], time: true))
            when "Extreme"
                fields = result_field_inputs(raw_fields, context, %w[type height_m local_time utc_offset_s], time: true)
                fields[:type] = Util.enum(fields[:type], ENUMS[:extreme_type]) if fields.key?(:type)
                Extreme.new(**fields)
            when "CurrentPoint"
                CurrentPoint.new(**result_field_inputs(raw_fields, context, %w[velocity_major_ms velocity_minor_ms speed_ms direction_deg local_time utc_offset_s], time: true))
            when "CurrentEvent"
                fields = result_field_inputs(raw_fields, context, %w[type velocity_ms direction_deg local_time utc_offset_s], time: true)
                fields[:type] = Util.enum(fields[:type], ENUMS[:current_event_type]) if fields.key?(:type)
                CurrentEvent.new(**fields)
            when "HeightSeries", "ExtremeList"
                fields = %w[station_id timezone method set_id convention_id astro_table_id reference_station_id reference_bin datum datum_name datum_kind datum_uncertainty_m tz tz_version release algorithm offset_id offset_source offset_source_version historical_offsets current_validity current_accuracy reference_set_id reference_source_version reference_2020_equivalence source_note]
                keywords = result_field_inputs(raw_fields, context, fields, collection: :items)
                keywords[:method] = Util.enum(keywords[:method], ENUMS[:prediction_method]) if keywords.key?(:method)
                model_type == "HeightSeries" ? HeightSeries.new(**keywords) : ExtremeList.new(**keywords)
            when "CurrentSeries"
                fields = result_field_inputs(raw_fields, context, %w[station_id timezone method set_id convention_id astro_table_id reference_station_id reference_bin datum datum_name datum_kind datum_uncertainty_m bin_number tz tz_version release algorithm], collection: :items)
                fields[:method] = Util.enum(fields[:method], ENUMS[:prediction_method]) if fields.key?(:method)
                CurrentSeries.new(**fields)
            when "CurrentEventList"
                fields = result_field_inputs(raw_fields, context, %w[station_id timezone method set_id convention_id astro_table_id reference_station_id reference_bin datum datum_name datum_kind datum_uncertainty_m bin_number omitted_event_types tz tz_version release algorithm], collection: :items)
                fields[:method] = Util.enum(fields[:method], ENUMS[:prediction_method]) if fields.key?(:method)
                if fields[:omitted_event_types]
                    fields[:omitted_event_types] = fields[:omitted_event_types].map { |type| Util.enum(type, ENUMS[:current_event_type]) }
                end
                CurrentEventList.new(**fields)
            when "DatumInfo"
                DatumInfo.new(**result_field_inputs(raw_fields, context, %w[set_id zero zero_name chart_datum msl_offset_m], collection: :levels))
            when "DatumLevel"
                DatumLevel.new(**result_field_inputs(raw_fields, context, %w[key value_m above_chart_m kind method source_name epoch data_span control_station_id control_set_id control_source_id uncertainty_m uncertainty_basis flags]))
            when "Ranges"
                Ranges.new(**result_field_inputs(raw_fields, context, %w[mn gt dhq dlq]))
            end
        end

        def result_field_inputs(raw_fields, context, scalar_fields, time: false, collection: nil)
            values = scalar_fields.each_with_object({}) do |field, result|
                result[field.to_sym] = raw_fields[field] if raw_fields.key?(field)
            end
            if time && raw_fields.key?("time")
                native_time = raw_fields["time"].nil? ? nil : context.time
                unless Util.time(raw_fields["time"]) == native_time
                    raise Unimplemented.new("B07 mismatched prepared Time")
                end
                values[:time] = native_time
            end
            if collection && raw_fields.key?(collection.to_s)
                raw = raw_fields[collection.to_s]
                native = raw.nil? ? nil : (raw.empty? ? [] : context.public_send(collection))
                unless raw.nil? || raw.length == native.length && raw.zip(native).all? { |row, item| row.all? { |field, value| result_field_matches?(item.public_send(field), value) } }
                    raise Unimplemented.new("B07 mismatched prepared #{collection}")
                end
                values[collection] = native
            end
            values[:_local] = context&.instance_variable_get(:@_local)
            values
        end

        def result_field_matches?(native, raw)
            return Util.time(raw) == native if native.is_a?(Time)
            return native.to_s == raw if native.is_a?(Symbol)
            native == raw
        end

        def access_raw_record(access_kind:, source_record:, station:, release_origin:, native_profile:)
            raise Unimplemented.new("B08")
        end

        def open_client_release(arguments:, environment:, platform_defaults:, cache_state:, clock:, native_profile:, reader_version:)
            raise Unimplemented.new("B09")
        end

        def resolve_release_request(release_request:, effective_options:, cache_state:, clock:, reader_version:)
            raise Unimplemented.new("B10")
        end

        def exchange_release_metadata(metadata_request:, trusted_cache:, transport_options:, cache_state:, clock:, reader_version:)
            raise Unimplemented.new("B11")
        end

        def update_client_release(client_state:, update_request:, clock:, reader_version:)
            raise Unimplemented.new("B12")
        end

        def refresh_client_if_due(client_state:, query_kind:, clock:, reader_version:)
            raise Unimplemented.new("B13")
        end

        def forward_held_release(held_release:, query_arguments:)
            raise Unimplemented.new("B14")
        end

        def enforce_resource_lifetime(resource_state:, lifetime_action:)
            raise Unimplemented.new("B15")
        end

        def bind_checksum_manifest(checksum_bytes:, pointer_digests:, required_files:)
            raise Unimplemented.new("B16")
        end

        def acquire_release_files(acquisition_descriptor:, effective_options:, load_mode:, cache_state:, clock:, reader_version:)
            raise Unimplemented.new("B17")
        end

        def merge_cache_receipt(locked_cache_state:, verified_file_rows:, release_metadata:)
            raise Unimplemented.new("B18")
        end

        def select_cached_release(release_candidates:, effective_options:, cache_state:, clock:)
            raise Unimplemented.new("B19")
        end

        def verify_release_files(release_files:, trusted_cached_pointer:)
            raise Unimplemented.new("B20")
        end

        def publish_download(destination:, format_selection:, overwrite_policy:, release_files:, checksum_bytes:, pointer_digests:)
            raise Unimplemented.new("B21")
        end

        def manage_cache_inventory(inventory_action:, cache_state:, keep:, current_cache_directory:, clock:)
            raise Unimplemented.new("B22")
        end

        def perform_guarded_io(io_kind:, io_request:, io_options:, clock:)
            raise Unimplemented.new("B23")
        end

        def project_station_index(station_source_row:, source_byte_span:, projection_contract:)
            Reader.index_entry(station_source_row, source_byte_span.offset_bytes, source_byte_span.length_bytes)
        end

        def authenticate_station_index(source_files:, supplied_index:, index_presence:, reader_version:)
            raise Unimplemented.new("B25")
        end

        def compare_station_source(index_entry:, station_source_row:, index_presence:)
            raise Unimplemented.new("B26")
        end

        def read_station_lazily(stream_reader:, station_id:, release_origin:, reader_version:)
            raise Unimplemented.new("B27")
        end

        def lookup_station_identity(release_view:, identity_query:, reader_version:)
            raise Unimplemented.new("B29")
        end

        def select_effective_recommendation(station_sets:, original_recommendation:, commercial_only:)
            raise Unimplemented.new("B30")
        end

        def admit_quality_path(candidate_path:, include_flagged:, include_fallback:)
            raise Unimplemented.new("B31")
        end

        def admit_commercial_path(candidate_path:, commercial_only:, commercial_basis:)
            raise Unimplemented.new("B32")
        end

        def resolve_reference_path(station_source_row:, path_request:, release_view:)
            raise Unimplemented.new("B33")
        end

        def execute_discovery_query(release_view:, query_kind:, query_options:, reader_version:)
            raise Unimplemented.new("B34")
        end

        def summarize_station_sets(summary_kind:, release_view:, station_sets:, summary_options:)
            raise Unimplemented.new("B35")
        end

        def admit_historical_offset(own_offset:, reference_path:, historical_policy:, selection_kind:, reader_version:)
            raise Unimplemented.new("B36")
        end

        def format_attribution(station:, release_view:, commercial_only:)
            raise Unimplemented.new("B37")
        end

        def format_citation(published_metadata:, citation_style:)
            raise Unimplemented.new("B38")
        end

        def parse_prediction_window(time_inputs:, window_inputs:, step:, local_time_profile:)
            if time_inputs.member_id == "Release.heights_at"
                times = time_inputs.times
                raise InvalidArgumentError, "times must be an Array of Time" unless times.is_a?(Array)
                instants = times.map { |time| Predict.instant(time) }
                return CanonicalTypes::PredictionWindow.new(start: nil, stop: nil, step: nil, instants: instants)
            end
            cadence = %w[Release.heights Release.currents].include?(window_inputs.member_id) ? step : nil
            first, last = Predict.window(window_inputs.start, window_inputs.stop, cadence)
            if !cadence.nil? || %w[Release.heights Release.currents].include?(window_inputs.member_id)
                raise InvalidArgumentError, "step_s must be a positive integer" unless cadence.is_a?(Integer) && cadence > 0
            end
            CanonicalTypes::PredictionWindow.new(start: first, stop: last, step: cadence, instants: nil)
        end

        def select_prediction_model(station_request:, release_view:, selection_options:, reader_version:)
            raise Unimplemented.new("B40")
        end

        def evaluate_astronomy(selected_prediction_model:, utc_instant:)
            year = Predict.utc(utc_instant).year
            origin, terms = selected_prediction_model.native_context.total.year_data(year)
            CanonicalTypes::AstronomicalTerms.new(utc_year: year, constituent_terms: terms.map { |term| term.dup.freeze }.freeze, epoch_hours: origin / 3600.0)
        end

        def evaluate_harmonic_height(selected_prediction_model:, prediction_instants:, requested_datum:)
            context = selected_prediction_model.native_context
            unless context && selected_prediction_model.selection_context.equal?(context) && !selected_prediction_model.prepared_datum.equal?(CanonicalTypes::ABSENT) && (selected_prediction_model.prepared_datum || "mean_level") == requested_datum
                raise Unimplemented.new("B42 mismatched or missing prepared datum/Context binding")
            end
            prediction_instants.map do |instant|
                evaluate_astronomy(selected_prediction_model: selected_prediction_model, utc_instant: instant)
                selected_prediction_model.native_context.total.value(instant)
            end
        end

        def find_tide_events(selected_prediction_model:, prediction_window:)
            raise Unimplemented.new("B43")
        end

        def evaluate_direct_current(selected_prediction_model:, prediction_window:, current_request:, current_operation:)
            raise Unimplemented.new("B44")
        end

        def evaluate_tide_offset(own_offset:, reference_path:, prediction_window:, tide_request:, reader_version:)
            raise Unimplemented.new("B45")
        end

        def fold_equal_tide_offset(own_offset:, reference_model:, prediction_instants:, requested_datum:)
            raise Unimplemented.new("B46")
        end

        def evaluate_current_offset(own_current_offsets:, reference_path:, prediction_window:, current_request:, reader_version:)
            raise Unimplemented.new("B47")
        end

        def dispatch_auxiliary_result(auxiliary_kind:, auxiliary_operation:, source_values:, result_context:, local_time_profile:, result_values:, utc_result:, selection_options:, reader_version:, auxiliary_member_id:)
            raise Unimplemented.new("B48")
        end

        def retain_raw_source_record(source_record:, native_profile:)
            Util.deep_freeze(source_record)
        end

        def check_station_origin(station:, release_origin:)
            raise Unimplemented.new("B08.origin")
        end

        def manage_cache_lock(lock_request:, lock_state:, clock:)
            raise Unimplemented.new("B23.lock")
        end

        def request_http_resource(http_request:, transport_options:)
            raise Unimplemented.new("B23.http")
        end

        def count_release_statistics(release_view:)
            raise Unimplemented.new("B35.stats")
        end

        def order_constant_sets(station_sets:, original_recommendation:, commercial_only:, include_no_constants:)
            raise Unimplemented.new("B35.sets")
        end

        def read_auxiliary_model_value(auxiliary_operation:, source_values:, selection_options:, reader_version:, auxiliary_member_id:)
            raise Unimplemented.new("B48.aux")
        end

        def construct_prediction_result(result_values:, result_context:)
            raise Unimplemented.new("B48.context")
        end

        def convert_result_to_local_time(utc_result:, local_time_profile:)
            raise Unimplemented.new("B48.local")
        end

        def find_unrounded_tide_events(selected_prediction_model:, prediction_window:)
            Predict.__send__(:unrounded_events, selected_prediction_model.native_context.total, prediction_window.start, prediction_window.stop).each_with_index.map do |(root, kind, value), order|
                CanonicalTypes::UnroundedTideEvent.new(root_seconds: root, event_type: kind, height_m: value, reference_order: order)
            end
        end

        def find_unrounded_current_events(selected_prediction_model:, prediction_window:, current_request:)
            context = selected_prediction_model.native_context
            bound = selected_prediction_model.prepared_current_request
            unless context && selected_prediction_model.selection_context.equal?(context) && (bound.is_a?(CanonicalTypes::ArgsReleaseCurrents) || bound.is_a?(CanonicalTypes::ArgsReleaseCurrentEvents)) && bound.class == current_request.class && %i[member_id station start stop bin_number set_id].all? { |field| bound.public_send(field) == current_request.public_send(field) }
                raise Unimplemented.new("B44.roots mismatched or missing prepared current request/Context binding")
            end
            Predict.__send__(:unrounded_current_events, selected_prediction_model.native_context, prediction_window.start, prediction_window.stop).each_with_index.map do |(root, kind, value, direction), order|
                CanonicalTypes::UnroundedCurrentEvent.new(root_seconds: root, event_type: kind, velocity_m_s: value, direction_deg: direction, reference_order: order)
            end
        end

        def acquire_checksum_sidecar(acquisition_descriptor:, effective_options:)
            raise Unimplemented.new("B17.sidecar")
        end

        def client_option_keywords(arguments, defaults = nil)
            %i[release file cache_dir offline mode base_url timeout proxy ca_file user_agent on_network_error auto_update update_interval logger verify_on_open commercial_only commercial_basis historical_offsets_policy].each_with_object({}) do |name, options|
                value = arguments.public_send(name)
                value = defaults.public_send(name) if value.equal?(CanonicalTypes::ABSENT) && defaults
                options[name] = value unless value.equal?(CanonicalTypes::ABSENT)
            end
        end

        def argument_value(arguments, name, default)
            return default unless arguments.respond_to?(name)
            value = arguments.public_send(name)
            value.equal?(CanonicalTypes::ABSENT) || value.nil? && name == :filters ? default : value
        end

    end
    private_constant :Canonical
end
