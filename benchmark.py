"""Reproducible local Qwen image runs with wall time, logs and GPU telemetry."""
import argparse
import csv
import ctypes
from ctypes import wintypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import struct
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parent
PRESETS = [
    {"name": "draft-512-10", "size": 512, "steps": 10, "cfg": 1.0},
    {"name": "balanced-768-20", "size": 768, "steps": 20, "cfg": 1.0},
    {"name": "detail-1024-25", "size": 1024, "steps": 25, "cfg": 1.0},
    {"name": "quality-1024-40", "size": 1024, "steps": 40, "cfg": 1.0},
    {"name": "guidance-1024-25-cfg6", "size": 1024, "steps": 25, "cfg": 6.0},
    {"name": "decode-1024-25-tile512", "size": 1024, "steps": 25, "cfg": 1.0, "vae_tile_size": 512},
]


class MemoryStatus(ctypes.Structure):
    _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD)] + [(name, ctypes.c_ulonglong) for name in ["total_phys", "avail_phys", "total_page", "avail_page", "total_virtual", "avail_virtual", "avail_extended"]]


class ProcessMemory(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("page_faults", wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in ["peak_working_set", "working_set", "peak_paged_pool", "paged_pool", "peak_nonpaged_pool", "nonpaged_pool", "pagefile", "peak_pagefile", "private"]]


def memory(pid=None):
    info = MemoryStatus()
    info.length = ctypes.sizeof(info)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info))
    result = {"system_total_bytes": info.total_phys, "system_available_bytes": info.avail_phys}
    if pid:
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x410, False, pid)
        if handle:
            counters = ProcessMemory()
            counters.cb = ctypes.sizeof(counters)
            function = ctypes.windll.psapi.GetProcessMemoryInfo
            function.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemory), wintypes.DWORD]
            if function(handle, ctypes.byref(counters), counters.cb):
                result.update(process_peak_working_set_bytes=counters.peak_working_set, process_private_bytes=counters.private)
            kernel.CloseHandle(handle)
    return result


def dimensions(path):
    with path.open("rb") as stream:
        stream.read(16)
        return struct.unpack(">II", stream.read(8))


def execute(preset, executable, repeat, max_vram):
    suffix = "" if repeat == 1 else f"-repeat{repeat}"
    name = preset["name"] + suffix
    output = ROOT / "outputs" / f"{name}.png"
    log = ROOT / "logs" / f"{name}.log"
    gpu_csv = ROOT / "logs" / f"{name}-gpu.csv"
    result_file = ROOT / "results" / f"{name}.json"
    if result_file.exists():
        prior = json.loads(result_file.read_text())
        if prior.get("status") == "success" and output.exists():
            print(f"Already complete: {name}", flush=True)
            return prior
        raise RuntimeError(f"Previous failed result exists: {result_file}; choose a new repeat number for a fresh run")
    prompt_path = ROOT / preset.get("prompt_file", "prompt.txt")
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    command = [str(executable), "--diffusion-model", str(ROOT / "models/qwen-image-2.1-UC-Q4_K_M.gguf"),
               "--vae", str(ROOT / "models/qwen_image_2.1_vae_bf16.safetensors"),
               "--llm", str(ROOT / "models/Qwen3VL-8B-Instruct-Q4_K_M.gguf"),
               "--prompt", prompt, "--width", str(preset["size"]), "--height", str(preset["size"]),
               "--steps", str(preset["steps"]), "--cfg-scale", str(preset["cfg"]),
               "--seed", "42", "--sampling-method", "euler", "--scheduler", "simple",
               "--backend", "cuda0", "--auto-fit", "on", "--max-vram", str(max_vram),
               "--flash-attn", "auto", "--vae-tiling", "--output", str(output)]
    if "vae_tile_size" in preset:
        command += ["--vae-tile-size", str(preset["vae_tile_size"])]
    result = {**preset, "repeat": repeat, "seed": 42, "sampler": "euler", "scheduler": "simple",
              "max_vram_budget_gib": max_vram, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
              "vae_requested_tile_size_pixels": preset.get("vae_tile_size", 256),
              "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "image": str(output), "log": str(log), "gpu_csv": str(gpu_csv), "command": command,
              "timing_scope": "Fresh process wall time including model load, text encoding, sampling, VAE decode, save and cleanup; OS disk cache may be warm.",
              "memory_before": memory(), "status": "running"}
    result_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    env = os.environ.copy()
    env["PATH"] = str(executable.parent) + os.pathsep + env.get("PATH", "")
    print(f"Starting {name}: {preset['size']} square, {preset['steps']} steps, CFG {preset['cfg']}", flush=True)
    telemetry = gpu_csv.open("w", encoding="utf-8")
    gpu = subprocess.Popen(["nvidia-smi", "--query-gpu=timestamp,memory.used,utilization.gpu,temperature.gpu,power.draw", "--format=csv,noheader,nounits", "-l", "1"], stdout=telemetry, stderr=subprocess.DEVNULL)
    started = time.perf_counter()
    samples = []
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        last = started
        while process.poll() is None:
            sample = {"elapsed_seconds": time.perf_counter()-started, **memory(process.pid)}
            samples.append(sample)
            if time.perf_counter()-last >= 25:
                print(f"{name}: {sample['elapsed_seconds']:.0f}s elapsed", flush=True)
                last = time.perf_counter()
            if time.perf_counter()-started > 1800:
                process.kill()
                result["timeout"] = True
                break
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        exit_code = process.wait()
    elapsed = time.perf_counter()-started
    gpu.terminate()
    gpu.wait()
    telemetry.close()
    text = log.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
    result.update(elapsed_seconds=elapsed, exit_code=exit_code,
                  status="success" if exit_code == 0 and output.exists() else "failed",
                  memory_after=memory(), memory_samples=samples)
    if output.exists():
        result["actual_dimensions"] = dimensions(output)
    result["reported_timing_lines"] = [line for line in text.splitlines() if re.search(r"(completed|taken|loading|generation|sampling|encode|decode|total).*(\d+\.\d+\s*(s|ms|sec))", line, re.I)]
    readings = []
    for row in csv.reader(gpu_csv.read_text().splitlines()):
        if len(row) >= 5:
            try:
                readings.append({"vram_mib": float(row[1]), "utilization_percent": float(row[2]), "temperature_c": float(row[3]), "power_w": float(row[4])})
            except ValueError:
                pass
    if readings:
        result["peak_device_vram_mib"] = max(x["vram_mib"] for x in readings)
        result["peak_temperature_c"] = max(x["temperature_c"] for x in readings)
    result["peak_process_working_set_bytes"] = max((x.get("process_peak_working_set_bytes", 0) for x in samples), default=0)
    result_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"{name}: {result['status']}, {elapsed:.1f}s; log: {log.name}", flush=True)
    if result["status"] != "success":
        print(text[-6000:], flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preset", choices=[x["name"] for x in PRESETS] + ["all"], default="all")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--max-vram", type=float, default=7.0)
    args = parser.parse_args()
    for folder in ["outputs", "logs", "results"]:
        (ROOT / folder).mkdir(exist_ok=True)
    candidates = list((ROOT / "runtime").rglob("sd-cli.exe"))
    if not candidates:
        raise RuntimeError("CUDA runtime not installed")
    executable = candidates[0]
    hardware = {"platform": platform.platform(), "cpu": platform.processor(), "memory": memory(),
                "gpu": subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"], text=True).strip()}
    if not (ROOT / "hardware.json").exists():
        (ROOT / "hardware.json").write_text(json.dumps(hardware, indent=2), encoding="utf-8")
    for preset in PRESETS:
        if args.preset in ("all", preset["name"]):
            result = execute(preset, executable, args.repeat, args.max_vram)
            if result["status"] != "success":
                raise SystemExit(1)


if __name__ == "__main__":
    main()
