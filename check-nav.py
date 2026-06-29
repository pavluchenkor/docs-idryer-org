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


def is_inside_mounted_repo(folder: Path) -> bool:
    """Вернуть True, если папка находится внутри смонтированного продуктового репо."""
    for path in (folder, *folder.parents):
        if (path / ".mounted").exists():
            return True
    return False


def build_tree(folder: Path) -> dict:
    """Построить полное дерево навигации с вложениями."""
    pages_file = folder / ".pages"
    pages_data = load_pages(pages_file) if pages_file.exists() else {}

    title = pages_data.get("title", folder.name)
    children = []
    warnings = []
    mounted_context = is_inside_mounted_repo(folder)

    def add_nav_entry(entry: Any, target_children: list, target_warnings: list) -> None:
        if isinstance(entry, str):
            # Пропустить многоточие
            if entry == "...":
                return
            # Пропустить файлы index.md
            if entry == "index.md":
                return

            path = folder / entry
            if path.is_dir():
                # Рекурсивно загрузить подпапку
                target_children.append(build_tree(path))
            elif path.with_suffix(".md").exists():
                target_children.append({
                    "title": entry.replace(".md", ""),
                    "type": "file",
                    "children": []
                })
            else:
                # Папка не существует — показать как "отсутствует"
                target_children.append({
                    "title": f"{entry} ⚠️ (не найдена)",
                    "type": "missing",
                    "children": []
                })
            return

        if isinstance(entry, dict):
            for display_name, target in entry.items():
                if isinstance(target, list):
                    group_children = []
                    for nested_entry in target:
                        add_nav_entry(nested_entry, group_children, target_warnings)
                    target_children.append({
                        "title": display_name,
                        "type": "folder",
                        "children": group_children,
                        "warnings": []
                    })
                    continue

                if not isinstance(target, str):
                    target_children.append({
                        "title": f"{display_name} ⚠️ (неподдерживаемый nav target)",
                        "type": "missing",
                        "children": []
                    })
                    continue

                if target.startswith("http"):
                    # Пропустить внешние ссылки
                    continue
                target_path = folder / target
                if target_path.is_dir():
                    if mounted_context:
                        # В центральной навигации это штатный формат. В смонтированных
                        # репо он может исказить итоговое дерево после раскладки по mount.
                        target_warnings.append(f"⚠️  Используется формат '{display_name}: {target}' для папки "
                                               f"в смонтированном репо: {folder / '.pages'}")
                    # Рекурсивно загрузить подпапку
                    subtree = build_tree(target_path)
                    subtree["title"] = display_name
                    target_children.append(subtree)
                elif target_path.with_suffix(".md").exists():
                    target_children.append({
                        "title": display_name,
                        "type": "file",
                        "children": []
                    })
                else:
                    target_children.append({
                        "title": f"{display_name} ⚠️ (не найдена)",
                        "type": "missing",
                        "children": []
                    })

    # Если есть явный nav в .pages, использовать его
    if "nav" in pages_data:
        nav = pages_data["nav"]
        if isinstance(nav, list):
            for entry in nav:
                add_nav_entry(entry, children, warnings)
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
        "children": children,
        "warnings": warnings
    }


def collect_warnings(node: dict) -> list:
    """Собрать все предупреждения из дерева."""
    warnings = node.get("warnings", [])
    for child in node.get("children", []):
        warnings.extend(collect_warnings(child))
    return warnings


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

    # На сервере в контейнере файлы в /build/docs-idryer-org/, пробуем оба варианта
    if not docs_path.exists():
        fallback = Path("/build/docs-idryer-org") / args.docs
        if fallback.exists():
            docs_path = fallback.resolve()
        else:
            print(f"❌ Путь не найден: {docs_path}", file=sys.stderr)
            return 1

    all_warnings = []

    # Если это docs/ — показать все языки
    if docs_path.name == "docs":
        for lang_dir in sorted(docs_path.iterdir()):
            if lang_dir.is_dir() and not lang_dir.name.startswith(".") and (lang_dir / ".pages").exists():
                print(f"\n📄 {lang_dir.name.upper()}:")
                tree = build_tree(lang_dir)
                print_tree(tree)
                all_warnings.extend(collect_warnings(tree))
    else:
        # Показать только этот язык
        tree = build_tree(docs_path)
        print_tree(tree)
        all_warnings.extend(collect_warnings(tree))

    # Вывести все предупреждения в конце
    if all_warnings:
        print("\n" + "="*60)
        for warning in all_warnings:
            print(warning)

    return 0


if __name__ == "__main__":
    sys.exit(main())
