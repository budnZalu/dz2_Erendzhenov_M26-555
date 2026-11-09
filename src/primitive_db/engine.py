"""Основной цикл базы данных, разбор команд и сохранение изменений."""

import shlex

import prompt

from primitive_db.core import create_table, drop_table
from primitive_db.utils import load_metadata, save_metadata

METADATA_FILE = "db_meta.json"
COMMANDS = {
    "create_table": "create_table <имя_таблицы> <столбец1:тип> <столбец2:тип> ...",
    "list_tables": "list_tables",
    "drop_table": "drop_table <имя_таблицы>",
    "exit": "exit",
    "help": "help",
}


def print_help() -> None:
    """Показать доступные команды."""
    print("\n***База данных***\n\nФункции:")
    descriptions = {
        "create_table": "создать таблицу",
        "list_tables": "показать список всех таблиц",
        "drop_table": "удалить таблицу",
        "exit": "выход из программы",
        "help": "справочная информация",
    }
    for command, usage in COMMANDS.items():
        print(f"<command> {usage} - {descriptions[command]}")
    print("\nТипы данных: int, str, bool. Столбец ID:int добавляется автоматически.\n")


def run() -> None:
    """Загружать актуальные метаданные и выполнять команды пользователя."""
    print_help()

    while True:
        metadata_error = None
        try:
            metadata = load_metadata(METADATA_FILE)
        except (OSError, ValueError) as error:
            metadata_error = error

        try:
            user_input = prompt.string(">>>Введите команду: ", empty=True) or ""
        except (EOFError, KeyboardInterrupt):
            print("\nВыход из программы.")
            return

        try:
            args = shlex.split(user_input)
        except ValueError:
            print(f"Некорректное значение: {user_input}. Попробуйте снова.")
            continue
        if not args:
            continue

        command, *arguments = args
        if command not in COMMANDS:
            print(f"Функции {command} нет. Попробуйте снова.")
            continue
        valid_arguments = (
            (command == "create_table" and len(arguments) >= 2)
            or (command == "drop_table" and len(arguments) == 1)
            or (command in {"list_tables", "help", "exit"} and not arguments)
        )
        if not valid_arguments:
            print(f"Некорректное значение: {user_input}. Попробуйте снова.")
            print(f"Использование: {COMMANDS[command]}")
            continue

        if command == "help":
            print_help()
            continue
        if command == "exit":
            print("Выход из программы.")
            return
        if metadata_error is not None:
            print(f"Ошибка чтения {METADATA_FILE}: {metadata_error}")
            print("Исправьте файл метаданных и повторите команду.")
            continue

        if command == "list_tables":
            if not metadata:
                print("Таблиц пока нет.")
            for table_name in sorted(metadata):
                print(f"- {table_name}")
            continue

        previous_metadata = metadata.copy()
        table_name = arguments[0]
        if command == "create_table":
            create_table(metadata, table_name, arguments[1:])
        else:
            drop_table(metadata, table_name)
        if metadata == previous_metadata:
            continue

        try:
            save_metadata(METADATA_FILE, metadata)
        except OSError as error:
            print(f"Ошибка сохранения {METADATA_FILE}: {error}")
            continue

        if command == "create_table":
            columns = ", ".join(metadata[table_name])
            print(f'Таблица "{table_name}" успешно создана со столбцами: {columns}')
        else:
            print(f'Таблица "{table_name}" успешно удалена.')
