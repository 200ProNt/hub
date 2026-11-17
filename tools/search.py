"""Общий поиск по хабу: инструменты, заметки и история буфера одним запросом."""

from __future__ import annotations

LIMIT = 6
AROUND = 44


def _flat(text: str) -> str:
    return " ".join(str(text).split())


def snippet(text: str, needle: str, around: int = AROUND) -> str:
    """Кусок текста вокруг первого совпадения, чтобы было видно, почему нашлось."""
    clean = _flat(text)
    if not clean:
        return ""
    at = clean.lower().find(needle) if needle else -1
    if at < 0:
        cut = clean[: around * 2]
        return cut + ("…" if len(clean) > len(cut) else "")
    start = max(0, at - around)
    end = min(len(clean), at + len(needle) + around)
    head = "…" if start else ""
    tail = "…" if end < len(clean) else ""
    return f"{head}{clean[start:end]}{tail}"


def run(
    query: str,
    tools: list[dict] | None = None,
    notes_items: list[dict] | None = None,
    clipboard_items: list[dict] | None = None,
    limit: int = LIMIT,
) -> dict:
    tools = tools or []
    notes_items = notes_items or []
    clipboard_items = clipboard_items or []
    needle = _flat(query).lower()
    if not needle:
        return {"query": "", "tools": [], "notes": [], "clipboard": [], "total": 0}

    tool_hits = [
        {"id": tool["id"], "name": tool["name"], "hint": tool.get("hint", ""), "icon": tool.get("icon", "")}
        for tool in tools
        if needle in f"{tool['name']} {tool.get('hint', '')}".lower()
    ][:limit]

    note_hits = []
    for note in notes_items:
        title = str(note.get("title") or "")
        text = str(note.get("text") or "")
        if needle in title.lower() or needle in text.lower():
            note_hits.append(
                {
                    "id": note.get("id", ""),
                    "title": title or text.splitlines()[0][:60] or "Без заголовка",
                    "snippet": snippet(text or title, needle),
                    "updated": note.get("updated", 0),
                }
            )
        if len(note_hits) >= limit:
            break

    clip_hits = []
    for item in clipboard_items:
        text = str(item.get("text") or item.get("preview") or "")
        if needle in text.lower():
            clip_hits.append(
                {
                    "id": item.get("id", ""),
                    "snippet": snippet(text, needle),
                    "time": item.get("time", 0),
                    "pinned": bool(item.get("pinned")),
                }
            )
        if len(clip_hits) >= limit:
            break

    return {
        "query": needle,
        "tools": tool_hits,
        "notes": note_hits,
        "clipboard": clip_hits,
        "total": len(tool_hits) + len(note_hits) + len(clip_hits),
    }
