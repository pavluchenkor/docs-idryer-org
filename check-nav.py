#!/usr/bin/env python3
"""Валидатор и визуализатор структуры навигации из .pages файлов.

Показывает, как будет выглядеть меню на сайте.

Запуск:
    python3 check-nav.py docs/ru/          # только русский
    python3 check-nav.py docs/             # все языки
"""

import argparse
import sys
from pathlib import Path
from typing import Any
import yaml


def load_pages(file_path: Path) -> dict:
    """Загрузить .pages файл."""
    try:
        return yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        return {"error": str(e)}


def build_tree(folder: Path, level: int = 0) -> list:
    """Построить дерево навигации из папок и .pages файлов."""
    items = []

    pages_file = folder / ".pages"
    pages_data = load_pages(pages_file) if pages_file.exists() else {}

    # Если есть явный nav в .pages, использовать его
    if "nav" in pages_data:
        nav = pages_data["nav"]
        if isinstance(nav, list):
            for entry in nav:
                if isinstance(entry, str):
                    # Просто имя файла или папки
                    path = folder / entry
                    if path.is_dir():
                        title = entry
                        if "title" in pages_data:
                            title = pages_data["title"]
                        items.append({
                            "title": title,
                            "path": path,
                            "type": "folder",
                            "level": level
                        })
                    elif path.with_suffix(".md").exists():
                        items.append({
                            "title": entry.replace(".md", ""),
                            "path": entry,
                            "type": "file",
                            "level": level
                        })
                elif isinstance(entry, dict):
                    # Переименованная папка/файл: {Display Name: folder}
                    for display_name, target in entry.items():
                        target_path = folder / target
                        if target_path.is_dir():
                            items.append({
                                "title": display_name,
                                "path": target_path,
                                "type": "folder",
                                "level": level
                            })
                        elif target_path.with_suffix(".md").exists():
                            items.append({
                                "title": display_name,
                                "path": target,
                                "type": "file",
                                "level": level
                            })
    else:
        # Автоматическое получение из папок
        title = pages_data.get("title", folder.name)

        # Рекурсивно добавить подпапки
        try:
            for item in sorted(folder.iterdir()):
                if item.name.startswith(".") or item.name.startswith("_"):
                    continue
                if item.is_dir():
                    items.append({
                        "title": item.name,
                        "path": item,
                        "type": "folder",
                        "level": level
                    })
                elif item.suffix == ".md" and item.name != "README.md":
                    items.append({
                        "title": item.stem,
                        "path": item.name,
                        "type": "file",
                        "level": level
                    })
        except PermissionError:
            pass

    return items


def print_tree(folder: Path, level: int = 0, prefix: str = "") -> None:
    """Вывести дерево навигации в консоль."""
    items = build_tree(folder, level)

    for i, item in enumerate(items):
        is_last = i == len(items) - 1

        # Определить префикс
        if level == 0:
            current_prefix = ""
            next_prefix = ""
        else:
            current_prefix = "└─ " if is_last else "├─ "
            next_prefix = "   " if is_last else "│  "

        # Вывести текущий элемент
        print(f"{prefix}{current_prefix}{item['title']}")

        # Если папка — рекурсивно вывести содержимое
        if item["type"] == "folder":
            print_tree(item["path"], level + 1, prefix + next_prefix)


def main():
    ap = argparse.ArgumentParser(description="Валидатор структуры навигации")
    ap.add_argument("docs", default="docs", nargs="?", help="Путь к docs/ или docs/<lang>/")
    args = ap.parse_args()

    docs_path = Path(args.docs).resolve()

    if not docs_path.exists():
        print(f"❌ Путь не найден: {docs_path}", file=sys.stderr)
        return 1

    # Если это docs/ — показать все языки
    if docs_path.name == "docs":
        for lang_dir in sorted(docs_path.iterdir()):
            if lang_dir.is_dir() and not lang_dir.name.startswith("."):
                print(f"\n📄 {lang_dir.name.upper()}:")
                print_tree(lang_dir)
    else:
        # Показать только этот язык
        print_tree(docs_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
