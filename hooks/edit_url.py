"""
mkdocs hook: переписывает page.edit_url для страниц из продуктовых репо.

Раскладка на сайте: docs/<lang>/<mount>/<rest>.md, где <mount> — вложенный
mount-путь репо (напр. `development/core`, `projects/idryer/x`). В исходном репо
тот же файл лежит как docs/<lang>/<rest>.md. Кнопка «edit» должна вести в ЭТОТ
продуктовый репо на исходный путь, а не в движок.

Карта mount→репо берётся ИЗ repos.yml (как в asset_links.py) — не дублируем
список руками: подключил репо в repos.yml → edit-ссылка для него заработала сама.

Страницы САМОГО движка (лендинг, обложки групп, community/license) под mount не
попадают — для них edit_url не трогаем, работает дефолтный edit_uri движка.
"""
import logging
import os

try:
    import yaml
except ImportError:
    yaml = None

log = logging.getLogger("mkdocs.hooks.edit_url")

EDIT_BRANCH = "main"

_REPO_MAP = None  # кэш: mount-путь → "owner/repo"


def _slug_from_url(url: str) -> str:
    """https://github.com/owner/repo.git → owner/repo."""
    slug = url.strip().rsplit("github.com/", 1)[-1]
    if slug.endswith(".git"):
        slug = slug[:-4]
    return slug.strip("/")


def _load_repo_map(config) -> dict:
    global _REPO_MAP
    if _REPO_MAP is not None:
        return _REPO_MAP
    m = {}
    try:
        if yaml is None:
            raise RuntimeError("pyyaml не установлен")
        cfg_path = (config.get("config_file_path") or "mkdocs.yml").replace("\\", "/")
        path = os.path.join(os.path.dirname(cfg_path), "repos.yml")
        data = yaml.safe_load(open(path, encoding="utf-8")) or {}
        for r in (data.get("repos") or []):
            mount = str(r.get("mount", "")).strip().strip("/")
            slug = _slug_from_url(str(r.get("url", "")))
            if mount and slug:
                m[mount] = slug
    except Exception as e:
        log.warning("edit_url: не прочитал repos.yml: %s", e)
        m = {}
    _REPO_MAP = m
    return m


def _compute_edit_url(page, config):
    src = page.file.src_path.replace("\\", "/")
    parts = src.split("/")
    if len(parts) < 2:
        return None
    lang, tail = parts[0], "/".join(parts[1:])
    repo_map = _load_repo_map(config)
    # самый длинный подходящий mount-префикс (вложенные пути)
    for mount in sorted(repo_map, key=len, reverse=True):
        if tail == mount or tail.startswith(mount + "/"):
            repo = repo_map[mount]
            inside = tail[len(mount):].lstrip("/")
            return f"https://github.com/{repo}/edit/{EDIT_BRANCH}/docs/{lang}/{inside}"
    return None


def on_page_context(context, page, config, nav):
    try:
        url = _compute_edit_url(page, config)
        if url is not None:  # иначе оставляем дефолтный edit_url движка
            page.edit_url = url
            context["page"] = page
    except Exception as e:
        log.warning("edit_url hook failed for %s: %s", page.file.src_path, e)
    return context
