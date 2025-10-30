from cryptography.fernet import Fernet

from src.security import SecretsBox
from src.storage import AccountRecord, ExtractRecord, ReportRecord, Storage


def make_storage(tmp_path):
    key = Fernet.generate_key().decode()
    secrets = SecretsBox(key)
    storage_path = tmp_path / "state.json"
    return Storage(storage_path, secrets), secrets


def test_account_persistence(tmp_path):
    storage, secrets = make_storage(tmp_path)
    record = AccountRecord(
        phone_encrypted=secrets.encrypt("+989121234567"),
        session_path="/tmp/session",
        api_id_encrypted=secrets.encrypt("12345"),
        api_hash_encrypted=secrets.encrypt("hash"),
    )
    storage.add_account(record)

    accounts = storage.list_accounts()
    assert len(accounts) == 1
    assert accounts[0].masked_phone(secrets).startswith("***")
    assert accounts[0].api_id_encrypted is not None
    assert accounts[0].api_hash_encrypted is not None

    storage.update_username("/tmp/session", "username")
    assert storage.list_accounts()[0].username == "username"


def test_reports_and_extracts(tmp_path):
    storage, _ = make_storage(tmp_path)
    report = ReportRecord(username="user", phone_masked="***4567", status="clean", response="ok")
    storage.store_reports([report])
    assert storage.get_reports()[0].status == "clean"

    extract = ExtractRecord(chat_id=123, chat_title="Group", count=2, usernames=["@a", "@b"])
    storage.add_extract(extract)
    stored = storage.list_extracts()
    assert stored[0].chat_id == 123
    assert stored[0].usernames == ["@a", "@b"]
