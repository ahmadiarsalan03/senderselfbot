"""Command parsing utilities for Persian commands."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CommandType(str, Enum):
    ADD_ACCOUNT = "add_account"
    LIST_ACCOUNTS = "list_accounts"
    LIST_REPORTS = "list_reports"
    EXTRACT_USERNAMES = "extract_usernames"
    UNKNOWN = "unknown"


@dataclass
class ParsedCommand:
    type: CommandType
    argument: Optional[int] = None


ADD_ACCOUNT_KEYWORDS = {"اضافه کردن اکانت", "افزودن اکانت"}
LIST_ACCOUNTS_KEYWORDS = {"لیست اکانت ها", "لیست اکانت‌ها"}
LIST_REPORTS_KEYWORDS = {"لیست ریپورت ها", "لیست ریپورت‌ها"}
EXTRACT_PATTERN = re.compile(r"^استخراج\s+(\d+)$")
GREETING_KEYWORDS = {"سلام"}


def parse_command(text: Optional[str]) -> ParsedCommand:
    """Return a :class:`ParsedCommand` based on the provided text."""

    if not text:
        return ParsedCommand(CommandType.UNKNOWN)

    normalized = text.strip()

    if normalized in ADD_ACCOUNT_KEYWORDS:
        return ParsedCommand(CommandType.ADD_ACCOUNT)
    if normalized in LIST_ACCOUNTS_KEYWORDS:
        return ParsedCommand(CommandType.LIST_ACCOUNTS)
    if normalized in LIST_REPORTS_KEYWORDS:
        return ParsedCommand(CommandType.LIST_REPORTS)

    extract_match = EXTRACT_PATTERN.match(normalized)
    if extract_match:
        count = int(extract_match.group(1))
        return ParsedCommand(CommandType.EXTRACT_USERNAMES, argument=count)

    return ParsedCommand(CommandType.UNKNOWN)


def contains_greeting(text: Optional[str]) -> bool:
    if not text:
        return False
    return any(keyword in text for keyword in GREETING_KEYWORDS)
