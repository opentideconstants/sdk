#!/bin/sh
# The C conformance runner (conformance/README.md). Build it first:
#   cmake -S c -B c/build && cmake --build c/build
# then: uv run conformance/driver.py --runner conformance/runners/c/run.sh
# OTC_C_RUNNER names another build of the runner binary (a sanitizer build, for example).
# OTC_C_RUNNER_WRAP is a command put in front of it (for example "valgrind -q --error-exitcode=99").
here=$(cd "$(dirname "$0")" && pwd)
exec ${OTC_C_RUNNER_WRAP:-} "${OTC_C_RUNNER:-$here/../../../c/build/otc_runner}" "$@"
