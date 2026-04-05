import json
import re
import os
from pathlib import Path
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL = "https://poizdato.net/ru/raspisanie-poezdov/verhovtsevo--kamenskoe/elektrichki/"
OUTPUT = Path("schedule.json")

def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()

def fetch_html() -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "keep-alive",
    }
    resp = requests.get(URL, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text

def parse_schedule(html: str):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True).replace("\xa0", " ")

    lines = [normalize_space(x) for x in text.splitlines() if normalize_space(x)]

    # ищем все позиции поездов (6005, 6015 и т.д.)
    train_positions = [
        i for i, line in enumerate(lines)
        if re.fullmatch(r"\d{4,5}", line)
    ]

    if not train_positions:
        raise RuntimeError("Не найдено ни одного поезда")

    records = []

    for idx, pos in enumerate(train_positions):
        next_pos = train_positions[idx + 1] if idx + 1 < len(train_positions) else len(lines)
        chunk = lines[pos:next_pos]

        train_no = chunk[0]

        times = [x for x in chunk if re.fullmatch(r"\d{2}\.\d{2}", x)]
        if len(times) < 2:
            continue

        departure = times[0].replace(".", ":")
        arrival = times[1].replace(".", ":")

        route_from = ""
        route_to = ""

        if "→" in chunk:
            arrow_idx = chunk.index("→")
            if arrow_idx > 0 and arrow_idx + 1 < len(chunk):
                route_from = chunk[arrow_idx - 1]
                route_to = chunk[arrow_idx + 1]

        records.append({
            "train_no": train_no,
            "route_from": route_from,
            "route_to": route_to,
            "station_from": route_from,
            "station_to": route_to,
            "departure": departure,
            "arrival": arrival,
            "duration": "",
            "schedule": "ежедневно"
        })

    return records

def load_previous():
    if not OUTPUT.exists():
        return None
    try:
        return json.loads(OUTPUT.read_text(encoding="utf-8"))
    except Exception:
        return None

def diff_items(old_items, new_items):
    old_map = {item["train_no"]: item for item in old_items}
    new_map = {item["train_no"]: item for item in new_items}
    changes = []

    for train_no in sorted(set(new_map) - set(old_map)):
        item = new_map[train_no]
        changes.append(f"🆕 Новый поезд {train_no}: {item['departure']} → {item['arrival']}")

    for train_no in sorted(set(old_map) - set(new_map)):
        item = old_map[train_no]
        changes.append(f"❌ Поезд исчез {train_no}: раньше было {item['departure']} → {item['arrival']}")

    for train_no in sorted(set(new_map) & set(old_map)):
        old_item = old_map[train_no]
        new_item = new_map[train_no]
        tracked_fields = {
            "departure": "отправление",
            "arrival": "прибытие",
            "duration": "время в пути",
            "schedule": "график",
        }
        local_changes = []
        for key, label in tracked_fields.items():
            if old_item.get(key) != new_item.get(key):
                local_changes.append(f"{label}: {old_item.get(key, '')} → {new_item.get(key, '')}")
        if local_changes:
            changes.append(f"⚠️ Поезд {train_no}: " + "; ".join(local_changes))

    return changes

def send_telegram(text):
    token = os.getenv("BOT_TOKEN", "").strip()
    chat_id = os.getenv("CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Telegram secrets не заданы, пропускаю уведомление.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": chat_id,
        "text": text[:4096],
        "disable_web_page_preview": True,
    }, timeout=30)
    resp.raise_for_status()

def main():
    previous = load_previous()
    html = fetch_html()
    items = parse_schedule(html)

    old_items = previous.get("items", []) if previous else []
    changes = diff_items(old_items, items) if previous else []

    payload = {
        "source": URL,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "has_changes": bool(changes),
        "changes": changes,
        "items": items,
    }

    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(items)} trains to {OUTPUT}")

    if changes:
        message = "⚠️ Изменилось расписание Верховцево → Каменское\\n\\n" + "\\n".join(changes[:20])
        send_telegram(message)
        print(f"Sent changes: {len(changes)}")
    else:
        print("Изменений нет.")

if __name__ == "__main__":
    main()
