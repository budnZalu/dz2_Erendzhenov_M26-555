"""Проверки CRUD, строгих типов, разбора строк и сохранности записей."""

import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from primitive_db.core import delete, insert, select, update
from primitive_db.engine import execute_crud, execute_table_command
from primitive_db.parser import (
    parse_command,
    parse_set_clause,
    parse_value,
    parse_where_clause,
)
from primitive_db.utils import load_table_data, save_table_data

METADATA = {"users": ["ID:int", "name:str", "age:int", "is_active:bool"]}
ROWS = [
    {"ID": 1, "name": "Sergei", "age": 28, "is_active": True},
    {"ID": 3, "name": "Anna", "age": 28, "is_active": False},
]


class ParserTests(unittest.TestCase):
    def test_values_preserve_types_and_punctuation_inside_strings(self):
        command = parse_command(
            'insert into users values ("where, set = (test)", -28, false)'
        )
        self.assertEqual(command["values"], ["where, set = (test)", -28, False])
        self.assertEqual(
            parse_command('insert into users values("28",28,true)')["values"],
            ["28", 28, True],
        )
        self.assertEqual(
            parse_command("insert into users values ('', 0, false)")["values"],
            ["", 0, False],
        )

    def test_escaped_quotes_and_backslashes(self):
        value = 'O\'Brien, "Sergei" \\ path'
        command = parse_command(
            f"insert into users values ({json.dumps(value)}, 28, true)"
        )
        self.assertEqual(command["values"][0], value)
        command = parse_command(r"insert into users values ('O\'Brien', 28, true)")
        self.assertEqual(command["values"][0], "O'Brien")

    def test_unicode_and_json_escapes_with_both_quote_styles(self):
        for literal, expected in (
            ('"Привет, мир"', "Привет, мир"),
            (r'"line\nnext\t\u0410"', "line\nnext\tА"),
            (r"'Он сказал: \"да\"'", 'Он сказал: "да"'),
            (r"'C:\\temp\\file'", "C:\\temp\\file"),
            (r'"O\'Brien"', "O'Brien"),
        ):
            with self.subTest(literal=literal):
                parsed = parse_command(f"insert into users values ({literal}, 1, true)")
                self.assertEqual(parsed["values"][0], expected)

    def test_invalid_escapes_quotes_and_numeric_literals_are_rejected(self):
        for literal in (
            r'"bad\q"',
            r"'bad\q'",
            '"unfinished',
            '"trailing\\',
            '"unescaped"quote"',
            "+",
            "--1",
            "1_000",
            "١",
        ):
            with self.subTest(literal=literal), self.assertRaises(ValueError):
                parse_value(literal)

    def test_where_and_multiple_set_assignments(self):
        self.assertEqual(parse_where_clause("age=28"), {"age": 28})
        self.assertEqual(parse_where_clause('name="true"'), {"name": "true"})
        self.assertEqual(
            parse_set_clause('name="A, B",age=29,is_active=false'),
            {"name": "A, B", "age": 29, "is_active": False},
        )
        command = parse_command('update users set where = "where" where set = "set"')
        self.assertEqual(command["set_clause"], {"where": "where"})
        self.assertEqual(command["where_clause"], {"set": "set"})

    def test_rejects_malformed_or_incomplete_commands(self):
        invalid = [
            "insert into users values (Sergei, 28, true)",
            'insert into users values ("Sergei", 28.5, true)',
            'insert into users values ("Sergei", null, true)',
            'insert into users values ("Sergei", 28, true,)',
            'insert into users values ("Sergei" 28 true)',
            'insert into users values ("Sergei",,true)',
            'insert into users values ("Sergei", 28, true) garbage',
            'insert into users values ("unfinished, 28, true)',
            "select from users where age == 28",
            "select from users where age = 28 extra",
            "delete from users",
            "delete from users where",
            "update users set age=29",
            "update users set age=29, age=30 where ID=1",
            "update users set age=29 where name=Sergei",
            "update users set age=29 where ID=1 trailing",
            "info users extra",
            "info",
            "select from ../users",
        ]
        for command in invalid:
            with self.subTest(command=command), self.assertRaises(ValueError):
                parse_command(command)


class CrudCoreTests(unittest.TestCase):
    def test_insert_loads_data_and_uses_max_id_not_length(self):
        rows = copy.deepcopy(ROWS)
        with patch("primitive_db.core.load_table_data", return_value=rows):
            result = insert(METADATA, "users", ["New", 30, True])
        self.assertEqual(
            result[-1],
            {
                "ID": 4,
                "name": "New",
                "age": 30,
                "is_active": True,
            },
        )

    def test_insert_rejects_missing_fields_explicit_id_and_wrong_types(self):
        for values in (
            ["S", 28],
            [9, "S", 28, True],
            ["S", True, True],
            ["S", "28", True],
            ["S", 28, 1],
            [28, 28, True],
            ["S", None, True],
        ):
            with self.subTest(values=values):
                rows = copy.deepcopy(ROWS)
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertIsNone(insert(METADATA, "users", values, rows))
                self.assertIn("Ошибка валидации:", output.getvalue())
                self.assertEqual(rows, ROWS)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertIsNone(insert(METADATA, "absent", []))
        self.assertIn("не существует", output.getvalue())

    def test_select_and_delete_compare_bool_and_int_strictly(self):
        self.assertEqual(select(ROWS, {"age": True}), [])
        self.assertEqual(select(ROWS, {"is_active": 1}), [])
        self.assertEqual(select(ROWS, {"age": 28}), ROWS)
        self.assertEqual(select(ROWS), ROWS)
        with patch("builtins.input", return_value="y"):
            self.assertEqual(delete(ROWS, {"is_active": False}), [ROWS[0]])
        self.assertEqual(len(ROWS), 2)

    def test_update_all_matches_and_keep_unmatched_records(self):
        rows = copy.deepcopy(ROWS)
        self.assertIs(update(rows, {"age": 29}, {"age": 28}), rows)
        self.assertEqual([row["age"] for row in rows], [29, 29])
        update(rows, {"name": "Changed"}, {"ID": 1})
        self.assertEqual(rows[1], {**ROWS[1], "age": 29})

    def test_invalid_update_is_not_partial_and_id_is_read_only(self):
        rows = copy.deepcopy(ROWS)
        for changes in ({"ID": 3}, {"age": True}, {"name": "X", "unknown": 1}):
            with (
                self.subTest(changes=changes),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertIsNone(update(rows, changes, {"age": 28}))
            self.assertEqual(rows, ROWS)
        with (
            patch("builtins.input", return_value="y"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertIsNone(delete(rows, {}))
            self.assertIsNone(update(rows, {"age": 29}, {}))


class CrudCliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "data/users.json"

    def cli(self, commands):
        result = subprocess.run(
            [sys.executable, "-m", "primitive_db.main"],
            input=commands,
            text=True,
            capture_output=True,
            cwd=self.root,
            timeout=5,
        )
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        return result.stdout

    def seed(self):
        self.cli(
            "create_table users name:str age:int is_active:bool\n"
            'insert into users values ("Sergei", 28, true)\n'
            'insert into users values ("Anna", 28, false)\nexit\n'
        )

    def rows(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_complete_persistent_crud_flow_and_info(self):
        self.seed()
        self.assertEqual(self.rows()[0], ROWS[0])
        output = self.cli('select from users where name="Sergei"\ninfo users\nexit\n')
        self.assertIn("| ID |", output)
        self.assertIn("| Sergei |", output)
        self.assertNotIn("|  Anna", output)
        self.assertIn("Количество записей: 2", output)
        output = self.cli('update users set age=29 where name="Sergei"\nexit\n')
        self.assertIn('Запись с ID=1 в таблице "users" успешно обновлена.', output)
        self.assertEqual(self.rows()[0]["age"], 29)
        output = self.cli("delete from users where ID=1\ny\ninfo users\nexit\n")
        self.assertIn('Запись с ID=1 успешно удалена из таблицы "users".', output)
        self.assertIn("Количество записей: 1", output)
        self.cli('insert into users values ("B", 18, true)\nexit\n')
        self.assertEqual([row["ID"] for row in self.rows()], [2, 3])

    def test_multiple_updates_bool_filter_and_quoted_delimiters(self):
        self.seed()
        output = self.cli(
            "update users set age=30,is_active=true where age=28\n"
            "select from users where is_active=true\nexit\n"
        )
        self.assertEqual(output.count("успешно обновлена."), 2)
        self.assertTrue(
            all(row["age"] == 30 and row["is_active"] for row in self.rows())
        )
        name = 'a, b (c) where set = "d"'
        self.cli(f"insert into users values ({json.dumps(name)}, 10, false)\nexit\n")
        output = self.cli(f"select from users where name={json.dumps(name)}\nexit\n")
        self.assertIn(name, output)

    def test_rejected_commands_leave_file_byte_for_byte_unchanged(self):
        self.seed()
        original = self.path.read_bytes()
        output = self.cli(
            'insert into users values (9,"Sergei",28,true)\n'
            'insert into users values ("Sergei",true,true)\n'
            'insert into users values ("Sergei",28)\n'
            "update users set ID=2 where ID=1\n"
            'update users set age="29" where ID=1\n'
            "update users set age=29 where missing=1\n"
            "update users set missing=29 where ID=999\n"
            "delete from users where ID=true\n"
            "delete from users\nselect from users where unknown=1\n"
            'select from users where age="28"\nexit\n'
        )
        self.assertIn("Ошибка валидации:", output)
        self.assertNotIn("успешно", output)
        self.assertEqual(self.path.read_bytes(), original)

    def test_empty_tables_and_no_matches_do_not_create_or_rewrite_data(self):
        output = self.cli(
            "create_table users name:str age:int is_active:bool\n"
            "select from users\ninfo users\n"
            "update users set age=29 where ID=999\n"
            "delete from users where ID=999\nexit\n"
        )
        self.assertIn("| ID |", output)
        self.assertIn("Количество записей: 0", output)
        self.assertFalse(self.path.exists())
        self.seed()
        original = self.path.read_bytes()
        self.cli(
            "update users set age=29 where ID=999\n"
            "delete from users where ID=999\nexit\n"
        )
        self.assertEqual(self.path.read_bytes(), original)

    def test_missing_table_and_invalid_schema_recover(self):
        output = self.cli(
            "insert into missing values (1)\nselect from missing\ninfo missing\nexit\n"
        )
        self.assertIn('Таблица "missing" не существует.', output)
        (self.root / "db_meta.json").write_text('{"users": ["name:str"]}')
        output = self.cli("select from users\nexit\n")
        self.assertIn("Некорректная структура таблицы", output)
        self.assertFalse(self.path.exists())

    def test_corrupt_data_and_invalid_records_are_preserved(self):
        self.seed()
        bad_data = [
            "broken",
            "{}",
            "[1]",
            '[{"ID":1}]',
            json.dumps([{**ROWS[0], "age": True}]),
            json.dumps([{**ROWS[0], "extra": 1}]),
            json.dumps([ROWS[0], ROWS[0]]),
            json.dumps([{**ROWS[0], "ID": 0}]),
        ]
        for contents in bad_data:
            with self.subTest(contents=contents):
                self.path.write_text(contents, encoding="utf-8")
                output = self.cli('insert into users values ("X", 1, true)\nexit\n')
                self.assertIn("Ошибка валидации:", output)
                self.assertEqual(self.path.read_text(encoding="utf-8"), contents)

    def test_drop_removes_data_and_recreate_starts_empty(self):
        self.seed()
        self.cli("drop_table users\ny\nexit\n")
        self.assertFalse(self.path.exists())
        self.cli(
            'create_table users name:str\ninsert into users values ("New")\nexit\n'
        )
        self.assertEqual(self.rows(), [{"ID": 1, "name": "New"}])

    def test_orphan_data_is_not_overwritten_when_creating_table(self):
        self.seed()
        (self.root / "db_meta.json").write_text("{}")
        original = self.path.read_bytes()
        output = self.cli("create_table users name:str\nexit\n")
        self.assertIn("уже существует без схемы", output)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(json.loads((self.root / "db_meta.json").read_text()), {})

    def test_only_id_table_accepts_empty_values(self):
        output = self.cli(
            "create_table ids ID:int\ninsert into ids values ()\ninfo ids\nexit\n"
        )
        self.assertIn("Запись с ID=1 успешно добавлена", output)
        self.assertEqual(
            json.loads((self.root / "data/ids.json").read_text()), [{"ID": 1}]
        )


class StorageFailureTests(unittest.TestCase):
    def test_table_helpers_validate_names_and_round_trip(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):
            self.assertEqual(load_table_data("users"), [])
            save_table_data("users", ROWS)
            self.assertEqual(load_table_data("users"), ROWS)
            for name in ("../users", "/users", "bad-name"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    save_table_data(name, [])

    def test_atomic_data_write_failure_preserves_original_and_reports_no_success(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):
            save_table_data("users", ROWS)
            path = Path("data/users.json")
            original = path.read_bytes()
            with (
                patch("primitive_db.utils.os.replace", side_effect=PermissionError),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                execute_crud(
                    METADATA, parse_command("update users set age=29 where ID=1")
                )
            self.assertEqual(path.read_bytes(), original)
            self.assertIn("Ошибка чтения или сохранения файла", output.getvalue())
            self.assertNotIn("успешно", output.getvalue())
            self.assertEqual(list(Path("data").glob("*.tmp")), [])

    def test_drop_failure_restores_metadata_and_keeps_data(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):
            Path("db_meta.json").write_text(json.dumps(METADATA))
            save_table_data("users", ROWS)
            with (
                patch(
                    "primitive_db.engine.delete_table_data", side_effect=PermissionError
                ),
                patch("builtins.input", return_value="y"),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                execute_table_command(copy.deepcopy(METADATA), "drop_table", ["users"])
            self.assertEqual(json.loads(Path("db_meta.json").read_text()), METADATA)
            self.assertEqual(load_table_data("users"), ROWS)
            self.assertNotIn("успешно удалена", output.getvalue())


if __name__ == "__main__":
    unittest.main()
