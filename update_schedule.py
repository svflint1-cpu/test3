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

TRAIN_RE = re.compile(r"^\d{4,5}$")
TIME_RE = re.compile(r"^\d{2}\.\d{2}$")


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
    text = soup.get_text("\n", strip=True).replace("\xa0", " ")
    lines = [normalize_space(x) for x in text.splitlines() if normalize_space(x)]

    # Берём только хвост страницы после блока с расписанием, чтобы не ловить "2026" из заголовка.
    start_idx = None
    for i, line in enumerate(lines):
        if line == "Электрички и пригородные поезда":
            start_idx = i
            break

    if start_idx is None:
        preview = "\n".join(lines[:120])
        raise RuntimeError("Не найден блок 'Электрички и пригородные поезда'. Начало текста:\n" + preview)

    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if lines[i].startswith("Выполнен поиск без указания даты.") or lines[i] == "Напишите нам":
            end_idx = i
            break

    block = lines[start_idx:end_idx]

    # Ищем номера поездов только внутри блока расписания.
    train_positions = []
    for i, line in enumerate(block):
        if TRAIN_RE.fullmatch(line):
            # Берём только если рядом реально есть времена — так не ловим цену, километры и т.п.
            nearby = block[i:i+12]
            times_near = [x for x in nearby if TIME_RE.fullmatch(x)]
            if len(times_near) >= 2:
                train_positions.append(i)

    if not train_positions:
        preview = "\n".join(block[:150])
        raise RuntimeError("Не найдены поезда внутри блока расписания. Блок:\n" + preview)

    records = []
    for idx, pos in enumerate(train_positions):
        next_pos = train_positions[idx + 1] if idx + 1 < len(train_positions) else len(block)
        chunk = block[pos:next_pos]

        train_no = chunk[0]
        star = len(chunk) > 1 and chunk[1] == "*"

        times = [x for x in chunk if TIME_RE.fullmatch(x)]
        if len(times) < 2:
            continue

        dep_raw, arr_raw = times[0], times[1]
        departure = dep_raw.replace(".", ":")
        arrival = arr_raw.replace(".", ":")

        route_from = ""
        route_to = ""
        if "→" in chunk:
            arrow_idx = chunk.index("→")
            if arrow_idx > 0 and arrow_idx + 1 < len(chunk):
                route_from = chunk[arrow_idx - 1]
                route_to = chunk[arrow_idx + 1]

        station_from = ""
        station_to = ""
        try:
            dep_idx = chunk.index(dep_raw)
            if dep_idx + 1 < len(chunk):
                station_from = chunk[dep_idx + 1]
            arr_idx = chunk.index(arr_raw, dep_idx + 1)
            if arr_idx + 1 < len(chunk):
                station_to = chunk[arr_idx + 1]
        except ValueError:
            pass

        duration = ""
        for item in chunk:
            if item not in {dep_raw, arr_raw} and re.search(r"\d", item) and ("ч" in item or "м" in item):
                duration = item
                break

        schedule = ""
        for item in reversed(chunk):
            low = item.lower()
            if "график" in low:
                schedule = item.replace(" - посмотреть", "")
                break
        if not schedule:
            schedule = "не указан"

        records.append({
            "train_no": train_no + ("*" if star else ""),
            "route_from": route_from,
            "route_to": route_to,
            "station_from": station_from,
            "station_to": station_to,
            "departure": departure,
            "arrival": arrival,
            "duration": duration,
            "schedule": schedule,
        })

    if not records:
        preview = "\n".join(block[:150])
        raise RuntimeError("После парсинга список поездов пуст. Блок:\n" + preview)

    return records


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
