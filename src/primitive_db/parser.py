"""Разбор CRUD-команд с сохранением кавычек и типов литералов."""

import ast
import re
import warnings

TOKEN = re.compile(r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s(),='"]+|[(),=]""")
CRUD_COMMANDS = {"insert", "select", "update", "delete", "info"}


def tokenize(text):
    """Разделить команду, сохранив строку с разделителями как один токен."""
    tokens = []
    end = 0
    for match in TOKEN.finditer(text):
        if text[end : match.start()].strip():
            raise ValueError("Некорректные кавычки в команде.")
        tokens.append(match.group())
        end = match.end()
    if text[end:].strip():
        raise ValueError("Некорректные кавычки в команде.")
    return tokens


def parse_value(token):
    """Прочитать int, bool или строку в кавычках без выполнения кода."""
    if token in {"true", "false"}:
        return token == "true"
    if re.fullmatch(r"[+-]?[0-9]+", token):
        return int(token)
    if token.startswith(('"', "'")):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", SyntaxWarning)
                value = ast.literal_eval(token)
        except (SyntaxError, ValueError) as error:
            raise ValueError(f"Некорректная строка: {token}.") from error
        if isinstance(value, str):
            return value
    raise ValueError(
        f"Некорректное значение: {token}. "
        "Используйте целое число, true/false или строку в кавычках."
    )


def _assignment(tokens):
    if len(tokens) != 3 or tokens[1] != "=" or not tokens[0].isidentifier():
        raise ValueError("Ожидается условие вида <столбец> = <значение>.")
    return {tokens[0]: parse_value(tokens[2])}


def parse_where_clause(text):
    """Превратить одно условие равенства в словарь."""
    return _assignment(tokenize(text))


def _read_set(tokens):
    result = {}
    position = 0
    while True:
        assignment = _assignment(tokens[position : position + 3])
        if result.keys() & assignment.keys():
            raise ValueError("Столбец повторяется в SET.")
        result.update(assignment)
        position += 3
        if position >= len(tokens) or tokens[position] != ",":
            return result, position
        position += 1


def parse_set_clause(text):
    """Превратить присваивания через запятую в словарь."""
    tokens = tokenize(text)
    result, position = _read_set(tokens)
    if position != len(tokens):
        raise ValueError("Некорректный SET: разделяйте присваивания запятыми.")
    return result


def _table_name(token):
    name = parse_value(token) if token.startswith(('"', "'")) else token
    if not isinstance(name, str) or not name.isidentifier():
        raise ValueError(f"Некорректное имя таблицы: {token}.")
    return name


def parse_command(text):
    """Разобрать полную CRUD-команду, не игнорируя лишние аргументы."""
    tokens = tokenize(text)
    if not tokens:
        raise ValueError("Пустая команда.")
    command = tokens[0]
    result = {"command": command}
    if command == "info" and len(tokens) == 2:
        result["table_name"] = _table_name(tokens[1])
        return result
    if command == "insert":
        if (
            len(tokens) < 6
            or tokens[1] != "into"
            or tokens[3:5] != ["values", "("]
            or tokens[-1] != ")"
        ):
            raise ValueError("Использование: insert into <таблица> values (...).")
        values = tokens[5:-1]
        if values and (len(values) % 2 == 0 or any(t != "," for t in values[1::2])):
            raise ValueError("Разделяйте значения запятыми без пустых элементов.")
        result.update(
            table_name=_table_name(tokens[2]),
            values=[parse_value(token) for token in values[::2]],
        )
        return result
    if command in {"select", "delete"}:
        if len(tokens) < 3 or tokens[1] != "from":
            raise ValueError(f"Использование: {command} from <таблица> [where ...].")
        result["table_name"] = _table_name(tokens[2])
        if len(tokens) == 3 and command == "select":
            result["where_clause"] = None
            return result
        if len(tokens) < 4 or tokens[3] != "where":
            raise ValueError("Ожидается условие WHERE.")
        result["where_clause"] = _assignment(tokens[4:])
        return result
    if command == "update":
        if len(tokens) < 10 or tokens[2] != "set":
            raise ValueError("Использование: update <таблица> set ... where ... .")
        result["table_name"] = _table_name(tokens[1])
        result["set_clause"], position = _read_set(tokens[3:])
        remainder = tokens[3 + position :]
        if not remainder or remainder[0] != "where":
            raise ValueError("Ожидается условие WHERE после SET.")
        result["where_clause"] = _assignment(remainder[1:])
        return result
    raise ValueError(f"Некорректная команда: {text}.")
