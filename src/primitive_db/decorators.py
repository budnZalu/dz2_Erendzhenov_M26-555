"""Общие обёртки операций базы данных и кэш в замыкании."""

import time


def _preserve_metadata(wrapper, func):
    """Сохранить метаданные функции без дополнительных стандартных модулей."""
    for name in (
        "__name__",
        "__qualname__",
        "__doc__",
        "__module__",
        "__annotations__",
    ):
        if hasattr(func, name):
            setattr(wrapper, name, getattr(func, name))
    wrapper.__wrapped__ = func
    return wrapper


def handle_db_errors(func):
    """Вывести понятную ошибку и вернуть None вместо неуспешного результата."""

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileNotFoundError:
            print(
                "Ошибка: Файл данных не найден. "
                "Возможно, база данных не инициализирована."
            )
        except KeyError as error:
            print(f"Ошибка: Таблица или столбец {error} не найден.")
        except ValueError as error:
            print(f"Ошибка валидации: {error}")
        except OSError as error:
            print(f"Ошибка чтения или сохранения файла: {error}")
        except Exception as error:
            print(f"Произошла непредвиденная ошибка: {error}")
        return None

    return _preserve_metadata(wrapper, func)


def confirm_action(action_name):
    """Выполнить операцию только после ответа y; отмену обозначить None."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                answer = input(
                    f'Вы уверены, что хотите выполнить "{action_name}"? [y/n]: '
                )
            except (EOFError, KeyboardInterrupt):
                print()
                answer = ""
            if answer != "y":
                print("Операция отменена.")
                return None
            return func(*args, **kwargs)

        return _preserve_metadata(wrapper, func)

    return decorator


def log_time(func):
    """Измерить время вызова, включая завершившийся исключением вызов."""

    def wrapper(*args, **kwargs):
        started = time.monotonic()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.monotonic() - started
            print(f"Функция {func.__name__} выполнилась за {elapsed:.3f} секунд")

    return _preserve_metadata(wrapper, func)


def create_cacher():
    """Создать независимый кэш; не сохранять результат ошибочного вычисления."""
    cache = {}

    def cache_result(key, value_func):
        if key not in cache:
            cache[key] = value_func()
        return cache[key]

    return cache_result
