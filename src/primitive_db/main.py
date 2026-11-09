#!/usr/bin/env python3
"""Точка входа консольного приложения."""

from primitive_db.engine import welcome


def main() -> None:
    """Запустить приложение."""
    welcome()


if __name__ == "__main__":
    main()
