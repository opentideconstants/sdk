#!/bin/sh
# Runs one C test against the conformance fixture server (conformance/server.py).
#   run_with_server.sh <test program> [rules.json]
# The server listens on a free port; the test gets OTC_TEST_SERVER and
# OTC_TEST_PROXY, and OTC_TEST_REQUIRE_SERVER=1, so a test that finds no server
# address fails (it does not skip). The server is stopped when the test ends.
set -u
here=$(cd "$(dirname "$0")" && pwd)
server="$here/../../conformance/server.py"
py=${OTC_TEST_PYTHON:-python3}
test_bin=$1
rules=${2:-}
log=$(mktemp "${TMPDIR:-/tmp}/otc-server-XXXXXX")
if [ -n "$rules" ]; then
    "$py" -u "$server" --port 0 --proxy-port 0 --rules "$rules" >"$log" 2>&1 &
else
    "$py" -u "$server" --port 0 --proxy-port 0 >"$log" 2>&1 &
fi
pid=$!
i=0
while ! grep -q '^recording proxy' "$log" 2>/dev/null; do
    i=$((i + 1))
    if [ $i -gt 100 ] || ! kill -0 $pid 2>/dev/null; then
        echo "the fixture server did not start:" >&2
        cat "$log" >&2
        kill $pid 2>/dev/null
        rm -f "$log"
        exit 2
    fi
    sleep 0.1
done
OTC_TEST_SERVER=$(sed -n 's/^fixture server \(http:[^ ]*\)\/ .*/\1/p' "$log")
OTC_TEST_PROXY=$(sed -n 's/^recording proxy \(http:[^ ]*\)$/\1/p' "$log")
if [ -z "$OTC_TEST_SERVER" ] || [ -z "$OTC_TEST_PROXY" ]; then
    echo "run_with_server.sh: no server address in the banner (OTC_TEST_SERVER='$OTC_TEST_SERVER', OTC_TEST_PROXY='$OTC_TEST_PROXY'); the server log:" >&2
    cat "$log" >&2
    kill $pid 2>/dev/null
    rm -f "$log"
    exit 2
fi
OTC_TEST_REQUIRE_SERVER=1
export OTC_TEST_SERVER OTC_TEST_PROXY OTC_TEST_REQUIRE_SERVER
"$test_bin"
rc=$?
kill $pid 2>/dev/null
wait $pid 2>/dev/null
rm -f "$log"
exit $rc
