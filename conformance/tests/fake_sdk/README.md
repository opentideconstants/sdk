Fake SDKs for the runner self-tests (tests/test_group_h.py). Each one has the shape of the public API that a
runner calls, and its behaviour is set by FAKE_SDK_MODE, so a test can make the SDK return a value a runner
cannot encode (inf, an object), raise a non-SDK exception, or leave a field out. They are not the SDKs.
