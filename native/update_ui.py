"""Настройки обновлений и подтверждение запуска установщика Hub."""

from threading import Lock

from tools import preferences, updater
from tools.i18n import tr


_installing = Lock()


def mount(page):
    page.section(tr("Updates", "Обновления"))
    info = page.hub.release
    installed = info.get("tag", page.hub.version) if isinstance(info, dict) else page.hub.version
    page.text(tr(f"Installed version: {installed}", f"Установлена версия {installed}"), muted=True)
    channels = ("stable", "beta")
    channel = "beta" if page.hub.settings.get(preferences.UPDATE_CHANNEL) == "beta" else "stable"
    selector = page.choice(tr("Release channel", "Канал обновлений"),
                           (tr("Stable", "Стабильный"), tr("Beta", "Бета")), channels.index(channel))
    status = page.text("", muted=True)
    release = None

    def open_release():
        fallback = updater.RELEASES_URL + ("/latest" if channel == "stable" else "")
        page.open_url(release.url if release else fallback)

    def set_enabled(enabled):
        selector.IsEnabled = check_button.IsEnabled = enabled
        install_button.IsEnabled = enabled and release is not None

    def change_channel(*_):
        nonlocal channel, release
        if selector.SelectedIndex not in (0, 1) or channels[selector.SelectedIndex] == channel:
            return
        selected = channels[selector.SelectedIndex]
        try:
            page.hub.settings = preferences.update({preferences.UPDATE_CHANNEL: selected})
        except OSError:
            selector.SelectedIndex = channels.index(channel)
            status.Text = tr("Could not save the update channel.", "Не удалось сохранить канал обновлений.")
            return
        channel = selected
        release = None
        install_button.IsEnabled = False
        status.Text = ""

    def check():
        nonlocal release
        release = None
        set_enabled(False)
        selected_channel = channel
        status.Text = tr("Checking for updates…", "Проверяю обновления…")

        def work():
            try:
                return updater.check(installed, selected_channel, include_installed=True), ""
            except updater.UpdateError as error:
                return None, tr(error.english, str(error))

        def finish(result):
            nonlocal release
            release, error = result
            if error:
                status.Text = error
            elif release is None:
                status.Text = tr("This channel has no published release.", "В этом канале пока нет опубликованных версий.")
            else:
                status.Text = tr(f"Latest in this channel: {release.version}", f"Последняя версия в канале: {release.version}")
                if updater.version_key(release.version) < updater.version_key(installed):
                    status.Text += tr(". Older than the installed version.", ". Она старее установленной.")
            set_enabled(True)

        page.run(work, finish, message="")

    def install():
        if release is None:
            return
        older = updater.version_key(release.version) < updater.version_key(installed)
        title = tr("Install an older version of Hub?", "Установить более старую версию Hub?") if older else tr(
            "Install this version of Hub?", "Установить эту версию Hub?")
        if not page.confirm(
            title,
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
        set_enabled(False)
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
                set_enabled(True)

        page.run(work, finish, message="")

    check_button, install_button, _ = page.actions(
        (tr("Check for updates", "Проверить обновления"), check),
        (tr("Download and install", "Скачать и установить"), install, True),
        (tr("Open release on GitHub", "Открыть релиз на GitHub"), open_release),
    )
    install_button.IsEnabled = False
    selector.SelectionChanged += change_channel
