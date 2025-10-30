"""Core Telegram account management logic."""
from __future__ import annotations

import asyncio
import getpass
import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from telethon import TelegramClient, events, errors

from .command_parser import CommandType, contains_greeting, parse_command
from .config import Config
from .security import SecretsBox
from .storage import AccountRecord, ExtractRecord, ReportRecord, Storage

LOGGER = logging.getLogger(__name__)

SPAMBOT_USER = "spambot"
SPAMBOT_OKAY_PHRASE = "Good news, no limits are currently applied to your account. You're free as a bird!"


class AccountManager:
    """Manage multiple Telegram accounts and command handling."""

    def __init__(self, config: Config, storage: Storage, secrets: SecretsBox) -> None:
        self.config = config
        self.storage = storage
        self.secrets = secrets
        self.clients: Dict[str, TelegramClient] = {}
        self._runner_tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    async def start_existing_clients(self) -> None:
        """Load and run clients for all accounts stored on disk."""

        for record in self.storage.list_accounts():
            session_path = Path(record.session_path)
            if not session_path.exists():
                LOGGER.warning("Session file %s missing; skipping", session_path)
                continue
            await self._start_client(record)

    async def _start_client(self, record: AccountRecord) -> Optional[TelegramClient]:
        session_path = Path(record.session_path)
        api_id, api_hash = self._resolve_credentials(record)
        if (api_id != self.config.api_id) or (api_hash != self.config.api_hash):
            self.config = replace(self.config, api_id=api_id, api_hash=api_hash)
        client = TelegramClient(session_path, api_id, api_hash)
        try:
            await client.connect()
        except Exception as exc:  # pragma: no cover - network error handling
            LOGGER.exception("Failed to connect client for %s: %s", session_path, exc)
            return None

        if not await client.is_user_authorized():
            LOGGER.warning("Session %s is not authorized anymore", session_path)
            return None

        me = await client.get_me()
        LOGGER.info("Connected to account %s", me.username or me.id)
        self.storage.update_username(str(session_path), getattr(me, "username", None))
        self._register_handlers(client)
        task = asyncio.create_task(client.run_until_disconnected())
        self.clients[str(session_path)] = client
        self._runner_tasks.append(task)
        return client

    def _resolve_credentials(self, record: AccountRecord) -> Tuple[int, str]:
        """Return API credentials for a stored account."""

        if record.api_id_encrypted and record.api_hash_encrypted:
            try:
                api_id = int(self.secrets.decrypt(record.api_id_encrypted))
                api_hash = self.secrets.decrypt(record.api_hash_encrypted)
                if api_hash:
                    return api_id, api_hash
            except Exception:  # pragma: no cover - corrupted data
                LOGGER.warning("Failed to decrypt API credentials for %s", record.session_path)

        return self.config.api_id, self.config.api_hash

    # ------------------------------------------------------------------
    async def ensure_initial_session(self) -> None:
        """Interactively bootstrap the first account if no sessions exist."""

        if any(self.config.sessions_dir.glob("*.session")):
            return

        LOGGER.info("No existing session files found; starting interactive setup")
        print("No Telegram sessions found. Let's add your first account.")

        phone = await self._prompt_text("Enter your phone number: ", allow_empty=False)
        api_id = await self._prompt_api_id()
        api_hash = await self._prompt_api_hash()

        normalized_phone = phone.replace(" ", "")
        session_path = (self.config.sessions_dir / f"{normalized_phone}.session").resolve()

        client = TelegramClient(session_path, api_id, api_hash)
        try:
            await client.connect()
            await client.send_code_request(phone)
        except errors.PhoneNumberInvalidError:
            print("❌ The provided phone number is invalid. Aborting setup.")
            await client.disconnect()
            return
        except Exception as exc:  # pragma: no cover - network errors
            print(f"❌ Failed to send code: {exc}")
            await client.disconnect()
            return

        print("A verification code has been sent to your Telegram app.")
        while True:
            code = await self._prompt_text("Enter the login code: ", allow_empty=False)
            try:
                await client.sign_in(phone=phone, code=code.replace(" ", ""))
                break
            except errors.SessionPasswordNeededError:
                while True:
                    password = await self._prompt_password(
                        "Your account has 2FA enabled. Enter your password: "
                    )
                    try:
                        await client.sign_in(password=password)
                        break
                    except errors.PasswordHashInvalidError:
                        print("❌ Invalid password provided. Try again.")
                if await client.is_user_authorized():
                    break
            except errors.PhoneCodeInvalidError:
                print("❌ Invalid code. Please try again.")
            except errors.PhoneCodeExpiredError:
                print("❌ Code expired. Requesting a new one.")
                await client.send_code_request(phone)

        if not await client.is_user_authorized():
            print("❌ Unable to authorize the account. Aborting setup.")
            await client.disconnect()
            return

        me = await client.get_me()
        record = self._build_account_record(
            phone=phone,
            session_path=session_path,
            username=getattr(me, "username", None),
            api_id=api_id,
            api_hash=api_hash,
        )
        self.storage.add_account(record)
        self.clients[str(session_path)] = client
        self._register_handlers(client)
        self._runner_tasks.append(asyncio.create_task(client.run_until_disconnected()))

        if (api_id != self.config.api_id) or (api_hash != self.config.api_hash):
            self.config = replace(self.config, api_id=api_id, api_hash=api_hash)

        print("✅ Account successfully added and session saved.")

    def _register_handlers(self, client: TelegramClient) -> None:
        @client.on(events.NewMessage(incoming=False))
        async def _(event: events.NewMessage.Event) -> None:
            await self._handle_outgoing_message(event)

        @client.on(events.NewMessage(incoming=True))
        async def _(event: events.NewMessage.Event) -> None:
            await self._handle_incoming_message(event)

    # ------------------------------------------------------------------
    async def _handle_outgoing_message(self, event: events.NewMessage.Event) -> None:
        text = event.raw_text or ""
        command = parse_command(text)

        if command.type != CommandType.UNKNOWN:
            await self._dispatch_command(command, event)
            return

        if contains_greeting(text):
            try:
                await event.edit("علیک سلام")
            except errors.MessageIdInvalidError:
                LOGGER.debug("Could not edit message %s", event.id)
            except errors.rpcbaseerrors.BadRequestError as exc:  # pragma: no cover - Telethon specifics
                LOGGER.debug("Failed to edit greeting message: %s", exc)

    async def _handle_incoming_message(self, event: events.NewMessage.Event) -> None:
        # Incoming messages currently do not trigger commands but this hook is
        # available for future monitoring logic.
        if event.is_private and contains_greeting(event.raw_text):
            LOGGER.debug("Greeting received in private chat %s", event.chat_id)

    # ------------------------------------------------------------------
    async def _dispatch_command(self, command, event: events.NewMessage.Event) -> None:
        if command.type == CommandType.ADD_ACCOUNT:
            await self._handle_add_account(event)
        elif command.type == CommandType.LIST_ACCOUNTS:
            await self._handle_list_accounts(event)
        elif command.type == CommandType.LIST_REPORTS:
            await self._handle_list_reports(event)
        elif command.type == CommandType.EXTRACT_USERNAMES:
            await self._handle_extract_usernames(event, command.argument or 0)

    # ------------------------------------------------------------------
    async def _handle_add_account(self, event: events.NewMessage.Event) -> None:
        client = event.client
        async with client.conversation(event.chat_id, timeout=180) as conv:
            status_message = await conv.send_message("Please enter your phone number:")
            phone_response = await conv.get_response()
            phone = phone_response.raw_text.strip()

            normalized_phone = phone.replace(" ", "")
            session_path = (self.config.sessions_dir / f"{normalized_phone}.session").resolve()
            temp_client = TelegramClient(session_path, self.config.api_id, self.config.api_hash)

            await status_message.edit("Sending login code…")
            try:
                await temp_client.connect()
                await temp_client.send_code_request(phone)
            except errors.PhoneNumberInvalidError:
                await status_message.edit("❌ Invalid phone number. Aborting.")
                await temp_client.disconnect()
                return
            except Exception as exc:  # pragma: no cover - network errors
                await status_message.edit(f"❌ Failed to send code: {exc}")
                await temp_client.disconnect()
                return

            await status_message.edit("Enter the login code sent by Telegram:")
            code_response = await conv.get_response()
            code = code_response.raw_text.strip().replace(" ", "")

            try:
                await temp_client.sign_in(phone=phone, code=code)
            except errors.SessionPasswordNeededError:
                await status_message.edit(
                    "Your account has 2-step verification. Please enter your password:"
                )
                password_response = await conv.get_response()
                password = password_response.raw_text
                try:
                    await temp_client.sign_in(password=password)
                except errors.PasswordHashInvalidError:
                    await status_message.edit("❌ Invalid password provided.")
                    await temp_client.disconnect()
                    return
                except Exception as exc:  # pragma: no cover - network errors
                    await status_message.edit(f"❌ Failed to verify password: {exc}")
                    await temp_client.disconnect()
                    return
            except errors.PhoneCodeInvalidError:
                await status_message.edit("❌ Invalid code provided. Please try again.")
                await temp_client.disconnect()
                return
            except errors.PhoneCodeExpiredError:
                await status_message.edit("❌ Code expired. Please request a new one.")
                await temp_client.disconnect()
                return
            except Exception as exc:  # pragma: no cover - network errors
                await status_message.edit(f"❌ Failed to sign in: {exc}")
                await temp_client.disconnect()
                return

            me = await temp_client.get_me()
            record = self._build_account_record(
                phone=phone,
                session_path=session_path,
                username=getattr(me, "username", None),
                api_id=self.config.api_id,
                api_hash=self.config.api_hash,
            )
            self.storage.add_account(record)
            await status_message.edit("✅ Account successfully added and session saved.")
            self._register_handlers(temp_client)
            self.clients[str(session_path)] = temp_client
            self._runner_tasks.append(asyncio.create_task(temp_client.run_until_disconnected()))

    # ------------------------------------------------------------------
    async def _handle_list_accounts(self, event: events.NewMessage.Event) -> None:
        records = self.storage.list_accounts()
        if not records:
            await event.respond("No accounts stored yet. Use 'اضافه کردن اکانت' to add one.")
            return

        lines = ["📋 Stored accounts:"]
        for record in records:
            session_key = record.session_path
            client = self.clients.get(session_key)
            status = "online" if client and client.is_connected() else "offline"
            username = record.username or "(no username)"
            masked = record.masked_phone(self.secrets)
            lines.append(f"• {masked} | {username} | {status}")

        await event.respond("\n".join(lines))

    # ------------------------------------------------------------------
    async def _handle_list_reports(self, event: events.NewMessage.Event) -> None:
        if not self.clients:
            await event.respond("No active sessions to query.")
            return

        records_by_session = {record.session_path: record for record in self.storage.list_accounts()}
        semaphore = asyncio.Semaphore(3)
        report_results: List[ReportRecord] = []

        async def check_client(session_path: str, client: TelegramClient) -> None:
            record = records_by_session.get(session_path)
            phone_masked = record.masked_phone(self.secrets) if record else "***"
            username = record.username if record else None
            async with semaphore:
                try:
                    await client.send_message(SPAMBOT_USER, "/start")
                    await asyncio.sleep(2)
                    response_message = await client.get_messages(SPAMBOT_USER, limit=1)
                    if not response_message:
                        raise RuntimeError("No response from @spambot")
                    text = response_message[0].message
                    status = "clean" if SPAMBOT_OKAY_PHRASE in text else "reported"
                except Exception as exc:  # pragma: no cover - network/Telegram errors
                    text = str(exc)
                    status = "error"
                report_results.append(
                    ReportRecord(
                        username=username,
                        phone_masked=phone_masked,
                        status=status,
                        response=text,
                    )
                )

        await asyncio.gather(
            *(check_client(session_path, client) for session_path, client in self.clients.items())
        )
        self.storage.store_reports(report_results)

        summary_lines = ["📊 Report summary:"]
        for report in report_results:
            summary_lines.append(
                f"• {report.phone_masked} | {report.username or '(no username)'} | {report.status}"
            )
        await event.respond("\n".join(summary_lines))

    # ------------------------------------------------------------------
    async def _handle_extract_usernames(self, event: events.NewMessage.Event, limit: int) -> None:
        if limit <= 0:
            await event.respond("Please provide a positive number of usernames to extract.")
            return
        if not event.is_reply:
            await event.respond("این دستور باید به عنوان پاسخ به یک پیام در گروه ارسال شود.")
            return
        if not (event.is_group or event.is_channel):
            await event.respond("Extraction is only supported in groups or supergroups.")
            return

        chat = await event.get_chat()
        usernames: List[str] = []
        async for participant in event.client.iter_participants(event.chat_id, limit=limit * 3):
            username = getattr(participant, "username", None)
            if username:
                usernames.append(f"@{username}")
            if len(usernames) >= limit:
                break

        if not usernames:
            await event.respond("No usernames with public handles were found.")
            return

        text_blob = "\n".join(usernames)
        await event.client.send_message(
            "me",
            f"Extracted {len(usernames)} usernames from {getattr(chat, 'title', 'this chat')}\n{text_blob}",
        )

        if len(usernames) < limit:
            await event.respond(f"Only found {len(usernames)} usernames with public handles.")
        else:
            await event.respond(f"✅ Sent {len(usernames)} usernames to Saved Messages.")

        self.storage.add_extract(
            ExtractRecord(
                chat_id=event.chat_id,
                chat_title=getattr(chat, "title", None),
                count=len(usernames),
                usernames=usernames,
            )
        )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        file_path = self.config.extracts_dir / f"extract-{timestamp}.txt"
        file_path.write_text(text_blob, encoding="utf-8")

    # ------------------------------------------------------------------
    async def stop(self) -> None:
        async with self._lock:
            for client in self.clients.values():
                await client.disconnect()
            for task in self._runner_tasks:
                task.cancel()

    # ------------------------------------------------------------------
    async def wait_forever(self) -> None:
        """Wait indefinitely for clients to run."""

        if not self._runner_tasks:
            await asyncio.Future()
        else:
            await asyncio.gather(*self._runner_tasks)

    # ------------------------------------------------------------------
    def _build_account_record(
        self,
        *,
        phone: str,
        session_path: Path,
        username: Optional[str],
        api_id: int,
        api_hash: str,
    ) -> AccountRecord:
        return AccountRecord(
            phone_encrypted=self.secrets.encrypt(phone),
            session_path=str(session_path),
            username=username,
            api_id_encrypted=self.secrets.encrypt(str(api_id)),
            api_hash_encrypted=self.secrets.encrypt(api_hash),
        )

    async def _prompt_text(self, prompt: str, *, allow_empty: bool = True) -> str:
        while True:
            try:
                value = await asyncio.to_thread(input, prompt)
            except EOFError as exc:  # pragma: no cover - interactive only
                raise RuntimeError("Interactive input aborted") from exc
            value = value.strip()
            if value or allow_empty:
                return value
            print("Input is required.")

    async def _prompt_secret(self, prompt: str, *, allow_empty: bool = False) -> str:
        while True:
            try:
                value = await asyncio.to_thread(getpass.getpass, prompt)
            except EOFError as exc:  # pragma: no cover - interactive only
                raise RuntimeError("Interactive input aborted") from exc
            value = value.strip()
            if value or allow_empty:
                return value
            print("Input cannot be empty.")

    async def _prompt_password(self, prompt: str) -> str:
        return await self._prompt_secret(prompt, allow_empty=False)

    async def _prompt_api_id(self) -> int:
        default = self.config.api_id
        prompt = "Enter your api_id"
        if default:
            prompt = f"{prompt} [{default}]: "
        else:
            prompt = f"{prompt}: "

        while True:
            value = await self._prompt_text(prompt)
            if not value and default:
                return default
            try:
                return int(value)
            except ValueError:
                print("api_id must be an integer.")

    async def _prompt_api_hash(self) -> str:
        has_default = bool(self.config.api_hash)
        if has_default:
            prompt = "Enter your api_hash (leave blank to reuse stored value): "
        else:
            prompt = "Enter your api_hash: "

        while True:
            value = await self._prompt_secret(prompt, allow_empty=has_default)
            if not value and has_default:
                return self.config.api_hash
            if value:
                return value
            print("api_hash cannot be empty.")
