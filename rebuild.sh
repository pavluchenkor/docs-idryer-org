#!/bin/bash
set -euo pipefail

# ── Очередь сборок (защита от параллельных запусков) ─────────────────────────
# Две сборки одновременно делят /build и /tmp/site-out и бьют друг друга.
# Очередь глубиной 1: одна сборка идёт; ОДИН следующий запрос ждёт её завершения;
# любые запросы, пришедшие пока кто-то уже ждёт, схлопываются (всё равно
# следующая сборка возьмёт самые свежие изменения из всех репо).
#   fd 9 = «идёт сборка», fd 8 = «место в очереди».
exec 9>/tmp/rebuild.run.lock
exec 8>/tmp/rebuild.queue.lock
if flock -n 9; then
  :                                   # сборок нет — собираем сразу
elif flock -n 8; then
  echo "[$(date -Iseconds)] rebuild: идёт сборка — встаю в очередь (жду)"
  flock 9                             # ждём завершения текущей (это и есть очередь)
  flock -u 8                          # освободить место → следующий сможет встать
else
  echo "[$(date -Iseconds)] rebuild: сборка уже идёт и одна в очереди — схлопываю запрос"
  exit 0
fi
# Здесь держим fd 9 до конца скрипта → следующая сборка не стартует параллельно.

WORKDIR=/build
OUTPUT=/output
CENTRAL_REPO_URL="https://github.com/pavluchenkor/docs-idryer-org.git"
CENTRAL_DIR="docs-idryer-org"
CENTRAL_BRANCH="main"

# Языки сайта. Добавить новый язык = дописать сюда одну строку + завести
# подпапку с тем же кодом в продуктовом репо (docs/<lang>/...) и в центральном
# (docs/<lang>/...). mkdocs-static-i18n в mkdocs.yml тоже должен знать про язык.
LANGUAGES=("ru" "en" "de" "fr" "es" "cs" "ja" "pt" "pt-BR" "zh" "zh-Hant")

# Конвенция: сайт тянет ТОЛЬКО ветку `docs-publish` из каждого продуктового репо
# Чтобы опубликовать правки — нужно явно слить/запушить в
# `docs-publish`. Работа идёт в master/feat-ветках, prod-сайт не шевелится, пока
# автор сам не «откроет кран».

# Карта продуктовых репо → разделы сайта задаётся в repos.yml (читается ниже,
# после клона центрального репо). Это единственное место правки — список репо
# в скрипте больше не хранится. Sparse-checkout тянет только docs/ и asset-папки.

# Экспериментальная возможность: внешние папки рядом с `docs/` в продуктовом
# репозитории. Если папки нет — сборка просто пропускает её.
#
# Пример в продуктовом репо:
#   docs/ru/README.md
#   CAD/enclosure.step
#
# На сайте будет:
#   /assets/<repo-key>/CAD/enclosure.step
#
# GitHub-ссылки вида ../../CAD/enclosure.step переписывает hook
# hooks/asset_links.py при mkdocs build.
EXTRA_ASSET_DIRS=("CAD" "KiCad" "PDF" "Schematics")

mkdir -p "$WORKDIR"
cd "$WORKDIR"

# Базовый язык — первый в списке (ru). Остальные языки проверяются на совместимость
# структуры папок с базовым перед копированием. Документация ведётся на русском.
BASE_LANG="${LANGUAGES[0]}"

# Полный clone для центрального репо (он маленький и нужен целиком).
# Reset на FETCH_HEAD, а не на origin/$branch — это работает даже если
# в кэш-volume осталась папка от клона с другой ветки (shallow fetch
# не создаёт remote-tracking ref для новой ветки автоматически).
clone_or_update() {
  local url="$1" dir="$2" branch="${3:-docs-publish}"
  if [ -d "$dir/.git" ]; then
    git -C "$dir" fetch --depth=1 origin "$branch"
    git -C "$dir" reset --hard FETCH_HEAD
    git -C "$dir" clean -fdx  # убрать stray-файлы (удалённые в origin), иначе тащим из кэша
  else
    rm -rf "$dir"
    git clone --depth=1 --branch "$branch" "$url" "$dir"
  fi
}

# Sparse clone для продуктовых: тянем только указанные подпапки.
clone_or_update_sparse() {
  local url="$1" dir="$2" branch="$3"
  shift 3
  local subpaths=("$@")
  if [ -d "$dir/.git" ]; then
    git -C "$dir" sparse-checkout set "${subpaths[@]}"
    git -C "$dir" fetch --depth=1 origin "$branch"
    git -C "$dir" reset --hard FETCH_HEAD
    git -C "$dir" clean -fdx  # убрать stray-файлы (удалённые в origin), иначе тащим из кэша
  else
    rm -rf "$dir"
    git clone --depth=1 --filter=blob:none --sparse --branch "$branch" "$url" "$dir"
    git -C "$dir" sparse-checkout set "${subpaths[@]}"
  fi
}

echo "[$(date -Iseconds)] rebuild: fetch central (${CENTRAL_DIR}, branch: ${CENTRAL_BRANCH})"
clone_or_update "$CENTRAL_REPO_URL" "$CENTRAL_DIR" "$CENTRAL_BRANCH"

# Карта репо → разделы из repos.yml (в центральном репо). Парсим в строки
# "mount<TAB>url<TAB>branch". mount может быть вложенным (projects/idryer/unit).
CONFIG="${CENTRAL_DIR}/repos.yml"
REPO_LINES=()
while IFS= read -r _cfg_line; do
  REPO_LINES+=("$_cfg_line")
done < <(
  python3 - "$CONFIG" <<'PY'
import sys, yaml
data = yaml.safe_load(open(sys.argv[1])) or {}
for r in (data.get("repos") or []):
    mount = str(r.get("mount", "")).strip().strip("/")
    url = str(r.get("url", "")).strip()
    branch = str(r.get("branch") or "docs-publish").strip()
    if mount and url:
        print("\t".join([mount, url, branch]))
PY
)

# Плоское имя из mount-пути: projects/idryer/unit -> projects_idryer_unit.
flat_name() { printf '%s' "$1" | tr '/' '_'; }

# Множества активных mount-путей и плоских ключей — для прунинга.
declare -A ACTIVE_MOUNTS=()
declare -A ACTIVE_FLAT=()
for line in "${REPO_LINES[@]}"; do
  IFS=$'\t' read -r m_mount _m_url _m_branch <<<"$line"
  ACTIVE_MOUNTS["$m_mount"]=1
  ACTIVE_FLAT["$(flat_name "$m_mount")"]=1
done

# Прунинг контента: каждой смонтированной папке скрипт кладёт метку .mounted.
# Удаляем только помеченные папки, которых больше нет в repos.yml. Папки-группы
# (projects/development/wiki), обложки index.md, .pages, общие img/ — метки не
# имеют и НЕ удаляются. Так прунинг работает с вложенными mount-путями и не
# сносит группы.
for lang in "${LANGUAGES[@]}"; do
  docroot="${CENTRAL_DIR}/docs/${lang}"
  [ -d "$docroot" ] || continue
  while IFS= read -r marker; do
    d="$(dirname "$marker")"
    mount="${d#"$docroot"/}"
    if [[ -z "${ACTIVE_MOUNTS[$mount]+x}" ]]; then
      echo "[prune] docs/${lang}/${mount} — нет в repos.yml, удаляю"
      rm -rf "$d"
    fi
  done < <(find "$docroot" -type f -name '.mounted' 2>/dev/null)
done

# Прунинг внешних asset-папок (ключ = плоское имя mount-пути).
asset_root="${CENTRAL_DIR}/docs/assets"
if [ -d "$asset_root" ]; then
  for d in "$asset_root"/*/; do
    [ -d "$d" ] || continue
    name="$(basename "$d")"
    if [[ -z "${ACTIVE_FLAT[$name]+x}" ]]; then
      echo "[prune] docs/assets/${name} — нет в repos.yml, удаляю"
      rm -rf "$d"
    fi
  done
fi

for line in "${REPO_LINES[@]}"; do
  IFS=$'\t' read -r mount url branch <<<"$line"
  flat="$(flat_name "$mount")"
  src="src_${flat}"
  sparse_paths=("docs" "${EXTRA_ASSET_DIRS[@]}")
  echo "[$(date -Iseconds)] rebuild: fetch ${mount} (sparse: ${sparse_paths[*]}, branch: ${branch})"
  if ! clone_or_update_sparse "$url" "$src" "$branch" "${sparse_paths[@]}"; then
    echo "[warn] не удалось получить ${mount}, пропуск" >&2
    continue
  fi
  # Раскладываем docs/<lang>/ продуктового репо в docs/<lang>/<mount>/ центрального,
  # чтобы mkdocs-static-i18n нашёл каждую локаль в ожидаемом месте.
  for lang in "${LANGUAGES[@]}"; do
    # mkdocs i18n (docs_structure: folder) сопоставляет переводы по совпадению путей:
    # docs/en/<path>.md ↔ docs/<lang>/<path>.md. Если имена папок между языками не
    # совпадают, i18n не свяжет файлы и создаст дублирующий раздел. Проверяем заранее.
    if [ "$lang" != "$BASE_LANG" ] && \
       [ -d "${src}/docs/${BASE_LANG}" ] && \
       [ -d "${src}/docs/${lang}" ]; then
      base_dirs=$(find "${src}/docs/${BASE_LANG}" -maxdepth 1 -mindepth 1 -type d -printf '%f\n' | sort)
      lang_dirs=$(find "${src}/docs/${lang}" -maxdepth 1 -mindepth 1 -type d -printf '%f\n' | sort)
      if [ "$base_dirs" != "$lang_dirs" ]; then
        echo "[warn] ${mount}: docs/${lang}/ имеет другие имена папок чем docs/${BASE_LANG}/ — пропуск; i18n fallback на ${BASE_LANG}" >&2
        continue
      fi
    fi
    target="${CENTRAL_DIR}/docs/${lang}/${mount}"
    rm -rf "$target"
    mkdir -p "$target"
    if [ -d "${src}/docs/${lang}" ]; then
      cp -a "${src}/docs/${lang}/." "$target/"
      touch "${target}/.mounted"   # метка для прунинга (mkdocs игнорирует dot-файлы)
    else
      echo "[warn] ${src}/docs/${lang} нет — у ${mount} нет перевода на ${lang}" >&2
    fi
  done
  # Общие картинки: docs/img/ продуктового репо → docs/img/ центрального сайта.
  if [ -d "${src}/docs/img" ]; then
    mkdir -p "${CENTRAL_DIR}/docs/img"
    cp -a "${src}/docs/img/." "${CENTRAL_DIR}/docs/img/"
  fi
  # Корневые asset-папки (CAD/PDF/...) → docs/assets/<flat>/
  repo_asset_root="${CENTRAL_DIR}/docs/assets/${flat}"
  rm -rf "$repo_asset_root"
  for asset_dir in "${EXTRA_ASSET_DIRS[@]}"; do
    if [ -d "${src}/${asset_dir}" ]; then
      mkdir -p "${repo_asset_root}/${asset_dir}"
      cp -a "${src}/${asset_dir}/." "${repo_asset_root}/${asset_dir}/"
    fi
  done
done

echo "[$(date -Iseconds)] rebuild: mkdocs build"
rm -rf /tmp/site-out
cd "$CENTRAL_DIR"
# Кэш плагина optimize (.cache/plugin/optimize) на ПОВТОРНОЙ сборке попадает в
# коллекцию файлов mkdocs и optimize падает (files.remove … not in collection).
# Чистим кэш перед сборкой — каждая сборка идёт «как первая».
find . -depth -type d -name .cache -exec rm -rf {} + 2>/dev/null || true
# CI=true включает плагин optimize (см. mkdocs.yml: enabled: !ENV [CI, false]) —
# сжатие PNG/JPG только при серверной сборке; локально optimize выключен.
# PYTHONUNBUFFERED + stdbuf — вывод идёт построчно в реальном времени,
# чтобы `docker logs -f` показывал прогресс сборки, а не выдавал всё пачкой в конце.
CI=true PYTHONUNBUFFERED=1 stdbuf -oL -eL mkdocs build --clean --site-dir /tmp/site-out

echo "[$(date -Iseconds)] rebuild: sync to output"
rsync -a --delete /tmp/site-out/ "$OUTPUT/"
rm -rf /tmp/site-out

echo "[$(date -Iseconds)] rebuild: validate nav"
python3 /app/check-nav.py "$CENTRAL_DIR/docs/" 2>&1 | sed "s/^/[validate] /" || true

echo "[$(date -Iseconds)] rebuild: done"
