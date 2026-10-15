# A CMake project that uses an installed libopentideconstants through
# find_package (the package config that c/CMakeLists.txt installs):
#
#     cmake -S c/tests/consumer -B b -DCMAKE_PREFIX_PATH=<install prefix>
cmake_minimum_required(VERSION 3.14)
project(otc_consumer LANGUAGES C)
find_package(opentideconstants 0.1 REQUIRED)
add_executable(consumer consumer.c)
target_link_libraries(consumer PRIVATE opentideconstants::opentideconstants)
option(OTC_CANONICAL_SHAPE_ONLY "Build public ABI preservation consumer" OFF)
if(OTC_CANONICAL_SHAPE_ONLY)
    add_executable(canonical_shape_consumer canonical_shape.c)
    target_link_libraries(canonical_shape_consumer PRIVATE opentideconstants::opentideconstants)
endif()
