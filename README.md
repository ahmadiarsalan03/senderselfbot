# Telegram Self-Management Bot

> **Disclaimer:** This project is provided for educational and research purposes only. You must comply with Telegram's Terms of Service, regional privacy regulations, and obtain consent from all affected parties before automating actions. Never use the bot for spam, harassment, or impersonation.

## Overview
This repository contains an asynchronous Telegram "self-bot" manager written with [Telethon](https://docs.telethon.dev). It allows you to securely manage multiple user accounts from a single process, monitor your outgoing messages, run Persian-language management commands, and perform targeted automations such as username extraction and @spambot status checks.

Key capabilities include:

- Guided login flow with OTP and optional 2FA password handling.
- Persistent storage of session files and encrypted metadata.
- Persian command parsing (e.g., `اضافه کردن اکانت`, `لیست ریپورت ها`).
- Automated @spambot report checks across all active sessions.
- Username extraction from group chats with rate-limited scraping.
- Auto-reply (message edit) for configurable greeting keywords.
- JSON-backed storage for accounts, reports, and extracted usernames.
- Built-in logging, graceful shutdown, and retry-friendly concurrency.

## Project Layout
```
.
├── config.example.ini        # Template for configuration
├── data/                     # Default storage directory (created at runtime)
├── requirements.txt          # Python dependencies
├── src/
│   ├── __init__.py
│   ├── account_manager.py    # Core Telethon logic and command handlers
│   ├── command_parser.py     # Persian command parsing utilities
│   ├── config.py             # Config loader and directory initialisation
│   ├── main.py               # Async entry point with graceful shutdown
│   ├── security.py           # Encryption helpers (Fernet wrapper)
│   └── storage.py            # JSON persistence for accounts/reports/extracts
└── tests/
    ├── __init__.py
    ├── test_command_parser.py
    └── test_storage.py
```

## Requirements
- Python 3.10+
- A Telegram API ID and API hash from [my.telegram.org](https://my.telegram.org/apps)
- A generated [Fernet](https://cryptography.io/en/latest/fernet/) key for encrypting sensitive metadata

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration
1. Copy the sample configuration:
   ```bash
   cp config.example.ini config.ini
   ```
2. Fill in your API credentials and Fernet key inside `config.ini`.
3. Ensure the storage directory (`[storage] root`) is accessible. The bot will create `sessions/`, `extracts/`, and a JSON database under that root automatically.

Sensitive values (phone numbers, OTP codes, passwords) are **never logged** and phone numbers are stored encrypted in the JSON database. Session files are saved under `<root>/sessions/` and should be protected with filesystem permissions.

## Running the Bot
Launch the manager with:

```bash
python -m src.main --config config.ini --log-level INFO
```

The process will connect to all stored sessions and remain idle until you stop it (Ctrl+C). Use the commands below from any of your logged-in accounts (Saved Messages, private chats, or groups). Commands must be sent by the account itself (outgoing messages).

## Supported Commands
| Command (Persian)            | Description |
|------------------------------|-------------|
| `اضافه کردن اکانت`           | Start the interactive login wizard. Asks for phone, code, and password if 2FA is enabled. Saves a session file on success. |
| `لیست اکانت ها`             | Display a masked list of stored accounts with usernames and online/offline status. |
| `لیست ریپورت ها`            | Query @spambot for each session, store the responses, and report clean/reported status. |
| `استخراج X` (reply in group) | Extract up to `X` usernames with public handles from the current group and send the list to Saved Messages. Stores the extraction in the JSON database and saves a text file under `extracts/`. |

### Keyword Auto-response
If you send a message containing `سلام`, the bot will edit that same message to respond with `علیک سلام`. Only messages that the account itself can edit are modified.

### Rate Limits & Backoff
All long-running tasks (e.g., @spambot queries) run with concurrent throttling and short delays to stay friendly with Telegram rate limits. If a request fails due to network issues or flood waits, the error is captured in the report summary so you can retry later.

## Data Storage
The JSON database (`<root>/state.json`) includes:
- Encrypted phone numbers and usernames for each account.
- Cached report results from the most recent @spambot check.
- Username extraction history with timestamps and chat metadata.

Extracted usernames are additionally written to timestamped text files inside `<root>/extracts/` for auditing.

## Example Interaction
Below is a simulated interaction using the Persian commands:

```
Me: اضافه کردن اکانت
Bot: Please enter your phone number:
Me: +98**********
Bot: Enter the login code sent by Telegram:
Me: 12345
Bot: Your account has 2-step verification. Please enter your password:
Me: mypassword
Bot (edits): ✅ Account successfully added and session saved.

Me: لیست اکانت ها
Bot: 📋 Stored accounts:
Bot: • ***1234 | username | online

Me: لیست ریپورت ها
Bot: 📊 Report summary:
Bot: • ***1234 | username | clean

(In a group, replying to a message)
Me: استخراج 50
Bot: ✅ Sent 50 usernames to Saved Messages.
(Saved Messages) Bot: Extracted 50 usernames from Group Name ...

Me: سلام
Bot (edit): علیک سلام
```

## Testing
Basic unit tests cover command parsing and JSON persistence. Run them with:

```bash
pytest
```

## Security, Ethics & Legal Compliance
- Only operate accounts you own or have explicit permission to manage.
- Do **not** scrape, store, or redistribute personal data without consent.
- Avoid mass messaging, unsolicited outreach, or any behaviour that could be construed as spam.
- Respect Telegram's [Terms of Service](https://telegram.org/tos). Automation against their guidelines may lead to account bans.
- Keep `api_id`, `api_hash`, OTP codes, and passwords secret. The bot never logs these values and stores phone numbers encrypted.
- Review applicable privacy laws (e.g., GDPR, CCPA) before capturing any user-generated data.

If you are unsure whether a use-case is compliant, run the bot in **dry-run mode** or abstain entirely.

## Troubleshooting
- **Invalid API credentials:** Double-check `api_id` and `api_hash` in `config.ini`.
- **Flood or rate-limit errors:** Wait before retrying @spambot or extraction commands.
- **Session expired:** Remove the stale `.session` file and re-run `اضافه کردن اکانت`.
- **Encryption errors:** Regenerate the Fernet key and update both `config.ini` and existing stored data (deleting `state.json` if necessary).

## License
This project is distributed under the MIT license. See `LICENSE` (if provided) or contact the author for details.
