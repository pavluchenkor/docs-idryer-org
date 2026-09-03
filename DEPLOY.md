# Деплой docs-idryer-org

Движок стоит **рядом** со старым dev-движком — отдельный путь/порт/контейнер,
ничего старого не трогает. Все три этапа (A/B/C) выполнены: прод живёт на
`https://docs.idryer.org`, `new.docs.idryer.org` — второе имя того же сайта.
Шаги ниже сохранены как референс для воспроизведения.

Сервер: `82.146.63.133`. Системный nginx (`include conf.d/*.conf` + `sites-enabled/*`),
certbot в Docker (webroot через `/var/www/certbot`), хостовые серты в `/etc/letsencrypt`.

## Карта: новый ↔ старый dev (рабочий эталон)
| | dev (старый, не трогаем) | новый |
|---|---|---|
| репо | `/opt/idryer-dev` | `/opt/docs-idryer-org` |
| site (output) | `/opt/idryer-docs/site` | `/opt/docs-idryer-org/site` |
| порт вебхука | `9001` | `9002` |
| nginx-конфиг | `conf.d/dev.idryer.org.conf` | `conf.d/new.docs.idryer.org.conf` |
| контейнер | `idryer-docs-builder` | `docs-idryer-org-builder` |

## A. Локально — ГОТОВО
- `nginx-new.docs.idryer.org.conf`, `docker-compose.yml` (9002 + `/opt/docs-idryer-org`),
  `mkdocs.yml` `site_url: !ENV [SITE_URL, …]` (проверено: переключение домена = одна переменная),
  `.env.example` (+ SITE_URL), Dockerfile (pngquant/pillow/glightbox).

## B. Стейджинг new.docs.idryer.org — РАЗВЁРНУТО ✅

> Стейджинг живой: `https://new.docs.idryer.org` (HTTPS), авто-сборка по webhook
> работает. Шаги ниже — как это было поднято (референс для воспроизведения/прода).
1. Залить движок:
   ```
   git clone https://github.com/pavluchenkor/docs-idryer-org.git /opt/docs-idryer-org
   cd /opt/docs-idryer-org && git checkout main
   ```
2. `.env`:
   ```
   cp .env.example .env
   # WEBHOOK_SECRET=$(openssl rand -hex 32)  ·  GITHUB_TOKEN=<свой fine-grained>  ·  SITE_URL=https://docs.idryer.org/
   ```
3. Образ + билдер:
   ```
   docker compose build
   docker compose up -d
   docker ps | grep docs-idryer-org-builder
   ```
4. nginx — сначала временный конфиг ТОЛЬКО с блоком :80 (для ACME-проверки;
   полный :443 нельзя — серта ещё нет, `nginx -t` упал бы на ssl_certificate):
   ```
   printf 'server {\n  listen 80;\n  server_name new.docs.idryer.org;\n  location /.well-known/acme-challenge/ { root /var/www/certbot; }\n  location / { return 301 https://$host$request_uri; }\n}\n' > /etc/nginx/conf.d/new.docs.idryer.org.conf
   nginx -t && nginx -s reload
   ```
5. certbot — ХОСТОВЫЙ (как для dev), метод webroot. Авто-обновление уже есть
   (systemd `certbot.timer`). Нужен DNS `new.docs → 82.146.63.133` + nginx :80 (п.4):
   ```
   certbot certonly --webroot -w /var/www/certbot -d new.docs.idryer.org \
     --email <твой-email> --agree-tos --no-eff-email
   ```
   Затем кладём ПОЛНЫЙ конфиг (с :443) и перезагружаем:
   ```
   cp /opt/docs-idryer-org/nginx-new.docs.idryer.org.conf /etc/nginx/conf.d/new.docs.idryer.org.conf
   nginx -t && nginx -s reload
   ```
6. Сборка: entrypoint — webhook-демон (порт `9000` в контейнере → `9002` на хосте).
   Ручной триггер: `docker exec docs-idryer-org-builder /app/rebuild.sh`.
   Результат → `/opt/docs-idryer-org/site` → проверить `https://new.docs.idryer.org`.
7. GitHub webhooks → `https://new.docs.idryer.org/hooks/rebuild` (secret = WEBHOOK_SECRET):
   на `docs-idryer-org` И на каждый активный продуктовый репо.
   `hooks.json` уже триггерит rebuild на: пуш в `main` репо движка ИЛИ пуш в
   ветку `docs-publish` ЛЮБОГО репо (матч по ветке, перечислять репо не нужно).
   Тогда же осмысленно запушить `idryer-core/docs-publish` (`11f8cd2`).

   Подключение нового репо по мере готовности (без правки hooks.json):
     а) раскомментировать репо в `repos.yml`;
     б) повесить GitHub-webhook этого репо на `/hooks/rebuild` (secret = WEBHOOK_SECRET).

## C. Переключение на docs.idryer.org — ВЫПОЛНЕНО ✅

> Прод живой: `https://docs.idryer.org` (HTTPS). `new.docs.idryer.org` остаётся
> вторым именем того же сайта — оба хоста отдают ОДНУ сборку из
> `/opt/docs-idryer-org/site`, canonical на обоих указывает на `docs.idryer.org`.
1. ✅ `certbot certonly … -d docs.idryer.org` (тот же webroot).
2. ✅ nginx: `docs.idryer.org` добавлен в `server_name` ОБОИХ блоков `new.docs`-конфига
   (root `/opt/docs-idryer-org/site` и `/hooks/` те же), `nginx -t && nginx -s reload`.
3. ✅ `SITE_URL=https://docs.idryer.org/` (2026-09-03). Строка `SITE_URL` удалена из
   серверного `.env` — теперь берётся дефолт из `docker-compose.yml` (прод-домен).
   ВАЖНО: `SITE_URL` в `.env` перебивает дефолт; оставленный там
   `https://new.docs.idryer.org/` = canonical и sitemap на ОБОИХ хостах указывают
   на стейджинг (так и было до 2026-09-03 — поисковики индексировали `new.docs`).
4. ✅ DNS: `docs.idryer.org → 82.146.63.133`.
5. Старый dev (`dev.idryer.org`) можно оставить или погасить — независимо.

### Пересоздание контейнера (баг docker-compose v1.29.2)
На сервере стоит только `docker-compose` v1.29.2 (плагина `docker compose` нет).
С Docker 25+ он падает на `--force-recreate` с `KeyError: 'ContainerConfig'` —
поле убрано из image inspect. При этом старый контейнер уже остановлен, а новый
не создан: сайт продолжает отдаваться (nginx читает `site/` напрямую), но
`/hooks/rebuild` даёт 502. Рабочая последовательность:
```
docker-compose stop && docker-compose rm -f && docker-compose up -d
```
`rm -f` без `-v` тома не трогает (кэш сборки — named volume, `site` — bind-mount).
Долгосрочно — поставить `docker-compose-plugin` и перейти на `docker compose`.
