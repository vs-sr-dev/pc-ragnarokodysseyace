# The ps3kit runtime, included by the generated CMakeLists.txt.
#   ps3kit_core  guest memory, dispatch, the loader, imports and lv2 system calls,
#                the system libraries, the renderer (SDL3, OpenGL 4.5)
#   ps3boot      the process start: ps3boot GAME.elf
# A target links ps3kit_core, then recomp. ps3kit_core is an object library
# so that every registration (PS3_HLE, LV2_SYSCALL) is linked in.
set(_rt ${CMAKE_CURRENT_LIST_DIR})
add_library(ps3kit_core OBJECT ${_rt}/core.cpp ${_rt}/mem.cpp ${_rt}/elf.cpp ${_rt}/hle.cpp
            ${_rt}/lv2.cpp ${_rt}/sysprx.cpp ${_rt}/thread.cpp ${_rt}/sync.cpp
            ${_rt}/intr.cpp ${_rt}/gcm.cpp ${_rt}/sysutil.cpp ${_rt}/fs.cpp ${_rt}/game.cpp ${_rt}/psf.cpp ${_rt}/savedata.cpp
            ${_rt}/audio.cpp ${_rt}/pad.cpp ${_rt}/spursjq.cpp ${_rt}/video.cpp ${_rt}/rsxcap.cpp ${_rt}/rsxgl.cpp
            ${_rt}/vpglsl.cpp ${_rt}/fpglsl.cpp ${_rt}/sail.cpp ${_rt}/mpeg2.cpp)
# the movie decoder and its colour conversion run in real time whatever the build
set_source_files_properties(${_rt}/mpeg2.cpp ${_rt}/sail.cpp PROPERTIES COMPILE_OPTIONS -O2)
target_include_directories(ps3kit_core PUBLIC ${_rt})
find_package(Threads REQUIRED)
find_package(SDL3 REQUIRED CONFIG)
target_link_libraries(ps3kit_core PUBLIC Threads::Threads SDL3::SDL3)
add_executable(ps3boot ${_rt}/boot.cpp)
# mpeg2test MOVIE OUT.yuv: the decoder alone, to compare it with another
add_executable(mpeg2test EXCLUDE_FROM_ALL ${_rt}/mpeg2test.cpp ${_rt}/mpeg2.cpp)
target_compile_options(mpeg2test PRIVATE -O2)
target_link_libraries(ps3boot ps3kit_core recomp)
# recompiled code recurses as deeply as the game does, on the host's stack
if(WIN32)
  target_link_options(ps3boot PRIVATE -Wl,--stack,268435456)
  target_link_libraries(ps3boot winmm)
endif()
