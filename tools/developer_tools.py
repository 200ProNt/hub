"""Local data and source-code utilities."""

from __future__ import annotations

import base64
import binascii
import difflib
import json
import os
import re
import stat
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, unquote

from tools import fileguard
from tools.av_media import publish_temporary
from tools.i18n import tr

CHUNK = 1024 * 1024
MAX_TEXT = 1024 * 1024


def parse_json(text):
    def disallow_constant(value):
        raise ValueError(tr(f"Invalid JSON value {value}.", f"Недопустимое значение JSON {value}."))

    def unique_pairs(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError(tr("JSON contains duplicate keys.", "В JSON есть повторяющиеся ключи."))
        return result

    return json.loads(text, parse_constant=disallow_constant, object_pairs_hook=unique_pairs)


def format_json(text, compact=False):
    value = parse_json(text)
    formatted = json.dumps(value, ensure_ascii=False, allow_nan=False,
                           **({"separators": (",", ":")} if compact else {"indent": 2}))
    return formatted.encode("utf-8", errors="backslashreplace").decode("utf-8"), value


def base64_text(text, decode):
    if not decode:
        return base64.b64encode(text.encode("utf-8")).decode("ascii")
    return base64.b64decode(re.sub(r"[\t\r\n ]+", "", text), validate=True).decode("utf-8")


def url_text(text, decode):
    if not decode:
        return quote(text, safe="")
    if re.search(r"%(?![0-9a-fA-F]{2})", text):
        raise ValueError(tr("Invalid percent escape.", "Некорректная последовательность с %."))
    return unquote(text, errors="strict")


def text_diff(left, right, names=("Before", "After")):
    if len(left) > MAX_TEXT or len(right) > MAX_TEXT:
        raise ValueError(tr("The diff input is too large.", "Слишком большой текст для сравнения."))
    lines = []
    for line in difflib.unified_diff(left.splitlines(keepends=True), right.splitlines(keepends=True), *names, lineterm="\n"):
        lines.append(line)
        if not line.endswith(("\n", "\r")):
            lines.append("\n\\ No newline at end of file\n")
    return "".join(lines)


def _file(raw):
    path = fileguard.local_path(raw)
    fileguard.check_safe_folder(path.parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or fileguard.is_link(info):
        raise ValueError(tr("Select a regular local file.", "Выбери обычный локальный файл."))
    return path, fileguard.identity(info)


def _read_input(path, snapshot):
    source = path.open("rb")
    if fileguard.identity(os.fstat(source.fileno()))[:3] != snapshot[:3]:
        source.close()
        raise ValueError(tr("The input changed. Select it again.", "Исходный файл изменился. Выбери его снова."))
    return source


def code_diff(left, right):
    inputs, names = [], []
    for raw in (left, right):
        path, snapshot = _file(raw)
        with _read_input(path, snapshot) as source:
            data = source.read(MAX_TEXT + 1)
        if len(data) > MAX_TEXT:
            raise ValueError(tr("Code diff accepts files up to 1 MiB.", "Сравнение кода поддерживает файлы до 1 МиБ."))
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            inputs.append(data.decode("utf-16"))
        elif b"\0" in data:
            raise ValueError(tr("Code diff requires text files.", "Для сравнения кода нужны текстовые файлы."))
        else:
            inputs.append(data.decode("utf-8-sig"))
        names.append(path.name)
    return text_diff(*inputs, names)


def base64_file(raw, directory, decode, control):
    path, snapshot = _file(raw)
    folder = fileguard.check_safe_folder(fileguard.local_path(directory))
    name = (path.stem if path.suffix.casefold() == ".b64" else path.name + ".decoded") if decode else path.name + ".b64"
    if not name:
        name = "decoded"
    remainder = b""
    position = 0
    with tempfile.TemporaryDirectory(prefix=".hub-base64-", dir=folder) as temporary:
        staged = Path(temporary) / "result"
        with _read_input(path, snapshot) as source, staged.open("xb") as output:
            while raw_chunk := source.read(CHUNK):
                control.check()
                position += len(raw_chunk)
                if decode:
                    data = remainder + raw_chunk.translate(None, b"\t\r\n ")
                    limit = max(0, (len(data) - 4) // 4 * 4)
                    prefix, remainder = data[:limit], data[limit:]
                    if b"=" in prefix:
                        raise binascii.Error("Invalid Base64 padding")
                    output.write(base64.b64decode(prefix, validate=True))
                else:
                    data = remainder + raw_chunk
                    limit = len(data) // 3 * 3
                    output.write(base64.b64encode(data[:limit]))
                    remainder = data[limit:]
                control.report(1, 0, position)
            output.write(base64.b64decode(remainder, validate=True) if decode else base64.b64encode(remainder))
            output.flush()
            os.fsync(output.fileno())
        control.check()
        return publish_temporary(staged, folder / name)


def regex(pattern, text, ignore_case=False):
    if len(pattern) > 1024 or len(text) > 256 * 1024:
        raise ValueError(tr("Regular expression input is too large.", "Слишком большой шаблон или текст для регулярного выражения."))
    from System import TimeSpan
    from System.Text.RegularExpressions import Regex, RegexOptions, RegexMatchTimeoutException

    options = RegexOptions.CultureInvariant
    if ignore_case:
        options |= RegexOptions.IgnoreCase
    engine = Regex(pattern, options, TimeSpan.FromMilliseconds(120))
    names = [str(name) for name in engine.GetGroupNames() if str(name) != "0"]
    result = []
    deadline = time.monotonic() + 0.6
    try:
        match = engine.Match(text)
        while match.Success and len(result) < 500:
            if time.monotonic() > deadline:
                raise ValueError(tr("Regular expression reached the time limit.", "Регулярное выражение превысило лимит времени."))
            groups = {name: str(match.Groups[name].Value) for name in names if match.Groups[name].Success}
            result.append((int(match.Index), int(match.Length), str(match.Value), groups))
            match = match.NextMatch()
    except RegexMatchTimeoutException as exc:
        raise ValueError(tr("Regular expression reached the time limit.", "Регулярное выражение превысило лимит времени.")) from exc
    return result, bool(match.Success)
