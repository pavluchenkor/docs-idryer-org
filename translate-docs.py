#!/usr/bin/env python3
"""
translate-docs.py — инкрементальный переводчик документации

Что делает:
    Переводит .md файлы из исходного языка (по умолчанию: ru) во все остальные
    языки, найденные в папке docs/. Запоминает состояние: при следующем запуске
    переводит только те файлы, которые изменились с прошлого раза.

    Добивание пробелов: файл переводится не только когда изменился ru-исходник,
    но и когда в каком-то целевом языке его ПРОСТО НЕТ — тогда скрипт переводит
    его именно в недостающие языки (по каждому языку отдельно), даже если хэш
    ru не менялся. Так закрываются пробелы перевода (которые показывает
    validate-i18n.py) без дорогого полного --force. Языки, где файл уже есть,
    не трогаются.

Как пользоваться:
    # Обычный запуск — из корня репозитория (рядом с docs/):
    python ~/Projects/iDryerDev/translate-docs.py

    # Если запускаешь не из корня репо:
    python ~/Projects/iDryerDev/translate-docs.py --docs /path/to/repo/docs

Параметры:
    --docs <путь>   Явный путь к папке docs/. По умолчанию ищет docs/ в текущей папке.
    --source <код>  Исходный язык. По умолчанию: ru.
    --seed          Первая инициализация. Используй один раз, когда переводы уже
                    есть и пересоздавать их не нужно — скрипт просто запомнит
                    текущее состояние и в следующий раз будет переводить только
                    реальные изменения.
    --force         Перевести все файлы заново, игнорируя кэш.
    --dry-run       Предохранитель: показать ПЛАН (что и на какие языки) и оценку
                    числа запросов к API — без перевода. Файлы, кэш и баланс не
                    трогаются, API-ключ не требуется. Запускай перед реальным
                    прогоном, чтобы увидеть объём и не потратить лишнего.

Требования:
    Anthropic SDK уже установлен в conda base:
        conda activate base   ← или убедись что base активен (видно в приглашении)
    Ключ задаётся ОТДЕЛЬНОЙ переменной (не стандартной ANTHROPIC_API_KEY, чтобы
    её не подхватывал агент/SDK):
        export TRANSLATE_API_KEY_ANT=...

    Запускать через python (не python3!):
        python translate-docs.py ...
    Либо явно через conda:
        ~/miniforge3/bin/python translate-docs.py ...

    Почему не python3: на macOS /usr/bin/python3 — системный, без conda-пакетов.

Файл состояния:
    .translation-state.json — создаётся рядом с docs/, в git не нужен.
    Добавь строку в .gitignore: .translation-state.json
"""

from __future__ import annotations  # аннотации как строки → работает и на Python 3.9

import os
import sys
import json
import hashlib
import argparse
from pathlib import Path

try:
    import anthropic
except ImportError:
    anthropic = None  # нужен только для реального перевода; --dry-run/--seed работают без него

try:
    import yaml  # для перевода .pages (меню). Если нет — .pages пропускаются.
except ImportError:
    yaml = None

MODEL = "claude-haiku-4-5-20251001"

LANG_NAMES = {
    "en":      "English",
    "ru":      "Russian",
    "de":      "German",
    "fr":      "French",
    "es":      "Spanish",
    "cs":      "Czech",
    "ja":      "Japanese",
    "pt":      "European Portuguese",
    "pt-BR":   "Brazilian Portuguese",
    "zh":      "Simplified Chinese (Mainland China)",
    "zh-Hant": "Traditional Chinese (Taiwan)",
}

# Папки внутри docs/, которые не являются языковыми локалями
NON_LANG_DIRS = {"img", "stylesheets", "assets", ".git"}

SYSTEM_PROMPT = """You are a technical documentation translator specializing in IoT and electronics documentation.

Rules (follow exactly):

1. PRESERVE unchanged:
   - All code blocks (```...``` and indented blocks) — copy byte-for-byte
   - All URLs in links: [text](URL) — translate only the display text, never the URL
   - File paths and directory names
   - Technical acronyms and terms: ESP32, MQTT, GPIO, PWM, WiFi, TLS, TCP, API, SDK, UART, I2C, SPI, CAN, NVS,
     NTC, PID, STM32, RP2040, Klipper, PlatformIO, Arduino, NFC, RFID, PETG, ABS, ASA, PLA, ADC, TRIAC,
     USB, TX, RX, GND, LED, DC, AC, Hz, mA, mF, pF, nF, µF, Ω, kΩ, MΩ, Vgs, Rds, CT, DFU, SWD, ST-Link,
     BOOT, STRAP, PSRAM, WROOM, C3, C6, S3, Nucleo, Blue Pill, Black Pill, Pico, H7, G4, F4, F1, G0, F0,
     C0, SRAM, flash, ADC1, ADC2, LEDC, PE, VIN, UF2, Wikimedia, Commons, CFM, dB, SPL, NRST, VTref,
     SWDIO, SWCLK, DTR, CTS, RTS, CAT, CC0, CC-BY-SA, HB, V-2, V-1, V-0, 5VB, 5VA, HBF, HF-1, HF-2,
     3MF, STL, LSB, MSB, XPS, EPS, PIR, RC522, MFRC522, PN532, NTAG, MIFARE, ISO14443A, Dupont, JST,
     Faston, URL, UID
   - Brand/product names: iDryer, iHeater, OpenSpool, OpenPrintTag, Home Assistant, PlatformIO, Arduino, Claude, Anthropic
   - Class and function names, variable names in code
   - YAML/JSON keys and values inside code blocks
   - Units and symbols: °C, %, g, kg, mm, h, min, V, A, W, Ω

2. TRANSLATE:
   - All prose text outside code blocks
   - Section headings (# Heading)
   - Bullet and numbered list text
   - Table cell content (but not code inside cells)
   - Link display text: [translate THIS part](keep-url)

3. OUTPUT:
   Return ONLY the translated markdown. No code fences around the whole output,
   no explanations, no preamble. The response must be a valid .md file.
"""


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def find_docs_dir(start: Path) -> Path:
    candidates = [start / "docs", start.parent / "docs"]
    for d in candidates:
        if d.is_dir():
            return d
    raise FileNotFoundError(
        f"Папка docs/ не найдена рядом с {start}. "
        "Запусти из корня репозитория или передай --docs /path/to/docs"
    )


def detect_target_langs(docs_dir: Path, source_lang: str) -> list[str]:
    langs = []
    for d in sorted(docs_dir.iterdir()):
        if (
            d.is_dir()
            and d.name != source_lang
            and d.name not in NON_LANG_DIRS
            and not d.name.startswith(".")
            and any(d.rglob("*.md"))
        ):
            langs.append(d.name)
    return langs


def check_api(client: anthropic.Anthropic) -> None:
    """Проверяет что ключ рабочий и есть баланс."""
    try:
        client.messages.create(
            model=MODEL,
            max_tokens=5,
            messages=[{"role": "user", "content": "hi"}],
        )
    except anthropic.AuthenticationError:
        print("Ошибка: неверный TRANSLATE_API_KEY_ANT.")
        sys.exit(1)
    except Exception as e:
        msg = str(e).lower()
        if any(w in msg for w in ("credit", "billing", "balance", "permission", "402", "403")):
            print("Недостаточно средств на балансе Anthropic API.")
            print("Пополни баланс: https://console.anthropic.com/settings/billing")
            sys.exit(1)
        # Другая ошибка — пробрасываем
        raise


def translate_file(
    client: anthropic.Anthropic,
    content: str,
    source_lang: str,
    target_lang: str,
) -> str | None:
    source_name = LANG_NAMES.get(source_lang, source_lang)
    target_name = LANG_NAMES.get(target_lang, target_lang)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Translate the following documentation from {source_name} to {target_name}.\n"
                        "Return only the translated markdown.\n\n"
                        f"<document>\n{content}\n</document>"
                    ),
                }
            ],
        )
        return response.content[0].text if response.content else None
    except Exception as e:
        print(f"    ошибка API: {e}")
        return None


LABEL_SYSTEM_PROMPT = """You translate short UI menu labels for technical documentation.
Return ONLY the translated label — no quotes, no extra punctuation, no explanation.
Keep technical terms, acronyms and brand names unchanged (ESP32, MQTT, iDryer, TDS, etc.).
"""


def translate_label(client, text, source_lang, target_lang):
    """Переводит одну короткую подпись меню (значение title: или подпись в nav:)."""
    source_name = LANG_NAMES.get(source_lang, source_lang)
    target_name = LANG_NAMES.get(target_lang, target_lang)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=200,
            system=[
                {"type": "text", "text": LABEL_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Translate this menu label from {source_name} to {target_name}. "
                        f"Return only the label:\n\n{text}"
                    ),
                }
            ],
        )
        out = response.content[0].text.strip() if response.content else None
        return out or None
    except Exception as e:
        print(f"    ошибка API (label): {e}")
        return None


def translate_pages_file(client, content, source_lang, target_lang):
    """Переводит .pages: ТОЛЬКО значение title: и подписи в nav: (текст слева от ':').
    Ключи, имена файлов/папок, порядок и прочие поля awesome-pages сохраняет как есть."""
    if yaml is None:
        return None
    try:
        data = yaml.safe_load(content)
    except Exception as e:
        print(f"    .pages не распарсился: {e}")
        return None
    if not isinstance(data, dict):
        return content  # нечего переводить — оставляем как есть

    changed = False

    if isinstance(data.get("title"), str) and data["title"].strip():
        t = translate_label(client, data["title"], source_lang, target_lang)
        if t is None:
            return None
        data["title"] = t
        changed = True

    nav = data.get("nav")
    if isinstance(nav, list):
        new_nav = []
        for item in nav:
            if isinstance(item, dict):
                new_item = {}
                for label, target in item.items():
                    if isinstance(label, str) and label.strip():
                        tl = translate_label(client, label, source_lang, target_lang)
                        if tl is None:
                            return None
                        new_item[tl] = target
                        changed = True
                    else:
                        new_item[label] = target  # просто файл/папка — не трогаем
                new_nav.append(new_item)
            else:
                new_nav.append(item)
        if changed:
            data["nav"] = new_nav

    if not changed:
        return content  # переводить нечего — возвращаем оригинал без изменений

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)


def _count_requests(content: str, kind: str) -> int:
    """Сколько запросов к API уйдёт на ОДИН язык для этого файла.
    .md = 1; .pages = по числу переводимых подписей (title + строковые метки nav)."""
    if kind != "pages":
        return 1
    if yaml is None:
        return 0
    try:
        data = yaml.safe_load(content)
    except Exception:
        return 0
    if not isinstance(data, dict):
        return 0
    n = 1 if isinstance(data.get("title"), str) and data["title"].strip() else 0
    nav = data.get("nav")
    if isinstance(nav, list):
        for item in nav:
            if isinstance(item, dict):
                for label in item:
                    if isinstance(label, str) and label.strip():
                        n += 1
    return n


def _print_plan(work: list, target_langs: list) -> None:
    """--dry-run: печатает план перевода и оценку числа запросов к API."""
    print("=== DRY-RUN: ничего не переводим; файлы и .translation-state.json не трогаем ===\n")
    full = [w for w in work if len(w[4]) == len(target_langs)]
    partial = [w for w in work if len(w[4]) != len(target_langs)]
    total = 0

    print(f"1) Во ВСЕ языки (новый/изменённый ru-исходник): {len(full)} файлов")
    for rel, content, _h, kind, langs in full:
        per = _count_requests(content, kind)
        total += per * len(langs)
        print(f"   ~ {rel}  →  {len(langs)} яз. ×{per} = {per * len(langs)} зап.")

    if partial:
        files_langs = sum(len(w[4]) for w in partial)
        print(f"\n2) Добить недостающие: {files_langs} файло-языков")
        for rel, content, _h, kind, langs in partial:
            per = _count_requests(content, kind)
            total += per * len(langs)
            print(f"   + {rel}  →  {', '.join(langs)}  = {per * len(langs)} зап.")

    print(f"\nИТОГО запросов к API (оценка): ~{total}")
    print("Запуск без --dry-run выполнит перевод и потратит баланс.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Incremental markdown docs translator")
    parser.add_argument("docs_path", nargs="?", type=Path, help="Путь к docs/ (позиционно, эквивалент --docs)")
    parser.add_argument("--docs", type=Path, help="Путь к папке docs/ (флагом)")
    parser.add_argument("--source", default="ru", help="Исходный язык (default: ru)")
    parser.add_argument("--force", action="store_true", help="Перевести всё заново, игнорируя кэш")
    parser.add_argument("--seed", action="store_true", help="Зафиксировать текущее состояние без перевода (первая инициализация)")
    parser.add_argument("--dry-run", action="store_true", help="Показать план и оценку запросов к API без перевода (ключ не нужен)")
    args = parser.parse_args()

    # --dry-run и --seed не зовут API → ключ для них не нужен.
    api_key = os.environ.get("TRANSLATE_API_KEY_ANT")
    if not api_key and not (args.dry_run or args.seed):
        print("Не задан TRANSLATE_API_KEY_ANT (отдельный ключ только для перевода).")
        print("Задай в окружении: export TRANSLATE_API_KEY_ANT=...")
        sys.exit(1)

    docs_dir = args.docs or args.docs_path or find_docs_dir(Path.cwd())
    source_lang = args.source
    source_dir = docs_dir / source_lang

    if not source_dir.is_dir():
        print(f"Исходная папка не найдена: {source_dir}")
        sys.exit(1)

    target_langs = detect_target_langs(docs_dir, source_lang)
    if not target_langs:
        print(f"Целевые языки не найдены в {docs_dir} (кроме {source_lang}/)")
        sys.exit(1)

    state_file = docs_dir.parent / ".translation-state.json"
    state: dict = {}
    if not args.force and state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    print(f"Docs:    {docs_dir}")
    print(f"Source:  {source_lang}/")
    print(f"Targets: {', '.join(target_langs)}")
    if args.force:
        print("Режим: --force (переводим всё)")
    print()

    # Режим --seed: просто сохранить хэши без перевода
    if args.seed:
        all_files = sorted(source_dir.rglob("*.md")) + sorted(source_dir.rglob(".pages"))
        for f in all_files:
            rel = str(f.relative_to(source_dir))
            state[rel] = sha256_of(f.read_text(encoding="utf-8"))
        state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Seed: зафиксировано {len(all_files)} файлов → {state_file}")
        print("Следующий запуск будет переводить только изменения.")
        return

    # Собираем переводимые файлы: .md (контент) и .pages (меню)
    src_files = [(f, "md") for f in sorted(source_dir.rglob("*.md"))]
    if yaml is not None:
        src_files += [(f, "pages") for f in sorted(source_dir.rglob(".pages"))]
    elif any(source_dir.rglob(".pages")):
        print("Внимание: pyyaml не установлен — .pages не переводятся (pip install pyyaml)\n")

    # Определяем что и на какие языки переводить.
    #   - изменился ru-исходник (или --force) → перевести на ВСЕ языки;
    #   - ru не менялся, но в каком-то языке файла НЕТ → добить только те языки,
    #     где файла нет (закрываем пробелы перевода без полного --force).
    # work: (rel_path, content, new_hash, kind, langs)
    work: list[tuple[str, str, str, str, list[str]]] = []
    for f, kind in src_files:
        rel = str(f.relative_to(source_dir))
        content = f.read_text(encoding="utf-8")
        h = sha256_of(content)
        if args.force or state.get(rel) != h:
            langs = list(target_langs)  # исходник изменился — переводим всем
        else:
            langs = [l for l in target_langs if not (docs_dir / l / rel).exists()]
        if langs:
            work.append((rel, content, h, kind, langs))

    if not work:
        print(f"Изменений и пробелов нет — все {len(src_files)} файлов покрыты во всех языках.")
        return

    # --dry-run: показать план и оценку, НИЧЕГО не переводить и не записывать.
    if args.dry_run:
        _print_plan(work, target_langs)
        return

    if anthropic is None:
        print("Для перевода нужен пакет anthropic: pip install anthropic")
        print("(или запусти conda-питоном, где он уже установлен)")
        sys.exit(1)
    client = anthropic.Anthropic(api_key=api_key)
    print("Проверка API... ", end="", flush=True)
    check_api(client)
    print("OK\n")

    print(f"К переводу: {len(work)} из {len(src_files)} файлов\n")

    for i, (rel, content, new_hash, kind, langs) in enumerate(work, 1):
        suffix = "" if len(langs) == len(target_langs) else f"  (добиваю: {', '.join(langs)})"
        print(f"[{i}/{len(work)}] {rel}{suffix}")
        file_ok = True

        for lang in langs:
            target_file = docs_dir / lang / rel
            target_file.parent.mkdir(parents=True, exist_ok=True)
            print(f"  → {lang:8s} ", end="", flush=True)

            if kind == "pages":
                translated = translate_pages_file(client, content, source_lang, lang)
            else:
                translated = translate_file(client, content, source_lang, lang)

            if translated:
                target_file.write_text(translated, encoding="utf-8")
                print("OK")
            else:
                print("FAIL")
                file_ok = False

        # Обновляем состояние только если все языки прошли успешно
        if file_ok:
            state[rel] = new_hash
            state_file.write_text(
                json.dumps(state, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        print()

    print("Готово.")


if __name__ == "__main__":
    main()
