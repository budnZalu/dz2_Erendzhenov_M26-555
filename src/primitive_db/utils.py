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
