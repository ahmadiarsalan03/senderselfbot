"""JSON backed persistence for account metadata, reports and extracts."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .security import SecretsBox, mask_phone


@dataclass
class AccountRecord:
    """Represents metadata about a Telegram account."""

    phone_encrypted: str
    session_path: str
    username: Optional[str] = None
    api_id_encrypted: Optional[str] = None
    api_hash_encrypted: Optional[str] = None

    def masked_phone(self, secrets: SecretsBox) -> str:
        try:
            phone = secrets.decrypt(self.phone_encrypted)
        except Exception:
            return "***"
        return mask_phone(phone)


@dataclass
class ReportRecord:
    username: Optional[str]
    phone_masked: str
    status: str
    response: str


@dataclass
class ExtractRecord:
    chat_id: int
    chat_title: Optional[str]
    count: int
    usernames: List[str]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Storage:
    """Manages persistence for the bot using a JSON document."""

    path: Path
    secrets: SecretsBox
    data: Dict[str, List[Dict[str, str]]] = field(
        default_factory=lambda: {"accounts": [], "reports": [], "extracts": []}
    )

    def __post_init__(self) -> None:
        if self.path.exists():
            self._load()
        else:
            self._save()

        # Ensure all required keys exist (for backwards compatibility)
        for key in ("accounts", "reports", "extracts"):
            self.data.setdefault(key, [])

    # Account management -------------------------------------------------
    def list_accounts(self) -> List[AccountRecord]:
        return [AccountRecord(**item) for item in self.data.get("accounts", [])]

    def add_account(self, record: AccountRecord) -> None:
        accounts = self.data.setdefault("accounts", [])
        accounts = [acc for acc in accounts if acc.get("session_path") != record.session_path]
        accounts.append(asdict(record))
        self.data["accounts"] = accounts
        self._save()

    def update_username(self, session_path: str, username: Optional[str]) -> None:
        for item in self.data.setdefault("accounts", []):
            if item["session_path"] == session_path:
                item["username"] = username
                break
        self._save()

    # Report management --------------------------------------------------
    def store_reports(self, reports: Iterable[ReportRecord]) -> None:
        self.data["reports"] = [asdict(report) for report in reports]
        self._save()

    def get_reports(self) -> List[ReportRecord]:
        return [ReportRecord(**item) for item in self.data.get("reports", [])]

    # Extract management -------------------------------------------------
    def add_extract(self, record: ExtractRecord) -> None:
        extracts = self.data.setdefault("extracts", [])
        extracts.append(asdict(record))
        self._save()

    def list_extracts(self) -> List[ExtractRecord]:
        return [ExtractRecord(**item) for item in self.data.get("extracts", [])]

    # Internal helpers ---------------------------------------------------
    def _load(self) -> None:
        self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
