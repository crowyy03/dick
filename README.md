# VPN Telegram Bot (3x-ui)

Telegram-бот на **Python 3.12**, **aiogram 3**, **SQLAlchemy 2** и **PostgreSQL** для выдачи и учёта VPN-ключей поверх уже установленной панели **3x-ui**. Работает через **long polling** (без webhook), не требует отдельного nginx для самого бота.

## Возможности

- Self-service: выдача доступа, «Мои подключения», отдельная кнопка «Трафик всего» (счётчики ↑+↓ по API панели), обновление ссылки (лимиты), второе устройство (`manual_approval` или `auto`), проверка и «Статус VPN», история из `audit_log`, FAQ, контакт с админом.
- `SUPPORT_TELEGRAM_USERNAME` — username для текстов «напиши админу» и кнопок `t.me/...` (по умолчанию `voronin_36`).
- Legacy: импорт клиентов из панели в БД как `imported_unbound`, ручная привязка к `telegram_user_id` **без вызовов 3x-ui по умолчанию** (ключ в панели не меняется).
- Админ: private-only, у аккаунта с `ADMIN_TELEGRAM_ID` в главном меню есть **«Администрация»** (reply-клавиатура: панель, импорт, заявки, логи и т.д.), плюс `/admin` и slash-команды; аудит в `audit_log`, уведомления админу о важных событиях.
- Секреты: в БД хранятся идентификаторы клиента панели; ссылка подписки собирается **on demand** (не кладём полный URI в БД).
- Очередь `pending_user_notifications` — если пользователю нельзя написать до `/start`, текст доставляется при первом входе.

## Быстрый старт локально

1. Python 3.12+, PostgreSQL 14+.
2. Скопируйте окружение:

   ```bash
   cp .env.example .env
   ```

   Заполните `TELEGRAM_BOT_TOKEN`, `ADMIN_TELEGRAM_ID`, `DATABASE_URL`, доступ к панели (`PANEL_*`, `DEFAULT_INBOUND_ID`).

3. Установка и миграции:

   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install -e .
   alembic upgrade head
   python -m app.main
   ```

## Telegram

1. Создайте бота у [@BotFather](https://t.me/BotFather), вставьте токен в `TELEGRAM_BOT_TOKEN`.
2. Узнайте свой числовой ID (например, у [@userinfobot](https://t.me/userinfobot)) → `ADMIN_TELEGRAM_ID`.
3. Все **админ-команды и админ-callback** обрабатываются **только в личке** и только с вашего ID. В группах админ-логика **не выполняется**.

## Подключение к 3x-ui (важно)

Интеграция вынесена в [`app/integrations/three_x_ui/client.py`](app/integrations/three_x_ui/client.py). Там же комментарии **`ASSUMPTION`** по путям и формату тел.

Что может понадобиться подправить под вашу версию панели:

| Место | Назначение |
|--------|------------|
| `PANEL_LOGIN_PATH`, тело логина | Часть сборок ждёт JSON вместо form-data — правка в `_login_unlocked`. |
| `PANEL_API_LIST_INBOUNDS` | Путь списка inbound. |
| `PANEL_API_ADD_CLIENT` / формат `settings` | Структура `clients[]` для вашего протокола (VLESS/VMess и т.д.). |
| `PANEL_API_DEL_CLIENT` | Отзыв клиента (`delClientByEmail` или аналог). |
| `PANEL_API_UPDATE_CLIENT` | Только если включите `PANEL_UPDATE_REMARK_ON_BIND=true` (по умолчанию выключено). |
| `PANEL_API_CLIENT_TRAFFIC` (раньше `PANEL_API_INBOUND_CLIENT_TRAFFIC`) | Шаблон `getClientTraffics/{email}` — в пути **email клиента** в панели (как в 3x-ui), не id inbound. |
| `SUBSCRIPTION_PUBLIC_BASE_URL` | Опционально для `build_subscription_link` (внутренне); **основная выдача пользователю — `vless://…`**, не `/sub/`. |
| `PANEL_CLIENT_LINK_HOST` | Если inbound слушает `0.0.0.0`, в `vless://` подставляется этот хост; иначе — `listen` или hostname из `PANEL_BASE_URL`. |

**Создание клиента через бота:** `POST …/addClient` с `id` = inbound id и `settings` = JSON `{"clients":[…]}`. После ответа панели бот делает **пост-проверку**: снова `GET …/list`, ищет клиента по **email + uuid**; затем собирает **`vless://`** из `streamSettings`/`settings` inbound по логике, близкой к 3x-ui web (`Inbound.genVLESSLink`). Поддерживается **только protocol=vless** для прямой строки; иначе — ошибка и откат `delClient`. Запись в БД — **после** успешной проверки и сборки URI. Регенерация: сначала новый клиент → проверка → удаление старого (старый ключ не теряется, если новый не подтвердился).

**Версия 3x-ui:** поля `streamSettings` (reality/tls/ws/…) должны совпадать с ожидаемой схемой Xray/панели; при другой форме правьте [`vless_link.py`](app/integrations/three_x_ui/vless_link.py) или откройте issue.

**«Ключ отдали другому» / второе устройство чужое:** стандартный API 3x-ui не даёт надёжного сигнала «два разных человека на одной подписке» — для сервера это один клиент, один счётчик трафика. Уведомление «кто-то ещё активировал» без отдельной инфраструктуры (логи ядра, сторонний мониторинг IP, политика `limitIp` в панели и т.д.) **в боте не реализовано** и честно не обещается.

### Трафик и «проверка доступа»

- Бот **не** проверяет интернет на стороне пользователя и **не** пингует его роутер.
- В «Мои подключения», «Проверить доступ» и «Статус VPN» используется только то, что отдаёт API панели: список клиентов inbound (есть ли запись, включена ли) и опционально `getClientTraffics`.
- Если эндпоинт трафика недоступен или формат ответа не совпадает, адаптер возвращает `None` — в интерфейсе честно пишется, что статистики нет (это не «ноль мегабайт»).
- **Последняя активность / «онлайн»:** адаптер пытается прочитать `lastOnline` (мс с эпохи) из клиента и из строк трафика и при наличии — флаг `online`. Семантика зависит от версии 3x-ui; это **не** доказательство, что VPN реально работает на устройстве пользователя. Если полей нет — бот так и пишет.

Проверка до боевой работы:

```text
/admin_panel_check
```

или кнопка «Проверка панели» в `/admin`. Должен вернуться список inbound без ошибок.

## Деплой на тот же Ubuntu, где уже стоит 3x-ui (Docker Compose)

Цель: **не открывать лишние порты наружу**, не трогать порты панели, бот ходит в панель по **loopback** или внутреннему IP.

1. Установите Docker и Docker Compose plugin (официальная документация Docker для Ubuntu).

2. Склонируйте проект, например в `/opt/vpn-bot`.

3. Создайте `.env` (см. `.env.example`). Для доступа к панели на том же хосте из контейнера используйте IP хоста:

   - `PANEL_BASE_URL=https://172.17.0.1:2053` **или** `https://host.docker.internal:...` (если настроено), **или** пробросьте только внутреннюю сеть docker — главное, чтобы из контейнера `bot` был достижим URL панели.
   - `PANEL_VERIFY_TLS=false`, если используете самоподписанный сертификат на панели.

4. В `.env` для Compose **не задавайте** свой `DATABASE_URL` (его переопределит `docker-compose.yml`) **или** закомментируйте строку `DATABASE_URL` в `.env`, чтобы сработало значение из compose.

5. Запуск:

   ```bash
   docker compose up -d --build
   ```

   Контейнер `bot` при старте выполняет `alembic upgrade head` и затем long polling. Порт наружу **не публикуется** — исходящие запросы к Telegram и панели достаточно.

6. Автозапуск после ребута: `restart: unless-stopped` уже в compose.

7. **Проверка, что VPN не сломан:** бот не меняет конфиги xray напрямую, только через API панели при выдаче/регенерации/отзыве. После деплоя откройте 3x-ui вручную, убедитесь, что inbound и существующие клиенты на месте; затем `/admin_panel_check` в боте.

## Деплой без Docker (systemd)

1. Создайте пользователя `vpn-bot`, каталог `/opt/vpn-bot`, виртуальное окружение, установите пакет `pip install -e .`.
2. Положите `.env` в `/opt/vpn-bot/.env`.
3. Скопируйте [`deploy/vpn-bot.service`](deploy/vpn-bot.service) в `/etc/systemd/system/vpn-bot.service`, поправьте пути при необходимости.
4. `sudo systemctl daemon-reload && sudo systemctl enable --now vpn-bot`.

`scripts/run.sh` выполняет миграции и запускает `python -m app.main`.

## Порты и конфликты

- Бот **не слушает** входящих TCP-портов (long polling).
- PostgreSQL в compose **не проброшен** наружу — только сеть `internal`.
- Панель 3x-ui продолжает использовать свои порты; проект их не занимает.

## Обновление

1. `git pull` (или обновите файлы).
2. `docker compose up -d --build` **или** в venv: `pip install -e . && alembic upgrade head && systemctl restart vpn-bot`.

## Логи

- Docker: `docker compose logs -f bot`
- systemd: `journalctl -u vpn-bot -f`

В логах панели и бота **не должны** попадать полные subscription URL — при отладке смотрите маскирование в [`app/core/logging.py`](app/core/logging.py) и аккуратно не включайте «сырой» дамп тел HTTP в production.

## Резервное копирование БД

```bash
docker compose exec db pg_dump -U vpn vpn_bot > backup.sql
```

Восстановление:

```bash
cat backup.sql | docker compose exec -T db psql -U vpn -d vpn_bot
```

## Сценарий legacy без поломки ключей

1. `/admin_add_user <telegram_id>` — запись в `users` (пользователь может ещё не писать боту).
2. `/admin_import_clients [inbound_id]` — клиенты с панели попадают в `vpn_keys` со статусом `imported_unbound` (дубликаты по inbound+email пропускаются).
3. `/admin_bind` или кнопка «Привязать ключ» → выбор ключа → ввод `telegram_id` → слот 1 или 2.  
   По умолчанию **только UPDATE в БД**; панель не трогается. `PANEL_UPDATE_REMARK_ON_BIND` по умолчанию `false`.
4. Когда пользователь напишет `/start`, увидит свои ключи.

Регенерация/отзыв **меняет** панель — для импортированных ключей это осознанное действие пользователя или админа.

## Админ-команды (личка)

| Команда | Описание |
|---------|-----------|
| `/admin` | Меню |
| `/admin_panel_check` | Логин + список inbound |
| `/admin_add_user <id>` | Создать пользователя по Telegram ID |
| `/admin_users` | Список пользователей |
| `/admin_user <id>` | Карточка |
| `/admin_keys <id>` | Активные ключи |
| `/admin_requests` | Заявки на 2-й ключ |
| `/admin_import_clients [inbound]` | Импорт клиентов inbound в БД |
| `/admin_unbound_clients` | Непривязанные импорты |
| `/admin_bind` | Мастер привязки |
| `/admin_revoke <id>` | Отозвать все ключи пользователя (панель + БД) |
| `/admin_disable_key <id>` | Отключить один ключ |
| `/admin_stats` | Статистика |
| `/admin_logs` | Последние записи аудита |

## Переменные окружения

См. [`.env.example`](.env.example).

## Структура проекта

- `app/bot` — factory, middlewares, тексты, FSM-состояния.
- `app/handlers` — пользовательские и админские хендлеры.
- `app/services` — сценарии и MVP rate limit.
- `app/repositories` — доступ к БД.
- `app/integrations/three_x_ui` — Protocol + адаптер HTTP.
- `alembic/versions` — миграции.

## Ограничения и риски

- Rate limit регенераций **в памяти процесса** — при нескольких репликах бота счётчики не общие.
- FSM привязки ключей — **MemoryStorage**; после рестарта незавершённые шаги сбрасываются.
- API 3x-ui может отличаться по версии — держите правки в адаптере.

## Лицензия

Проект как есть для частного/внутреннего использования; при необходимости добавьте свою лицензию.
