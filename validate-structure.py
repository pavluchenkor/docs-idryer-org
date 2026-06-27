#!/usr/bin/env python3
"""Проверяет совпадение структуры docs/ между языками.

Использование:
    python3 validate-structure.py docs/              # все языки
    python3 validate-structure.py docs/ru/projects   # конкретный путь
"""

import sys
from pathlib import Path

def get_structure(path):
    """Получить список папок в пути (исключая dot-файлы)."""
    if not path.exists():
        return set()
    return {d.name for d in path.iterdir() if d.is_dir() and not d.name.startswith('.')}

def validate_language_pair(docs_path, lang1, lang2):
    """Сравнить структуру двух языков."""
    struct1 = get_structure(docs_path / lang1)
    struct2 = get_structure(docs_path / lang2)

    if struct1 == struct2:
        return True, None

    missing = struct1 - struct2
    extra = struct2 - struct1

    msg = f"  {lang1} vs {lang2}: "
    if missing:
        msg += f"в {lang2} не хватает {sorted(missing)}; "
    if extra:
        msg += f"в {lang2} лишние {sorted(extra)}"

    return False, msg

def main():
    if len(sys.argv) < 2:
        path = Path("docs")
    else:
        path = Path(sys.argv[1])

    if not path.exists():
        print(f"❌ Путь не найден: {path}")
        return 1

    # Найти языки (исключить служебные папки)
    SKIP_DIRS = {'img', 'imgweb', 'assets', 'CAD', 'KiCad', 'PDF', 'Schematics'}
    languages = sorted([d.name for d in path.iterdir()
                       if d.is_dir() and not d.name.startswith('.') and d.name not in SKIP_DIRS])

    if len(languages) < 2:
        print(f"⚠️  Найден только один язык: {languages}")
        return 0

    print(f"📄 Проверка структуры: {path}")
    print(f"   Языки: {languages}\n")

    base_lang = languages[0]
    base_structure = get_structure(path / base_lang)
    print(f"   Базовый ({base_lang}): {sorted(base_structure)}")

    errors = []
    for lang in languages[1:]:
        ok, msg = validate_language_pair(path, base_lang, lang)
        if not ok:
            errors.append(msg)
            print(f"   ❌ {msg}")
        else:
            print(f"   ✅ {lang}: OK")

    print()
    if not errors:
        print("✅ Структура совпадает во всех языках!")
        return 0
    else:
        print(f"❌ Найдено {len(errors)} различий")
        return 1

if __name__ == "__main__":
    sys.exit(main())
