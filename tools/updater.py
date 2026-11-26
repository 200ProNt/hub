"""Проверка и установка стабильных обновлений Hub с GitHub."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from http.client import HTTPException
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


RELEASES_URL = "https://github.com/200ProNt/hub/releases"
API_URL = "https://api.github.com/repos/200ProNt/hub/releases/latest"
INSTALLER_NAME = "Hub-Setup-Windows-x64.exe"
MAX_INSTALLER_SIZE = 256 * 1024 * 1024
_ASSET_HOSTS = frozenset(("release-assets.githubusercontent.com", "objects.githubusercontent.com"))
_VERSION = re.compile(r"[0-9]{1,6}(?:\.[0-9]{1,6}){2,4}")
_VERIFY_ERROR = "Установщик не прошёл проверку размера или SHA-256."


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class Release:
    version: str
    size: int
    sha256: str

    def __post_init__(self):
        if not _VERSION.fullmatch(self.version):
            raise UpdateError("Тег релиза Hub имеет неверный формат.")
        if type(self.size) is not int or not 0 < self.size <= MAX_INSTALLER_SIZE:
            raise UpdateError("GitHub указал недопустимый размер установщика Hub.")
        if not re.fullmatch(r"[a-f0-9]{64}", self.sha256):
            raise UpdateError("GitHub не предоставил SHA-256 установщика Hub.")

    @property
    def url(self):
        return f"{RELEASES_URL}/tag/v{self.version}"

    @property
    def installer_url(self):
        return f"{RELEASES_URL}/download/v{self.version}/{INSTALLER_NAME}"


class _Redirects(HTTPRedirectHandler):
    def __init__(self, allowed_hosts):
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme != "https" or target.netloc not in self.allowed_hosts:
            fp.close()
            raise UpdateError("GitHub перенаправил запрос на неожиданный адрес.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _get(url, accept, allowed_hosts=()):
    opener = build_opener(_Redirects(allowed_hosts))
    request = Request(url, headers={"Accept": accept, "User-Agent": "Hub Windows Updater"})
    return opener.open(request, timeout=12)


def _version_key(version):
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise UpdateError("Версия Hub имеет неверный формат.")
    parts = tuple(map(int, version.split(".")))
    return parts + (0,) * (5 - len(parts))


def check(current_version):
    """Вернуть новый релиз или None. При сбое поднять UpdateError."""
    installed = _version_key(current_version)
    max_metadata = 1024 * 1024
    try:
        with _get(API_URL, "application/vnd.github+json") as response:
            body = response.read(max_metadata + 1)
        if len(body) > max_metadata:
            raise UpdateError("Ответ GitHub слишком большой.")
        data = json.loads(body)
    except (OSError, HTTPException) as error:
        raise UpdateError("Не удалось связаться с GitHub. Проверь подключение и попробуй ещё раз.") from error
    except (ValueError, RecursionError) as error:
        raise UpdateError("GitHub вернул некорректный ответ.") from error

    if not isinstance(data, dict) or any(type(data.get(key)) is not bool for key in ("draft", "prerelease")):
        raise UpdateError("GitHub вернул некорректный ответ.")
    if data["draft"] or data["prerelease"]:
        return None
    tag = data.get("tag_name")
    if not isinstance(tag, str) or not tag.startswith("v"):
        raise UpdateError("Тег релиза Hub имеет неверный формат.")
    if _version_key(tag[1:]) <= installed:
        return None

    assets = data.get("assets")
    matches = [
        asset for asset in assets
        if isinstance(asset, dict) and asset.get("name") == INSTALLER_NAME
    ] if isinstance(assets, list) else []
    if len(matches) != 1 or matches[0].get("state") != "uploaded":
        raise UpdateError("В релизе GitHub нет установщика Hub для Windows x64.")
    asset = matches[0]
    digest = asset.get("digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise UpdateError("GitHub не предоставил SHA-256 установщика Hub.")
    release = Release(tag[1:], asset.get("size"), digest.removeprefix("sha256:"))
    if data.get("html_url") != release.url or asset.get("browser_download_url") != release.installer_url:
        raise UpdateError("Адрес релиза или установщика не соответствует версии Hub.")
    return release


def _launch(installer):
    # Мастер может заново запустить Hub после удаления временных файлов старой версии.
    environment = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    bundle = getattr(sys, "_MEIPASS", None)
    restore_dll_directory = None
    if sys.platform == "win32" and bundle:
        import ctypes
        from ctypes.wintypes import LPCWSTR

        restore_dll_directory = ctypes.WinDLL("kernel32", use_last_error=True).SetDllDirectoryW
        restore_dll_directory.argtypes = [LPCWSTR]
        if not restore_dll_directory(None):
            raise ctypes.WinError(ctypes.get_last_error())
    try:
        subprocess.Popen([str(installer)], cwd=installer.parent, shell=False, env=environment)
    finally:
        if restore_dll_directory is not None:
            restore_dll_directory(bundle)


def install(release):
    """Скачать проверенный релиз и запустить мастер после согласия пользователя."""
    directory = None
    launched = False
    try:
        directory = Path(tempfile.mkdtemp(prefix="Hub-update-"))
        partial = directory / "download.part"
        digest = hashlib.sha256()
        received = 0
        with _get(release.installer_url, "application/octet-stream", _ASSET_HOSTS) as response, partial.open("xb") as output:
            while chunk := response.read(min(1024 * 1024, release.size - received + 1)):
                received += len(chunk)
                if received > release.size:
                    raise UpdateError(_VERIFY_ERROR)
                digest.update(chunk)
                output.write(chunk)
        if received != release.size or digest.hexdigest() != release.sha256:
            raise UpdateError(_VERIFY_ERROR)
        installer = partial.rename(directory / INSTALLER_NAME)
        try:
            _launch(installer)
        except OSError as error:
            raise UpdateError("Не удалось запустить установщик Hub.") from error
        launched = True
    except (OSError, HTTPException, ValueError) as error:
        raise UpdateError("Не удалось скачать и сохранить установщик Hub. Попробуй открыть релиз на GitHub.") from error
    finally:
        # shortcut: файл остаётся в %TEMP% после запуска, удалять после выхода мастера при необходимости
        if directory is not None and not launched:
            shutil.rmtree(directory, ignore_errors=True)
