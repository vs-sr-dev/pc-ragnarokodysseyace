// ps3kit runtime — an MPEG-2 program stream reader: packs and PES packets
// from a file, one elementary stream's payload out. PAMF, the system's movie
// container, is a Sony header over exactly such a stream.
#pragma once
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

class MpegPsReader {
public:
    ~MpegPsReader() { close(); }
    bool open(const std::string& path, uint64_t offset) {
        close();
        f_ = std::fopen(path.c_str(), "rb");
        if (!f_) return false;
#ifdef _WIN32
        _fseeki64(f_, (long long)offset, SEEK_SET);
#else
        fseeko(f_, (off_t)offset, SEEK_SET);
#endif
        buf_.clear();
        pos_ = 0;
        eof_ = false;
        return true;
    }
    void close() {
        if (f_) std::fclose(f_);
        f_ = nullptr;
    }
    // Appends the payload of the next PES packets of `stream_id` to `out`,
    // at least `want` bytes unless the stream ends. False at the end.
    bool read(uint8_t stream_id, std::vector<uint8_t>& out, size_t want) {
        size_t got = 0;
        while (got < want) {
            if (!fill(16)) return got > 0;
            const uint8_t* p = &buf_[pos_];
            if (p[0] || p[1] || p[2] != 1) { ++pos_; continue; }   // resynchronise
            uint8_t id = p[3];
            if (id == 0xBA) {            // pack header: MPEG-2 (14 bytes and stuffing) or MPEG-1 (12)
                if ((p[4] >> 6) == 1) {
                    if (!fill(14)) return got > 0;
                    pos_ += 14 + (buf_[pos_ + 13] & 7);
                } else {
                    pos_ += 12;
                }
            } else if (id == 0xB9) {     // end of the program stream
                pos_ += 4;
            } else if (id >= 0xBB) {
                size_t len = (size_t)p[4] << 8 | p[5];
                if (!fill(6 + len)) return got > 0;
                p = &buf_[pos_];
                if (id == stream_id && len >= 3 && (p[6] >> 6) == 2) {
                    size_t hdr = 9 + p[8];
                    if (hdr <= 6 + len) {
                        out.insert(out.end(), p + hdr, p + 6 + len);
                        got += 6 + len - hdr;
                    }
                }
                pos_ += 6 + len;
            } else {
                ++pos_;
            }
        }
        return true;
    }

private:
    bool fill(size_t n) {
        if (pos_ + n <= buf_.size()) return true;
        buf_.erase(buf_.begin(), buf_.begin() + pos_);
        pos_ = 0;
        while (buf_.size() < n && !eof_) {
            size_t old = buf_.size();
            buf_.resize(old + 65536);
            size_t r = f_ ? std::fread(&buf_[old], 1, 65536, f_) : 0;
            buf_.resize(old + r);
            if (r == 0) eof_ = true;
        }
        return buf_.size() >= n;
    }
    FILE* f_ = nullptr;
    std::vector<uint8_t> buf_;
    size_t pos_ = 0;
    bool eof_ = false;
};
