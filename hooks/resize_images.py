"""
MkDocs hook: ресайз картинок до макс. 2000px по большей стороне.

Зачем:
  Авторы кладут картинки как есть (могут быть 4000+px). Для веба это лишний
  вес. Уменьшаем до 2000px по большей стороне с сохранением пропорций
  (Pillow.thumbnail — то же, что делал старый плагин resize-images, но без
  отдельной папки imgweb и без коммита служебных копий).

Когда:
  on_pre_build — ДО копирования в site и ДО плагина optimize, чтобы сначала
  ресайз, потом сжатие.

Гейт по CI:
  Работает только при серверной сборке (env CI), как и optimize. На сервере
  docs_dir — эфемерный checkout центрального репо (правка безопасна). Локально
  (CI не задан) хук пропускается, чтобы не менять реальные исходники.

Идемпотентно: картинки, у которых обе стороны ≤2000, пропускаются.
SVG/GIF не трогаем (вектор / возможная анимация).
"""
import logging
import os

log = logging.getLogger("mkdocs.hooks.resize_images")

MAX_SIDE = 2000
EXTS = (".png", ".jpg", ".jpeg", ".webp")


def on_pre_build(config):
    if not os.environ.get("CI"):
        return
    try:
        from PIL import Image
    except ImportError:
        log.warning("resize_images: Pillow не установлен — пропуск")
        return

    docs_dir = config["docs_dir"]
    resized = 0
    for root, _dirs, files in os.walk(docs_dir):
        for name in files:
            if not name.lower().endswith(EXTS):
                continue
            path = os.path.join(root, name)
            try:
                with Image.open(path) as img:
                    if max(img.size) <= MAX_SIDE:
                        continue
                    fmt = img.format
                    img.thumbnail((MAX_SIDE, MAX_SIDE))
                    img.save(path, format=fmt)
                    resized += 1
            except Exception as e:
                log.warning("resize_images: не удалось обработать %s: %s", path, e)

    if resized:
        log.info("resize_images: уменьшено %d картинок до ≤%dpx", resized, MAX_SIDE)
