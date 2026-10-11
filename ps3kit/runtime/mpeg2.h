// ps3kit runtime — an MPEG-2 video decoder (ISO/IEC 13818-2), for the
// movies the system's players decode on the SPUs: frame pictures, 4:2:0,
// I, P and B, frame and field prediction and DCT. It takes the elementary
// stream in any pieces and hands out pictures in display order.
#pragma once
#include <cstddef>
#include <cstdint>
#include <functional>
#include <vector>

struct Mpeg2Picture {
    int width, height;                  // the display size the sequence states
    const uint8_t* y; const uint8_t* cb; const uint8_t* cr;
    int y_stride, c_stride;             // chroma is half size both ways
    int type;                           // 1 I, 2 P, 3 B
    int fields;                         // display duration in fields: 2, or 3/4/6 with repeat_first_field
    int frame_rate_code;                // 1..8, as the sequence header says
    int matrix;                         // matrix_coefficients: 1 BT.709 (also when unstated), 5/6 BT.601
};

class Mpeg2Decoder {
public:
    Mpeg2Decoder();
    ~Mpeg2Decoder();
    // Elementary stream bytes, in pieces of any size. Each picture completed
    // in display order goes to the callback, which must not keep its planes.
    void push(const uint8_t* data, size_t n);
    void flush();                       // the end of the stream: the last pictures out
    void reset();                       // a new stream
    std::function<void(const Mpeg2Picture&)> on_picture;
    // Problems met, by kind (unsupported syntax, damaged data), each counted once.
    uint32_t errors() const;

private:
    struct Impl;
    Impl* d;
};
