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


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def fetch_html(url: str) -> str:
    session = requests.Session()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8,uk;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
    }
    resp = session.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_schedule(html: str):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True).replace("\xa0", " ")

    start_marker = "Тип Номер Маршрут Отправление"
    end_marker = "Выполнен поиск без указания даты."

    start_idx = text.find(start_marker)

    # Основной вариант — старая структура страницы
    if start_idx != -1:
        end_idx = text.find(end_marker, start_idx)
        if end_idx == -1:
            end_idx = len(text)

        block = text[start_idx:end_idx]
        lines = [normalize_space(x) for x in block.splitlines() if normalize_space(x)]
        train_positions = [i for i, line in enumerate(lines) if re.match(r"^\d{4,5}\*?$", line)]

        if train_positions:
            records = []
            for idx, pos in enumerate(train_positions):
                next_pos = train_positions[idx + 1] if idx + 1 < len(train_positions) else len(lines)
                chunk = lines[pos:next_pos]

                train_no = chunk[0].replace("*", "")
                times = [x for x in chunk if re.match(r"^\d{2}\.\d{2}$", x)]
                if len(times) < 2:
                    continue

                departure, arrival = times[0], times[1]
                duration = next((x for x in chunk if re.search(r"\bч\b|\bм\b", x) and re.search(r"\d", x)), "")
                schedule = ""
                for x in reversed(chunk):
                    if "график" in x.lower():
                        schedule = x.replace(" - посмотреть", "")
                        break

                arrow_idx = chunk.index("→") if "→" in chunk else -1
                route_from, route_to = "", ""
                if arrow_idx > 0 and arrow_idx + 1 < len(chunk):
                    route_from = chunk[arrow_idx - 1]
                    route_to = chunk[arrow_idx + 1]

                station_from, station_to = "", ""
                try:
                    dep_idx = chunk.index(departure)
                    if dep_idx + 1 < len(chunk):
                        station_from = chunk[dep_idx + 1]
                    arr_idx = chunk.index(arrival, dep_idx + 1)
                    if arr_idx + 1 < len(chunk):
                        station_to = chunk[arr_idx + 1]
                except ValueError:
                    pass

                records.append({
                    "train_no": train_no,
                    "route_from": route_from,
                    "route_to": route_to,
                    "station_from": station_from,
                    "station_to": station_to,
                    "departure": departure.replace(".", ":"),
                    "arrival": arrival.replace(".", ":"),
                    "duration": duration,
                    "schedule": schedule,
                })

            if records:
                return records

    # Запасной вариант — если сайт отдал другую структуру
    full_text = normalize_space(text)

    # Пытаемся вытащить число электричек из описания
    count_match = re.search(
        r"включает\s+(\d+)\s+электрич",
        full_text,
        flags=re.IGNORECASE
    )

    # Пытаемся вытащить рекомендованную/скоростную электричку
    fast_match = re.search(
        r"отправляется\s+в\s+(\d{1,2})\s+ч\s+(\d{1,2})\s+м.*?прибывает.*?в\s+(\d{1,2})\s+ч\s+(\d{1,2})\s+м",
        full_text,
        flags=re.IGNORECASE
    )

    records = []

    if fast_match:
        dep_h, dep_m, arr_h, arr_m = fast_match.groups()
        departure = f"{int(dep_h):02d}:{int(dep_m):02d}"
        arrival = f"{int(arr_h):02d}:{int(arr_m):02d}"

        records.append({
            "train_no": "—",
            "route_from": "Каменское",
            "route_to": "Верховцево",
            "station_from": "Каменское",
            "station_to": "Верховцево",
            "departure": departure,
            "arrival": arrival,
            "duration": "",
            "schedule": "Из текстового описания сайта",
        })

    if records:
        return records

    preview = text[:1000]
    raise RuntimeError(f"Не найден блок расписания на странице. Начало ответа: {preview}")


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
        json={
            "chat_id": chat_id,
            "text": text[:4096],
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    resp.raise_for_status()


def save_payload(path: Path, route_name: str, route_title: str, route_url: str, items, changes):
    payload = {
        "route_name": route_name,
        "route_title": route_title,
        "source": route_url,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "has_changes": bool(changes),
        "changes": changes,
        "items": items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def process_route(route):
    previous = load_previous(route["output"])

    try:
        html = fetch_html(route["url"])
        items = parse_schedule(html)
    except Exception as e:
        print(f"Ошибка для маршрута {route['name']}: {e}")

        # Если уже есть старые НЕпустые данные — оставляем их
        if previous and previous.get("items"):
            print(f"Оставляю старые непустые данные в {route['output']}")
            return False

        # Если данных нет вообще — пишем явную заглушку
        payload = {
            "route_name": route["name"],
            "route_title": route["title"],
            "source": route["url"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "has_changes": False,
            "changes": [f"Не удалось обновить маршрут: {e}"],
            "items": [],
            "error": str(e),
        }
        route["output"].write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"Сохранил пустой файл с ошибкой: {route['output']}")
        return False

    old_items = previous.get("items", []) if previous else []
    changes = diff_items(old_items, items) if previous else []

    payload = {
        "route_name": route["name"],
        "route_title": route["title"],
        "source": route["url"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "has_changes": bool(changes),
        "changes": changes,
        "items": items,
    }

    route["output"].write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"Saved {len(items)} trains to {route['output']}")

    if changes:
        message = f"⚠️ Изменилось расписание {route['title']}\\n\\n" + "\\n".join(changes[:20])
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
