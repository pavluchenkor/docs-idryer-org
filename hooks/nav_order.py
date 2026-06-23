"""Восстановление порядка верхнего уровня навигации после mkdocs-static-i18n.

Проблема: плагин i18n в folder-режиме распаковывает секцию языка
(`reconfigure_navigation` в folder.py) и ПРИНУДИТЕЛЬНО сортирует верхний
уровень по заголовку (`nav.items.sort(...)`). Из-за этого лента вкладок идёт
по алфавиту, игнорируя порядок из `docs/<lang>/.pages`. Внутри секций порядок
awesome-pages сохраняется — ломается только верхний уровень.

Решение: хук с низким приоритетом (выполняется ПОСЛЕ on_nav плагина i18n)
читает порядок верхних пунктов из `.pages` текущего языка и пересортировывает
`nav.items` под него. Пункты, которых нет в `.pages`, уходят в конец, сохраняя
исходный относительный порядок.
"""

from pathlib import Path

import yaml
from mkdocs.plugins import event_priority

# Маркер для записи `- index.md` (домашняя страница: её заголовок берётся из H1
# и не совпадает с именем файла, поэтому матчим по факту "это index верхнего уровня").
_HOME = "\x00home\x00"


def _top_level_labels(pages_file: Path):
    """Список меток верхнего уровня из .pages в порядке объявления."""
    try:
        data = yaml.safe_load(pages_file.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    nav = data.get("nav")
    if not isinstance(nav, list):
        return []
    labels = []
    for entry in nav:
        if isinstance(entry, str):
            labels.append(_HOME if entry.lower().endswith("index.md") else entry)
        elif isinstance(entry, dict) and entry:
            labels.append(next(iter(entry)))  # ключ группы/страницы
    return labels


def _is_home(item) -> bool:
    file = getattr(item, "file", None)
    if getattr(item, "is_page", False) and file is not None:
        src = file.src_uri
        return src.endswith("index.md") and src.count("/") <= 1
    return False


@event_priority(-100)  # после i18n и awesome-pages
def on_nav(nav, config, files):
    i18n = None
    plugins = config.get("plugins")
    if plugins is not None:
        i18n = plugins.get("i18n")
    if i18n is None:
        return nav
    lang = getattr(i18n, "current_language", None) or getattr(i18n, "default_language", None)
    if not lang:
        return nav

    labels = _top_level_labels(Path(config["docs_dir"]) / lang / ".pages")
    if not labels:
        return nav

    def rank(item):
        key = _HOME if _is_home(item) else item.title
        try:
            return labels.index(key)
        except ValueError:
            return len(labels)  # неизвестные — в конец, стабильно

    nav.items.sort(key=rank)
    return nav
