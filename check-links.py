#!/usr/bin/env python3
"""Проверка локальных ссылок в .md (картинки, страницы, файлы).

Находит в каждом .md ссылки вида ![alt](путь), [текст](путь) и <img src="...">,
берёт ЛОКАЛЬНЫЕ (не http/mailto/#якорь) и проверяет, что цель существует
ОТНОСИТЕЛЬНО самого файла — с учётом РЕГИСТРА.

Зачем регистр: macOS — регистронезависимая ФС, поэтому ../img/Box.jpg и
../img/box.jpg на твоём Mac «оба работают». На сервере (Linux) — нет, и ссылка
ломается уже на проде. Этот чекер ловит такие случаи заранее.

Запуск (из корня docs-idryer-org):
    python3 check-links.py '/path/to/repo/docs'
    python3 check-links.py '/path/to/repo/docs' --root /path/to/repo   # если ссылки ведут выше docs (../CAD)

Только отчёт, всегда выходит с кодом 0.

Про монтирование: чекер резолвит ссылки в ИСХОДНОМ дереве репо — это правильный
слой. Автор пишет ЕСТЕСТВЕННЫЕ ссылки (../../img/..., ../../../CAD/...), верные
относительно своего файла (работают в превью и на GitHub), а под глубину mount
их на сборке переписывает хук движка `hooks/asset_links.py` (img → /img/...,
CAD/PDF/... → /assets/...). Поэтому: зелёный отчёт здесь = ссылки корректны и
хук их правильно перепишет на сайте. Отдельный --mount не нужен.
"""

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

# ![alt](target)  и  [text](target)  — target до пробела+кавычки (title) или до ')'
RE_MD = re.compile(r"!?\[[^\]]*\]\(\s*([^)]+?)\s*\)")
# <img src="..."> / <a href="...">
RE_HTML = re.compile(r"""<(?:img|a)\b[^>]*?\b(?:src|href)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

SKIP_PREFIXES = ("http://", "https://", "//", "mailto:", "tel:", "data:", "#")


def clean_target(raw: str) -> str:
    """Отрезает markdown-title (path "title") и якорь (#...), декодирует %20."""
    t = raw.strip()
    # title после пробела: ... "Подпись"  или  ... 'Подпись'
    for q in (' "', " '"):
        i = t.find(q)
        if i != -1:
            t = t[:i].strip()
    t = t.split("#", 1)[0]  # убрать якорь
    return unquote(t.strip())


def case_sensitive_exists(target_abs: Path, stop_root: Path) -> bool:
    """Существует ли путь, сверяя РЕГИСТР каждого сегмента ниже stop_root."""
    try:
        rel = target_abs.relative_to(stop_root)
    except ValueError:
        return target_abs.exists()  # вне stop_root — обычная проверка
    cur = stop_root
    for seg in rel.parts:
        try:
            entries = os.listdir(cur)
        except OSError:
            return False
        if seg not in entries:  # точное совпадение регистра
            return False
        cur = cur / seg
    return True


def remove_code_blocks(text: str) -> str:
    """Remove code blocks (```...```) and inline code (backticks) to avoid false matches on C++ lambdas etc."""
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", "", text)
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description="Проверка локальных ссылок в .md")
    ap.add_argument("docs", help="путь к папке docs/")
    ap.add_argument("--root", help="корень для регистро-проверки (по умолчанию docs/..)")
    args = ap.parse_args()

    docs = Path(args.docs).resolve()
    if not docs.is_dir():
        print(f"Папка не найдена: {docs}", file=sys.stderr)
        return 0
    stop_root = Path(args.root).resolve() if args.root else docs.parent

    total = broken = files_with_issues = 0
    for md in sorted(docs.rglob("*.md")):
        issues = []
        text = md.read_text(encoding="utf-8")
        text_no_code = remove_code_blocks(text)
        lines_no_code = text_no_code.splitlines()
        original_lines = text.splitlines()
        for i, line in enumerate(original_lines, 1):
            clean_line = lines_no_code[i - 1] if i <= len(lines_no_code) else ""
            for m in list(RE_MD.finditer(clean_line)) + list(RE_HTML.finditer(clean_line)):
                raw = m.group(1)
                if not raw or raw.startswith(SKIP_PREFIXES):
                    continue
                target = clean_target(raw)
                if not target or target.startswith(SKIP_PREFIXES):
                    continue
                total += 1
                abs_target = Path(os.path.normpath(md.parent / target))
                if not abs_target.exists():
                    issues.append((i, raw, "не найден"))
                    broken += 1
                elif not case_sensitive_exists(abs_target, stop_root):
                    issues.append((i, raw, "регистр/имя не совпадает (сломается на Linux)"))
                    broken += 1

        if issues:
            files_with_issues += 1
            print(f"\n{md.relative_to(docs)}")
            for ln, raw, why in issues:
                print(f"   ✗ стр.{ln}: {raw}  — {why}")

    print(f"\nИтого: проверено {total} ссылок, битых {broken} в {files_with_issues} файлах.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
