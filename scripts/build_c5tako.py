#!/usr/bin/env python3
"""Build with an exported ESP-IDF 6.1 environment; merge and verify flash images."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FLASH_SIZE = 8 * 1024 * 1024


def config_values(path):
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"(CONFIG_\w+)=(.*)", line)
        disabled = re.match(r"# (CONFIG_\w+) is not set", line)
        if match:
            values[match[1]] = match[2]
        elif disabled:
            values[disabled[1]] = "n"
    return values


def run(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True,
                   env={**os.environ, "PYTHONUTF8": "1"})


def merge(build):
    flash = json.loads((build / "flasher_args.json").read_text())
    config = config_values(build / "sdkconfig")
    for key, expected in config_values(ROOT / "configs/sdkconfig.C5TAKO").items():
        assert config.get(key, "n") == expected, f"Resolved board setting differs: {key}"
    assert config["CONFIG_IDF_TARGET"] == '"esp32c5"'
    assert config["CONFIG_ESPTOOLPY_FLASHSIZE"] == '"8MB"'
    assert config["CONFIG_BOARD_C5TAKO"] == "y"
    assert config["CONFIG_LV_HOR_RES_MAX"] == config["CONFIG_LV_VER_RES_MAX"] == "240"
    assert config.get("CONFIG_USE_TOUCHSCREEN", "n") == "n"
    assert config["CONFIG_LV_TFT_DISPLAY_X_OFFSET"] == config["CONFIG_LV_TFT_DISPLAY_Y_OFFSET"] == "0"
    parts = sorted((int(offset, 0), build / name) for offset, name in flash["flash_files"].items())
    partitions = (build / flash["partition-table"]["file"]).read_bytes()
    ranges = []
    for pos in range(0, len(partitions), 32):
        magic, kind, subtype, offset, size, label, flags = struct.unpack_from("<HBBII16sI", partitions, pos)
        if magic != 0x50AA:
            break
        assert offset + size <= FLASH_SIZE, "Partition exceeds 8MB"
        ranges.append((offset, offset + size, kind, label.rstrip(b"\0").decode()))
    for previous, current in zip(sorted(ranges), sorted(ranges)[1:]):
        assert previous[1] <= current[0], "Overlapping partitions"
    app_offset = int(flash["app"]["offset"], 0)
    app_path = build / flash["app"]["file"]
    assert any(start == app_offset and kind == 0 and app_path.stat().st_size <= end - start
               for start, end, kind, label in ranges), "App does not fit partition"
    version_header = (ROOT / "include/core/ghostesp_version.h").read_text()
    version = re.search(r'#define GHOSTESP_VERSION "([^"]+)"', version_header)[1]
    version = re.sub(r"[^A-Za-z0-9._-]+", "-", version)
    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    output = ROOT / "local_builds/C5TAKO"
    output.mkdir(parents=True, exist_ok=True)
    merged = output / f"GhostESP-{version}-{commit}-C5TAKO-8MB-merged.bin"
    arguments = [sys.executable, "-m", "esptool", "--chip", "esp32c5", "merge-bin",
                 "--output", merged]
    for offset, path in parts:
        arguments.extend([hex(offset), path])
    run(*arguments)
    data = merged.read_bytes()
    assert len(data) <= FLASH_SIZE, "Merged image exceeds 8MB"
    previous_end = 0
    images = []
    for offset, path in parts:
        source = path.read_bytes()
        assert previous_end <= offset, "Overlapping images"
        assert data[previous_end:offset] == b"\xff" * (offset - previous_end), "Invalid padding"
        assert data[offset:offset + len(source)] == source, f"Merge differs from {path}"
        previous_end = offset + len(source)
        images.append(dict(offset=hex(offset), file=str(path.relative_to(ROOT)),
                           size=len(source), sha256=hashlib.sha256(source).hexdigest()))
    report = dict(firmware=merged.name, flash_offset="0x0", flash_size=FLASH_SIZE,
                  size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  idf_version=subprocess.check_output([sys.executable, str(Path(os.environ["IDF_PATH"]) / "tools/idf.py"),
                                                       "--version"], text=True).strip(),
                  commit=commit, images=images, partitions=ranges, hardware_tested=False)
    merged.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Verified: {merged}\nApp: {app_path.stat().st_size:,} bytes; merged: {len(data):,} bytes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--merge-only", action="store_true")
    args = parser.parse_args()
    assert args.jobs > 0
    idf = Path(os.environ["IDF_PATH"])
    version_header = (idf / "components/esp_common/include/esp_idf_version.h").read_text()
    assert re.search(r"ESP_IDF_VERSION_MAJOR\s+6\b", version_header) and re.search(
        r"ESP_IDF_VERSION_MINOR\s+1\b", version_header), "Use ESP-IDF 6.1 for this checkout"
    build = ROOT / "build/c5tako"
    if not args.merge_only:
        build.mkdir(parents=True, exist_ok=True)
        values = config_values(ROOT / "configs/sdkconfig.xiao_esp32c5")
        values.update(config_values(ROOT / "configs/sdkconfig.C5TAKO"))
        # Choice values in the base must not override the board's selected choice.
        for prefix, selected in (("CONFIG_LV_TFT_DISPLAY_USER_CONTROLLER_", "ST7789"),
                                 ("CONFIG_LV_DISPLAY_ORIENTATION_", "PORTRAIT"),
                                 ("CONFIG_LV_TOUCH_CONTROLLER_", "NONE"),
                                 ("CONFIG_LV_TFT_SPI_CLK_DIVIDER_", "2")):
            for key in values:
                if key.startswith(prefix) and key != prefix + selected:
                    values[key] = "n"
        defaults = build / "sdkconfig.defaults"
        defaults.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
        (build / "sdkconfig").write_text(defaults.read_text())
        run(sys.executable, idf / "tools/idf.py", "-B", build,
            "-D", "IDF_TARGET=esp32c5", "-D", f"SDKCONFIG={build / 'sdkconfig'}",
            "-D", f"SDKCONFIG_DEFAULTS={defaults}", "reconfigure")
        run("cmake", "--build", build, "--parallel", args.jobs)
    merge(build)


if __name__ == "__main__":
    main()
