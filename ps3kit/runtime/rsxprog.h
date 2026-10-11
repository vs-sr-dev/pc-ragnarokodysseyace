// ps3kit runtime — the RSX's two kinds of program, translated to GLSL 4.50.
//
// A vertex program is 128-bit instructions from the transform program
// memory (uploaded through NV4097_SET_TRANSFORM_PROGRAM); each pairs a
// vector and a scalar operation. A fragment program is 128-bit instructions
// in RSX memory, every 32-bit word stored with its 16-bit halves swapped,
// and an instruction that reads a constant is followed by the constant.
//
// The translations take their words already decoded (host order, halves
// put back) and name what the GLSL expects of the renderer:
//   vertex:   in vec4 in0..in15 (location = attribute), uniform vec4 vc[468],
//             uniform vec4 vp_scale, vp_offset, vp_clip (viewport and surface);
//             out vec4 at locations 1..15, the output registers o1..o15.
//   fragment: in vec4 at locations 1..15; uniform vec4 fc[] (the inline
//             constants, in the order fp_translate lists them); sampler
//             tex0..tex15; uniform vec4 fp_wpos (scale_y, bias_y, x, y offsets),
//             uniform ivec4 fp_alpha (enable, func, 0, 0), uniform float fp_alpha_ref;
//             out vec4 at locations 0..3.
#pragma once
#include <cstdint>
#include <string>
#include <vector>

struct VPConfig {
    uint32_t start = 0;                 // NV4097_SET_TRANSFORM_PROGRAM_START
    uint32_t tex_dims = 0;              // 2 bits per vertex texture unit: 0 1D, 1 2D, 2 3D, 3 cube
};

struct FPConfig {
    uint32_t ctrl = 0;                  // NV4097_SET_SHADER_CONTROL
    uint32_t tex_dims = 0;              // 2 bits per texture unit: 0 1D, 1 2D, 2 3D, 3 cube
    uint32_t tc_2d = 0;                 // texture coordinates in 2D mode (NV4097_SET_TEX_COORD_CONTROL bit 0)
};

struct ProgramText {
    std::string glsl;
    std::vector<uint32_t> literals;     // fragment: the word index of each inline constant, in fc[] order
    std::vector<std::string> problems;  // what the translation could not express
};

ProgramText vp_translate(const uint32_t* prog, uint32_t ninstr, const VPConfig& cfg);
// The fragment program's length in words, constants included; 0 if no
// instruction ends it within max_words.
uint32_t fp_length(const uint32_t* words, uint32_t max_words);
// The word index of each inline constant, in fc[] order.
std::vector<uint32_t> fp_literal_words(const uint32_t* words, uint32_t nwords);
ProgramText fp_translate(const uint32_t* words, uint32_t nwords, const FPConfig& cfg);
// A fragment program word as it is stored in RSX memory, put back in order.
static inline uint32_t fp_word(uint32_t stored_be) { return stored_be << 16 | stored_be >> 16; }
