#!/usr/bin/env python3
"""Apply the MINI LCD read-mode fix to Prusa's st7789v.cpp (issue prusa3d/Prusa-Firmware-Buddy#3277).

Usage: apply.py <path to src/guiapi/src/st7789v.cpp>

It edits by function, not by line, so it keeps working when the code around it changes. If a function it
needs is not there any more, it stops with an error, so the build fails and nothing wrong is published.
"""
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
src = path.read_text()


def fail(why):
    sys.exit(f"apply.py: {why} in {path}; the fix needs updating for this firmware version")


if "st7789v_cmd_rd_half_duplex" in src:
    fail("already patched")

# The SPI handle, as Prusa's own read uses it (`spi_handle_lcd` in 8.x, `&SPI_HANDLE_FOR(lcd)` in 6.x).
m = re.search(r"HAL_SPI_TransmitReceive\(\s*([^,]+?)\s*,\s*data_to_write", src)
if not m:
    fail("st7789v_cmd_rd's HAL_SPI_TransmitReceive not found")
handle = m.group(1)

# Find a top-level function by its signature, up to its closing brace at column 0.
def function_span(signature):
    start = src.find(signature)
    if start < 0:
        fail(f"`{signature}` not found")
    end = src.find("\n}\n", start)
    if end < 0:
        fail(f"end of `{signature}` not found")
    return start, end + 3


HALF_DUPLEX = """
/// Like st7789v_cmd_rd, but for displays that answer on SDA (half duplex, IM3 low) instead of SDO.
/// Many third-party MINI displays are wired so. The command goes out on MOSI, then the SPI is switched
/// to one-line (bidirectional) mode and the answer is read back on the same MOSI/SDA line.
static void st7789v_cmd_rd_half_duplex(uint8_t cmd, uint8_t *pdata) {
    uint16_t tmp_flg = st7789v_flg; // save flags
    if (st7789v_flg & FLG_CS) {
        st7789v_clr_cs(); // CS = L
    }
    if (st7789v_flg & FLG_RS) {
        st7789v_clr_rs(); // RS = L
    }
    SPI_HandleTypeDef *hspi = HANDLE;
    HAL_SPI_Transmit(hspi, &cmd, 1, HAL_MAX_DELAY);
    const uint32_t direction = hspi->Init.Direction;
    __HAL_SPI_DISABLE(hspi);
    hspi->Init.Direction = SPI_DIRECTION_1LINE;
    SET_BIT(hspi->Instance->CR1, SPI_CR1_BIDIMODE);
    HAL_SPI_Receive(hspi, pdata, ST7789V_MAX_COMMAND_READ_LENGHT, 10);
    __HAL_SPI_DISABLE(hspi);
    CLEAR_BIT(hspi->Instance->CR1, SPI_CR1_BIDIMODE | SPI_CR1_BIDIOE);
    hspi->Init.Direction = direction;
    __HAL_SPI_CLEAR_OVRFLAG(hspi);
    if (tmp_flg & FLG_CS) {
        st7789v_set_cs();
    }
}
""".replace("HANDLE", handle)

CHECK = """// How this display answers a read (third-party displays, issue #3277). Found once, on the first checks.
enum class ReadMode : uint8_t {
    unknown, ///< not found yet
    full_duplex, ///< answers on SDO (original Prusa display): Prusa's own check
    half_duplex, ///< answers on SDA: checked against what it answered when it was known good
    none, ///< no usable answer either way: no periodic check (it would reset the display every 2 s)
};
static ReadMode st7789v_read_mode = ReadMode::unknown;
static uint8_t st7789v_read_failures = 0;
static uint8_t st7789v_half_duplex_good[ST7789V_MAX_COMMAND_READ_LENGHT] = {};
/// Reset-and-check rounds before a display that never answers is taken as one that cannot.
static constexpr uint8_t ST7789V_READ_ATTEMPTS = 3;

static bool st7789v_full_duplex_ok() {
    uint8_t pdata[ST7789V_MAX_COMMAND_READ_LENGHT] = { 0x00 };
    st7789v_cmd_rd(CMD_MADCTLRD, pdata);
    return pdata[1] == 0xE0 || pdata[1] == 0xF0 || pdata[1] == 0xF8;
}

/// A half-duplex answer is usable when two reads agree and the line is not stuck high or low.
static bool st7789v_half_duplex_answer(uint8_t *answer) {
    uint8_t second[ST7789V_MAX_COMMAND_READ_LENGHT] = { 0x00 };
    st7789v_cmd_rd_half_duplex(CMD_MADCTLRD, answer);
    st7789v_cmd_rd_half_duplex(CMD_MADCTLRD, second);
    if (memcmp(answer, second, ST7789V_MAX_COMMAND_READ_LENGHT) != 0) {
        return false;
    }
    bool all_low = true, all_high = true;
    for (uint8_t i = 0; i < ST7789V_MAX_COMMAND_READ_LENGHT; i++) {
        all_low &= answer[i] == 0x00;
        all_high &= answer[i] == 0xFF;
    }
    return !all_low && !all_high;
}

bool st7789v_is_reset_required() {
    switch (st7789v_read_mode) {
    case ReadMode::full_duplex:
        return !st7789v_full_duplex_ok();
    case ReadMode::half_duplex: {
        uint8_t pdata[ST7789V_MAX_COMMAND_READ_LENGHT] = { 0x00 };
        st7789v_cmd_rd_half_duplex(CMD_MADCTLRD, pdata);
        return memcmp(pdata, st7789v_half_duplex_good, ST7789V_MAX_COMMAND_READ_LENGHT) != 0;
    }
    case ReadMode::none:
        return false;
    case ReadMode::unknown:
        break;
    }
    if (st7789v_full_duplex_ok()) {
        st7789v_read_mode = ReadMode::full_duplex;
        return false;
    }
    if (st7789v_half_duplex_answer(st7789v_half_duplex_good)) {
        st7789v_read_mode = ReadMode::half_duplex;
        return false;
    }
    // No answer: the display may really need a reset (Prusa's behaviour), a few times; after that it is
    // a display that cannot answer, and resetting it every 2 s is the flashing of issue #3277.
    if (++st7789v_read_failures >= ST7789V_READ_ATTEMPTS) {
        st7789v_read_mode = ReadMode::none;
        return false;
    }
    return true;
}
"""

# Prusa's check must still be the one this fix was made for.
s, e = function_span("bool st7789v_is_reset_required() {")
old_check = src[s:e]
for needed in ("st7789v_cmd_rd(CMD_MADCTLRD", "0xE0", "0xF0", "0xF8"):
    if needed not in old_check:
        fail(f"st7789v_is_reset_required changed (no `{needed}`)")
src = src[:s] + CHECK + src[e:]

_, e = function_span("void st7789v_cmd_rd(uint8_t cmd, uint8_t *pdata) {")
src = src[:e] + HALF_DUPLEX + src[e:]

if "#include <string.h>" not in src:
    src = "#include <string.h>\n" + src

path.write_text(src)
print(f"apply.py: patched {path} (SPI handle {handle})")
