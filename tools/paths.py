from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICON = ROOT / "web" / "hub-icon.ico"
DATA_DIR = ROOT / "data"
DESKTOP_EXE: Path | None = None
