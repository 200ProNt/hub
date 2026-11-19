/* Инструмент «Мониторинг ПК» */

(function () {
  const REFRESH_MS = 2000;
  const REFRESH_NOTE = "обновляется каждые 2 с";

  const LOCK_ICON =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5.5" y="10.5" width="13" height="9.5" rx="2.5"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5"/></svg>';

  const TEMPLATE = `
    <section class="mon-vitals">
      <article class="card mon-vital">
        <span class="mon-vital-label">Процессор</span>
        <span class="mon-vital-value" id="monCpu">—</span>
        <span class="mon-vital-sub" id="monCpuSub">считаю…</span>
        <span class="mon-bar" aria-hidden="true"><i id="monCpuBar" style="width:0%"></i></span>
        <svg class="mon-sparkline" id="monCpuSparkline" viewBox="0 0 120 26" preserveAspectRatio="none" aria-hidden="true"></svg>
      </article>
      <article class="card mon-vital">
        <span class="mon-vital-label">Память</span>
        <span class="mon-vital-value" id="monRam">—</span>
        <span class="mon-vital-sub" id="monRamSub">считаю…</span>
        <span class="mon-bar" aria-hidden="true"><i id="monRamBar" class="is-blue" style="width:0%"></i></span>
        <svg class="mon-sparkline" id="monRamSparkline" viewBox="0 0 120 26" preserveAspectRatio="none" aria-hidden="true"></svg>
      </article>
      <article class="card mon-vital">
        <span class="mon-vital-label">Диск</span>
        <span class="mon-vital-value" id="monDisk">—</span>
        <span class="mon-vital-sub" id="monDiskSub">считаю…</span>
        <span class="mon-bar" aria-hidden="true"><i id="monDiskBar" class="is-green" style="width:0%"></i></span>
      </article>
      <article class="card mon-vital">
        <span class="mon-vital-label">Компьютер работает</span>
        <span class="mon-vital-value mon-vital-uptime" id="monUptime">—</span>
        <span class="mon-vital-sub" id="monUptimeSub">без перезагрузки</span>
      </article>
    </section>

    <section class="card mon-card">
      <div class="mon-head">
        <div class="mon-head-main">
          <h2>Процессы <span class="mon-count" id="monCount"></span></h2>
          <span class="mon-live" id="monLive"><span class="mon-dot" aria-hidden="true"></span><span id="monLiveText">${REFRESH_NOTE}</span></span>
        </div>
        <div class="mon-controls">
          <label class="search mon-search">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>
            <input id="monQuery" type="search" placeholder="Найти процесс" autocomplete="off" aria-label="Найти процесс по имени или номеру">
          </label>
          <label class="select-field mon-sort">
            <span>сортировка</span>
            <select id="monSort" aria-label="Сортировка процессов">
              <option value="cpu" selected>по процессору</option>
              <option value="memory">по памяти</option>
              <option value="name">по имени</option>
            </select>
          </label>
          <button class="btn ghost small" id="monPause" type="button" aria-pressed="false">Пауза</button>
        </div>
      </div>
      <div class="mon-table">
        <div class="mon-thead" aria-hidden="true">
          <span>Процесс</span>
          <span class="mon-right">Процессор</span>
          <span class="mon-right">Память</span>
          <span></span>
        </div>
        <div class="mon-list" id="monList">
          <p class="mon-empty">Смотрю, что сейчас запущено…</p>
        </div>
      </div>
      <p class="mon-note" id="monNote">Закрыть можно только свои программы. Системные процессы защищены: без них Windows работает плохо.</p>
    </section>`;

  window.HubTools.monitor = {
    mount(root) {
      root.innerHTML = TEMPLATE;

      const $ = (selector) => root.querySelector(selector);
      const escape = Hub.escapeHtml;

      const state = {
        data: null,
        timer: null,
        inflight: false,
        paused: false,
        failing: false,
        closed: false,
        query: "",
        sort: "cpu",
      };

      /* --- форматирование --- */

      function fmtPercent(value) {
        return `${(Number(value) || 0).toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%`;
      }

      function fmtUptime(seconds) {
        const total = Math.max(0, Number(seconds) || 0);
        const days = Math.floor(total / 86400);
        const hours = Math.floor((total % 86400) / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        if (days) return `${days} ${Hub.plural(days, "день", "дня", "дней")} ${hours} ч`;
        if (hours) return `${hours} ч ${minutes} мин`;
        if (minutes) return `${minutes} мин`;
        return "меньше минуты";
      }

      function fmtStarted(timestamp) {
        const seconds = Number(timestamp) || 0;
        if (!seconds) return "";
        const date = new Date(seconds * 1000);
        if (Number.isNaN(date.getTime())) return "";
        const months = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
        const time = `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
        return `запущен ${date.getDate()} ${months[date.getMonth()]}, ${time}`;
      }

      function setBar(id, percent) {
        const bar = $(id);
        if (bar) bar.style.width = `${Math.min(100, Math.max(0, Number(percent) || 0))}%`;
      }

      function renderSparkline(svgId, points, colorClass) {
        const svg = $(svgId);
        if (!svg) return;
        if (!points || points.length < 2) {
          svg.innerHTML = "";
          return;
        }
        const width = 120;
        const height = 26;
        const step = width / (points.length - 1);
        const coords = points.map((val, idx) => {
          const x = (idx * step).toFixed(1);
          const y = (height - (Math.min(100, Math.max(0, Number(val) || 0)) / 100) * (height - 4) - 2).toFixed(1);
          return `${x},${y}`;
        });
        const linePath = coords.join(" ");
        const firstX = coords[0].split(",")[0];
        const lastX = coords[coords.length - 1].split(",")[0];
        const areaPath = `M ${firstX},${height} L ${coords.join(" L ")} L ${lastX},${height} Z`;
        svg.innerHTML = `
          <path class="sparkline-area is-${colorClass}" d="${areaPath}"/>
          <polyline class="sparkline-line is-${colorClass}" points="${linePath}"/>
        `;
      }

      /* --- витрина --- */

      function renderVitals() {
        const data = state.data;
        if (!data) return;
        const system = data.system;
        const memory = system.memory || {};
        const disk = system.disk || {};

        $("#monCpu").textContent = fmtPercent(system.cpu);
        $("#monCpuSub").textContent = `${system.cores} ${Hub.plural(system.cores, "ядро", "ядра", "ядер")} · ${data.processes.length} ${Hub.plural(data.processes.length, "процесс", "процесса", "процессов")}`;
        setBar("#monCpuBar", system.cpu);

        $("#monRam").textContent = fmtPercent(memory.percent);
        $("#monRamSub").textContent = memory.total
          ? `${Hub.fmtSize(memory.used)} из ${Hub.fmtSize(memory.total)}`
          : "не удалось узнать";
        setBar("#monRamBar", memory.percent);

        $("#monDisk").textContent = disk.total ? fmtPercent(100 - disk.percent) : "—";
        $("#monDiskSub").textContent = disk.total
          ? `свободно ${Hub.fmtSize(disk.free)} из ${Hub.fmtSize(disk.total)}`
          : "не удалось узнать";
        setBar("#monDiskBar", disk.total ? 100 - disk.percent : 0);

        $("#monUptime").textContent = fmtUptime(system.uptime);
        $("#monUptimeSub").textContent = "без перезагрузки";

        const history = data.history || [];
        if (history.length >= 2) {
          renderSparkline("#monCpuSparkline", history.map((h) => h.cpu), "cpu");
          renderSparkline("#monRamSparkline", history.map((h) => h.memory), "ram");
        }
      }

      /* --- список --- */

      function visibleProcesses() {
        const items = state.data?.processes || [];
        const query = state.query.trim().toLowerCase();
        const filtered = query
          ? items.filter((item) => String(item.name).toLowerCase().includes(query) || String(item.pid).includes(query))
          : items;
        const sorted = filtered.slice();
        if (state.sort === "memory") {
          sorted.sort((a, b) => (b.memory || 0) - (a.memory || 0) || (b.cpu || 0) - (a.cpu || 0) || String(a.name).localeCompare(String(b.name)));
        } else if (state.sort === "name") {
          sorted.sort((a, b) => String(a.name).localeCompare(String(b.name)) || (b.cpu || 0) - (a.cpu || 0));
        } else {
          sorted.sort((a, b) => (b.cpu || 0) - (a.cpu || 0) || (b.memory || 0) - (a.memory || 0) || String(a.name).localeCompare(String(b.name)));
        }
        return { items: sorted, total: items.length, shown: filtered.length };
      }

      function renderList() {
        if (!state.data) return;
        const { items, total, shown } = visibleProcesses();
        const list = $("#monList");
        $("#monCount").textContent = state.query ? `${shown} из ${total}` : String(total);

        if (!items.length) {
          list.innerHTML = state.query
            ? `<p class="mon-empty">Ничего не нашлось по «${escape(state.query)}».</p>`
            : '<p class="mon-empty">Windows не отдал список процессов.</p>';
          return;
        }

        list.innerHTML = items.map((item, index) => {
          const meta = [`PID ${item.pid}`, fmtStarted(item.started)].filter(Boolean).join(" · ");
          const tools = item.can_stop
            ? `<button class="btn ghost tiny mon-close" type="button" data-pid="${item.pid}" data-name="${escape(item.name)}">Закрыть</button>`
            : `<span class="mon-lock" title="${escape(item.why_not || "Этот процесс трогать нельзя")}" aria-label="${escape(item.why_not || "Процесс защищён")}">${LOCK_ICON}</span>`;
          return `
            <article class="mon-row${item.own ? " is-own" : ""}${index > 12 ? " is-still" : ""}" data-pid="${item.pid}">
              <div class="mon-proc">
                <span class="mon-name" title="${escape(item.name)}">${escape(item.name)}${item.own ? ' <span class="mon-you">это хаб</span>' : ""}</span>
                <span class="mon-meta">${escape(meta)}</span>
              </div>
              <span class="mon-right mon-value">${fmtPercent(item.cpu)}</span>
              <span class="mon-right mon-value">${Hub.fmtSize(item.memory)}</span>
              <div class="mon-action">${tools}</div>
            </article>`;
        }).join("");
      }

      function renderLive() {
        const live = $("#monLive");
        live.classList.toggle("is-paused", state.paused);
        $("#monLiveText").textContent = state.paused ? "на паузе" : REFRESH_NOTE;
        const button = $("#monPause");
        button.textContent = state.paused ? "Продолжить" : "Пауза";
        button.setAttribute("aria-pressed", String(state.paused));
      }

      function render() {
        renderVitals();
        renderList();
      }

      /* --- загрузка --- */

      function schedule() {
        clearTimeout(state.timer);
        if (state.closed || state.paused) return;
        state.timer = setTimeout(load, REFRESH_MS);
      }

      async function load() {
        if (state.closed || state.paused || state.inflight) return;
        state.inflight = true;
        try {
          const data = await Hub.api("/api/monitor/snapshot");
          if (state.closed) return;
          state.data = data;
          state.failing = false;
          render();
        } catch (error) {
          if (state.closed) return;
          if (!state.failing) {
            state.failing = true;
            Hub.toast(error.message);
          }
          $("#monLiveText").textContent = "нет связи";
        } finally {
          state.inflight = false;
          schedule();
        }
      }

      async function terminate(pid, name) {
        if (state.closed) return;
        const confirmed = await Hub.confirm({
          title: "Закрыть процесс?",
          text: `«${name}» (PID ${pid}) закроется. Несохранённые данные в нём пропадут, и это нельзя отменить.`,
          confirmText: "Закрыть процесс",
          danger: true,
        });
        if (!confirmed || state.closed) return;
        clearTimeout(state.timer);
        try {
          await Hub.api("/api/monitor/terminate", { pid });
          if (state.closed) return;
          Hub.toast(`«${name}» закрыт`);
        } catch (error) {
          if (state.closed) return;
          Hub.toast(error.message);
        }
        load();
      }

      /* --- события --- */

      $("#monQuery").addEventListener("input", (event) => {
        state.query = event.target.value;
        renderList();
      });

      $("#monSort").addEventListener("change", (event) => {
        state.sort = event.target.value;
        renderList();
      });

      $("#monPause").addEventListener("click", () => {
        state.paused = !state.paused;
        renderLive();
        if (state.paused) {
          clearTimeout(state.timer);
        } else {
          load();
        }
      });

      $("#monList").addEventListener("click", (event) => {
        const button = event.target.closest("[data-pid]");
        if (!button || !button.classList.contains("mon-close")) return;
        terminate(Number(button.dataset.pid), button.dataset.name || "процесс");
      });

      const onVisibility = () => {
        if (document.hidden) {
          clearTimeout(state.timer);
        } else if (!state.paused && !state.closed) {
          load();
        }
      };
      document.addEventListener("visibilitychange", onVisibility);

      renderLive();
      load();

      return () => {
        state.closed = true;
        clearTimeout(state.timer);
        document.removeEventListener("visibilitychange", onVisibility);
      };
    },
  };
})();
