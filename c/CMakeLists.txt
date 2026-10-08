cmake_minimum_required(VERSION 3.14)
project(opentideconstants VERSION 0.1.0 LANGUAGES C)

option(OTC_WITH_FETCH "Build the otc_fetch module (needs libcurl)" OFF)
option(OTC_BUILD_RUNNER "Build the conformance runner" ON)
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
    set(OTC_PC_REQUIRES_PRIVATE "libcurl")
else()
    list(APPEND OTC_SOURCES src/otc_fetch_stub.c)
    set(OTC_PC_REQUIRES_PRIVATE "")
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

include(GNUInstallDirs)
install(TARGETS opentideconstants
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES include/opentideconstants.h DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
configure_file(opentideconstants.pc.in opentideconstants.pc @ONLY)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/opentideconstants.pc DESTINATION ${CMAKE_INSTALL_LIBDIR}/pkgconfig)
