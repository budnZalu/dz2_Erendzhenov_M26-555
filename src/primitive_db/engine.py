"""Интерфейс базы данных: команды, вывод таблиц и сохранение изменений."""

import shlex

import prompt
from prettytable import PrettyTable

from primitive_db.constants import (
    COMMANDS,
    CRUD_COMMANDS,
    ID_COLUMN,
    ID_DEFINITION,
    METADATA_FILE,
)
from primitive_db.core import (
    create_table,
    delete,
    drop_table,
    insert,
    select,
    update,
)
from primitive_db.decorators import handle_db_errors
from primitive_db.parser import parse_command
from primitive_db.utils import (
    ensure_table_data_absent,
    load_metadata,
    load_table_data,
    save_metadata,
    save_table_data,
    save_table_removal,
)
from primitive_db.validation import get_schema, validate_clause, validate_table_data


def print_help() -> None:
    """Показать команды управления таблицами и данными."""
    print("\n***База данных***\n\nФункции:")
    for usage, description in COMMANDS.values():
        print(f"<command> {usage} - {description}")
    print("\nТипы: int, str, bool. Строки — в кавычках; bool — true или false.")
    print(
        f"{ID_DEFINITION} генерируется автоматически; в insert его передавать не нужно."
    )
    print("Удаление таблиц и записей требует подтверждения: y — да, иначе отмена.\n")


def print_table(schema, rows):
    """Вывести записи в порядке столбцов схемы, включая пустой результат."""
    table = PrettyTable()
    table.field_names = list(schema)
    table.add_rows([[row[column] for column in schema] for row in rows])
    print(table)
    if not rows:
        print("Записей не найдено.")


@handle_db_errors
def execute_crud(metadata, parsed):
    """Загрузить данные, выполнить CRUD и сообщить об успехе после записи."""
    command = parsed["command"]
    table_name = parsed["table_name"]
    schema = get_schema(metadata, table_name)
    table_data = load_table_data(table_name)
    validate_table_data(schema, table_data)
    where_clause = parsed.get("where_clause")
    if where_clause is not None:
        validate_clause(schema, where_clause)

    if command == "info":
        print(f"Таблица: {table_name}")
        print(f"Столбцы: {', '.join(metadata[table_name])}")
        print(f"Количество записей: {len(table_data)}")
    elif command == "select":
        rows = select(table_data, where_clause)
        if rows is not None:
            print_table(schema, rows)
    elif command == "insert":
        table_data = insert(metadata, table_name, parsed["values"], table_data)
        if table_data is None:
            return
        save_table_data(table_name, table_data)
        print(
            f"Запись с {ID_COLUMN}={table_data[-1][ID_COLUMN]} "
            f'успешно добавлена в таблицу "{table_name}".'
        )
    else:
        if command == "update":
            validate_clause(schema, parsed["set_clause"], updating=True)
        matched = select(table_data, where_clause)
        if matched is None:
            return
        if not matched:
            print("Записей не найдено.")
            return
        if command == "update":
            result = update(table_data, parsed["set_clause"], where_clause)
        else:
            result = delete(table_data, where_clause)
        if result is None:
            return
        save_table_data(table_name, result)
        for row in matched:
            if command == "update":
                print(
                    f'Запись с {ID_COLUMN}={row[ID_COLUMN]} в таблице "{table_name}" '
                    "успешно обновлена."
                )
            else:
                print(
                    f"Запись с {ID_COLUMN}={row[ID_COLUMN]} успешно удалена "
                    f'из таблицы "{table_name}".'
                )


@handle_db_errors
def execute_table_command(metadata, command, arguments):
    """Выполнить команду управления таблицами и сохранить схему."""
    if command == "list_tables":
        if not metadata:
            print("Таблиц пока нет.")
        for table_name in sorted(metadata):
            print(f"- {table_name}")
        return

    previous_metadata = metadata.copy()
    updated_metadata = metadata.copy()
    table_name = arguments[0]
    if command == "create_table":
        result = create_table(updated_metadata, table_name, arguments[1:])
    else:
        get_schema(metadata, table_name)
        result = drop_table(updated_metadata, table_name)
    if result is None:
        return

    if command == "create_table":
        ensure_table_data_absent(table_name)
        save_metadata(METADATA_FILE, updated_metadata)
    else:
        save_table_removal(
            METADATA_FILE, previous_metadata, updated_metadata, table_name
        )
    metadata.clear()
    metadata.update(updated_metadata)

    if command == "create_table":
        columns = ", ".join(metadata[table_name])
        print(f'Таблица "{table_name}" успешно создана со столбцами: {columns}')
    else:
        print(f'Таблица "{table_name}" успешно удалена.')


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
        if not user_input.strip():
            continue

        try:
            parsed = None
            if user_input.split(maxsplit=1)[0] in CRUD_COMMANDS:
                parsed = parse_command(user_input)
                command = parsed["command"]
            else:
                args = shlex.split(user_input)
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
                    print(f"Использование: {COMMANDS[command][0]}")
                    continue
        except ValueError as error:
            print(f"Некорректное значение: {user_input}. Попробуйте снова. {error}")
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

        if parsed is not None:
            execute_crud(metadata, parsed)
        else:
            execute_table_command(metadata, command, arguments)
