# GhostESP Revival / C5TAKO

Checkout: `Development-deki`, upstream commit `9ba53c60`, GhostESP `v2.2 BETA`.
Use **ESP-IDF v6.1**, matching this checkout's README and CI. The older
version suggestions in the upstream interactive `build.py` are stale.

After installing ESP-IDF for `esp32c5`, export its environment and build:

```powershell
$env:IDF_PATH = 'C:\Users\User\.cache\c5tako-idf\esp-idf-v6.1'
$env:IDF_TOOLS_PATH = 'C:\Users\User\.cache\c5tako-idf\tools'
. "$env:IDF_PATH\export.ps1"
python scripts/build_c5tako.py --jobs 2
```

The paths above identify the local toolchain installed for this task; change
them when using another ESP-IDF installation. ESP-IDF installation commands
are `python "$env:IDF_PATH\tools\idf_tools.py" install --targets esp32c5` and
`python "$env:IDF_PATH\tools\idf_tools.py" install-python-env`.

The script combines the existing XIAO C5 configuration with
`configs/sdkconfig.C5TAKO`, regenerates the board configuration, and builds in
`build/c5tako`. It uses the actual `flasher_args.json` image offsets, verifies
the merged bytes against every input image, checks partition/app bounds and
8MB flash limits, and writes the merged image plus SHA-256 report into
`local_builds/C5TAKO`. To repeat only merge/verification, add `--merge-only`.
Use `--jobs 1` if memory is limited. Build errors stop packaging.

Flash the resulting `GhostESP-*-C5TAKO-8MB-merged.bin` at **0x0**. No OTA
partition is required; the stock C5 factory/native-app XIP table is retained.
The board has 8MB flash and 8MB quad PSRAM.

Verified build: app 3,843,056 bytes in the 3,997,696-byte factory partition
(154,640 bytes / 4% free); merged image 3,908,592 bytes, within 8MB flash.
The local ESP-IDF build reports `ESP-IDF v6.1-dirty`; the exact version and
SHA-256 values are recorded in the adjacent JSON verification report.
Bootloader, partition table, and app are at 0x2000, 0x8000, and 0x10000.
All three image regions and every intervening 0xFF padding byte were also
verified independently after packaging.

| Signal | GPIO |
| --- | --- |
| SPI SCK / MOSI / MISO | 8 / 10 / 9 |
| ST7789 CS / DC / reset | 7 / 1 / none (software reset) |
| Backlight | 25, active high |
| SD CS | 5, same SPI2 bus as display |
| Left / Center / Up / Right / Down | 23 / 4 / 24 / 0 / 28, active low |
| Battery ADC / divider enable | 6 (ADC1 channel 5) / 26, active high |
| CC1101 CS / GDO0 / GDO2 | 2 / 12 / 11 (shared SPI2) |
| Buzzer | 3 low |
| User LED | 27, active low, held off |

Display starts at 240x240, RGB, inversion on, SPI mode 0 at 40MHz,
rotation 0 (`MADCTL=0x00`), explicit X/Y offsets 0/0. These match the working
Bruce/Marauder reference. Touch and optional peer UART are disabled because
the default peer pins 6/7 conflict with the battery/display wiring. CC1101
Sub-GHz (`CONFIG_HAS_SUBGHZ=y` on shared SPI2), BadBLE HID, and Chameleon Ultra
BLE NFC (`CONFIG_NFC_CHAMELEON=y`) are enabled using the enlarged 8MB factory
partition layout (`partitions_banshee_c5_factory.csv`).
The existing IDF SPI device arbitration and SD shared-bus paths are reused.

Battery reading reuses GhostESP's calibrated ADC path: enable divider, wait
at least 3ms, average 16 readings, disable divider even on read failure,
and multiply nominal voltage by 2. Percentage is estimated over 3.30–4.15V,
as in Marauder. Adjust `CONFIG_C5TAKO_BATTERY_SCALE_PERMILLE` against a
multimeter if needed. Charging status is unavailable without a status pin.

The original GhostESP UI uses its 240px row/layout rules. Up/Down scroll,
Center selects, Left goes back. On the main menu Left/Right move between
items; inside settings Left/Right change values and the Back row leaves.
Left cancels settings choice/confirmation popups. In terminal modes Left
uses the existing stop/exit path. Keyboard and setup wizard already support
the five-button joystick.

A successful build and byte verification do **not** establish hardware
operation. No board has been flashed or physically tested in this task.
On-device checks still required: cold boot with/without SD, display colors
and orientation, all five buttons, popup/back behavior, scan results,
battery voltage, and sustained shared-SPI display/SD operation.
