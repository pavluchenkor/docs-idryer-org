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


def build_tree(folder: Path) -> dict:
    """Построить полное дерево навигации с вложениями."""
    pages_file = folder / ".pages"
    pages_data = load_pages(pages_file) if pages_file.exists() else {}

    title = pages_data.get("title", folder.name)
    children = []

    # Если есть явный nav в .pages, использовать его
    if "nav" in pages_data:
        nav = pages_data["nav"]
        if isinstance(nav, list):
            for entry in nav:
                if isinstance(entry, str):
                    path = folder / entry
                    if path.is_dir():
                        # Рекурсивно загрузить подпапку
                        children.append(build_tree(path))
                    elif path.with_suffix(".md").exists():
                        children.append({
                            "title": entry.replace(".md", ""),
                            "type": "file",
                            "children": []
                        })
                elif isinstance(entry, dict):
                    for display_name, target in entry.items():
                        if target.startswith("http"):
                            # Пропустить внешние ссылки
                            continue
                        target_path = folder / target
                        if target_path.is_dir():
                            # Рекурсивно загрузить подпапку
                            subtree = build_tree(target_path)
                            subtree["title"] = display_name
                            children.append(subtree)
                        elif target_path.with_suffix(".md").exists():
                            children.append({
                                "title": display_name,
                                "type": "file",
                                "children": []
                            })
    else:
        # Автоматическое получение из папок
        try:
            for item in sorted(folder.iterdir()):
                if item.name.startswith(".") or item.name.startswith("_"):
                    continue
                if item.is_dir():
                    children.append(build_tree(item))
                elif item.suffix == ".md" and item.name != "README.md":
                    children.append({
                        "title": item.stem,
                        "type": "file",
                        "children": []
                    })
        except PermissionError:
            pass

    return {
        "title": title,
        "type": "folder",
        "children": children
    }


def print_tree(node: dict, prefix: str = "", is_last: bool = True) -> None:
    """Вывести дерево навигации в консоль."""
    # Вывести текущий узел
    connector = "└─ " if is_last else "├─ "
    print(f"{prefix}{connector}{node['title']}" if prefix else node['title'])

    # Вывести детей
    children = node.get("children", [])
    for i, child in enumerate(children):
        is_last_child = i == len(children) - 1
        extension = "   " if is_last else "│  "
        print_tree(child, prefix + extension, is_last_child)


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
            if lang_dir.is_dir() and not lang_dir.name.startswith(".") and lang_dir.name != "img":
                print(f"\n📄 {lang_dir.name.upper()}:")
                tree = build_tree(lang_dir)
                print_tree(tree)
    else:
        # Показать только этот язык
        tree = build_tree(docs_path)
        print_tree(tree)

    return 0


if __name__ == "__main__":
    sys.exit(main())
