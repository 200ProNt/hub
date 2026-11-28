"""PDF operations on local files with a validated, non-overwriting output."""

from __future__ import annotations

import os
import re
import tempfile
from contextlib import ExitStack, contextmanager
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from tools import fileguard
from tools.av_media import MediaError, local_file, publish_temporary
from tools.i18n import tr

PDF = frozenset({"pdf"})


@contextmanager
def _open(raw):
    path = local_file(raw, PDF)
    expected = fileguard.identity(path.lstat())
    try:
        with path.open("rb") as source:
            if fileguard.identity(os.fstat(source.fileno()))[:3] != expected[:3]:
                raise MediaError(tr("The PDF changed before reading.", "PDF изменился до чтения."))
            reader = PdfReader(source)
            if reader.is_encrypted:
                raise MediaError(tr("The PDF is encrypted.", "PDF защищён паролем."))
            yield path, reader
    except PdfReadError as exc:
        raise MediaError(tr("The PDF could not be read.", "Не удалось прочитать PDF.")) from exc


def info(raw):
    with _open(raw) as (path, reader):
        metadata = reader.metadata
        return {"pages": len(reader.pages), "size": path.stat().st_size,
                "title": str(metadata.title or "")[:400] if metadata else "",
                "author": str(metadata.author or "")[:400] if metadata else ""}


def page_numbers(specification, total):
    if not specification.strip():
        return range(total)
    result = {}
    for token in specification.split(","):
        value = re.fullmatch(r"\s*(\d{1,7})(?:\s*-\s*(\d{1,7}))?\s*", token)
        if not value:
            raise MediaError(tr("Use page numbers such as 1,3-5.", "Укажи номера страниц, например 1,3-5."))
        first, last = int(value[1]), int(value[2] or value[1])
        if not 1 <= first <= last <= total:
            raise MediaError(tr("A page number is outside the document.", "Номер страницы выходит за пределы документа."))
        result.update(dict.fromkeys(range(first - 1, last)))
    return tuple(result)


def _write(writer, target, control):
    with tempfile.TemporaryDirectory(prefix=".hub-pdf-", dir=target.parent) as folder:
        staged = Path(folder) / "result.pdf"
        with staged.open("xb") as stream:
            writer.write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        control.check()
        with _open(staged) as (_, check):
            if len(check.pages) != len(writer.pages):
                raise MediaError(tr("Unable to verify PDF output.", "Не удалось проверить результат PDF."))
        return publish_temporary(staged, target)


def process(operation, paths, destination, ranges, angle, control):
    if not paths or operation not in ("merge", "split", "extract", "rotate", "compress", "text"):
        raise MediaError(tr("Choose PDF files and an operation.", "Выбери файлы PDF и операцию."))
    if angle not in (90, 180, 270):
        raise MediaError(tr("Choose a right-angle rotation.", "Выбери поворот на 90, 180 или 270 градусов."))
    folder = fileguard.check_safe_folder(fileguard.local_path(destination))
    if operation == "merge":
        count = 0
        with ExitStack() as stack:
            writer = PdfWriter()
            for raw in paths:
                control.check()
                _, reader = stack.enter_context(_open(raw))
                for index in page_numbers(ranges, len(reader.pages)):
                    control.check()
                    writer.add_page(reader.pages[index])
                    count += 1
                    control.report(count, 0, 0)
            if not count:
                raise MediaError(tr("There are no pages to merge.", "Нет страниц для объединения."))
            return [_write(writer, folder / "Merged.pdf", control)]
    outputs = []
    for item_index, raw in enumerate(paths, 1):
        control.check()
        with _open(raw) as (source, reader):
            count = len(reader.pages)
            selected = page_numbers(ranges, count)
            if operation == "text":
                target = folder / f"{source.stem}.txt"
                with tempfile.TemporaryDirectory(prefix=".hub-text-", dir=folder) as temporary:
                    staged = Path(temporary) / "result.txt"
                    with staged.open("x", encoding="utf-8") as stream:
                        for number in selected:
                            control.check()
                            stream.write((reader.pages[number].extract_text() or "") + "\n\n")
                            control.report(number + 1, item_index - 1, 0)
                        stream.flush()
                        os.fsync(stream.fileno())
                    control.check()
                    outputs.append(publish_temporary(staged, target))
            elif operation == "split":
                for number in selected:
                    control.check()
                    writer = PdfWriter()
                    writer.add_page(reader.pages[number])
                    outputs.append(_write(writer, folder / f"{source.stem}-{number + 1}.pdf", control))
                    control.report(number + 1, item_index - 1, 0)
            else:
                writer = PdfWriter(clone_from=reader) if operation in ("rotate", "compress") else PdfWriter()
                for number in selected:
                    control.check()
                    if operation == "rotate":
                        writer.pages[number].rotate(angle)
                    elif operation == "compress":
                        writer.pages[number].compress_content_streams()
                    else:
                        writer.add_page(reader.pages[number])
                    control.report(number + 1, item_index - 1, 0)
                if operation == "compress":
                    writer.compress_identical_objects()
                outputs.append(_write(writer, folder / f"{source.stem}-{operation}.pdf", control))
            control.report(count, item_index, source.stat().st_size)
    return outputs
