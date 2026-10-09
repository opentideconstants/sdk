#!/bin/sh
# Runs one C test against the conformance fixture server (conformance/server.py).
#   run_with_server.sh <test program> [rules.json]
# The server listens on a free port; the test gets OTC_TEST_SERVER and
# OTC_TEST_PROXY, and OTC_TEST_REQUIRE_SERVER=1, so a test that finds no server
# address fails (it does not skip). The exit status is the test's, except:
#   2   the server did not start, or its banner gave no address
#   77  the test skipped itself (ctest's SKIP_RETURN_CODE)
# The wrapper stops only the server and the test it started, also when it is
# interrupted.
set -u
if [ $# -lt 1 ] || [ $# -gt 2 ]; then
    echo "usage: $0 <test program> [rules.json]" >&2
    exit 2
fi
here=$(cd "$(dirname "$0")" && pwd)
server="$here/../../conformance/server.py"
py=${OTC_TEST_PYTHON:-python3}
test_bin=$1
rules=${2:-}
pid=
test_pid=
log=$(mktemp "${TMPDIR:-/tmp}/otc-server-XXXXXX") || {
    echo "run_with_server.sh: cannot make a temporary file for the server log" >&2
    exit 2
}

cleanup() {
    if [ -n "$test_pid" ]; then kill "$test_pid" 2>/dev/null; wait "$test_pid" 2>/dev/null; fi
    if [ -n "$pid" ]; then kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null; fi
    rm -f "$log"
}
fail_with_log() {
    echo "run_with_server.sh: $1; the server log:" >&2
    cat "$log" >&2
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if [ -n "$rules" ]; then
    "$py" -u "$server" --port 0 --proxy-port 0 --rules "$rules" >"$log" 2>&1 &
else
    "$py" -u "$server" --port 0 --proxy-port 0 >"$log" 2>&1 &
fi
pid=$!
i=0
while ! grep -q '^recording proxy' "$log" 2>/dev/null; do
    i=$((i + 1))
    if [ $i -gt 100 ] || ! kill -0 "$pid" 2>/dev/null; then
        fail_with_log "the fixture server did not start"
        exit 2
    fi
    sleep 0.1
done
OTC_TEST_SERVER=$(sed -n 's/^fixture server \(http:[^ ]*\)\/ .*/\1/p' "$log")
OTC_TEST_PROXY=$(sed -n 's/^recording proxy \(http:[^ ]*\)$/\1/p' "$log")
if [ -z "$OTC_TEST_SERVER" ] || [ -z "$OTC_TEST_PROXY" ]; then
    fail_with_log "no server address in the banner (OTC_TEST_SERVER='$OTC_TEST_SERVER', OTC_TEST_PROXY='$OTC_TEST_PROXY')"
    exit 2
fi
OTC_TEST_REQUIRE_SERVER=1
export OTC_TEST_SERVER OTC_TEST_PROXY OTC_TEST_REQUIRE_SERVER

# in the background, so that a signal to this script reaches the trap at once
"$test_bin" &
test_pid=$!
wait "$test_pid"
rc=$?
test_pid=

exit $rc
