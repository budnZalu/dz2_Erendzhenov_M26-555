"""Имена файлов, допустимые типы и команды консольной базы данных."""

DATA_DIR = "data"
SUPPORTED_TYPES = {"int": int, "str": str, "bool": bool}
CRUD_COMMANDS = {"insert", "select", "update", "delete", "info"}
TEMP_TOKEN_BYTES = 8  # Случайный суффикс временного файла: 16 hex-символов.

METADATA_FILE = "db_meta.json"
COMMANDS = {
    "create_table": (
        "create_table <имя_таблицы> <столбец1:тип> <столбец2:тип> ...",
        "создать таблицу",
    ),
    "list_tables": ("list_tables", "показать список всех таблиц"),
    "drop_table": ("drop_table <имя_таблицы>", "удалить таблицу и её данные"),
    "insert": ("insert into <таблица> values (<значение1>, ...)", "создать запись"),
    "select": (
        "select from <таблица> [where <столбец> = <значение>]",
        "прочитать записи",
    ),
    "update": (
        "update <таблица> set <столбец> = <значение> where <столбец> = <значение>",
        "обновить записи",
    ),
    "delete": (
        "delete from <таблица> where <столбец> = <значение>",
        "удалить записи",
    ),
    "info": ("info <таблица>", "структура таблицы и количество записей"),
    "exit": ("exit", "выход из программы"),
    "help": ("help", "справочная информация"),
}
