"""Настройки обновлений и подтверждение запуска установщика Hub."""

from threading import Lock

from tools import updater
from tools.i18n import tr


_installing = Lock()


def mount(page):
    page.section(tr("Updates", "Обновления"))
    page.text(tr(f"Installed version: {page.hub.version}", f"Установлена версия {page.hub.version}"), muted=True)
    status = page.text("", muted=True)
    release = None

    def open_release():
        page.open_url(release.url if release else updater.RELEASES_URL + "/latest")

    def check():
        nonlocal release
        release = None
        check_button.IsEnabled = install_button.IsEnabled = False
        status.Text = tr("Checking for updates…", "Проверяю обновления…")

        def work():
            try:
                return updater.check(page.hub.version), ""
            except updater.UpdateError as error:
                return None, tr(error.english, str(error))

        def finish(result):
            nonlocal release
            release, error = result
            status.Text = error or (
                tr(f"Version {release.version} is available", f"Доступна версия {release.version}") if release else
                tr("Hub is up to date.", "У тебя актуальная версия Hub.")
            )
            check_button.IsEnabled = True
            install_button.IsEnabled = release is not None

        page.run(work, finish, message="")

    def install():
        if release is None or not page.confirm(
            tr("Install the Hub update?", "Установить обновление Hub?"),
            tr(
                f"Download Hub {release.version} from GitHub, verify it and start the installer. Hub will close.",
                f"Скачаю Hub {release.version} с GitHub, проверю файл и запущу мастер установки. Hub закроется.",
            ),
        ):
            return
        if not _installing.acquire(blocking=False):
            page.notice(tr("An update is already in progress.", "Обновление Hub уже запущено."))
            return
        selected = release
        check_button.IsEnabled = install_button.IsEnabled = False
        status.Text = tr(f"Downloading Hub {selected.version}…", f"Скачиваю Hub {selected.version}…")

        def work():
            try:
                updater.install(selected)
                page.hub.dispatch(page.hub.close)
                return ""
            except updater.UpdateError as error:
                return tr(error.english, str(error))
            finally:
                _installing.release()

        def finish(error):
            if error:
                status.Text = error
                check_button.IsEnabled = install_button.IsEnabled = True

        page.run(work, finish, message="")

    check_button, install_button, _ = page.actions(
        (tr("Check for updates", "Проверить обновления"), check),
        (tr("Download and install", "Скачать и установить"), install, True),
        (tr("Open release on GitHub", "Открыть релиз на GitHub"), open_release),
    )
    install_button.IsEnabled = False
