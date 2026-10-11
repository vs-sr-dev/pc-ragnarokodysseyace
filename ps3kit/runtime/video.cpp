// ps3kit runtime — the renderer: a window, and the RSX's record (rsx.h)
// executed with OpenGL 4.5.
//
// It runs on the host's main thread, which owns the window and the GL
// context; the game runs on its own threads and hands over a record on each
// flip, at most frames_ahead flips ahead.
//
// Render targets live on the host GPU: each colour or depth surface the game
// names is a texture, found again by where it is in RSX memory (location and
// offset) and its size and format. Rows are stored top first, as the RSX
// stores them. A flip shows the colour surface at the display buffer's
// offset; a display buffer no surface has been drawn to is read from guest
// memory, as the RSX would scan it out.
#include "rsx.h"
#include "gl.h"
#include "rt.h"
#include <SDL3/SDL.h>
#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <filesystem>
#include <mutex>
#include <string>
#include <unordered_map>

#define PS3KIT_GL_DEFINE(T, n) T n = nullptr;
PS3KIT_GL_FUNCS(PS3KIT_GL_DEFINE)
#undef PS3KIT_GL_DEFINE

namespace {
VideoOptions opt;
using Clock = std::chrono::steady_clock;

// ---- the queue from the game ------------------------------------------------------------------
struct Chunk { std::vector<uint8_t> data; int flips = 0; };
std::mutex qmx;
std::condition_variable q_space;
std::deque<Chunk> q;
int q_flips = 0;
SDL_Semaphore* wake = nullptr;

// ---- surfaces -----------------------------------------------------------------------------------
struct Surface { GLuint tex = 0, fbo = 0; int w = 0, h = 0; GLenum fmt = 0; };
std::unordered_map<uint64_t, Surface> colors, depths;     // by location << 32 | offset
Surface scanout;                                          // a display buffer read from guest memory
RsxSurface surf{};
SDL_Window* win = nullptr;

struct Counters { uint64_t flips, presents, clears, surfaces; } cnt;

uint64_t key(uint32_t dma, uint32_t offset) { return (uint64_t)(dma == 0xFEED0001u) << 32 | offset; }

GLenum color_format(uint32_t f) {
    switch (f & 0x1F) {
    case 3: return GL_RGB565;
    case 9: return GL_R8;
    case 10: return GL_RG8;
    case 11: return GL_RGBA16F;
    case 12: return GL_RGBA32F;
    case 13: return GL_R32F;
    default: return GL_RGBA8;                             // the 5551s, the 8888s
    }
}

Surface& surface(std::unordered_map<uint64_t, Surface>& m, uint64_t k, int w, int h, GLenum fmt, GLenum attach) {
    Surface& s = m[k];
    if (s.tex && s.w == w && s.h == h && s.fmt == fmt) return s;
    if (s.tex) { glDeleteTextures(1, &s.tex); glDeleteFramebuffers(1, &s.fbo); }
    s = Surface{0, 0, w, h, fmt};
    glCreateTextures(GL_TEXTURE_2D, 1, &s.tex);
    glTextureStorage2D(s.tex, 1, fmt, w, h);
    glCreateFramebuffers(1, &s.fbo);
    glNamedFramebufferTexture(s.fbo, attach, s.tex, 0);
    ++cnt.surfaces;
    rt_log("video: %s surface %s:%X, %dx%d, format %X", attach == GL_COLOR_ATTACHMENT0 ? "colour" : "depth",
           (k >> 32) ? "main" : "local", (uint32_t)k, w, h, fmt);
    return s;
}

int surf_w() { return surf.clip_x + surf.clip_w; }
int surf_h() { return surf.clip_y + surf.clip_h; }

// The colour targets the surface registers enable, as indices 0..3 (A..D).
int targets(int out[4]) {
    switch (surf.target) {
    case 0x01: out[0] = 0; return 1;
    case 0x02: out[0] = 1; return 1;
    case 0x13: out[0] = 0; out[1] = 1; return 2;
    case 0x17: out[0] = 0; out[1] = 1; out[2] = 2; return 3;
    case 0x1F: out[0] = 0; out[1] = 1; out[2] = 2; out[3] = 3; return 4;
    default: return 0;
    }
}

void clear(const RsxClear& c) {
    ++cnt.clears;
    int w = surf_w(), h = surf_h();
    if (w <= 0 || h <= 0) return;
    glEnable(GL_SCISSOR_TEST);
    glScissor(c.x, c.y, c.w, c.h);                        // rows top first: y counts from the top
    if (c.mask & 0xF0) {
        float col[4] = {(c.color >> 16 & 0xFF) / 255.0f, (c.color >> 8 & 0xFF) / 255.0f, (c.color & 0xFF) / 255.0f,
                        (c.color >> 24) / 255.0f};
        glColorMask(c.mask & 0x10, c.mask & 0x20, c.mask & 0x40, c.mask & 0x80);
        int t[4], n = targets(t);
        for (int i = 0; i < n; ++i) {
            Surface& s = surface(colors, key(surf.color_dma[t[i]], surf.color_offset[t[i]]), w, h,
                                 color_format(surf.format), GL_COLOR_ATTACHMENT0);
            glClearNamedFramebufferfv(s.fbo, GL_COLOR, 0, col);
        }
        glColorMask(1, 1, 1, 1);
    }
    if (c.mask & 3) {
        bool z16 = (surf.format >> 5 & 7) == 1;
        Surface& s = surface(depths, key(surf.zeta_dma, surf.zeta_offset), w, h,
                             z16 ? GL_DEPTH_COMPONENT16 : GL_DEPTH24_STENCIL8,
                             z16 ? GL_DEPTH_ATTACHMENT : GL_DEPTH_STENCIL_ATTACHMENT);
        float depth = z16 ? (c.zstencil & 0xFFFF) / 65535.0f : (c.zstencil >> 8) / 16777215.0f;
        glDepthMask(c.mask & 1);
        glStencilMask((c.mask & 2) ? 0xFF : 0);
        if (z16) glClearNamedFramebufferfv(s.fbo, GL_DEPTH, 0, &depth);
        else glClearNamedFramebufferfi(s.fbo, GL_DEPTH_STENCIL, 0, depth, (GLint)(c.zstencil & 0xFF));
        glDepthMask(1);
        glStencilMask(0xFF);
    }
    glDisable(GL_SCISSOR_TEST);
}

// ---- frames to PNG (stored deflate: no compression, no dependency) ------------------------------
uint32_t crc32(const uint8_t* p, size_t n, uint32_t c = 0) {
    static uint32_t t[256];
    if (!t[1]) for (uint32_t i = 0; i < 256; ++i) { uint32_t v = i; for (int k = 0; k < 8; ++k) v = v & 1 ? 0xEDB88320u ^ v >> 1 : v >> 1; t[i] = v; }
    c = ~c;
    while (n--) c = t[(c ^ *p++) & 0xFF] ^ c >> 8;
    return ~c;
}

void write_png(const std::string& path, int w, int h, const std::vector<uint8_t>& rgb) {
    std::vector<uint8_t> raw, z, out;
    for (int y = 0; y < h; ++y) {
        raw.push_back(0);
        raw.insert(raw.end(), rgb.begin() + (size_t)y * w * 3, rgb.begin() + (size_t)(y + 1) * w * 3);
    }
    z = {0x78, 0x01};
    uint32_t a = 1, b = 0;
    for (size_t i = 0; i < raw.size(); i += 65535) {
        size_t n = std::min<size_t>(65535, raw.size() - i);
        z.push_back(i + n == raw.size());
        z.push_back(n & 0xFF); z.push_back(n >> 8); z.push_back(~n & 0xFF); z.push_back((~n >> 8) & 0xFF);
        z.insert(z.end(), raw.begin() + i, raw.begin() + i + n);
    }
    for (uint8_t v : raw) { a = (a + v) % 65521; b = (b + a) % 65521; }
    for (int s = 24; s >= 0; s -= 8) z.push_back((b << 16 | a) >> s & 0xFF);
    auto be32 = [&](uint32_t v) { for (int s = 24; s >= 0; s -= 8) out.push_back(v >> s & 0xFF); };
    auto chunk = [&](const char* type, const std::vector<uint8_t>& d) {
        be32((uint32_t)d.size());
        size_t at = out.size();
        out.insert(out.end(), type, type + 4);
        out.insert(out.end(), d.begin(), d.end());
        be32(crc32(out.data() + at, d.size() + 4));
    };
    static const uint8_t sig[] = {0x89, 'P', 'N', 'G', '\r', '\n', 0x1A, '\n'};
    out.insert(out.end(), sig, sig + 8);
    std::vector<uint8_t> ihdr;
    for (uint32_t v : {(uint32_t)w, (uint32_t)h}) for (int s = 24; s >= 0; s -= 8) ihdr.push_back(v >> s & 0xFF);
    ihdr.insert(ihdr.end(), {8, 2, 0, 0, 0});            // 8-bit RGB
    chunk("IHDR", ihdr);
    chunk("IDAT", z);
    chunk("IEND", {});
    if (FILE* f = std::fopen(path.c_str(), "wb")) { std::fwrite(out.data(), 1, out.size(), f); std::fclose(f); }
}

void dump(const Surface& s) {
    std::vector<uint8_t> rgba((size_t)s.w * s.h * 4), rgb((size_t)s.w * s.h * 3);
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glGetTextureImage(s.tex, 0, GL_RGBA, GL_UNSIGNED_BYTE, (GLsizei)rgba.size(), rgba.data());
    for (size_t i = 0; i < (size_t)s.w * s.h; ++i) std::memcpy(&rgb[i * 3], &rgba[i * 4], 3);
    char name[64];
    std::snprintf(name, sizeof name, "/flip%06llu.png", (unsigned long long)cnt.flips);
    std::filesystem::create_directories(opt.dump_dir);
    write_png(std::string(opt.dump_dir) + name, s.w, s.h, rgb);
}

// A flip: the colour surface at the display buffer, or the buffer as guest
// memory holds it, drawn to the window at the display's shape.
void flip(const RsxFlip& f) {
    ++cnt.flips;
    const Surface* src = nullptr;
    auto it = colors.find(key(0xFEED0000u, f.offset));
    if (it != colors.end()) src = &it->second;
    else if (f.width && f.height) {
        if (scanout.w != (int)f.width || scanout.h != (int)f.height) {
            if (scanout.tex) { glDeleteTextures(1, &scanout.tex); glDeleteFramebuffers(1, &scanout.fbo); }
            scanout = Surface{0, 0, (int)f.width, (int)f.height, GL_RGBA8};
            glCreateTextures(GL_TEXTURE_2D, 1, &scanout.tex);
            glTextureStorage2D(scanout.tex, 1, GL_RGBA8, scanout.w, scanout.h);
            glCreateFramebuffers(1, &scanout.fbo);
            glNamedFramebufferTexture(scanout.fbo, GL_COLOR_ATTACHMENT0, scanout.tex, 0);
        }
        glPixelStorei(GL_UNPACK_ROW_LENGTH, (GLint)(f.pitch / 4));
        glTextureSubImage2D(scanout.tex, 0, 0, 0, scanout.w, scanout.h, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8,
                            g_mem + mm::VIDEO + f.offset);       // X8R8G8B8, big-endian: X R G B in memory
        glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
        src = &scanout;
    }
    int ww = 0, wh = 0;
    SDL_GetWindowSizeInPixels(win, &ww, &wh);
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    glViewport(0, 0, ww, wh);
    float black[4] = {0, 0, 0, 1};
    glClearNamedFramebufferfv(0, GL_COLOR, 0, black);
    if (src) {
        float aspect = 16.0f / 9.0f;                              // the television (cellVideoOut)
        int dw = ww, dh = (int)(ww / aspect);
        if (dh > wh) { dh = wh; dw = (int)(wh * aspect); }
        int x0 = (ww - dw) / 2, y0 = (wh - dh) / 2;
        // top row first in the surface, bottom first in the window
        glBlitNamedFramebuffer(src->fbo, 0, 0, 0, src->w, src->h, x0, y0 + dh, x0 + dw, y0, GL_COLOR_BUFFER_BIT,
                               GL_LINEAR);
        if (opt.dump_dir && cnt.flips % (uint64_t)opt.dump_every == 1) dump(*src);
    }
    SDL_GL_SwapWindow(win);
    ++cnt.presents;
}

void exec(const std::vector<uint8_t>& d) {
    size_t i = 0;
    auto take = [&](void* p, size_t n) { std::memcpy(p, d.data() + i, n); i += n; };
    while (i < d.size()) {
        uint8_t op = d[i++];
        switch (op) {
        case RC_SURFACE: take(&surf, sizeof surf); break;
        case RC_CLEAR: { RsxClear c; take(&c, sizeof c); clear(c); break; }
        case RC_FLIP: { RsxFlip f; take(&f, sizeof f); flip(f); break; }
        default: rt_log("video: bad record byte %02X at %zu", op, i - 1); return;
        }
    }
}

bool gl_load() {
    bool ok = true;
#define PS3KIT_GL_LOAD(T, n)                                                   \
    n = reinterpret_cast<T>(SDL_GL_GetProcAddress(#n));                        \
    if (!n) { rt_log("video: no %s", #n); ok = false; }
    PS3KIT_GL_FUNCS(PS3KIT_GL_LOAD)
#undef PS3KIT_GL_LOAD
    return ok;
}

void APIENTRY gl_debug(GLenum, GLenum type, GLuint, GLenum severity, GLsizei, const GLchar* msg, const void*) {
    if (severity == GL_DEBUG_SEVERITY_NOTIFICATION) return;
    rt_log("gl: %s%s", type == GL_DEBUG_TYPE_ERROR ? "error: " : "", msg);
}

[[noreturn]] void quit() {
    rt_log("video: %llu flips, %llu presents, %llu clears, %llu surfaces", (unsigned long long)cnt.flips,
           (unsigned long long)cnt.presents, (unsigned long long)cnt.clears, (unsigned long long)cnt.surfaces);
    std::fflush(stdout);
    std::fflush(stderr);
    std::_Exit(0);
}
}  // namespace

void video_configure(const VideoOptions& o) { opt = o; }
bool video_enabled() { return opt.enabled; }

void video_submit(std::vector<uint8_t>& rec, int flips) {
    if (!opt.enabled) { rec.clear(); return; }
    {
        std::unique_lock<std::mutex> lk(qmx);
        q_space.wait(lk, [] { return q_flips < opt.frames_ahead; });
        q.push_back(Chunk{std::move(rec), flips});
        q_flips += flips;
    }
    rec = std::vector<uint8_t>();
    if (wake) SDL_SignalSemaphore(wake);
}

void video_run(const char* title) {
    if (!SDL_Init(SDL_INIT_VIDEO)) { rt_log("video: SDL_Init: %s", SDL_GetError()); std::_Exit(1); }
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 4);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 5);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    bool debug = std::getenv("PS3KIT_GLDEBUG") != nullptr;
    if (debug) SDL_GL_SetAttribute(SDL_GL_CONTEXT_FLAGS, SDL_GL_CONTEXT_DEBUG_FLAG);
    win = SDL_CreateWindow(title, 1280, 720, SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE);
    if (!win) { rt_log("video: SDL_CreateWindow: %s", SDL_GetError()); std::_Exit(1); }
    SDL_GLContext ctx = SDL_GL_CreateContext(win);
    if (!ctx) { rt_log("video: no OpenGL 4.5 context: %s", SDL_GetError()); std::_Exit(1); }
    SDL_GL_MakeCurrent(win, ctx);
    SDL_GL_SetSwapInterval(0);                                    // the vblank clock paces the flips
    if (!gl_load()) { rt_log("video: OpenGL functions missing"); std::_Exit(1); }
    rt_log("video: %s, %s", (const char*)glGetString(GL_RENDERER), (const char*)glGetString(GL_VERSION));
    if (debug) {
        glEnable(GL_DEBUG_OUTPUT_SYNCHRONOUS);
        glDebugMessageCallback(gl_debug, nullptr);
    }
    wake = SDL_CreateSemaphore(0);

    auto t0 = Clock::now(), t_title = t0;
    uint64_t flips_then = 0;
    for (;;) {
        SDL_Event e;
        while (SDL_PollEvent(&e)) {
            if (e.type == SDL_EVENT_QUIT) quit();
            if (e.type == SDL_EVENT_KEY_DOWN && !e.key.repeat &&
                (e.key.scancode == SDL_SCANCODE_F11 ||
                 ((e.key.scancode == SDL_SCANCODE_RETURN || e.key.scancode == SDL_SCANCODE_KP_ENTER) &&
                  (e.key.mod & SDL_KMOD_ALT))))
                SDL_SetWindowFullscreen(win, !(SDL_GetWindowFlags(win) & SDL_WINDOW_FULLSCREEN));
        }
        auto now = Clock::now();
        if (opt.quit_after > 0 && std::chrono::duration<double>(now - t0).count() > opt.quit_after) quit();
        if (now - t_title >= std::chrono::seconds(1)) {
            double s = std::chrono::duration<double>(now - t_title).count();
            char buf[256];
            std::snprintf(buf, sizeof buf, "%s  |  %.1f fps", title, (double)(cnt.flips - flips_then) / s);
            SDL_SetWindowTitle(win, buf);
            flips_then = cnt.flips;
            t_title = now;
        }
        Chunk c;
        {
            std::lock_guard<std::mutex> lk(qmx);
            if (!q.empty()) { c = std::move(q.front()); q.pop_front(); }
        }
        if (c.flips || !c.data.empty()) {
            exec(c.data);
            {
                std::lock_guard<std::mutex> lk(qmx);
                q_flips -= c.flips;
            }
            q_space.notify_all();
            continue;
        }
        SDL_WaitSemaphoreTimeout(wake, 5);
    }
}
