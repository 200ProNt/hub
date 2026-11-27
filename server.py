"""Hub — локальный сайт с инструментами. Один сервер, только stdlib.

Слушает 127.0.0.1, наружу не смотрит.
"""

from __future__ import annotations

import json
import os
import platform
import re
import socket
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from tools import (
    autostart,
    bigfiles,
    checksum,
    cleanup,
    clipboard,
    compare,
    diskmap,
    duplicates,
    fileguard,
    filesorter,
    images,
    jobs,
    monitor,
    notes,
    paths,
    preferences,
    qrdrop,
    renamer,
    rust_diskmap,
    search,
    shortcuts,
    trash,
    tray,
)
from tools.registry import TOOLS

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = paths.DATA_DIR

START_PORT = 8770
PORT_ATTEMPTS = 30
MAX_BODY_BYTES = 8 * 1024 * 1024
VERSION = "1.6.0"

# История версий для вкладки «О программе». Новые записи — сверху.
CHANGELOG = [
    {
        "version": VERSION,
        "date": "2026-11-27",
        "title": "Быстрая карта диска и каналы обновлений",
        "title_en": "Faster Disk Map and update channels",
        "items": [
            "Карта диска быстрее показывает первые 100 файлов в большой папке.",
            "«Показать ещё файлы» подгружает следующую сотню. При переходе между папками старый список закрывается.",
            "Расчёт размеров показывает прогресс, поддерживает отмену и может посчитать локальный диск.",
            "Rust Core включается в настройках экспериментов. По умолчанию выбран Python, и Hub возвращается к нему при сбое Rust Worker.",
            "Hub загружает Python и его библиотеки из каталога приложения, без распаковки в TEMP при запуске.",
            "В настройках обновлений можно выбрать последнюю стабильную версию или бету.",
        ],
        "items_en": [
            "Disk Map displays the first 100 files in a large folder faster.",
            "Show more files loads the next 100. Navigating to another folder closes the previous list.",
            "Disk Map shows progress, supports cancellation, and can scan an entire local drive.",
            "Rust Core is available under Experiments. Python is the default and the fallback if the Rust worker fails.",
            "Hub loads Python and its libraries from the app folder without extracting them to TEMP at startup.",
            "Update settings now let you choose the latest stable release or beta.",
        ],
    },
    {
        "version": "1.5.3.1",
        "date": "2026-11-26",
        "title": "Язык, палитры и главная",
        "title_en": "Language, palettes, and Home",
        "items": [
            "В настройках можно выбрать английский или русский язык. Для новых профилей выбран английский.",
            "Режим «Авто (Windows)» следует системной теме. Обновлены акценты, а Material You помечена как бета.",
            "Новая главная показывает задачи, буфер обмена, загрузку процессора и памяти. Диаграмма карты диска плавно раскрывается.",
            "Установщик обновляет иконки ярлыков на рабочем столе и в меню «Пуск».",
        ],
        "items_en": [
            "Choose English or Russian in Settings. New profiles start in English.",
            "Auto (Windows) follows the system theme. Accent palettes are refreshed and Material You is marked as beta.",
            "Home shows tasks, clipboard history, CPU, and memory. The Disk Map chart unfolds into a ring.",
            "Setup refreshes the icons of desktop and Start menu shortcuts.",
        ],
    },
    {
        "version": "1.5.3",
        "date": "2026-11-26",
        "title": "Новая иконка Hub",
        "items": [
            "Чёрно-белая H стала иконкой Hub в Windows и браузере.",
            "Внутри Hub логотип меняет цвет вместе с выбранным акцентом.",
            "Сборка установщика использует системные пути Windows для поиска DLL.",
        ],
        "title_en": "New Hub icon",
        "items_en": [
            "The black-and-white H is now the Hub icon in Windows and the browser.",
            "Inside Hub, the logo follows your selected accent color.",
            "The installer build uses Windows system paths to resolve DLLs.",
        ],
    },
    {
        "version": "1.5.2.5.1",
        "date": "2026-11-26",
        "title": "Умеренные скругления в Material You",
        "items": [
            "Кнопки, навигация и поиск получили прямоугольную форму с мягкими углами.",
            "Скругление карточек, меню и списков стало меньше.",
        ],
        "title_en": "Softer Material You corners",
        "items_en": [
            "Buttons, navigation, and search now have rectangular shapes with rounded corners.",
            "Cards, menus, and lists use smaller corner radii.",
        ],
    },
    {
        "version": "1.5.2.5",
        "date": "2026-11-26",
        "title": "Компоненты Material You",
        "items": [
            "Кнопки, поля ввода и списки в настольной теме используют библиотеку Material Design 3 для WPF.",
            "Шрифт Roboto, просторная навигация, строка поиска и цветная карточка быстрой записи.",
        ],
        "title_en": "Material You components",
        "items_en": [
            "Buttons, fields, and drop-down lists in the desktop theme use Material Design 3 for WPF.",
            "Roboto, more spacious navigation, a search field, and a colored Quick Capture card.",
        ],
    },
    {
        "version": "1.5.2",
        "date": "2026-11-25",
        "title": "Цвет, стекло и движение",
        "items": [
            "Material You подбирает оттенки панелей и кнопок под акцент Windows или выбранный тобой цвет.",
            "В Liquid Glass боковая панель получила направленный блик, а карточки — плотную подложку.",
            "Обновлены переходы между экранами, появление поиска и отклик элементов управления.",
        ],
        "title_en": "Color, glass, and motion",
        "items_en": [
            "Material You uses the Windows accent or your selected color for panels and buttons.",
            "The Liquid Glass sidebar gains a directional highlight, with solid backgrounds behind card text.",
            "Updated page transitions, search entrance, and control feedback.",
        ],
    },
    {
        "version": "1.5.1",
        "date": "2026-11-25",
        "title": "Оформление и обновления",
        "items": [
            "Material You и Liquid Glass меняют палитру, панели и форму элементов Hub.",
            "Новые переходы, скруглённый QR-код и знакомый значок из четырёх квадратов.",
            "Обновлённый мониторинг ПК с возможностью свернуть окно выбранного приложения.",
            "Проверка релизов GitHub, установка обновления из Hub и экран «Что нового».",
        ],
        "title_en": "Appearance and updates",
        "items_en": [
            "Material You and Liquid Glass change the Hub palette, panels, and control shapes.",
            "New transitions, rounded QR codes, and the familiar four-square icon.",
            "PC Monitor can minimize windows for the selected application.",
            "Check GitHub releases, install updates from Hub, and see what's new.",
        ],
    },
    {
        "version": "1.5.0",
        "date": "2026-11-24",
        "items": [
            "Нативные экраны Hub на WPF для Windows 11.",
            "Прозрачный акриловый материал окна, собственный логотип и контурные иконки.",
        ],
        "title_en": "Native Windows interface",
        "items_en": [
            "Native WPF screens for Windows 11.",
            "Translucent acrylic window, custom logo, and outline icons.",
        ],
    },
    {
        "version": "1.4.0",
        "date": "2026-11-23",
        "items": [
            "Отдельное окно Hub для Windows 11, запуск из ярлыка и быстрый поиск из трея.",
            "Компактная панель инструментов, светлая и тёмная темы, навигация с клавиатуры.",
            "Перенос заметок, истории буфера, корзины и настроек из браузерной версии.",
        ],
        "title_en": "Desktop Hub for Windows",
        "items_en": [
            "A dedicated Windows 11 window, launch from a shortcut, and quick search from the tray.",
            "Compact tool navigation, light and dark themes, and keyboard navigation.",
            "Migrate notes, clipboard history, Trash, and settings from the browser version.",
        ],
    },
    {
        "version": "1.3.2.1",
        "date": "2026-11-19",
        "items": [
            "Хотфикс QR-Drop: устранена циклическая ошибка 'Cannot set properties of null' при переходе между вкладками; таймер автообновления корректно очищается при размонтировании.",
            "Надёжная интеграция с треем Windows: поток трея автоматически подключается к интерактивному рабочему столу Windows Default, гарантируя появление иконки рядом с часами.",
            "Глобальный хоткей Ctrl+Alt+H: регистрация надёжной системной комбинации клавиш (с альтернативой Alt+Shift+H), открывающей быстрый поиск и команды из любой программы поверх всех окон.",
        ],
        "title_en": "Phone transfer and Windows integration fixes",
        "items_en": [
            "Fixed a recurring QR-Drop error when switching tabs. Automatic refresh stops when the page closes.",
            "The tray worker attaches to the interactive Windows desktop so the icon appears beside the clock.",
            "Ctrl+Alt+H opens quick search and commands from any app, with Alt+Shift+H as a fallback.",
        ],
    },
    {
        "version": "1.3.2",
        "date": "2026-11-19",
        "items": [
            "Интеграция в системный трей Windows: значок Hub у часов с меню быстрого доступа («Открыть Hub», «Быстрая заметка», «Мониторинг», «QR-Drop», «Выход»).",
            "Глобальный хоткей Windows (Win+Alt+H / Ctrl+Shift+H): моментальный вызов хаба из любого приложения, игры или проводника поверх окон.",
            "Локальный обмен с телефоном по Wi-Fi (QR-Drop): мобильный веб-интерфейс (/drop) для передачи текста из буфера и файлов со смартфона на ПК и обратно по QR-коду.",
            "Пакетное переименование файлов (Batch Renamer): массовое переименование по правилам (замена, нумерация, регистр, транслитерация, даты) с живым предпросмотром, защитой от коллизий и отменой (Undo).",
            "Хэши и безопасность файлов (Checksum & Crypto): расчет контрольных сумм SHA-256, MD5, SHA-1 потоковым чтением, проверка подлинности файлов и генератор надёжных паролей.",
        ],
        "title_en": "Tray, phone transfer, and file tools",
        "items_en": [
            "Windows tray icon with shortcuts for opening Hub, adding a note, checking PC Monitor, using QR-Drop, or quitting.",
            "Use Win+Alt+H or Ctrl+Shift+H to open Hub above other windows.",
            "Local Wi-Fi transfer for text and files between your phone and PC using a QR code.",
            "Batch file renaming with rules, live previews, collision checks, and undo.",
            "Stream file data to compute SHA-256, MD5, or SHA-1, verify checksums, and generate strong passwords.",
        ],
    },
    {
        "version": "1.3.1.2",
        "date": "2026-11-19",
        "items": [
            "Хотфикс полей поиска и ввода: устранено паразитное наложение двойных рамок, фона и скругления на текстовые поля внутри строки поиска (Мониторинг, Буфер обмена, Дубликаты, Сортировка) в режиме стекла (Acrylic Glass).",
            "Изоляция составных элементов: контейнеры поиска и выбора получили единое аккуратное закругление, а внутренние input-элементы остаются полностью прозрачными и бесшовными.",
        ],
        "title_en": "Search and input fixes",
        "items_en": [
            "Fixed doubled backgrounds, borders, and corners inside search fields in Acrylic Glass mode.",
            "Search and picker containers now have consistent corners, with transparent inputs inside.",
        ],
    },
    {
        "version": "1.3.1.1",
        "date": "2026-11-19",
        "items": [
            "Хотфикс бокового меню: закреплена боковая панель (position: fixed / sticky) — теперь меню зафиксировано на весь экран и больше не уезжает вниз при прокрутке длинных списков.",
            "Редизайн карточек настроек и стекла: убраны некрасивые острые прямоугольные рамки, карточки параметров стали элегантными с мягким закруглением (border-radius: 14px), компактными переключателями-пилюлями и гармоничными отступами.",
        ],
        "title_en": "Sidebar and settings refinements",
        "items_en": [
            "The sidebar stays visible when long lists scroll.",
            "Settings use rounded cards, compact switches, and adjusted spacing.",
        ],
    },
    {
        "version": "1.3.1",
        "date": "2026-11-19",
        "items": [
            "Панель настроек (Settings): вынесено отдельное компактное окно настроек (Ctrl+,), освободившее боковое меню от нагромождения кнопок.",
            "Настоящий Fluent Acrylic Glassmorphism: реалистичное матовое стекло Windows 11 с многослойным размытием, микро-текстурой шума (noise texture), световыми бликами на гранях и глубоким свечением фонового градиента.",
            "Быстрый поиск настроек: открытие окна параметров прямо через глобальный поиск по Ctrl+K.",
        ],
        "title_en": "Settings and Acrylic Glass",
        "items_en": [
            "Settings moved to a dedicated panel, opened with Ctrl+,.",
            "Added a Windows 11-inspired Acrylic Glass theme with layered blur, fine texture, edge highlights, and a background gradient.",
            "Open Settings from quick search with Ctrl+K.",
        ],
    },
    {
        "version": "1.3.0",
        "date": "2026-11-19",
        "items": [
            "Кастомизация UI в стиле Windows 11 Fluent Design: выбор акцентных цветов (Cyber Purple, Hacker Emerald, Ocean Blue, Sunset Orange, Neon Pink) и эффект матового стекла (Glassmorphism / Acrylic blur).",
            "Главный экран — Дашборд: новый стартовый раздел со сводкой дня, живыми виджетами CPU/RAM, интерактивными задачами To-Do, последними записями буфера и быстрыми действиями.",
            "Микро-звуки интерфейса: мягкие тактильные звуковые щелчки и переливы на Web Audio API (копирование, выполнение задач, удаление, переключение) с возможностью отключения.",
        ],
        "title_en": "Dashboard and appearance",
        "items_en": [
            "Windows 11 Fluent-inspired appearance with accent choices and acrylic blur.",
            "New Home dashboard with a daily summary, live CPU and RAM, tasks, recent clipboard entries, and quick actions.",
            "Optional Web Audio feedback for copying, completing tasks, deleting, and switching.",
        ],
    },
    {
        "version": "1.2.6",
        "date": "2026-11-19",
        "items": [
            "Сжатие картинок: новый инструмент — смена формата (PNG, JPEG, WebP), качественное сжатие, масштабирование (Full HD, HD, веб, иконка), вставка из буфера обмена и сохранение на диск.",
            "Заметки: поддержка интерактивных чекбоксов [ ] / [x] с моментальным переключением по клику, форматирование Markdown (заголовки, жирный текст, списки) и фильтрация по тегам #тег.",
            "Буфер обмена: фильтр закреплённых заметок/шаблонов, быстрое добавление своих сниппетов, форматирование текста (очистка лишних пробелов, регистр, транслитерация).",
            "Сравнение папок: двусторонняя синхронизация — копирование недостающих файлов и папок в один клик прямо из отчёта сравнения.",
            "Интеграция с Windows: безопасное выключение сервера Hub в один клик из интерфейса и создание полного резервного ZIP-архива всех данных (папка data/) для переноса.",
        ],
        "title_en": "Image tools and workflow improvements",
        "items_en": [
            "Convert, compress, resize, paste, and save images in PNG, JPEG, or WebP.",
            "Notes support clickable Markdown checkboxes, formatting, and hashtag filters.",
            "Clipboard filters for pinned entries and snippets, custom snippets, and text formatting.",
            "Copy missing files and folders in either direction from the comparison report.",
            "Quit the Hub server from the interface and export a complete ZIP backup.",
        ],
    },
    {
        "version": "1.2.5",
        "date": "2026-11-19",
        "items": [
            "Буфер обмена: фильтрация по типу контента (все, ссылки, код, текст), подсчёт слов и символов на карточках.",
            "Мониторинг ПК: живые мини-графики нагрузки CPU и оперативной памяти за последние 30 измерений.",
            "Экспорт заметок: скачивание отдельных записей и всей базы заметок в форматах Markdown (.md) и TXT.",
            "Сортировка и Уборка: интерактивная настройка правил — добавление своих категорий, расширений и мусорных файлов прямо из интерфейса.",
            "Интеграция с Windows: создание и удаление ярлыков на Рабочем столе и в меню «Пуск» в один клик.",
        ],
        "title_en": "Clipboard, monitoring, and note exports",
        "items_en": [
            "Filter clipboard entries by content type and see word and character counts.",
            "Live CPU and RAM charts show the last 30 PC Monitor readings.",
            "Export individual notes or the whole collection as Markdown or TXT.",
            "Edit sorter and cleanup rules, including categories, extensions, and junk filenames.",
            "Create or remove Windows desktop and Start menu shortcuts from Hub.",
        ],
    },
    {
        "version": "1.2.0.1",
        "date": "2026-11-19",
        "items": [
            "Хотфикс запуска: исправлен скрипт start.bat (устранена ошибка парсинга команд 'EXE' / 'ATA\\Programs' из-за несовместимости переводов строк и многострочных блоков в cmd.exe).",
            "Улучшен поиск Python: поддержка путей с пробелами (Program Files), py launcher и принудительный CRLF через .gitattributes.",
        ],
        "title_en": "Startup fixes",
        "items_en": [
            "Fixed start.bat parsing in cmd.exe for multiline blocks and line endings.",
            "Improved Python discovery, with support for paths containing spaces, the Python launcher, and enforced CRLF.",
        ],
    },
    {
        "version": "1.2.0",
        "date": "2026-11-19",
        "items": [
            "Защита буфера обмена: скрытие паролей из менеджеров (ExcludeClipboardContent) и пропуск чувствительных данных (ключи, токены).",
            "Защита HTTP API: блокировка межсайтовых запросов (CSRF), проверка заголовков Host, Origin и Sec-Fetch-Site от атак DNS Rebinding.",
            "Защита от сканирования: блокировка доступа к системным папкам Windows и корню диска во всех инструментах.",
            "Защита заметок и буфера: синхронизация fsync от сбоев питания, автосохранение копий .bak и резервирование повреждённых файлов.",
        ],
        "title_en": "Security and data protection",
        "items_en": [
            "Respect ExcludeClipboardContent and skip sensitive clipboard items such as keys and tokens.",
            "Protect the HTTP API from cross-site requests and DNS rebinding by checking Host, Origin, and Sec-Fetch-Site.",
            "Block scans of Windows system folders and drive roots.",
            "Flush note and clipboard writes to disk, make automatic .bak copies, and keep corrupted files for recovery.",
        ],
    },
    {
        "version": "1.1.1",
        "date": "2026-11-17",
        "items": [
            "В «О программе» появилась история версий: что менялось и когда.",
        ],
        "title_en": "Release history",
        "items_en": [
            "About now lists previous versions, changes, and dates.",
        ],
    },
    {
        "version": "1.1.0",
        "date": "2026-11-17",
        "items": [
            "Корзина стала отдельной вкладкой: видно каждый перенос, его можно вернуть или удалить навсегда.",
            "Поиск по всему хабу по Ctrl+K: инструменты, заметки и буфер обмена.",
            "Автозапуск вместе с Windows переключателем внизу меню.",
        ],
        "title_en": "Trash, quick search, and startup",
        "items_en": [
            "A separate Trash page lists each move with restore and permanent deletion actions.",
            "Find tools, notes, and clipboard history from quick search with Ctrl+K.",
            "Turn Windows startup on or off from the sidebar.",
        ],
    },
    {
        "version": "1.0.0",
        "date": "2026-11-17",
        "items": [
            "Первая версия: буфер обмена, заметки, сортировка файлов, дубликаты, карта диска, сравнение папок, уборка, мониторинг ПК и «О программе».",
        ],
        "title_en": "First release",
        "items_en": [
            "Clipboard history, notes, file sorting, duplicate files, disk map, folder comparison, cleanup, PC Monitor, and About.",
        ],
    },
]

CONTENT_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".json": "application/json",
}

IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".avif": "image/avif",
}

MAX_THUMB_BYTES = 12 * 1024 * 1024

_state: dict[str, object] = {"store": None, "watcher": None}


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def store() -> clipboard.ClipboardStore:
    instance = _state.get("store")
    if not isinstance(instance, clipboard.ClipboardStore):
        raise ApiError("История буфера ещё не готова", 503)
    return instance


def watcher() -> clipboard.ClipboardWatcher:
    instance = _state.get("watcher")
    if not isinstance(instance, clipboard.ClipboardWatcher):
        raise ApiError("Наблюдатель буфера не запущен", 503)
    return instance


# --- Системные действия ----------------------------------------------------


def about_info() -> dict:
    """Общие сведения о программе для вкладки «О программе»."""
    try:
        license_text = (BASE_DIR / "LICENSE").read_text(encoding="utf-8")
    except OSError:
        license_text = ""
    return {
        "name": "Hub",
        "version": VERSION,
        "author": "devrin",
        "license": "MIT",
        "license_text": license_text,
        "folder": str(paths.DESKTOP_EXE.parent if paths.DESKTOP_EXE else BASE_DIR),
        "readme": str(BASE_DIR / "README.md"),
        "tools": len(TOOLS),
        "python": platform.python_version(),
        "changes": CHANGELOG,
    }


def home_summary() -> dict:
    """Сводка данных для главной страницы (дашборда)."""
    uncompleted_todos = []
    notes_count = 0
    try:
        notes_store = notes.store()
        notes_count = notes_store.count()
        for note in notes_store.listing(""):
            lines = note.get("text", "").splitlines()
            for idx, line in enumerate(lines):
                trimmed = line.strip()
                if trimmed.startswith("- [ ]"):
                    todo_text = trimmed[5:].strip()
                    uncompleted_todos.append({
                        "note_id": note["id"],
                        "note_title": note["title"] or "Без названия",
                        "line_idx": idx,
                        "text": todo_text,
                    })
                    if len(uncompleted_todos) >= 8:
                        break
            if len(uncompleted_todos) >= 8:
                break
    except Exception:
        pass

    try:
        snapshot = monitor.snapshot()
        system = snapshot.get("system", {}) if snapshot.get("ready") else {}
        memory = system.get("memory", {})
        vitals = {
            "cpu_percent": system.get("cpu"),
            "memory_percent": memory.get("percent") if memory.get("total") else None,
            "memory_used_gb": round(memory.get("used", 0) / 1024**3, 1),
            "memory_total_gb": round(memory.get("total", 0) / 1024**3, 1),
        } if system else {}
    except Exception:
        vitals = {}

    recent_clips = []
    clipboard_count = 0
    try:
        clip_store = store()
        recent_clips = clip_store.listing("", limit=3)
        clipboard_count = clip_store.count()
    except Exception:
        pass

    try:
        trash_items = trash.runs()
    except Exception:
        trash_items = []

    return {
        "vitals": vitals,
        "todos": uncompleted_todos,
        "recent_clips": recent_clips,
        "stats": {
            "notes_count": notes_count,
            "clipboard_count": clipboard_count,
            "trash_count": sum(r.get("count", 0) for r in trash_items),
            "trash_size": sum(r.get("size", 0) for r in trash_items),
        },
        "version": VERSION,
    }


def default_folder() -> str:
    downloads = Path.home() / "Downloads"
    return str(downloads) if downloads.is_dir() else str(Path.home())


def pick_folder(initial: str = "") -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # noqa: BLE001
        raise ApiError("Диалог выбора папки недоступен — впиши путь вручную") from exc

    result = {"path": ""}

    def run_dialog() -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:  # noqa: BLE001
            pass
        root.update()
        try:
            result["path"] = filedialog.askdirectory(
                parent=root,
                initialdir=initial or str(Path.home()),
                title="Выбери папку",
                mustexist=True,
            )
        finally:
            root.destroy()

    worker = threading.Thread(target=run_dialog, daemon=True)
    worker.start()
    worker.join(timeout=300)
    if worker.is_alive():
        raise ApiError("Диалог не ответил — впиши путь вручную")
    return result["path"]


def pick_file(initial: str = "") -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # noqa: BLE001
        raise ApiError("Диалог выбора файла недоступен — впиши путь вручную") from exc

    result = {"path": ""}

    def run_dialog() -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:  # noqa: BLE001
            pass
        root.update()
        try:
            result["path"] = filedialog.askopenfilename(
                parent=root,
                initialdir=initial or str(Path.home()),
                title="Выбери файл",
            )
        finally:
            root.destroy()

    worker = threading.Thread(target=run_dialog, daemon=True)
    worker.start()
    worker.join(timeout=300)
    if worker.is_alive():
        raise ApiError("Диалог не ответил — впиши путь вручную")
    return result["path"]


def open_in_explorer(path: str) -> None:
    target = Path(path).expanduser()
    if not target.exists():
        raise ApiError("Папка или файл не найдены")
    if sys.platform == "win32":
        if target.is_file():
            subprocess.Popen(["explorer", "/select,", str(target)])
        else:
            os.startfile(str(target))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


# --- HTTP ------------------------------------------------------------------


def _scan_diskmap(folder, selected_rust, job):
    diskmap.close_file_listing()
    if selected_rust:
        try:
            result = rust_diskmap.scan(folder, allow_volume_root=True, control=job)
        except rust_diskmap.WorkerError as exc:
            job.check()
            job.warning = str(exc)
            job.report(0, 0, 0)
        else:
            result["scan_backend"] = "rust"
            return result
    result = diskmap.scan(folder, allow_volume_root=True, control=job)
    result["scan_backend"] = "python"
    if job.warning:
        result["fallback_reason"] = job.warning
    return result


class HubServer(ThreadingHTTPServer):
    def __init__(self, *args, **kwargs):
        self.jobs = jobs.Jobs()
        super().__init__(*args, **kwargs)

    def server_close(self):
        self.jobs.shutdown()
        super().server_close()


class HubHandler(BaseHTTPRequestHandler):
    server_version = f"Hub/{VERSION}"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        if sys.stderr and args and str(args[0]).startswith(("4", "5")):
            sys.stderr.write(f"[hub] {fmt % args}\n")

    def _is_private_ip(self, hostname: str) -> bool:
        if hostname in ("127.0.0.1", "localhost", "[::1]"):
            return True
        try:
            parts = [int(p) for p in hostname.split(".")]
            if len(parts) == 4 and all(0 <= p <= 255 for p in parts):
                if parts[0] == 10:
                    return True
                if parts[0] == 172 and 16 <= parts[1] <= 31:
                    return True
                if parts[0] == 192 and parts[1] == 168:
                    return True
                if parts[0] == 127:
                    return True
        except Exception:
            pass
        return False

    def _is_allowed_host(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        if not host:
            return False
        hostname = host.split(":")[0]
        return self._is_private_ip(hostname)

    def _is_allowed_origin(self) -> bool:
        # Проверка Sec-Fetch-Site (отправляется браузерами на все запросы)
        fetch_site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if fetch_site and fetch_site not in ("same-origin", "none", "same-site"):
            return False

        # Проверка Origin (при CORS и POST/DELETE)
        origin = (self.headers.get("Origin") or "").strip().lower()
        if origin:
            parsed = urlparse(origin)
            if not self._is_private_ip(parsed.hostname or ""):
                return False

        # Проверка Referer
        referer = (self.headers.get("Referer") or "").strip().lower()
        if referer:
            parsed = urlparse(referer)
            if not self._is_private_ip(parsed.hostname or ""):
                return False

        return True

    def _security_check(self) -> bool:
        if getattr(self.server, "desktop", False):
            local = self.client_address[0] == "127.0.0.1"
            host = self.headers.get("Host", "").lower()
            origin = self.headers.get("Origin")
            local_hosts = {f"{name}:{self.server.server_port}" for name in ("127.0.0.1", "localhost")}
            phone_routes = {
                "GET": {"/drop", "/api/drop/info", "/api/drop/latest-text", "/api/drop/download"},
                "POST": {"/api/drop/send-text", "/api/drop/upload"},
            }
            if (local and host not in local_hosts) or (
                not local and urlparse(self.path).path not in phone_routes.get(self.command, ())
            ) or (origin and origin != f"http://{host}"):
                self._send_json({"error": "Запрос недоступен"}, 403)
                return False
        if not self._is_allowed_host():
            self._send_json(
                {"error": "Запрос заблокирован: недопустимый узел Host (защита от DNS Rebinding)"},
                403,
            )
            return False
        if not self._is_allowed_origin():
            self._send_json(
                {"error": "Запрос заблокирован: запрещён межсайтовый доступ (CSRF/CORS)"},
                403,
            )
            return False
        return True

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' data:; connect-src 'self'")
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path) -> None:
        data = path.read_bytes()
        content_type = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
        if content_type.startswith(("text/", "application/json", "application/javascript", "image/svg")):
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' data:; connect-src 'self'")
        self.end_headers()
        self.wfile.write(data)

    def _send_text_attachment(self, content: str, filename: str, content_type: str = "text/plain") -> None:
        data = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        quoted_filename = filename.replace('"', '\\"')
        self.send_header("Content-Disposition", f'attachment; filename="{quoted_filename}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' data:; connect-src 'self'")
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes_attachment(self, data: bytes, filename: str, content_type: str = "application/octet-stream") -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        quoted_filename = filename.replace('"', '\\"')
        self.send_header("Content-Disposition", f'attachment; filename="{quoted_filename}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' data:; connect-src 'self'")
        self.end_headers()
        self.wfile.write(data)

    def _send_thumb(self, raw_path: str) -> None:
        """Превью для найденных дубликатов: только файлы из последнего скана."""
        path = Path(unquote(raw_path))
        if not raw_path or not duplicates.allowed_path(str(path)):
            return self._send_json({"error": "Этот файл не из последней проверки"}, 404)
        content_type = IMAGE_TYPES.get(path.suffix.lower())
        if not content_type:
            return self._send_json({"error": "Превью есть только для картинок"}, 404)
        try:
            if not path.is_file() or path.stat().st_size > MAX_THUMB_BYTES:
                return self._send_json({"error": "Не получилось показать файл"}, 404)
            data = path.read_bytes()
        except OSError:
            return self._send_json({"error": "Не получилось прочитать файл"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=120")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' data:; connect-src 'self'")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError("Некорректная длина запроса")
        if length > MAX_BODY_BYTES:
            raise ApiError("Слишком большой запрос", 413)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ApiError("Некорректный JSON")
        return parsed if isinstance(parsed, dict) else {}

    # -- маршруты --

    def do_GET(self) -> None:  # noqa: N802
        if not self._security_check():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/desktop-state.js":
                state = preferences.read() if getattr(self.server, "desktop", False) else None
                data = f"window.hubDesktopState = {json.dumps(state)};".encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/javascript; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            if path == "/api/info":
                return self._send_json(
                    {
                        "tools": TOOLS,
                        "version": VERSION,
                        "default_folder": default_folder(),
                        "platform": sys.platform,
                        "diskmap_jobs": self.client_address[0] == "127.0.0.1" and hasattr(self.server, "jobs"),
                        "diskmap_rust": self.client_address[0] == "127.0.0.1" and
                        preferences.read().get(preferences.RUST_DISKMAP) == "on",
                    }
                )
            if path == "/api/about":
                return self._send_json(about_info())
            if path == "/api/home/summary":
                return self._send_json(home_summary())
            if path == "/api/clipboard/items":
                query = parse_qs(parsed.query)
                text = (query.get("q") or [""])[0]
                kind = (query.get("type") or [""])[0]
                try:
                    limit = max(1, min(1000, int((query.get("limit") or ["150"])[0])))
                except ValueError:
                    limit = 150
                return self._send_json(
                    {
                        "items": store().listing(text, limit, kind=kind),
                        "total": store().count(),
                        "paused": watcher().paused.is_set(),
                    }
                )
            if path == "/api/clipboard/state":
                return self._send_json(
                    {
                        "paused": watcher().paused.is_set(),
                        "total": store().count(),
                        "error": watcher().last_error,
                    }
                )
            if path == "/api/sorter/last-run":
                return self._send_json({"last_run": filesorter.last_run()})
            if path == "/api/sorter/rules":
                return self._send_json({"rules": filesorter.get_rules()})
            if path == "/api/dupes/last-run":
                return self._send_json({"last_run": duplicates.last_run()})
            if path == "/api/diskmap/last-run":
                try:
                    return self._send_json({"last_run": diskmap.last_run()})
                except OSError as exc:
                    return self._send_json({"error": str(exc)}, 400)
            if path == "/api/bigfiles/last-run":
                return self._send_json({"last_run": bigfiles.last_run()})
            if path == "/api/cleanup/last-run":
                return self._send_json({"last_run": cleanup.last_run()})
            if path == "/api/cleanup/rules":
                return self._send_json(cleanup.get_rules())
            if path == "/api/notes/items":
                query = parse_qs(parsed.query)
                text = (query.get("q") or [""])[0]
                return self._send_json({"items": notes.store().listing(text), "total": notes.store().count()})
            if path == "/api/notes/export":
                query = parse_qs(parsed.query)
                note_id = (query.get("id") or [""])[0]
                fmt = (query.get("format") or ["md"])[0]
                mime = "text/markdown" if fmt == "md" else "text/plain"
                try:
                    if note_id:
                        filename, content = notes.store().export_note(note_id, fmt)
                    else:
                        filename, content = notes.store().export_all(fmt)
                    return self._send_text_attachment(content, filename, mime)
                except Exception as exc:
                    return self._send_json({"error": str(exc)}, 400)
            if path == "/api/monitor/snapshot":
                return self._send_json(monitor.snapshot())
            if path == "/api/trash/runs":
                runs = trash.runs()
                return self._send_json(
                    {
                        "runs": runs,
                        "total_count": sum(run["count"] for run in runs),
                        "total_size": sum(run["size"] for run in runs),
                    }
                )
            if path == "/api/autostart":
                return self._send_json(autostart.status())
            if path == "/api/shortcuts/status":
                return self._send_json(shortcuts.status())
            if path == "/api/system/backup":
                import io
                import zipfile
                from datetime import datetime

                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    if DATA_DIR.is_dir():
                        for root, _, files in os.walk(DATA_DIR):
                            for file in sorted(files):
                                if file.endswith((".lock", ".tmp")):
                                    continue
                                fp = Path(root) / file
                                arcname = fp.relative_to(DATA_DIR)
                                zf.write(fp, arcname)
                buffer.seek(0)
                filename = f"hub_backup_{datetime.now().strftime('%Y-%m-%d')}.zip"
                return self._send_bytes_attachment(buffer.getvalue(), filename, "application/zip")
            if path == "/api/search":
                query = parse_qs(parsed.query)
                text = (query.get("q") or [""])[0]
                return self._send_json(
                    search.run(text, TOOLS, notes.store().listing(""), store().listing("", 500))
                )
            if path == "/drop":
                return self._send_file(WEB_DIR / "drop.html")
            if path == "/api/renamer/last-run":
                return self._send_json({"last_run": renamer.last_run()})
            if path == "/api/drop/info":
                return self._send_json(qrdrop.get_info(self.server.server_port))
            if path == "/api/drop/qr.svg":
                try:
                    from qrcode import make
                    from qrcode.image.svg import SvgPathFillImage
                    from qrcode.image.styles.moduledrawers.svg import SvgPathCircleDrawer
                except ImportError:
                    return self._send_json({"error": "QR-код недоступен, используй адрес"}, 404)
                svg = make(qrdrop.get_drop_url(self.server.server_port), image_factory=SvgPathFillImage,
                           module_drawer=SvgPathCircleDrawer()).to_string()
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml")
                self.send_header("Content-Length", str(len(svg)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(svg)
                return
            if path == "/api/drop/latest-text":
                texts = qrdrop.list_incoming_texts(1)
                try:
                    clip_items = store().listing("", 1)
                    clip_text = clip_items[0]["text"] if clip_items else ""
                except Exception:
                    clip_text = ""
                return self._send_json({
                    "latest_text": texts[0]["text"] if texts else clip_text,
                    "clipboard": clip_text,
                })
            if path == "/api/drop/download":
                query = parse_qs(parsed.query)
                name = (query.get("name") or [""])[0]
                kind = (query.get("type") or ["shared"])[0]
                folder = qrdrop.INCOMING_DIR if kind == "incoming" else qrdrop.SHARED_DIR
                target = folder / qrdrop._sanitize_filename(name)
                if target.is_file():
                    return self._send_bytes_attachment(target.read_bytes(), target.name)
                return self._send_json({"error": "Файл не найден"}, 404)
            if path == "/api/tray/status":
                return self._send_json(tray.status())
            if path == "/api/dupes/thumb":
                query = parse_qs(parsed.query)
                return self._send_thumb((query.get("path") or [""])[0])
            if path.startswith("/api/"):
                return self._send_json({"error": "Неизвестный запрос"}, 404)
        except ApiError as exc:
            return self._send_json({"error": str(exc)}, exc.status)
        return self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        if not self._security_check():
            return
        path = urlparse(self.path).path
        if path == "/api/drop/upload":
            try:
                content_type = self.headers.get("Content-Type", "")
                length = int(self.headers.get("Content-Length") or 0)
                if length > qrdrop.MAX_FILE_BYTES:
                    return self._send_json({"error": "Файл слишком большой (максимум 100 МБ)"}, 413)

                if "multipart/form-data" in content_type:
                    boundary = content_type.split("boundary=")[-1].strip().encode("utf-8")
                    raw_body = self.rfile.read(length)
                    parts = raw_body.split(b"--" + boundary)
                    saved_files = []
                    for part in parts:
                        if b'filename="' in part:
                            headers_part, file_data = part.split(b"\r\n\r\n", 1)
                            if file_data.endswith(b"\r\n"):
                                file_data = file_data[:-2]
                            match = re.search(rb'filename="([^"]+)"', headers_part)
                            if match:
                                filename = match.group(1).decode("utf-8", errors="replace")
                                res = qrdrop.save_incoming_file(filename, file_data)
                                saved_files.append(res)
                    if saved_files:
                        return self._send_json({"saved": saved_files, "ok": True})
                    return self._send_json({"error": "Файл не найден в форме"}, 400)

                raw_filename = self.headers.get("X-Filename")
                if raw_filename:
                    filename = unquote(raw_filename)
                    data = self.rfile.read(length)
                    res = qrdrop.save_incoming_file(filename, data)
                    return self._send_json({"file": res, "ok": True})

                return self._send_json({"error": "Не указан заголовок X-Filename или multipart/form-data"}, 400)
            except Exception as e:
                return self._send_json({"error": str(e)}, 500)

        try:
            body = self._read_json()
            payload = self._dispatch_post(path, body)
        except ApiError as exc:
            return self._send_json({"error": str(exc)}, exc.status)
        except (
            fileguard.GuardError,
            filesorter.ScanError,
            duplicates.ScanError,
            duplicates.RemoveError,
            diskmap.ScanError,
            diskmap.RemoveError,
            bigfiles.ScanError,
            bigfiles.RemoveError,
            cleanup.ScanError,
            cleanup.RemoveError,
            compare.CompareError,
            images.ImageError,
            monitor.MonitorError,
            notes.NoteError,
            trash.TrashError,
            autostart.AutostartError,
            FileNotFoundError,
            NotADirectoryError,
            ValueError,
            PermissionError,
        ) as exc:
            return self._send_json({"error": str(exc)}, 400)
        except clipboard.ClipboardUnavailable as exc:
            return self._send_json({"error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            return self._send_json({"error": f"Внутренняя ошибка: {exc}"}, 500)
        self._send_json(payload)

    def _dispatch_post(self, path: str, body: dict) -> dict:
        desktop = getattr(self.server, "desktop", False)
        if desktop and path == "/api/desktop/preferences":
            settings = preferences.update(body)
            if preferences.OPTIONS.keys() & body.keys():
                self.server.apply_theme(settings.get("hub-theme") == "dark")
            return settings

        if desktop and path == "/api/desktop/open-transfer":
            webbrowser.open(f"http://127.0.0.1:{self.server.server_port}/transfer.html")
            return {"ok": True}

        if path == "/api/clipboard/copy":
            item = store().get(str(body.get("id", "")))
            if not item:
                raise ApiError("Запись не найдена", 404)
            clipboard.write_text(item["text"])
            return {"ok": True}

        if path == "/api/clipboard/pin":
            item = store().toggle_pin(str(body.get("id", "")))
            if not item:
                raise ApiError("Запись не найдена", 404)
            return {"item": {"id": item["id"], "pinned": item["pinned"]}}

        if path == "/api/clipboard/delete":
            if not store().delete(str(body.get("id", ""))):
                raise ApiError("Запись не найдена", 404)
            return {"ok": True}

        if path == "/api/clipboard/clear":
            return {"removed": store().clear()}

        if path == "/api/clipboard/add":
            text = str(body.get("text", ""))
            pin = bool(body.get("pin", False))
            item = store().add(text, skip_sensitive=False)
            if not item:
                raise ApiError("Не удалось добавить текст (пустой или слишком длинный)")
            if pin:
                item = store().toggle_pin(item["id"]) or item
            return {"item": item}

        if path == "/api/clipboard/pause":
            paused = bool(body.get("paused"))
            if paused:
                watcher().pause()
            else:
                watcher().resume()
            return {"paused": paused}

        if path == "/api/sorter/scan":
            return filesorter.scan(str(body.get("folder", "")))

        if path == "/api/sorter/apply":
            files = body.get("files") or []
            if not isinstance(files, list):
                raise ApiError("Список файлов должен быть массивом")
            return filesorter.apply(str(body.get("folder", "")), [str(item) for item in files])

        if path == "/api/sorter/undo":
            return filesorter.undo(str(body.get("run_id", "")))

        if path == "/api/sorter/rules":
            if body.get("reset"):
                return {"rules": filesorter.reset_rules()}
            return {"rules": filesorter.save_rules(body.get("rules") or [])}

        if path == "/api/dupes/scan":
            recursive = body.get("recursive")
            try:
                min_size = int(body.get("min_size", duplicates.DEFAULT_MIN_SIZE))
            except (TypeError, ValueError):
                min_size = duplicates.DEFAULT_MIN_SIZE
            return duplicates.scan(
                str(body.get("folder", "")),
                recursive=True if recursive is None else bool(recursive),
                min_size=min_size,
            )

        if path == "/api/dupes/remove":
            paths = body.get("files") or []
            if not isinstance(paths, list):
                raise ApiError("Список файлов должен быть массивом")
            return duplicates.remove(str(body.get("folder", "")), [str(item) for item in paths])

        if path == "/api/dupes/undo":
            return duplicates.undo(str(body.get("run_id", "")))

        if path == "/api/diskmap/backend":
            if self.client_address[0] != "127.0.0.1":
                raise ApiError("Настройки карты диска доступны только на этом ПК", 403)
            enabled = body.get("enabled")
            if not isinstance(enabled, bool):
                raise ApiError("Укажи, включён ли Rust Core", 400)
            settings = preferences.update({preferences.RUST_DISKMAP: "on" if enabled else "off"})
            return {"enabled": settings.get(preferences.RUST_DISKMAP) == "on"}

        if path in ("/api/diskmap/jobs/start", "/api/diskmap/jobs/status", "/api/diskmap/jobs/cancel"):
            if self.client_address[0] != "127.0.0.1" or not hasattr(self.server, "jobs"):
                raise ApiError("Задания карты диска доступны только на этом ПК", 403)
            if path.endswith("/start"):
                folder = body.get("folder", "")
                if not isinstance(folder, str) or not folder.strip():
                    raise ApiError("Укажи папку, которую нужно посчитать", 400)
                selected_rust = preferences.read().get(preferences.RUST_DISKMAP) == "on"
                try:
                    identity = self.server.jobs.start(lambda job: _scan_diskmap(folder, selected_rust, job))
                except jobs.Busy as exc:
                    raise ApiError(str(exc), 409) from exc
                return {"id": identity}
            status = self.server.jobs.poll(body.get("id"), cancel=path.endswith("/cancel"))
            if status is None:
                raise ApiError("Задание карты диска недоступно", 404)
            return status

        if path == "/api/diskmap/scan":
            diskmap.close_file_listing()
            return diskmap.scan(str(body.get("folder", "")))

        if path == "/api/diskmap/files":
            return diskmap.files(str(body.get("folder", "")), paged=body.get("paged") is True)

        if path == "/api/diskmap/files/page":
            return diskmap.file_page(body.get("listing"), body.get("offset"))

        if path == "/api/diskmap/remove":
            return diskmap.remove_file(
                str(body.get("path", "")), str(body.get("mode", "")), body.get("confirmed", False),
                listing=body.get("listing"),
            )

        if path == "/api/diskmap/undo":
            return diskmap.undo(str(body.get("run_id", "")))

        if path == "/api/bigfiles/scan":
            try:
                limit = int(body.get("limit", bigfiles.DEFAULT_LIMIT))
            except (TypeError, ValueError):
                limit = bigfiles.DEFAULT_LIMIT
            try:
                min_size = int(body.get("min_size", bigfiles.DEFAULT_MIN_SIZE))
            except (TypeError, ValueError):
                min_size = bigfiles.DEFAULT_MIN_SIZE
            return bigfiles.scan(str(body.get("folder", "")), limit=limit, min_size=min_size)

        if path == "/api/bigfiles/remove":
            return bigfiles.remove(
                str(body.get("path", "")), str(body.get("mode", "")), body.get("confirmed", False)
            )

        if path == "/api/bigfiles/undo":
            return bigfiles.undo(str(body.get("run_id", "")))

        if path == "/api/compare/run":
            return compare.compare(
                str(body.get("left", "")), str(body.get("right", "")), deep=bool(body.get("deep"))
            )

        if path == "/api/compare/sync":
            return compare.sync_entry(
                str(body.get("source", "")),
                str(body.get("target", "")),
                str(body.get("path", "")),
            )

        if path == "/api/images/save":
            return images.save_image(
                str(body.get("folder", "")),
                str(body.get("filename", "")),
                str(body.get("data", "")),
            )

        if path == "/api/cleanup/scan":
            try:
                age_days = int(body.get("age_days", cleanup.DEFAULT_AGE_DAYS))
            except (TypeError, ValueError):
                age_days = cleanup.DEFAULT_AGE_DAYS
            include_junk = body.get("include_junk")
            return cleanup.scan(
                str(body.get("folder", "")),
                age_days=age_days,
                include_junk=True if include_junk is None else bool(include_junk),
            )

        if path == "/api/cleanup/remove":
            paths = body.get("paths") or []
            if not isinstance(paths, list):
                raise ApiError("Список путей должен быть массивом")
            return cleanup.remove(
                [str(item) for item in paths],
                str(body.get("mode", "trash")),
                body.get("confirmed", False),
                folder=str(body.get("folder", "")),
            )

        if path == "/api/cleanup/undo":
            return cleanup.undo(str(body.get("run_id", "")))

        if path == "/api/cleanup/rules":
            if body.get("reset"):
                return cleanup.reset_rules()
            return cleanup.save_rules(body.get("rules") or {})

        if path == "/api/monitor/terminate":
            try:
                pid = int(body.get("pid", 0))
            except (TypeError, ValueError):
                raise ApiError("Не понял, какой процесс закрывать")
            if "created" in body or "name" in body:
                expected = (str(body.get("name", "")), float(body.get("created", 0)))
                if "creation" in body:
                    expected += (str(body["creation"]),)
                return monitor.terminate(pid, expected)
            return monitor.terminate(pid)

        if path == "/api/monitor/minimize":
            if self.client_address[0] != "127.0.0.1":
                raise ApiError("Сворачивание окон доступно только на этом компьютере", 403)
            pid, name, creation = body.get("pid"), body.get("name"), body.get("creation")
            if type(pid) is not int or pid <= 0 or not isinstance(name, str) or not isinstance(creation, str):
                raise ApiError("Выбери процесс и попробуй снова")
            return monitor.minimize(pid, name, creation)

        if path == "/api/notes/create":
            return {"item": notes.store().create(str(body.get("title", "")), str(body.get("text", "")))}

        if path == "/api/notes/update":
            return {
                "item": notes.store().update(
                    str(body.get("id", "")), str(body.get("title", "")), str(body.get("text", ""))
                )
            }

        if path == "/api/notes/pin":
            return {"item": notes.store().toggle_pin(str(body.get("id", "")))}

        if path == "/api/notes/delete":
            if not notes.store().delete(str(body.get("id", ""))):
                raise ApiError("Заметка не найдена", 404)
            return {"ok": True}

        if path == "/api/trash/restore":
            return trash.undo(str(body.get("run_id", "")))

        if path == "/api/trash/purge":
            if body.get("confirmed") is not True:
                raise ApiError("Удаление из корзины требует подтверждения")
            raw = body.get("run_ids")
            if raw is None:
                raw = [str(body.get("run_id", ""))]
            if not isinstance(raw, list):
                raise ApiError("Список переносов должен быть массивом")
            return trash.purge([str(item) for item in raw])

        if path == "/api/trash/empty":
            if body.get("confirmed") is not True:
                raise ApiError("Очистка корзины требует подтверждения")
            return trash.empty()

        if path == "/api/autostart":
            return autostart.set_enabled(bool(body.get("enabled")))

        if path == "/api/shortcuts/create":
            target = str(body.get("target") or "desktop")
            try:
                return shortcuts.create(target)
            except shortcuts.ShortcutError as exc:
                raise ApiError(str(exc), 400) from exc

        if path == "/api/shortcuts/remove":
            target = str(body.get("target") or "desktop")
            try:
                return shortcuts.remove(target)
            except shortcuts.ShortcutError as exc:
                raise ApiError(str(exc), 400) from exc

        if path in ("/api/pick-folder", "/api/sorter/pick-folder", "/api/bigfiles/pick-folder",
                    "/api/cleanup/pick-folder", "/api/compare/pick-folder", "/api/images/pick-folder",
                    "/api/renamer/pick-folder"):
            return {"folder": pick_folder(str(body.get("initial", "")))}

        if path in ("/api/pick-file", "/api/checksum/pick-file", "/api/drop/pick-file"):
            return {"file": pick_file(str(body.get("initial", "")))}

        if path in ("/api/open", "/api/sorter/open", "/api/bigfiles/open",
                    "/api/cleanup/open", "/api/compare/open", "/api/images/open",
                    "/api/renamer/open", "/api/drop/open"):
            open_in_explorer(str(body.get("path", "")))
            return {"ok": True}

        if path == "/api/renamer/scan":
            return renamer.scan(
                str(body.get("folder", "")),
                str(body.get("filter", "*")),
                bool(body.get("recursive", False)),
            )

        if path == "/api/renamer/preview":
            return renamer.preview(
                str(body.get("folder", "")),
                body.get("files") or [],
                body.get("rule") or {},
            )

        if path == "/api/renamer/apply":
            return renamer.apply(
                str(body.get("folder", "")),
                body.get("renames") or [],
            )

        if path == "/api/renamer/undo":
            return renamer.undo(body.get("run_id"))

        if path == "/api/checksum/file":
            return checksum.compute_file_hashes(
                str(body.get("path", "")),
                body.get("algorithms"),
            )

        if path == "/api/checksum/text":
            return checksum.compute_text_hash(str(body.get("text", "")))

        if path == "/api/checksum/password":
            opts = {
                k: v for k, v in body.items()
                if k in ("length", "uppercase", "lowercase", "digits", "symbols",
                         "avoid_ambiguous", "mode", "words_count", "separator")
            }
            return checksum.generate_password(**opts)

        if path == "/api/drop/send-text":
            return qrdrop.save_incoming_text(str(body.get("text", "")), str(body.get("source", "phone")))

        if path == "/api/drop/share-file":
            return qrdrop.share_file(str(body.get("path", "")))

        if path == "/api/drop/unshare-file":
            return {"ok": qrdrop.unshare_file(str(body.get("name", "")))}

        if path == "/api/tray/toggle":
            enabled = bool(body.get("enabled", True))
            if enabled:
                tray.start_tray(self.server.server_port)
            else:
                tray.stop_tray()
            if desktop:
                preferences.update({"tray": "on" if enabled else "off"})
            return tray.status()

        if path == "/api/system/shutdown":
            if desktop:
                threading.Timer(0.3, self.server.close_window).start()
                return {"ok": True}

            def _stop() -> None:
                import time
                time.sleep(0.3)
                try:
                    watcher().stop()
                except Exception:
                    pass
                try:
                    monitor.stop()
                except Exception:
                    pass
                os._exit(0)

            threading.Thread(target=_stop, daemon=True).start()
            return {"ok": True, "message": "Сервер Hub остановлен"}

        raise ApiError("Неизвестный запрос", 404)

    def _serve_static(self, path: str) -> None:
        if getattr(self.server, "native_shell", False) and path not in ("/transfer.html", "/transfer.js"):
            return self._send_json({"error": "Не найдено"}, 404)
        relative = "index.html" if path in ("", "/") else unquote(path).lstrip("/")
        try:
            target = (WEB_DIR / relative).resolve()
            target.relative_to(WEB_DIR.resolve())
        except (ValueError, OSError):
            return self._send_json({"error": "Не найдено"}, 404)
        if not target.is_file():
            return self._send_json({"error": "Не найдено"}, 404)
        self._send_file(target)


def find_port(start: int = START_PORT) -> int:
    for port in range(start, start + PORT_ATTEMPTS):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise SystemExit("Не нашёл свободный порт. Закрой лишние программы и попробуй снова.")


def start_clipboard() -> clipboard.ClipboardWatcher:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    store_instance = clipboard.ClipboardStore(DATA_DIR / "clipboard.json")
    watcher_instance = clipboard.ClipboardWatcher(store_instance)
    _state.update(store=store_instance, watcher=watcher_instance)
    watcher_instance.start()
    return watcher_instance


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    watcher_instance = start_clipboard()

    open_browser = "--no-browser" not in sys.argv
    port = find_port()
    local_ip = qrdrop.get_local_ip()
    url = f"http://127.0.0.1:{port}/"

    server = HubServer(("0.0.0.0", port), HubHandler)
    server.daemon_threads = True

    # Запуск иконки в системном трее Windows и глобальных хоткеев (Win+Alt+H)
    if sys.platform == "win32":
        try:
            tray.start_tray(port)
        except Exception:
            pass

    print("Hub запущен")
    print(f"  Адрес на ПК: {url}")
    print(f"  Обмен с телефоном (QR-Drop): http://{local_ip}:{port}/drop")
    print(f"  История буфера: {DATA_DIR / 'clipboard.json'}")
    print("  Закрыть: Ctrl+C или закрой это окно")
    print()

    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстанавливаюсь…")
    finally:
        if sys.platform == "win32":
            try:
                tray.stop_tray()
            except Exception:
                pass
        watcher_instance.stop()
        server.server_close()


if __name__ == "__main__":
    main()
