"""Управление схемами таблиц и операции над записями."""

from primitive_db.constants import ID_COLUMN
from primitive_db.decorators import (
    confirm_action,
    create_cacher,
    handle_db_errors,
    log_time,
)
from primitive_db.utils import load_table_data
from primitive_db.validation import (
    get_schema,
    normalize_columns,
    validate_clause,
    validate_table_data,
)

_select_cache = create_cacher()


@handle_db_errors
def create_table(metadata, table_name, columns):
    """Добавить таблицу или вернуть None, не меняя метаданные при ошибке."""
    if not table_name.isidentifier():
        raise ValueError(f"Некорректное значение: {table_name}. Попробуйте снова.")
    if table_name in metadata:
        raise ValueError(f'Таблица "{table_name}" уже существует.')
    metadata[table_name] = normalize_columns(columns)
    return metadata


@handle_db_errors
@confirm_action("удаление таблицы")
def drop_table(metadata, table_name):
    """После подтверждения удалить таблицу и вернуть метаданные."""
    get_schema(metadata, table_name)
    del metadata[table_name]
    return metadata


@handle_db_errors
@log_time
def insert(metadata, table_name, values, table_data=None):
    """Добавить типизированную запись с новым ID и вернуть данные таблицы."""
    schema = get_schema(metadata, table_name)
    columns = [name for name in schema if name != ID_COLUMN]
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
    new_id = max((row[ID_COLUMN] for row in table_data), default=0) + 1
    table_data.append({ID_COLUMN: new_id, **record})
    return table_data


def _matches(row, where_clause):
    """Сравнить значения без смешения bool и int (True не равен 1)."""
    return all(
        name in row and type(row[name]) is type(value) and row[name] == value
        for name, value in where_clause.items()
    )


def _freeze_record(record):
    """Сформировать ключ с учётом точных типов (True отличается от 1)."""
    return tuple(sorted((name, type(value), value) for name, value in record.items()))


@handle_db_errors
@log_time
def select(table_data, where_clause=None):
    """Кэшировать выборку по содержимому данных и вернуть независимые записи."""
    condition = where_clause or {}
    key = (tuple(_freeze_record(row) for row in table_data), _freeze_record(condition))
    result = _select_cache(
        key,
        lambda: [row.copy() for row in table_data if _matches(row, condition)],
    )
    return [row.copy() for row in result]


@handle_db_errors
def update(table_data, set_clause, where_clause):
    """Проверить изменения, обновить все совпадения и вернуть данные."""
    if not set_clause or not where_clause:
        raise ValueError("Для update нужны непустые SET и WHERE.")
    if ID_COLUMN in set_clause:
        raise ValueError(f"Изменять {ID_COLUMN} нельзя: он генерируется автоматически.")
    matched = [row for row in table_data if _matches(row, where_clause)]
    for row in matched:
        for name, value in set_clause.items():
            if name not in row or type(value) is not type(row[name]):
                raise ValueError(f'Некорректное значение для столбца "{name}".')
    for row in matched:
        row.update(set_clause)
    return table_data


@handle_db_errors
@confirm_action("удаление записей")
def delete(table_data, where_clause):
    """Вернуть записи, не соответствующие обязательному условию WHERE."""
    if not where_clause:
        raise ValueError("Для delete нужно непустое условие WHERE.")
    return [row for row in table_data if not _matches(row, where_clause)]
