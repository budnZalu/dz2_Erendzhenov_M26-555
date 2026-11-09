"""Проверки данных: исключения обрабатывает декоратор вызывающей операции."""

from primitive_db.constants import SUPPORTED_TYPES


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
