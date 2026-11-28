"""Local audio and video operations using user-supplied FFmpeg executables."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Thread

from tools import fileguard, filesorter
from tools.i18n import tr

VIDEO = {
    "mp4": ("libx264", "aac"),
    "mkv": ("libx264", "aac"),
    "webm": ("libvpx-vp9", "libopus"),
}
AUDIO = {"mp3": "libmp3lame", "m4a": "aac", "wav": "pcm_s16le", "flac": "flac", "ogg": "libopus"}
INPUT = frozenset((*VIDEO, *AUDIO, "mov", "avi", "mpg", "mpeg", "aac", "wma", "wmv", "m4v", "ts", "m2ts", "opus"))
DEMUXER = {extension: name for name, extensions in (
    ("mov", ("mp4", "m4a", "mov", "m4v")),
    ("matroska", ("mkv", "webm")),
    ("ogg", ("ogg", "opus")),
    ("mpeg", ("mpg", "mpeg")),
    ("mpegts", ("ts", "m2ts")),
    ("asf", ("wmv", "wma")),
) for extension in extensions}
QUALITY = {"high": 20, "balanced": 27, "small": 34}


class MediaError(RuntimeError):
    pass


def local_file(value, extensions):
    path = fileguard.local_path(value)
    fileguard.check_safe_folder(path.parent)
    info = path.lstat()
    if fileguard.is_link(info) or not stat.S_ISREG(info.st_mode) or path.suffix.casefold().lstrip(".") not in extensions:
        raise MediaError(tr("Choose a supported local file.", "Выбери поддерживаемый локальный файл."))
    return path


def _tools(directory):
    result = []
    for name in ("ffmpeg", "ffprobe"):
        if directory:
            folder = fileguard.local_path(directory)
            fileguard.parents(folder)
            path = folder / (name + (".exe" if os.name == "nt" else ""))
        else:
            found = shutil.which(name)
            path = Path(found) if found else None
        if path is None or not path.is_file():
            raise MediaError(tr("Select the folder containing FFmpeg and ffprobe.",
                                "Выбери папку с FFmpeg и ffprobe."))
        try:
            with open(path, "rb") as handle:
                if os.name == "nt" and handle.read(2) != b"MZ":
                    raise MediaError(tr("FFmpeg tools must be Windows executables.", "Для FFmpeg нужны исполняемые файлы Windows."))
        except OSError as exc:
            raise MediaError(tr("FFmpeg cannot be read.", "Не удаётся прочитать FFmpeg.")) from exc
        result.append(str(path.absolute()))
    return result


def _flags():
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _probe(probe, path):
    extension = path.suffix.casefold().lstrip(".")
    command = [probe, "-v", "error", "-protocol_whitelist", "file,pipe", "-f", DEMUXER.get(extension, extension), "-show_entries",
               "format=duration,size,format_name:stream=codec_type,codec_name,width,height,sample_rate,channels",
               "-of", "json", str(path)]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=15, creationflags=_flags())
        parsed = json.loads(result.stdout) if result.returncode == 0 and len(result.stdout) <= 1024 * 1024 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        parsed = None
    if (not isinstance(parsed, dict) or not isinstance(parsed.get("format"), dict)
            or not isinstance(parsed.get("streams"), list)):
        raise MediaError(tr("ffprobe couldn't read the media. Check the file and FFmpeg version.",
                            "ffprobe не смог прочитать файл. Проверь файл и версию FFmpeg."))
    return parsed


def info(directory, path):
    _, probe = _tools(directory)
    return _probe(probe, local_file(path, INPUT))


def _convert(command, control, seconds, index, size):
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=_flags()) as process:
        updates = Queue(maxsize=64)

        def read():
            for line in process.stdout:
                try:
                    if line.startswith(b"out_time_us="):
                        updates.put_nowait(int(line.split(b"=", 1)[1]))
                except (ValueError, Full):
                    pass

        reader = Thread(target=read, daemon=True)
        reader.start()
        try:
            while process.poll() is None:
                control.check()
                try:
                    elapsed = updates.get(timeout=.15) / 1_000_000
                except Empty:
                    continue
                fraction = min(1.0, max(0.0, elapsed / seconds)) if seconds > 0 else 0
                control.report(index, index - 1, int(size * fraction))
            control.check()
            if process.returncode:
                raise MediaError(tr(f"FFmpeg failed with code {process.returncode}.",
                                    f"FFmpeg завершился с кодом {process.returncode}."))
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            reader.join(timeout=2)


def publish_temporary(temporary, target):
    fileguard.parents(target.parent)
    output = filesorter.unique_target(target)
    if os.name == "nt":
        temporary.rename(output)
    else:
        os.link(temporary, output)
    return str(output)


def convert(directory, inputs, destination, mode, format_name, resolution, quality, bitrate, control):
    format_name = format_name.casefold().lstrip(".")
    if mode not in ("audio", "video") or format_name not in (VIDEO if mode == "video" else AUDIO):
        raise MediaError(tr("Choose a supported output format.", "Выбери поддерживаемый формат результата."))
    if resolution not in (0, 480, 720, 1080, 2160) or quality not in QUALITY or not 32 <= bitrate <= 320:
        raise MediaError(tr("Invalid encoding settings.", "Недопустимые параметры кодирования."))
    executable, probe = _tools(directory)
    folder = fileguard.check_safe_folder(fileguard.local_path(destination))
    outputs = []
    for index, raw in enumerate(inputs, 1):
        control.check()
        path = local_file(raw, INPUT)
        source = _probe(probe, path)
        try:
            seconds = float(source["format"].get("duration", 0))
        except (ValueError, TypeError):
            seconds = 0
        path_info = path.stat()
        extension = path.suffix.casefold().lstrip(".")
        with tempfile.TemporaryDirectory(prefix=".hub-media-", dir=folder) as temporary:
            target = Path(temporary) / ("result." + format_name)
            args = [executable, "-v", "error", "-nostdin", "-n", "-progress", "pipe:1",
                    "-protocol_whitelist", "file,pipe", "-threads", "2", "-f", DEMUXER.get(extension, extension), "-i", str(path)]
            if mode == "video":
                video, audio = VIDEO[format_name]
                args.extend(("-map", "0:v:0", "-map", "0:a:0?", "-c:v", video, "-crf", str(QUALITY[quality]), "-c:a", audio))
                if video == "libvpx-vp9":
                    args.extend(("-b:v", "0"))
                if resolution:
                    args.extend(("-vf", f"scale=-2:{resolution}"))
            else:
                codec = AUDIO[format_name]
                args.extend(("-vn", "-map", "0:a:0", "-c:a", codec))
                if codec not in ("pcm_s16le", "flac"):
                    args.extend(("-b:a", f"{bitrate}k"))
            args.extend(("-threads", "2", str(target)))
            _convert(args, control, seconds, index, path_info.st_size)
            built = _probe(probe, target)
            if not any(isinstance(stream, dict) and stream.get("codec_type") == mode for stream in built["streams"]):
                raise MediaError(tr("Output stream couldn't be verified.", "Не удалось проверить поток результата."))
            control.check()
            outputs.append(publish_temporary(target, folder / f"{path.stem}.{format_name}"))
            control.report(index, index, path_info.st_size)
    return outputs
