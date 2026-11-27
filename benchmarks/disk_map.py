"""Windows baseline for Hub's disk map. Run from the repository root."""

import argparse
import ctypes
import inspect
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

from tools import diskmap


class MemoryCounters(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("page_faults", wintypes.DWORD)] + [
        (key, ctypes.c_size_t)
        for key in ("peak_working_set", "working_set", "quota_peak_paged", "quota_paged",
                    "quota_peak_nonpaged", "quota_nonpaged", "pagefile", "peak_pagefile")
    ]


def memory(handle=None):
    get_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_info.argtypes = (wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD)
    get_info.restype = wintypes.BOOL
    current = ctypes.windll.kernel32.GetCurrentProcess
    current.restype = wintypes.HANDLE
    counters = MemoryCounters()
    counters.size = ctypes.sizeof(counters)
    if not get_info(current() if handle is None else handle, ctypes.byref(counters), counters.size):
        raise ctypes.WinError()
    return counters


def measure(folder, operation):
    options = {"use_cache": True} if operation == "scan-cached" and "use_cache" in inspect.signature(diskmap.scan).parameters else {}
    if operation in ("scan-cached", "scan-repeat"):
        diskmap.scan(folder, **options)
        if operation == "scan-repeat":
            diskmap._cache.clear()
    before = memory()
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    payload = diskmap.files(folder) if operation == "files" else diskmap.scan(folder, **options)
    cpu, wall = time.process_time() - start_cpu, time.perf_counter() - start_wall
    after = memory()
    if payload["errors"] or payload["truncated"]:
        raise RuntimeError(f"Expected a complete benchmark scan: {payload['errors']}")
    count = len(payload["files"]) if operation == "files" else payload["files"]
    total = sum(item["size"] for item in payload["files"]) if operation == "files" else payload["total"]
    return {
        "wall_ms": wall * 1000,
        "cpu_ms": cpu * 1000,
        "cpu_one_core_pct": cpu / wall * 100,
        "rss_before_mib": before.working_set / 1024**2,
        "rss_after_mib": after.working_set / 1024**2,
        "rss_peak_mib": after.peak_working_set / 1024**2,
        "files": count,
        "logical_bytes": total,
    }


def fixture(root, count, wide):
    root.mkdir()
    for index in range(count):
        folder = root if wide else root / f"group-{index // 1000:03}" / f"batch-{index // 100 % 10:02}"
        if index % 100 == 0 and not wide:
            folder.mkdir(parents=True)
        (folder / f"file-{index:06}.bin").write_bytes(bytes(256))


def run(repeats, temp_dir, repeat_full=False, reference_root=None):
    cases = (
        ("nested-small", 2_000, False, ("scan",)),
        ("nested-large", 30_000, False, ("scan", "scan-cached")),
        ("wide-large", 30_000, True, ("scan", "files")),
    )
    roots = [Path.cwd()]
    if reference_root is not None:
        roots.append(reference_root.resolve())
    results = [[] for _ in roots]
    with tempfile.TemporaryDirectory(prefix="hub-bench-", dir=temp_dir) as directory:
        for name, count, wide, operations in cases:
            folder = Path(directory) / name
            fixture(folder, count, wide)
            ordered = ("scan", "scan-repeat", *operations[1:]) if repeat_full else operations
            for operation in ordered:
                samples = [[] for _ in roots]
                for repeat in range(repeats):
                    order = range(len(roots))
                    if repeat % 2:
                        order = reversed(order)
                    for index in order:
                        result = subprocess.check_output(
                            [sys.executable, "-m", "benchmarks.disk_map", "--worker", operation, str(folder)],
                            cwd=roots[index], text=True, timeout=90,
                        )
                        sample = json.loads(result)
                        if (sample["files"], sample["logical_bytes"]) != (count, count * 256):
                            raise RuntimeError(f"Fixture mismatch in {name}/{operation}: {sample}")
                        samples[index].append(sample)
                for target, rows in zip(results, samples, strict=True):
                    target.append({
                        "fixture": name, "operation": operation, "samples": rows,
                        "median": {key: statistics.median(s[key] for s in rows) for key in rows[0]},
                    })
    metadata = {
        "backend": "python", "os": platform.platform(), "python": platform.python_version(),
        "logical_cpus": os.cpu_count(), "fixture_drive": Path(temp_dir or tempfile.gettempdir()).resolve().anchor,
    }
    return [{**metadata, "results": rows} for rows in results]


def compare(before_path, after_path):
    before, after = (json.loads(Path(path).read_text(encoding="utf-8-sig"))
                     for path in (before_path, after_path))
    for key in ("os", "python", "logical_cpus", "fixture_drive"):
        if before[key] != after[key]:
            raise ValueError(f"Different benchmark environments: {key}")
    for old, new in zip(before["results"], after["results"], strict=True):
        keys = ("fixture", "operation")
        if any(old[key] != new[key] for key in keys):
            raise ValueError("Benchmark scenarios differ.")
        a, b = old["median"], new["median"]
        if (a["files"], a["logical_bytes"]) != (b["files"], b["logical_bytes"]):
            raise ValueError(f"Scan totals differ: {old['fixture']}/{old['operation']}")
        yield {
            **{key: old[key] for key in keys},
            "wall_ms_before": a["wall_ms"], "wall_ms_after": b["wall_ms"],
            "wall_change_pct": (b["wall_ms"] / a["wall_ms"] - 1) * 100,
            "cpu_ms_change": b["cpu_ms"] - a["cpu_ms"],
            "rss_peak_mib_change": b["rss_peak_mib"] - a["rss_peak_mib"],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--temp-dir", type=Path)
    parser.add_argument("--repeat-full", action="store_true", help="Measure repeat full scans as distinct scenarios.")
    parser.add_argument("--reference-root", type=Path, help="Run workers alternately in a reference source tree.")
    parser.add_argument("--reference-output", type=Path, help="Write the alternating reference samples to this JSON file.")
    parser.add_argument("--compare", nargs=2, metavar=("BASELINE", "CANDIDATE"))
    parser.add_argument("--worker", nargs=2, metavar=("OPERATION", "FOLDER"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.compare:
        print(json.dumps(list(compare(*args.compare)), indent=2))
        return
    if os.name != "nt":
        parser.error("Windows is required for working-set measurements.")
    if not 1 <= args.repeats <= 20:
        parser.error("--repeats must be between 1 and 20.")
    if args.worker and args.worker[0] not in ("scan", "scan-repeat", "scan-cached", "files"):
        parser.error("Unknown operation.")
    if bool(args.reference_root) != bool(args.reference_output):
        parser.error("--reference-root and --reference-output must be provided together.")
    if args.worker:
        result = measure(args.worker[1], args.worker[0])
    else:
        result, *reference = run(args.repeats, args.temp_dir, args.repeat_full, args.reference_root)
        if reference:
            args.reference_output.write_text(json.dumps(reference[0], indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
