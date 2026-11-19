# MINI LCD fix

Prusa MINI firmware, built from [Prusa's own source](https://github.com/prusa3d/Prusa-Firmware-Buddy) with one patch for third-party displays (Fysetc, some BTT) that flash white every 2 seconds. See [Prusa-Firmware-Buddy#3277](https://github.com/prusa3d/Prusa-Firmware-Buddy/issues/3277).

Each new stable Prusa release is built here automatically: [Releases](../../releases).

## The cause

Since firmware 4.6.1 the MINI reads a register back from the display every 2 seconds. If the answer is wrong, it resets the display. That fixes a display that went white because of a loose cable or interference.

The original Prusa display answers on its SDO line. Many third-party displays are wired for half duplex (ST7789V pin IM3 low), and they answer on SDA instead. On those displays the check always fails, so the display is reset every 2 seconds.

## The patch

[patch/apply.py](patch/apply.py) changes only `src/guiapi/src/st7789v.cpp`. It edits by function, so it keeps fitting new firmware versions; if Prusa changes the check itself, the build stops instead of publishing something wrong. On the first checks after start-up, the firmware works out how this display answers:

| The display answers | What the firmware does |
|---|---|
| on SDO (original Prusa display) | Prusa's own check, unchanged |
| on SDA (half duplex) | It reads the answer back on SDA, and checks every 2 s against the answer it gave at start-up. A display that goes white is still reset. |
| not at all | It resets the display up to 3 times, as Prusa's firmware does. After that it stops the periodic check, so the display no longer flashes. |

Earlier builds (5.1.0 to 6.3.0, "no_reinit_lcd") switched the reset off completely. This patch keeps the reset for every display that can answer.

## Flashing

This is custom firmware. The MINI only accepts it after the appendix on the Buddy board has been broken off: see [Flashing custom firmware](https://help.prusa3d.com/article/flashing-custom-firmware-mini).

1. Put the `.bbf` for your language on a USB drive.
2. Press the reset button, then immediately press the knob twice.
3. Choose **FLASH** and press the knob.

You flash it at your own risk. It is not Prusa's firmware, and Prusa does not support it.

## License

GPL-3.0, like Prusa's firmware. The source is Prusa's tagged release plus the patch in this repository.
