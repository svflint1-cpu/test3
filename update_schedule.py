def parse_schedule(html: str):
    import re
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True).replace("\xa0", " ")

    lines = [x.strip() for x in text.splitlines() if x.strip()]

    records = []

    i = 0
    while i < len(lines):
        if re.fullmatch(r"\d{4,5}", lines[i]):
            train_no = lines[i]

            chunk = lines[i:i+20]

            times = [x for x in chunk if re.fullmatch(r"\d{2}\.\d{2}", x)]

            if len(times) >= 2:
                departure = times[0].replace(".", ":")
                arrival = times[1].replace(".", ":")

                route_from = ""
                route_to = ""

                if "→" in chunk:
                    idx = chunk.index("→")
                    if idx > 0 and idx + 1 < len(chunk):
                        route_from = chunk[idx - 1]
                        route_to = chunk[idx + 1]

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

                i += 10
                continue

        i += 1

    return records
