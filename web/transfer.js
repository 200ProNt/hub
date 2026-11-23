const button = document.getElementById("transferBtn");
const status = document.getElementById("transferStatus");

function readSettings() {
  const values = {};
  for (const name of ["theme", "motion", "accent", "glass", "sound", "onboarded"]) {
    const key = `hub-${name}`;
    const value = localStorage.getItem(key);
    if (value !== null) values[key] = value;
  }
  if (!Object.keys(values).length) throw new Error("Здесь нет прежних настроек. Проверь профиль браузера и порт прежнего Hub.");
  return values;
}

button.addEventListener("click", async () => {
  button.disabled = true;
  try {
    const values = readSettings();
    const response = await fetch("/api/desktop/preferences", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    if (!response.ok) throw new Error("Сохрани настройки в файл и выбери его в настольном Hub.");
    status.textContent = "Настройки перенесены. Закрой Hub через значок в трее и снова открой его с ярлыка.";
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

document.getElementById("transferExport").addEventListener("click", () => {
  try {
    const href = URL.createObjectURL(new Blob([JSON.stringify(readSettings())], { type: "application/json" }));
    const download = document.createElement("a");
    download.href = href;
    download.download = "hub-settings.json";
    download.click();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
  } catch (error) {
    status.textContent = error.message;
  }
});
