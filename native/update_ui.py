"""Настройки обновлений и подтверждение запуска установщика Hub."""

from threading import Lock

from tools import updater


_installing = Lock()


def mount(page):
    page.section("Обновления")
    page.text(f"Установлена версия {page.hub.version}", muted=True)
    status = page.text("", muted=True)
    release = None

    def open_release():
        page.open_url(release.url if release else updater.RELEASES_URL + "/latest")

    def check():
        nonlocal release
        release = None
        check_button.IsEnabled = install_button.IsEnabled = False
        status.Text = "Проверяю обновления…"

        def work():
            try:
                return updater.check(page.hub.version), ""
            except updater.UpdateError as error:
                return None, str(error)

        def finish(result):
            nonlocal release
            release, error = result
            status.Text = error or (f"Доступна версия {release.version}" if release else "У тебя актуальная версия Hub.")
            check_button.IsEnabled = True
            install_button.IsEnabled = release is not None

        page.run(work, finish, message="")

    def install():
        if release is None or not page.confirm(
            "Установить обновление Hub?",
            f"Скачаю Hub {release.version} с GitHub, проверю файл и запущу мастер установки. Hub закроется.",
        ):
            return
        if not _installing.acquire(blocking=False):
            page.notice("Обновление Hub уже запущено.")
            return
        selected = release
        check_button.IsEnabled = install_button.IsEnabled = False
        status.Text = f"Скачиваю Hub {selected.version}…"

        def work():
            try:
                updater.install(selected)
                page.hub.dispatch(page.hub.close)
                return ""
            except updater.UpdateError as error:
                return str(error)
            finally:
                _installing.release()

        def finish(error):
            if error:
                status.Text = error
                check_button.IsEnabled = install_button.IsEnabled = True

        page.run(work, finish, message="")

    check_button, install_button, _ = page.actions(
        ("Проверить обновления", check),
        ("Скачать и установить", install, True),
        ("Открыть релиз на GitHub", open_release),
    )
    install_button.IsEnabled = False
