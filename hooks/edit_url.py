"""
mkdocs hook: переписывает page.edit_url для страниц из продуктовых репо.

Раскладка на сайте: docs/<lang>/<mount>/<rest>.md, где <mount> — вложенный
mount-путь репо (напр. `development/core`). В исходном репо тот же файл лежит
как docs/<lang>/<rest>.md. PR открывается в ветку EDIT_BRANCH этого репо.

Страницы САМОГО движка (лендинг, обложки групп, community/license) под mount не
попадают — для них edit_url не трогаем, работает дефолтный edit_uri движка.

С mkdocs-static-i18n (docs_structure: folder) src_path сохраняет префикс
локали: parts[0] — язык, дальше — mount + путь внутри репо.

Добавил репо в rebuild.sh — допиши строку в REPO_MAP (ключ = mount-путь).
"""
import logging

log = logging.getLogger("mkdocs.hooks.edit_url")

# Ключ = mount-путь на сайте (как в rebuild.sh), значение = owner/repo на GitHub.
REPO_MAP = {
    "development/core": "pavluchenkor/idryer-core",
    "development/byod": "pavluchenkor/Build-Your-Own-iDryer",
}

EDIT_BRANCH = "main"


def _compute_edit_url(page):
    src = page.file.src_path.replace("\\", "/")
    parts = src.split("/")
    if len(parts) < 2:
        return None
    lang, tail = parts[0], "/".join(parts[1:])
    # Самый длинный подходящий mount-префикс (на случай вложенности).
    for mount in sorted(REPO_MAP, key=len, reverse=True):
        if tail == mount or tail.startswith(mount + "/"):
            repo = REPO_MAP[mount]
            inside = tail[len(mount):].lstrip("/")
            return f"https://github.com/{repo}/edit/{EDIT_BRANCH}/docs/{lang}/{inside}"
    return None


def on_page_context(context, page, config, nav):
    try:
        url = _compute_edit_url(page)
        if url is not None:  # иначе оставляем дефолтный edit_url движка
            page.edit_url = url
            context["page"] = page
    except Exception as e:
        log.warning("edit_url hook failed for %s: %s", page.file.src_path, e)
    return context
