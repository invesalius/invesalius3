cmake_minimum_required(VERSION 3.15...3.26)
project(${SKBUILD_PROJECT_NAME} VERSION ${SKBUILD_PROJECT_VERSION} LANGUAGES C CXX)

add_definitions(-DNPY_NO_DEPRECATED_API=NPY_1_7_API_VERSION)

add_subdirectory(invesalius_cy)
if(EXISTS "./plugins/CMakeLists.txt")
    add_subdirectory(plugins)
endif()
