<div align="center">

# Keitaro Wrapper

**Создаватор кампаний и редактор офферов поверх Keitaro Admin API.**

Одна форма создаёт кампанию с двумя потоками. Редактор правит офферы в черновике,<br>
пересчитывает доли и публикует изменения в трекер одной кнопкой.

[![Python](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy%202-D71F00?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![Alembic](https://img.shields.io/badge/миграции-Alembic-6BA539)](#миграции)
[![Tests](https://img.shields.io/badge/тесты-29%20passed-2ea44f)](#тесты)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

<img src="docs/editor.png" alt="Редактор кампании" width="860">

[Быстрый старт](#быстрый-старт) ·
[Создаватор](#создаватор) ·
[Редактор](#редактор) ·
[Миграции](#миграции) ·
[API](#api) ·
[Тесты](#тесты)

</div>

---

## Быстрый старт

Нужны Python 3.12+ и [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/derekzwan/keitaro-wrapper.git
cd keitaro-wrapper

cp .env.example .env          # вписать KEITARO_URL и KEITARO_API_KEY
uv sync                       # зависимости
uv run alembic upgrade head   # миграции
uv run uvicorn app.main:app --port 8000
```

Интерфейс: http://localhost:8000 · Swagger: http://localhost:8000/docs

> [!TIP]
> API-ключ лежит в Keitaro: **Профиль → API ключи**. В `KEITARO_URL` нужен адрес трекера без `/admin_api`,
> например `https://tracker.example.com`.

<details>
<summary><b>Все переменные окружения</b></summary>

| Переменная | По умолчанию | Что задаёт |
|---|---|---|
| `KEITARO_URL` | — | адрес трекера |
| `KEITARO_API_KEY` | — | ключ Admin API |
| `KEITARO_TIMEZONE` | `Europe/Moscow` | таймзона отчётов |
| `DEFAULT_DOMAIN` · `DEFAULT_GROUP` · `DEFAULT_SOURCE` | первый в списке | что выбрано в форме создаватора (по имени) |
| `GOOGLE_URL` | `https://google.com` | куда ведёт гео-поток |
| `DATABASE_URL` | `sqlite:///./keitaro_wrapper.db` | база; для Postgres `postgresql+psycopg://user:pass@host/db` |

</details>

---

## Создаватор

<img src="docs/creator.png" alt="Создаватор кампаний" width="860">

Принимает название, гео (одна страна или список: `MX, AU, RO`) и оффер с автокомплитом по базе Keitaro.
Домен, группа и источник выбираются из того, что есть в трекере. Справа видна живая схема будущей кампании.

```mermaid
flowchart LR
    U[посетитель] --> C[кампания<br>домен · группа · источник]
    C --> F1{Flow 1<br>страна в списке?}
    F1 -- да --> G[google.com]
    F1 -- нет --> F2[Flow 2<br>оффер 100%]
```

- **Сначала проверка, потом запись.** Оффер, домен, группа и источник проверяются до первого `POST`: в трекере не остаётся мусора от неудачной попытки.
- **Откат.** Если кампания создалась, а поток нет, кампания удаляется.
- **Гео.** Коды ISO 3166 с проверкой, `UK` автоматически превращается в `GB`, дубли убираются.

---

## Редактор

Повторяет логику редактора из ТЗ. Каждое изменение сначала попадает в черновик в базе, а в Keitaro уходит только по **Push to KT**.

| Действие | Что происходит |
|---|---|
| **Fetch streams from KT** | Забирает потоки из Keitaro. Потоки без офферов показываются как есть, их содержимое не разбирается. Офферы, которых больше нет в Keitaro, становятся `removed` |
| **Add** | Поиск оффера по ID или названию, доли пересчитываются, поток подсвечивается жёлтым: «не опубликовано» |
| **Remove** | Оффер сереет, доля 0%, сам он остаётся в архиве обёртки. Неопубликованный оффер удаляется совсем |
| **Bring back** | Возвращает оффер из архива |
| **Pin** | Закреплённая доля не меняется при пересчётах. Клик по проценту позволяет ввести долю руками, после чего она закрепляется |
| **Push to KT** | Публикует офферы потока и сверяется с тем, что Keitaro реально сохранил |
| **Cancel** | Выкидывает неопубликованные офферы и возвращает всё к опубликованному состоянию |

### Как считаются доли

Остаток `100 − Σ закреплённых` делится поровну между незакреплёнными офферами, лишние единицы достаются первым по порядку:

| Офферы | Закреплено | Результат |
|---|---|---|
| 3 | — | 34 · 33 · 33 |
| 4 | — | 25 · 25 · 25 · 25 |
| 3 | 25% | 38 · **25** · 37 |

Сумма всегда 100. Операцию, которая ломает сумму (закреплённые доли больше 100% или всё закреплено, а в сумме не 100%), обёртка отменяет целиком и объясняет почему. Поток без офферов опубликовать нельзя.

### Что ещё есть

<img src="docs/offers.png" alt="Панель всех офферов" width="860">

| | |
|---|---|
| **Статистика** | Клики, конверсии, CR, доход по каждому офферу и по кампании: сегодня, вчера, 7 или 30 дней |
| **Тренды** | Мини-графики кликов по дням, точками отмечены дни с конверсиями |
| **preview** | Открывает оффер: лендинг на трекере для локального, URL для внешнего |
| **Все офферы** | Панель с поиском: где стоит каждый оффер и с какой долей. Добавить в поток можно прямо отсюда |
| **Защита от рассинхрона** | Если поток удалили в админке Keitaro, Push в него откажет и попросит сделать Fetch |
| **Тёмная тема** | Включается по системной настройке, вёрстка работает и на телефоне |

<img src="docs/dark.png" alt="Тёмная тема" width="860">

---

## Миграции

```bash
uv run alembic upgrade head                              # применить
uv run alembic downgrade -1                              # откатить последнюю
uv run alembic revision --autogenerate -m "описание"     # новая миграция после правки app/models.py
uv run alembic current                                   # текущая ревизия
```

URL базы берётся из `DATABASE_URL`, отдельно настраивать `alembic.ini` не нужно.

<details>
<summary><b>Схема базы</b></summary>

| Таблица | Что хранит |
|---|---|
| `campaigns` | кампании: ID в Keitaro, alias, ссылка, гео и оффер при создании через обёртку |
| `streams` | потоки: позиция, тип, сводка фильтров, есть ли офферы |
| `stream_offers` | оффер в потоке: черновик (`share`, `pinned`, `status`) и снимок опубликованного (`published_*`) |

Поток считается «не опубликованным», если хотя бы у одного оффера черновик отличается от снимка.

</details>

---

## API

<details>
<summary><b>Эндпоинты</b></summary>

| Метод | Путь | Что делает |
|---|---|---|
| `GET` | `/api/meta` | домены, группы, источники и значения по умолчанию |
| `GET` | `/api/offers?q=` | поиск офферов |
| `POST` | `/api/campaigns` | создать кампанию с двумя потоками |
| `GET` | `/api/campaigns` | кампании из Keitaro |
| `GET` | `/api/campaigns/{id}` | кампания с потоками и офферами |
| `POST` | `/api/campaigns/{id}/fetch` | Fetch streams from KT |
| `GET` | `/api/campaigns/{id}/stats?period=` | статистика: `today` · `yesterday` · `7d` · `30d` |
| `GET` | `/api/campaigns/{id}/trends?days=` | клики и конверсии по дням |
| `POST` | `/api/streams/{id}/offers` | добавить оффер |
| `POST` | `/api/streams/{id}/push` | опубликовать в Keitaro |
| `POST` | `/api/streams/{id}/cancel` | отменить черновик |
| `POST` | `/api/stream-offers/{id}/remove` | убрать оффер |
| `POST` | `/api/stream-offers/{id}/restore` | вернуть оффер |
| `PUT` | `/api/stream-offers/{id}/share` | задать долю (закрепляет её) |
| `PUT` | `/api/stream-offers/{id}/pin` | закрепить или открепить долю |

Ошибки приходят как `{"detail": "текст"}`: `422` — неверная операция, `502` — ошибка Keitaro, `503` — Keitaro не настроен.

</details>

<details>
<summary><b>Структура проекта</b></summary>

```
app/
  main.py              приложение и статика
  api.py               HTTP-роуты
  keitaro.py           клиент Keitaro Admin API: ретраи GET, кэш офферов
  models.py            Campaign, Stream, StreamOffer
  services/creator.py  создание кампании и потоков
  services/editor.py   fetch, add, remove, bring back, pin, push, cancel, статистика, тренды
  services/shares.py   расчёт долей
  services/geo.py      проверка кодов стран
  static/              фронт на чистом JS, без сборки
migrations/            Alembic
tests/                 pytest + имитация Keitaro
```

</details>

---

## Тесты

```bash
uv run pytest
```

Тесты не ходят в настоящий Keitaro, вместо него работает имитация [tests/fake_keitaro.py](tests/fake_keitaro.py).
Сценарии повторяют видео из ТЗ: 33 · 33 · 34 → после добавления четвёртого оффера 25 × 4 → после закрепления 25% и удаления 38 · 25 · 37.
Отдельно проверяются Cancel и Bring back, перевод удалённого в Keitaro оффера в `removed`, откат кампании при сбое создания потока, отказ публиковать в удалённый поток и миграции вверх и вниз.

Имитацию можно запустить, чтобы покликать интерфейс без доступа к трекеру:

```bash
uv run uvicorn tests.fake_keitaro:app --port 8090 &
KEITARO_URL=http://127.0.0.1:8090 KEITARO_API_KEY=test-key uv run uvicorn app.main:app --port 8000
```

<div align="center">
<sub>MIT · FastAPI · SQLAlchemy · без сборки фронта</sub>
</div>
