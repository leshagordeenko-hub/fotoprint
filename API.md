# API · Фотопринт (трек 1)

Базовый адрес `http://localhost:8080/api`. Формат — JSON (UTF-8). Даты — ISO 8601 с `+03:00` (Europe/Minsk). Деньги — BYN.
Все методы, кроме `/login` и `/health`, требуют заголовок `Authorization: Bearer <token>`.

Доступ к экранам: директор и аналитик — все; руководитель производства (`prod`) — `/production`, `/forecast`; руководитель продаж (`sales`) — `/sales`. Остальные экраны для руководителя → 403 (пишется в журнал); `/kpi/{id}` — только KPI своего подразделения; фильтр `dept` для руководителя всегда своё подразделение. Список доступных экранов — `permissions.screens` в `/meta`.

Ошибки: `{"error": "<понятное сообщение на русском>", "fields": {...}?}` с кодами 400 (неверный параметр), 401 (нет входа), 403 (нет прав — пишется в журнал), 404, 409 (карточку изменили), 413, 422 (ошибки полей), 500.

## Фильтры (общие для аналитических методов)

| Параметр | Значения |
|---|---|
| `period` | `ГГГГ-ММ`, `last28`, `last90` (по умолчанию — текущий месяц) |
| `dept` | `all`, `D-SALES`, `D-PROD`, `D-SUP`, `D-FIN`, `D-HR` |
| `product` | `all`, `PRD-BOOK`, `PRD-PRINT`, `PRD-CAL`, `PRD-CANVAS`, `PRD-SOUV` |

## Методы

| Метод | Путь | Описание | Права |
|---|---|---|---|
| POST | `/login` | `{login, password}` → `{token, user}` | все |
| POST | `/logout` | Завершить сессию | вошедший |
| GET | `/me` | Текущий пользователь | вошедший |
| GET | `/meta` | Периоды, справочники, KPI (формулы — только видимых), владельцы, права | вошедший |
| GET | `/pulse?period&dept&product&chart=revenue\|orders\|output` | KPI (план, факт, прогноз, отклонение, статус, формула, источники, время), карточки, график, загрузка участков, клиенты по каналам | директор, аналитик |
| GET | `/kpi/{id}?…` | Детализация: разрезы с вкладом в изменение, объяснение, связанные факторы, база сравнения; `notes` — ответственный и лента комментариев | руководитель — только KPI своего подразделения, иначе 403 |
| POST | `/kpi/{id}/comments` | `{text}` (до 1000 символов) → `notes`. Ошибки: 422 пустой/длинный текст | только директор; руководитель видит комментарии к своим KPI |
| PATCH | `/kpi/{id}/owner` | `{owner: id из meta.owners \| null}` → `notes`; назначенный получает уведомление | только директор |
| GET | `/orders?kind=all\|late\|defect&section&product_name&channel&campaign&reason&q&page` | Заказы для детализации (10 на странице) | вошедший |
| GET | `/orders/{ORD-…}` | Сквозная карточка: ERP + CRM + Helpdesk + MES + 1С | себестоимость — директору/аналитику/производству |
| GET | `/tickets?breached=1&topic&channel&page` | Обращения (SLA) | директор, аналитик |
| GET | `/sales?…` | Воронка, сегменты, каналы, кампании, отток | директор, аналитик, руководитель продаж; ROMI — только при доступе к марже |
| GET | `/production?…` | Участки: план/факт, загрузка, очередь, простои, брак, lead time, персонал | директор, аналитик, руководитель производства |
| GET | `/forecast` | Прогноз спроса и мощности на 6 недель, неделя дефицита, метод | директор, аналитик, руководитель производства |
| GET | `/finance?…` | БДР/БДДС, маржа по продуктам, персонал, ФОТ | директор, аналитик |
| GET | `/quality` | Свежесть источников, пропуски, дубли, сверка ERP ↔ 1С, связность | директор, аналитик |
| GET | `/decisions?status&priority&dept&overdue&q` | Реестр решений | директор, аналитик |
| GET | `/decisions/{id}` | Карточка с историей | так же |
| POST | `/decisions` | Создать: `kpi_id, dept, title, impact, cause, action, owner, due, priority, status, context` | только директор |
| PATCH | `/decisions/{id}` | Изменить поля; `version` = `rev` карточки (иначе 409) | только директор |
| GET | `/audit?user&result&q&page&per` | Журнал действий | директор, аналитик |
| GET | `/alerts` · POST `/alerts/read` | Уведомления (критичные KPI, просроченные решения, дефицит, источники) | вошедший |
| GET | `/fotik` | Подключён ли ассистент (`enabled`, `model`); ключ не возвращается | вошедший |
| GET | `/fotik/context?…` | Снимок данных, который получает Фотик (фильтры, KPI, агрегаты, аномалии, тренды) | вошедший; руководителю — только данные своего подразделения |
| POST | `/fotik` | `{question, history:[{role, content}], filters:{period, dept, product}, screen}` → `{answer, model, context, usage}`. Ошибки: 422 пустой/длинный вопрос, 429 больше 20 вопросов в минуту, 502/503/504 сбой Claude API, 503 нет `ANTHROPIC_API_KEY` | вошедший |
| POST | `/export` | Фиксация выгрузки CSV в журнале | вошедший |
| GET | `/health` | Проверка работоспособности; `data_loaded_at`, `data_checked_at`, `refresh_sec` (15), `reload_error` — состояние автообновления базы; `live_simulation`, `live_orders_today`, `orders_total` — живой поток заказов | все |

## Пример

```bash
TOKEN=$(curl -s -X POST localhost:8080/api/login -H 'Content-Type: application/json' \
  -d '{"login":"director","password":"demo2026"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -s "localhost:8080/api/kpi/on_time?period=2026-10" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -40
```
