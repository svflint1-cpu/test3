import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = "https://poizdato.net/ru/raspisanie-poezdov/verhovtsevo--kamenskoe/elektrichki/"
OUTPUT = Path("schedule.json")

def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()

def fetch_html() -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
        ),
        "Accept-Language": "ru,en;q=0.9,uk;q=0.8",
    }
    resp = requests.get(URL, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text

def parse_schedule(html: str):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True).replace("\xa0", " ")
    start_marker = "Тип Номер Маршрут Отправление"
    end_marker = "Выполнен поиск без указания даты."

    start_idx = text.find(start_marker)
    if start_idx == -1:
        raise RuntimeError("Не найден блок расписания на странице.")
    end_idx = text.find(end_marker, start_idx)
    if end_idx == -1:
        end_idx = len(text)

    block = text[start_idx:end_idx]
    lines = [normalize_space(x) for x in block.splitlines() if normalize_space(x)]

    train_positions = [i for i, line in enumerate(lines) if re.match(r"^\d{4,5}\*?$", line)]
    if not train_positions:
        raise RuntimeError("Не удалось выделить строки поездов.")

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

    if not records:
        raise RuntimeError("После парсинга не осталось валидных записей.")

    return records

def main():
    html = fetch_html()
    items = parse_schedule(html)
    payload = {
        "source": URL,
        "updated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "items": items,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(items)} trains to {OUTPUT}")

if __name__ == "__main__":
    main()
