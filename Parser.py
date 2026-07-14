import feedparser
import os
from bs4 import BeautifulSoup
import requests

url = "https://www.sarkariresult.com/feed/"

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def load_seen_guid():
    guid_set = set()
    if os.path.exists("Checked.txt"):
        with open("Checked.txt", "r") as f:
            for line in f:
                guid_set.add(line.strip())
    return guid_set


def fetch_new_jobs():
    seen_guid = load_seen_guid()
    new_jobs = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    feed = feedparser.parse(url, request_headers=headers)
    raw = requests.get(url).text
    print(raw[:500])
    print(feed.bozo)
    print(feed.bozo_exception)
    print(len(feed.entries))
    print(len(feed.entries))
    for entries in feed.entries:
        if entries.guid in seen_guid:
            pass
        else:
            link=get_apply_link (entries.link)
            line = f"📌{entries.title}\n\n🗓️{entries.published}\n\n🔗{link}"
            new_jobs.append(line)
            seen_guid.add(entries.guid)
    return new_jobs, seen_guid


def save_seen_guid(seen_guid):
    k = "\n".join(seen_guid)
    with open("Checked.txt", "w") as f:
        f.write(k)


def get_apply_link(link):
    HTML = requests.get(link).text
    soup = BeautifulSoup(HTML, "html.parser")
    label = soup.find(string="Apply Online")
    if label is None:
        return None
    a = label.find_next("a")
    return a["href"]


def send_message(chat_id, text):
    response = requests.get(TELEGRAM_URL, params={"chat_id": chat_id, "text": text})
    return response.text


new_jobs, seen_guid = fetch_new_jobs()

for job in new_jobs:
    print(send_message(CHANNEL_ID, job))

save_seen_guid(seen_guid)

