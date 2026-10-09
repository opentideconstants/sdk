# A CMake project that uses an installed libopentideconstants through
# find_package (the package config that c/CMakeLists.txt installs):
#
#     cmake -S c/tests/consumer -B b -DCMAKE_PREFIX_PATH=<install prefix>
cmake_minimum_required(VERSION 3.14)
project(otc_consumer LANGUAGES C)
find_package(opentideconstants 0.1 REQUIRED)
add_executable(consumer consumer.c)
target_link_libraries(consumer PRIVATE opentideconstants::opentideconstants)
