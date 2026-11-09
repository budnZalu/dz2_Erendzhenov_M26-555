# Primitive DB

Автор: **Эрендженов (Erendzhenov)**. Группа: **M26-555**.

Учебный проект на Python 3.12 и выше. Первый шаг: устанавливаемый пакет
`primitive_db` с консольной командой `project`.

## Установка и запуск

Установите [uv](https://docs.astral.sh/uv/getting-started/installation/),
затем выполните в корне этого проекта:

```sh
uv sync
uv run project
```

Альтернативный запуск:

```sh
uv run python -m primitive_db.main
```

Оба варианта выводят `DB project is running!`.

## Сборка и проверка метаданных

```sh
uv build
uvx twine check dist/*
```

В папке `dist/` появятся wheel и исходный архив. Команда `twine check`
проверяет метаданные локально и не публикует пакет на PyPI.

## Установка CLI из wheel

```sh
uv tool install dist/*.whl
project
```

Если uv сообщает, что папка инструментов отсутствует в `PATH`, выполните
`uv tool update-shell` и перезапустите терминал.
