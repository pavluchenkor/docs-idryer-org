#!/usr/bin/env python3
"""Отчёт о пробелах перевода в docs/.

Сравнивает набор .md-страниц каждой локали с эталонной (по умолчанию `ru`)
и показывает, каких файлов НЕ ХВАТАЕТ в языке (они подменяются fallback'ом
на эталон — читатель видит чужой язык) и какие ЛИШНИЕ (есть в языке, но нет в
эталоне — такие пути i18n не свяжет с переводом).

Запуск из корня проекта:
    python3 validate-i18n.py            # docs/, эталон ru
    python3 validate-i18n.py path/to/docs --base ru

Только отчёт, всегда выходит с кодом 0 — в сборку не вмешивается.
Запускать ПОСЛЕ rebuild.sh, когда контент продуктовых репо уже смонтирован.
"""

import argparse
import sys
from pathlib import Path
from re import compile as re_compile

# Та же логика, что у mkdocs-static-i18n: что считается папкой-локалью.
RE_LOCALE = re_compile(r"(^[a-z]{2}(-[A-Za-z]{4})?(-[A-Z]{2})?$)|(^[a-z]{2}_[A-Z]{2}$)")


def md_set(lang_dir: Path) -> set:
    """Относительные пути всех .md внутри папки локали."""
    return {
        p.relative_to(lang_dir).as_posix()
        for p in lang_dir.rglob("*.md")
        if p.is_file()
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Отчёт о пробелах перевода в docs/")
    ap.add_argument("docs", nargs="?", default="docs", help="путь к папке docs (по умолчанию docs)")
    ap.add_argument("--base", default="ru", help="эталонная локаль (по умолчанию ru)")
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

    langs = sorted(
        d.name
        for d in docs.iterdir()
        if d.is_dir() and d.name != args.base and RE_LOCALE.match(d.name)
    )

    print(f"Пробелы перевода в {docs}/  (эталон: {args.base}, всего {len(base)} страниц)\n")

    total_missing = total_extra = 0
    clean = []
    for lang in langs:
        cur = md_set(docs / lang)
        missing = sorted(base - cur)
        extra = sorted(cur - base)
        total_missing += len(missing)
        total_extra += len(extra)

        if not missing and not extra:
            clean.append(lang)
            continue

        print(f"── {lang} ──  не хватает: {len(missing)}, лишних: {len(extra)}")
        for f in missing:
            print(f"   ✗ нет перевода: {f}")
        for f in extra:
            print(f"   ⚠ лишний (нет в {args.base}): {f}")
        print()

    if clean:
        print(f"✓ Полный перевод: {', '.join(clean)}\n")

    print(f"Итого: не хватает {total_missing}, лишних {total_extra}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
