"""Windows disk, network, GPU and temperature telemetry for the WPF monitor."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from functools import lru_cache


@lru_cache(maxsize=1)
def _management():
    import clr

    clr.AddReference("System.Management")
    from System.Management import ManagementObjectSearcher
    return ManagementObjectSearcher


def _rows(class_name, fields, namespace=r"root\cimv2"):
    query = f"SELECT {', '.join(fields)} FROM {class_name}"
    try:
        search = _management()(namespace, query)
        try:
            search.Options.ReturnImmediately = True
            search.Options.Rewindable = False
            from System import TimeSpan

            search.Options.Timeout = TimeSpan.FromSeconds(2)
            results = search.Get()
            rows = []
            try:
                for record in results:
                    try:
                        rows.append(tuple(record[field] for field in fields))
                    finally:
                        record.Dispose()
            finally:
                results.Dispose()
            return rows
        finally:
            search.Dispose()
    except Exception:
        return []  # Availability depends on the installed drivers and WMI provider.


def _percent(value):
    return max(0, min(100, int(value))) if value is not None else None


def _disk_rows():
    fields = ("Name", "PercentIdleTime", "DiskReadBytesPerSec", "DiskWriteBytesPerSec")
    return [{"name": name, "busy": _percent(100 - idle) if idle is not None else None,
             "read": read, "write": write}
            for name, idle, read, write in _rows("Win32_PerfFormattedData_PerfDisk_PhysicalDisk", fields)
            if name and str(name).casefold() != "_total"]


def _network_rows():
    fields = ("Name", "BytesReceivedPersec", "BytesSentPersec")
    return [{"name": name, "received": received, "sent": sent}
            for name, received, sent in _rows("Win32_PerfFormattedData_Tcpip_NetworkInterface", fields)
            if name and str(name).casefold() != "_total"]


_ENGINE = re.compile(r"pid_\d+_(luid_.+?_phys_\d+)_eng_(\d+)_engtype_.+", re.IGNORECASE)


def _gpu_rows():
    instances = _rows("Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine", ("Name", "UtilizationPercentage"))
    memory = _rows("Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory", ("Name", "DedicatedUsage"))
    engines = defaultdict(int)
    for name, usage in instances:
        match = _ENGINE.fullmatch(str(name))
        if match and usage is not None:
            engines[match[1].casefold(), match[2]] += int(usage)
    busiest = {}
    for (adapter, _), usage in engines.items():
        busiest[adapter] = max(busiest.get(adapter, 0), _percent(usage))
    dedicated = {str(adapter).casefold(): usage for adapter, usage in memory if adapter}
    return [{"name": f"GPU {index}", "busy": busiest.get(adapter), "memory": dedicated.get(adapter)}
            for index, adapter in enumerate(sorted(busiest.keys() | dedicated.keys()), start=1)]


def _temperatures():
    rows = _rows("Sensor", ("Identifier", "Name", "SensorType", "Value"), r"root\LibreHardwareMonitor")
    temperatures = {"cpu": [], "gpu": []}
    for identifier, name, category, value in rows:
        if category != "Temperature" or value is None:
            continue
        value = float(value)
        if not math.isfinite(value):
            continue
        hardware = str(identifier).casefold()
        if hardware.startswith(("/intelcpu/", "/amdcpu/", "/cpu/")):
            temperatures["cpu"].append({"name": name, "value": round(value, 1)})
        elif hardware.startswith(("/gpu-", "/gpu/")):
            temperatures["gpu"].append({"name": name, "value": round(value, 1)})
    return temperatures


def read(metric):
    return {"disk": _disk_rows, "network": _network_rows, "gpu": _gpu_rows, "temperature": _temperatures}[metric]()
