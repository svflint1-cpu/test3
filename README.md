# Нормальный вариант: HTML + schedule.json + GitHub Actions

Что тут лежит:
- `index.html` — страница/Telegram Web App
- `schedule.json` — данные, которые читает HTML
- `update_schedule.py` — парсит Poizdato и обновляет JSON
- `.github/workflows/update_schedule.yml` — GitHub Actions, который запускает обновление автоматически

## Как запустить
1. Создай новый репозиторий на GitHub.
2. Закинь в него все эти файлы.
3. В репозитории открой **Settings → Pages** и включи GitHub Pages:
   - Source: **Deploy from a branch**
   - Branch: **main** (или master), folder: **/root**
4. Проверь, что файл workflow лежит в default branch.
5. Вкладка **Actions** → запусти workflow **Update train schedule JSON** вручную через **Run workflow**.
6. Потом открой ссылку GitHub Pages.

## Как это работает
- HTML вообще не лезет на чужой сайт.
- Он читает только `schedule.json` из твоего же репозитория.
- GitHub Actions обновляет `schedule.json` по cron.
- Официально scheduled workflows можно запускать минимум раз в 5 минут, они идут с default branch, а на public repo стандартные GitHub-hosted runners бесплатны. citeturn438374search0turn438374search1turn438374search7

## Важно
- Если Poizdato поменяет вёрстку, нужно будет поправить `update_schedule.py`.
- Scheduled workflow может иногда задерживаться, особенно в начале часа. Поэтому cron специально поставлен не на `0,15,30,45`, а на `7,22,37,52`. Это снижает шанс задержек. citeturn438374search1
