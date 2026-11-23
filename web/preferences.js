const HubPreferences = {
  get(key) {
    if (window.hubDesktopState) return window.hubDesktopState[key] ?? null;
    return localStorage.getItem(key);
  },

  set(key, value) {
    const state = window.hubDesktopState;
    if (!state) {
      localStorage.setItem(key, value);
      return;
    }
    if ((state[key] ?? "") === value) return;
    state[key] = value;
    fetch("/api/desktop/preferences", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [key]: value }),
      keepalive: true,
    }).then(response => {
      if (!response.ok) throw new Error();
    }).catch(() => window.Hub?.toast("Не удалось сохранить настройку"));
  },
};
if (window.hubDesktopState) document.documentElement.dataset.desktop = "true";
