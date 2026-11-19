/* Hub — Хэши и пароли (Checksum & Crypto) */

(function () {
  const TEMPLATE = `
    <div class="crypto-layout">
      <!-- Навигация по вкладкам инструмента -->
      <div class="crypto-nav-tabs" id="cryptoNavTabs">
        <button class="crypto-tab-btn is-active" data-tab="file" type="button">Контрольные суммы файла</button>
        <button class="crypto-tab-btn" data-tab="text" type="button">Хэширование текста</button>
        <button class="crypto-tab-btn" data-tab="password" type="button">Генератор паролей</button>
      </div>

      <!-- Вкладка 1: Хэши файла -->
      <section class="card crypto-panel is-active" id="panelFile">
        <div class="path-field" style="margin-bottom: 14px;">
          <svg class="path-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          <input id="cryptoFilePath" type="text" placeholder="Укажи путь к файлу на компьютере…" aria-label="Путь к файлу">
          <button class="btn ghost small" id="cryptoPickFileBtn" type="button">Выбрать файл</button>
          <button class="btn primary small" id="cryptoCalcBtn" type="button">Рассчитать хэши</button>
        </div>

        <div class="crypto-dropzone" id="cryptoDropZone">
          <div class="dropzone-icon">📥</div>
          <div class="dropzone-text">Перетащи файл сюда или выбери его кнопкой выше</div>
          <div class="dropzone-hint">Поддерживаются файлы любого размера — чтение выполняется потоково</div>
        </div>

        <div class="crypto-file-results hidden" id="cryptoFileResults">
          <div class="crypto-file-meta" id="cryptoFileMeta"></div>

          <!-- Результаты вычисления -->
          <div class="crypto-hash-grid">
            <div class="hash-card">
              <div class="hash-card-head">
                <span class="hash-alg">SHA-256</span>
                <button class="btn ghost tiny" data-copy="sha256">Скопировать</button>
              </div>
              <code class="hash-val" id="hashSha256"></code>
            </div>

            <div class="hash-card">
              <div class="hash-card-head">
                <span class="hash-alg">MD5</span>
                <button class="btn ghost tiny" data-copy="md5">Скопировать</button>
              </div>
              <code class="hash-val" id="hashMd5"></code>
            </div>

            <div class="hash-card">
              <div class="hash-card-head">
                <span class="hash-alg">SHA-1</span>
                <button class="btn ghost tiny" data-copy="sha1">Скопировать</button>
              </div>
              <code class="hash-val" id="hashSha1"></code>
            </div>
          </div>

          <!-- Сверка с эталонным хэшем -->
          <div class="hash-verify-box">
            <h3 class="verify-title">Проверка подлинности (сверка с эталоном)</h3>
            <div class="search" style="margin-bottom: 10px;">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>
              <input type="text" id="verifyInput" placeholder="Вставь ожидаемый хэш с сайта разработчика…">
            </div>
            <div class="verify-verdict" id="verifyVerdict"></div>
          </div>
        </div>
      </section>

      <!-- Вкладка 2: Хэши текста -->
      <section class="card crypto-panel" id="panelText">
        <h2 class="section-title">Хэширование текста и кодирование Base64</h2>
        <p class="section-hint">Моментальный расчёт контрольных сумм введённого текста</p>

        <textarea id="textHashInput" placeholder="Введи или вставь любой текст для хэширования…"></textarea>

        <div class="crypto-hash-grid" id="textHashResults" style="margin-top: 14px;">
          <div class="hash-card">
            <div class="hash-card-head">
              <span class="hash-alg">SHA-256</span>
              <button class="btn ghost tiny" data-copy-text="sha256">Скопировать</button>
            </div>
            <code class="hash-val" id="textSha256">—</code>
          </div>

          <div class="hash-card">
            <div class="hash-card-head">
              <span class="hash-alg">MD5</span>
              <button class="btn ghost tiny" data-copy-text="md5">Скопировать</button>
            </div>
            <code class="hash-val" id="textMd5">—</code>
          </div>

          <div class="hash-card">
            <div class="hash-card-head">
              <span class="hash-alg">Base64 Encode</span>
              <button class="btn ghost tiny" data-copy-text="b64enc">Скопировать</button>
            </div>
            <code class="hash-val" id="textB64Enc">—</code>
          </div>
        </div>
      </section>

      <!-- Вкладка 3: Генератор паролей -->
      <section class="card crypto-panel" id="panelPassword">
        <div class="pwd-display-card">
          <div class="pwd-val-wrapper">
            <span class="pwd-val" id="pwdResult">••••••••••••••••</span>
          </div>
          <div class="pwd-meter">
            <div class="pwd-meter-bar" id="pwdMeterBar"></div>
          </div>
          <div class="pwd-actions">
            <span class="pwd-entropy" id="pwdEntropyInfo">Стойкость: 0 бит</span>
            <div style="display:flex; gap:8px;">
              <button class="btn ghost small" id="pwdCopyBtn" type="button">Скопировать</button>
              <button class="btn primary small" id="pwdGenBtn" type="button">Сгенерировать новый</button>
            </div>
          </div>
        </div>

        <div class="pwd-settings-grid">
          <div class="pwd-setting-item">
            <label class="pwd-label">Длина пароля: <b id="pwdLenVal">16</b></label>
            <input type="range" id="pwdLenSlider" min="8" max="64" value="16" class="img-slider">
          </div>

          <div class="pwd-setting-item">
            <label class="pwd-label">Режим генерации:</label>
            <select id="pwdModeSelect" class="renamer-select">
              <option value="random">Случайные символы</option>
              <option value="passphrase">Фраза-пароль (Passphrase из слов)</option>
            </select>
          </div>

          <div class="pwd-checks" id="pwdRandomChecks">
            <label class="check-inline"><input type="checkbox" id="pwdUpper" checked> Заглавные буквы (A-Z)</label>
            <label class="check-inline"><input type="checkbox" id="pwdLower" checked> Строчные буквы (a-z)</label>
            <label class="check-inline"><input type="checkbox" id="pwdDigits" checked> Цифры (0-9)</label>
            <label class="check-inline"><input type="checkbox" id="pwdSymbols" checked> Спецсимволы (!@#$%^&*)</label>
            <label class="check-inline"><input type="checkbox" id="pwdAmbiguous" checked> Исключать похожие (1, l, I, 0, O)</label>
          </div>
        </div>
      </section>
    </div>
  `;

  function mount(container) {
    container.innerHTML = TEMPLATE;
    const $ = (sel) => container.querySelector(sel);

    let currentFileHashes = null;
    let textHashes = null;

    // Переключение вкладок
    $("#cryptoNavTabs").addEventListener("click", (e) => {
      const btn = e.target.closest(".crypto-tab-btn");
      if (!btn) return;
      container.querySelectorAll(".crypto-tab-btn").forEach((b) => b.classList.remove("is-active"));
      container.querySelectorAll(".crypto-panel").forEach((p) => p.classList.remove("is-active"));
      btn.classList.add("is-active");
      const tabId = btn.dataset.tab;
      if (tabId === "file") $("#panelFile").classList.add("is-active");
      if (tabId === "text") $("#panelText").classList.add("is-active");
      if (tabId === "password") $("#panelPassword").classList.add("is-active");
    });

    // 1. Хэши файла
    async function calcFileHashes(filePath) {
      if (!filePath) return;
      try {
        $("#cryptoCalcBtn").disabled = true;
        Hub.playSound("action");
        const res = await Hub.api("/api/checksum/file", { path: filePath });
        currentFileHashes = res.hashes || {};

        $("#cryptoFileMeta").innerHTML = `<b>${Hub.escapeHtml(res.name)}</b> · Размер: ${Hub.fmtSize(res.size)} · Изменён: ${Hub.timeAgo(res.mtime)}`;
        $("#hashSha256").textContent = currentFileHashes.sha256 || "—";
        $("#hashMd5").textContent = currentFileHashes.md5 || "—";
        $("#hashSha1").textContent = currentFileHashes.sha1 || "—";
        $("#cryptoFileResults").classList.remove("hidden");
        checkVerify();
      } catch (e) {
        Hub.toast(e.message);
      } finally {
        $("#cryptoCalcBtn").disabled = false;
      }
    }

    $("#cryptoCalcBtn").addEventListener("click", () => {
      calcFileHashes($("#cryptoFilePath").value.trim());
    });

    $("#cryptoPickFileBtn").addEventListener("click", async () => {
      try {
        const res = await Hub.api("/api/checksum/pick-file", { initial: $("#cryptoFilePath").value.trim() });
        if (res && res.file) {
          $("#cryptoFilePath").value = res.file;
          calcFileHashes(res.file);
        }
      } catch (e) {
        Hub.toast(e.message);
      }
    });

    // Drag and Drop
    const dropZone = $("#cryptoDropZone");
    ["dragenter", "dragover"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropZone.classList.add("drag-over");
      });
    });
    ["dragleave", "drop"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropZone.classList.remove("drag-over");
      });
    });

    // Копирование хэшей файла
    container.addEventListener("click", (e) => {
      const copyBtn = e.target.closest("[data-copy]");
      if (copyBtn && currentFileHashes) {
        const alg = copyBtn.dataset.copy;
        const val = currentFileHashes[alg];
        if (val) {
          navigator.clipboard.writeText(val);
          Hub.playSound("copy");
          Hub.toast(`${alg.toUpperCase()} скопирован`);
        }
      }
    });

    // Сверка с эталоном
    function checkVerify() {
      const expected = $("#verifyInput").value.trim().toLowerCase();
      const verdict = $("#verifyVerdict");
      if (!expected || !currentFileHashes) {
        verdict.innerHTML = "";
        return;
      }

      const matchAlg = Object.keys(currentFileHashes).find(
        (alg) => currentFileHashes[alg].toLowerCase() === expected
      );

      if (matchAlg) {
        verdict.innerHTML = `<span class="verdict-tag match">✅ Хэш совпадает (${matchAlg.toUpperCase()}) — файл подлинный и не повреждён</span>`;
      } else {
        verdict.innerHTML = `<span class="verdict-tag mismatch">❌ Хэш не совпадает ни с одним алгоритмом — возможно, файл повреждён</span>`;
      }
    }
    $("#verifyInput").addEventListener("input", checkVerify);

    // 2. Хэши текста
    let textTimer = null;
    $("#textHashInput").addEventListener("input", () => {
      clearTimeout(textTimer);
      textTimer = setTimeout(async () => {
        const text = $("#textHashInput").value;
        if (!text) {
          $("#textSha256").textContent = "—";
          $("#textMd5").textContent = "—";
          $("#textB64Enc").textContent = "—";
          return;
        }
        try {
          const res = await Hub.api("/api/checksum/text", { text });
          textHashes = res;
          $("#textSha256").textContent = res.sha256;
          $("#textMd5").textContent = res.md5;
          $("#textB64Enc").textContent = res.base64_encode;
        } catch {}
      }, 100);
    });

    // Копирование текстовых хэшей
    container.addEventListener("click", (e) => {
      const copyBtn = e.target.closest("[data-copy-text]");
      if (copyBtn && textHashes) {
        const key = copyBtn.dataset.copyText;
        let val = "";
        if (key === "sha256") val = textHashes.sha256;
        if (key === "md5") val = textHashes.md5;
        if (key === "b64enc") val = textHashes.base64_encode;
        if (val) {
          navigator.clipboard.writeText(val);
          Hub.playSound("copy");
          Hub.toast("Скопировано");
        }
      }
    });

    // 3. Генератор паролей
    async function generatePwd() {
      const length = parseInt($("#pwdLenSlider").value, 10);
      const mode = $("#pwdModeSelect").value;
      const uppercase = $("#pwdUpper").checked;
      const lowercase = $("#pwdLower").checked;
      const digits = $("#pwdDigits").checked;
      const symbols = $("#pwdSymbols").checked;
      const avoid_ambiguous = $("#pwdAmbiguous").checked;

      try {
        const res = await Hub.api("/api/checksum/password", {
          length,
          mode,
          uppercase,
          lowercase,
          digits,
          symbols,
          avoid_ambiguous,
          words_count: Math.round(length / 4),
        });

        $("#pwdResult").textContent = res.password;
        $("#pwdEntropyInfo").textContent = `Стойкость: ~${res.entropy} бит (${res.strength === 'very_strong' ? 'Превосходная' : res.strength === 'strong' ? 'Надёжная' : 'Средняя'})`;

        const bar = $("#pwdMeterBar");
        bar.className = "pwd-meter-bar " + res.strength;
        const pct = Math.min(100, Math.round((res.entropy / 80) * 100));
        bar.style.width = pct + "%";
      } catch (e) {
        Hub.toast(e.message);
      }
    }

    $("#pwdLenSlider").addEventListener("input", (e) => {
      $("#pwdLenVal").textContent = e.target.value;
      generatePwd();
    });

    $("#pwdModeSelect").addEventListener("change", (e) => {
      const isPassphrase = e.target.value === "passphrase";
      $("#pwdRandomChecks").style.display = isPassphrase ? "none" : "flex";
      generatePwd();
    });

    ["#pwdUpper", "#pwdLower", "#pwdDigits", "#pwdSymbols", "#pwdAmbiguous"].forEach((sel) => {
      $(sel)?.addEventListener("change", generatePwd);
    });

    $("#pwdGenBtn").addEventListener("click", () => {
      Hub.playSound("action");
      generatePwd();
    });

    $("#pwdCopyBtn").addEventListener("click", () => {
      const pwd = $("#pwdResult").textContent;
      if (pwd && !pwd.startsWith("•")) {
        navigator.clipboard.writeText(pwd);
        Hub.playSound("copy");
        Hub.toast("Пароль скопирован в буфер");
      }
    });

    generatePwd();

    return () => {
      clearTimeout(textTimer);
    };
  }

  window.HubTools = window.HubTools || {};
  window.HubTools.checksum = { mount };
})();
