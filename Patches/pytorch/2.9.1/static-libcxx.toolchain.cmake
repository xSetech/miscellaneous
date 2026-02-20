# Toolchain file: link all C++ targets against a specific static libc++/libc++abi.
#
# Usage: set CMAKE_TOOLCHAIN_FILE to the absolute path of this file when
# invoking the cmake configure step (e.g. via the pip build command).
# CMake caches CMAKE_TOOLCHAIN_FILE in CMakeCache.txt, so subsequent
# reconfigures pick it up automatically without re-specifying the env var.

set(STATIC_LIBCXX    "/example/lib/libc++.a")
set(STATIC_LIBCXXABI "/example/lib/libc++abi.a")

# Prevent the compiler driver from implicitly injecting a C++ runtime,
# and prevent the macOS linker from pulling in implicit dylib dependencies.
set(CMAKE_EXE_LINKER_FLAGS_INIT    "-nostdlib++ -Wl,-no_implicit_dylibs")
set(CMAKE_SHARED_LINKER_FLAGS_INIT "-nostdlib++ -Wl,-no_implicit_dylibs")
set(CMAKE_MODULE_LINKER_FLAGS_INIT "-nostdlib++ -Wl,-no_implicit_dylibs")

# Replace the default C++ standard libraries with the static versions.
# CMAKE_CXX_STANDARD_LIBRARIES is appended to the link line for every
# C++ target; this is what populates LINK_LIBRARIES in build.ninja.
set(CMAKE_CXX_STANDARD_LIBRARIES
    "${STATIC_LIBCXX} ${STATIC_LIBCXXABI}"
    CACHE STRING "" FORCE)

# caffe2/CMakeLists.txt unconditionally calls target_link_libraries(foo stdc++)
# for all non-MSVC builds, which adds -lstdc++ (GCC's stdlib) even when building
# with Clang/libc++.  By defining an INTERFACE target named "stdc++" immediately
# after the top-level project() call, CMake resolves that name to this empty
# target instead of searching for the system library, making the call a no-op.
set(CMAKE_PROJECT_Torch_INCLUDE
    "${CMAKE_CURRENT_LIST_DIR}/static-libcxx-intercept.cmake")
