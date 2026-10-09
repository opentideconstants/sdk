#!/bin/sh
# Check an installed libopentideconstants the way an application uses it
# (c.yml, install job):
#
#     sh c/tests/consumer/check_install.sh PREFIX FETCH [relocate|fixed]
#
# FETCH is 1 when the library was built with otc_fetch. It builds
# consumer.c with the flags of `pkg-config --cflags --libs` and runs it
# without LD_LIBRARY_PATH, builds it with find_package(opentideconstants)
# and runs it, compares the installed supported-formats.json, and checks
# the installed library's global symbols with nm. With "relocate" (the
# default) it then moves the install and does the two consumers again: the
# .pc and the CMake config must find the moved files. An install with an
# absolute CMAKE_INSTALL_LIBDIR is not relocatable; pass "fixed".
set -eu
prefix=$(cd "$1" && pwd)
fetch=$2
mode=${3:-relocate}
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
fixture=$root/conformance/fixtures/reader/OTC_20991231.2.jsonl
CC=${CC:-cc}
PYTHON=${PYTHON:-python3}
work=$(mktemp -d)
trap 'if [ -d "$prefix.hidden" ]; then mv "$prefix.hidden" "$prefix"; fi; rm -rf "$work"' EXIT

consumers() { # label, install prefix
    pc=$(find "$2" -name opentideconstants.pc | head -n 1)
    test -n "$pc" || { echo "$1: no opentideconstants.pc under $2"; exit 1; }
    flags=$(PKG_CONFIG_PATH=$(dirname "$pc") pkg-config --cflags --libs opentideconstants)
    echo "$1: pkg-config --cflags --libs: $flags"
    # shellcheck disable=SC2086  # the flags are separate words
    "$CC" -std=c99 -Wall -Wextra -Werror -o "$work/$1-pc" "$here/consumer.c" $flags
    mkdir "$work/$1-pc-cache"
    "$work/$1-pc" "$fixture" "$work/$1-pc-cache" "$fetch"
    echo "$1: find_package(opentideconstants)"
    cmake -S "$here" -B "$work/$1-fp" -DCMAKE_PREFIX_PATH="$2" -DCMAKE_C_COMPILER="$CC" -DCMAKE_BUILD_TYPE=Release >/dev/null
    cmake --build "$work/$1-fp" --config Release >/dev/null
    mkdir "$work/$1-fp-cache"
    "$work/$1-fp/consumer" "$fixture" "$work/$1-fp-cache" "$fetch"
}

consumers installed "$prefix"
cmp "$root/c/supported-formats.json" "$prefix/share/opentideconstants/supported-formats.json"
echo "installed supported-formats.json is the source's"
lib=$(find "$prefix" -name libopentideconstants.a -o -name libopentideconstants.so -o -name libopentideconstants.dylib | head -n 1)
test -n "$lib" || { echo "no libopentideconstants under $prefix"; exit 1; }
"$PYTHON" "$root/c/tools/gen_sources.py" --symbols "$lib"

if [ "$mode" = relocate ]; then
    cp -R "$prefix" "$work/moved"
    mv "$prefix" "$prefix.hidden"
    consumers moved "$work/moved"
fi
echo "the installed library links and runs through pkg-config and find_package"
