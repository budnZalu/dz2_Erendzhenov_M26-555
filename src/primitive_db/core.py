"""Управление схемами таблиц и операции над записями."""

from primitive_db.utils import load_table_data

SUPPORTED_TYPES = {"int": int, "str": str, "bool": bool}


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


def get_schema(metadata, table_name):
    """Получить проверенную схему существующей таблицы."""
    if not table_name.isidentifier():
        raise ValueError(f"Некорректное имя таблицы: {table_name}.")
    if table_name not in metadata:
        raise ValueError(f'Таблица "{table_name}" не существует.')
    columns = metadata[table_name]
    if normalize_columns(columns) != columns:
        raise ValueError(f'Некорректная структура таблицы "{table_name}".')
    return dict(column.split(":") for column in columns)


def validate_clause(schema, clause, *, updating=False):
    """Проверить имена полей и точные типы значений WHERE или SET."""
    for name, value in clause.items():
        if name not in schema:
            raise ValueError(f'Столбец "{name}" не существует.')
        if updating and name == "ID":
            raise ValueError("Изменять ID нельзя: он генерируется автоматически.")
        if type(value) is not SUPPORTED_TYPES[schema[name]]:
            raise ValueError(
                f"Некорректное значение: {value!r}. "
                f'Столбец "{name}" требует тип {schema[name]}.'
            )


def validate_table_data(schema, table_data):
    """Проверить обязательные поля, типы и уникальность сохранённых ID."""
    ids = set()
    for row in table_data:
        if set(row) != set(schema):
            raise ValueError("Запись не соответствует схеме: все поля обязательны.")
        validate_clause(schema, row)
        if row["ID"] <= 0 or row["ID"] in ids:
            raise ValueError(
                "ID в файле данных должны быть положительными и уникальными."
            )
        ids.add(row["ID"])


def insert(metadata, table_name, values, table_data=None):
    """Добавить типизированную запись с новым ID и вернуть данные таблицы."""
    schema = get_schema(metadata, table_name)
    columns = [name for name in schema if name != "ID"]
    if len(values) != len(columns):
        raise ValueError(
            f"Ожидается {len(columns)} значений без ID, получено {len(values)}. "
            "Все поля обязательны."
        )
    record = dict(zip(columns, values))
    validate_clause(schema, record)
    if table_data is None:
        table_data = load_table_data(table_name)
    validate_table_data(schema, table_data)
    new_id = max((row["ID"] for row in table_data), default=0) + 1
    table_data.append({"ID": new_id, **record})
    return table_data


def _matches(row, where_clause):
    """Сравнить значения без смешения bool и int (True не равен 1)."""
    return all(
        name in row and type(row[name]) is type(value) and row[name] == value
        for name, value in where_clause.items()
    )


def select(table_data, where_clause=None):
    """Вернуть все записи или записи, соответствующие условию."""
    return [row for row in table_data if _matches(row, where_clause or {})]


def update(table_data, set_clause, where_clause):
    """Проверить изменения, обновить все совпадения и вернуть данные."""
    if not set_clause or not where_clause:
        raise ValueError("Для update нужны непустые SET и WHERE.")
    if "ID" in set_clause:
        raise ValueError("Изменять ID нельзя: он генерируется автоматически.")
    matched = select(table_data, where_clause)
    for row in matched:
        for name, value in set_clause.items():
            if name not in row or type(value) is not type(row[name]):
                raise ValueError(f'Некорректное значение для столбца "{name}".')
    for row in matched:
        row.update(set_clause)
    return table_data


def delete(table_data, where_clause):
    """Вернуть записи, не соответствующие обязательному условию WHERE."""
    if not where_clause:
        raise ValueError("Для delete нужно непустое условие WHERE.")
    return [row for row in table_data if not _matches(row, where_clause)]
