// mpeg2test — decode a movie's video to raw 4:2:0 frames, to compare the
// decoder against another one.
//
//     mpeg2test MOVIE OUT.yuv [--offset BYTES] [--frames N]
//
// MOVIE is a program stream (a .pam: --offset 2048 or more, the PAMF header)
// or an elementary stream (.m2v, detected by its first start code).
#include "mpeg2.h"
#include "mpegps.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage: mpeg2test MOVIE OUT.yuv [--offset BYTES] [--frames N]\n");
        return 2;
    }
    uint64_t offset = 0;
    long max_frames = -1;
    for (int i = 3; i + 1 < argc; i += 2) {
        if (!std::strcmp(argv[i], "--offset")) offset = std::strtoull(argv[i + 1], nullptr, 0);
        else if (!std::strcmp(argv[i], "--frames")) max_frames = std::strtol(argv[i + 1], nullptr, 0);
    }
    FILE* out = std::fopen(argv[2], "wb");
    if (!out) { std::perror(argv[2]); return 1; }
    Mpeg2Decoder dec;
    long frames = 0;
    dec.on_picture = [&](const Mpeg2Picture& p) {
        if (max_frames >= 0 && frames >= max_frames) return;
        for (int y = 0; y < p.height; ++y) std::fwrite(p.y + (size_t)y * p.y_stride, 1, p.width, out);
        for (int y = 0; y < p.height / 2; ++y) std::fwrite(p.cb + (size_t)y * p.c_stride, 1, p.width / 2, out);
        for (int y = 0; y < p.height / 2; ++y) std::fwrite(p.cr + (size_t)y * p.c_stride, 1, p.width / 2, out);
        ++frames;
    };
    auto t0 = std::chrono::steady_clock::now();
    FILE* probe = std::fopen(argv[1], "rb");
    if (!probe) { std::perror(argv[1]); return 1; }
    uint8_t head[4] = {};
    std::fseek(probe, (long)offset, SEEK_SET);
    size_t got = std::fread(head, 1, 4, probe);
    bool es = got == 4 && !head[0] && !head[1] && head[2] == 1 && head[3] == 0xB3;
    if (es) {
        std::fseek(probe, (long)offset, SEEK_SET);
        std::vector<uint8_t> chunk(1 << 16);
        size_t n;
        while ((n = std::fread(chunk.data(), 1, chunk.size(), probe)) > 0 && (max_frames < 0 || frames < max_frames))
            dec.push(chunk.data(), n);
        std::fclose(probe);
    } else {
        std::fclose(probe);
        MpegPsReader ps;
        if (!ps.open(argv[1], offset)) { std::perror(argv[1]); return 1; }
        std::vector<uint8_t> v;
        while (max_frames < 0 || frames < max_frames) {
            v.clear();
            if (!ps.read(0xE0, v, 1 << 16)) break;
            dec.push(v.data(), v.size());
        }
    }
    dec.flush();
    std::fclose(out);
    double s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::fprintf(stderr, "%ld frames in %.2f s (%.1f fps), %u errors\n", frames, s, frames / s, dec.errors());
    return 0;
}
