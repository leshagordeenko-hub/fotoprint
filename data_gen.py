#!/usr/bin/env python3
"""
Генератор синтетических данных ООО «Фотопринт» (трек 1 хакатона).

Все данные вымышленные и обезличенные: клиенты — это ID без ФИО, сотрудники —
только численность по подразделениям. Генерация детерминирована (seed), поэтому
набор можно воспроизвести командой:  python3 data_gen.py

Источники (имитация интеграций), связанные общими идентификаторами:
  CRM (клиенты, обращения)      customer_id, order_id
  ERP (заказы, статусы)         order_id, customer_id, product_id, channel_id, campaign_id, section_id
  MES (производство по участкам) section_id, date
  1С:ЗУП (численность, ФОТ)      dept_id, section_id, month
  1С:Бухгалтерия (БДР / БДДС)    dept_id, product_id, month
  Веб-аналитика picPac.by        channel_id, date

Заложенный сценарий (чтобы детализация могла объяснить отклонения):
  * за 60 дней до даты генерации участок «Переплёт» потерял 5 операторов из 14 (1С:ЗУП);
  * акция «Фотокниги −20%» (дни −42…−12) подняла спрос на фотокниги на ~45 %;
  * партия клея (дни −33…−6) дала всплеск брака «Расслоение переплёта»;
  * очередь на переплёте → заказы не в срок → обращения «Сроки изготовления» → падение SLA;
  * в декабре сезонный пик (Новый год) → прогнозируемый дефицит мощности.
"""
import hashlib
import json
import math
import os
import random
from datetime import date, datetime, time, timedelta, timezone

MINSK = timezone(timedelta(hours=3), "Europe/Minsk")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

DEPARTMENTS = [
    {"id": "D-SALES", "name": "Продажи и маркетинг"},
    {"id": "D-PROD", "name": "Производство"},
    {"id": "D-SUP", "name": "Клиентский сервис"},
    {"id": "D-FIN", "name": "Финансы"},
    {"id": "D-HR", "name": "Персонал"},
]
SECTIONS = [
    {"id": "SEC-PRINT", "name": "Цифровая печать", "cap": 50.0},
    {"id": "SEC-BIND", "name": "Переплёт", "cap": 16.0},
    {"id": "SEC-WIDE", "name": "Широкоформат", "cap": 15.0},
]
PRODUCTS = [
    # base = заказов в день, price = BYN за изделие, lead = обещанный срок (дней)
    {"id": "PRD-BOOK", "name": "Фотокниги", "section": "SEC-BIND", "base": 6.0, "price": 78.0, "cost": 0.44, "lead": 4, "units": [1, 1, 1, 2], "defect": 0.020},
    {"id": "PRD-PRINT", "name": "Фотопечать", "section": "SEC-PRINT", "base": 15.0, "price": 21.0, "cost": 0.36, "lead": 3, "units": [1], "defect": 0.012},
    {"id": "PRD-CAL", "name": "Календари", "section": "SEC-WIDE", "base": 1.2, "price": 32.0, "cost": 0.40, "lead": 3, "units": [1, 1, 2, 3], "defect": 0.015},
    {"id": "PRD-CANVAS", "name": "Холсты и постеры", "section": "SEC-WIDE", "base": 3.2, "price": 55.0, "cost": 0.38, "lead": 3, "units": [1, 1, 2], "defect": 0.025},
    {"id": "PRD-SOUV", "name": "Фотосувениры", "section": "SEC-PRINT", "base": 4.3, "price": 18.0, "cost": 0.50, "lead": 3, "units": [1, 1, 2, 3, 4], "defect": 0.018},
]
CHANNELS = [
    {"id": "CH-WEB", "name": "Сайт picPac.by", "w": 0.45, "online": True},
    {"id": "CH-APP", "name": "Мобильное приложение", "w": 0.22, "online": True},
    {"id": "CH-SALON", "name": "Фотосалоны", "w": 0.18, "online": False},
    {"id": "CH-B2B", "name": "Корпоративные (B2B)", "w": 0.07, "online": False},
    {"id": "CH-MKT", "name": "Маркетплейсы", "w": 0.08, "online": False},
]
REGIONS = [("Минск", .48), ("Гомель", .12), ("Брест", .11), ("Гродно", .10), ("Витебск", .10), ("Могилёв", .09)]
SEASON = {1: .80, 2: .85, 3: .95, 4: 1.0, 5: 1.10, 6: 1.15, 7: 1.0, 8: 1.0, 9: 1.05, 10: 1.05, 11: 1.15, 12: 1.60}
CAL_SEASON = {9: 1.2, 10: 1.6, 11: 2.6, 12: 3.2}
WEEKDAY = [1.05, 1.0, 1.0, 1.0, 1.05, 1.15, 0.95]
DEFECT_REASONS = ["Цветопередача", "Низкое разрешение исходника", "Обрезка и вылеты", "Повреждение при упаковке"]
DOWNTIME_REASONS = ["Плановое обслуживание", "Нет материалов", "Сбой ПО", "Отсутствие оператора"]
TICKET_TOPICS = ["Оплата", "Доставка", "Редактор проекта", "Возврат", "Консультация"]
TICKET_CHANNELS = [("Чат", .40, 15), ("Email", .25, 240), ("Телефон", .20, 10), ("Instagram", .15, 60)]


def month_add(d, k):
    m = d.month - 1 + k
    return date(d.year + m // 12, m % 12 + 1, 1)


def days_in_month(d):
    return (month_add(d, 1) - date(d.year, d.month, 1)).days


def iso(dt):
    return dt.isoformat(timespec="seconds") if dt else None


def at(d, h, m=0):
    return datetime.combine(d, time(int(h), int(m)), MINSK)


def generate(now=None, seed=2026):
    rnd = random.Random(seed)
    now = (now or datetime.now(MINSK)).astimezone(MINSK).replace(microsecond=0)
    today = now.date()
    start = month_add(today.replace(day=1), -7)
    D = lambda k: today + timedelta(days=k)  # noqa: E731  смещение от даты генерации

    STAFF_LOSS = D(-60)
    GLUE = (D(-33), D(-6))
    SECOND_SHIFT = D(-10)
    CAMPAIGNS = [
        {"id": "CMP-01", "name": "Весенняя печать −15%", "product_id": "PRD-PRINT", "source": "Email-рассылка", "start": month_add(start, 1), "end": month_add(start, 1) + timedelta(days=20), "uplift": 1.25, "discount": .15, "budget": 4200},
        {"id": "CMP-02", "name": "Выпускной альбом", "product_id": "PRD-BOOK", "source": "Instagram", "start": month_add(start, 2) + timedelta(days=10), "end": month_add(start, 3) + timedelta(days=5), "uplift": 1.20, "discount": .10, "budget": 6500},
        {"id": "CMP-03", "name": "Летние холсты", "product_id": "PRD-CANVAS", "source": "Яндекс Директ", "start": month_add(start, 4), "end": month_add(start, 4) + timedelta(days=25), "uplift": 1.30, "discount": .10, "budget": 3800},
        {"id": "CMP-04", "name": "Фотокниги −20%", "product_id": "PRD-BOOK", "source": "Instagram + Google Ads", "start": D(-42), "end": D(-12), "uplift": 1.45, "discount": .20, "budget": 12500},
        {"id": "CMP-05", "name": "Календари 2027", "product_id": "PRD-CAL", "source": "Email-рассылка", "start": D(-20), "end": D(30), "uplift": 1.35, "discount": .05, "budget": 5200},
    ]
    prod = {p["id"]: p for p in PRODUCTS}

    # ------------------------------------------------------------------ ERP: заказы
    orders, customers = [], []
    cust_pool = []  # (customer, weight)
    oid = 100000
    d = start
    while d <= today:
        months_from_start = (d.year - start.year) * 12 + d.month - start.month
        trend = 1 + 0.01 * months_from_start
        for p in PRODUCTS:
            lam = p["base"] * SEASON[d.month] * WEEKDAY[d.weekday()] * trend
            if p["id"] == "PRD-CAL":
                lam *= CAL_SEASON.get(d.month, 0.5)
            camp = next((c for c in CAMPAIGNS if c["product_id"] == p["id"] and c["start"] <= d <= c["end"]), None)
            if camp:
                lam *= camp["uplift"]
            n = poisson(rnd, lam)
            for _ in range(n):
                hh = min(23.5, max(0, rnd.gauss(14.5, 4.2)))
                created = at(d, int(hh), int((hh % 1) * 60))
                if created > now:
                    continue
                ch = pick(rnd, [(c["id"], c["w"] + (0.06 * months_from_start / 7 if c["id"] == "CH-APP" else 0)) for c in CHANNELS])
                # клиент: повторный или новый
                repeat_p = 0.30 + 0.015 * months_from_start
                if cust_pool and rnd.random() < repeat_p:
                    cust = cust_pool[int(len(cust_pool) * (1 - rnd.random() ** 1.6)) - 1]
                else:
                    cust = {
                        "id": f"CUS-{len(customers) + 1:05d}",
                        "segment": "Корпоративные" if ch == "CH-B2B" else ("Фотографы-профи" if rnd.random() < .1 else "Частные"),
                        "region": pick(rnd, REGIONS),
                        "acquisition_channel_id": ch,
                        "created_at": iso(created),
                        "phone_hash": hashlib.sha1(f"{seed}-{len(customers)}".encode()).hexdigest()[:12],
                        "marketing_consent": rnd.random() < .62,
                    }
                    customers.append(cust)
                    cust_pool.append(cust)
                units = rnd.choice(p["units"]) * (rnd.choice([2, 3, 5]) if ch == "CH-B2B" else 1)
                gross = round(units * p["price"] * rnd.uniform(.75, 1.3), 2)
                attributed = camp and rnd.random() < .55
                discount = round(gross * camp["discount"], 2) if attributed else 0.0
                orders.append({
                    "id": f"ORD-{oid}", "customer_id": cust["id"], "product_id": p["id"], "section_id": p["section"],
                    "channel_id": ch, "campaign_id": camp["id"] if attributed else None, "segment": cust["segment"], "region": cust["region"],
                    "units": units, "amount": round(gross - discount, 2), "discount": discount, "currency": "BYN",
                    "cost": round(gross * p["cost"] * rnd.uniform(.92, 1.08), 2),
                    "created_at": iso(created), "promised_date": (created.date() + timedelta(days=p["lead"])).isoformat(),
                    "_created": created,
                })
                oid += 1
        d += timedelta(days=1)
    orders.sort(key=lambda o: o["_created"])
    for i, o in enumerate(orders):
        o["id"] = f"ORD-{100000 + i}"

    # отмены и модерация
    for o in orders:
        c = o["_created"]
        if rnd.random() < .02:
            o["cancelled"] = True
            o["_mod"] = None
            continue
        m = c + timedelta(minutes=rnd.randint(40, 300))
        if m.hour >= 19 or m.date() != c.date():
            nd = c.date() + timedelta(days=1)
            m = at(nd, 9, rnd.randint(30, 59))
        o["_mod"] = m

    # ------------------------------------------------------------------ MES: производство (очередь по участкам)
    mes = []
    by_section_day = {}
    for o in orders:
        if o.get("_mod") and o["_mod"] <= now:
            by_section_day.setdefault((o["section_id"], o["_mod"].date()), []).append(o)
    for sec in SECTIONS:
        queue = []  # [order, remaining_units, is_reprint]
        d = start
        while d <= today:
            for o in sorted(by_section_day.get((sec["id"], d), []), key=lambda x: x["_mod"]):
                queue.append([o, float(o["units"]), False])
            working = d.weekday() != 6
            cap = sec["cap"]
            if sec["id"] == "SEC-BIND" and d >= STAFF_LOSS:
                cap = sec["cap"] * 9 / 14 * 1.21  # 9 операторов из 14 + переработки
                if d >= SECOND_SHIFT:
                    cap *= 1.25  # решение РШ-002: временная вторая смена (3 оператора из печати)
            downtime, reason = 0, None
            if working and rnd.random() < .14:
                downtime, reason = rnd.choice([30, 45, 60, 90, 120, 180]), rnd.choice(DOWNTIME_REASONS)
            if sec["id"] == "SEC-BIND" and GLUE[0] <= d <= GLUE[0] + timedelta(days=2) and working:
                downtime, reason = 240, "Нет материалов"
            eff = cap * (1 - downtime / 960) if working else 0
            q_units = sum(x[1] for x in queue)
            if working and q_units > 2 * cap:
                eff *= 1.2  # сверхурочные при длинной очереди
            out, budget = 0.0, eff
            done_today = []
            while queue and budget > 0:
                item = queue[0]
                take = min(item[1], budget)
                item[1] -= take
                budget -= take
                out += take
                if item[1] <= 1e-9:
                    queue.pop(0)
                    done_today.append(item)
            for o, _, is_reprint in done_today:
                p = prod[o["product_id"]]
                hh = rnd.uniform(10, 20)
                done_at = at(d, int(hh), int((hh % 1) * 60))
                if done_at > now:
                    done_at = now - timedelta(minutes=rnd.randint(5, 60))
                if not is_reprint:
                    rate = p["defect"]
                    defect_reason = rnd.choice(DEFECT_REASONS)
                    if sec["id"] == "SEC-BIND" and GLUE[0] <= d <= GLUE[1]:
                        rate, defect_reason = 0.11, "Расслоение переплёта"
                    if p["id"] == "PRD-PRINT" and month_add(start, 1) + timedelta(days=5) <= d <= month_add(start, 1) + timedelta(days=16):
                        rate, defect_reason = 0.06, "Цветопередача"
                    if rnd.random() < rate:
                        o["defect"] = True
                        o["defect_reason"] = defect_reason
                        o["reprint_cost"] = round(o["cost"] * rnd.uniform(.85, 1.0), 2)
                        queue.insert(0, [o, float(o["units"]), True])  # перепечатка — вне очереди
                        continue
                o["_produced"] = done_at
            mes.append({
                "date": d.isoformat(), "section_id": sec["id"], "working_day": working,
                "capacity_units": round(cap if working else 0, 2), "output_units": round(out, 2),
                "downtime_min": downtime, "downtime_reason": reason, "queue_units_eod": round(sum(x[1] for x in queue), 2),
                "source": "MES",
            })
            d += timedelta(days=1)

    # отгрузка, доставка, статусы
    for o in orders:
        hist = [{"status": "Принят", "at": iso(o["_created"])}]
        if o.get("cancelled"):
            ca = o["_created"] + timedelta(hours=rnd.randint(1, 20))
            hist.append({"status": "Отменён", "at": iso(min(ca, now))})
            o.update(status="Отменён", status_history=hist)
            continue
        mod = o["_mod"]
        if mod > now:
            o.update(status="Модерация", status_history=hist)
            continue
        hist.append({"status": "Модерация", "at": iso(mod - timedelta(minutes=rnd.randint(10, 30)))})
        hist.append({"status": "Производство", "at": iso(mod)})
        prod_at = o.get("_produced")
        if not prod_at:
            o.update(status="Производство", status_history=hist)
            continue
        hist.append({"status": "Готов", "at": iso(prod_at)})
        sd = prod_at.date() + timedelta(days=1)
        if sd.weekday() == 6:
            sd += timedelta(days=1)
        shipped = at(sd, rnd.randint(11, 17), rnd.randint(0, 59))
        o["produced_at"] = iso(prod_at)
        if shipped > now:
            o.update(status="Готов", status_history=hist)
            continue
        o["shipped_at"] = iso(shipped)
        hist.append({"status": "Передан в доставку", "at": iso(shipped)})
        delivered = shipped + timedelta(days=rnd.choice([1, 1, 2, 3]), hours=rnd.randint(0, 6))
        if delivered > now:
            o.update(status="Передан в доставку", status_history=hist)
            continue
        o["delivered_at"] = iso(delivered)
        hist.append({"status": "Завершён", "at": iso(delivered)})
        o.update(status="Завершён", status_history=hist)

    # ------------------------------------------------------------------ CRM: обращения
    tickets = []
    tickets_per_day = {}
    proto = []
    for o in orders:
        created = o["_created"]
        promised = datetime.fromisoformat(o["promised_date"] + "T18:00:00+03:00")
        shipped = datetime.fromisoformat(o["shipped_at"]) if o.get("shipped_at") else None
        late = (shipped and shipped > promised) or (not shipped and not o.get("cancelled") and now > promised)
        if late and rnd.random() < .33:
            proto.append((promised + timedelta(hours=rnd.randint(2, 40)), o, "Сроки изготовления"))
        if o.get("defect") and rnd.random() < .7:
            base = datetime.fromisoformat(o["delivered_at"]) if o.get("delivered_at") else datetime.fromisoformat(o.get("produced_at") or o["created_at"])
            proto.append((base + timedelta(hours=rnd.randint(3, 30)), o, "Качество продукции"))
        if rnd.random() < .055:
            proto.append((created + timedelta(hours=rnd.randint(1, 72)), o, rnd.choice(TICKET_TOPICS)))
    proto = [p for p in proto if p[0] <= now]
    proto.sort(key=lambda x: x[0])
    for ts, _, _ in proto:
        tickets_per_day[ts.date()] = tickets_per_day.get(ts.date(), 0) + 1
    for i, (ts, o, topic) in enumerate(proto):
        ch, _, sla = pick_full(rnd, TICKET_CHANNELS)
        load = (tickets_per_day.get(ts.date(), 0) / 3.6) ** 1.6
        first = max(1, int(rnd.lognormvariate(math.log(sla * .40), .55) * max(.6, load)))
        resolved = ts + timedelta(minutes=first + rnd.randint(20, 2400))
        result = {"Качество продукции": rnd.choice(["Перепечатка", "Перепечатка", "Возврат средств"]),
                  "Сроки изготовления": rnd.choice(["Консультация", "Компенсация промокодом"]),
                  "Возврат": "Возврат средств"}.get(topic, "Решено")
        tickets.append({
            "id": f"TCK-{20000 + i}", "customer_id": o["customer_id"], "order_id": o["id"], "topic": topic, "channel": ch,
            "created_at": iso(ts), "first_response_min": first, "sla_min": sla, "sla_met": first <= sla,
            "resolved_at": iso(resolved) if resolved <= now else None, "result": result if resolved <= now else "В работе",
            "assignee": f"Оператор {rnd.randint(1, 9):02d}", "source": "Helpdesk",
        })

    # ------------------------------------------------------------------ Веб-аналитика
    web = {}
    for o in orders:
        if o["channel_id"] in ("CH-WEB", "CH-APP"):
            k = (o["created_at"][:10], o["channel_id"])
            web[k] = web.get(k, 0) + 1
    web_rows = []
    d = start
    while d <= today:
        for ch, conv in (("CH-WEB", .031), ("CH-APP", .045)):
            n = web.get((d.isoformat(), ch), 0)
            camp_boost = 1.1 if any(c["start"] <= d <= c["end"] for c in CAMPAIGNS) else 1.0
            visits = int(max(n, 1) / (conv * camp_boost * rnd.uniform(.9, 1.1)))
            projects = int(visits * rnd.uniform(.18, .22))
            carts = int(projects * rnd.uniform(.40, .46))
            web_rows.append({"date": d.isoformat(), "channel_id": ch, "visits": visits, "projects_started": projects,
                             "carts": max(carts, n), "orders": n, "paid": int(round(n * .965)), "source": "Веб-аналитика"})
        d += timedelta(days=1)

    # ------------------------------------------------------------------ 1С:ЗУП (обезличенная витрина)
    staff = []
    STAFF_PLAN = {"D-PROD": 48, "D-SALES": 12, "D-SUP": 10, "D-FIN": 6, "D-HR": 3}
    SECTION_PLAN = {"SEC-PRINT": 20, "SEC-BIND": 14, "SEC-WIDE": 10}
    AVG_SALARY = {"D-PROD": 1850, "D-SALES": 2300, "D-SUP": 1700, "D-FIN": 2600, "D-HR": 2200}
    m = start
    while m <= today:
        month_end = month_add(m, 1) - timedelta(days=1)
        loss = month_end >= STAFF_LOSS
        for dep, plan in STAFF_PLAN.items():
            fact = plan
            if dep == "D-PROD":
                fact = plan - (5 if loss else rnd.choice([0, 1]))
            elif dep == "D-SUP":
                fact = plan - (2 if m.month == D(-30).month and m.year == D(-30).year else rnd.choice([0, 0, 1]))
            else:
                fact = plan - rnd.choice([0, 0, 0, 1])
            vac = round(fact * rnd.uniform(.8, 1.6), 1)
            sick = round(fact * rnd.uniform(.4, 1.0) * (1.6 if m.month in (10, 11, 1, 2) else 1), 1)
            staff.append({"month": m.isoformat()[:7], "dept_id": dep, "section_id": None, "headcount_plan": plan, "headcount_fact": fact,
                          "vacancies": plan - fact, "absence_vacation_days": vac, "absence_sick_days": sick,
                          "payroll_plan": round(plan * AVG_SALARY[dep], 2), "payroll_fact": round(fact * AVG_SALARY[dep] * rnd.uniform(1.0, 1.07), 2),
                          "currency": "BYN", "source": "1С:ЗУП"})
        for sec, plan in SECTION_PLAN.items():
            fact = plan - (5 if (sec == "SEC-BIND" and loss) else 0)
            shifts_plan = plan * 22
            staff.append({"month": m.isoformat()[:7], "dept_id": "D-PROD", "section_id": sec, "headcount_plan": plan, "headcount_fact": fact,
                          "vacancies": plan - fact, "shifts_plan": shifts_plan, "shifts_fact": int(shifts_plan * fact / plan * rnd.uniform(.95, 1.02)),
                          "source": "1С:ЗУП"})
        m = month_add(m, 1)

    # ------------------------------------------------------------------ планы (утверждённый бюджет)
    plans = []
    m = start
    while m < month_add(today.replace(day=1), 3):
        dim = days_in_month(m)
        months_from_start = (m.year - start.year) * 12 + m.month - start.month
        wd = sum(WEEKDAY[(m + timedelta(days=i)).weekday()] for i in range(dim))
        for p in PRODUCTS:
            lam = p["base"] * SEASON[m.month] * (1 + .01 * months_from_start) * wd * 1.04
            if p["id"] == "PRD-CAL":
                lam *= CAL_SEASON.get(m.month, .5)
            units = sum(p["units"]) / len(p["units"])
            avg_amount = units * p["price"] * 1.025 * 1.06  # с учётом крупных B2B-заказов
            plans.append({"month": m.isoformat()[:7], "metric": "orders", "product_id": p["id"], "value": round(lam, 1)})
            plans.append({"month": m.isoformat()[:7], "metric": "revenue", "product_id": p["id"], "value": round(lam * avg_amount, 2), "currency": "BYN"})
            plans.append({"month": m.isoformat()[:7], "metric": "cost", "product_id": p["id"], "value": round(lam * avg_amount * p["cost"] * 1.02, 2), "currency": "BYN"})
            plans.append({"month": m.isoformat()[:7], "metric": "output_units", "product_id": p["id"], "section_id": p["section"], "value": round(lam * units, 1)})
        plans.append({"month": m.isoformat()[:7], "metric": "marketing", "value": round(9000.0 + sum(c["budget"] * overlap_share(c, m) for c in CAMPAIGNS) * .9, 2), "currency": "BYN"})
        plans.append({"month": m.isoformat()[:7], "metric": "reprint_cost", "value": 950.0, "currency": "BYN"})
        m = month_add(m, 1)

    # клиенты: план = среднее факта 3 предыдущих месяцев × 1,05
    def month_of(s):
        return s[:7]
    first_order = {}
    active_by_month = {}
    for o in orders:
        if o.get("cancelled"):
            continue
        mo = month_of(o["created_at"])
        first_order.setdefault(o["customer_id"], mo)
        active_by_month.setdefault(mo, set()).add(o["customer_id"])
    new_by_month = {}
    for c, mo in first_order.items():
        new_by_month[mo] = new_by_month.get(mo, 0) + 1
    months = sorted(active_by_month)
    for i, mo in enumerate(months + [month_add(today.replace(day=1), k).isoformat()[:7] for k in (1, 2)]):
        prev = [mo2 for mo2 in months if mo2 < mo][-3:] or [mo]
        dim_scale = 1.0
        if mo == today.isoformat()[:7]:
            dim_scale = days_in_month(today) / today.day  # текущий месяц: факт неполный
        base_new = sum(new_by_month.get(x, 0) * (dim_scale if x == mo else 1) for x in prev) / len(prev)
        base_act = sum(len(active_by_month.get(x, ())) * (dim_scale if x == mo else 1) for x in prev) / len(prev)
        plans.append({"month": mo, "metric": "new_customers", "value": round(base_new * 1.05)})
        plans.append({"month": mo, "metric": "active_customers", "value": round(base_act * 1.05)})

    # ------------------------------------------------------------------ 1С:Бухгалтерия (БДР / БДДС)
    finance = []
    m = start
    reco_gap_month = month_add(today.replace(day=1), -2).isoformat()[:7]
    one_c_cutoff = now - timedelta(hours=27)  # выгрузка из 1С не обновлялась 27 часов
    plan_idx = {}
    for p in plans:
        plan_idx[(p["month"], p["metric"], p.get("product_id"))] = p["value"]
    staff_idx = {(s["month"], s["dept_id"]): s for s in staff if not s["section_id"]}
    while m <= today:
        mo = m.isoformat()[:7]
        mo_orders = [o for o in orders if o.get("shipped_at") and o["shipped_at"][:7] == mo and datetime.fromisoformat(o["shipped_at"]) <= one_c_cutoff]
        rev_fact = {p["id"]: 0.0 for p in PRODUCTS}
        cost_fact = {p["id"]: 0.0 for p in PRODUCTS}
        for o in mo_orders:
            rev_fact[o["product_id"]] += o["amount"]
            cost_fact[o["product_id"]] += o["cost"] + o.get("reprint_cost", 0)
        if mo == reco_gap_month:  # не проведены 3 возврата → расхождение сверки ERP ↔ 1С
            rev_fact["PRD-BOOK"] -= 3 * 84.30
        for p in PRODUCTS:
            finance.append({"month": mo, "kind": "БДР", "article": "Выручка", "dept_id": "D-SALES", "product_id": p["id"],
                            "plan": plan_idx.get((mo, "revenue", p["id"]), 0), "fact": round(rev_fact[p["id"]], 2), "currency": "BYN", "source": "1С:Бухгалтерия"})
            finance.append({"month": mo, "kind": "БДР", "article": "Себестоимость продукции", "dept_id": "D-PROD", "product_id": p["id"],
                            "plan": plan_idx.get((mo, "cost", p["id"]), 0), "fact": round(cost_fact[p["id"]], 2), "currency": "BYN", "source": "1С:Бухгалтерия"})
        payroll_plan = sum(s["payroll_plan"] for (mm, _), s in staff_idx.items() if mm == mo)
        payroll_fact = sum(s["payroll_fact"] for (mm, _), s in staff_idx.items() if mm == mo)
        mkt_fact = 9000 * rnd.uniform(.85, 1.05) + sum(c["budget"] * overlap_share(c, m) for c in CAMPAIGNS)
        shipped_n = len(mo_orders)
        rows = [
            ("ФОТ", "D-HR", payroll_plan * 1.34, payroll_fact * 1.34),
            ("Маркетинг", "D-SALES", 9000.0 + sum(c["budget"] * overlap_share(c, m) for c in CAMPAIGNS) * .9, mkt_fact),
            ("Аренда и коммунальные", "D-FIN", 14500.0, 14500.0 * rnd.uniform(.98, 1.04)),
            ("Логистика", "D-SALES", shipped_n * 2.1 * 1.0 + 400, shipped_n * 2.3),
            ("Прочие расходы", "D-FIN", 4200.0, 4200 * rnd.uniform(.8, 1.25)),
        ]
        for art, dep, pl, fa in rows:
            finance.append({"month": mo, "kind": "БДР", "article": art, "dept_id": dep, "product_id": None, "plan": round(pl, 2), "fact": round(fa, 2), "currency": "BYN", "source": "1С:Бухгалтерия"})
        rev_total_fact = sum(rev_fact.values())
        rev_total_plan = sum(plan_idx.get((mo, "revenue", p["id"]), 0) for p in PRODUCTS)
        cash = [
            ("Поступления от клиентов", "D-FIN", rev_total_plan * .99, rev_total_fact * rnd.uniform(.96, 1.0)),
            ("Оплата поставщикам", "D-FIN", -sum(plan_idx.get((mo, "cost", p["id"]), 0) for p in PRODUCTS) * .97, -sum(cost_fact.values()) * rnd.uniform(.92, 1.0)),
            ("Заработная плата и налоги с ФОТ", "D-HR", -payroll_plan * 1.34, -payroll_fact * 1.34),
            ("Маркетинг", "D-SALES", -(9000.0 + sum(c["budget"] * overlap_share(c, m) for c in CAMPAIGNS) * .9), -mkt_fact),
            ("Аренда", "D-FIN", -14500.0, -14500.0),
            ("Налоги", "D-FIN", -rev_total_plan * .06, -rev_total_fact * .06),
        ]
        for art, dep, pl, fa in cash:
            finance.append({"month": mo, "kind": "БДДС", "article": art, "dept_id": dep, "product_id": None, "plan": round(pl, 2), "fact": round(fa, 2), "currency": "BYN", "source": "1С:Бухгалтерия"})
        m = month_add(m, 1)

    # ------------------------------------------------------------------ дефекты качества данных (для сценария аналитика)
    dq_rnd = random.Random(seed + 1)
    for o in dq_rnd.sample(orders[-1500:], 23):
        o["channel_id"] = None  # пропуск канала: сбой интеграции сайта
    dups = []
    for c in dq_rnd.sample(customers, 14):
        dup = dict(c)
        dup["id"] = f"CUS-{len(customers) + len(dups) + 1:05d}"
        dup["created_at"] = iso(datetime.fromisoformat(c["created_at"]) + timedelta(days=dq_rnd.randint(3, 90)))
        dups.append(dup)
    customers.extend(dups)
    for t in dq_rnd.sample(tickets, 6):
        dup = dict(t)
        dup["id"] = f"TCK-{20000 + len(tickets)}"
        dup["created_at"] = iso(datetime.fromisoformat(t["created_at"]) + timedelta(minutes=dq_rnd.randint(1, 3)))
        tickets.append(dup)

    for o in orders:
        for k in [k for k in o if k.startswith("_")]:
            del o[k]
        o.setdefault("defect", False)
        o.setdefault("source", "ERP")

    sources = [
        {"id": "CRM", "name": "CRM (клиенты)", "entity": "customer", "interval_min": 15, "file": "crm_customers.json", "owner": "D-SALES"},
        {"id": "HELPDESK", "name": "Поддержка (обращения)", "entity": "interaction", "interval_min": 10, "file": "crm_tickets.json", "owner": "D-SUP"},
        {"id": "ERP", "name": "ERP (заказы и статусы)", "entity": "order", "interval_min": 5, "file": "erp_orders.json", "owner": "D-PROD"},
        {"id": "MES", "name": "MES (производство)", "entity": "metric", "interval_min": 30, "file": "mes_production.json", "owner": "D-PROD"},
        {"id": "WEB", "name": "Веб-аналитика picPac.by", "entity": "metric", "interval_min": 60, "file": "web_analytics.json", "owner": "D-SALES"},
        {"id": "ZUP", "name": "1С:ЗУП (персонал)", "entity": "metric", "interval_min": 720, "file": "zup_staff.json", "owner": "D-HR"},
        {"id": "1C", "name": "1С:Бухгалтерия (БДР/БДДС)", "entity": "metric", "interval_min": 60, "file": "onec_finance.json", "owner": "D-FIN",
         "failing_since": iso(one_c_cutoff), "last_error": "Таймаут подключения к базе 1С (выгрузка не выполнена)"},
    ]
    dicts = {
        "departments": DEPARTMENTS,
        "sections": [{k: v for k, v in s.items()} for s in SECTIONS],
        "products": [{k: p[k] for k in ("id", "name", "section", "price", "lead")} for p in PRODUCTS],
        "channels": [{k: c[k] for k in ("id", "name", "online")} for c in CHANNELS],
        "regions": [r for r, _ in REGIONS],
        "campaigns": [{**c, "start": c["start"].isoformat(), "end": c["end"].isoformat()} for c in CAMPAIGNS],
        "story": {"staff_loss": STAFF_LOSS.isoformat(), "glue": [GLUE[0].isoformat(), GLUE[1].isoformat()], "second_shift": SECOND_SHIFT.isoformat()},
    }
    meta = {"generated_at": iso(now), "today": today.isoformat(), "start": start.isoformat(), "seed": seed, "timezone": "Europe/Minsk (UTC+03:00)",
            "counts": {"orders": len(orders), "customers": len(customers), "tickets": len(tickets), "mes_rows": len(mes), "finance_rows": len(finance)}}

    os.makedirs(DATA, exist_ok=True)
    out = {"meta.json": meta, "dict.json": dicts, "sources.json": sources, "crm_customers.json": customers, "crm_tickets.json": tickets,
           "erp_orders.json": orders, "mes_production.json": mes, "web_analytics.json": web_rows, "zup_staff.json": staff,
           "onec_finance.json": finance, "plans.json": plans}
    for name, obj in out.items():
        tmp = os.path.join(DATA, name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, os.path.join(DATA, name))
    return meta


def overlap_share(c, m):
    """Доля бюджета кампании, приходящаяся на месяц m (пропорционально дням)."""
    ms, me = m, month_add(m, 1) - timedelta(days=1)
    s, e = max(c["start"], ms), min(c["end"], me)
    total = (c["end"] - c["start"]).days + 1
    return max(0, (e - s).days + 1) / total if e >= s else 0


def poisson(rnd, lam):
    if lam <= 0:
        return 0
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rnd.random()
        if p <= L:
            return k
        k += 1


def pick(rnd, pairs):
    r, acc = rnd.random() * sum(w for _, w in pairs), 0
    for v, w in pairs:
        acc += w
        if r <= acc:
            return v
    return pairs[-1][0]


def pick_full(rnd, rows):
    r, acc = rnd.random() * sum(x[1] for x in rows), 0
    for x in rows:
        acc += x[1]
        if r <= acc:
            return x
    return rows[-1]


if __name__ == "__main__":
    info = generate()
    print("Сгенерировано:", json.dumps(info["counts"], ensure_ascii=False), "→", DATA)
