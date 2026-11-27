"""Pair Windows Disk Map runs on shared fixtures. Use a local NTFS volume."""

import argparse
import csv
import ctypes
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

sys.path[:0] = [os.getcwd(), str(Path(__file__).resolve().parents[1])]

from benchmarks.disk_map import fixture, memory
from tools import diskmap

MIB = 1024**2
ROOT = Path(__file__).resolve().parents[1]


def worker_resources(process):
    handle = int(process._handle)
    times = [wintypes.FILETIME() for _ in range(4)]
    measure = ctypes.windll.kernel32.GetProcessTimes
    measure.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    measure.restype = wintypes.BOOL
    if not measure(handle, *(ctypes.byref(point) for point in times)):
        raise ctypes.WinError()
    ticks = sum((point.dwHighDateTime << 32) | point.dwLowDateTime for point in times[-2:])
    return {"worker_cpu_ms": ticks / 10_000, "worker_rss_peak_mib": memory(handle).peak_working_set / MIB}


def worker(backend, operation, folder):
    metrics = {}
    control = None
    if operation in ("scan-repeat", "scan-cached"):
        if backend == "optimized" and operation == "scan-cached":
            diskmap.scan(folder, use_cache=True)
        elif backend == "rust":
            from tools import rust_diskmap
            rust_diskmap.scan(folder)
        else:
            diskmap.scan(folder)
        if operation == "scan-repeat":
            diskmap._cache.clear()
    if operation in ("scan", "scan-repeat") and backend != "original":
        from tools.jobs import Job
        control = Job(time.monotonic() + 90)
    if backend == "rust":
        from tools import rust_diskmap

    before = memory()
    wall_start, cpu_start = time.perf_counter(), time.process_time()
    if operation == "files":
        result = diskmap.files(folder)
    elif backend == "rust":
        result = rust_diskmap.scan(folder, control=control, metrics=metrics,
                                  sample_process=lambda child: metrics.update(worker_resources(child)))
    elif backend == "optimized":
        result = diskmap.scan(folder, use_cache=operation == "scan-cached", control=control)
    else:
        result = diskmap.scan(folder)
    wall, parent_cpu = (time.perf_counter() - wall_start) * 1000, (time.process_time() - cpu_start) * 1000
    peak = memory().peak_working_set / MIB
    if result["truncated"]:
        raise ValueError(f"{backend} unexpectedly truncated {folder}")
    if operation == "files":
        count, size = len(result["files"]), sum(item["size"] for item in result["files"])
        comparable = result["files"]
    else:
        count, size = result["files"], result["total"]
        comparable = (result["dirs"], result["links"], result["entries"])
    errors = sorted(item["path"] for item in result["errors"])
    checksum = hashlib.sha256(json.dumps((comparable, errors), sort_keys=True).encode()).hexdigest()
    total_cpu = parent_cpu + metrics.get("worker_cpu_ms", 0)
    return {
        "wall_ms": wall, "parent_cpu_ms": parent_cpu, "cpu_ms": total_cpu,
        "cpu_one_core_pct": total_cpu / wall * 100, "parent_rss_before_mib": before.working_set / MIB,
        "parent_rss_peak_mib": peak, "rss_peak_upper_bound_mib": peak + metrics.get("worker_rss_peak_mib", 0),
        "files": count, "logical_bytes": size, "errors": result.get("error_count", len(errors)),
        "digest": checksum, **metrics,
    }


@contextmanager
def blocked_folders(root):
    who = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True).strip()
    sid = "*" + next(csv.reader([who]))[1]
    blocked = []
    try:
        for child in sorted(root.glob("blocked-*")):
            subprocess.run(["icacls", str(child), "/deny", f"{sid}:(RD)"], check=True, capture_output=True)
            blocked.append(child)
        yield
    finally:
        for child in blocked:
            subprocess.run(["icacls", str(child), "/remove:d", sid], check=True, capture_output=True)


def make_cases(root):
    for name, count, wide in (("nested-small", 2_000, False), ("nested-large", 30_000, False), ("wide-large", 30_000, True)):
        path = root / name
        fixture(path, count, wide)
        yield name, path, (count, count * 256, 0)
    deep = root / "deep"
    folder = deep
    for depth in range(55):
        folder /= "d"
        folder.mkdir(parents=True, exist_ok=True)
        for index in range(20):
            (folder / f"{index}.bin").write_bytes(b"x" * 64)
    yield "deep", deep, (1100, 1100 * 64, 0)
    limited = root / "access"
    fixture(limited, 1000, True)
    for index in range(12):
        fixture(limited / f"blocked-{index}", 100, True)
    with blocked_folders(limited):
        yield "access-denied", limited, (1000, 256_000, 12)
    variable = root / "variable"
    expected_bytes = 0
    for index in range(35_000):
        folder = variable / f"group-{index // 500:03}"
        if index % 500 == 0:
            folder.mkdir(parents=True)
        size = (index % 64) * 257
        with (folder / f"{index}.bin").open("wb") as stream:
            stream.truncate(size)
        expected_bytes += size
    yield "variable-large", variable, (35_000, expected_bytes, 0)


def measure(repeats, directory, original, optimized, revisions):
    roots = {"original": original.resolve(), "optimized": optimized.resolve(), "rust": ROOT}
    output = []
    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="hub-rust-bench-", dir=directory.resolve()) as work:
        for name, folder, expected in make_cases(Path(work)):
            operations = ["scan", "scan-repeat"] if name in ("nested-small", "nested-large", "wide-large") else ["scan"]
            if name == "wide-large":
                operations.append("files")
            if name == "nested-large":
                operations.append("scan-cached")
            for operation in operations:
                backends = tuple(roots) if operation.startswith("scan") and operation != "scan-cached" else ("original", "optimized")
                samples = {backend: [] for backend in backends}
                digests = set()
                for index in range(repeats):
                    shift = index % len(backends)
                    order = backends[shift:] + backends[:shift]
                    for backend in order:
                        command = [sys.executable, __file__, "--worker", backend, operation, str(folder)]
                        sample = json.loads(subprocess.check_output(command, cwd=roots[backend], timeout=150))
                        if (sample["files"], sample["logical_bytes"], sample["errors"]) != expected:
                            raise ValueError(f"{name}/{operation}/{backend} did not match fixture: {sample}")
                        digests.add(sample["digest"])
                        samples[backend].append(sample)
                if len(digests) != 1:
                    raise ValueError(f"{name}/{operation}: result structures differ")
                print(f"{name}/{operation}: {repeats} matched runs per backend", file=sys.stderr, flush=True)
                output.append({"fixture": name, "operation": operation, "backends": {
                    backend: {"samples": rows, "median": {
                        key: statistics.median(row[key] for row in rows)
                        for key, sample in rows[0].items() if isinstance(sample, (int, float))
                    }} for backend, rows in samples.items()
                }})
    from tools import rust_diskmap
    return {
        "utc_started": started, "os": platform.platform(), "python": platform.python_version(),
        "logical_cpus": os.cpu_count(), "fixture_drive": directory.resolve().anchor,
        "worker_sha256": hashlib.sha256(rust_diskmap.executable().read_bytes()).hexdigest(),
        "revisions": revisions, "runs_per_backend": repeats, "results": output,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", nargs=3, help=argparse.SUPPRESS)
    parser.add_argument("--temp-dir", type=Path)
    parser.add_argument("--original", type=Path)
    parser.add_argument("--optimized", type=Path)
    parser.add_argument("--revisions", nargs=3, metavar=("ORIGINAL", "OPTIMIZED", "RUST"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(*args.worker)))
        return
    if not all((args.original, args.optimized, args.temp_dir, args.revisions, args.output)) or args.repeats < 10:
        parser.error("Provide both source trees, revisions, output and a temporary folder; use at least 10 runs.")
    revisions = dict(zip(("original", "optimized", "rust"), args.revisions, strict=True))
    result = measure(args.repeats, args.temp_dir, args.original, args.optimized, revisions)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
