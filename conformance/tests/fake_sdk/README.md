Fake SDKs for the runner self-tests (tests/test_group_h.py). Each one has the shape of the public API that a
runner calls, and its behaviour is set by FAKE_SDK_MODE, so a test can make the SDK return a value a runner
cannot encode (inf, an object), raise a non-SDK exception (mode "raise": tombstone_count in each fake), or leave a
field out. Each fake has only the members its tests use: for example the Ruby fake's require_station needs the Error
class, so it does not work in the "no-error-class" mode, which only the handshake test uses. They are not the SDKs.
