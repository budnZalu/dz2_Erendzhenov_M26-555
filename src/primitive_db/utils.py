"""Чтение и запись метаданных в формате JSON."""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile


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
    path = Path(filepath)
    temporary_path = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def table_data_path(table_name):
    """Получить путь к данным, не позволяя использовать имя как путь."""
    if not table_name.isidentifier():
        raise ValueError(f"Некорректное имя таблицы: {table_name}.")
    return Path("data") / f"{table_name}.json"


def load_table_data(table_name):
    """Прочитать записи таблицы; отсутствие файла означает пустую таблицу."""
    path = table_data_path(table_name)
    try:
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return []
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        raise ValueError(f"Файл {path} должен содержать список записей-словарей.")
    return data


def save_table_data(table_name, data):
    """Создать каталог data при необходимости и атомарно сохранить записи."""
    path = table_data_path(table_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_metadata(path, data)


def delete_table_data(table_name):
    """Удалить файл данных при удалении таблицы."""
    table_data_path(table_name).unlink(missing_ok=True)
