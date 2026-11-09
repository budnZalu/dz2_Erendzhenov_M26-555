"""Хранение схем и записей: чтение, атомарная запись и откат удаления."""

import json
import os

from primitive_db.constants import (
    DATA_DIR,
    JSON_INDENT,
    JSON_SUFFIX,
    TEMP_SUFFIX,
    TEMP_TOKEN_BYTES,
    TEXT_ENCODING,
)


def load_metadata(filepath):
    """Загрузить метаданные; только отсутствие файла означает пустую базу."""
    try:
        with open(filepath, encoding=TEXT_ENCODING) as file:
            data = json.load(file)
    except FileNotFoundError:
        return {}

    if not isinstance(data, dict) or any(
        not isinstance(columns, list)
        or not all(isinstance(column, str) for column in columns)
        for columns in data.values()
    ):
        raise ValueError(
            "Метаданные должны содержать объект с именами таблиц и списками столбцов."
        )
    return data


def save_metadata(filepath, data):
    """Сохранить JSON, заменив исходный файл только после успешной записи."""
    path = os.fspath(filepath)
    directory = os.path.dirname(path) or "."
    token = os.urandom(TEMP_TOKEN_BYTES).hex()
    temporary_path = os.path.join(
        directory, f".{os.path.basename(path)}.{token}{TEMP_SUFFIX}"
    )
    created = False
    try:
        with open(temporary_path, "x", encoding=TEXT_ENCODING) as file:
            created = True
            json.dump(data, file, ensure_ascii=False, indent=JSON_INDENT)
            file.write("\n")
        os.replace(temporary_path, path)
    finally:
        if created and os.path.exists(temporary_path):
            os.remove(temporary_path)


def table_data_path(table_name):
    """Получить путь к данным, не позволяя использовать имя как путь."""
    if not table_name.isidentifier():
        raise ValueError(f"Некорректное имя таблицы: {table_name}.")
    return os.path.join(DATA_DIR, f"{table_name}{JSON_SUFFIX}")


def ensure_table_data_absent(table_name):
    """Запретить создание таблицы поверх оставшегося файла данных без схемы."""
    path = table_data_path(table_name)
    if os.path.exists(path):
        raise ValueError(
            f"Файл {path} уже существует без схемы. "
            "Проверьте или перенесите его перед созданием таблицы."
        )


def load_table_data(table_name):
    """Прочитать записи таблицы; отсутствие файла означает пустую таблицу."""
    path = table_data_path(table_name)
    try:
        with open(path, encoding=TEXT_ENCODING) as file:
            data = json.load(file)
    except FileNotFoundError:
        return []
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        raise ValueError(f"Файл {path} должен содержать список записей-словарей.")
    return data


def save_table_data(table_name, data):
    """Создать каталог data при необходимости и атомарно сохранить записи."""
    path = table_data_path(table_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    save_metadata(path, data)


def delete_table_data(table_name):
    """Удалить файл данных при удалении таблицы."""
    try:
        os.remove(table_data_path(table_name))
    except FileNotFoundError:
        pass


def save_table_removal(filepath, previous_metadata, updated_metadata, table_name):
    """Сохранить схему без таблицы; восстановить её при ошибке удаления данных."""
    save_metadata(filepath, updated_metadata)
    try:
        delete_table_data(table_name)
    except OSError:
        save_metadata(filepath, previous_metadata)
        raise
