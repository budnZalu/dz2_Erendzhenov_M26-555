"""Проверки структуры таблиц, сохранности JSON и консольного интерфейса."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from primitive_db.core import create_table, drop_table
from primitive_db.engine import run
from primitive_db.utils import load_metadata, save_metadata


class CoreTests(unittest.TestCase):
    def test_create_adds_id_without_changing_input_columns(self):
        metadata = {}
        columns = ["name:str", "age:int", "is_active:bool"]
        result = create_table(metadata, "users", columns)
        self.assertIs(result, metadata)
        self.assertEqual(metadata, {"users": ["ID:int", *columns]})
        self.assertEqual(columns, ["name:str", "age:int", "is_active:bool"])

    def test_explicit_id_is_first_and_not_duplicated(self):
        metadata = create_table({}, "users", ["name:str", "ID:int"])
        self.assertEqual(metadata["users"], ["ID:int", "name:str"])

    def test_invalid_columns_do_not_change_metadata(self):
        for columns in (
            [],
            ["age:float"],
            ["name"],
            [":str"],
            ["name:"],
            ["name:str:bool"],
            ["name:str", "name:int"],
            ["ID:str"],
            ["ID:bool"],
            ["ID:int", "ID:int"],
            ["bad-name:str"],
        ):
            with self.subTest(columns=columns):
                metadata = {"existing": ["ID:int"]}
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    result = create_table(metadata, "users", columns)
                self.assertIsNone(result)
                self.assertEqual(metadata, {"existing": ["ID:int"]})
                self.assertIn("Некорректное значение:", output.getvalue())

    def test_duplicate_table_preserves_existing_columns(self):
        metadata = {"users": ["ID:int", "name:str"]}
        with contextlib.redirect_stdout(io.StringIO()) as output:
            create_table(metadata, "users", ["age:int"])
        self.assertEqual(metadata["users"], ["ID:int", "name:str"])
        self.assertIn('Таблица "users" уже существует.', output.getvalue())

    def test_invalid_names_and_missing_table(self):
        for table_name in ("", "bad-name", "two words", "123users"):
            with self.subTest(name=table_name):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertIsNone(create_table({}, table_name, ["x:int"]))
        metadata = {"users": ["ID:int"]}
        with (
            contextlib.redirect_stdout(io.StringIO()) as output,
            patch("builtins.input", return_value="y"),
        ):
            self.assertIsNone(drop_table(metadata, "missing"))
        self.assertEqual(metadata, {"users": ["ID:int"]})
        self.assertIn('Таблица "missing" не существует.', output.getvalue())
        with patch("builtins.input", return_value="y"):
            self.assertIs(drop_table(metadata, "users"), metadata)
        self.assertEqual(metadata, {})


class StorageAndCliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "db_meta.json"

    def cli(self, commands):
        result = subprocess.run(
            [sys.executable, "-m", "primitive_db.main"],
            input=commands,
            text=True,
            capture_output=True,
            cwd=self.directory.name,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def test_missing_file_and_unicode_round_trip(self):
        self.assertEqual(load_metadata(self.path), {})
        data = {"люди": ["ID:int", "имя:str"]}
        save_metadata(self.path, data)
        self.assertEqual(load_metadata(self.path), data)
        self.assertIn("люди", self.path.read_text(encoding="utf-8"))

    def test_bad_json_and_invalid_structure_are_not_empty_databases(self):
        for contents in ("{", "[]", "null", '{"users": 1}', '{"users": [1]}'):
            with self.subTest(contents=contents):
                self.path.write_text(contents, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_metadata(self.path)

    def test_failed_atomic_replace_preserves_original_file(self):
        save_metadata(self.path, {"users": ["ID:int"]})
        original = self.path.read_bytes()
        with patch("primitive_db.utils.Path.replace", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                save_metadata(self.path, {})
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_create_list_and_drop_persist_across_processes(self):
        output = self.cli(
            'create_table "users" "name:str" age:int is_active:bool\nexit\n'
        )
        self.assertIn("ID:int, name:str, age:int, is_active:bool", output)
        self.assertEqual(
            load_metadata(self.path),
            {"users": ["ID:int", "name:str", "age:int", "is_active:bool"]},
        )
        self.assertIn("- users", self.cli("list_tables\nexit\n"))
        output = self.cli("drop_table users\ny\nlist_tables\nexit\n")
        self.assertIn('Таблица "users" успешно удалена.', output)
        self.assertIn("Таблиц пока нет.", output)
        self.assertEqual(load_metadata(self.path), {})

    def test_bad_commands_recover_without_creating_metadata(self):
        output = self.cli(
            "\n  \nunknown\ncreate_table\ncreate_table users\n"
            "drop_table\nlist_tables extra\nhelp extra\nexit extra\n"
            'create_table "unterminated\ncreate_table users age:float\n'
            "create_table users ID:str\ncreate_table users name:str name:int\n"
            "drop_table missing\nhelp\nexit\n"
        )
        self.assertIn("Функции unknown нет. Попробуйте снова.", output)
        self.assertIn("Некорректное значение:", output)
        self.assertIn('Таблица "missing" не существует.', output)
        self.assertEqual(output.count("***База данных***"), 2)
        self.assertFalse(self.path.exists())

    def test_corrupt_file_is_preserved_and_help_and_exit_still_work(self):
        self.path.write_text("broken json", encoding="utf-8")
        output = self.cli("create_table users name:str\nlist_tables\nhelp\nexit\n")
        self.assertIn("Ошибка чтения db_meta.json:", output)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "broken json")
        self.assertEqual(output.count("***База данных***"), 2)

    def test_read_only_commands_do_not_rewrite_metadata(self):
        original = '{"users": ["ID:int"]}'
        self.path.write_text(original, encoding="utf-8")
        self.cli("list_tables\ncreate_table users age:int\ndrop_table missing\nexit\n")
        self.assertEqual(self.path.read_text(encoding="utf-8"), original)

    def test_metadata_reloads_each_iteration(self):
        def user_input():
            yield "list_tables"
            save_metadata(self.path, {"external": ["ID:int"]})
            yield "help"
            yield "list_tables"
            yield "exit"

        with (
            patch("primitive_db.engine.METADATA_FILE", self.path),
            patch("primitive_db.engine.prompt.string", side_effect=user_input()),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            run()
        self.assertIn("Таблиц пока нет.", output.getvalue())
        self.assertIn("- external", output.getvalue())

    def test_save_error_does_not_report_success(self):
        with (
            patch("primitive_db.engine.METADATA_FILE", self.path),
            patch(
                "primitive_db.engine.prompt.string",
                side_effect=["create_table users name:str", "exit"],
            ),
            patch("primitive_db.engine.save_metadata", side_effect=PermissionError),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            run()
        self.assertIn("Ошибка чтения или сохранения файла", output.getvalue())
        self.assertNotIn("успешно создана", output.getvalue())
        self.assertFalse(self.path.exists())

    def test_eof_and_keyboard_interrupt(self):
        self.assertIn("Выход из программы.", self.cli(""))
        with (
            patch("primitive_db.engine.prompt.string", side_effect=KeyboardInterrupt),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            run()
        self.assertIn("Выход из программы.", output.getvalue())

    def test_imports_have_no_side_effects(self):
        result = subprocess.run(
            [sys.executable, "-c", "import primitive_db.main"],
            input="",
            text=True,
            capture_output=True,
            cwd=self.directory.name,
            timeout=5,
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
