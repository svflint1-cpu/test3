import json
import re
import os
from pathlib import Path
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

ROUTES = [
    {
        "name": "forward",
        "url": "https://poizdato.net/ru/raspisanie-poezdov/verhovtsevo--kamenskoe/elektrichki/",
        "output": Path("schedule.json"),
        "title": "Верховцево → Каменское",
    },
    {
        "name": "reverse",
        "url": "https://poizdato.net/ru/raspisanie-poezdov/kamenskoe--verhovtsevo/elektrichki/",
        "output": Path("schedule_reverse.json"),
        "title": "Каменское → Верховцево",
    },
]

RECORD_RE = re.compile(
    r'(?P<train>\d{4,5})'
    r'(?:\s+(?P<star>\*))?'
    r'\s+(?P<route_from>.+?)'
    r'\s+→\s+'
    r'(?P<route_to>.+?)'
    r'\s+(?P<dep>\d{2}\.\d{2})'
    r'\s+(?P<station_from>.+?)'
    r'\s+(?P<arr>\d{2}\.\d{2})'
    r'\s+(?P<station_to>.+?)'
    r'\s+(?P<duration>\d+\s*ч\s*\d+\s*м|\d+\s*м)'
    r'(?=\s+\d{4,5}(?:\s+\*)?\s+|\s+Выполнен поиск без указания даты\.|\s+Напишите нам|\Z)',
    re.IGNORECASE | re.DOTALL
)


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8,uk;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_schedule(html: str):
    soup = BeautifulSoup(html, "html.parser")
    raw_text = soup.get_text("\n", strip=True).replace("\xa0", " ")
    text = normalize_space(raw_text)

    start_markers = [
        "Электрички и пригородные поезда",
        "Тип Номер Маршрут Отправление Прибытие В пути График",
    ]

    start_idx = -1
    for marker in start_markers:
        idx = text.find(marker)
        if idx != -1:
            start_idx = idx
            break

    if start_idx == -1:
        raise RuntimeError("Не найден блок расписания на странице.")

    block = text[start_idx:]

    end_markers = [
        "Выполнен поиск без указания даты.",
        "Напишите нам",
    ]
    end_idx = len(block)
    for marker in end_markers:
        idx = block.find(marker)
        if idx != -1:
            end_idx = min(end_idx, idx)

    block = block[:end_idx]
    block = normalize_space(block)

    records = []
    for match in RECORD_RE.finditer(block):
        train_no = match.group("train")
        if match.group("star"):
            train_no += "*"

        records.append({
            "train_no": train_no,
            "route_from": normalize_space(match.group("route_from")),
            "route_to": normalize_space(match.group("route_to")),
            "station_from": normalize_space(match.group("station_from")),
            "station_to": normalize_space(match.group("station_to")),
            "departure": match.group("dep").replace(".", ":"),
            "arrival": match.group("arr").replace(".", ":"),
            "duration": normalize_space(match.group("duration")),
            "schedule": "ежедневно",
        })

    if not records:
        preview = block[:1500]
        raise RuntimeError("Не удалось распарсить поезда. Блок: " + preview)

    # Убираем возможные дубли по номеру поезда, сохраняя порядок
    seen = set()
    deduped = []
    for item in records:
        if item["train_no"] in seen:
            continue
        seen.add(item["train_no"])
        deduped.append(item)

    return deduped


def load_previous(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
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
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text[:4096], "disable_web_page_preview": True},
        timeout=30,
    )
    resp.raise_for_status()


def save_payload(path: Path, route_name: str, route_title: str, route_url: str, items, changes, error=None):
    payload = {
        "route_name": route_name,
        "route_title": route_title,
        "source": route_url,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "has_changes": bool(changes),
        "changes": changes,
        "items": items,
    }
    if error:
        payload["error"] = error
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def process_route(route):
    previous = load_previous(route["output"])
    try:
        html = fetch_html(route["url"])
        items = parse_schedule(html)
    except Exception as e:
        print(f"Ошибка для маршрута {route['name']}: {e}")
        if previous and previous.get("items"):
            print(f"Оставляю старые непустые данные в {route['output']}")
            return False
        save_payload(
            route["output"],
            route["name"],
            route["title"],
            route["url"],
            [],
            [f"Не удалось обновить маршрут: {e}"],
            str(e),
        )
        return False

    old_items = previous.get("items", []) if previous else []
    changes = diff_items(old_items, items) if previous else []

    save_payload(route["output"], route["name"], route["title"], route["url"], items, changes)
    print(f"Saved {len(items)} trains to {route['output']}")

    if changes:
        message = f"⚠️ Изменилось расписание {route['title']}\n\n" + "\n".join(changes[:20])
        send_telegram(message)
        print(f"Sent changes for {route['name']}: {len(changes)}")
    else:
        print(f"Изменений нет: {route['name']}")
    return True


def main():
    results = []
    for route in ROUTES:
        results.append(process_route(route))
    if not any(results):
        print("Ни одно направление не обновилось, но workflow завершён без падения.")


if __name__ == "__main__":
    main()
