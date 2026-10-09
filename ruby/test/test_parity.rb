# Values that must be the same in every SDK (spec §4.2, §4.4.1, §4.6, CR D12, D15).
require_relative "support"

class ParityTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants

    # R69 (CR D15): OPENTIDECONSTANTS_OFFLINE reads 1, true, yes and on, in
    # any case and with spaces around; the variable wins over offline: false.
    def test_offline_environment_values
        srv = serve
        ["1", "true", " YES ", "On"].each do |v|
            with_env("OPENTIDECONSTANTS_OFFLINE" => v) do
                assert_raises(OTC::OfflineError, v.inspect) { OTC.new(base_url: srv.url("/"), cache_dir: tmpdir, offline: false) }
            end
        end
        assert_empty srv.requests
        ["0", "false", "", "nope"].each do |v|
            with_env("OPENTIDECONSTANTS_OFFLINE" => v) do
                OTC.new(base_url: srv.url("/"), cache_dir: tmpdir).close
            end
        end
        refute_empty srv.requests
    end

    # R74 (CR D12): the fold trims only U+0020, so a NUL at the end stays.
    def test_fold_trims_only_spaces
        assert_equal "pier\u0000", OTC::Fold.fold(" Pier\u0000 ")
        assert_equal "a b", OTC::Fold.fold("  a \t\n b  ")
        assert_equal "\u0000a", OTC::Fold.fold("\u0000a")
    end

    def with_env(vars)
        old = vars.keys.to_h { |k| [k, ENV[k]] }
        vars.each { |k, v| ENV[k] = v }
        yield
    ensure
        old.each { |k, v| ENV[k] = v }
    end
end
