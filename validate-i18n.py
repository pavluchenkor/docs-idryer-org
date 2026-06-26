#!/usr/bin/env python3
"""Отчёт о пробелах перевода в docs/.

Сравнивает набор .md-страниц каждой локали с эталонной (по умолчанию `ru`)
и создаёт публичные страницы-заглушки для отсутствующих переводов. Файлы с
маркером `<!-- i18n-placeholder: true -->` считаются непереведёнными.

Запуск из корня проекта:
    python3 validate-i18n.py            # docs/, эталон ru
    python3 validate-i18n.py path/to/docs --base ru

Всегда выходит с кодом 0 — сборку не валит.
Запускать ПОСЛЕ rebuild.sh, когда контент продуктовых репо уже смонтирован.
"""

import argparse
import sys
from pathlib import Path
from re import compile as re_compile

import yaml

# Та же логика, что у mkdocs-static-i18n: что считается папкой-локалью.
RE_LOCALE = re_compile(r"(^[a-z]{2}(-[A-Za-z]{4})?(-[A-Z]{2})?$)|(^[a-z]{2}_[A-Z]{2}$)")
PLACEHOLDER_MARKER = "<!-- i18n-placeholder: true -->"
PLACEHOLDER_TEXT = """<!-- i18n-placeholder: true -->

# Translation wanted

This page is not available in this language yet.

You can help the iDryer project by translating this article. Please use the English or Russian version as the source, check the meaning carefully, and submit your translation as a pull request to the documentation repository.

Thank you for helping make the documentation available to more makers.
"""


def md_set(lang_dir: Path) -> set:
    """Относительные пути всех .md внутри папки локали."""
    return {
        p.relative_to(lang_dir).as_posix()
        for p in lang_dir.rglob("*.md")
        if p.is_file()
    }


def create_placeholder(lang_dir: Path, rel_path: str) -> None:
    path = lang_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PLACEHOLDER_TEXT, encoding="utf-8")


def placeholder_set(lang_dir: Path) -> set:
    result = set()
    for path in lang_dir.rglob("*.md"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if PLACEHOLDER_MARKER in text:
            result.add(path.relative_to(lang_dir).as_posix())
    return result


def configured_languages(mkdocs_file: Path) -> list[str]:
    try:
        data = yaml.load(mkdocs_file.read_text(encoding="utf-8"), Loader=yaml.BaseLoader) or {}
    except (OSError, yaml.YAMLError):
        return []

    plugins = data.get("plugins") or []
    for plugin in plugins:
        if not isinstance(plugin, dict) or "i18n" not in plugin:
            continue
        languages = plugin["i18n"].get("languages") or []
        result = []
        for item in languages:
            if not isinstance(item, dict):
                continue
            if str(item.get("build", "true")).lower() == "false":
                continue
            locale = item.get("locale")
            if locale:
                result.append(str(locale))
        return result
    return []


def existing_languages(docs: Path, base: str) -> list[str]:
    return sorted(
        d.name
        for d in docs.iterdir()
        if d.is_dir() and d.name != base and RE_LOCALE.match(d.name)
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Отчёт о пробелах перевода в docs/")
    ap.add_argument("docs", nargs="?", default="docs", help="путь к папке docs (по умолчанию docs)")
    ap.add_argument("--base", default="ru", help="эталонная локаль (по умолчанию ru)")
    ap.add_argument(
        "--mkdocs",
        default=str(Path(__file__).with_name("mkdocs.yml")),
        help="путь к mkdocs.yml со списком языков",
    )
    args = ap.parse_args()

    docs = Path(args.docs)
    if not docs.is_dir():
        print(f"Папка не найдена: {docs}", file=sys.stderr)
        return 0  # только отчёт, сборку не валим

    base_dir = docs / args.base
    if not base_dir.is_dir():
        print(f"Нет эталонной локали: {base_dir}", file=sys.stderr)
        return 0

    base = md_set(base_dir)

    langs = [lang for lang in configured_languages(Path(args.mkdocs)) if lang != args.base]
    if not langs:
        langs = existing_languages(docs, args.base)

    print(f"Пробелы перевода в {docs}/  (эталон: {args.base}, всего {len(base)} страниц)\n")

    total_missing = total_extra = total_placeholders = 0
    clean = []
    for lang in langs:
        lang_dir = docs / lang
        cur = md_set(lang_dir)
        missing = sorted(base - cur)
        extra = sorted(cur - base)
        for f in missing:
            create_placeholder(lang_dir, f)
        placeholders = sorted(placeholder_set(lang_dir))
        total_missing += len(missing)
        total_extra += len(extra)
        total_placeholders += len(placeholders)

        if not missing and not extra and not placeholders:
            clean.append(lang)
            continue

        print(
            f"── {lang} ──  создано заглушек: {len(missing)}, "
            f"не переведено: {len(placeholders)}, лишних: {len(extra)}"
        )
        for f in missing:
            print(f"   + создана заглушка: {f}")
        for f in placeholders:
            print(f"   ✗ не переведено: {f}")
        for f in extra:
            print(f"   ⚠ лишний (нет в {args.base}): {f}")
        print()

    if clean:
        print(f"✓ Полный перевод: {', '.join(clean)}\n")

    print(
        f"Итого: создано заглушек {total_missing}, "
        f"не переведено {total_placeholders}, лишних {total_extra}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
