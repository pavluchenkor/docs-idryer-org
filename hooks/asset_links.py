"""
MkDocs hook: переписывает ссылки на ассеты продуктового репо под структуру сайта.

Зачем: автор пишет ЕСТЕСТВЕННЫЕ относительные ссылки (они работают в превью и на
GitHub), а на сайте раздел смонтирован глубже (docs/<lang>/<mount>/...), из-за чего
относительный путь промахнулся бы. Хук переписывает такие ссылки при сборке —
автору не нужно думать про глубину mount.

Два случая:

1. Бинарь в корне репо (CAD/KiCad/PDF/Schematics):
     в репо:  docs/ru/page.md -> ../../CAD/enclosure.step
     на сайте: /assets/<repo-key>/CAD/enclosure.step

2. Общие картинки docs/img/ (одна папка на все языки):
     в репо:  docs/ru/<секция>/page.md -> ../../img/<секция>/x.jpg
     на сайте: /img/<секция>/x.jpg   (абсолютный путь, не зависит от mount)
"""
import logging
import posixpath
import re
from urllib.parse import urlsplit, urlunsplit

log = logging.getLogger("mkdocs.hooks.asset_links")

DEFAULT_ASSET_DIRS = ("CAD", "KiCad", "PDF", "Schematics")

LINK_RE = re.compile(r"(!?\[[^\]]*?\]\()([^)#?\s]+)((?:[?#][^)]*)?\))")


def _asset_dirs(config) -> tuple[str, ...]:
    extra = config.get("extra", {}) or {}
    dirs = extra.get("extra_asset_dirs") or DEFAULT_ASSET_DIRS
    return tuple(str(d).strip("/") for d in dirs if str(d).strip("/"))


def _is_external_or_absolute(url: str) -> bool:
    if url.startswith(("/", "#")):
        return True
    parsed = urlsplit(url)
    return bool(parsed.scheme or parsed.netloc)


_MOUNTS_CACHE = None


def _load_mounts(config) -> list:
    """mount-пути из repos.yml (рядом с mkdocs.yml), длинные первыми.

    Нужны, чтобы из пути страницы вычленить вложенный mount
    (development/core, projects/idryer/unit) и плоский ключ репо.
    """
    global _MOUNTS_CACHE
    if _MOUNTS_CACHE is not None:
        return _MOUNTS_CACHE
    mounts = []
    try:
        import yaml
        cfg_path = (config.get("config_file_path") or "mkdocs.yml").replace("\\", "/")
        path = posixpath.join(posixpath.dirname(cfg_path), "repos.yml")
        data = yaml.safe_load(open(path, encoding="utf-8")) or {}
        for r in (data.get("repos") or []):
            m = str(r.get("mount", "")).strip().strip("/")
            if m:
                mounts.append(m)
        mounts.sort(key=lambda m: m.count("/"), reverse=True)
    except Exception:
        mounts = []
    _MOUNTS_CACHE = mounts
    return mounts


def _split_mount(src: str, mounts: list):
    """src = '<lang>/<mount...>/<inner>.md' → (lang, repo_key, inner_parts).

    repo_key — плоское имя mount-пути (projects/idryer/unit → projects_idryer_unit),
    совпадает с ключом папки в docs/assets/. Если mount в repos.yml не найден —
    откат на одно-сегментный ключ (parts[1]) для обратной совместимости.
    """
    parts = src.split("/")
    if len(parts) < 2:
        return None
    lang = parts[0]
    rel = "/".join(parts[1:])
    for m in mounts:
        if rel == m or rel.startswith(m + "/"):
            inner = rel[len(m):].lstrip("/")
            return lang, m.replace("/", "_"), (inner.split("/") if inner else [])
    if len(parts) < 3:
        return None
    return lang, parts[1], parts[2:]


def _rewrite_url(url: str, source_dir: str, repo_key: str, asset_dirs: tuple[str, ...]) -> str:
    if _is_external_or_absolute(url):
        return url

    parsed = urlsplit(url)
    if not parsed.path:
        return url

    # source_dir — путь файла в ИСХОДНОМ продуктовом репо (docs/<lang>/<inner>),
    # относительно которого автор писал ссылку ../../CAD/... для GitHub.
    resolved = posixpath.normpath(posixpath.join(source_dir, parsed.path))

    # Общая папка картинок docs/img/ → абсолютный /img/... .
    # Автор пишет ЕСТЕСТВЕННУЮ ссылку ../../img/<секция>/x.jpg (она верна
    # относительно docs/<lang>/<секция>/ — работает в превью и на GitHub),
    # а на сайте раздел смонтирован глубже (docs/<lang>/<mount>/...), поэтому
    # относительный путь промахнулся бы. Переписываем в абсолютный /img/...,
    # который не зависит от глубины mount. img общий на все репо → без repo_key.
    if resolved == "docs/img" or resolved.startswith("docs/img/"):
        img_rel = resolved[len("docs/img"):].lstrip("/")
        new_path = "/img" + (f"/{img_rel}" if img_rel else "")
        return urlunsplit(("", "", new_path, parsed.query, parsed.fragment))

    for asset_dir in asset_dirs:
        prefix = f"{asset_dir}/"
        if resolved == asset_dir:
            asset_rel = ""
        elif resolved.startswith(prefix):
            asset_rel = resolved[len(prefix):]
        else:
            continue

        new_path = f"/assets/{repo_key}/{asset_dir}"
        if asset_rel:
            new_path = f"{new_path}/{asset_rel}"
        return urlunsplit(("", "", new_path, parsed.query, parsed.fragment))

    return url


def on_page_markdown(markdown, page, config, files):
    try:
        src = page.file.src_path.replace("\\", "/")
        split = _split_mount(src, _load_mounts(config))
        if not split:
            return markdown

        lang, repo_key, inner_parts = split
        source_dir = posixpath.dirname(posixpath.join("docs", lang, *inner_parts))
        asset_dirs = _asset_dirs(config)

        def replace(match):
            before, url, after = match.groups()
            return before + _rewrite_url(url, source_dir, repo_key, asset_dirs) + after

        return LINK_RE.sub(replace, markdown)
    except Exception as e:
        log.warning("asset_links hook failed for %s: %s", page.file.src_path, e)
        return markdown
