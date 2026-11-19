"""Инструмент «Хэши и пароли»: вычисление контрольных сумм файлов и генератор надёжных паролей."""

from __future__ import annotations

import base64
import hashlib
import math
import os
import secrets
import string
from pathlib import Path

CHUNK_SIZE = 64 * 1024

AMBIGUOUS_CHARS = set("il1Lo0O")
SYMBOLS_SAFE = "!@#$%^&*()-_=+[]{}:;,.?"

WORDLIST = [
    "amber", "anchor", "angel", "apple", "arrow", "badge", "baker", "beacon",
    "breeze", "bridge", "cabin", "canyon", "cedar", "charm", "cherry", "cloud",
    "clover", "comet", "coral", "crane", "crest", "crown", "crystal", "dawn",
    "delta", "diver", "dolphin", "dragon", "drift", "eagle", "ember", "falcon",
    "feather", "field", "flame", "flash", "flight", "forest", "frost", "galaxy",
    "garden", "glacier", "globe", "grace", "grove", "harbor", "haven", "hawk",
    "hazel", "honey", "horizon", "island", "jasper", "jewel", "jungle", "lagoon",
    "lake", "lark", "laurel", "leaf", "legend", "lemon", "lily", "lion",
    "lotus", "meadow", "meteor", "mist", "moon", "moss", "mountain", "nebula",
    "nexus", "oasis", "ocean", "olive", "orbit", "otter", "owl", "palace",
    "panda", "panther", "parrot", "peak", "pebble", "pepper", "petal", "phoenix",
    "pioneer", "planet", "polar", "prairie", "prism", "quarry", "quartz", "rabbit",
    "radar", "rain", "ranger", "rapids", "raven", "reef", "rhino", "ridge",
    "river", "robin", "rocket", "rover", "ruby", "saddle", "sage", "sailor",
    "salmon", "sand", "sapphire", "scout", "shadow", "shield", "sierra", "silver",
    "siren", "sky", "solar", "spark", "sparrow", "sphere", "spiral", "spring",
    "star", "stone", "storm", "stream", "summit", "sun", "swan", "swift",
    "temple", "thistle", "tiger", "timber", "topaz", "torch", "tower", "trail",
    "tulip", "tundra", "valley", "vapor", "velvet", "vessel", "vine", "violet",
    "vortex", "walnut", "wave", "whisper", "willow", "wind", "winter", "wolf",
    "wren", "zenith", "zephyr", "alder", "aspen", "aster", "aurora", "balsam",
    "basalt", "birch", "blaze", "bloom", "bonfire", "branch", "brook", "cascade",
    "cavern", "chalet", "cliff", "clover", "copper", "coyote", "crag", "creek",
    "cypress", "dune", "echo", "elm", "evergreen", "fern", "fawn", "fig",
    "finch", "fjord", "flint", "fox", "garnet", "geyser", "glade", "granite",
    "gull", "heather", "heron", "hickory", "holly", "iris", "ivy", "jade",
    "juniper", "kelp", "lapis", "lichen", "lynx", "maple", "marble", "marten",
    "mesa", "monarch", "moonstone", "moor", "myrtle", "nutmeg", "oak", "onyx",
    "opal", "orca", "osprey", "peacock", "pine", "pipit", "poplar", "poppy",
    "puffin", "redwood", "robin", "saffron", "sagebrush", "sequoia", "spruce", "starling",
    "sycamore", "taiga", "tamarack", "thrush", "tidal", "timberland", "tor", "trillium",
    "trout", "vulture", "warbler", "wolverine", "woodland", "yarrow", "yellowstone", "yucca"
]


def compute_file_hashes(file_path: str, algorithms: list[str] | None = None) -> dict:
    """Вычисляет контрольные суммы файла (MD5, SHA-1, SHA-256, SHA-512) потоковым чтением."""
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Файл не найден: {path}")

    selected = algorithms or ["md5", "sha1", "sha256", "sha512"]
    hashers = {}
    for alg in selected:
        alg_lower = alg.lower()
        if alg_lower == "md5":
            hashers["md5"] = hashlib.md5()
        elif alg_lower == "sha1":
            hashers["sha1"] = hashlib.sha1()
        elif alg_lower == "sha256":
            hashers["sha256"] = hashlib.sha256()
        elif alg_lower == "sha512":
            hashers["sha512"] = hashlib.sha512()
        else:
            raise ValueError(f"Неподдерживаемый алгоритм хэширования: {alg}")

    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            for h in hashers.values():
                h.update(chunk)

    stat = path.stat()
    result = {
        "name": path.name,
        "path": str(path),
        "size": stat.st_size,
        "mtime": int(stat.st_mtime),
        "hashes": {name: h.hexdigest() for name, h in hashers.items()},
    }
    return result


def compute_text_hash(text: str) -> dict:
    """Вычисляет хэши и Base64 для произвольного текста."""
    data = text.encode("utf-8")
    sha256 = hashlib.sha256(data).hexdigest()
    md5 = hashlib.md5(data).hexdigest()
    sha1 = hashlib.sha1(data).hexdigest()
    b64_enc = base64.b64encode(data).decode("utf-8")

    b64_dec = None
    try:
        # Проверяем, можно ли декодировать обратно
        dec_bytes = base64.b64decode(text.strip().encode("utf-8"), validate=True)
        b64_dec = dec_bytes.decode("utf-8", errors="replace")
    except Exception:
        b64_dec = None

    return {
        "text": text,
        "length": len(text),
        "sha256": sha256,
        "md5": md5,
        "sha1": sha1,
        "base64_encode": b64_enc,
        "base64_decode": b64_dec,
    }


def generate_password(
    length: int = 16,
    uppercase: bool = True,
    lowercase: bool = True,
    digits: bool = True,
    symbols: bool = True,
    avoid_ambiguous: bool = True,
    mode: str = "random",
    words_count: int = 4,
    separator: str = "-",
) -> dict:
    """Генерирует криптографически стойкий пароль или мнемоническую фразу (Passphrase)."""
    if mode == "passphrase":
        words_count = max(2, min(10, words_count))
        chosen = [secrets.choice(WORDLIST) for _ in range(words_count)]
        # Добавляем одну случайную цифру в конец для стойкости
        num = secrets.randbelow(90) + 10
        password = separator.join(chosen) + f"{separator}{num}"
        # Оценка энтропии: log2(len(WORDLIST) ** words_count * 90)
        entropy = round(words_count * math.log2(len(WORDLIST)) + math.log2(90), 1)
        strength = "very_strong" if entropy >= 60 else "strong"
        return {
            "password": password,
            "length": len(password),
            "entropy": entropy,
            "strength": strength,
            "mode": "passphrase",
        }

    length = max(6, min(128, length))
    pool_parts = []
    guaranteed = []

    if uppercase:
        chars = string.ascii_uppercase
        if avoid_ambiguous:
            chars = "".join(c for c in chars if c not in AMBIGUOUS_CHARS)
        if chars:
            pool_parts.append(chars)
            guaranteed.append(secrets.choice(chars))

    if lowercase:
        chars = string.ascii_lowercase
        if avoid_ambiguous:
            chars = "".join(c for c in chars if c not in AMBIGUOUS_CHARS)
        if chars:
            pool_parts.append(chars)
            guaranteed.append(secrets.choice(chars))

    if digits:
        chars = string.digits
        if avoid_ambiguous:
            chars = "".join(c for c in chars if c not in AMBIGUOUS_CHARS)
        if chars:
            pool_parts.append(chars)
            guaranteed.append(secrets.choice(chars))

    if symbols:
        chars = SYMBOLS_SAFE
        pool_parts.append(chars)
        guaranteed.append(secrets.choice(chars))

    if not pool_parts:
        # Fallback to lowercase
        pool_parts = [string.ascii_lowercase]
        guaranteed = [secrets.choice(string.ascii_lowercase)]

    full_pool = "".join(pool_parts)
    remaining_len = max(0, length - len(guaranteed))
    random_part = [secrets.choice(full_pool) for _ in range(remaining_len)]

    all_chars = guaranteed + random_part
    # Перемешиваем криптографически стойко (Fisher-Yates)
    for i in range(len(all_chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        all_chars[i], all_chars[j] = all_chars[j], all_chars[i]

    password = "".join(all_chars)
    pool_size = len(set(full_pool))
    entropy = round(length * math.log2(max(2, pool_size)), 1)

    if entropy >= 75:
        strength = "very_strong"
    elif entropy >= 50:
        strength = "strong"
    elif entropy >= 35:
        strength = "medium"
    else:
        strength = "weak"

    return {
        "password": password,
        "length": len(password),
        "entropy": entropy,
        "strength": strength,
        "mode": "random",
    }
