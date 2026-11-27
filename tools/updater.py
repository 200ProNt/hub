"""Проверка и установка стабильных и бета-релизов Hub с GitHub."""

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
API_RELEASES = "https://api.github.com/repos/200ProNt/hub/releases"
API_URL = API_RELEASES + "/latest"
INSTALLER_NAME = "Hub-Setup-Windows-x64.exe"
MAX_INSTALLER_SIZE = 256 * 1024 * 1024
_ASSET_HOSTS = frozenset(("release-assets.githubusercontent.com", "objects.githubusercontent.com"))
_VERSION = re.compile(r"[0-9]{1,6}(?:\.[0-9]{1,6}){2,4}")
_RELEASE_VERSION = re.compile(rf"(?P<number>{_VERSION.pattern})(?P<beta>-beta(?:\.(?P<revision>[1-9][0-9]{{0,5}}))?)?")
_VERIFY_ERROR = (
    "Установщик не прошёл проверку размера или SHA-256.",
    "The installer failed its file size or SHA-256 check.",
)


class UpdateError(RuntimeError):
    def __init__(self, russian, english=None):
        super().__init__(russian)
        self.english = english or russian


@dataclass(frozen=True)
class Release:
    version: str
    size: int
    sha256: str

    def __post_init__(self):
        if not _RELEASE_VERSION.fullmatch(self.version):
            raise UpdateError("Тег релиза Hub имеет неверный формат.", "The Hub release tag has an invalid format.")
        if type(self.size) is not int or not 0 < self.size <= MAX_INSTALLER_SIZE:
            raise UpdateError("GitHub указал недопустимый размер установщика Hub.", "GitHub reported an invalid installer size.")
        if not re.fullmatch(r"[a-f0-9]{64}", self.sha256):
            raise UpdateError("GitHub не предоставил SHA-256 установщика Hub.", "GitHub did not provide the installer's SHA-256.")

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
            raise UpdateError("GitHub перенаправил запрос на неожиданный адрес.", "GitHub redirected the request to an unexpected address.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _get(url, accept, allowed_hosts=()):
    opener = build_opener(_Redirects(allowed_hosts))
    request = Request(url, headers={"Accept": accept, "User-Agent": "Hub Windows Updater"})
    return opener.open(request, timeout=12)


def _version_key(version):
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise UpdateError("Версия Hub имеет неверный формат.", "The Hub version has an invalid format.")
    parts = tuple(map(int, version.split(".")))
    return parts + (0,) * (5 - len(parts))


def version_key(version):
    match = _RELEASE_VERSION.fullmatch(version) if isinstance(version, str) else None
    if match is None:
        raise UpdateError("Версия Hub имеет неверный формат.", "The Hub version has an invalid format.")
    return _version_key(match["number"]), not match["beta"], int(match["revision"] or 0)


def _metadata(url):
    max_metadata = 4 * 1024 * 1024
    try:
        with _get(url, "application/vnd.github+json") as response:
            body = response.read(max_metadata + 1)
        if len(body) > max_metadata:
            raise UpdateError("Ответ GitHub слишком большой.", "The GitHub response was too large.")
        return json.loads(body)
    except (OSError, HTTPException) as error:
        raise UpdateError(
            "Не удалось связаться с GitHub. Проверь подключение и попробуй ещё раз.",
            "Could not reach GitHub. Check your connection and try again.",
        ) from error
    except (ValueError, RecursionError) as error:
        raise UpdateError("GitHub вернул некорректный ответ.", "GitHub returned an invalid response.") from error


def _latest_beta():
    best = None
    page = 1
    while True:
        releases = _metadata(f"{API_RELEASES}?per_page=100&page={page}")
        if not isinstance(releases, list):
            raise UpdateError("GitHub вернул некорректный ответ.", "GitHub returned an invalid response.")
        for release in releases:
            if not isinstance(release, dict) or release.get("draft") is not False or release.get("prerelease") is not True:
                continue
            tag = release.get("tag_name")
            match = _RELEASE_VERSION.fullmatch(tag[1:]) if isinstance(tag, str) and tag.startswith("v") else None
            if match and match["beta"] and (best is None or version_key(tag[1:]) > version_key(best["tag_name"][1:])):
                best = release
        if len(releases) < 100:
            return best
        page += 1


def check(current_version, channel="stable", *, include_installed=False):
    """Return the selected channel's installer, optionally allowing reinstall or downgrade."""
    installed = version_key(current_version)
    if channel == "beta":
        data = _latest_beta()
        if data is None:
            return None
    elif channel == "stable":
        data = _metadata(API_URL)
        if not isinstance(data, dict) or any(type(data.get(key)) is not bool for key in ("draft", "prerelease")):
            raise UpdateError("GitHub вернул некорректный ответ.", "GitHub returned an invalid response.")
        if data["draft"] or data["prerelease"]:
            return None
    else:
        raise ValueError(f"Unknown Hub update channel: {channel}")
    tag = data.get("tag_name")
    match = _RELEASE_VERSION.fullmatch(tag[1:]) if isinstance(tag, str) and tag.startswith("v") else None
    if match is None or bool(match["beta"]) != (channel == "beta"):
        raise UpdateError("Тег релиза Hub имеет неверный формат.", "The Hub release tag has an invalid format.")
    if not include_installed and version_key(tag[1:]) <= installed:
        return None

    assets = data.get("assets")
    matches = [
        asset for asset in assets
        if isinstance(asset, dict) and asset.get("name") == INSTALLER_NAME
    ] if isinstance(assets, list) else []
    if len(matches) != 1 or matches[0].get("state") != "uploaded":
        raise UpdateError("В релизе GitHub нет установщика Hub для Windows x64.", "The GitHub release has no Hub installer for Windows x64.")
    asset = matches[0]
    digest = asset.get("digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise UpdateError("GitHub не предоставил SHA-256 установщика Hub.", "GitHub did not provide the installer's SHA-256.")
    release = Release(tag[1:], asset.get("size"), digest.removeprefix("sha256:"))
    if data.get("html_url") != release.url or asset.get("browser_download_url") != release.installer_url:
        raise UpdateError(
            "Адрес релиза или установщика не соответствует версии Hub.",
            "The release or installer address does not match the Hub version.",
        )
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
                    raise UpdateError(*_VERIFY_ERROR)
                digest.update(chunk)
                output.write(chunk)
        if received != release.size or digest.hexdigest() != release.sha256:
            raise UpdateError(*_VERIFY_ERROR)
        installer = partial.rename(directory / INSTALLER_NAME)
        try:
            _launch(installer)
        except OSError as error:
            raise UpdateError("Не удалось запустить установщик Hub.", "Could not start the Hub installer.") from error
        launched = True
    except (OSError, HTTPException, ValueError) as error:
        raise UpdateError(
            "Не удалось скачать и сохранить установщик Hub. Попробуй открыть релиз на GitHub.",
            "Could not download and save the Hub installer. Try opening the release on GitHub.",
        ) from error
    finally:
        # shortcut: файл остаётся в %TEMP% после запуска, удалять после выхода мастера при необходимости
        if directory is not None and not launched:
            shutil.rmtree(directory, ignore_errors=True)
