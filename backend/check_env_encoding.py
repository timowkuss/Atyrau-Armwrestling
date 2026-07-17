"""
Находит байты, которые не являются валидным UTF-8, в вашем .env файле.
Не печатает сам пароль/секреты целиком — только байты вокруг проблемы.

Запуск:
    python check_env_encoding.py путь\к\.env

Если путь не указан, ищет .env в той же папке, где лежит скрипт.
"""
import sys
from pathlib import Path

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".env")

if not path.exists():
    print(f"Файл не найден: {path.resolve()}")
    sys.exit(1)

raw = path.read_bytes()
print(f"Файл: {path.resolve()}")
print(f"Размер: {len(raw)} байт")

# Проверка на BOM
if raw.startswith(b"\xef\xbb\xbf"):
    print("! Обнаружен UTF-8 BOM в начале файла — это может ломать парсинг некоторых .env-загрузчиков.")

try:
    raw.decode("utf-8")
    print("Файл целиком является валидным UTF-8 — проблема НЕ в кодировке файла как таковой.")
    print("Возможно, битые байты добавляются позже — при склейке строки подключения в коде,")
    print("или переменная окружения берётся из другого места (системная переменная Windows, docker-compose и т.п.)")
except UnicodeDecodeError as e:
    print(f"\n!!! НАЙДЕНА ПРОБЛЕМА: {e}")
    start = max(0, e.start - 20)
    end = min(len(raw), e.end + 20)
    context = raw[start:end]

    # Определяем, на какой строке и в каком примерно поле это находится
    line_no = raw[:e.start].count(b"\n") + 1
    line_start = raw.rfind(b"\n", 0, e.start) + 1
    line_end = raw.find(b"\n", e.start)
    if line_end == -1:
        line_end = len(raw)
    key = raw[line_start:line_end].split(b"=", 1)[0].decode("ascii", errors="replace")

    print(f"Строка №{line_no}, переменная: {key}")
    print(f"Байты вокруг проблемы (hex): {context.hex(' ')}")
    print(f"Проблемный байт: 0x{raw[e.start]:02x} на позиции {e.start}")
    print("\nЭто похоже на символ, сохранённый не в UTF-8 (например Windows-1251/1252),")
    print("или спецсимвол (длинное тире, «умные» кавычки, неразрывный пробел),")
    print(f"случайно попавший в значение переменной '{key}'.")
    print("\nЧто делать: откройте .env в VS Code / Notepad++, найдите эту переменную,")
    print("удалите и заново вручную наберите её значение обычными ASCII-символами,")
    print("затем сохраните файл в кодировке UTF-8 (без BOM).")
