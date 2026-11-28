"""Connect to local models and review their output."""

import json

from System.Windows import Visibility
from System.Windows.Controls import PasswordBox
from tools import file_index, jobs, local_ai
from tools.i18n import tr
from tools.registry import NATIVE_TOOLS, TOOLS

from .widgets import make


def mount(page):
    settings = local_ai.settings()
    providers = tuple(local_ai.PORTS)
    saved_provider = settings.get("provider")
    provider = page.choice(tr("Local server", "Локальный сервер"), ("Ollama", "LM Studio"),
                           index=providers.index(saved_provider) if saved_provider in providers else 0)
    default = lambda name: f"http://127.0.0.1:{local_ai.PORTS[name]}"
    address = page.field(tr("Server address", "Адрес сервера"),
                         str(settings.get("address") or default(providers[provider.SelectedIndex])))
    token = make(PasswordBox, MinHeight=32)
    page.group(tr("Local API token (optional)", "Токен локального API (необязательно)"), token).Children.Add(token)
    model = page.choice(tr("Model", "Модель"), [])
    temperature = page.field(tr("Temperature (0–1)", "Температура (0–1)"), str(settings.get("temperature", 0.3)))
    tokens = page.field(tr("Maximum output tokens", "Максимум токенов ответа"), str(settings.get("tokens", 768)))
    state = page.text(tr("Test the connection to list local models.", "Проверь подключение, чтобы увидеть локальные модели."), 13, True)
    purpose = page.choice(tr("Task", "Задача"), (
        tr("Help with Hub", "Помощь по Hub"), tr("Find files", "Найти файлы"),
        tr("Explain results", "Объяснить результат"), tr("Organize files", "Организовать файлы"),
        tr("Technical question", "Технический вопрос"), tr("Draft a workflow", "Подготовить сценарий")))
    index_query = page.field(tr("Optional query for the local file index", "Запрос к локальному индексу (по желанию)"))
    index_query.Parent.Visibility = Visibility.Collapsed
    prompt = page.field(tr("Question or instructions", "Вопрос или инструкция"), multiline=True)
    output = page.field(tr("Model response", "Ответ модели"), multiline=True)
    output.IsReadOnly = True
    output.MaxHeight = 290
    current = None
    draft = None

    def clear_models(*_):
        model.Items.Clear()
        state.Text = tr("Test the connection to list local models.", "Проверь подключение, чтобы увидеть локальные модели.")

    def provider_changed(*_):
        address.Text = default(providers[max(0, provider.SelectedIndex)])
        token.Clear()
        clear_models()

    def make_client():
        code = providers[max(0, provider.SelectedIndex)]
        return local_ai.Client(code, address.Text, jobs.Job(float("inf")), token.Password)

    def cancel():
        if current:
            current.cancel()

    def launch(client, work, complete, message):
        nonlocal current
        if page.busy:
            return
        current = client
        cancel_button.IsEnabled = True
        state.Text = message

        def run():
            try:
                return work(), ""
            except jobs.Cancelled:
                return None, tr("Request cancelled.", "Запрос отменён.")
            except Exception as exc:
                return None, str(exc)

        def finish(result):
            nonlocal current
            current = None
            cancel_button.IsEnabled = False
            value, error = result
            if error:
                state.Text = error
            else:
                complete(value)

        page.run(run, finish, message)

    def test():
        if page.busy:
            return
        endpoint_text = address.Text
        client = make_client()

        def show(names):
            if address.Text != endpoint_text or providers[max(0, provider.SelectedIndex)] != client.provider:
                return
            for name in names:
                model.Items.Add(name)
            model.SelectedIndex = names.index(settings.get("model")) if settings.get("model") in names else (0 if names else -1)
            state.Text = (tr(f"Connected · {len(names)} local models", f"Подключено · Локальных моделей: {len(names)}")
                          if names else tr("Connected. No supported local models found.", "Подключено. Локальных моделей нет."))

        clear_models()
        launch(client, client.models, show, tr("Checking local server…", "Проверяю локальный сервер…"))

    def ask():
        nonlocal draft
        if page.busy:
            return
        if model.SelectedItem is None:
            page.notice(tr("Test the connection and select a model.", "Проверь подключение и выбери модель."))
            return
        client = make_client()
        selected, endpoint_text = str(model.SelectedItem), address.Text
        variation, limit = float(temperature.Text.replace(",", ".")), int(tokens.Text)
        question, mode, search = prompt.Text, purpose.SelectedIndex, index_query.Text.strip()
        draft, output.Text = None, ""
        review.IsEnabled = False

        def work():
            guides = (
                "Explain Hub's tools and how to use them. Available tools: " +
                ", ".join(item["name"] for item in (*TOOLS, *NATIVE_TOOLS)),
                "Help the user look for local files using Hub's File Search. Do not invent file locations.",
                "Explain the output or error pasted by the user. Distinguish observations from assumptions.",
                "Suggest ways to organize files. Give suggestions without performing any operations.",
                "Help with the technical data supplied by the user.",
                local_ai.WORKFLOW_PROMPT,
            )
            guide = guides[max(0, mode)]
            if mode == 1 and search:
                found, _ = file_index.search(search)
                guide += "\nLocal index matches: " + json.dumps(
                    [record["path"] for record in found[:10]], ensure_ascii=False)
            text = client.ask(selected, guide, question, variation, limit, workflow=mode == 5)
            try:
                local_ai.save_settings(client.provider, endpoint_text, selected, variation, limit)
            except OSError:
                pass
            return text

        def show(text):
            nonlocal draft
            output.Text = text
            state.Text = tr("Response from the local model.", "Ответ локальной модели.")
            if mode == 5:
                try:
                    draft = local_ai.proposal(text)
                except local_ai.ModelError as error:
                    state.Text = str(error)
                review.IsEnabled = draft is not None

        launch(client, work, show, tr("Waiting for local model…", "Жду ответа локальной модели…"))

    def open_draft():
        if draft:
            page.hub.workflow_draft = draft
            page.go("automation")

    _, _, cancel_button, review, _ = page.actions(
        (tr("Test connection", "Проверить подключение"), test),
        (tr("Ask model", "Спросить модель"), ask, True),
        (tr("Cancel", "Отменить"), cancel),
        (tr("Review workflow draft", "Проверить черновик сценария"), open_draft),
        (tr("Copy response", "Скопировать ответ"), lambda: page.copy(output.Text)),
    )
    cancel_button.IsEnabled = review.IsEnabled = False
    provider.SelectionChanged += provider_changed
    address.TextChanged += clear_models
    purpose.SelectionChanged += lambda *_: setattr(index_query.Parent, "Visibility",
                                                    Visibility.Visible if purpose.SelectedIndex == 1 else Visibility.Collapsed)
    page.on_leave(cancel)
