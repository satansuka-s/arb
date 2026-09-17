# ARB Platform

Расширяемая realtime-платформа для сбора коэффициентов из нескольких букмекеров, нормализации событий и cross-book арбитража.

## Что изменилось

Старый монолит разбит на отдельные слои:

```text
source adapter
    -> parser
    -> normalized event
    -> canonical event matcher
    -> realtime state
    -> detectors
    -> batched storage
```

Общий pipeline больше не знает, как устроен конкретный букмекер.

### Архитектура

```text
arb-platform/
├── app/
│   └── runtime.py
├── config/
│   └── settings.py
├── models/
│   └── domain.py
├── sources/
│   ├── base.py
│   ├── discovery.py
│   ├── sporthub/
│   │   ├── adapter.py
│   │   ├── parser.py
│   │   └── subscriptions.py
│   └── _template_bookmaker/
├── normalization/
│   ├── names.py
│   ├── markets.py
│   └── matcher.py
├── storage/
│   ├── repository.py
│   └── sqlite.py
├── realtime/
│   └── state.py
├── detection/
│   ├── movement.py
│   ├── arbitrage.py
│   └── engine.py
├── tools/
│   └── refresh_subscriptions.py
├── tests/
└── data/
```

## Быстрый старт

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -e .
python -m app.runtime
```

Для API (необязательно):

```bash
pip install -e ".[api]"
uvicorn api.app:app --reload
```

Для Playwright-сборщика подписок:

```bash
pip install -e '.[collector]'
playwright install chromium
python -m sources.sporthub.subscriptions --sport dota
```

Настройки можно положить в `.env` на основе `.env.example`.

## Добавление нового букмекера

Новый источник добавляется отдельным пакетом. Общая система менять не должна.

1. Создай `sources/newbookmaker/`.
2. Реализуй `adapter.py`, унаследовавшись от `BookmakerWSAdapter`.
3. Реализуй `decode_frame()` и, если требуется, `build_subscriptions()` или `refresh_subscriptions()`.
4. Добавь `__init__.py` с `build_adapter()`.
5. При необходимости добавь собственный parser и browser collector рядом с адаптером.
6. Либо создай каркас одной командой: `python -m tools.new_bookmaker fonbet`.
7. Запусти платформу. `sources.discovery` найдёт пакет автоматически.

Минимальный пример:

```python
from sources.base import BookmakerWSAdapter
from models.domain import SourceEvent

class NewBookmakerAdapter(BookmakerWSAdapter):
    source_name = "newbookmaker"
    display_name = "New Bookmaker"
    ws_url = "wss://example.com/live"

    def decode_frame(self, payload: bytes) -> list[SourceEvent]:
        return parse_newbookmaker(payload)

def build_adapter():
    return NewBookmakerAdapter()
```

То есть новый букмекер отвечает только за внешний мир: соединение, подписки и парсинг. Matching, canonical events, хранение, state и detectors остаются общими.

## Cross-book arbitrage

Арбитраж считается по `canonical_event_id`, а не по bookmaker-specific `event_id`.

Пример:

```text
BetBoom event 123  ─┐
Fonbet event 456   ├─> canonical event ABC
Book3 event xyz    ─┘
                     │
                     ├─> canonical market
                     └─> best odds per outcome
```

Это позволяет находить арбитраж между разными букмекерами, даже когда их идентификаторы событий не совпадают.

## Хранилище

Текущие backend-реализации - SQLite в WAL-режиме и PostgreSQL через `psycopg`. В обоих случаях runtime работает через один интерфейс repository. По умолчанию используется SQLite. Слой `storage.repository` специально отделён от runtime, чтобы позже без переделки источников заменить backend на PostgreSQL/ClickHouse и т.п.

Текущий SQLite больше не делает `commit()` на каждый event: runtime складывает изменения в batch и пишет транзакциями.

## Важные особенности

- Unknown league больше не приводит к тихому выбрасыванию события.
- Realtime state имеет TTL и не растёт бесконечно.
- Snapshot пишется атомарно и периодически, а не на каждый event.
- Detector движения и cross-book arbitrage разделены.
- Повторные arb-срабатывания throttled по cooldown.
- Все source-specific данные хранятся рядом с source adapter.
- Подписки теперь лежат отдельно по source и sport: `data/subscriptions/<source>/<sport>.txt`.

## Проверка

```bash
pytest -q
python -m compileall app config models sources normalization storage realtime detection tools
```

## Ограничение текущей версии

Автоматический matching использует нормализацию названий команд + спорт + временное окно. Для нестандартных названий предусмотрен файл alias-карты в `data/cache/team_aliases.json`. Для production-уровня его можно постепенно заменить отдельным сервисом matching/ML, не трогая ingestion.
