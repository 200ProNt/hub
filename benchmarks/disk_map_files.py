"""Measure Disk Map files through loopback HTTP and the WPF rendering event."""

import argparse
import cProfile
import json
import os
import platform
import stat
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from threading import Thread as PythonThread
from time import perf_counter
from unittest.mock import patch

from benchmarks.disk_map import fixture


def profile(work):
    with cProfile.Profile() as profiler:
        work()
    categories = {"metadata": 0.0, "sort": 0.0, "authorization_calls": 0.0}
    for row in profiler.getstats():
        code = row.code
        name = code if isinstance(code, str) else code.co_name
        if name in ("<built-in method nt.lstat>", "<built-in method nt.scandir>",
                    "<method 'stat' of 'nt.DirEntry' objects>"):
            category = "metadata"
        elif name == "<method 'sort' of 'list' objects>":
            categories["sort"] += row.totaltime * 1000
            continue
        elif name in ("_identity", "identity", "normcase"):
            category = "authorization_calls"
        else:
            continue
        categories[category] += row.inlinetime * 1000
    return {f"{key}_ms": value for key, value in categories.items()}


def metadata_probe(folder, rust, count, repeats):
    def python_rows(stat_entry):
        with os.scandir(folder) as entries:
            rows = []
            for entry in entries:
                info = stat_entry(entry)
                if stat.S_ISREG(info.st_mode) and not info.st_file_attributes & 0x400:
                    rows.append((entry.name, info.st_size))
            return rows

    def rust_rows():
        output = subprocess.check_output([str(rust)], input=f"{folder}\n".encode(), timeout=60)
        return [(name, int(size)) for line in output.decode().splitlines()
                for size, name in [line.split("\t", 1)]]

    ways = {
        "python_lstat": lambda: python_rows(lambda entry: os.lstat(entry.path)),
        "python_scandir": lambda: python_rows(lambda entry: entry.stat(follow_symlinks=False)),
        "rust_process_and_pipe": rust_rows,
    }
    samples = {key: [] for key in ways}
    for attempt in range(repeats):
        order = list(ways)
        shift = attempt % len(ways)
        for key in order[shift:] + order[:shift]:
            start = perf_counter()
            rows = ways[key]()
            samples[key].append((perf_counter() - start) * 1000)
            assert sorted(rows) == [(f"file-{i:06}.bin", 256) for i in range(count)]
    return {key: {"samples_ms": values, "median_ms": statistics.median(values)}
            for key, values in samples.items()}


def measure(folder, count, repeats):
    from native.ui import ApartmentState, HubWindow, Thread, ThreadStart
    from server import HubHandler, HubServer, VERSION
    from tools import diskmap
    from System import EventHandler, TimeSpan
    from System.Windows import RoutedEventArgs, WindowState
    from System.Windows.Automation import AutomationProperties
    from System.Windows.Controls import ListBox, WrapPanel
    from System.Windows.Controls.Primitives import ButtonBase
    from System.Windows.Media import CompositionTarget
    from System.Windows.Threading import Dispatcher, DispatcherFrame, DispatcherTimer

    route = "/api/diskmap/files"
    stamps = {}
    list_body = {}
    samples = []
    errors = []
    clock = perf_counter

    class Handler(HubHandler):
        def _dispatch_post(self, path, body):
            if path != route:
                return super()._dispatch_post(path, body)
            list_body.update(body)
            stamps["server_begin"] = clock()
            result = super()._dispatch_post(path, body)
            stamps["server_end"] = clock()
            assert result.get("count", len(result["files"])) == count
            return result

    def wait_for(predicate, event, describe):
        frame = DispatcherFrame()
        timer = DispatcherTimer()
        timer.Interval = TimeSpan.FromSeconds(15)
        observer = EventHandler(lambda *_: setattr(frame, "Continue", False) if predicate() else None)
        timer.Tick += EventHandler(lambda *_: setattr(frame, "Continue", False))
        event(observer, True)
        timer.Start()
        try:
            Dispatcher.PushFrame(frame)
        finally:
            event(observer, False)
            timer.Stop()
        assert predicate(), f"Timed out: {describe()}"

    with HubServer(("127.0.0.1", 0), Handler) as server:
        worker = PythonThread(target=server.serve_forever, daemon=True)
        worker.start()

        def ui():
            hub = None
            try:
                with patch("native.ui.preferences.read", return_value={"hub-language": "en", "hub-motion": "off"}):
                    hub = HubWindow(server.server_port, VERSION, str(folder))
                hub.window.WindowState = WindowState.Maximized
                hub.window.Show()
                hub.go("diskmap")
                page = hub.current
                buttons = {AutomationProperties.GetName(button): button
                           for group in page.panel.Children if isinstance(group, WrapPanel)
                           for button in group.Children}
                boxes = [box for box in page.panel.Children if isinstance(box, ListBox)]
                folders_box, files_box = boxes
                request = page._request
                post = page.post

                def timed_request(path, payload=None):
                    data = request(path, payload)
                    if path == route:
                        stamps.update(read=clock(), response_bytes=len(data))
                    return data

                def timed_post(path, payload):
                    value = post(path, payload)
                    if path == route:
                        stamps["decoded"] = clock()
                    return value

                def observe_render(handler, add):
                    if add:
                        CompositionTarget.Rendering += handler
                    else:
                        CompositionTarget.Rendering -= handler

                def observe_scan(handler, add):
                    if add:
                        scan_timer.Tick += handler
                        scan_timer.Start()
                    else:
                        scan_timer.Stop()
                        scan_timer.Tick -= handler

                def status():
                    return f"{hub.widget('Status').Text}, busy={page.busy}, stamps={stamps}"

                def click(name):
                    button = buttons[name]
                    button.RaiseEvent(RoutedEventArgs(ButtonBase.ClickEvent, button))

                def rows_ready():
                    if not files_box.IsVisible or files_box.Items.Count != min(100, count):
                        return False
                    row = files_box.Items[0]
                    if not row.IsVisible or not row.IsArrangeValid or row.ActualHeight <= 0:
                        return False
                    stamps.setdefault("first_rows", clock())
                    return True

                page._request = timed_request
                page.post = timed_post
                scan_timer = DispatcherTimer()
                scan_timer.Interval = TimeSpan.FromMilliseconds(20)
                click("Calculate sizes")
                wait_for(lambda: not page.busy and folders_box.Items.Count == 1, observe_scan, status)
                for _ in range(repeats):
                    click("Hide file list")
                    stamps.clear()
                    stamps["click"] = clock()
                    click("Files in this folder")
                    wait_for(rows_ready, observe_render, status)
                    assert "file-000000.bin" in str(files_box.Items[0].Content.Text)
                    phases = {
                        "dispatch": ("click", "server_begin"),
                        "server": ("server_begin", "server_end"),
                        "response_encode_and_transfer": ("server_end", "read"),
                        "decode": ("read", "decoded"),
                        "wpf_dispatch_layout_render": ("decoded", "first_rows"),
                        "click_to_first_rows": ("click", "first_rows"),
                    }
                    sample = {f"{key}_ms": (stamps[end] - stamps[start]) * 1000
                              for key, (start, end) in phases.items()}
                    samples.append({**sample, "response_bytes": stamps["response_bytes"]})
            except BaseException as error:
                errors.append(error)
            finally:
                if hub is not None:
                    hub.exiting = True
                    hub.window.Close()

        try:
            thread = Thread(ThreadStart(ui))
            thread.SetApartmentState(ApartmentState.STA)
            thread.Start()
            thread.Join()
        finally:
            server.shutdown()
            worker.join()
    if errors:
        raise errors[0]
    options = {"paged": True} if list_body.get("paged") else {}
    return {"samples": samples, "profile": profile(lambda: diskmap.files(str(folder), **options))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path)
    parser.add_argument("--temp-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--rust-probe", type=Path)
    parser.add_argument("--only-metadata", action="store_true")
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--worker", nargs=3, metavar=("SOURCE", "FOLDER", "COUNT"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        root, folder, count = args.worker
        sys.path.insert(0, root)
        # fixture imports tools from the caller's checkout. Load the worker's source tree.
        for name in list(sys.modules):
            if name == "tools" or name.startswith("tools."):
                del sys.modules[name]
        print(json.dumps(measure(Path(folder), int(count), args.repeats)))
        return
    roots = {"candidate": Path.cwd()}
    if args.reference_root:
        roots["reference"] = args.reference_root.resolve()
    results = {}
    with tempfile.TemporaryDirectory(prefix="hub-files-", dir=args.temp_dir) as directory:
        for name, count in (("wide-small", 50), ("wide-large", 30_000)):
            folder = Path(directory).resolve() / name
            fixture(folder, count, wide=True)
            if args.only_metadata:
                results[name] = metadata_probe(folder, args.rust_probe.resolve(), count, args.repeats)
                continue
            runs = {key: {"samples": [], "profiles": []} for key in roots}
            for round_index in range(3):
                order = list(roots) if round_index % 2 == 0 else list(reversed(roots))
                for key in order:
                    command = [sys.executable, "-m", "benchmarks.disk_map_files", "--worker",
                               str(roots[key]), str(folder), str(count), "--repeats", str(args.repeats)]
                    result = json.loads(subprocess.check_output(command, text=True, timeout=120))
                    runs[key]["samples"].extend(result["samples"])
                    runs[key]["profiles"].append(result["profile"])
            for row in runs.values():
                row["median"] = {key: statistics.median(s[key] for s in row["samples"])
                                 for key in row["samples"][0]}
            results[name] = {"files": count, **runs}
            if args.rust_probe:
                results[name]["metadata_probe"] = metadata_probe(folder, args.rust_probe.resolve(), count, args.repeats)
    report = {
        "os": platform.platform(), "python": platform.python_version(), "logical_cpus": os.cpu_count(),
        "fixture_drive": Path(args.temp_dir or tempfile.gettempdir()).resolve().anchor,
        "method": "alternating source processes, warm OS cache, WPF animation off, profile runs separate",
        "results": results,
    }
    output = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
