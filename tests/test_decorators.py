"""Проверки декораторов, замыкания, отмены операций и актуальности выборок."""

import contextlib
import copy
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from primitive_db import core
from primitive_db.decorators import (
    confirm_action,
    create_cacher,
    handle_db_errors,
    log_time,
)
from primitive_db.engine import execute_crud, execute_table_command
from primitive_db.parser import parse_command
from primitive_db.utils import load_table_data, save_metadata, save_table_data

METADATA = {"users": ["ID:int", "name:str", "active:bool"]}
ROWS = [{"ID": 1, "name": "Anna", "active": True}]


class DecoratorTests(unittest.TestCase):
    def test_wrappers_preserve_metadata_arguments_and_return_value(self):
        def operation(a, *, b):
            """Описание исходной функции."""
            return a + b

        for decorator in (handle_db_errors, log_time, confirm_action("тест")):
            with (
                self.subTest(decorator=decorator),
                patch("builtins.input", return_value="y"),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                wrapped = decorator(operation)
                self.assertEqual(wrapped(2, b=3), 5)
                self.assertEqual(wrapped.__name__, "operation")
                self.assertEqual(wrapped.__doc__, operation.__doc__)
                self.assertIs(wrapped.__wrapped__, operation)

    def test_errors_are_reported_once_and_return_none(self):
        cases = [
            (KeyError("missing"), "Таблица или столбец 'missing' не найден"),
            (ValueError("wrong type"), "Ошибка валидации: wrong type"),
            (FileNotFoundError(), "Файл данных не найден"),
            (PermissionError("denied"), "Ошибка чтения или сохранения файла: denied"),
            (RuntimeError("unexpected"), "непредвиденная ошибка: unexpected"),
        ]
        for error, message in cases:
            with self.subTest(error=error):
                wrapped = handle_db_errors(Mock(side_effect=error))
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertIsNone(wrapped())
                self.assertIn(message, output.getvalue())
                self.assertEqual(len(output.getvalue().splitlines()), 1)

    def test_process_control_exceptions_are_not_swallowed(self):
        for error in (KeyboardInterrupt, SystemExit):
            with self.subTest(error=error), self.assertRaises(error):
                handle_db_errors(Mock(side_effect=error))()

    def test_confirmation_requires_exact_y_and_cancels_interrupts(self):
        for answer in ("n", "", "yes", "Y", " y ", EOFError, KeyboardInterrupt):
            with self.subTest(answer=answer):
                operation = Mock(return_value="done")
                input_mock = Mock(
                    **(
                        {"side_effect": answer}
                        if isinstance(answer, type)
                        else {"return_value": answer}
                    )
                )
                with (
                    patch("builtins.input", input_mock),
                    contextlib.redirect_stdout(io.StringIO()) as output,
                ):
                    result = confirm_action("удаление таблицы")(operation)()
                self.assertIsNone(result)
                operation.assert_not_called()
                input_mock.assert_called_once_with(
                    'Вы уверены, что хотите выполнить "удаление таблицы"? [y/n]: '
                )
                self.assertIn("Операция отменена.", output.getvalue())

    def test_monotonic_time_format_and_exception_propagation(self):
        @log_time
        def operation(fail=False):
            if fail:
                raise ValueError("test")
            return "done"

        for fail in (False, True):
            with (
                self.subTest(fail=fail),
                patch("primitive_db.decorators.time.monotonic", side_effect=[5, 6.234]),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                if fail:
                    with self.assertRaises(ValueError):
                        operation(fail=True)
                else:
                    self.assertEqual(operation(), "done")
            self.assertEqual(
                output.getvalue(), "Функция operation выполнилась за 1.234 секунд\n"
            )

    def test_core_file_errors_are_handled_without_mutation(self):
        with (
            patch("primitive_db.core.load_table_data", side_effect=FileNotFoundError),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertIsNone(core.insert(METADATA, "users", ["New", True]))
        self.assertEqual(output.getvalue().count("Файл данных не найден"), 1)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.cache_patch = patch("primitive_db.core._select_cache", create_cacher())
        self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def test_closure_caches_falsy_values_and_has_independent_instances(self):
        cache = create_cacher()
        for key, value in enumerate((None, False, 0, [], "")):
            compute = Mock(return_value=value)
            self.assertIs(cache(key, compute), value)
            self.assertIs(cache(key, compute), value)
            compute.assert_called_once_with()
        other = create_cacher()
        self.assertEqual(other(0, lambda: "independent"), "independent")
        self.assertIsNone(cache(0, lambda: "replacement"))

    def test_failed_computation_is_retried(self):
        compute = Mock(side_effect=[ValueError("failed"), "ok"])
        cache = create_cacher()
        with self.assertRaises(ValueError):
            cache("key", compute)
        self.assertEqual(cache("key", compute), "ok")
        self.assertEqual(cache("key", compute), "ok")
        self.assertEqual(compute.call_count, 2)

    def test_repeated_query_reuses_filter_even_with_reloaded_rows(self):
        with patch("primitive_db.core._matches", wraps=core._matches) as matches:
            self.assertEqual(core.select(ROWS, {"active": True}), ROWS)
            self.assertEqual(core.select(copy.deepcopy(ROWS), {"active": True}), ROWS)
            self.assertEqual(matches.call_count, len(ROWS))
            self.assertEqual(core.select(ROWS, {"active": False}), [])
            self.assertEqual(matches.call_count, 2 * len(ROWS))

    def test_cache_keys_distinguish_bool_and_int_in_data_and_conditions(self):
        self.assertEqual(core.select(ROWS, {"active": True}), ROWS)
        self.assertEqual(core.select(ROWS, {"active": 1}), [])
        number_rows = [{**ROWS[0], "active": 1}]
        self.assertEqual(core.select(number_rows, {"active": True}), [])
        self.assertEqual(core.select(number_rows, {"active": 1}), number_rows)

    def test_cached_results_do_not_alias_source_or_previous_results(self):
        rows = copy.deepcopy(ROWS)
        first = core.select(rows)
        first[0]["name"] = "Changed"
        first.append({"ID": 99})
        self.assertEqual(rows, ROWS)
        self.assertEqual(core.select(rows), ROWS)
        rows[0]["name"] = "External"
        self.assertEqual(core.select(rows)[0]["name"], "External")
        self.assertEqual(core.select(ROWS), ROWS)

    def test_queries_refresh_after_insert_update_and_delete(self):
        rows = copy.deepcopy(ROWS)
        self.assertEqual(core.select(rows, {"active": True}), ROWS)
        core.insert(METADATA, "users", ["New", True], rows)
        self.assertEqual(len(core.select(rows, {"active": True})), 2)
        core.update(rows, {"active": False}, {"ID": 1})
        self.assertEqual(core.select(rows, {"active": True}), [rows[1]])
        with patch("builtins.input", return_value="y"):
            rows = core.delete(rows, {"ID": 2})
        self.assertEqual(core.select(rows, {"active": True}), [])


class DecoratedCliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(contextlib.chdir(directory.name))
        self.metadata = copy.deepcopy(METADATA)
        save_metadata("db_meta.json", self.metadata)
        save_table_data("users", ROWS)
        self.data_path = Path("data/users.json")
        self.meta_path = Path("db_meta.json")
        self.enterContext(patch("primitive_db.core._select_cache", create_cacher()))

    def execute(self, command):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            execute_crud(self.metadata, parse_command(command))
        return output.getvalue()

    def test_cancelled_delete_and_drop_preserve_bytes_and_mtime(self):
        before = [
            (path.read_bytes(), path.stat().st_mtime_ns)
            for path in (self.meta_path, self.data_path)
        ]
        with (
            patch("builtins.input", return_value="n") as confirm,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            execute_crud(self.metadata, parse_command("delete from users where ID=1"))
            execute_table_command(self.metadata, "drop_table", ["users"])
        self.assertEqual(confirm.call_count, 2)
        self.assertEqual(output.getvalue().count("Операция отменена."), 2)
        self.assertNotIn("успешно", output.getvalue())
        self.assertEqual(self.metadata, METADATA)
        self.assertEqual(
            before,
            [
                (path.read_bytes(), path.stat().st_mtime_ns)
                for path in (self.meta_path, self.data_path)
            ],
        )

    def test_invalid_or_empty_delete_does_not_ask_for_confirmation(self):
        with patch("builtins.input") as confirm:
            self.assertIn(
                "не существует", self.execute("delete from absent where ID=1")
            )
            self.assertIn("не существует", self.execute("delete from users where x=1"))
            self.assertIn(
                "Записей не найдено", self.execute("delete from users where ID=9")
            )
        confirm.assert_not_called()

    def test_invalid_insert_is_not_saved_or_reported_as_success(self):
        original = self.data_path.read_bytes()
        output = self.execute('insert into users values ("New", 1)')
        self.assertEqual(output.count("Ошибка валидации:"), 1)
        self.assertIn("Функция insert выполнилась за", output)
        self.assertNotIn("успешно", output)
        self.assertEqual(self.data_path.read_bytes(), original)

    def test_cache_refreshes_after_external_file_change_and_table_recreation(self):
        self.assertIn("Anna", self.execute("select from users"))
        save_table_data("users", [{**ROWS[0], "name": "External"}])
        self.assertIn("External", self.execute("select from users"))
        with (
            patch("builtins.input", return_value="y"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            execute_table_command(self.metadata, "drop_table", ["users"])
            execute_table_command(self.metadata, "create_table", ["users", "name:str"])
        output = self.execute("select from users")
        self.assertIn("Записей не найдено", output)
        self.assertNotIn("Anna", output)
        self.execute('insert into users values ("Recreated")')
        self.assertIn("Recreated", self.execute("select from users"))
        self.assertEqual(load_table_data("users"), [{"ID": 1, "name": "Recreated"}])


if __name__ == "__main__":
    unittest.main()
