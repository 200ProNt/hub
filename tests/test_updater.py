import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import URLError
from urllib.request import Request

from native import update_ui
from tools import updater


INSTALLER = b"test installer"
RELEASE = updater.Release("1.10.0", len(INSTALLER), hashlib.sha256(INSTALLER).hexdigest())


def metadata(**changes):
    asset = {
        "name": updater.INSTALLER_NAME,
        "state": "uploaded",
        "browser_download_url": RELEASE.installer_url,
        "size": RELEASE.size,
        "digest": f"sha256:{RELEASE.sha256}",
    }
    return {
        "tag_name": f"v{RELEASE.version}",
        "html_url": RELEASE.url,
        "draft": False,
        "prerelease": False,
        "assets": [asset],
        **changes,
    }


class UpdaterTests(unittest.TestCase):
    def check_with(self, data, installed="1.9.9.1"):
        with patch.object(updater, "_get", return_value=io.BytesIO(json.dumps(data).encode())) as get:
            result = updater.check(installed)
        get.assert_called_once_with(updater.API_URL, "application/vnd.github+json")
        return result

    def test_check_compares_version_components(self):
        self.assertEqual(self.check_with(metadata()), RELEASE)
        self.assertIsNone(self.check_with(metadata(), "1.10.0.0"))
        self.assertIsNone(self.check_with(metadata(), "1.10.0.1"))

    def test_check_uses_fifth_version_component(self):
        release = updater.Release("1.5.2.5.1", RELEASE.size, RELEASE.sha256)
        data = metadata(tag_name="v" + release.version, html_url=release.url)
        data["assets"][0]["browser_download_url"] = release.installer_url
        self.assertEqual(self.check_with(data, "1.5.2.5"), release)
        self.assertIsNone(self.check_with(data, release.version))
        self.assertIsNone(self.check_with(data, "1.5.2.6"))

    def test_check_skips_previews_and_drafts(self):
        for flags in ({"prerelease": True}, {"draft": True}):
            with self.subTest(flags=flags):
                self.assertIsNone(self.check_with(metadata(**flags)))

    def test_check_rejects_wrong_asset_metadata(self):
        for key, value in (
            ("name", "Unexpected.exe"),
            ("browser_download_url", RELEASE.installer_url.replace("v1.10.0", "v1.10.1")),
            ("browser_download_url", "https://untrusted.invalid/Hub-Setup-Windows-x64.exe"),
            ("size", updater.MAX_INSTALLER_SIZE + 1),
            ("digest", "sha256:abc"),
        ):
            with self.subTest(key=key, value=value):
                data = metadata()
                data["assets"][0][key] = value
                with self.assertRaises(updater.UpdateError):
                    self.check_with(data)
        with self.assertRaises(updater.UpdateError):
            self.check_with(metadata(tag_name="v1.10.0-preview"))

    def test_check_reports_offline(self):
        with patch.object(updater, "_get", side_effect=URLError("offline")):
            with self.assertRaisesRegex(updater.UpdateError, "Проверь подключение"):
                updater.check("1.9.9")

    def test_redirects_allow_only_pinned_https_asset_hosts(self):
        request = Request(RELEASE.installer_url)
        handler = updater._Redirects(updater._ASSET_HOSTS)
        allowed = "https://release-assets.githubusercontent.com/github-production-release-asset/123"
        self.assertEqual(handler.redirect_request(request, io.BytesIO(), 302, "", {}, allowed).full_url, allowed)
        for url in (
            allowed.replace("https://", "http://"),
            allowed.replace(".com/", ".com.untrusted.invalid/"),
            allowed.replace(".com/", ".com@untrusted.invalid/"),
            "https://github.com/another/repo/releases/download/v1.10.0/setup.exe",
        ):
            with self.subTest(url=url), io.BytesIO() as response:
                with self.assertRaises(updater.UpdateError):
                    handler.redirect_request(request, response, 302, "", {}, url)
        with self.assertRaises(updater.UpdateError):
            updater._Redirects(()).redirect_request(request, io.BytesIO(), 302, "", {}, allowed)

    def test_install_launches_only_verified_content_in_unique_directories(self):
        with tempfile.TemporaryDirectory() as root, patch.object(updater.tempfile, "tempdir", root):
            with patch.object(updater.subprocess, "Popen") as popen:
                for _ in range(2):
                    with patch.object(updater, "_get", return_value=io.BytesIO(INSTALLER)):
                        updater.install(RELEASE)
                paths = [Path(call.args[0][0]) for call in popen.call_args_list]
                self.assertEqual(len(set(paths)), 2)
                for path, call in zip(paths, popen.call_args_list):
                    self.assertEqual(path.name, updater.INSTALLER_NAME)
                    self.assertEqual(path.read_bytes(), INSTALLER)
                    self.assertEqual(call.kwargs["cwd"], path.parent)
                    self.assertFalse(call.kwargs["shell"])
                    self.assertEqual(call.kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1")

    def test_install_cleans_up_and_does_not_launch_invalid_downloads(self):
        with tempfile.TemporaryDirectory() as root, patch.object(updater.tempfile, "tempdir", root):
            for data in (b"x" * RELEASE.size, INSTALLER[:-1], INSTALLER + b"x"):
                with self.subTest(data=data):
                    with patch.object(updater, "_get", return_value=io.BytesIO(data)):
                        with patch.object(updater.subprocess, "Popen") as popen:
                            with self.assertRaisesRegex(updater.UpdateError, "SHA-256"):
                                updater.install(RELEASE)
                            popen.assert_not_called()
                    self.assertFalse(list(Path(root).iterdir()))


class UpdateUiTests(unittest.TestCase):
    def test_install_needs_confirmation_and_closes_hub_after_launch(self):
        page = Mock()
        page.hub.version = "1.9.9"
        check_button, install_button = Mock(), Mock()
        page.actions.return_value = [check_button, install_button, Mock()]
        page.run.side_effect = lambda work, finish, **_: finish(work())
        page.hub.dispatch.side_effect = lambda callback: callback()

        with patch.object(updater, "check", return_value=RELEASE) as check:
            update_ui.mount(page)
            check.assert_not_called()
            self.assertFalse(install_button.IsEnabled)
            (_, check_for_update), (_, install, _), (_, open_release) = page.actions.call_args.args
            check_for_update()
            check.assert_called_once_with("1.9.9")
            self.assertTrue(install_button.IsEnabled)
            open_release()
            page.open_url.assert_called_once_with(RELEASE.url)

        with patch.object(updater, "install") as launch:
            page.confirm.return_value = False
            install()
            launch.assert_not_called()
            page.hub.close.assert_not_called()

            page.confirm.return_value = True
            launch.side_effect = updater.UpdateError("Скачивание прервано.")
            install()
            self.assertTrue(install_button.IsEnabled)
            page.hub.close.assert_not_called()

            launch.side_effect = None
            install()
            launch.assert_called_with(RELEASE)
            page.hub.close.assert_called_once_with()
