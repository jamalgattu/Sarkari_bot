# Sarkari_bot

Automated job alert bot that scrapes [sarkariresult.com.cm](https://sarkariresult.com.cm)'s RSS feed for new govt job/exam postings and pushes them straight to a Telegram channel — no manual checking needed.

Built entirely phone-only, zero budget, running on GitHub Actions.

## How it works

1. Parses the sarkariresult.com RSS feed with `feedparser`.
2. Compares each entry's GUID against `Checked.txt` to skip anything already posted.
3. For every new entry, visits the job's page and scrapes the actual "Apply Online" link using `BeautifulSoup`.
4. Sends a formatted message (title + apply link) to a Telegram channel via the raw Bot API.
5. Appends the new GUIDs to `Checked.txt` so they're not posted again next run.

## Files

| File | Purpose |
|---|---|
| `Parser.py` | Main script — fetch, dedupe, scrape, send, save |
| `Checked.txt` | Persisted set of already-seen job GUIDs |
| `.github/workflows/` | GitHub Actions workflow to run the script on a schedule |

## Environment variables

The script reads these from the environment (set as GitHub Actions secrets):

| Variable | Description |
|---|---|
| `URL` | RSS feed URL to scrape |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from BotFather |
| `TELEGRAM_CHANNEL_ID` | Target channel/chat ID to post alerts to |

## Setup

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather) and get the token.
2. Add the bot as admin to your target channel and note the channel ID.
3. In your fork's repo settings, add `URL`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHANNEL_ID` as Actions secrets.
4. The workflow in `.github/workflows/` runs the script on schedule (edit the cron as needed).

## Stack

Python · `feedparser` · `BeautifulSoup` · `requests` · GitHub Actions (scheduler + free compute)

