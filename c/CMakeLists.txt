cmake_minimum_required(VERSION 3.14)
project(opentideconstants VERSION 0.1.0 LANGUAGES C)

option(OTC_WITH_FETCH "Build the otc_fetch module (needs libcurl)" OFF)
# The conformance runner lives outside c/ (conformance/runners/c), so it is built
# by default only when c/ is the top-level project of the repository; a project
# that vendors c/ with add_subdirectory does not need it (and may not have it).
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR
   AND EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/../conformance/runners/c/runner.c)
    set(OTC_BUILD_RUNNER_DEFAULT ON)
else()
    set(OTC_BUILD_RUNNER_DEFAULT OFF)
endif()
option(OTC_BUILD_RUNNER "Build the conformance runner" ${OTC_BUILD_RUNNER_DEFAULT})
set(OTC_SANITIZE "" CACHE STRING "Sanitizers for the library and the runner, e.g. address,undefined")

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

find_package(Threads REQUIRED)

set(OTC_SOURCES
    src/otc_util.c
    src/otc_release.c
    src/otc_query.c
    src/otc_station.c
    src/otc_fold_table.c
    src/otc_vendor_cjson.c
    src/otc_vendor_sha256.c)
if(OTC_WITH_FETCH)
    # The otc_fetch module (SDK spec 5, 6.4): libcurl, only in this module.
    find_package(CURL REQUIRED)
    list(APPEND OTC_SOURCES src/otc_fetch.c)
    # the .pc names libcurl.pc only when pkg-config has one; CMake may have found
    # curl without it (its FindCURL module, a macOS SDK .tbd): then -lcurl (B4-4)
    find_package(PkgConfig QUIET)
    if(PKG_CONFIG_FOUND)
        pkg_check_modules(OTC_PC_CURL QUIET libcurl)
    endif()
    if(OTC_PC_CURL_FOUND)
        set(OTC_PC_REQUIRES_PRIVATE "libcurl")
        set(OTC_PC_CURL_LIBS "")
    else()
        set(OTC_PC_REQUIRES_PRIVATE "")
        set(OTC_PC_CURL_LIBS "-lcurl")
    endif()
else()
    list(APPEND OTC_SOURCES src/otc_fetch_stub.c)
    set(OTC_PC_REQUIRES_PRIVATE "")
    set(OTC_PC_CURL_LIBS "")
endif()

add_library(opentideconstants ${OTC_SOURCES})
target_include_directories(opentideconstants
    PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include> $<INSTALL_INTERFACE:include>
    PRIVATE src vendor/cjson vendor/sha256)
target_compile_definitions(opentideconstants PRIVATE CJSON_HIDE_SYMBOLS)
target_link_libraries(opentideconstants PRIVATE Threads::Threads)
if(OTC_WITH_FETCH)
    target_link_libraries(opentideconstants PRIVATE CURL::libcurl)
endif()
if(NOT WIN32)
    target_link_libraries(opentideconstants PRIVATE m)
endif()
set_target_properties(opentideconstants PROPERTIES
    VERSION ${PROJECT_VERSION} SOVERSION 1 WINDOWS_EXPORT_ALL_SYMBOLS ON)

if(MSVC)
    set(OTC_WARNINGS /W4 /wd4996)
else()
    set(OTC_WARNINGS -Wall -Wextra -Wpedantic -Wshadow -Wstrict-prototypes)
endif()
set_source_files_properties(src/otc_util.c src/otc_release.c src/otc_query.c src/otc_station.c
    src/otc_fetch_stub.c src/otc_fetch.c PROPERTIES COMPILE_OPTIONS "${OTC_WARNINGS}")

if(OTC_SANITIZE)
    target_compile_options(opentideconstants PUBLIC -fsanitize=${OTC_SANITIZE} -fno-omit-frame-pointer -fno-sanitize-recover=all)
    target_link_options(opentideconstants PUBLIC -fsanitize=${OTC_SANITIZE})
endif()

if(OTC_BUILD_RUNNER)
    add_executable(otc_runner ../conformance/runners/c/runner.c vendor/cjson/cJSON.c)
    target_include_directories(otc_runner PRIVATE vendor/cjson)
    target_compile_definitions(otc_runner PRIVATE CJSON_HIDE_SYMBOLS)
    if(OTC_WITH_FETCH)
        # The runner says hello as "c-fetch" (conformance/README.md, Profiles).
        target_compile_definitions(otc_runner PRIVATE OTC_RUNNER_FETCH=1)
    endif()
    target_link_libraries(otc_runner PRIVATE opentideconstants Threads::Threads)
    if(NOT WIN32)
        target_link_libraries(otc_runner PRIVATE m)
    endif()
endif()

# The library's own tests (c/tests): small programs against the real library.
# A test whose name starts with test_fetch_ runs under the conformance fixture
# server (c/tests/run_with_server.sh needs python3). Run them with ctest.
option(OTC_BUILD_TESTS "Build the C library's own tests (c/tests)" OFF)
if(OTC_BUILD_TESTS)
    enable_testing()
    file(GLOB OTC_TEST_SOURCES ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_*.c)
    if(OTC_WITH_FETCH)
        # test_fetch_lock* link a copy of the library whose lock timers are short
        add_library(otc_test_fast_locks STATIC ${OTC_SOURCES})
        target_include_directories(otc_test_fast_locks
            PUBLIC include PRIVATE src vendor/cjson vendor/sha256)
        target_compile_definitions(otc_test_fast_locks PRIVATE CJSON_HIDE_SYMBOLS
            OTC_LOCK_STALE_MS=600 OTC_LOCK_POLL_MS=50)
        target_link_libraries(otc_test_fast_locks PRIVATE Threads::Threads CURL::libcurl)
        if(NOT WIN32)
            target_link_libraries(otc_test_fast_locks PRIVATE m)
        endif()
    endif()
    foreach(src ${OTC_TEST_SOURCES})
        get_filename_component(name ${src} NAME_WE)
        if(name MATCHES "^test_fetch_" AND NOT OTC_WITH_FETCH)
            continue()
        endif()
        # out-of-memory tests replace malloc, which the sanitizers do too
        if(name MATCHES "_oom" AND (OTC_SANITIZE OR WIN32))
            continue()
        endif()
        add_executable(${name} ${src})
        target_include_directories(${name} PRIVATE tests src vendor/cjson)
        if(name MATCHES "^test_fetch_lock")
            target_link_libraries(${name} PRIVATE otc_test_fast_locks Threads::Threads CURL::libcurl)
        else()
            target_link_libraries(${name} PRIVATE opentideconstants Threads::Threads)
        endif()
        if(NOT WIN32)
            target_link_libraries(${name} PRIVATE m)
        endif()
        if(name MATCHES "^test_fetch_")
            set(rules "")
            string(REGEX REPLACE "^test_fetch_" "" stem ${name})
            if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/tests/rules_${stem}.json)
                set(rules ${CMAKE_CURRENT_SOURCE_DIR}/tests/rules_${stem}.json)
            endif()
            add_test(NAME ${name} COMMAND sh ${CMAKE_CURRENT_SOURCE_DIR}/tests/run_with_server.sh
                $<TARGET_FILE:${name}> ${rules})
        else()
            add_test(NAME ${name} COMMAND ${name})
        endif()
    endforeach()
endif()

include(GNUInstallDirs)
install(TARGETS opentideconstants
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES include/opentideconstants.h DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
# Spec 7.4: supported-formats.json ships with every C release artifact.
install(FILES supported-formats.json DESTINATION ${CMAKE_INSTALL_DATADIR}/opentideconstants)
# opentideconstants.pc. The default build is a static archive: then its
# dependencies are part of Libs/Requires, so a plain `pkg-config --libs` links
# (C71); a shared library keeps them private.
if(WIN32)
    set(OTC_PC_SYSLIBS "${OTC_PC_CURL_LIBS}")
else()
    string(STRIP "${OTC_PC_CURL_LIBS} -lm -pthread" OTC_PC_SYSLIBS)
endif()
if(BUILD_SHARED_LIBS)
    set(OTC_PC_REQUIRES "")
    # macOS: the dylib's install name is @rpath/..., so the app needs an rpath to
    # the library's folder, or dyld aborts at load (B4-1)
    if(APPLE)
        set(OTC_PC_LIBS "-Wl,-rpath,\${libdir}")
    else()
        set(OTC_PC_LIBS "")
    endif()
    set(OTC_PC_LIBS_PRIVATE "${OTC_PC_SYSLIBS}")
else()
    set(OTC_PC_REQUIRES "${OTC_PC_REQUIRES_PRIVATE}")
    set(OTC_PC_REQUIRES_PRIVATE "")
    set(OTC_PC_LIBS "${OTC_PC_SYSLIBS}")
    set(OTC_PC_LIBS_PRIVATE "")
endif()
# The .pc is relocatable: prefix is found from the .pc's own folder, so
# `cmake --install --prefix X` (or a moved install) still gives the right
# paths. An absolute CMAKE_INSTALL_LIBDIR / INCLUDEDIR is used as it is (C72).
if(IS_ABSOLUTE "${CMAKE_INSTALL_LIBDIR}")
    set(OTC_PC_PREFIX "${CMAKE_INSTALL_PREFIX}")
    set(OTC_PC_LIBDIR "${CMAKE_INSTALL_LIBDIR}")
else()
    string(REGEX REPLACE "[^/]+" ".." OTC_PC_UP "${CMAKE_INSTALL_LIBDIR}/pkgconfig")
    set(OTC_PC_PREFIX "\${pcfiledir}/${OTC_PC_UP}")
    set(OTC_PC_LIBDIR "\${prefix}/${CMAKE_INSTALL_LIBDIR}")
endif()
if(IS_ABSOLUTE "${CMAKE_INSTALL_INCLUDEDIR}")
    set(OTC_PC_INCLUDEDIR "${CMAKE_INSTALL_INCLUDEDIR}")
else()
    set(OTC_PC_INCLUDEDIR "\${prefix}/${CMAKE_INSTALL_INCLUDEDIR}")
endif()
configure_file(opentideconstants.pc.in opentideconstants.pc @ONLY)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/opentideconstants.pc DESTINATION ${CMAKE_INSTALL_LIBDIR}/pkgconfig)
