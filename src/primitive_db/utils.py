"""Чтение и запись метаданных в формате JSON."""

import json
import os

from primitive_db.constants import DATA_DIR, TEMP_TOKEN_BYTES


def load_metadata(filepath):
    """Загрузить метаданные; только отсутствие файла означает пустую базу."""
    try:
        with open(filepath, encoding="utf-8") as file:
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
    temporary_path = os.path.join(directory, f".{os.path.basename(path)}.{token}.tmp")
    created = False
    try:
        with open(temporary_path, "x", encoding="utf-8") as file:
            created = True
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary_path, path)
    finally:
        if created and os.path.exists(temporary_path):
            os.remove(temporary_path)


def table_data_path(table_name):
    """Получить путь к данным, не позволяя использовать имя как путь."""
    if not table_name.isidentifier():
        raise ValueError(f"Некорректное имя таблицы: {table_name}.")
    return os.path.join(DATA_DIR, f"{table_name}.json")


def load_table_data(table_name):
    """Прочитать записи таблицы; отсутствие файла означает пустую таблицу."""
    path = table_data_path(table_name)
    try:
        with open(path, encoding="utf-8") as file:
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
