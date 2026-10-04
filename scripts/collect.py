#!/usr/bin/env python3
"""Capture ColorOS 17 diagnostic hardware fields with ADB; no third-party dependencies."""
import argparse
import json
import queue
import re
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

TAGS = ("Postman-StorageHealthCheckItem", "StorageHealthInfoService")
FIELDS = ("RecordTime", "MarketName", "DDRDev", "MemoryDev", "StorageDev", "StorageSize")
OUTPUT_NAMES = ("hardware-result.json", "hardware-evidence.txt")
CXSH_SOURCE = "https://www.gigabyte.com/lt/Motherboard/B650E-AORUS-STEALTH-ICE/support"


def usable(value):
    return bool(value and value.strip().casefold() not in {"null", "unknown", "none", "n/a"})


def device_field(raw, label):
    match = re.search(re.escape(label) + r":\s*([^|\r\n]+)", raw or "")
    return match.group(1).strip() if match else None


def parse_line(line):
    if "Postman-StorageHealthCheckItem:" not in line:
        return None
    match = re.search(r"health info map\s*:\s*\{([^{}\r\n]*)\}", line)
    if not match:
        return None
    pairs = re.split(r",\s*(?=[A-Za-z_]\w*\s*=)", match.group(1))
    fields = {}
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if separator and key.strip() in FIELDS:
            fields[key.strip()] = value.strip()
    ddr = fields.get("DDRDev")
    ufs = fields.get("MemoryDev")
    ram_vendor = device_field(ddr, "Device manufacture")
    ufs_vendor = device_field(ufs, "Device manufacture")
    if not usable(ram_vendor) and not usable(ufs_vendor):
        return None
    result = {
        "status": "complete" if usable(ram_vendor) and usable(ufs_vendor) else "partial",
        "source": "Postman-StorageHealthCheckItem / health info map",
        "record_time": fields.get("RecordTime"),
        "market_name": fields.get("MarketName"),
        "ram_manufacturer_reported": ram_vendor,
        "ram_type_reported": device_field(ddr, "Device version"),
        "ufs_manufacturer_reported": ufs_vendor,
        "ufs_model_reported": device_field(ufs, "Device version"),
        "storage_capacity_reported": fields.get("StorageSize"),
        "raw_hardware_fields": fields,
    }
    if ram_vendor and ram_vendor.casefold() == "cxsh":
        result["ram_manufacturer_interpretation"] = {
            "name": "CXMT / 长鑫存储",
            "basis": "外部名称对照：技嘉官方资料使用 CXSH (CXMT)",
            "source_url": CXSH_SOURCE,
        }
    return result


def parse_log(path):
    latest = None
    with path.open("r", encoding="utf-8-sig") as source:
        for line in source:
            result = parse_line(line)
            if result:
                latest = result
    return latest


class Adb:
    def __init__(self, executable, serial):
        self.executable = executable
        self.serial = serial

    def command(self, *arguments):
        prefix = [self.executable]
        if self.serial:
            prefix.extend(["-s", self.serial])
        return prefix + list(arguments)

    def run(self, *arguments):
        completed = subprocess.run(
            self.command(*arguments), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20,
        )
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"ADB 执行失败：{detail}")
        return completed.stdout.strip()

    def property(self, name):
        return self.run("shell", "getprop", name)

    def set_property(self, name, value):
        # ADB shell interprets the remote command; quote even an empty value.
        self.run("shell", f"setprop {name} {shlex.quote(value)}")
        if self.property(name) != value:
            raise RuntimeError(f"日志属性未成功设置：{name}")


def choose_device(executable, requested):
    listing = Adb(executable, None).run("devices", "-l")
    devices = {}
    for line in listing.splitlines():
        columns = line.split()
        if len(columns) >= 2 and not line.startswith("List of devices"):
            devices[columns[0]] = columns[1]
    if requested:
        if devices.get(requested) != "device":
            raise RuntimeError("指定设备未就绪，请确认连接与 USB 调试授权。")
        return Adb(executable, requested)
    if len(devices) != 1:
        raise RuntimeError("需要恰好一台设备；多设备请使用 --serial 指定。")
    serial, state = next(iter(devices.items()))
    if state != "device":
        raise RuntimeError(f"设备状态为 {state}，请先完成 ADB 授权。")
    return Adb(executable, serial)


def read_lines(process, messages):
    try:
        for line in process.stdout:
            messages.put(line)
    finally:
        messages.put(None)


def stop_capture(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    process.stdout.close()


def capture(adb, timeout):
    model = adb.property("ro.product.model")
    android = adb.property("ro.build.version.release")
    if not adb.run("shell", "pm", "path", "com.oplus.postmanservice"):
        raise RuntimeError("未找到 com.oplus.postmanservice，此系统不适用默认诊断路径。")
    print(f"设备型号：{model}；Android：{android}", flush=True)
    originals = {}
    process = None
    try:
        for tag in TAGS:
            key = "log.tag." + tag
            originals[key] = adb.property(key)
            print(f"待恢复原值：{key}={json.dumps(originals[key])}", flush=True)
            adb.set_property(key, "DEBUG")
        since = adb.run("shell", "date '+%m-%d %H:%M:%S.000'")
        process = subprocess.Popen(
            adb.command("logcat", "-T", since, "-v", "threadtime", "-s",
                        TAGS[0] + ":D", TAGS[1] + ":D", "*:S"),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace",
        )
        messages = queue.Queue()
        reader = threading.Thread(target=read_lines, args=(process, messages), daemon=True)
        reader.start()
        print("捕获已启动。请在手机管家常规检测中勾选‘性能’，点击‘开始检测’。", flush=True)
        deadline = time.monotonic() + timeout
        last_line = ""
        while time.monotonic() < deadline:
            try:
                line = messages.get(timeout=min(1, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if line is None:
                code = process.wait(timeout=3)
                raise RuntimeError(f"logcat 提前退出（{code}）：{last_line}")
            last_line = line.strip()
            result = parse_line(line)
            if result:
                result["device_model"] = model
                result["android_version"] = android
                result["capture_mode"] = "live"
                return result
        raise TimeoutError("未捕获到有效厂商字段。请核对入口、性能勾选项及启动顺序；不要据此猜厂家。")
    finally:
        cleanup_errors = []
        if process is not None:
            try:
                stop_capture(process)
            except (OSError, subprocess.SubprocessError) as error:
                cleanup_errors.append(f"停止本次 logcat 失败：{error}")
        for key, original in originals.items():
            try:
                adb.set_property(key, original)
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                cleanup_errors.append(f"恢复 {key} 失败，原值为 {json.dumps(original)}：{error}")
        if cleanup_errors:
            raise RuntimeError("\n".join(cleanup_errors))
        if originals:
            print("临时日志标签已恢复。", flush=True)


def save_result(result, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / OUTPUT_NAMES[0]
    evidence_path = output_dir / OUTPUT_NAMES[1]
    # Exclusive creation also prevents a concurrent run from replacing evidence.
    with json_path.open("x", encoding="utf-8") as target:
        target.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    fields = result["raw_hardware_fields"]
    evidence = "\n".join(f"{key}={fields[key]}" for key in FIELDS if key in fields)
    with evidence_path.open("x", encoding="utf-8") as target:
        target.write("Source: Postman-StorageHealthCheckItem / health info map\n" + evidence + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"已保存：{json_path.resolve()}\n已保存：{evidence_path.resolve()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default="adb", help="ADB 可执行文件路径")
    parser.add_argument("--serial", help="明确选择连接设备；不会写入分享结果")
    parser.add_argument("--timeout", type=int, default=180, help="实时捕获秒数，默认 180")
    parser.add_argument("--output-dir", type=Path, default=Path("output/phone-hardware-check"))
    parser.add_argument("--log", type=Path, help="离线解析已有 UTF8 日志；不使用 ADB")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    if any((args.output_dir / name).exists() for name in OUTPUT_NAMES):
        parser.error("输出目录已有硬件结果，请选择新的 --output-dir，避免覆盖证据。")
    if args.log:
        result = parse_log(args.log)
        if result is None:
            raise RuntimeError("日志中没有完整且含有效厂商字段的目标 map。")
        result["capture_mode"] = "offline"
    else:
        result = capture(choose_device(args.adb, args.serial), args.timeout)
    save_result(result, args.output_dir)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        main()
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        sys.exit(130)
    except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as error:
        print(f"错误：{error}", file=sys.stderr)
        sys.exit(1)
