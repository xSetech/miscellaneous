# Included after project(Torch ...) via CMAKE_PROJECT_Torch_INCLUDE.
# Defines a no-op INTERFACE target named "stdc++" so that any
# target_link_libraries(foo stdc++) call resolves to this target rather
# than adding -lstdc++ to the link line.
if(NOT TARGET stdc++)
  add_library(stdc++ INTERFACE)
endif()
