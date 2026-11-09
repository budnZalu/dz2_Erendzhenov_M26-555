"""Создание и удаление таблиц в словаре метаданных."""

SUPPORTED_TYPES = {"int", "str", "bool"}


def normalize_columns(columns):
    """Проверить столбцы и поставить единственный ID:int первым."""
    if not columns:
        raise ValueError(
            "Некорректное значение: пустой список столбцов. Попробуйте снова."
        )

    names = set()
    result = ["ID:int"]
    for column in columns:
        name, separator, data_type = column.partition(":")
        if (
            not separator
            or not name.isidentifier()
            or data_type not in SUPPORTED_TYPES
            or name in names
            or (name == "ID" and data_type != "int")
        ):
            raise ValueError(f"Некорректное значение: {column}. Попробуйте снова.")
        names.add(name)
        if name != "ID":
            result.append(column)
    return result


def create_table(metadata, table_name, columns):
    """Добавить таблицу; при ошибке вывести сообщение и сохранить метаданные."""
    if not table_name.isidentifier():
        print(f"Некорректное значение: {table_name}. Попробуйте снова.")
        return metadata
    if table_name in metadata:
        print(f'Ошибка: Таблица "{table_name}" уже существует.')
        return metadata

    try:
        normalized = normalize_columns(columns)
    except ValueError as error:
        print(error)
        return metadata

    metadata[table_name] = normalized
    return metadata


def drop_table(metadata, table_name):
    """Удалить таблицу; при ошибке вывести сообщение и сохранить метаданные."""
    if not table_name.isidentifier():
        print(f"Некорректное значение: {table_name}. Попробуйте снова.")
    elif table_name not in metadata:
        print(f'Ошибка: Таблица "{table_name}" не существует.')
    else:
        del metadata[table_name]
    return metadata
