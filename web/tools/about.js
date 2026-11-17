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

    <details class="card about-license" id="aboutLicense">
      <summary>Текст лицензии MIT</summary>
      <pre id="aboutLicenseText">Загружаю…</pre>
    </details>

    <p class="about-foot">© 2026 devrin · MIT License · сделано для себя и друзей</p>`;

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
          || "Файл LICENSE не найден рядом с программой.";
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

      $("#aboutOpen").addEventListener("click", openFolder);
      $("#aboutReadme").addEventListener("click", openReadme);
      $("#aboutIntro").addEventListener("click", replayIntro);

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
