"""Приветствие и основной цикл обработки команд."""

import prompt


def print_help() -> None:
    """Показать доступные команды."""
    print("<command> exit - выйти из программы")
    print("<command> help - справочная информация")


def welcome() -> None:
    """Приветствовать пользователя и обрабатывать команды до выхода."""
    print("Первая попытка запустить проект!\n\n***")
    print_help()

    while True:
        try:
            command = prompt.string("Введите команду: ", empty=True)
        except (EOFError, KeyboardInterrupt):
            print("\nВыход из программы.")
            return

        command = (command or "").strip()
        if not command:
            continue
        if command == "exit":
            print("Выход из программы.")
            return
        if command == "help":
            print_help()
        else:
            print(f"Неизвестная команда: {command}. Введите help для справки.")
