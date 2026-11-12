#!/usr/bin/env python3
"""
ООО «Фотопринт» · Управленческая платформа (трек 1 хакатона «Фабрика идей»).

Сервер без внешних зависимостей (только стандартная библиотека Python 3.10+):
  * REST/JSON API (/api/...), раздача фронтенда из ./static
  * вход по ролям, проверка прав на сервере (ОТ-02, УП-05)
  * расчёт KPI с формулой, источником и временем обновления (УП-02)
  * детализация с объяснением отклонения (УП-03), реестр решений с историей (УП-04)
  * журнал действий (ОТ-04)

Запуск:  python3 server.py      →  http://localhost:8080
"""
import calendar
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import data_gen

MINSK = data_gen.MINSK
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = data_gen.DATA
STATE = os.path.join(HERE, "state")
STATIC = os.path.join(HERE, "static")
PORT = int(os.environ.get("PORT", "8080"))
SESSION_HOURS = 8
DATA_REFRESH_SEC = max(5, int(os.environ.get("DATA_REFRESH_SEC", "15")))  # как часто перечитывать базу (data/*.json)
LOCK = threading.RLock()

MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
MONTHS_SHORT = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]


def now():
    return datetime.now(MINSK).replace(microsecond=0)


def iso(dt):
    return dt.isoformat(timespec="seconds") if dt else None


# ============================================================== пользователи и роли
# Тестовые учётные записи (синтетические). Пароли хранятся только в виде PBKDF2-хэша.
def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120_000).hex()


_USERS_SRC = [
    ("director", "Ольга Миронова", "director", None, "Директор"),
    ("prod", "Дмитрий Савич", "head", "D-PROD", "Руководитель производства"),
    ("sales", "Анна Лисовская", "head", "D-SALES", "Руководитель продаж и маркетинга"),
    ("analyst", "Павел Орлов", "analyst", None, "Аналитик / администратор"),
]
DEMO_PASSWORD = os.environ.get("FOTOPRINT_DEMO_PASSWORD", "demo2026")
USERS = {}
for login, name, role, dept, title in _USERS_SRC:
    salt = hashlib.sha256(("fotoprint-" + login).encode()).hexdigest()[:16]
    USERS[login] = {"login": login, "name": name, "role": role, "dept": dept, "title": title, "salt": salt, "hash": _hash(DEMO_PASSWORD, salt)}
ROLE_NAMES = {"director": "Директор", "head": "Руководитель подразделения", "analyst": "Аналитик / администратор"}
SESSIONS = {}  # token -> (login, expires_ts)

OWNERS = [
    {"id": "director", "name": "Ольга Миронова", "title": "Директор", "dept": None},
    {"id": "prod", "name": "Дмитрий Савич", "title": "Руководитель производства", "dept": "D-PROD"},
    {"id": "sales", "name": "Анна Лисовская", "title": "Руководитель продаж и маркетинга", "dept": "D-SALES"},
    {"id": "pos-bind", "name": "Начальник участка «Переплёт»", "title": "Должность", "dept": "D-PROD"},
    {"id": "pos-tech", "name": "Технолог производства", "title": "Должность", "dept": "D-PROD"},
    {"id": "pos-sup", "name": "Старший оператор поддержки", "title": "Должность", "dept": "D-SUP"},
    {"id": "pos-mkt", "name": "Маркетолог", "title": "Должность", "dept": "D-SALES"},
    {"id": "pos-fin", "name": "Финансовый менеджер", "title": "Должность", "dept": "D-FIN"},
    {"id": "pos-hr", "name": "HR-менеджер", "title": "Должность", "dept": "D-HR"},
]
DECISION_STATUSES = ["Новое", "В работе", "На проверке", "Выполнено", "Отменено"]
PRIORITIES = ["Высокий", "Средний", "Низкий"]


# ============================================================== хранилище данных
class Store:
    def load(self):
        meta_path = os.path.join(DATA, "meta.json")
        regenerate = True
        if os.path.exists(meta_path):
            with open(meta_path, encoding="utf-8") as f:
                regenerate = json.load(f).get("today") != now().date().isoformat()
        if regenerate:  # синтетический набор всегда «свежий» на дату демонстрации
            data_gen.generate()
        L = lambda n: json.load(open(os.path.join(DATA, n), encoding="utf-8"))  # noqa: E731
        self.meta, self.dict, self.sources = L("meta.json"), L("dict.json"), L("sources.json")
        self.customers, self.tickets, self.orders = L("crm_customers.json"), L("crm_tickets.json"), L("erp_orders.json")
        self.mes, self.web, self.staff, self.finance, self.plans = L("mes_production.json"), L("web_analytics.json"), L("zup_staff.json"), L("onec_finance.json"), L("plans.json")
        # заказы и клиенты, «поступившие» после генерации набора (имитация живого потока, см. simulate_tick)
        live = load_live(self.meta["today"])
        self.live_count = len(live["orders"])
        self.orders += live["orders"]
        self.customers += live["customers"]
        self.tickets += live["tickets"]
        if live["updates"]:  # смена статусов, выпуск, отгрузка, брак — поверх исходных записей ERP
            for o in self.orders:
                if o["id"] in live["updates"]:
                    o.update(live["updates"][o["id"]])
        for r in self.mes:
            if r["date"] == live["date"] and r["section_id"] in live["mes"]:
                r.update(live["mes"][r["section_id"]])
        for r in self.web:
            if r["date"] == live["date"] and r["channel_id"] in live["web"]:
                r.update(live["web"][r["channel_id"]])
        self.today = date.fromisoformat(self.meta["today"])
        self.data_start = date.fromisoformat(self.meta["start"])
        self.generated_at = datetime.fromisoformat(self.meta["generated_at"])
        self.dept = {d["id"]: d for d in self.dict["departments"]}
        self.product = {p["id"]: p for p in self.dict["products"]}
        self.section = {s["id"]: s for s in self.dict["sections"]}
        self.channel = {c["id"]: c for c in self.dict["channels"]}
        self.campaign = {c["id"]: c for c in self.dict["campaigns"]}
        self.customer = {c["id"]: c for c in self.customers}
        self.order = {}
        d = lambda s: datetime.fromisoformat(s) if s else None  # noqa: E731
        for o in self.orders:
            o["_c"] = d(o["created_at"])
            o["_cd"] = o["_c"].date()
            o["_due"] = date.fromisoformat(o["promised_date"])
            o["_sh"] = d(o.get("shipped_at"))
            o["_shd"] = o["_sh"].date() if o["_sh"] else None
            o["_pr"] = d(o.get("produced_at"))
            o["_prd"] = o["_pr"].date() if o["_pr"] else None
            o["_x"] = o["status"] == "Отменён"
            self.order[o["id"]] = o
        self.first_order = {}
        for o in self.orders:
            if not o["_x"] and o["customer_id"] not in self.first_order:
                self.first_order[o["customer_id"]] = o
        self.tickets_by_order = {}
        for t in self.tickets:
            t["_c"] = datetime.fromisoformat(t["created_at"])
            t["_cd"] = t["_c"].date()
            self.tickets_by_order.setdefault(t["order_id"], []).append(t)
        for r in self.mes:
            r["_d"] = date.fromisoformat(r["date"])
        for r in self.web:
            r["_d"] = date.fromisoformat(r["date"])
        self.plan_idx = {}
        for p in self.plans:
            self.plan_idx.setdefault((p["month"], p["metric"]), []).append(p)
        self.onec_cutoff = datetime.fromisoformat(next(s for s in self.sources if s["id"] == "1C")["failing_since"])
        self.signature = data_signature()
        self.loaded_at = now()


def data_signature():
    """Отпечаток базы: имена, размеры и время изменения файлов data/*.json."""
    out = []
    for n in sorted(os.listdir(DATA)):
        if n.endswith(".json"):
            st_ = os.stat(os.path.join(DATA, n))
            out.append((n, st_.st_size, st_.st_mtime_ns))
    return tuple(out)


S = Store()


def reload_data(force=False):
    """Перечитать базу, если файлы изменились (или наступил новый день). Новый набор собирается отдельно
    и подменяется целиком, поэтому запросы никогда не видят наполовину загруженные данные."""
    day_changed = S.meta["today"] != now().date().isoformat()
    if not force and not day_changed and data_signature() == S.signature:
        S.checked_at = now()
        return False
    fresh = Store()
    try:
        fresh.load()
    except Exception as e:  # noqa: BLE001 — битый файл: оставляем прежние данные
        S.reload_error = f"{type(e).__name__}: {e}"
        S.checked_at = now()
        print(f"База не перечитана, работают прежние данные: {S.reload_error}", flush=True)
        return False
    fresh.checked_at = fresh.loaded_at
    fresh.reload_error = None
    S.__dict__ = fresh.__dict__
    print(f"База перечитана: заказов {len(S.orders)}, данные на {S.today}", flush=True)
    return True


# ---------------------------------------------------------------- имитация живой работы компании
# Раз в DATA_REFRESH_SEC (15 с) меняются данные всех подразделений:
#   продажи (ERP, CRM, веб-аналитика) — 2–4 новых заказа, часть от новых клиентов, визиты и воронка сайта/приложения;
#   производство (ERP, MES) — заказы проходят этапы «Принят → Модерация → Производство → Готов → Передан в доставку → Завершён»,
#     выпуск и очередь участков, брак и перепечатки;
#   поддержка (Helpdesk) — новые обращения с соблюдением или нарушением SLA.
# Всё пишется в data/live_orders.json — часть базы; при генерации набора на новый день файл сбрасывается.
LIVE_SIM = os.environ.get("LIVE_SIM", "1") != "0"
LIVE_PATH = os.path.join(DATA, "live_orders.json")
_live_rnd = __import__("random").Random()
NEXT_STATUS = {"Принят": "Модерация", "Модерация": "Производство", "Производство": "Готов", "Готов": "Передан в доставку", "Передан в доставку": "Завершён"}
ORDER_LIVE_FIELDS = ("status", "status_history", "produced_at", "shipped_at", "delivered_at", "defect", "defect_reason", "reprint_cost")


def load_live(today):
    empty = {"date": today, "orders": [], "customers": [], "tickets": [], "updates": {}, "mes": {}, "web": {}}
    if not os.path.exists(LIVE_PATH):
        return empty
    with open(LIVE_PATH, encoding="utf-8") as f:
        live = json.load(f)
    if live.get("date") != today:  # поток прошлого дня к новому набору не относится
        return empty
    return {**empty, **live}


def save_live(live):
    tmp = LIVE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(live, f, ensure_ascii=False)
    os.replace(tmp, LIVE_PATH)


def _index_order(o):
    """Те же служебные поля, что проставляет Store.load."""
    d = lambda s: datetime.fromisoformat(s) if s else None  # noqa: E731
    o["_c"] = d(o["created_at"])
    o["_cd"] = o["_c"].date()
    o["_due"] = date.fromisoformat(o["promised_date"])
    o["_sh"] = d(o.get("shipped_at"))
    o["_shd"] = o["_sh"].date() if o["_sh"] else None
    o["_pr"] = d(o.get("produced_at"))
    o["_prd"] = o["_pr"].date() if o["_pr"] else None
    o["_x"] = o["status"] == "Отменён"


def _today_row(rows, key, val):
    return next((r for r in rows if r["date"] == S.meta["today"] and r[key] == val), None)


def _mes_push(live, sid, d_out=0.0, d_queue=0.0):
    """Изменить выпуск и очередь участка за сегодня (MES); выпуск ограничен 125 % мощности смены."""
    r = _today_row(S.mes, "section_id", sid)
    if not r:
        return
    r["output_units"] = round(min(r["output_units"] + d_out, max(r["capacity_units"], 1) * 1.25), 2)
    r["queue_units_eod"] = round(max(0.0, r["queue_units_eod"] + d_queue), 2)
    live["mes"][sid] = {"output_units": r["output_units"], "queue_units_eod": r["queue_units_eod"]}


def advance_orders(live, rnd, t):
    """Продвинуть заказы по этапам: на каждом этапе 1–2 самых давних заказа; за такт заказ сдвигается не больше чем на шаг."""
    moved = []
    pool = {}
    for o in S.orders:
        if o["status"] in NEXT_STATUS:
            pool.setdefault(o["status"], []).append(o)
    ts = iso(t)
    for status in ("Передан в доставку", "Готов", "Производство", "Модерация", "Принят"):  # с конца, чтобы не перескакивать этапы
        cand = sorted(pool.get(status, []), key=lambda o: o["status_history"][-1]["at"] if o.get("status_history") else o["created_at"])
        for o in cand[:rnd.choice([1, 1, 2]) if status != "Принят" else rnd.choice([2, 3])]:
            nxt = NEXT_STATUS[status]
            o["status"] = nxt
            o["status_history"] = (o.get("status_history") or []) + [{"status": nxt, "at": ts}]
            if nxt == "Готов":
                o["produced_at"] = ts
                if rnd.random() < 0.12:  # брак → перепечатка
                    o["defect"] = True
                    o["defect_reason"] = rnd.choice(data_gen.DEFECT_REASONS)
                    o["reprint_cost"] = round(o["cost"] * rnd.uniform(.85, 1.0), 2)
                _mes_push(live, o["section_id"], d_out=o["units"], d_queue=-o["units"])
            elif nxt == "Передан в доставку":
                o["shipped_at"] = ts
            elif nxt == "Завершён":
                o["delivered_at"] = ts
            _index_order(o)
            live["updates"][o["id"]] = {k: o[k] for k in ORDER_LIVE_FIELDS if k in o}
            moved.append(o)
    return moved


def new_ticket(live, rnd, t):
    """Новое обращение в поддержку по одному из недавних заказов (Helpdesk)."""
    recent = [o for o in S.orders[-400:] if not o["_x"]]
    if not recent:
        return None
    o = rnd.choice(recent)
    ch, _, sla = data_gen.pick_full(rnd, data_gen.TICKET_CHANNELS)
    first = max(1, int(rnd.gauss(sla * 0.8, sla * 0.45)))
    num = max(int(x["id"].split("-")[1]) for x in S.tickets) + 1
    tk = {"id": f"TCK-{num}", "customer_id": o["customer_id"], "order_id": o["id"], "topic": rnd.choice(data_gen.TICKET_TOPICS), "channel": ch,
          "created_at": iso(t), "first_response_min": first, "sla_min": sla, "sla_met": first <= sla, "resolved_at": None,
          "result": "В работе", "assignee": f"Оператор {rnd.randint(1, 9):02d}", "source": "Helpdesk"}
    live["tickets"].append(dict(tk))
    tk["_c"] = t
    tk["_cd"] = t.date()
    S.tickets.append(tk)
    S.tickets_by_order.setdefault(o["id"], []).append(tk)
    return tk


def simulate_tick(n=None):
    """Один такт живой работы компании: новые заказы (n или 2–4), движение заказов по этапам, выпуск, брак,
    визиты сайта, обращения. Возвращает список новых заказов."""
    rnd = _live_rnd
    t = now()
    if t.date().isoformat() != S.meta["today"]:
        return []  # наступил новый день — сначала перегенерируется набор
    n = n if n is not None else rnd.choice([2, 2, 3, 3, 4])
    with LOCK:
        live = load_live(S.meta["today"])
        moved = advance_orders(live, rnd, t)  # сначала двигаем имеющиеся, новые заказы стартуют с «Принят»
        last = max(int(o["id"].split("-")[1]) for o in S.orders)
        added = []
        for i in range(n):
            p = data_gen.pick(rnd, [(p, p["base"]) for p in data_gen.PRODUCTS])
            ch = data_gen.pick(rnd, [(c["id"], c["w"]) for c in data_gen.CHANNELS])
            created = t - timedelta(seconds=rnd.randint(0, max(1, DATA_REFRESH_SEC - 1)))
            if rnd.random() < 0.4 and S.customers:
                cust = S.customers[int(len(S.customers) * (1 - rnd.random() ** 1.6)) - 1]
            else:
                num = max(int(c["id"].split("-")[1]) for c in S.customers) + 1
                cust = {"id": f"CUS-{num:05d}", "segment": "Корпоративные" if ch == "CH-B2B" else ("Фотографы-профи" if rnd.random() < .1 else "Частные"),
                        "region": data_gen.pick(rnd, data_gen.REGIONS), "acquisition_channel_id": ch, "created_at": iso(created),
                        "phone_hash": hashlib.sha1(f"live-{num}".encode()).hexdigest()[:12], "marketing_consent": rnd.random() < .62}
                live["customers"].append(cust)
                S.customers.append(cust)
                S.customer[cust["id"]] = cust
            units = rnd.choice(p["units"]) * (rnd.choice([2, 3, 5]) if ch == "CH-B2B" else 1)
            gross = round(units * p["price"] * rnd.uniform(.75, 1.3), 2)
            o = {"id": f"ORD-{last + 1 + i}", "customer_id": cust["id"], "product_id": p["id"], "section_id": p["section"], "channel_id": ch,
                 "campaign_id": None, "segment": cust["segment"], "region": cust["region"], "units": units, "amount": gross, "discount": 0.0,
                 "currency": "BYN", "cost": round(gross * p["cost"] * rnd.uniform(.92, 1.08), 2), "created_at": iso(created),
                 "promised_date": (created.date() + timedelta(days=p["lead"])).isoformat(), "status": "Принят",
                 "status_history": [{"status": "Принят", "at": iso(created)}], "defect": False, "source": "ERP"}
            live["orders"].append(o)
            _index_order(o)
            S.orders.append(o)
            S.order[o["id"]] = o
            S.first_order.setdefault(cust["id"], o)
            added.append(o)
            _mes_push(live, p["section"], d_queue=units)  # новый заказ встаёт в очередь участка
            w = _today_row(S.web, "channel_id", ch)  # онлайн-заказ: визиты и воронка сайта/приложения
            if w:
                w["visits"] += rnd.randint(20, 45)
                w["projects_started"] += rnd.randint(2, 5)
                w["carts"] += rnd.randint(1, 2)
                w["orders"] += 1
                w["paid"] += 1
                live["web"][ch] = {k: w[k] for k in ("visits", "projects_started", "carts", "orders", "paid")}
        tk = new_ticket(live, rnd, t) if rnd.random() < 0.35 else None
        save_live({"date": live["date"], "orders": [{k: v for k, v in x.items() if not k.startswith("_")} for x in live["orders"]],
                   "customers": live["customers"], "tickets": [{k: v for k, v in x.items() if not k.startswith("_")} for x in live["tickets"]],
                   "updates": live["updates"], "mes": live["mes"], "web": live["web"]})
        S.live_count = len(live["orders"])
        S.signature = data_signature()  # свои изменения уже в памяти — полная перезагрузка не нужна
        S.loaded_at = now()
    print(f"Такт: новые заказы {', '.join(o['id'] for o in added)}; этапы сменили {len(moved)}"
          f"{'; обращение ' + tk['id'] if tk else ''} · новых за сегодня {S.live_count}", flush=True)
    return added


def auto_reload_loop():
    while True:
        time.sleep(DATA_REFRESH_SEC)
        try:
            reload_data()
            if LIVE_SIM:
                simulate_tick()
        except Exception:  # noqa: BLE001
            import traceback
            traceback.print_exc()


# ============================================================== журнал и состояние (решения)
def state_path(name):
    os.makedirs(STATE, exist_ok=True)
    return os.path.join(STATE, name)


def audit(user, action, obj, result="успех", details=None):
    entry = {"at": iso(now()), "user": user["login"] if user else "аноним", "user_name": user["name"] if user else "—",
             "role": ROLE_NAMES.get(user["role"]) if user else "—", "action": action, "object": obj, "result": result}
    if details:
        entry["details"] = details
    with LOCK, open(state_path("audit.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_audit():
    p = state_path("audit.jsonl")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def load_decisions():
    p = state_path("decisions.json")
    if not os.path.exists(p):
        save_decisions(seed_decisions())
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_decisions(items):
    p = state_path("decisions.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def seed_decisions():
    t = S.today
    D = lambda k, h=10: iso(datetime.combine(t + timedelta(days=k), datetime.min.time(), MINSK).replace(hour=h))  # noqa: E731
    dd = lambda k: (t + timedelta(days=k)).isoformat()  # noqa: E731
    base = [
        dict(id=1, kpi_id="defect", dept="D-PROD", title="Брак «Цветопередача» на цифровой печати",
             impact="Перепечатка ≈6 % заказов фотопечати, рост обращений «Качество продукции»",
             cause="Сбой калибровки принтеров после обновления ПО (MES: участок «Цифровая печать»)",
             action="Перекалибровать принтеры, ввести ежедневный контроль цветовой шкалы", owner="pos-tech",
             due=dd(-170), priority="Высокий", status="Выполнено", created=-182, by="director"),
        dict(id=2, kpi_id="on_time", dept="D-PROD", title="Опоздания фотокниг из-за очереди на переплёте",
             impact="Доля заказов в срок по фотокнигам упала до ~45 %, растут обращения «Сроки изготовления»",
             cause="Нехватка 5 операторов переплёта (1С:ЗУП) и рост спроса по акции «Фотокниги −20%»",
             action="Временная вторая смена: 3 оператора из цифровой печати; ускорить найм 5 операторов", owner="prod",
             due=dd(14), priority="Высокий", status="В работе", created=-11, by="director"),
        dict(id=3, kpi_id="defect", dept="D-PROD", title="Расслоение переплёта после смены партии клея",
             impact="Брак на переплёте до 11 %, затраты на перепечатку выше плана",
             cause="Новая партия клея от поставщика (с даты начала всплеска брака)",
             action="Вернуть прежнего поставщика, ввести входной контроль каждой партии", owner="pos-bind",
             due=dd(-3), priority="Высокий", status="В работе", created=-25, by="prod"),
        dict(id=4, kpi_id="sla", dept="D-SUP", title="Падение SLA поддержки",
             impact="Менее половины обращений получают первый ответ в срок",
             cause="Всплеск обращений «Сроки изготовления» и «Качество продукции» при нехватке операторов",
             action="Подключить 2 операторов на чат в часы пик, шаблоны ответов о сроках", owner="pos-sup",
             due=dd(7), priority="Средний", status="Новое", created=-2, by="director"),
        dict(id=5, kpi_id="cac", dept="D-SALES", title="Рост стоимости привлечения клиента в акции",
             impact="CAC выше плана при скидке 20 % — маржа акции под давлением",
             cause="Высокий бюджет кампании «Фотокниги −20%» в Instagram и Google Ads",
             action="Перераспределить бюджет в email-рассылку и программу лояльности", owner="pos-mkt",
             due=dd(10), priority="Средний", status="На проверке", created=-9, by="sales"),
    ]
    out = []
    for b in base:
        created = D(b.pop("created"))
        by = b.pop("by")
        hist = [{"at": created, "user": by, "user_name": USERS[by]["name"], "action": "Создано", "changes": []}]
        if b["status"] != "Новое":
            hist.append({"at": iso(datetime.fromisoformat(created) + timedelta(days=1, hours=2)), "user": by, "user_name": USERS[by]["name"],
                         "action": "Изменено", "changes": [{"field": "status", "from": "Новое", "to": "В работе"}]})
        if b["status"] in ("Выполнено", "На проверке"):
            hist.append({"at": iso(datetime.fromisoformat(created) + timedelta(days=6)), "user": by, "user_name": USERS[by]["name"],
                         "action": "Изменено", "changes": [{"field": "status", "from": "В работе", "to": b["status"]}]})
        out.append({**b, "created_at": created, "created_by": by, "updated_at": hist[-1]["at"], "rev": len(hist), "history": hist, "context": None})
    return out


# ============================================================== периоды и фильтры
class Period:
    def __init__(self, key):
        t = S.today
        key = key or t.strftime("%Y-%m")
        self.key = key
        if key == "last28":
            self.start, self.end, self.label = t - timedelta(days=27), t, "Последние 4 недели"
            self.prev = (self.start - timedelta(days=28), self.start - timedelta(days=1))
        elif key == "last90":
            self.start, self.end, self.label = t - timedelta(days=89), t, "Последние 90 дней"
            self.prev = (self.start - timedelta(days=90), self.start - timedelta(days=1))
        else:
            m = re.fullmatch(r"(\d{4})-(\d{2})", key)
            if not m:
                raise ApiError(400, "Неверный формат периода. Ожидается ГГГГ-ММ, last28 или last90.")
            y, mo = int(m.group(1)), int(m.group(2))
            if not 1 <= mo <= 12:
                raise ApiError(400, "Неверный месяц в периоде.")
            self.start = date(y, mo, 1)
            self.end = date(y, mo, calendar.monthrange(y, mo)[1])
            if self.start > t or self.end < S.data_start:
                raise ApiError(400, f"Нет данных за период {key}. Доступно с {S.data_start.isoformat()} по {t.isoformat()}.")
            self.label = f"{MONTHS[mo - 1]} {y}"
            pm = (self.start - timedelta(days=1)).replace(day=1)
            self.prev = (pm, self.start - timedelta(days=1))
        self.to = min(self.end, t)
        self.days = (self.end - self.start).days + 1
        self.elapsed = (self.to - self.start).days + 1
        self.partial = self.end > t

    def json(self):
        return {"key": self.key, "label": self.label, "start": self.start.isoformat(), "end": self.end.isoformat(), "to": self.to.isoformat(),
                "partial": self.partial, "elapsed_days": self.elapsed, "days": self.days,
                "prev": {"start": self.prev[0].isoformat(), "end": self.prev[1].isoformat()}}


def period_options():
    opts = []
    m = S.today.replace(day=1)
    while m >= S.data_start:
        opts.append({"key": m.strftime("%Y-%m"), "label": f"{MONTHS[m.month - 1]} {m.year}" + (" (текущий)" if m.month == S.today.month and m.year == S.today.year else "")})
        m = (m - timedelta(days=1)).replace(day=1)
    return [{"key": "last28", "label": "Последние 4 недели"}, *opts[:7], {"key": "last90", "label": "Последние 90 дней"}]


def parse_filters(q, user):
    product = (q.get("product") or "all")
    dept = (q.get("dept") or "all")
    if product != "all" and product not in S.product:
        raise ApiError(400, "Неизвестный продукт в фильтре.")
    if dept != "all" and dept not in S.dept:
        raise ApiError(400, "Неизвестное подразделение в фильтре.")
    if user and user["role"] == "head":  # руководитель всегда смотрит только своё подразделение
        dept = user["dept"]
    return {"product": None if product == "all" else product, "dept": None if dept == "all" else dept}


# ============================================================== KPI: определения
KPIS = [
    dict(id="revenue", name="Оборот", dept="D-SALES", unit="BYN", dir=1, closed=False, kind="sum", src=["ERP"], product=True,
         formula="Σ сумм заказов (BYN), созданных в периоде, без отменённых"),
    dict(id="gross_margin", name="Валовая маржа", dept="D-FIN", unit="%", dir=1, closed=True, kind="ratio", src=["ERP", "1C"], product=True, tol=2.0,
         formula="(Выручка − себестоимость − затраты на перепечатку) / выручка × 100 %"),
    dict(id="on_time", name="Заказы в срок", dept="D-PROD", unit="%", dir=1, closed=False, kind="ratio", src=["ERP"], product=True, target=95.0, tol=3.0,
         formula="Заказы со сроком в периоде, отгруженные не позднее обещанной даты / все заказы со сроком в периоде × 100 % (неотгруженные просроченные — опоздавшие)"),
    dict(id="defect", name="Брак и перепечатка", dept="D-PROD", unit="%", dir=-1, closed=False, kind="ratio", src=["ERP", "MES"], product=True, target=2.0, tol=0.5,
         formula="Изготовленные заказы с браком (отправлены на перепечатку) / изготовленные заказы × 100 %"),
    dict(id="new_customers", name="Новые клиенты", dept="D-SALES", unit="чел.", dir=1, closed=False, kind="sum", src=["CRM", "ERP"], product=True,
         formula="Клиенты CRM, первый неотменённый заказ которых в ERP создан в периоде"),
    dict(id="active_customers", name="Активные клиенты", dept="D-SALES", unit="чел.", dir=1, closed=False, kind="count", src=["CRM", "ERP"], product=True,
         formula="Уникальные клиенты с ≥ 1 неотменённым заказом в периоде"),
    dict(id="sla", name="SLA поддержки", dept="D-SUP", unit="%", dir=1, closed=False, kind="ratio", src=["HELPDESK"], product=True, target=90.0, tol=5.0,
         formula="Обращения с первым ответом в пределах SLA канала (чат 15 мин, телефон 10 мин, Instagram 60 мин, email 4 ч) / все обращения × 100 %"),
    dict(id="load", name="Загрузка мощности", dept="D-PROD", unit="%", dir=0, closed=False, kind="ratio", src=["MES"], product=True, target=85.0,
         formula="Выпуск, изделий / доступная мощность участков, изделий × 100 % (норма 65–92 %, выше 100 % — перегрузка)"),
    dict(id="staffing", name="Обеспеченность персоналом", dept="D-HR", unit="%", dir=1, closed=False, kind="ratio", src=["ZUP"], product=False, target=95.0, tol=3.0,
         formula="Фактическая численность / штатная численность × 100 % (по месяцам периода)"),
    dict(id="avg_check", name="Средний чек", dept="D-SALES", unit="BYN", dir=1, closed=False, kind="avg", src=["ERP"], product=True,
         formula="Оборот / число неотменённых заказов"),
    dict(id="conversion", name="Конверсия сайта и приложения", dept="D-SALES", unit="%", dir=1, closed=False, kind="ratio", src=["WEB", "ERP"], product=False, target=3.4, tol=0.3,
         formula="Онлайн-заказы (сайт picPac.by + приложение) / визиты × 100 %"),
    dict(id="repeat", name="Повторные покупки", dept="D-SALES", unit="%", dir=1, closed=False, kind="ratio", src=["CRM", "ERP"], product=True, target=33.0, tol=3.0,
         formula="Активные клиенты периода, у которых был заказ раньше периода / активные клиенты × 100 %"),
    dict(id="lead_time", name="Lead time", dept="D-PROD", unit="дн.", dir=-1, closed=False, kind="avg", src=["ERP", "MES"], product=True, target=2.6, tol=0.3,
         formula="Среднее (дата отгрузки − дата создания заказа) по заказам, отгруженным в периоде, дней"),
    dict(id="cac", name="Стоимость привлечения клиента", dept="D-SALES", unit="BYN", dir=-1, closed=True, kind="special", src=["1C", "CRM"], product=False,
         formula="Расходы на маркетинг (1С, статья БДР «Маркетинг») / новые клиенты"),
    dict(id="reprint_cost", name="Затраты на перепечатку", dept="D-PROD", unit="BYN", dir=-1, closed=True, kind="sum", src=["ERP", "MES"], product=True,
         formula="Σ себестоимости повторного изготовления заказов с браком"),
    dict(id="payroll", name="Фонд оплаты труда", dept="D-HR", unit="BYN", dir=-1, closed=True, kind="sum", src=["ZUP"], product=False,
         formula="Σ начисленной зарплаты (1С:ЗУП, факт) против штатного ФОТ (план)"),
]
KPI = {k["id"]: k for k in KPIS}
GENDER = {"gross_margin": "f", "on_time": "pl", "new_customers": "pl", "active_customers": "pl", "load": "f", "staffing": "f", "conversion": "f",
          "repeat": "pl", "cac": "f", "reprint_cost": "pl"}
DIMS = {
    "revenue": ["product", "channel", "campaign", "segment"], "gross_margin": ["product", "campaign", "channel"],
    "on_time": ["section", "product", "channel"], "defect": ["reason", "section", "product"],
    "new_customers": ["channel", "campaign", "region"], "active_customers": ["region", "segment", "channel"],
    "sla": ["topic", "tchannel", "product"], "load": ["section"], "staffing": ["dept"],
    "avg_check": ["product", "channel", "segment"], "conversion": ["channel"], "repeat": ["region", "segment"],
    "lead_time": ["section", "product", "channel"], "cac": [], "reprint_cost": ["reason", "section", "product"], "payroll": ["dept"],
}
DIM_LABEL = {"product": "Продукт", "section": "Участок", "channel": "Канал", "campaign": "Кампания", "segment": "Сегмент", "region": "Регион",
             "reason": "Причина брака", "topic": "Тема обращения", "tchannel": "Канал обращения", "dept": "Подразделение"}
CARDS = {None: ["revenue", "on_time", "defect", "sla"], "D-SALES": ["revenue", "new_customers", "avg_check", "conversion"],
         "D-PROD": ["on_time", "defect", "load", "lead_time"], "D-SUP": ["sla", "on_time", "defect", "active_customers"],
         "D-FIN": ["revenue", "gross_margin", "cac", "payroll"], "D-HR": ["staffing", "payroll", "load", "on_time"]}


def can_see(user, kpi):
    """Директор и аналитик видят все KPI; руководитель — только показатели своего подразделения (открытые и закрытые)."""
    return user["role"] in ("director", "analyst") or kpi["dept"] == user["dept"]


# Экраны дашборда. Директор видит все; аналитик — все (реестр только для чтения);
# руководитель подразделения — только дашборд своего подразделения.
ALL_SCREENS = ("pulse", "sales", "production", "finance", "decisions", "forecast", "quality", "audit")
DEPT_SCREENS = {"D-PROD": ("production", "forecast"), "D-SALES": ("sales",)}
SCREEN_TITLES = {"pulse": "Пульс компании", "sales": "Продажи и клиенты", "production": "Производство и качество", "finance": "Финансы и люди",
                 "decisions": "Реестр решений", "forecast": "Прогноз спроса и мощности", "quality": "Качество данных", "audit": "Журнал действий",
                 "tickets": "Обращения поддержки"}
# какие ряды (оборот / заказы / выпуск) относятся к подразделению — для графиков и ИИ-ассистента
DEPT_METRICS = {"D-PROD": ("orders", "output"), "D-SALES": ("revenue", "orders")}


def screens_for(user):
    if user["role"] in ("director", "analyst"):
        return list(ALL_SCREENS)
    return list(DEPT_SCREENS.get(user["dept"], ()))


def metrics_for(user):
    if user["role"] in ("director", "analyst"):
        return ("revenue", "orders", "output")
    return DEPT_METRICS.get(user["dept"], ())


def require_screen(user, screen):
    if screen not in screens_for(user) and not (screen == "tickets" and user["role"] in ("director", "analyst")):
        audit(user, "Открытие экрана", SCREEN_TITLES[screen], "отказано")
        raise ApiError(403, f"Экран «{SCREEN_TITLES[screen]}» недоступен: руководитель подразделения видит только дашборд своего подразделения.")


def src_info(ids):
    out = []
    for sid in ids:
        s = next(x for x in S.sources if x["id"] == sid)
        out.append({"id": sid, "name": s["name"], "last_sync": iso(last_sync(s))})
    return out


def last_sync(s):
    """Имитация планировщика интеграций: источник выгружается каждые interval_min минут; 1С — со сбоем."""
    if s.get("failing_since"):
        return datetime.fromisoformat(s["failing_since"])
    n = now()
    mins = (n.hour * 60 + n.minute) // s["interval_min"] * s["interval_min"]
    return n.replace(hour=mins // 60, minute=mins % 60, second=0)


# ============================================================== KPI: расчёт
def dim_vals(o):
    return {"product": S.product[o["product_id"]]["name"], "section": S.section[o["section_id"]]["name"],
            "channel": S.channel[o["channel_id"]]["name"] if o["channel_id"] else "Не указан (пропуск)",
            "campaign": S.campaign[o["campaign_id"]]["name"] if o["campaign_id"] else "Без кампании",
            "segment": o["segment"], "region": o["region"]}


def orders_in(a, b, F, field="_cd"):
    p = F.get("product")
    return [o for o in S.orders if not o["_x"] and o[field] and a <= o[field] <= b and (not p or o["product_id"] == p)]


def month_overlaps(a, b):
    m = a.replace(day=1)
    while m <= b:
        dim = calendar.monthrange(m.year, m.month)[1]
        me = m.replace(day=dim)
        s, e = max(a, m), min(b, me)
        yield m.strftime("%Y-%m"), ((e - s).days + 1) / dim
        m = me + timedelta(days=1)


def plan_sum(metric, a, b, product=None, section=None):
    total = 0.0
    for mo, share in month_overlaps(a, b):
        for p in S.plan_idx.get((mo, metric), []):
            if product and p.get("product_id") not in (None, product):
                continue
            if section and p.get("section_id") != section:
                continue
            total += p["value"] * share
    return total


def items(kid, a, b, F):
    """Строки расчёта KPI: (измерения, числитель, знаменатель)."""
    t = S.today
    if kid in ("revenue", "avg_check"):
        return [(dim_vals(o), o["amount"], 1) for o in orders_in(a, b, F)]
    if kid == "gross_margin":
        return [(dim_vals(o), o["amount"] - o["cost"] - o.get("reprint_cost", 0), o["amount"]) for o in orders_in(a, b, F)]
    if kid == "on_time":
        hi = min(b, t - timedelta(days=1))
        return [(dim_vals(o), 1 if (o["_shd"] and o["_shd"] <= o["_due"]) else 0, 1) for o in orders_in(a, hi, F, "_due")] if hi >= a else []
    if kid == "defect":
        return [({**dim_vals(o), "reason": o.get("defect_reason") or "Без брака"}, 1 if o["defect"] else 0, 1) for o in orders_in(a, b, F, "_prd")]
    if kid == "reprint_cost":
        return [({**dim_vals(o), "reason": o.get("defect_reason")}, o.get("reprint_cost", 0), 1) for o in orders_in(a, b, F, "_prd") if o["defect"]]
    if kid == "lead_time":
        return [(dim_vals(o), (o["_sh"] - o["_c"]).total_seconds() / 86400, 1) for o in orders_in(a, b, F, "_shd")]
    if kid == "new_customers":
        p = F.get("product")
        out = []
        for cid, o in S.first_order.items():
            if a <= o["_cd"] <= b and (not p or o["product_id"] == p):
                out.append((dim_vals(o), 1, 1))
        return out
    if kid in ("active_customers", "repeat"):
        seen = {}
        for o in orders_in(a, b, F):
            seen.setdefault(o["customer_id"], o)
        res = []
        for cid, o in seen.items():
            dv = dim_vals(o)
            num = 1 if kid == "active_customers" else (1 if S.first_order[cid]["_cd"] < a else 0)
            res.append((dv, num, 1))
        return res
    if kid == "sla":
        p = F.get("product")
        res = []
        for tk in S.tickets:
            if a <= tk["_cd"] <= b:
                o = S.order.get(tk["order_id"])
                if p and (not o or o["product_id"] != p):
                    continue
                res.append(({"topic": tk["topic"], "tchannel": tk["channel"], "product": S.product[o["product_id"]]["name"] if o else "—"}, 1 if tk["sla_met"] else 0, 1))
        return res
    if kid == "load":
        sec = S.product[F["product"]]["section"] if F.get("product") else None
        return [({"section": S.section[r["section_id"]]["name"]}, r["output_units"], r["capacity_units"]) for r in S.mes
                if a <= r["_d"] <= min(b, t) and (not sec or r["section_id"] == sec)]
    if kid in ("staffing", "payroll"):
        res = []
        for mo, share in month_overlaps(a, b):
            for r in S.staff:
                if r["month"] == mo and not r["section_id"]:
                    dv = {"dept": S.dept[r["dept_id"]]["name"]}
                    if kid == "staffing":
                        res.append((dv, r["headcount_fact"] * share, r["headcount_plan"] * share))
                    else:
                        res.append((dv, r["payroll_fact"] * share, r["payroll_plan"] * share))
        return res
    if kid == "conversion":
        return [({"channel": S.channel[r["channel_id"]]["name"]}, r["orders"], r["visits"]) for r in S.web if a <= r["_d"] <= min(b, t)]
    return []


def value_of(kid, rows):
    k = KPI[kid]["kind"]
    if k in ("sum", "count"):
        return sum(r[1] for r in rows)
    den = sum(r[2] for r in rows)
    if not den:
        return None
    v = sum(r[1] for r in rows) / den
    return v * 100 if k == "ratio" else v


def marketing_fact(a, b):
    total = 0.0
    for mo, share in month_overlaps(a, b):
        for r in S.finance:
            if r["month"] == mo and r["kind"] == "БДР" and r["article"] == "Маркетинг":
                total += r["fact"] * share
    return total


def fact(kid, a, b, F):
    if kid == "cac":
        n = value_of("new_customers", items("new_customers", a, b, F))
        return marketing_fact(a, min(b, S.today)) / n if n else None
    if kid == "payroll":
        return sum(r[1] for r in items("payroll", a, b, F))
    return value_of(kid, items(kid, a, b, F))


def plan(kid, P, F):
    a, b = P.start, P.end
    p = F.get("product")
    share = 1.0
    if p:
        tot = plan_sum("revenue", a, b)
        share = plan_sum("revenue", a, b, p) / tot if tot else 0
    k = KPI[kid]
    if "target" in k:
        return k["target"]
    if kid == "revenue":
        return plan_sum("revenue", a, b, p)
    if kid == "gross_margin":
        r, c = plan_sum("revenue", a, b, p), plan_sum("cost", a, b, p)
        return (r - c - plan_sum("reprint_cost", a, b) * share) / r * 100 if r else None
    if kid == "avg_check":
        n = plan_sum("orders", a, b, p)
        return plan_sum("revenue", a, b, p) / n if n else None
    if kid == "new_customers":
        return plan_sum("new_customers", a, b) * share
    if kid == "active_customers":
        return plan_sum("active_customers", a, b) * share
    if kid == "cac":
        n = plan_sum("new_customers", a, b)
        return plan_sum("marketing", a, b) / n if n else None
    if kid == "reprint_cost":
        return plan_sum("reprint_cost", a, b) * share
    if kid == "payroll":
        return sum(r[2] for r in items("payroll", a, b, F))
    return None


def kpi_values(kid, P, F):
    k = KPI[kid]
    cur = fact(kid, P.start, P.end, F)
    prev = fact(kid, P.prev[0], P.prev[1], F)
    pl = plan(kid, P, F)
    fc = cur
    if P.partial and cur is not None:
        if k["kind"] == "sum" and kid != "payroll":
            fc = cur * P.days / P.elapsed
        elif k["kind"] == "count":
            fc = cur * (P.days / P.elapsed) ** 0.85
        elif k["kind"] in ("ratio", "avg") and kid not in ("staffing",):
            a14 = max(P.start, S.today - timedelta(days=13))
            fc = fact(kid, a14, S.today, F)
        elif kid == "cac":
            fc = cur
    cmp_v = fc if (P.partial and k["kind"] in ("sum", "count")) else cur
    dev, dev_unit, status = None, "%", "ok"
    if cmp_v is not None and pl:
        if k["unit"] == "%":
            dev, dev_unit = cmp_v - pl, "п.п."
        else:
            dev = (cmp_v - pl) / pl * 100
        status = status_of(k, cmp_v, pl)
    return {"fact": rnd(cur), "plan": rnd(pl), "forecast": rnd(fc), "prev": rnd(prev), "dev": rnd(dev), "dev_unit": dev_unit, "status": status,
            "compare": "forecast" if (P.partial and k["kind"] in ("sum", "count")) else "fact"}


def status_of(k, v, pl):
    if k["dir"] == 0:  # загрузка: коридор
        if v > 100 or v < 55:
            return "crit"
        if v > 92 or v < 65:
            return "warn"
        return "ok"
    tol = k.get("tol")
    if tol is None:
        tol = abs(pl) * 0.04
    diff = (v - pl) * k["dir"]
    if diff >= 0:
        return "ok"
    return "warn" if diff >= -tol else "crit"


def rnd(v, n=2):
    return None if v is None else round(v, n)


def kpi_public(user, kid, P, F, with_values=True):
    k = KPI[kid]
    base = {"id": kid, "name": k["name"], "dept": k["dept"], "dept_name": S.dept[k["dept"]]["name"], "unit": k["unit"], "dir": k["dir"],
            "closed": k["closed"], "formula": k["formula"], "sources": src_info(k["src"]), "product_scope": k["product"],
            "target": k.get("target")}
    base["updated_at"] = min(s["last_sync"] for s in base["sources"])
    if not can_see(user, k):
        return {**base, "locked": True, "formula": None}
    if with_values:
        base.update(kpi_values(kid, P, F))
    n = load_kpi_notes().get(kid, {})
    base["responsible"] = owner_public(n.get("owner"))
    base["comments_count"] = sum(1 for c in n.get("feed", []) if c["kind"] == "comment")
    return base


# ============================================================== ответственные и комментарии по KPI
# state/kpi_notes.json: {kpi_id: {"owner": id | null, "feed": [{id, kind: comment|assign, at, user, user_name, text}]}}
def load_kpi_notes():
    p = state_path("kpi_notes.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_kpi_notes(data):
    p = state_path("kpi_notes.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def owner_public(oid):
    o = next((x for x in OWNERS if x["id"] == oid), None)
    return {"id": o["id"], "name": o["name"], "title": o["title"]} if o else None


def kpi_notes_public(user, kid):
    n = load_kpi_notes().get(kid, {})
    return {"owner": owner_public(n.get("owner")), "feed": n.get("feed", []), "can_edit": user["role"] == "director"}


def kpi_notes_target(user, kid, action):
    """Проверки для изменения: KPI существует, пишет только директор."""
    if kid not in KPI:
        raise ApiError(404, "Показатель не найден.")
    if user["role"] != "director":
        audit(user, action, f"KPI «{KPI[kid]['name']}»", "отказано")
        raise ApiError(403, "Оставлять комментарии и назначать ответственных по показателям может только директор.")
    return KPI[kid]


def api_kpi_comment(user, kid, body):
    k = kpi_notes_target(user, kid, "Комментарий к показателю")
    text = str(body.get("text") or "").strip()
    if not text:
        raise ApiError(422, {"message": "Введите текст комментария.", "fields": {"text": "Введите текст комментария."}})
    if len(text) > 1000:
        raise ApiError(422, {"message": "Комментарий длиннее 1000 символов.", "fields": {"text": "Не больше 1000 символов."}})
    with LOCK:
        data = load_kpi_notes()
        n = data.setdefault(kid, {"owner": None, "feed": []})
        cid = max([c["id"] for c in n["feed"]] or [0]) + 1
        n["feed"].append({"id": cid, "kind": "comment", "at": iso(now()), "user": user["login"], "user_name": user["name"], "text": text})
        save_kpi_notes(data)
    audit(user, "Комментарий к показателю", f"KPI «{k['name']}»", details={"length": len(text)})
    return kpi_notes_public(user, kid)


def api_kpi_owner(user, kid, body):
    k = kpi_notes_target(user, kid, "Назначение ответственного")
    oid = body.get("owner") or None
    if oid is not None and not owner_public(oid):
        raise ApiError(422, {"message": "Выберите ответственного из списка.", "fields": {"owner": "Выберите ответственного из списка."}})
    with LOCK:
        data = load_kpi_notes()
        n = data.setdefault(kid, {"owner": None, "feed": []})
        if n.get("owner") == oid:
            return kpi_notes_public(user, kid)
        n["owner"] = oid
        cid = max([c["id"] for c in n["feed"]] or [0]) + 1
        who = owner_public(oid)
        n["feed"].append({"id": cid, "kind": "assign", "at": iso(now()), "user": user["login"], "user_name": user["name"],
                          "text": f"Ответственный: {who['name']}" if who else "Ответственный снят", "owner": oid})
        save_kpi_notes(data)
    audit(user, "Назначение ответственного", f"KPI «{k['name']}»", details={"owner": oid})
    return kpi_notes_public(user, kid)


# ============================================================== детализация и объяснение
class Range:
    def __init__(self, a, b, label):
        self.start, self.end, self.label = a, b, label


def baseline(kid, P, F):
    """База сравнения: последний из 4 предыдущих периодов, где KPI был в норме; иначе — непосредственно предыдущий."""
    k = KPI[kid]
    a, b = P.prev
    first = None
    for _ in range(4):
        if b < S.data_start:
            break
        label = f"{MONTHS[a.month - 1].lower()} {a.year}" if a.day == 1 and P.key not in ("last28", "last90") else f"{a.strftime('%d.%m')}–{b.strftime('%d.%m')}"
        r = Range(a, b, label)
        first = first or r
        v = fact(kid, a, b, F)
        pl = plan(kid, r, F)
        if v is not None and pl and status_of(k, v, pl) == "ok":
            return r, r is not first
        if P.key in ("last28", "last90"):
            ln = (b - a).days + 1
            a, b = a - timedelta(days=ln), a - timedelta(days=1)
        else:
            b = a - timedelta(days=1)
            a = b.replace(day=1)
    return first or Range(*P.prev, "предыдущий период"), False


def breakdown(kid, P, F, base=None):
    k = KPI[kid]
    base = base or Range(*P.prev, "предыдущий период")
    cur = items(kid, P.start, P.end, F)
    prv = items(kid, base.start, base.end, F)
    total_cur, total_prev = value_of(kid, cur), value_of(kid, prv)
    den_c = sum(r[2] for r in cur) or 1
    den_p = sum(r[2] for r in prv) or 1
    mult = 100 if k["kind"] == "ratio" else 1
    out = []
    for dim in DIMS.get(kid, []):
        g = {}
        for dv, n, d in cur:
            x = g.setdefault(dv.get(dim, "—"), [0, 0, 0, 0])
            x[0] += n
            x[1] += d
        for dv, n, d in prv:
            x = g.setdefault(dv.get(dim, "—"), [0, 0, 0, 0])
            x[2] += n
            x[3] += d
        rows = []
        for key, (nc, dc, np_, dp) in g.items():
            if k["kind"] in ("sum", "count"):
                val, pval, contrib = nc, np_, nc - np_
            else:
                val = nc / dc * mult if dc else None
                pval = np_ / dp * mult if dp else None
                # разложение изменения: эффект показателя внутри группы + эффект структуры (сумма по группам = общему изменению)
                wc, wp = dc / den_c, dp / den_p
                rc = nc / dc if dc else 0
                Rp = sum(r[1] for r in prv) / den_p if prv else 0
                rp = np_ / dp if dp else Rp
                contrib = (wc * (rc - rp) + (wc - wp) * (rp - Rp)) * mult if dc else (-(wp) * (rp - Rp)) * mult
            rows.append({"key": key, "value": rnd(val), "prev": rnd(pval), "weight": rnd(dc / den_c * 100 if k["kind"] not in ("sum", "count") else (nc / total_cur * 100 if total_cur else 0), 1),
                         "contribution": rnd(contrib), "count": dc if k["kind"] not in ("sum", "count") else None})
        rows.sort(key=lambda r: -abs(r["contribution"] or 0))
        out.append({"dim": dim, "label": DIM_LABEL[dim], "rows": rows[:12]})
    return out, total_cur, total_prev


def dmy(s):
    return date.fromisoformat(s).strftime("%d.%m.%Y")


def ru(v, n=0):
    """Число в русском формате: пробел (неразрывный) между разрядами, запятая в дробной части."""
    return f"{v:,.{n}f}".replace(",", " ").replace(".", ",")


def fmt_v(k, v):
    if v is None:
        return "—"
    if k["unit"] == "%":
        return f"{ru(v, 1)} %"
    if k["unit"] == "BYN":
        return f"{ru(v, 2 if k['kind'] == 'avg' or abs(v) < 100 else 0)} BYN"
    if k["unit"] == "дн.":
        return f"{ru(v, 1)} дн."
    return f"{ru(v)} {k['unit']}"


def explain(kid, P, F, bds, cur, prev, base, skipped):
    k = KPI[kid]
    if cur is None or prev is None:
        return {"text": "Недостаточно данных за период сравнения, чтобы объяснить изменение.", "factors": [], "baseline": base.label}
    delta = cur - prev
    unit = "п.п." if k["unit"] == "%" else k["unit"]
    vs = f"по сравнению с периодом «{base.label}»" + (" — последним, когда показатель был в норме" if skipped else "")
    tol = k.get("tol") or abs(prev) * 0.02
    if abs(delta) < tol / 4:
        return {"text": f"{k['name']}: {fmt_v(k, cur)} — почти без изменений {vs} ({fmt_v(k, prev)}).", "factors": [], "baseline": base.label, "good": True}
    best = None
    for bd in bds:  # измерения упорядочены по смысловому приоритету (DIMS)
        r = next((x for x in bd["rows"] if (x["contribution"] or 0) * delta > 0), None)
        if r and abs(r["contribution"]) >= abs(delta) * 0.35:
            best = (bd, r)
            break
    if not best:
        for bd in bds:
            r = next((x for x in bd["rows"] if (x["contribution"] or 0) * delta > 0), None)
            if r and (best is None or abs(r["contribution"]) > abs(best[1]["contribution"])):
                best = (bd, r)
    good = delta * (k["dir"] or 1) >= 0
    g = GENDER.get(kid, "m")
    verb = {"m": ("вырос", "снизился"), "f": ("выросла", "снизилась"), "pl": ("выросли", "снизились")}[g][0 if delta > 0 else 1]
    text = f"{k['name']} {verb} с {fmt_v(k, prev)} до {fmt_v(k, cur)} ({'+' if delta > 0 else '−'}{ru(abs(delta), 1)} {unit}) {vs}"
    factors = []
    if best:
        bd, r = best
        share = min(100, abs(r["contribution"]) / abs(delta) * 100)
        text += f". Основной вклад — {bd['label'].lower()} «{r['key']}»: {fmt_contrib(k, r['contribution'])} ({share:.0f} % изменения)."
        factors.append({"dim": bd["dim"], "label": bd["label"], "key": r["key"], "contribution": r["contribution"], "share": rnd(share, 0)})
        factors += linked_factors(bd["dim"], r["key"], P, F)
    else:
        text += "."
    if kid == "sla":
        factors += sla_factors(P, base)
    return {"text": text, "good": good, "factors": factors, "baseline": base.label}


def sla_factors(P, base):
    cur = [t for t in S.tickets if P.start <= t["_cd"] <= P.to]
    prv = [t for t in S.tickets if base.start <= t["_cd"] <= base.end]
    dc, dp = max(1, (P.to - P.start).days + 1), max(1, (base.end - base.start).days + 1)
    out = [{"source": "Helpdesk", "text": f"Обращений в день: {ru(len(cur) / dc, 1)} против {ru(len(prv) / dp, 1)} в базовом периоде"}]
    topics = {}
    for t in cur:
        topics[t["topic"]] = topics.get(t["topic"], 0) + 1
    top = sorted(topics.items(), key=lambda kv: -kv[1])[:2]
    if top:
        out.append({"source": "Helpdesk", "text": "Основные темы: " + ", ".join(f"«{k}» — {v}" for k, v in top) + " (следствие опозданий и брака)"})
    st = next((r for r in S.staff if r["month"] == P.to.strftime("%Y-%m") and r["dept_id"] == "D-SUP" and not r["section_id"]), None)
    if st:
        out.append({"source": "1С:ЗУП", "text": f"Клиентский сервис: операторов {st['headcount_fact']} из {st['headcount_plan']} по штату"})
    return out


def fmt_contrib(k, c):
    if k["kind"] in ("sum", "count"):
        return ("+" if c > 0 else "−") + fmt_v(k, abs(c))
    return f"{'+' if c > 0 else '−'}{ru(abs(c), 2)} {'п.п.' if k['unit'] == '%' else k['unit']}"


def linked_factors(dim, key, P, F):
    """Связанные факторы из других источников (MES, 1С:ЗУП, маркетинг) по общим идентификаторам."""
    out = []
    a, b = P.start, P.to
    sec = next((s for s in S.section.values() if s["name"] == key), None) if dim == "section" else None
    prod = next((p for p in S.product.values() if p["name"] == key), None) if dim == "product" else None
    if dim == "reason":
        o = next((o for o in S.orders if o.get("defect_reason") == key), None)
        sec = S.section[o["section_id"]] if o else None
    if prod:
        sec = S.section[prod["section"]]
        for c in S.campaign.values():
            cs, ce = date.fromisoformat(c["start"]), date.fromisoformat(c["end"])
            if c["product_id"] == prod["id"] and cs <= b and ce >= a:
                n = sum(1 for o in S.orders if o.get("campaign_id") == c["id"] and a <= o["_cd"] <= b)
                out.append({"source": "Маркетинг (ERP)", "text": f"Кампания «{c['name']}» ({dmy(c['start'])} — {dmy(c['end'])}): {n} заказов в периоде, скидка до {int(c['discount'] * 100)} %"})
    if sec:
        rows = [r for r in S.mes if r["section_id"] == sec["id"] and a <= r["_d"] <= b]
        cap = sum(r["capacity_units"] for r in rows)
        load = sum(r["output_units"] for r in rows) / cap * 100 if cap else 0
        dt = sum(r["downtime_min"] for r in rows) / 60
        q = rows[-1]["queue_units_eod"] if rows else 0
        out.append({"source": "MES", "text": f"Участок «{sec['name']}»: загрузка {ru(load)} %, простои {ru(dt)} ч, очередь на конец периода {ru(q)} изд."})
        mo = b.strftime("%Y-%m")
        st = next((r for r in S.staff if r["month"] == mo and r["section_id"] == sec["id"]), None)
        if st:
            out.append({"source": "1С:ЗУП", "text": f"Участок «{sec['name']}»: операторов {st['headcount_fact']} из {st['headcount_plan']} по штату, вакансий {st['vacancies']}"})
        for c in S.campaign.values():
            p = S.product[c["product_id"]]
            cs, ce = date.fromisoformat(c["start"]), date.fromisoformat(c["end"])
            if p["section"] == sec["id"] and cs <= b and ce >= a and not prod:
                out.append({"source": "Маркетинг (ERP)", "text": f"Кампания «{c['name']}» повышает спрос на «{p['name']}» (участок «{sec['name']}»)"})
    return out


# ============================================================== прочие расчёты
def bucketize(P):
    out = []
    if P.days <= 31:
        d = P.start
        while d <= P.end:
            e = min(P.end, d + timedelta(days=6 - d.weekday()))
            out.append((d, e, f"{d.day:02d}.{d.month:02d}"))
            d = e + timedelta(days=1)
    else:
        for mo, _ in month_overlaps(P.start, P.end):
            y, m = int(mo[:4]), int(mo[5:])
            s, e = max(P.start, date(y, m, 1)), min(P.end, date(y, m, calendar.monthrange(y, m)[1]))
            out.append((s, e, MONTHS_SHORT[m - 1]))
    return out


def chart(P, F, metric):
    def series(a, b):
        if metric == "revenue":
            return sum(o["amount"] for o in orders_in(a, b, F))
        if metric == "orders":
            return len(orders_in(a, b, F))
        return sum(o["units"] for o in orders_in(a, b, F, "_prd"))

    def planv(a, b):
        p = F.get("product")
        return plan_sum({"revenue": "revenue", "orders": "orders", "output": "output_units"}[metric], a, b, p)

    t = S.today
    r14 = series(t - timedelta(days=13), t) / 14
    buckets = []
    for a, b, label in bucketize(P):
        complete = b < t
        f = series(a, min(b, t)) if a <= t else 0
        fc = None
        if not complete:
            fc = f + r14 * (b - max(a, t)).days
        buckets.append({"label": label, "start": a.isoformat(), "end": b.isoformat(), "plan": rnd(planv(a, b)), "fact": rnd(f), "forecast": rnd(fc), "complete": complete})
    units = {"revenue": "BYN", "orders": "заказов", "output": "изделий"}[metric]
    return {"metric": metric, "unit": units, "buckets": buckets}


def load_by_section(P, F):
    res = []
    for sid, s in S.section.items():
        def ld(a, b):
            rows = [r for r in S.mes if r["section_id"] == sid and a <= r["_d"] <= min(b, S.today)]
            cap = sum(r["capacity_units"] for r in rows)
            return (sum(r["output_units"] for r in rows) / cap * 100 if cap else None), rows
        cur, rows = ld(P.start, P.end)
        prev, _ = ld(*P.prev)
        res.append({"id": sid, "name": s["name"], "load": rnd(cur, 1), "prev": rnd(prev, 1), "status": status_of(KPI["load"], cur or 0, 85),
                    "output": rnd(sum(r["output_units"] for r in rows), 0), "capacity": rnd(sum(r["capacity_units"] for r in rows), 0),
                    "downtime_h": rnd(sum(r["downtime_min"] for r in rows) / 60, 1), "queue": rows[-1]["queue_units_eod"] if rows else 0})
    tot = items("load", P.start, P.end, {})
    totp = items("load", P.prev[0], P.prev[1], {})
    return {"total": rnd(value_of("load", tot), 1), "prev": rnd(value_of("load", totp), 1), "sections": res}


def clients_by_channel(P, F):
    act, new = {}, {}
    seen = set()
    for o in orders_in(P.start, P.end, F):
        if o["customer_id"] in seen:
            continue
        seen.add(o["customer_id"])
        ch = o["channel_id"] or "—"
        act[ch] = act.get(ch, 0) + 1
    for cid, o in S.first_order.items():
        if P.start <= o["_cd"] <= P.end and (not F.get("product") or o["product_id"] == F["product"]):
            ch = o["channel_id"] or "—"
            new[ch] = new.get(ch, 0) + 1
    return [{"id": c["id"], "name": c["name"], "active": act.get(c["id"], 0), "new": new.get(c["id"], 0)} for c in S.dict["channels"]]


def order_row(o):
    late = None
    if o["_x"]:
        late = None
    elif o["_shd"]:
        late = (o["_shd"] - o["_due"]).days
    elif S.today > o["_due"]:
        late = (S.today - o["_due"]).days
    return {"id": o["id"], "created_at": o["created_at"], "product": S.product[o["product_id"]]["name"], "section": S.section[o["section_id"]]["name"],
            "channel": S.channel[o["channel_id"]]["name"] if o["channel_id"] else None, "campaign": S.campaign[o["campaign_id"]]["name"] if o["campaign_id"] else None,
            "amount": o["amount"], "currency": "BYN", "status": o["status"], "promised_date": o["promised_date"], "shipped_at": o.get("shipped_at"),
            "late_days": late if late and late > 0 else 0, "defect_reason": o.get("defect_reason"), "customer_id": o["customer_id"]}


def forecast(user):
    """Прогноз спроса и доступной мощности на 6 недель (метод описан в formula)."""
    t = S.today
    hist_a = t - timedelta(days=55)
    camps = [dict(c, _s=date.fromisoformat(c["start"]), _e=date.fromisoformat(c["end"])) for c in S.dict["campaigns"]]
    prod_src = {p["id"]: next(x for x in data_gen.PRODUCTS if x["id"] == p["id"]) for p in S.dict["products"]}

    def factor(pid, d):
        f = data_gen.SEASON[d.month] * data_gen.WEEKDAY[d.weekday()]
        if pid == "PRD-CAL":
            f *= data_gen.CAL_SEASON.get(d.month, .5)
        c = next((c for c in camps if c["product_id"] == pid and c["_s"] <= d <= c["_e"]), None)
        if c:
            f *= c["uplift"]
        if d.month == 12:
            f *= 1.18 if d.day <= 22 else 0.55  # предновогодний пик, затем спад
        return f

    base = {}
    for p in S.dict["products"]:
        units = sum(o["units"] for o in S.orders if not o["_x"] and o["product_id"] == p["id"] and hist_a <= o["_cd"] <= t)
        fsum = sum(factor(p["id"], hist_a + timedelta(days=i)) for i in range(56))
        base[p["id"]] = units / fsum if fsum else 0
    mo = t.strftime("%Y-%m")
    staff = {r["section_id"]: r for r in S.staff if r["month"] == mo and r["section_id"]}
    queue = {s: next((r["queue_units_eod"] for r in reversed(S.mes) if r["section_id"] == s), 0) for s in S.section}
    second_shift = date.fromisoformat(S.dict["story"]["second_shift"])
    week0 = t - timedelta(days=t.weekday()) + timedelta(days=7)
    weeks = []
    deficit_week = None
    for w in range(6):
        ws = week0 + timedelta(days=7 * w)
        we = ws + timedelta(days=6)
        secs = []
        for sid, s in S.section.items():
            demand = sum(base[p["id"]] * factor(p["id"], ws + timedelta(days=i)) for p in S.dict["products"] if p["section"] == sid for i in range(7))
            if w == 0:
                demand += queue[sid]
            st = staff.get(sid)
            ratio = st["headcount_fact"] / st["headcount_plan"] if st else 1
            cap_day = s["cap"] * ratio * 1.2  # допустимые переработки до 20 %
            if sid == "SEC-BIND" and t >= second_shift:
                cap_day *= 1.25  # временная вторая смена (решение РШ-002)
            capacity = cap_day * 6  # 6 рабочих дней в неделю
            secs.append({"id": sid, "name": s["name"], "demand": round(demand, 1), "capacity": round(capacity, 1), "balance": round(capacity - demand, 1),
                         "deficit": demand > capacity, "staff": f"{st['headcount_fact']}/{st['headcount_plan']}" if st else None})
        tot_d = sum(x["demand"] for x in secs)
        tot_c = sum(x["capacity"] for x in secs)
        label = f"{ws.day} {MONTHS_GEN[ws.month - 1]} — {we.day} {MONTHS_GEN[we.month - 1]}"
        wk = {"start": ws.isoformat(), "end": we.isoformat(), "label": label, "short": f"{ws.day:02d}.{ws.month:02d}", "demand": round(tot_d, 1), "capacity": round(tot_c, 1),
              "deficit_sections": [x["name"] for x in secs if x["deficit"]], "sections": secs}
        if deficit_week is None and wk["deficit_sections"]:
            deficit_week = {"start": ws.isoformat(), "label": label, "sections": [{"name": x["name"], "gap": round(x["demand"] - x["capacity"], 0)} for x in secs if x["deficit"]]}
        weeks.append(wk)
    return {"weeks": weeks, "deficit_week": deficit_week, "generated_at": iso(now()),
            "method": "Спрос: средний дневной спрос по каждому продукту за 8 недель, очищенный от сезонности, дня недели и акций, × коэффициенты прогнозной недели "
                      "(сезонность, предновогодний пик, запланированные кампании); в первую неделю добавлена текущая очередь (MES). "
                      "Мощность: норматив участка × (факт/штат операторов по 1С:ЗУП) × 1,2 (допустимые переработки) × 6 рабочих дней; "
                      "для «Переплёта» учтена временная вторая смена ×1,25.",
            "sources": src_info(["ERP", "MES", "ZUP"])}


# ============================================================== API
class ApiError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


def require(user, *roles):
    if user["role"] not in roles:
        raise ApiError(403, "Недостаточно прав для этого раздела.")


def api_pulse(user, q):
    require_screen(user, "pulse")
    return pulse_data(user, q)


def pulse_data(user, q):
    P = Period(q.get("period"))
    F = parse_filters(q, user)
    visible = [k for k in KPIS if not F["dept"] or k["dept"] == F["dept"]]
    kpis = [kpi_public(user, k["id"], P, F) for k in visible]
    crit_list = [k["name"] for k in kpi_public_all(user, P, F) if k.get("status") == "crit"]
    crit = len(crit_list)
    metric = q.get("chart") or {"D-PROD": "output", "D-SUP": "orders", "D-HR": "output"}.get(F["dept"], "revenue")
    if metric not in ("revenue", "orders", "output"):
        raise ApiError(400, "Неизвестная метрика графика.")
    cards = [kpi_public(user, kid, P, F) for kid in CARDS[F["dept"]]]
    locked = [k["name"] for k in kpis + cards if k.get("locked")]
    return {"period": P.json(), "filters": F, "kpis": kpis, "cards": cards, "critical": crit, "critical_names": crit_list, "chart": chart(P, F, metric),
            "load": load_by_section(P, F), "clients": clients_by_channel(P, F), "locked": sorted(set(locked)), "computed_at": iso(now())}


def kpi_public_all(user, P, F):
    # руководителю чужие показатели не перечисляются вовсе (даже как закрытые)
    return [kpi_public(user, k["id"], P, F) for k in KPIS if user["role"] != "head" or can_see(user, k)]


def api_kpi(user, kid, q):
    if kid not in KPI:
        raise ApiError(404, "Показатель не найден.")
    k = KPI[kid]
    if not can_see(user, k):
        audit(user, "Детализация закрытого показателя", f"KPI «{k['name']}» ({S.dept[k['dept']]['name']})", "отказано")
        raise ApiError(403, f"Показатель «{k['name']}» закрыт для вашей роли: он принадлежит подразделению «{S.dept[k['dept']]['name']}».")
    P = Period(q.get("period"))
    F = parse_filters(q, user)
    info = kpi_public(user, kid, P, F)
    k = KPI[kid]
    base, skipped = baseline(kid, P, F)
    if P.partial and k["kind"] in ("sum", "count"):
        n = P.elapsed
        base = Range(base.start, min(base.end, base.start + timedelta(days=n - 1)), f"{base.label}, первые {n} дн.")
    if kid == "cac":
        return {**info, "period": P.json(), "filters": F, "breakdowns": [], "explanation": cac_explain(P, F),
                "baseline": {"label": base.label, "start": base.start.isoformat(), "end": base.end.isoformat(), "last_normal": skipped}, "orders_kind": None}
    bds, cur, prev = breakdown(kid, P, F, base)
    return {**info, "period": P.json(), "filters": F, "breakdowns": bds, "explanation": explain(kid, P, F, bds, cur, prev, base, skipped),
            "baseline": {"label": base.label, "start": base.start.isoformat(), "end": base.end.isoformat(), "last_normal": skipped},
            "orders_kind": {"on_time": "late", "defect": "defect", "reprint_cost": "defect", "lead_time": "late", "revenue": "top", "avg_check": "top",
                            "gross_margin": "top", "sla": "tickets"}.get(kid)}


def cac_explain(P, F):
    mk_f, mk_p = marketing_fact(P.start, P.to), plan_sum("marketing", P.start, P.to)
    n_f = value_of("new_customers", items("new_customers", P.start, P.to, F)) or 0
    n_p = plan_sum("new_customers", P.start, P.to)
    text = (f"Расходы на маркетинг {ru(mk_f)} BYN (план {ru(mk_p)} BYN, {'+' if mk_f >= mk_p else '−'}{ru(abs(mk_f - mk_p) / mk_p * 100 if mk_p else 0)} %) "
            f"при {ru(n_f)} новых клиентах (план {ru(n_p)}). Стоимость привлечения = {ru(mk_f / n_f if n_f else 0, 2)} BYN.")
    factors = []
    for c in S.campaign.values():
        cs, ce = date.fromisoformat(c["start"]), date.fromisoformat(c["end"])
        if cs <= P.to and ce >= P.start:
            n = sum(1 for cid, o in S.first_order.items() if o.get("campaign_id") == c["id"] and P.start <= o["_cd"] <= P.to)
            factors.append({"source": "1С + CRM", "text": f"Кампания «{c['name']}»: бюджет {ru(c['budget'])} BYN, привлечено новых клиентов: {n}"})
    return {"text": text, "good": False, "factors": factors, "baseline": None}


def api_orders(user, q):
    P = Period(q.get("period"))
    F = parse_filters(q, user)
    kind = q.get("kind") or "all"
    filt = {k: q.get(k) for k in ("section", "product_name", "channel", "campaign", "reason") if q.get(k)}
    if kind == "late":
        rows = [o for o in orders_in(P.start, min(P.end, S.today - timedelta(days=1)), F, "_due") if not (o["_shd"] and o["_shd"] <= o["_due"])]
    elif kind == "defect":
        rows = [o for o in orders_in(P.start, P.end, F, "_prd") if o["defect"]]
    else:
        rows = orders_in(P.start, P.end, F)
    out = []
    for o in rows:
        dv = dim_vals(o)
        if any((dv.get("product") if k == "product_name" else (o.get("defect_reason") if k == "reason" else dv.get(k))) != v for k, v in filt.items()):
            continue
        out.append(order_row(o))
    sq = (q.get("q") or "").strip().upper()
    if sq:
        out = [r for r in out if sq in r["id"] or sq in r["customer_id"]]
    out.sort(key=lambda r: (-(r["late_days"] or 0), -r["amount"]) if kind == "late" else (r["created_at"]), reverse=kind not in ("late",))
    page, per = max(1, int(q.get("page") or 1)), 10
    return {"total": len(out), "page": page, "per_page": per, "items": out[(page - 1) * per: page * per], "amount": rnd(sum(r["amount"] for r in out))}


def api_order(user, oid):
    o = S.order.get(oid)
    if not o:
        raise ApiError(404, f"Заказ {oid} не найден в ERP.")
    c = S.customer.get(o["customer_id"])
    mes = next((r for r in S.mes if o["_prd"] and r["_d"] == o["_prd"] and r["section_id"] == o["section_id"]), None)
    in_1c = bool(o["_sh"] and o["_sh"] <= S.onec_cutoff)
    return {"order": {**order_row(o), "units": o["units"], "discount": o["discount"], "status_history": o["status_history"], "defect": o["defect"],
                      "cost": o["cost"] if user["role"] != "head" or user["dept"] == "D-PROD" else None},
            "customer": {"id": c["id"], "segment": c["segment"], "region": c["region"], "created_at": c["created_at"],
                         "orders": sum(1 for x in S.orders if x["customer_id"] == c["id"]), "source": "CRM"} if c else None,
            "tickets": [{k: t[k] for k in ("id", "topic", "channel", "created_at", "first_response_min", "sla_min", "sla_met", "result")} for t in S.tickets_by_order.get(oid, [])],
            "production": {"section": S.section[o["section_id"]]["name"], "date": mes["date"], "load_day": rnd(mes["output_units"] / mes["capacity_units"] * 100 if mes["capacity_units"] else 0, 0),
                           "queue_units_eod": mes["queue_units_eod"], "source": "MES"} if mes else None,
            "finance": {"posted_1c": in_1c, "note": "Выручка признана в 1С" if in_1c else "Ещё не выгружено в 1С (последняя успешная выгрузка " + iso(S.onec_cutoff) + ")", "source": "1С:Бухгалтерия"}}


def api_tickets(user, q):
    require_screen(user, "tickets")
    P = Period(q.get("period"))
    F = parse_filters(q, user)
    rows = [t for t in S.tickets if P.start <= t["_cd"] <= P.end]
    if F["product"]:
        rows = [t for t in rows if S.order.get(t["order_id"], {}).get("product_id") == F["product"]]
    if q.get("breached") == "1":
        rows = [t for t in rows if not t["sla_met"]]
    for k in ("topic", "channel"):
        if q.get(k):
            rows = [t for t in rows if t[k] == q[k]]
    rows.sort(key=lambda t: t["created_at"], reverse=True)
    page, per = max(1, int(q.get("page") or 1)), 10
    return {"total": len(rows), "page": page, "per_page": per,
            "items": [{k: t[k] for k in ("id", "order_id", "topic", "channel", "created_at", "first_response_min", "sla_min", "sla_met", "result", "assignee")} for t in rows[(page - 1) * per: page * per]]}



def api_sales(user, q):
    require_screen(user, "sales")
    P = Period(q.get("period"))
    F = parse_filters(q, user)
    web = [r for r in S.web if P.start <= r["_d"] <= P.to]
    funnel = [{"step": s, "value": sum(r[k] for r in web)} for s, k in (("Визиты", "visits"), ("Начатые проекты", "projects_started"), ("Корзина", "carts"), ("Заказы", "orders"), ("Оплачено", "paid"))]
    ords = orders_in(P.start, P.end, F)
    prev = orders_in(P.prev[0], P.prev[1], F)

    def group(rows, key):
        g = {}
        for o in rows:
            x = g.setdefault(key(o), [0, 0.0, set()])
            x[0] += 1
            x[1] += o["amount"]
            x[2].add(o["customer_id"])
        return g

    tot = sum(o["amount"] for o in ords) or 1
    gc, gp = group(ords, lambda o: o["channel_id"] or "—"), group(prev, lambda o: o["channel_id"] or "—")
    channels = []
    for c in S.dict["channels"] + [{"id": "—", "name": "Не указан (пропуск)"}]:
        x = gc.get(c["id"])
        if not x:
            continue
        p = gp.get(c["id"], [0, 0, set()])
        channels.append({"id": c["id"], "name": c["name"], "orders": x[0], "revenue": rnd(x[1]), "avg_check": rnd(x[1] / x[0]), "share": rnd(x[1] / tot * 100, 1),
                         "customers": len(x[2]), "delta": rnd((x[1] - p[1]) / p[1] * 100 if p[1] else None, 1)})
    gs = group(ords, lambda o: o["segment"])
    segments = [{"name": k, "orders": v[0], "revenue": rnd(v[1]), "avg_check": rnd(v[1] / v[0]), "share": rnd(v[1] / tot * 100, 1), "customers": len(v[2])} for k, v in sorted(gs.items(), key=lambda kv: -kv[1][1])]
    camps = []
    for c in S.dict["campaigns"]:
        rows = [o for o in ords if o["campaign_id"] == c["id"]]
        cs, ce = date.fromisoformat(c["start"]), date.fromisoformat(c["end"])
        if not rows and not (cs <= P.end and ce >= P.start):
            continue
        rev = sum(o["amount"] for o in rows)
        disc = sum(o["discount"] for o in rows)
        margin = sum(o["amount"] - o["cost"] - o.get("reprint_cost", 0) for o in rows)
        budget = c["budget"] * data_gen.overlap_share({"start": cs, "end": ce}, P.start) if P.days <= 31 else c["budget"]
        camps.append({"id": c["id"], "name": c["name"], "product": S.product[c["product_id"]]["name"], "source": c["source"], "start": c["start"], "end": c["end"],
                      "orders": len(rows), "revenue": rnd(rev), "discount": rnd(disc), "budget": rnd(budget),
                      "romi": rnd((margin - budget) / budget * 100, 0) if (budget and can_see(user, KPI["gross_margin"])) else None})
    # отток: активные в прошлом периоде, не купившие в текущем
    prev_c = {o["customer_id"] for o in prev}
    cur_c = {o["customer_id"] for o in ords}
    churn = len(prev_c - cur_c) / len(prev_c) * 100 if prev_c else None
    kp = lambda kid: kpi_public(user, kid, P, F)  # noqa: E731
    return {"period": P.json(), "kpis": [kp("conversion"), kp("avg_check"), kp("repeat"), kp("new_customers")], "churn": rnd(churn, 1),
            "funnel": funnel, "channels": channels, "segments": segments, "campaigns": camps,
            "funnel_source": src_info(["WEB", "ERP"])}


def api_production(user, q):
    require_screen(user, "production")
    P = Period(q.get("period"))
    F = parse_filters(q, user)
    kp = lambda kid: kpi_public(user, kid, P, F)  # noqa: E731
    secs = []
    for sid, s in S.section.items():
        rows = [r for r in S.mes if r["section_id"] == sid and P.start <= r["_d"] <= P.to]
        ords = [o for o in orders_in(P.start, P.end, F, "_prd") if o["section_id"] == sid]
        shipped = [o for o in orders_in(P.start, P.end, F, "_shd") if o["section_id"] == sid]
        plan_out = plan_sum("output_units", P.start, P.to, F.get("product"), sid)
        cap = sum(r["capacity_units"] for r in rows)
        reasons = {}
        for r in rows:
            if r["downtime_reason"]:
                reasons[r["downtime_reason"]] = reasons.get(r["downtime_reason"], 0) + r["downtime_min"]
        st = next((r for r in S.staff if r["month"] == P.to.strftime("%Y-%m") and r["section_id"] == sid), None)
        secs.append({"id": sid, "name": s["name"], "plan_output": rnd(plan_out, 0), "output": rnd(sum(o["units"] for o in ords), 0),
                     "capacity": rnd(cap, 0), "load": rnd(sum(r["output_units"] for r in rows) / cap * 100 if cap else None, 1),
                     "downtime_h": rnd(sum(r["downtime_min"] for r in rows) / 60, 1), "downtime_reasons": [{"reason": k, "hours": rnd(v / 60, 1)} for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])],
                     "queue": rows[-1]["queue_units_eod"] if rows else 0, "defect": rnd(sum(o["defect"] for o in ords) / len(ords) * 100 if ords else None, 2),
                     "reprints": sum(1 for o in ords if o["defect"]), "lead_time": rnd(sum((o["_sh"] - o["_c"]).total_seconds() for o in shipped) / 86400 / len(shipped) if shipped else None, 2),
                     "staff": {"fact": st["headcount_fact"], "plan": st["headcount_plan"], "shifts_fact": st.get("shifts_fact"), "shifts_plan": st.get("shifts_plan")} if st else None})
    reasons = {}
    for o in orders_in(P.start, P.end, F, "_prd"):
        if o["defect"]:
            reasons[o["defect_reason"]] = reasons.get(o["defect_reason"], 0) + 1
    queue_orders = sum(1 for o in S.orders if o["status"] in ("Модерация", "Производство") and (not F["product"] or o["product_id"] == F["product"]))
    return {"period": P.json(), "kpis": [kp("on_time"), kp("defect"), kp("load"), kp("lead_time"), kp("reprint_cost")], "chart": chart(P, F, "output"),
            "sections": secs, "defect_reasons": [{"reason": k, "count": v} for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])], "queue_orders": queue_orders,
            "sources": src_info(["MES", "ERP", "ZUP"])}


def api_finance(user, q):
    require_screen(user, "finance")
    P = Period(q.get("period"))
    F = parse_filters(q, user)
    fin_ok = can_see(user, KPI["gross_margin"])
    hr_ok = can_see(user, KPI["payroll"])
    months = [mo for mo, _ in month_overlaps(P.start, P.end)]
    res = {"period": P.json(), "months": months, "sources": src_info(["1C", "ZUP"]), "access": {"finance": fin_ok, "payroll": hr_ok}}
    if fin_ok:
        def agg(kind):
            g = {}
            for r in S.finance:
                if r["kind"] == kind and r["month"] in months and (not F["product"] or r["product_id"] in (None, F["product"]) or r["article"] not in ("Выручка", "Себестоимость продукции")):
                    if F["product"] and r["product_id"] and r["product_id"] != F["product"]:
                        continue
                    x = g.setdefault(r["article"], [0.0, 0.0, r["dept_id"]])
                    x[0] += r["plan"]
                    x[1] += r["fact"]
            return [{"article": k, "dept": S.dept[v[2]]["name"], "plan": rnd(v[0]), "fact": rnd(v[1]), "dev": rnd(v[1] - v[0]), "dev_pct": rnd((v[1] - v[0]) / abs(v[0]) * 100 if v[0] else None, 1)} for k, v in g.items()]
        bdr = agg("БДР")
        rev = next((r for r in bdr if r["article"] == "Выручка"), {"plan": 0, "fact": 0})
        exp_p = sum(r["plan"] for r in bdr if r["article"] != "Выручка")
        exp_f = sum(r["fact"] for r in bdr if r["article"] != "Выручка")
        res["bdr"] = bdr
        res["bdr_result"] = {"plan": rnd(rev["plan"] - exp_p), "fact": rnd(rev["fact"] - exp_f)}
        bdds = agg("БДДС")
        res["bdds"] = bdds
        res["bdds_result"] = {"plan": rnd(sum(r["plan"] for r in bdds)), "fact": rnd(sum(r["fact"] for r in bdds))}
        mp = []
        for p in S.dict["products"]:
            if F["product"] and p["id"] != F["product"]:
                continue
            ords = [o for o in orders_in(P.start, P.end, {"product": p["id"]})]
            r = sum(o["amount"] for o in ords)
            c = sum(o["cost"] + o.get("reprint_cost", 0) for o in ords)
            mp.append({"product": p["name"], "revenue": rnd(r), "cost": rnd(c), "margin": rnd((r - c) / r * 100 if r else None, 1)})
        res["margin_by_product"] = mp
        res["onec_note"] = f"Последняя успешная выгрузка из 1С: {iso(S.onec_cutoff)}. Факт текущего месяца в 1С неполный."
    else:
        audit(user, "Просмотр БДР/БДДС и маржи", "Финансы", "отказано", "Закрытые показатели подразделения «Финансы»")
    people = []
    mo = P.to.strftime("%Y-%m")
    for r in S.staff:
        if r["month"] == mo and not r["section_id"]:
            row = {"dept": S.dept[r["dept_id"]]["name"], "plan": r["headcount_plan"], "fact": r["headcount_fact"], "vacancies": r["vacancies"],
                   "staffing": rnd(r["headcount_fact"] / r["headcount_plan"] * 100, 1), "vacation_days": r["absence_vacation_days"], "sick_days": r["absence_sick_days"]}
            if hr_ok:
                row.update(payroll_plan=r["payroll_plan"], payroll_fact=r["payroll_fact"])
            people.append(row)
    res["people"] = people
    res["people_month"] = mo
    kp = lambda kid: kpi_public(user, kid, P, F)  # noqa: E731
    res["kpis"] = [kp("revenue"), kp("gross_margin"), kp("staffing"), kp("payroll")]
    return res


def api_quality(user, q):
    if user["role"] not in ("analyst", "director"):
        audit(user, "Просмотр качества данных", "Качество данных", "отказано")
        raise ApiError(403, "Раздел «Качество данных» доступен аналитику и директору.")
    n = now()
    sources = []
    counts = {"CRM": len(S.customers), "HELPDESK": len(S.tickets), "ERP": len(S.orders), "MES": len(S.mes), "WEB": len(S.web), "ZUP": len(S.staff), "1C": len(S.finance)}
    for s in S.sources:
        ls = last_sync(s)
        age = (n - ls).total_seconds() / 60
        st = "ok" if age <= max(60, s["interval_min"] * 2) else ("warn" if age <= 24 * 60 else "crit")
        sources.append({"id": s["id"], "name": s["name"], "entity": s["entity"], "records": counts[s["id"]], "last_sync": iso(ls), "age_min": round(age),
                        "interval_min": s["interval_min"], "status": st, "error": s.get("last_error"), "owner": S.dept[s["owner"]]["name"]})
    no_channel = [o["id"] for o in S.orders if not o["channel_id"]]
    by_phone = {}
    for c in S.customers:
        by_phone.setdefault(c["phone_hash"], []).append(c["id"])
    dup_c = [v for v in by_phone.values() if len(v) > 1]
    seen, dup_t = {}, []
    for t in sorted(S.tickets, key=lambda t: t["created_at"]):
        k = (t["order_id"], t["topic"])
        if k in seen and (t["_c"] - seen[k]["_c"]).total_seconds() <= 300:
            dup_t.append([seen[k]["id"], t["id"]])
        seen[k] = t
    orphan_orders = sum(1 for o in S.orders if o["customer_id"] not in S.customer)
    orphan_t = sum(1 for t in S.tickets if t["order_id"] not in S.order)
    reco = []
    for mo in sorted({r["month"] for r in S.finance}):
        erp = sum(o["amount"] for o in S.orders if o.get("shipped_at") and o["shipped_at"][:7] == mo)
        one_c = sum(r["fact"] for r in S.finance if r["month"] == mo and r["article"] == "Выручка")
        diff = one_c - erp
        pct = diff / erp * 100 if erp else 0
        current = mo == S.today.strftime("%Y-%m")
        st = "ok" if abs(pct) < 0.1 else ("warn" if current else "crit")
        note = "1С не обновлялась: факт месяца неполный" if current and st != "ok" else ("Совпадает" if st == "ok" else "Расхождение: в 1С не проведены операции ERP")
        by_prod = []
        if st != "ok":
            for p in S.dict["products"]:
                e = sum(o["amount"] for o in S.orders if o.get("shipped_at") and o["shipped_at"][:7] == mo and o["product_id"] == p["id"])
                c1 = sum(r["fact"] for r in S.finance if r["month"] == mo and r["article"] == "Выручка" and r["product_id"] == p["id"])
                if abs(c1 - e) > 0.5:
                    by_prod.append({"product": p["name"], "erp": rnd(e), "one_c": rnd(c1), "diff": rnd(c1 - e)})
        reco.append({"month": mo, "erp": rnd(erp), "one_c": rnd(one_c), "diff": rnd(diff), "diff_pct": rnd(pct, 2), "status": st, "note": note, "by_product": by_prod})
    audit(user, "Просмотр качества данных", "Качество данных")
    return {"checked_at": iso(n), "sources": sources,
            "gaps": [{"check": "Заказы ERP без канала продаж", "count": len(no_channel), "sample": no_channel[:8], "source": "ERP", "status": "warn" if no_channel else "ok",
                      "hint": "Сбой передачи UTM/канала из picPac.by; влияет на разрез «Канал»"},
                     {"check": "Заказы без клиента в CRM", "count": orphan_orders, "sample": [], "source": "ERP ↔ CRM", "status": "ok" if not orphan_orders else "crit", "hint": "Связь по customer_id"},
                     {"check": "Обращения без заказа в ERP", "count": orphan_t, "sample": [], "source": "Helpdesk ↔ ERP", "status": "ok" if not orphan_t else "crit", "hint": "Связь по order_id"}],
            "duplicates": [{"check": "Дубли клиентов (совпадает хэш телефона)", "count": len(dup_c), "sample": dup_c[:8], "source": "CRM", "status": "warn" if dup_c else "ok"},
                           {"check": "Дубли обращений (тот же заказ и тема в пределах 5 минут)", "count": len(dup_t), "sample": dup_t[:8], "source": "Helpdesk", "status": "warn" if dup_t else "ok"}],
            "reconciliation": reco,
            "linkage": {"orders_with_customer": rnd((len(S.orders) - orphan_orders) / len(S.orders) * 100, 1), "tickets_with_order": rnd((len(S.tickets) - orphan_t) / len(S.tickets) * 100, 1),
                        "keys": ["customer_id: CRM ↔ ERP ↔ Helpdesk", "order_id: ERP ↔ Helpdesk", "product_id / section_id: ERP ↔ MES ↔ 1С", "dept_id: 1С:ЗУП ↔ 1С:Бухгалтерия", "channel_id: ERP ↔ веб-аналитика"]}}


def dec_public(d):
    owner = next((o for o in OWNERS if o["id"] == d["owner"]), {"name": d["owner"], "title": ""})
    overdue = d["status"] not in ("Выполнено", "Отменено") and date.fromisoformat(d["due"]) < S.today
    return {**d, "code": f"РШ-{d['id']:03d}", "owner_name": owner["name"], "owner_title": owner["title"], "dept_name": S.dept[d["dept"]]["name"],
            "kpi_name": KPI[d["kpi_id"]]["name"] if d.get("kpi_id") in KPI else None, "overdue": overdue}


def can_edit_decision(user, dept):
    return user["role"] == "director"


def visible_decision(user, d):
    return user["role"] in ("director", "analyst") or d["dept"] == user["dept"]


def api_decisions(user, q):
    require_screen(user, "decisions")
    items_ = [dec_public(d) for d in load_decisions() if visible_decision(user, d)]
    for k in ("status", "priority", "dept"):
        if q.get(k) and q[k] != "all":
            items_ = [d for d in items_ if d[k] == q[k]]
    if q.get("overdue") == "1":
        items_ = [d for d in items_ if d["overdue"]]
    s = (q.get("q") or "").strip().lower()
    if s:
        items_ = [d for d in items_ if s in (d["title"] + d["action"] + d["code"] + d["owner_name"]).lower()]
    items_.sort(key=lambda d: (d["status"] in ("Выполнено", "Отменено"), PRIORITIES.index(d["priority"]), d["due"]))
    return {"items": items_, "can_create": user["role"] == "director"}


FIELDS = {"title": "Проблема", "impact": "Влияние", "cause": "Причина", "action": "Действие", "owner": "Ответственный", "due": "Срок",
          "priority": "Приоритет", "status": "Статус", "dept": "Подразделение", "kpi_id": "Показатель"}


def validate_decision(body, partial=False):
    errs = {}
    out = {}
    for f in FIELDS:
        if f not in body:
            if not partial and f in ("title", "action", "owner", "due", "priority", "dept"):
                errs[f] = "Обязательное поле."
            continue
        v = body[f]
        v = v.strip() if isinstance(v, str) else v
        out[f] = v
        if f in ("title", "action") and (not v or len(v) < 5):
            errs[f] = "Минимум 5 символов."
        if f in ("title", "impact", "cause", "action") and v and len(v) > 600:
            errs[f] = "Не более 600 символов."
        if f == "owner" and v not in {o["id"] for o in OWNERS}:
            errs[f] = "Выберите ответственного из списка."
        if f == "priority" and v not in PRIORITIES:
            errs[f] = "Недопустимый приоритет."
        if f == "status" and v not in DECISION_STATUSES:
            errs[f] = "Недопустимый статус."
        if f == "dept" and v not in S.dept:
            errs[f] = "Недопустимое подразделение."
        if f == "kpi_id" and v and v not in KPI:
            errs[f] = "Неизвестный показатель."
        if f == "due":
            try:
                dv = date.fromisoformat(v)
                if not partial and dv < S.today:
                    errs[f] = "Срок не может быть в прошлом."
            except (TypeError, ValueError):
                errs[f] = "Дата в формате ГГГГ-ММ-ДД."
    if errs:
        raise ApiError(422, {"message": "Проверьте поля карточки решения.", "fields": errs})
    return out


def api_decision_create(user, body):
    if user["role"] != "director":
        audit(user, "Создание решения", "Реестр решений", "отказано")
        raise ApiError(403, "Создавать решения может только директор: аналитик видит реестр только для чтения, руководителю подразделения реестр недоступен.")
    data = validate_decision(body)
    if not can_edit_decision(user, data["dept"]):
        audit(user, "Создание решения", f"Подразделение {data['dept']}", "отказано")
        raise ApiError(403, "Руководитель подразделения может создавать решения только для своего подразделения.")
    with LOCK:
        items_ = load_decisions()
        nid = max([d["id"] for d in items_] or [0]) + 1
        ts = iso(now())
        d = {"id": nid, "kpi_id": data.get("kpi_id"), "dept": data["dept"], "title": data["title"], "impact": data.get("impact", ""), "cause": data.get("cause", ""),
             "action": data["action"], "owner": data["owner"], "due": data["due"], "priority": data["priority"], "status": data.get("status") or "Новое",
             "created_at": ts, "created_by": user["login"], "updated_at": ts, "rev": 1, "context": body.get("context"),
             "history": [{"at": ts, "user": user["login"], "user_name": user["name"], "action": "Создано", "changes": []}]}
        items_.append(d)
        save_decisions(items_)
    audit(user, "Создание решения", f"РШ-{nid:03d} «{d['title']}»", details={"kpi": d["kpi_id"], "priority": d["priority"], "owner": d["owner"], "due": d["due"]})
    return dec_public(d)


def api_decision_update(user, did, body):
    with LOCK:
        items_ = load_decisions()
        d = next((x for x in items_ if str(x["id"]) == str(did)), None)
        if user["role"] == "head":
            audit(user, "Изменение решения", f"РШ-{int(did):03d}", "отказано")
            raise ApiError(403, "Реестр решений недоступен руководителю подразделения.")
        if not d or not visible_decision(user, d):
            raise ApiError(404, "Решение не найдено.")
        if not can_edit_decision(user, d["dept"]):
            audit(user, "Изменение решения", f"РШ-{d['id']:03d}", "отказано")
            raise ApiError(403, "Недостаточно прав для изменения этого решения.")
        data = validate_decision(body, partial=True)
        if "dept" in data and not can_edit_decision(user, data["dept"]):
            raise ApiError(403, "Нельзя передать решение в чужое подразделение.")
        if body.get("version") is not None and body["version"] != d.get("rev", 1):
            raise ApiError(409, "Карточку уже изменил другой пользователь. Закройте её, откройте заново и повторите изменение.")
        changes = [{"field": f, "label": FIELDS[f], "from": d.get(f), "to": v} for f, v in data.items() if d.get(f) != v]
        if not changes:
            return dec_public(d)
        for c in changes:
            d[c["field"]] = c["to"]
        ts = iso(now())
        d["updated_at"] = ts
        d["rev"] = d.get("rev", 1) + 1
        d["history"].append({"at": ts, "user": user["login"], "user_name": user["name"], "action": "Изменено", "changes": changes})
        save_decisions(items_)
    audit(user, "Изменение решения", f"РШ-{d['id']:03d} «{d['title']}»", details={c["field"]: f"{c['from']} → {c['to']}" for c in changes})
    return dec_public(d)


def api_audit(user, q):
    if user["role"] not in ("analyst", "director"):
        audit(user, "Просмотр журнала", "Журнал действий", "отказано")
        raise ApiError(403, "Журнал действий доступен аналитику/администратору и директору.")
    rows = list(reversed(read_audit()))
    for k in ("user", "result"):
        if q.get(k) and q[k] != "all":
            rows = [r for r in rows if r[k] == q[k]]
    s = (q.get("q") or "").strip().lower()
    if s:
        rows = [r for r in rows if s in (r["action"] + r["object"] + r.get("user_name", "")).lower()]
    page, per = max(1, int(q.get("page") or 1)), min(1000, max(1, int(q.get("per") or 15)))
    return {"total": len(rows), "page": page, "per_page": per, "items": rows[(page - 1) * per: page * per]}


def api_alerts(user):
    P = Period(None)
    out = []
    screens = screens_for(user)
    home = "pulse" if "pulse" in screens else (screens[0] if screens else "help")
    for k in KPIS:
        if can_see(user, k):
            v = kpi_values(k["id"], P, {"product": None})
            if v["status"] == "crit":
                out.append({"id": f"kpi-{k['id']}-{P.key}", "kind": "kpi", "icon": "alert", "text": f"{k['name']}: {fmt_v(k, v['fact'])} при плане {fmt_v(k, v['plan'])}", "href": f"#/{home}?kpi={k['id']}"})
    for d in load_decisions():
        dp = dec_public(d)
        if dp["overdue"] and "decisions" in screens and visible_decision(user, d):
            out.append({"id": f"dec-{d['id']}-overdue", "kind": "decision", "icon": "report", "text": f"{dp['code']} просрочено: «{d['title']}»", "href": f"#/decisions?id={d['id']}"})
    fc = forecast(user) if "forecast" in screens else {"deficit_week": None}
    if fc["deficit_week"]:
        out.append({"id": f"fc-{fc['deficit_week']['start']}", "kind": "forecast", "icon": "truck", "text": f"Дефицит мощности: неделя {fc['deficit_week']['label']} ({', '.join(s['name'] for s in fc['deficit_week']['sections'])})", "href": "#/forecast"})
    for kid, n in load_kpi_notes().items():
        if n.get("owner") != user["login"] or kid not in KPI or not can_see(user, KPI[kid]) or user["role"] == "director":
            continue
        for c in n.get("feed", []):
            if c["kind"] == "assign" and c.get("owner") == user["login"]:
                out.append({"id": f"kpi-own-{kid}-{c['id']}", "kind": "kpi", "icon": "visitor", "text": f"Вы назначены ответственным: «{KPI[kid]['name']}»", "href": f"#/{home}?kpi={kid}"})
            elif c["kind"] == "comment":
                out.append({"id": f"kpi-cmt-{kid}-{c['id']}", "kind": "kpi", "icon": "report", "text": f"Комментарий к «{KPI[kid]['name']}»: {c['text'][:80]}", "href": f"#/{home}?kpi={kid}"})
    if user["role"] in ("analyst", "director"):
        for s in S.sources:
            if s.get("failing_since"):
                out.append({"id": f"src-{s['id']}-{s['failing_since']}", "kind": "source", "icon": "alert", "text": f"{s['name']}: нет выгрузки с {datetime.fromisoformat(s['failing_since']).strftime('%d.%m %H:%M')}", "href": "#/quality"})
    read = set(load_read().get(user["login"], []))
    for a in out:
        a["unread"] = a["id"] not in read
    return {"items": out}


def load_read():
    p = state_path("alerts_read.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def mark_read(user, ids):
    with LOCK:
        r = load_read()
        r[user["login"]] = sorted(set(r.get(user["login"], [])) | set(ids))
        with open(state_path("alerts_read.json"), "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False)


def api_meta(user):
    kpis = []
    for k in KPIS:
        if user["role"] == "head" and not can_see(user, k):
            continue  # руководителю чужие показатели не показываются даже в справочнике
        pub = {"id": k["id"], "name": k["name"], "dept": k["dept"], "dept_name": S.dept[k["dept"]]["name"], "unit": k["unit"], "closed": k["closed"],
               "sources": src_info(k["src"]), "product_scope": k["product"], "target": k.get("target")}
        if can_see(user, k):
            pub["formula"] = k["formula"]
        else:
            pub["locked"] = True
        kpis.append(pub)
    return {"user": pub_user(user), "server_time": iso(now()), "timezone": "Europe/Minsk (UTC+03:00)", "currency": "BYN",
            "refresh_sec": DATA_REFRESH_SEC, "data_loaded_at": iso(S.loaded_at),
            "data": {"generated_at": S.meta["generated_at"], "start": S.meta["start"], "counts": S.meta["counts"], "seed": S.meta["seed"]},
            "periods": period_options(), "default_period": S.today.strftime("%Y-%m"),
            "departments": S.dict["departments"], "products": [{"id": p["id"], "name": p["name"]} for p in S.dict["products"]],
            "sections": [{"id": s["id"], "name": s["name"]} for s in S.dict["sections"]], "channels": S.dict["channels"],
            "campaigns": [{"id": c["id"], "name": c["name"]} for c in S.dict["campaigns"]],
            "owners": OWNERS, "statuses": DECISION_STATUSES, "priorities": PRIORITIES, "kpis": kpis,
            "permissions": {"quality": user["role"] in ("analyst", "director"), "audit": user["role"] in ("analyst", "director"),
                            "decide": user["role"] == "director", "finance": can_see(user, KPI["gross_margin"]),
                            "screens": screens_for(user)}}


# ============================================================== ИИ-ассистент «Фотик»
# Ключ Claude API берётся только из окружения сервера и никогда не попадает в ответы API, журнал или фронтенд.
FOTIK_API_URL = os.environ.get("FOTIK_API_URL", "https://api.anthropic.com/v1/messages")
FOTIK_MODEL = os.environ.get("FOTIK_MODEL", "claude-sonnet-5-5")
FOTIK_TIMEOUT = 60
FOTIK_RATE = {}  # login -> [метки времени запросов за последнюю минуту]
FOTIK_SYSTEM = (
    "Ты Фотик, аналитик этого дашборда. Отвечай по-русски, коротко и по делу. "
    "Опирайся только на переданные данные, ничего не выдумывай. "
    "Объясняй тренды, находи аномалии, сравнивай периоды, делай выводы. "
    "Прогноз давай с допущениями и диапазоном, а не одной цифрой. "
    "Если данных не хватает, так и скажи.\n\n"
    "Как читать данные ниже:\n"
    "• Это снимок дашборда ООО «Фотопринт», рассчитанный сервером прямо перед вопросом, с учётом выбранных фильтров и прав пользователя.\n"
    "• Показатели с \"locked\": true пользователю недоступны — их значения не называй и не оценивай, скажи, что доступа нет.\n"
    "• Блок \"trend\" — расчётный прогноз (линейная регрессия по дням с поправкой на день недели и скользящие средние). "
    "Для прогнозов используй эти цифры и их диапазоны, не придумывай свои; перечисли допущения из \"assumptions\".\n"
    "• Блок \"week\" — сравнение последних 7 полных дней с 7 днями до них; \"anomalies\" — дни и показатели, выбивающиеся из нормы.\n"
    "• Деньги — BYN, даты — Europe/Minsk. Формат ответа: 2–6 коротких пунктов или абзац, числа с единицами, без таблиц, если о них не просят."
)


def _daily(metric, a, b, F):
    """Дневной ряд метрики за [a, b]: revenue (BYN), orders (шт.), output (изделий)."""
    p = F.get("product")
    vals = {a + timedelta(days=i): 0.0 for i in range((b - a).days + 1)}
    field = "_prd" if metric == "output" else "_cd"
    for o in S.orders:
        d = o[field]
        if o["_x"] or not d or d < a or d > b or (p and o["product_id"] != p):
            continue
        vals[d] += o["amount"] if metric == "revenue" else (o["units"] if metric == "output" else 1)
    return [vals[d] for d in sorted(vals)]


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def _linreg(ys):
    """y = a + b·x по x = 0..n-1; возвращает (a, b, σ остатков, Sxx, x̄, R²)."""
    n = len(ys)
    xs = list(range(n))
    xm, ym = _mean(xs), _mean(ys)
    sxx = sum((x - xm) ** 2 for x in xs) or 1
    b = sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / sxx
    a = ym - b * xm
    res = [y - (a + b * x) for x, y in zip(xs, ys)]
    sig = (sum(r * r for r in res) / max(1, n - 2)) ** 0.5
    sst = sum((y - ym) ** 2 for y in ys) or 1
    return a, b, sig, sxx, xm, 1 - sum(r * r for r in res) / sst


def fotik_trend(metric, F, horizon_end=None, hist_days=56, z=1.28):
    """Тренд и прогноз метрики: регрессия по дням (ряд очищен от дня недели) + скользящие средние.
    Возвращает сумму на 30 дней вперёд и до конца текущего месяца с 80-% диапазоном."""
    t = S.today
    end = t - timedelta(days=1)  # сегодняшний день неполный — в обучение не берём
    start = max(S.data_start, end - timedelta(days=hist_days - 1))
    ys = _daily(metric, start, end, F)
    days = [start + timedelta(days=i) for i in range(len(ys))]
    overall = _mean(ys) or 1
    wd = {w: (_mean([y for y, d in zip(ys, days) if d.weekday() == w]) or overall) / overall for w in range(7)}
    des = [y / wd[d.weekday()] for y, d in zip(ys, days)]
    a, b, sig, sxx, xm, r2 = _linreg(des)
    n = len(des)

    def project(d_from, d_to):
        if d_to < d_from:
            return 0.0, 0.0
        pts = [(n + (d_from - end).days - 1 + i, wd[(d_from + timedelta(days=i)).weekday()]) for i in range((d_to - d_from).days + 1)]
        point = sum(max(0.0, a + b * x) * w for x, w in pts)
        sw, swx, sw2 = sum(w for _, w in pts), sum(w * (x - xm) for x, w in pts), sum(w * w for _, w in pts)
        se = sig * (sw * sw / n + swx * swx / sxx + sw2) ** 0.5
        return point, se

    nxt_a, nxt_b = t, t + timedelta(days=29)
    p30, se30 = project(nxt_a, nxt_b)
    ma7, ma28 = _mean(ys[-7:]), _mean(ys[-28:])
    mend = date(t.year, t.month, calendar.monthrange(t.year, t.month)[1])
    mstart = t.replace(day=1)
    so_far = sum(_daily(metric, mstart, end, F)) if end >= mstart else 0.0
    rest, se_rest = project(t, mend)
    plan_key = {"revenue": "revenue", "orders": "orders", "output": "output_units"}[metric]
    month_plan = plan_sum(plan_key, mstart, mend, F.get("product"))
    unit = {"revenue": "BYN", "orders": "заказов", "output": "изделий"}[metric]
    r = lambda v: round(v, 1)
    return {
        "metric": metric, "unit": unit, "history": f"{start.isoformat()} — {end.isoformat()} ({n} дн.)",
        "avg_per_day": {"last7": r(ma7), "last28": r(ma28), f"all_{n}d": r(overall)},
        "slope_per_day": r(b), "slope_pct_per_week": r(b * 7 / overall * 100) if overall else None, "r2": round(r2, 2),
        "weekday_factor": {["пн", "вт", "ср", "чт", "пт", "сб", "вс"][w]: round(v, 2) for w, v in wd.items()},
        "next_30_days": {"from": nxt_a.isoformat(), "to": nxt_b.isoformat(), "regression": r(p30),
                         "range_80": [r(max(0, p30 - z * se30)), r(p30 + z * se30)], "moving_avg_28x30": r(ma28 * 30)},
        "current_month": {"month": t.strftime("%Y-%m"), "fact_to_yesterday": r(so_far), "forecast_rest": r(rest),
                          "forecast_total": r(so_far + rest), "range_80": [r(max(0, so_far + rest - z * se_rest)), r(so_far + rest + z * se_rest)],
                          "plan": r(month_plan) if month_plan else None},
    }


def _weekly(metric, F, weeks=8):
    end = S.today - timedelta(days=1)
    out = []
    for w in range(weeks - 1, -1, -1):
        b = end - timedelta(days=7 * w)
        a = b - timedelta(days=6)
        if a < S.data_start:
            continue
        out.append({"week": f"{a.strftime('%d.%m')}–{b.strftime('%d.%m')}", "value": round(sum(_daily(metric, a, b, F)), 1)})
    return out


def _anomalies(F, days=42):
    """Дни, где значение отличается от ожидаемого (тренд × день недели) более чем на 2,5 σ."""
    end = S.today - timedelta(days=1)
    start = max(S.data_start, end - timedelta(days=days - 1))
    found = []
    for metric, unit in (("revenue", "BYN"), ("orders", "заказов"), ("output", "изделий")):
        ys = _daily(metric, start, end, F)
        dd = [start + timedelta(days=i) for i in range(len(ys))]
        ov = _mean(ys) or 1
        wd = {w: (_mean([y for y, d in zip(ys, dd) if d.weekday() == w]) or ov) / ov for w in range(7)}
        des = [y / wd[d.weekday()] for y, d in zip(ys, dd)]
        a, b, sig, *_ = _linreg(des)
        if not sig:
            continue
        for i, (y, d) in enumerate(zip(ys, dd)):
            exp = (a + b * i) * wd[d.weekday()]
            zz = (des[i] - (a + b * i)) / sig
            if abs(zz) >= 2.5:
                found.append({"date": d.isoformat(), "metric": metric, "value": round(y, 1), "expected": round(exp, 1), "unit": unit, "z": round(zz, 1)})
    return sorted(found, key=lambda x: -abs(x["z"]))[:8]


def fotik_context(user, q):
    """Снимок дашборда для модели: фильтры, KPI, ряды (агрегатами), сравнение недель, аномалии, расчётные тренды."""
    # руководитель получает только данные своего подразделения: свои KPI, свои ряды, мощность — только производству
    screens, mets = screens_for(user), metrics_for(user)
    head = user["role"] == "head"
    qq = dict(q)
    if head and qq.get("chart") not in mets:
        qq["chart"] = mets[-1] if user["dept"] == "D-PROD" else mets[0]
    pulse = pulse_data(user, qq)
    P = Period(q.get("period"))
    F = parse_filters(q, user)
    t = S.today
    kp = lambda k: k if k.get("locked") else {x: k.get(x) for x in ("name", "unit", "plan", "fact", "forecast", "prev", "dev", "dev_unit", "status", "compare")}
    kpis = [{"id": k["id"], "name": k["name"], "dept": k["dept_name"], "locked": True} if k.get("locked") else {"id": k["id"], "dept": k["dept_name"], **kp(k)}
            for k in kpi_public_all(user, P, F)]
    # неделя к неделе по KPI (только доступные, без помесячных)
    a1, b1 = t - timedelta(days=7), t - timedelta(days=1)
    a0, b0 = t - timedelta(days=14), t - timedelta(days=8)
    wk = []
    for k in KPIS:
        if not can_see(user, k) or k["id"] in ("payroll", "staffing", "cac") or (F["dept"] and k["dept"] != F["dept"]):
            continue
        v1, v0 = fact(k["id"], a1, b1, F), fact(k["id"], a0, b0, F)
        if v1 is None or v0 is None:
            continue
        ch = (v1 - v0) if k["unit"] == "%" else ((v1 - v0) / v0 * 100 if v0 else None)
        wk.append({"name": k["name"], "unit": k["unit"], "this_week": rnd(v1), "prev_week": rnd(v0),
                   "change": rnd(ch, 1), "change_unit": "п.п." if k["unit"] == "%" else "%", "better_if": {1: "выше", -1: "ниже", 0: "в коридоре 65–92 %"}[k["dir"]]})
    fc = forecast(user) if "forecast" in screens else None
    own_src = {sid for k in KPIS if can_see(user, k) for sid in k["src"]}
    srcs = [{"name": s["name"], "last_sync": iso(last_sync(s)), "stale_hours": round((now() - last_sync(s)).total_seconds() / 3600, 1)}
            for s in S.sources if not head or s["id"] in own_src]
    chart_ = pulse["chart"]
    return {
        "generated_at": iso(now()), "today": t.isoformat(), "timezone": "Europe/Minsk", "currency": "BYN",
        "user": {"name": user["name"], "role": ROLE_NAMES[user["role"]]},
        "filters": {"period": P.label, "period_dates": f"{P.start.isoformat()} — {P.end.isoformat()}",
                    "period_progress": f"прошло {P.elapsed} из {P.days} дн." if P.partial else "период завершён",
                    "compared_with": f"{P.prev[0].isoformat()} — {P.prev[1].isoformat()}",
                    "department": S.dept[F["dept"]]["name"] if F["dept"] else "Все подразделения",
                    "product": S.product[F["product"]]["name"] if F["product"] else "Все продукты",
                    "note": "Фильтр продукта сужает заказы; фильтр подразделения — только набор показателей."},
        "kpis": kpis, "critical": pulse["critical_names"],
        "chart_on_screen": {"metric": chart_["metric"], "unit": chart_["unit"],
                            "buckets": [{k: b[k] for k in ("label", "plan", "fact", "forecast")} for b in chart_["buckets"]]},
        "capacity_load_by_section": pulse["load"] if "production" in screens else None,
        "weekly_series_8w": {m: _weekly(m, F) for m in mets},
        "week": {"this_week": f"{a1.isoformat()} — {b1.isoformat()}", "prev_week": f"{a0.isoformat()} — {b0.isoformat()}", "kpis": wk},
        "anomalies": [a for a in _anomalies(F) if a["metric"] in mets],
        "trend": {"assumptions": ["прогноз = линейный тренд за последние 56 полных дней × профиль дня недели",
                                  "не учитывает будущие акции, праздники и сезонный пик декабря (для них см. capacity_forecast)",
                                  "диапазон — 80-% интервал по разбросу остатков и неопределённости наклона",
                                  "moving_avg_28x30 — наивная оценка: среднее за 28 дней × 30"],
                  **{m: fotik_trend(m, F) for m in mets}},
        "capacity_forecast": {"method": fc["method"], "deficit_week": fc["deficit_week"],
                              "weeks": [{"week": w["label"], "demand": w["demand"], "capacity": w["capacity"], "deficit_sections": w["deficit_sections"]} for w in fc["weeks"]]} if fc else None,
        "data_sources": srcs,
    }


def _clean_history(h):
    msgs = []
    for m in (h if isinstance(h, list) else [])[-12:]:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            continue
        txt = str(m.get("content") or "").strip()[:4000]
        if not txt:
            continue
        if msgs and msgs[-1]["role"] == m["role"]:
            msgs[-1]["content"] += "\n\n" + txt
        else:
            msgs.append({"role": m["role"], "content": txt})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if msgs and msgs[-1]["role"] == "user":  # незакрытый вопрос без ответа — отбрасываем
        msgs.pop()
    return msgs


def call_claude(system, messages):
    import urllib.error
    import urllib.request
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise ApiError(503, "Фотик пока не подключён: администратору нужно задать ANTHROPIC_API_KEY на сервере и перезапустить его.")
    req = urllib.request.Request(FOTIK_API_URL, method="POST",
                                 data=json.dumps({"model": FOTIK_MODEL, "max_tokens": 1200, "system": system, "messages": messages}).encode(),
                                 headers={"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=FOTIK_TIMEOUT) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"Фотик: Claude API ответил {e.code}\n")
        if e.code in (401, 403):
            raise ApiError(502, "Фотик не смог подключиться к Claude API: ключ недействителен или нет доступа. Сообщите администратору.")
        if e.code in (429, 529) or e.code >= 500:
            raise ApiError(503, "Фотик сейчас перегружен. Повторите вопрос через минуту.")
        raise ApiError(502, "Фотик не смог получить ответ от Claude API. Повторите попытку позже.")
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ApiError(504, "Фотик не дождался ответа от Claude API. Проверьте интернет на сервере и повторите.")
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    if not text:
        raise ApiError(502, "Фотик вернул пустой ответ. Попробуйте переформулировать вопрос.")
    return text, data.get("usage") or {}


def api_fotik(user, body):
    question = str(body.get("question") or "").strip()
    if not question:
        raise ApiError(422, {"message": "Введите вопрос для Фотика.", "fields": {"question": "Пустой вопрос"}})
    if len(question) > 2000:
        raise ApiError(422, {"message": "Вопрос слишком длинный — до 2000 символов.", "fields": {"question": "Больше 2000 символов"}})
    ts = [x for x in FOTIK_RATE.get(user["login"], []) if x > time.time() - 60]
    if len(ts) >= 20:
        raise ApiError(429, "Слишком много вопросов подряд. Подождите минуту.")
    FOTIK_RATE[user["login"]] = ts + [time.time()]
    f = body.get("filters") if isinstance(body.get("filters"), dict) else {}
    q = {k: str(f[k]) for k in ("period", "dept", "product") if f.get(k)}
    ctx = fotik_context(user, q)
    screen = str(body.get("screen") or "")[:40]
    system = FOTIK_SYSTEM + (f"\n\nПользователь сейчас на экране: {screen}." if screen else "") + \
        "\n\nДанные дашборда (JSON):\n" + json.dumps(ctx, ensure_ascii=False, separators=(",", ":"))
    messages = _clean_history(body.get("history")) + [{"role": "user", "content": question}]
    try:
        answer, usage = call_claude(system, messages)
    except ApiError as e:
        audit(user, "Вопрос ИИ-ассистенту", "Фотик", "ошибка", {"code": e.code, "period": ctx["filters"]["period"]})
        raise
    audit(user, "Вопрос ИИ-ассистенту", "Фотик", details={"period": ctx["filters"]["period"], "chars": len(question)})
    return {"answer": answer, "model": FOTIK_MODEL, "context": {"period": ctx["filters"]["period"], "department": ctx["filters"]["department"],
                                                                 "product": ctx["filters"]["product"], "generated_at": ctx["generated_at"]},
            "usage": {k: usage.get(k) for k in ("input_tokens", "output_tokens")}}


def fotik_status():
    return {"enabled": bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()), "model": FOTIK_MODEL}


def pub_user(u):
    return {"login": u["login"], "name": u["name"], "role": u["role"], "role_name": ROLE_NAMES[u["role"]], "title": u["title"], "dept": u["dept"],
            "dept_name": S.dept[u["dept"]]["name"] if u["dept"] else None}


# ============================================================== HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "FotoprintMVP/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (now().strftime("%H:%M:%S"), fmt % args))

    def send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def user(self):
        h = self.headers.get("Authorization", "")
        tok = h[7:] if h.startswith("Bearer ") else None
        s = SESSIONS.get(tok)
        if not s or s[1] < time.time():
            SESSIONS.pop(tok, None)
            raise ApiError(401, "Требуется вход в систему.")
        return USERS[s[0]]

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 64_000:
            raise ApiError(413, "Слишком большой запрос.")
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            raise ApiError(400, "Некорректный JSON в запросе.")

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PATCH(self):
        self.route("PATCH")

    def route(self, method):
        u = urlparse(self.path)
        path = unquote(u.path)
        if not path.startswith("/api/"):
            return self.static(path) if method == "GET" else self.send_json(405, {"error": "Метод не поддерживается."})
        q = {k: v[-1] for k, v in parse_qs(u.query).items()}
        try:
            if path == "/api/health":
                return self.send_json(200, {"status": "ok", "time": iso(now()), "data_loaded_at": iso(S.loaded_at),
                                            "data_checked_at": iso(getattr(S, "checked_at", S.loaded_at)), "refresh_sec": DATA_REFRESH_SEC,
                                            "reload_error": getattr(S, "reload_error", None),
                                            "live_simulation": LIVE_SIM, "live_orders_today": getattr(S, "live_count", 0), "orders_total": len(S.orders)})
            if path == "/api/login" and method == "POST":
                return self.login(self.body())
            user = self.user()
            if path == "/api/logout" and method == "POST":
                SESSIONS.pop(self.headers.get("Authorization", "")[7:], None)
                audit(user, "Выход из системы", "Сессия")
                return self.send_json(200, {"ok": True})
            m = re.fullmatch(r"/api/kpi/([a-z_]+)", path)
            n = re.fullmatch(r"/api/orders/(ORD-\d+)", path)
            dm = re.fullmatch(r"/api/decisions/(\d+)", path)
            km = re.fullmatch(r"/api/kpi/([a-z_]+)/(comments|owner)", path)
            if method == "GET":
                if path == "/api/me":
                    return self.send_json(200, pub_user(user))
                if path == "/api/meta":
                    return self.send_json(200, api_meta(user))
                if path == "/api/pulse":
                    return self.send_json(200, api_pulse(user, q))
                if m:
                    return self.send_json(200, {**api_kpi(user, m.group(1), q), "notes": kpi_notes_public(user, m.group(1))})
                if path == "/api/orders":
                    return self.send_json(200, api_orders(user, q))
                if n:
                    return self.send_json(200, api_order(user, n.group(1)))
                if path == "/api/tickets":
                    return self.send_json(200, api_tickets(user, q))
                if path == "/api/sales":
                    return self.send_json(200, api_sales(user, q))
                if path == "/api/production":
                    return self.send_json(200, api_production(user, q))
                if path == "/api/forecast":
                    require_screen(user, "forecast")
                    return self.send_json(200, forecast(user))
                if path == "/api/finance":
                    return self.send_json(200, api_finance(user, q))
                if path == "/api/quality":
                    return self.send_json(200, api_quality(user, q))
                if path == "/api/decisions":
                    return self.send_json(200, api_decisions(user, q))
                if dm:
                    require_screen(user, "decisions")
                    d = next((dec_public(x) for x in load_decisions() if str(x["id"]) == dm.group(1) and visible_decision(user, x)), None)
                    if not d:
                        raise ApiError(404, "Решение не найдено.")
                    return self.send_json(200, d)
                if path == "/api/audit":
                    return self.send_json(200, api_audit(user, q))
                if path == "/api/alerts":
                    return self.send_json(200, api_alerts(user))
                if path == "/api/fotik":
                    return self.send_json(200, fotik_status())
                if path == "/api/fotik/context":
                    return self.send_json(200, fotik_context(user, q))
            if method == "POST" and km and km.group(2) == "comments":
                return self.send_json(201, api_kpi_comment(user, km.group(1), self.body()))
            if method in ("PATCH", "PUT") and km and km.group(2) == "owner":
                return self.send_json(200, api_kpi_owner(user, km.group(1), self.body()))
            if method == "POST":
                if path == "/api/fotik":
                    return self.send_json(200, api_fotik(user, self.body()))
                if path == "/api/decisions":
                    return self.send_json(201, api_decision_create(user, self.body()))
                if path == "/api/alerts/read":
                    mark_read(user, self.body().get("ids", []))
                    return self.send_json(200, {"ok": True})
                if path == "/api/export":
                    b = self.body()
                    audit(user, "Экспорт CSV", b.get("object", "—"), details={"rows": b.get("rows")})
                    return self.send_json(200, {"ok": True})
            if method == "PATCH" and dm:
                return self.send_json(200, api_decision_update(user, dm.group(1), self.body()))
            raise ApiError(404, "Метод API не найден.")
        except ApiError as e:
            payload = e.msg if isinstance(e.msg, dict) else {"message": e.msg}
            return self.send_json(e.code, {"error": payload["message"], **({"fields": payload["fields"]} if "fields" in payload else {})})
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            return self.send_json(500, {"error": "Внутренняя ошибка сервера. Попробуйте повторить запрос.", "detail": type(e).__name__})

    def login(self, b):
        login = str(b.get("login", "")).strip().lower()
        pw = str(b.get("password", ""))
        u = USERS.get(login)
        if not u or not hmac.compare_digest(u["hash"], _hash(pw, u["salt"])):
            audit({"login": login or "—", "name": login or "—", "role": "—"} if not u else u, "Вход в систему", "Сессия", "отказано", "Неверный логин или пароль")
            time.sleep(0.4)
            raise ApiError(401, "Неверный логин или пароль.")
        tok = secrets.token_urlsafe(32)
        SESSIONS[tok] = (login, time.time() + SESSION_HOURS * 3600)
        audit(u, "Вход в систему", "Сессия")
        return self.send_json(200, {"token": tok, "user": pub_user(u), "expires_in": SESSION_HOURS * 3600})

    def static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        full = os.path.realpath(os.path.join(STATIC, path.lstrip("/")))
        if not full.startswith(os.path.realpath(STATIC)) or not os.path.isfile(full):
            full = os.path.join(STATIC, "index.html")
        ctype = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".json": "application/json"}.get(os.path.splitext(full)[1], "application/octet-stream")
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


ROLE_NAMES["—"] = "—"


def main():
    S.load()
    load_decisions()
    threading.Thread(target=auto_reload_loop, name="data-reload", daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Фотопринт · Управленческая платформа → http://localhost:{PORT}  (данные на {S.today}, заказов: {len(S.orders)})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
