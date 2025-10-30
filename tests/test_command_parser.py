from src.command_parser import CommandType, contains_greeting, parse_command


def test_parse_add_account():
    command = parse_command("اضافه کردن اکانت")
    assert command.type is CommandType.ADD_ACCOUNT


def test_parse_list_reports():
    command = parse_command("لیست ریپورت ها")
    assert command.type is CommandType.LIST_REPORTS


def test_parse_extract_argument():
    command = parse_command("استخراج 25")
    assert command.type is CommandType.EXTRACT_USERNAMES
    assert command.argument == 25


def test_unknown_command():
    command = parse_command("something else")
    assert command.type is CommandType.UNKNOWN


def test_contains_greeting():
    assert contains_greeting("سلام دوست من")
    assert not contains_greeting("hello")
