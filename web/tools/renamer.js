/* Hub — Пакетное переименование файлов (Batch Renamer) */

(function () {
  const TEMPLATE = `
    <div class="renamer-layout">
      <!-- 1. Панель выбора папки и фильтра -->
      <section class="card renamer-bar">
        <div class="path-field renamer-path-field">
          <svg class="path-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2c.6 0 1.2.2 1.6.7l1 1.05c.2.2.5.35.8.35H18.5A2.5 2.5 0 0 1 21 9.6v7.9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"/>
          </svg>
          <input id="renamerFolder" type="text" spellcheck="false" autocomplete="off" placeholder="Введи путь к папке с файлами…" aria-label="Путь к папке">
          <button class="btn ghost small" id="renamerPickBtn" type="button">Выбрать папку</button>
        </div>

        <div class="renamer-filter-row">
          <label class="search renamer-filter-input">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>
            <input id="renamerFilter" type="text" placeholder="Фильтр: *.jpg, *.png или *.*" value="*">
          </label>
          <button class="btn primary" id="renamerScanBtn" type="button">Найти файлы</button>
          <button class="btn ghost" id="renamerUndoBtn" type="button">Отменить последнее (Undo)</button>
        </div>
      </section>

      <!-- 2. Панель правил переименования -->
      <section class="card renamer-rules-card" id="renamerRulesCard">
        <div class="renamer-tabs" id="renamerTabs">
          <button class="renamer-tab is-active" data-mode="replace" type="button">Замена текста</button>
          <button class="renamer-tab" data-mode="number" type="button">Нумерация</button>
          <button class="renamer-tab" data-mode="affix" type="button">Префикс / Суффикс</button>
          <button class="renamer-tab" data-mode="case" type="button">Регистр букв</button>
          <button class="renamer-tab" data-mode="translit" type="button">Транслитерация</button>
          <button class="renamer-tab" data-mode="date" type="button">Добавить дату</button>
        </div>

        <div class="renamer-rule-body" id="renamerRuleBody">
          <!-- Динамические поля правила -->
        </div>
      </section>

      <!-- 3. Таблица предпросмотра -->
      <section class="card renamer-results-card">
        <div class="renamer-results-head">
          <div>
            <h2 class="section-title">Предпросмотр переименования</h2>
            <div class="renamer-stats" id="renamerStats">Файлы ещё не выбраны</div>
          </div>
          <button class="btn primary large" id="renamerApplyBtn" type="button" disabled>Переименовать файлы</button>
        </div>

        <div class="renamer-table-wrapper">
          <div class="renamer-table" id="renamerTable">
            <div class="renamer-empty">Выбери папку и нажми «Найти файлы», чтобы увидеть список.</div>
          </div>
        </div>
      </section>
    </div>
  `;

  function mount(container) {
    container.innerHTML = TEMPLATE;
    const $ = (sel) => container.querySelector(sel);

    let currentFiles = [];
    let currentPreview = [];
    let activeMode = "replace";

    // Установка папки по умолчанию
    if (Hub.defaultFolder) {
      const folderInput = $("#renamerFolder");
      if (folderInput) folderInput.value = Hub.defaultFolder;
    } else {
      Hub.api("/api/info").then((info) => {
        if (info && info.default_folder) {
          const folderInput = $("#renamerFolder");
          if (folderInput && !folderInput.value) folderInput.value = info.default_folder;
        }
      }).catch(() => {});
    }

    function renderRuleInputs() {
      const body = $("#renamerRuleBody");
      if (activeMode === "replace") {
        body.innerHTML = `
          <div class="rule-inputs-row">
            <div class="rule-field">
              <label>Что найти:</label>
              <input type="text" id="ruleFind" placeholder="Текст для поиска">
            </div>
            <div class="rule-field">
              <label>На что заменить:</label>
              <input type="text" id="ruleReplace" placeholder="Новый текст (или оставь пустым для удаления)">
            </div>
            <div class="rule-checks">
              <label class="check-inline"><input type="checkbox" id="ruleRegex"> Регулярные выражения (Regex)</label>
              <label class="check-inline"><input type="checkbox" id="ruleCaseSense"> Учитывать регистр</label>
            </div>
          </div>
        `;
      } else if (activeMode === "number") {
        body.innerHTML = `
          <div class="rule-inputs-row">
            <div class="rule-field">
              <label>Префикс:</label>
              <input type="text" id="ruleNumPrefix" placeholder="Например: photo_">
            </div>
            <div class="rule-field" style="max-width: 120px;">
              <label>Начать с:</label>
              <input type="number" id="ruleNumStart" value="1" min="0">
            </div>
            <div class="rule-field" style="max-width: 120px;">
              <label>Цифр (01, 001):</label>
              <input type="number" id="ruleNumDigits" value="2" min="1" max="8">
            </div>
            <div class="rule-field" style="max-width: 120px;">
              <label>Шаг:</label>
              <input type="number" id="ruleNumStep" value="1" min="1">
            </div>
            <div class="rule-checks">
              <label class="check-inline"><input type="checkbox" id="ruleNumKeep"> Сохранять исходное имя</label>
            </div>
          </div>
        `;
      } else if (activeMode === "affix") {
        body.innerHTML = `
          <div class="rule-inputs-row">
            <div class="rule-field">
              <label>Добавить в начало (префикс):</label>
              <input type="text" id="ruleAffixPrefix" placeholder="Например: 2026_">
            </div>
            <div class="rule-field">
              <label>Добавить в конец (суффикс):</label>
              <input type="text" id="ruleAffixSuffix" placeholder="Например: _готово">
            </div>
          </div>
        `;
      } else if (activeMode === "case") {
        body.innerHTML = `
          <div class="rule-inputs-row">
            <div class="rule-field">
              <label>Регистр имени файла:</label>
              <select id="ruleCaseTarget" class="renamer-select">
                <option value="lower">все строчные (lowercase)</option>
                <option value="upper">ВСЕ ЗАГЛАВНЫЕ (UPPERCASE)</option>
                <option value="sentence">Как в предложении (Sentence case)</option>
                <option value="title">Каждое Слово С Заглавной (Title Case)</option>
              </select>
            </div>
          </div>
        `;
      } else if (activeMode === "translit") {
        body.innerHTML = `
          <div class="rule-note">Переводит русские буквы в латиницу (ГОСТ 7.79): «документ.pdf» → «dokument.pdf».</div>
        `;
      } else if (activeMode === "date") {
        body.innerHTML = `
          <div class="rule-inputs-row">
            <div class="rule-field">
              <label>Формат даты:</label>
              <select id="ruleDateFormat" class="renamer-select">
                <option value="YYYY-MM-DD">ГГГГ-ММ-ДД (2026-11-19)</option>
                <option value="YYYY-MM-DD_HH-mm">ГГГГ-ММ-ДД_ЧЧ-ММ (2026-11-19_12-30)</option>
              </select>
            </div>
            <div class="rule-field">
              <label>Положение даты:</label>
              <select id="ruleDatePos" class="renamer-select">
                <option value="prefix">В начале имени</option>
                <option value="suffix">В конце имени</option>
              </select>
            </div>
          </div>
        `;
      }

      // Привязка слушателей на все инпуты внутри правила для авто-обновления предпросмотра
      body.querySelectorAll("input, select").forEach((elem) => {
        elem.addEventListener("input", scheduleUpdatePreview);
        elem.addEventListener("change", scheduleUpdatePreview);
      });
    }

    function getRuleConfig() {
      const config = { mode: activeMode };
      if (activeMode === "replace") {
        config.find = $("#ruleFind")?.value || "";
        config.replace = $("#ruleReplace")?.value || "";
        config.use_regex = Boolean($("#ruleRegex")?.checked);
        config.case_sensitive = Boolean($("#ruleCaseSense")?.checked);
      } else if (activeMode === "number") {
        config.prefix = $("#ruleNumPrefix")?.value || "";
        config.start = parseInt($("#ruleNumStart")?.value || "1", 10);
        config.digits = parseInt($("#ruleNumDigits")?.value || "2", 10);
        config.step = parseInt($("#ruleNumStep")?.value || "1", 10);
        config.keep_name = Boolean($("#ruleNumKeep")?.checked);
      } else if (activeMode === "affix") {
        config.prefix = $("#ruleAffixPrefix")?.value || "";
        config.suffix = $("#ruleAffixSuffix")?.value || "";
      } else if (activeMode === "case") {
        config.target = $("#ruleCaseTarget")?.value || "lower";
      } else if (activeMode === "date") {
        config.format = $("#ruleDateFormat")?.value || "YYYY-MM-DD";
        config.position = $("#ruleDatePos")?.value || "prefix";
      }
      return config;
    }

    let previewTimer = null;
    function scheduleUpdatePreview() {
      clearTimeout(previewTimer);
      previewTimer = setTimeout(updatePreview, 120);
    }

    async function updatePreview() {
      if (!currentFiles.length) return;
      const folder = $("#renamerFolder").value.trim();
      const rule = getRuleConfig();

      try {
        const res = await Hub.api("/api/renamer/preview", {
          folder,
          files: currentFiles,
          rule,
        });

        currentPreview = res.preview || [];
        renderTable(res);
      } catch (e) {
        Hub.toast("Ошибка предпросмотра: " + e.message);
      }
    }

    function renderTable(res) {
      const stats = $("#renamerStats");
      stats.innerHTML = `Всего: <b>${res.total}</b> · Готово к переименованию: <b style="color:var(--accent);">${res.ready_count}</b> · Без изменений: <b>${res.unchanged_count}</b>` +
        (res.conflict_count ? ` · <b style="color:var(--danger);">Конфликтов: ${res.conflict_count}</b>` : "");

      $("#renamerApplyBtn").disabled = res.ready_count === 0 || res.conflict_count > 0;

      const table = $("#renamerTable");
      if (!currentPreview.length) {
        table.innerHTML = '<div class="renamer-empty">Нет файлов для отображения.</div>';
        return;
      }

      table.innerHTML = `
        <div class="ren-head-row">
          <span style="flex:1;">Исходное имя</span>
          <span style="width:30px; text-align:center;">→</span>
          <span style="flex:1;">Новое имя</span>
          <span style="width:110px; text-align:right;">Статус</span>
        </div>
        ${currentPreview.map((item) => {
          let badge = '<span class="ren-badge ok">Готов</span>';
          if (item.status === "unchanged") badge = '<span class="ren-badge unchanged">Без изм.</span>';
          if (item.status === "conflict") badge = `<span class="ren-badge conflict" title="${Hub.escapeHtml(item.error || '')}">Конфликт</span>`;
          if (item.status === "error") badge = `<span class="ren-badge conflict" title="${Hub.escapeHtml(item.error || '')}">Ошибка</span>`;

          const isDiff = item.old_name !== item.new_name;
          return `
            <div class="ren-row ${item.status}">
              <span class="ren-old-name" title="${Hub.escapeHtml(item.old_name)}">${Hub.escapeHtml(item.old_name)}</span>
              <span class="ren-arrow">→</span>
              <span class="ren-new-name ${isDiff ? 'is-changed' : ''}" title="${Hub.escapeHtml(item.new_name)}">${Hub.escapeHtml(item.new_name)}</span>
              <div class="ren-status">${badge}</div>
            </div>
          `;
        }).join("")}
      `;
    }

    async function scanFiles() {
      const folder = $("#renamerFolder").value.trim();
      const filter = $("#renamerFilter").value.trim() || "*";
      if (!folder) {
        Hub.toast("Укажи папку для переименования");
        return;
      }

      $("#renamerScanBtn").disabled = true;
      try {
        const res = await Hub.api("/api/renamer/scan", { folder, filter });
        currentFiles = res.files || [];
        if (!currentFiles.length) {
          Hub.toast("В этой папке нет подходящих файлов");
          $("#renamerTable").innerHTML = '<div class="renamer-empty">Файлов по данному фильтру не найдено.</div>';
          $("#renamerStats").textContent = "Найдено 0 файлов";
          $("#renamerApplyBtn").disabled = true;
          return;
        }

        Hub.playSound("action");
        await updatePreview();
      } catch (e) {
        Hub.toast(e.message);
      } finally {
        $("#renamerScanBtn").disabled = false;
      }
    }

    // Слушатели событий
    $("#renamerScanBtn").addEventListener("click", scanFiles);
    $("#renamerFilter").addEventListener("keydown", (e) => {
      if (e.key === "Enter") scanFiles();
    });

    $("#renamerPickBtn").addEventListener("click", async () => {
      try {
        const res = await Hub.api("/api/renamer/pick-folder", { initial: $("#renamerFolder").value.trim() });
        if (res && res.folder) {
          $("#renamerFolder").value = res.folder;
          scanFiles();
        }
      } catch (e) {
        Hub.toast(e.message);
      }
    });

    $("#renamerTabs").addEventListener("click", (e) => {
      const tab = e.target.closest(".renamer-tab");
      if (!tab) return;
      container.querySelectorAll(".renamer-tab").forEach((t) => t.classList.remove("is-active"));
      tab.classList.add("is-active");
      activeMode = tab.dataset.mode;
      renderRuleInputs();
      scheduleUpdatePreview();
    });

    $("#renamerApplyBtn").addEventListener("click", async () => {
      const folder = $("#renamerFolder").value.trim();
      if (!currentPreview.length) return;

      $("#renamerApplyBtn").disabled = true;
      try {
        const res = await Hub.api("/api/renamer/apply", {
          folder,
          renames: currentPreview,
        });

        if (res.errors && res.errors.length) {
          Hub.toast("Переименовано частично: " + res.errors.join("; "));
        } else {
          Hub.playSound("action");
          Hub.toast(`Успешно переименовано файлов: ${res.renamed_count}`);
        }
        await scanFiles();
      } catch (e) {
        Hub.toast(e.message);
      } finally {
        $("#renamerApplyBtn").disabled = false;
      }
    });

    $("#renamerUndoBtn").addEventListener("click", async () => {
      try {
        const res = await Hub.api("/api/renamer/undo", {});
        Hub.playSound("trash");
        Hub.toast(`Отменено переименование для ${res.restored_count} файлов`);
        await scanFiles();
      } catch (e) {
        Hub.toast("Нечего отменять: " + e.message);
      }
    });

    renderRuleInputs();

    return () => {
      clearTimeout(previewTimer);
    };
  }

  window.HubTools = window.HubTools || {};
  window.HubTools.renamer = { mount };
})();
