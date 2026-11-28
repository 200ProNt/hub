"""Audio, video, and PDF tools for the native desktop."""

import json
from pathlib import Path

from System import TimeSpan
from System.Windows import Visibility
from System.Windows.Automation import AutomationProperties
from System.Windows.Threading import DispatcherTimer
from tools import av_media, jobs, pdf_media
from tools.i18n import tr


def mount(page):
    mode = page.choice(tr("Media type", "Тип медиа"), (tr("Video", "Видео"), tr("Audio or audio track", "Аудио или звуковая дорожка"), "PDF"))
    page.actions((tr("Image Tools", "Работа с изображениями"), lambda: page.go("images")))
    sources = page.field(tr("Input files, one path on each line", "Исходные файлы, по одному пути на строку"), multiline=True)
    picked = page.file(tr("Choose a file to add", "Выбрать файл"))
    destination = page.folder(tr("Output folder", "Папка результата"), page.default_folder)
    operation = page.choice(tr("PDF operation", "Операция PDF"), (
        tr("Merge", "Объединить"), tr("Split into pages", "Разделить на страницы"), tr("Extract pages", "Извлечь страницы"),
        tr("Rotate pages", "Повернуть страницы"), tr("Compress", "Сжать"), tr("Extract text", "Извлечь текст")))
    ranges = page.field(tr("Pages, empty for all", "Страницы, пусто для всех"))
    angles = (90, 180, 270)
    angle = page.choice(tr("Rotation", "Поворот"), [f"{n}°" for n in angles])
    video_format = page.choice(tr("Video output format", "Формат видео результата"), [value.upper() for value in av_media.VIDEO])
    audio_format = page.choice(tr("Audio output format", "Формат аудио результата"), [value.upper() for value in av_media.AUDIO])
    resolutions = (0, 480, 720, 1080, 2160)
    resolution = page.choice(tr("Output height", "Высота видео"), (tr("Original", "Исходная"), "480p", "720p", "1080p", "2160p"))
    quality = page.choice(tr("Video quality", "Качество видео"), (tr("High", "Высокое"), tr("Balanced", "Среднее"), tr("Small file", "Малый размер")), index=1)
    bitrates = (96, 128, 192, 256, 320)
    bitrate = page.choice(tr("Audio bitrate", "Битрейт аудио"), [f"{value} kb/s" for value in bitrates], index=2)
    status = page.text("", 13, True)
    progress = page.text("", 13, True)
    output_list = page.rows(max_height=205)
    AutomationProperties.SetName(output_list, tr("Media results", "Результаты обработки медиа"))
    metadata = page.field(tr("File information", "Информация о файле"), multiline=True)
    metadata.IsReadOnly = True
    metadata.MaxHeight = 220
    metadata.Parent.Visibility = Visibility.Collapsed
    current = None
    actions = ("merge", "split", "extract", "rotate", "compress", "text")

    def options(*_):
        pdf = mode.SelectedIndex == 2
        audio = mode.SelectedIndex == 1
        for field, visible in ((operation, pdf), (ranges, pdf), (angle, pdf and operation.SelectedIndex == 3),
                               (video_format, not pdf and not audio), (audio_format, audio),
                               (resolution, not pdf and not audio), (quality, not pdf and not audio), (bitrate, audio)):
            field.Parent.Visibility = Visibility.Visible if visible else Visibility.Collapsed

    def add():
        raw = picked.Text.strip()
        inputs = sources.Text.splitlines()
        if raw and raw not in inputs:
            sources.Text = "\n".join((*inputs, raw))
        picked.Text = ""

    def task(info_only=False):
        nonlocal current
        if page.busy:
            return
        inputs = list(dict.fromkeys(text.strip() for text in sources.Text.splitlines() if text.strip()))
        if not inputs and picked.Text.strip():
            inputs = [picked.Text.strip()]
        if not inputs or not info_only and not destination.Text.strip():
            page.notice(tr("Select input files and an output folder.", "Выбери файлы и папку результата."))
            return
        pdf, audio = mode.SelectedIndex == 2, mode.SelectedIndex == 1
        folder = destination.Text.strip()
        target = tuple(av_media.AUDIO)[max(0, audio_format.SelectedIndex)] if audio else tuple(av_media.VIDEO)[max(0, video_format.SelectedIndex)]
        options_av = (resolutions[max(0, resolution.SelectedIndex)], tuple(av_media.QUALITY)[max(0, quality.SelectedIndex)],
                      bitrates[max(0, bitrate.SelectedIndex)])
        options_pdf = actions[max(0, operation.SelectedIndex)], ranges.Text, angles[max(0, angle.SelectedIndex)]
        control = current = jobs.Job(float("inf"))
        cancel.IsEnabled = True
        output_list.Items.Clear()
        metadata.Parent.Visibility = Visibility.Collapsed
        status.Text = ""

        def work():
            try:
                if info_only:
                    rows = []
                    for path in inputs:
                        control.check()
                        rows.append((Path(path).name, pdf_media.info(path) if pdf else av_media.info("", path)))
                    return rows, ""
                if pdf:
                    command, pages, rotation = options_pdf
                    return pdf_media.process(command, inputs, folder, pages, rotation, control), ""
                return av_media.convert("", inputs, folder, "audio" if audio else "video", target, *options_av, control), ""
            except jobs.Cancelled:
                return [], tr("Processing cancelled. Completed files remain in the output folder.",
                              "Обработка отменена. Готовые файлы остаются в папке результата.")
            except Exception as exc:
                return [], str(exc)

        def finish(result):
            nonlocal current
            current = None
            cancel.IsEnabled = False
            progress.Text = ""
            data, error = result
            if error:
                status.Text = error
            elif info_only:
                metadata.Parent.Visibility = Visibility.Visible
                metadata.Text = "\n\n".join(name + "\n" + json.dumps(values, ensure_ascii=False, indent=2)
                                              for name, values in data)
            else:
                page.show_rows(output_list, data, str)
                status.Text = tr(f"Files written: {len(data)}", f"Создано файлов: {len(data)}")

        page.run(work, finish, tr("Processing media…", "Обрабатываю файлы…"))

    def stop():
        if current:
            current.cancelled.set()

    _, _, _, cancel = page.actions((tr("Add file", "Добавить файл"), add),
                                   (tr("Show file information", "Показать информацию"), lambda: task(True)),
                                   (tr("Process files", "Обработать файлы"), task, True),
                                   (tr("Cancel", "Отменить"), stop))
    cancel.IsEnabled = False
    timer = DispatcherTimer()
    timer.Interval = TimeSpan.FromMilliseconds(250)

    def tick(*_):
        if current:
            item, files, size = current.progress
            progress.Text = tr(f"Progress: {item} · Finished files: {files} · {size / 1024**2:.1f} MiB",
                               f"Ход работы: {item} · Готовых файлов: {files} · {size / 1024**2:.1f} МиБ")

    timer.Tick += tick
    timer.Start()
    page.on_leave(timer.Stop)
    page.on_leave(stop)
    mode.SelectionChanged += options
    operation.SelectionChanged += options
    options()
