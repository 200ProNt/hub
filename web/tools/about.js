/* Инструмент «О программе» */

(function () {
  const MARK = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <rect x="3.5" y="3.5" width="7" height="7" rx="2"/>
      <rect x="13.5" y="3.5" width="7" height="7" rx="2"/>
      <rect x="3.5" y="13.5" width="7" height="7" rx="2"/>
      <rect x="13.5" y="13.5" width="7" height="7" rx="2"/>
    </svg>`;

  const TEMPLATE = `
    <section class="card about-hero">
      <div class="about-mark" aria-hidden="true">${MARK}</div>
      <div class="about-hero-text">
        <h2>Hub <span class="pill pill-quiet" id="aboutVersion">версия …</span></h2>
        <p>Локальный набор инструментов: буфер обмена, заметки, файлы, уборка и мониторинг ПК.</p>
        <p class="about-author">Автор: <b>devrin</b> · открытый код</p>
      </div>
    </section>

    <section class="about-grid">
      <article class="card about-card">
        <span class="about-label">Версия</span>
        <span class="about-value" id="aboutVersionValue">—</span>
        <span class="about-sub">текущая сборка</span>
      </article>
      <article class="card about-card">
        <span class="about-label">Лицензия</span>
        <span class="about-value">MIT</span>
        <span class="about-sub">можно использовать и менять</span>
      </article>
      <article class="card about-card">
        <span class="about-label">Инструментов</span>
        <span class="about-value" id="aboutTools">—</span>
        <span class="about-sub">в одном окне</span>
      </article>
      <article class="card about-card">
        <span class="about-label">Технологии</span>
        <span class="about-value">Python + JS</span>
        <span class="about-sub">без сторонних библиотек</span>
      </article>
    </section>

    <div class="about-columns">
      <section class="card about-panel">
        <h3>Что это</h3>
        <p>Hub — маленький локальный сайт с инструментами на каждый день. Он запускается на этом компьютере и открывается в браузере: никаких аккаунтов, облака и подписок.</p>
        <ul class="about-points">
          <li>Все данные лежат в папке <code>data/</code> рядом с программой.</li>
          <li>Ничего не отправляется в сеть и не собирается телеметрия.</li>
          <li>Сторонних библиотек нет: только стандартный Python и обычные HTML, CSS, JavaScript.</li>
          <li>Сервер слушает только <code>127.0.0.1</code> — из локальной сети доступа нет.</li>
        </ul>
        <div class="about-actions">
          <button class="btn ghost small" id="aboutDesktopShortcut" type="button">Ярлык на Рабочий стол</button>
          <button class="btn ghost small" id="aboutStartShortcut" type="button">Ярлык в меню «Пуск»</button>
          <button class="btn ghost small" id="aboutIntro" type="button">Показать обучение снова</button>
        </div>
      </section>

      <section class="card about-panel">
        <h3>Исходный код</h3>
        <p>Проект открыт под лицензией MIT: код можно читать, запускать, менять и использовать в своих проектах. Достаточно сохранить уведомление об авторских правах.</p>
        <code class="about-path" id="aboutFolder">папка проекта</code>
        <div class="about-actions">
          <button class="btn ghost small" id="aboutOpen" type="button">Открыть папку проекта</button>
          <button class="btn ghost small" id="aboutReadme" type="button">Открыть README</button>
        </div>
      </section>
    </div>

    <section class="card about-changelog" id="aboutChangelog">
      <h3>История версий</h3>
      <ol class="about-releases" id="aboutReleases">
        <li class="about-release-empty">Загружаю…</li>
      </ol>
    </section>

    <details class="card about-license" id="aboutLicense">
      <summary>Текст лицензии MIT</summary>
      <pre id="aboutLicenseText">Загружаю…</pre>
    </details>

    <p class="about-foot">© 2026 devrin · MIT License · сделано для себя и друзей</p>`;

  const MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
  ];

  function formatDate(value) {
    const parts = String(value || "").split("-");
    if (parts.length !== 3) return String(value || "");
    const month = MONTHS[Number(parts[1]) - 1];
    if (!month) return String(value);
    return `${Number(parts[2])} ${month} ${parts[0]}`;
  }

  function renderReleases(changes, current) {
    const escape = Hub.escapeHtml;
    const list = Array.isArray(changes) ? changes : [];
    if (!list.length) {
      return '<li class="about-release-empty">История пока пустая.</li>';
    }
    return list
      .map((release, index) => {
        const version = String(release?.version || "—");
        const date = release?.date ? formatDate(release.date) : "";
        const items = Array.isArray(release?.items) ? release.items : [];
        const badge = version === current
          ? '<span class="about-release-badge">сейчас</span>'
          : "";
        const points = items
          .map((item) => `<li>${escape(item)}</li>`)
          .join("");
        return `
          <li class="about-release${index === 0 ? " is-latest" : ""}">
            <div class="about-release-head">
              <span class="about-release-version">${escape(version)}</span>
              ${badge}
              ${date ? `<span class="about-release-date">${escape(date)}</span>` : ""}
            </div>
            <ul class="about-release-items">${points}</ul>
          </li>`;
      })
      .join("");
  }

  window.HubTools.about = {
    mount(root) {
      root.innerHTML = TEMPLATE;

      const $ = (selector) => root.querySelector(selector);

      const state = {
        info: null,
        closed: false,
      };

      function render(data) {
        const version = data?.version || Hub.version || "—";
        $("#aboutVersion").textContent = version === "—" ? "версия неизвестна" : `версия ${version}`;
        $("#aboutVersionValue").textContent = version;
        $("#aboutTools").textContent = String(data?.tools || Hub.tools.length || "—");
        $("#aboutFolder").textContent = data?.folder || "папка проекта";
        $("#aboutFolder").title = data?.folder || "";
        $("#aboutLicenseText").textContent = data?.license_text
          || (data ? "Файл LICENSE не найден рядом с программой." : "Загружаю…");
        $("#aboutReleases").innerHTML = data
          ? renderReleases(data.changes, version)
          : '<li class="about-release-empty">Загружаю…</li>';
      }

      async function openFolder() {
        const folder = state.info?.folder;
        if (!folder || state.closed) return;
        try {
          await Hub.api("/api/open", { path: folder });
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        }
      }

      async function openReadme() {
        const readme = state.info?.readme;
        if (!readme || state.closed) return;
        try {
          await Hub.api("/api/open", { path: readme });
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        }
      }

      function replayIntro() {
        if (state.closed) return;
        if (window.HubIntro && typeof window.HubIntro.open === "function") window.HubIntro.open();
      }

      async function syncShortcuts() {
        try {
          const res = await Hub.api("/api/shortcuts/status");
          if (!res.supported) {
            const dt = $("#aboutDesktopShortcut");
            const sm = $("#aboutStartShortcut");
            if (dt) dt.classList.add("hidden");
            if (sm) sm.classList.add("hidden");
            return;
          }
          const dtBtn = $("#aboutDesktopShortcut");
          const smBtn = $("#aboutStartShortcut");
          if (dtBtn) {
            dtBtn.textContent = res.desktop ? "Удалить ярлык с Рабочего стола" : "Ярлык на Рабочий стол";
            dtBtn.classList.toggle("danger", res.desktop);
          }
          if (smBtn) {
            smBtn.textContent = res.start_menu ? "Удалить ярлык из меню «Пуск»" : "Ярлык в меню «Пуск»";
            smBtn.classList.toggle("danger", res.start_menu);
          }
        } catch {}
      }

      const dtBtn = $("#aboutDesktopShortcut");
      if (dtBtn) {
        dtBtn.addEventListener("click", async () => {
          try {
            const st = await Hub.api("/api/shortcuts/status");
            if (st.desktop) {
              await Hub.api("/api/shortcuts/remove", { target: "desktop" });
              Hub.toast("Ярлык удалён с Рабочего стола");
            } else {
              await Hub.api("/api/shortcuts/create", { target: "desktop" });
              Hub.toast("Ярлык создан на Рабочем столе");
            }
            syncShortcuts();
          } catch (e) {
            Hub.toast(e.message);
          }
        });
      }

      const smBtn = $("#aboutStartShortcut");
      if (smBtn) {
        smBtn.addEventListener("click", async () => {
          try {
            const st = await Hub.api("/api/shortcuts/status");
            if (st.start_menu) {
              await Hub.api("/api/shortcuts/remove", { target: "start_menu" });
              Hub.toast("Ярлык удалён из меню «Пуск»");
            } else {
              await Hub.api("/api/shortcuts/create", { target: "start_menu" });
              Hub.toast("Ярлык добавлен в меню «Пуск»");
            }
            syncShortcuts();
          } catch (e) {
            Hub.toast(e.message);
          }
        });
      }

      $("#aboutOpen").addEventListener("click", openFolder);
      $("#aboutReadme").addEventListener("click", openReadme);
      $("#aboutIntro").addEventListener("click", replayIntro);

      syncShortcuts();

      render(null);
      Hub.api("/api/about")
        .then((data) => {
          if (state.closed) return;
          state.info = data;
          render(data);
        })
        .catch((error) => {
          if (!state.closed) Hub.toast(error.message);
        });

      return () => {
        state.closed = true;
      };
    },
  };
})();
