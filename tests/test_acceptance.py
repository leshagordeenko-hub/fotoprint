"""
Приёмочные тесты трека 1 (УП-01…УП-05) и общих требований (ОТ-02, 04, 05, 07).
Запуск:  python3 -m unittest discover -s tests -v
Сервер поднимается в фоне на свободном порту с временным каталогом состояния,
поэтому тесты не трогают решения и журнал демо-стенда.
"""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from urllib.parse import quote
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server  # noqa: E402

PW = server.DEMO_PASSWORD


class Api:
    def __init__(self, base):
        self.base, self.token = base, None

    def call(self, path, method="GET", body=None):
        req = urllib.request.Request(self.base + "/api" + quote(path, safe="/?=&"), method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + self.token} if self.token else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def login(self, login):
        code, data = self.call("/login", "POST", {"login": login, "password": PW})
        assert code == 200, data
        self.token = data["token"]
        return self


class Acceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="fotoprint-state-")
        server.STATE = cls.tmp
        server.LIVE_PATH = os.path.join(cls.tmp, "live_orders.json")  # поток новых заказов — во временной папке, база не трогается
        server.S.load()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def api(self, who=None):
        a = Api(self.base)
        return a.login(who) if who else a

    # ---------------------------------------------------------------- ОТ-02: роли, вход
    def test_ot02_login_and_roles(self):
        code, data = self.api().call("/login", "POST", {"login": "director", "password": "wrong"})
        self.assertEqual(code, 401)
        self.assertIn("Неверный", data["error"])
        for u in ("director", "prod", "sales", "analyst"):
            code, me = self.api(u).call("/me")
            self.assertEqual(code, 200)
            self.assertEqual(me["login"], u)
        code, _ = self.api().call("/pulse")
        self.assertEqual(code, 401, "без токена данные недоступны")

    # ---------------------------------------------------------------- УП-01: ≥3 источника с общими ID
    def test_up01_sources_joined_by_ids(self):
        a = self.api("analyst")
        code, q = a.call("/quality")
        self.assertEqual(code, 200)
        self.assertGreaterEqual(len(q["sources"]), 3)
        self.assertEqual(q["linkage"]["orders_with_customer"], 100.0)
        self.assertEqual(q["linkage"]["tickets_with_order"], 100.0)
        oid = next(t["order_id"] for t in server.S.tickets)
        code, o = a.call("/orders/" + oid)
        self.assertEqual(code, 200)
        self.assertEqual(o["order"]["id"], oid)
        self.assertIsNotNone(o["customer"], "заказ связан с клиентом CRM")
        self.assertTrue(o["tickets"], "заказ связан с обращением Helpdesk")
        self.assertIn("posted_1c", o["finance"])

    # ---------------------------------------------------------------- УП-02: ≥10 KPI с формулой, источником, временем
    def test_up02_ten_kpis_with_formula_source_time(self):
        code, p = self.api("director").call("/pulse")
        self.assertEqual(code, 200)
        computed = [k for k in p["kpis"] if k.get("fact") is not None]
        self.assertGreaterEqual(len(computed), 10)
        for k in computed:
            self.assertTrue(k["formula"], k["id"])
            self.assertTrue(k["sources"], k["id"])
            self.assertTrue(k["updated_at"].endswith("+03:00"), k["id"])
            self.assertIn(k["status"], ("ok", "warn", "crit"))
            self.assertIsNotNone(k["plan"], k["id"])

    # ---------------------------------------------------------------- УП-03: фильтр меняет показатели, детализация объясняет
    def test_up03_filters_and_explanation(self):
        a = self.api("director")
        _, all_ = a.call("/pulse?period=2026-10")
        _, book = a.call("/pulse?period=2026-10&product=PRD-BOOK")
        rev = lambda d: next(k for k in d["kpis"] if k["id"] == "revenue")["fact"]  # noqa: E731
        self.assertLess(rev(book), rev(all_), "фильтр по продукту меняет оборот")
        _, sep = a.call("/pulse?period=2026-09")
        self.assertNotEqual(rev(sep), rev(all_), "фильтр по периоду меняет оборот")
        _, prod = a.call("/pulse?period=2026-10&dept=D-PROD")
        self.assertTrue(all(k["dept"] == "D-PROD" for k in prod["kpis"]), "фильтр по подразделению")
        code, d = a.call("/kpi/on_time?period=2026-10")
        self.assertEqual(code, 200)
        self.assertEqual(d["status"], "crit")
        self.assertIn("Переплёт", d["explanation"]["text"], "детализация объясняет отклонение")
        self.assertTrue(any(f.get("source") == "1С:ЗУП" for f in d["explanation"]["factors"]), "причина связана с данными 1С:ЗУП")
        code, lst = a.call("/orders?period=2026-10&kind=late&section=Переплёт")
        self.assertEqual(code, 200)
        self.assertGreater(lst["total"], 0, "переход от участка к заказам")

    # ---------------------------------------------------------------- УП-04: решение сохраняется и попадает в журнал
    def test_up04_decision_saved_and_audited(self):
        a = self.api("director")
        body = {"kpi_id": "defect", "dept": "D-PROD", "title": "Брак выше нормы на переплёте", "impact": "Перепечатки", "cause": "Партия клея",
                "action": "Входной контроль партии клея", "owner": "pos-bind", "due": "2099-01-01", "priority": "Высокий", "status": "Новое"}
        code, d = a.call("/decisions", "POST", body)
        self.assertEqual(code, 201, d)
        code, d2 = a.call(f"/decisions/{d['id']}", "PATCH", {"status": "В работе", "version": d["rev"]})
        self.assertEqual(code, 200, d2)
        self.assertEqual(d2["status"], "В работе")
        self.assertEqual(len(d2["history"]), 2)
        self.assertEqual(d2["history"][-1]["changes"][0], {"field": "status", "label": "Статус", "from": "Новое", "to": "В работе"})
        _, lst = a.call("/decisions")
        self.assertIn(d["id"], [x["id"] for x in lst["items"]], "решение сохранено")
        _, au = a.call("/audit?per=50")
        acts = [(x["action"], x["object"]) for x in au["items"]]
        self.assertIn(("Создание решения", f"{d['code']} «{body['title']}»"), acts)
        self.assertIn(("Изменение решения", f"{d['code']} «{body['title']}»"), acts)

    def test_up04_validation_and_conflict(self):
        a = self.api("director")
        code, e = a.call("/decisions", "POST", {"title": "x", "dept": "D-PROD"})
        self.assertEqual(code, 422)
        self.assertIn("action", e["fields"])
        code, d = a.call("/decisions", "POST", {"dept": "D-PROD", "title": "Проверка версии", "action": "Проверить конфликт", "owner": "prod", "due": "2099-01-01", "priority": "Низкий"})
        a.call(f"/decisions/{d['id']}", "PATCH", {"status": "В работе", "version": d["rev"]})
        code, e = a.call(f"/decisions/{d['id']}", "PATCH", {"status": "Выполнено", "version": d["rev"]})
        self.assertEqual(code, 409, "устаревшая версия карточки не перезаписывает чужие изменения")

    # ---------------------------------------------------------------- УП-05: закрытые показатели другого подразделения
    def test_up05_head_cannot_see_other_dept_closed(self):
        prod = self.api("prod")
        # свой закрытый KPI виден на своём экране, чужие KPI (открытые и закрытые) — нет
        _, pr = prod.call("/production")
        by = {k["id"]: k for k in pr["kpis"]}
        self.assertFalse(by["reprint_cost"].get("locked"), "свой закрытый KPI виден")
        self.assertIn("fact", by["reprint_cost"])
        for kid in ("gross_margin", "cac", "revenue"):
            code, _ = prod.call(f"/kpi/{kid}")
            self.assertEqual(code, 403, f"чужой KPI {kid} закрыт")
        _, meta = prod.call("/meta")
        self.assertEqual({k["dept"] for k in meta["kpis"]}, {"D-PROD"}, "в справочнике только свои KPI")
        sales = self.api("sales")
        self.assertEqual(sales.call("/kpi/reprint_cost")[0], 403)
        self.assertEqual(sales.call("/kpi/cac")[0], 200, "свой закрытый KPI продаж виден")
        _, au = self.api("analyst").call("/audit?result=отказано&per=100")
        self.assertTrue(any(x["user"] == "prod" and "Валовая маржа" in x["object"] for x in au["items"]), "отказ записан в журнал")

    def test_heads_see_only_own_dashboard(self):
        expect = {"prod": {"production", "forecast"}, "sales": {"sales"}}
        all_screens = {"/pulse": "pulse", "/sales": "sales", "/production": "production", "/finance": "finance",
                       "/decisions": "decisions", "/forecast": "forecast", "/quality": "quality", "/audit": "audit", "/tickets": "tickets"}
        for login, own in expect.items():
            a = self.api(login)
            _, meta = a.call("/meta")
            self.assertEqual(set(meta["permissions"]["screens"]), own)
            self.assertFalse(meta["permissions"]["decide"])
            for path, scr in all_screens.items():
                code, _ = a.call(path)
                self.assertEqual(code, 200 if scr in own else 403, f"{login} {path}")
            code, _ = a.call("/decisions", "POST", {"dept": meta["user"]["dept"], "title": "Руководитель пробует", "action": "Не должно сработать",
                                                     "owner": login, "due": "2099-01-01", "priority": "Низкий"})
            self.assertEqual(code, 403, "руководитель не создаёт решения")
            _, al = a.call("/alerts")
            self.assertTrue(all(not x["href"].startswith(("#/pulse", "#/decisions", "#/quality")) for x in al["items"]), "уведомления ведут только на свои экраны")
        self.assertNotIn("forecast", [x["kind"] for x in self.api("sales").call("/alerts")[1]["items"]], "продажам не приходит дефицит мощности")
        for login in ("director", "analyst"):
            a = self.api(login)
            for path in all_screens:
                self.assertEqual(a.call(path)[0], 200, f"{login} {path}")
        _, au = self.api("analyst").call("/audit?result=отказано&per=200")
        self.assertTrue(any(x["user"] == "sales" and x["object"] == "Пульс компании" for x in au["items"]), "попытка открыть чужой экран в журнале")

    def test_kpi_comments_and_responsible(self):
        d = self.api("director")
        code, n = d.call("/kpi/on_time/owner", "PATCH", {"owner": "prod"})
        self.assertEqual(code, 200)
        self.assertEqual(n["owner"]["id"], "prod")
        code, n = d.call("/kpi/on_time/comments", "POST", {"text": "Разобрать очередь на переплёте до пятницы"})
        self.assertEqual(code, 201)
        self.assertEqual(n["feed"][-1]["text"], "Разобрать очередь на переплёте до пятницы")
        self.assertEqual(d.call("/kpi/on_time/comments", "POST", {"text": "  "})[0], 422)
        self.assertEqual(d.call("/kpi/on_time/owner", "PATCH", {"owner": "nobody"})[0], 422)
        # ответственный в таблице KPI и в детализации
        _, p = d.call("/pulse")
        k = next(x for x in p["kpis"] if x["id"] == "on_time")
        self.assertEqual(k["responsible"]["name"], "Дмитрий Савич")
        self.assertGreaterEqual(k["comments_count"], 1)
        # руководитель видит комментарии к своему KPI, но не пишет; получает уведомление о назначении
        prod = self.api("prod")
        _, kd = prod.call("/kpi/on_time")
        self.assertEqual(kd["notes"]["owner"]["id"], "prod")
        self.assertFalse(kd["notes"]["can_edit"])
        self.assertEqual(prod.call("/kpi/on_time/comments", "POST", {"text": "Руководитель пробует"})[0], 403)
        self.assertEqual(prod.call("/kpi/on_time/owner", "PATCH", {"owner": "sales"})[0], 403)
        self.assertEqual(self.api("analyst").call("/kpi/on_time/comments", "POST", {"text": "Аналитик пробует"})[0], 403)
        _, al = prod.call("/alerts")
        self.assertTrue(any("назначены ответственным" in x["text"] for x in al["items"]))
        # чужой KPI недоступен вместе с комментариями
        self.assertEqual(self.api("sales").call("/kpi/on_time")[0], 403)
        _, au = self.api("analyst").call("/audit?per=200")
        acts = {(x["user"], x["action"], x["result"]) for x in au["items"]}
        self.assertIn(("director", "Комментарий к показателю", "успех"), acts)
        self.assertIn(("director", "Назначение ответственного", "успех"), acts)
        self.assertIn(("prod", "Комментарий к показателю", "отказано"), acts)

    def test_ot02_server_side_permissions(self):
        code, _ = self.api("analyst").call("/decisions", "POST", {"dept": "D-PROD", "title": "Аналитик пробует", "action": "Не должно сработать", "owner": "prod", "due": "2099-01-01", "priority": "Низкий"})
        self.assertEqual(code, 403)
        code, _ = self.api("prod").call("/decisions", "POST", {"dept": "D-PROD", "title": "Руководитель пробует", "action": "Не должно сработать", "owner": "prod", "due": "2099-01-01", "priority": "Низкий"})
        self.assertEqual(code, 403)
        self.assertEqual(self.api("prod").call("/quality")[0], 403)
        self.assertEqual(self.api("sales").call("/audit")[0], 403)

    # ---------------------------------------------------------------- сценарии 4 и 5
    def test_scenario4_forecast_4_weeks_and_deficit(self):
        code, f = self.api("prod").call("/forecast")
        self.assertEqual(code, 200)
        self.assertGreaterEqual(len(f["weeks"]), 4)
        self.assertIsNotNone(f["deficit_week"])
        self.assertTrue(f["method"])

    def test_scenario5_analyst_quality(self):
        _, q = self.api("analyst").call("/quality")
        st = {s["id"]: s["status"] for s in q["sources"]}
        self.assertEqual(st["1C"], "crit", "устаревшая выгрузка 1С обнаружена")
        self.assertTrue(any(g["count"] > 0 for g in q["gaps"]), "пропуски найдены")
        self.assertTrue(any(x["count"] > 0 for x in q["duplicates"]), "дубли найдены")
        self.assertTrue(any(r["status"] == "crit" and r["by_product"] for r in q["reconciliation"]), "расхождение сверки ERP ↔ 1С найдено")

    # ---------------------------------------------------------------- ОТ-05 / ОТ-07 / данные
    def test_ot05_errors_are_readable(self):
        a = self.api("director")
        code, e = a.call("/pulse?period=1999-01")
        self.assertEqual(code, 400)
        self.assertIn("Нет данных", e["error"])
        code, e = a.call("/kpi/unknown")
        self.assertEqual(code, 404)
        code, e = a.call("/nope")
        self.assertEqual(code, 404)

    def test_data_auto_reload(self):
        """База перечитывается раз в 15 с: без изменений — не трогаем, при изменении — подменяем целиком."""
        self.assertEqual(server.DATA_REFRESH_SEC, int(os.environ.get("DATA_REFRESH_SEC", "15")))
        _, meta = self.api("director").call("/meta")
        self.assertEqual(meta["refresh_sec"], server.DATA_REFRESH_SEC)
        before = server.S.loaded_at
        self.assertFalse(server.reload_data(), "файлы не менялись — повторная загрузка не нужна")
        self.assertEqual(server.S.loaded_at, before)
        obj = server.S
        server.S.signature = ()  # имитируем изменение файлов базы
        self.assertTrue(server.reload_data())
        self.assertIs(server.S, obj, "объект хранилища тот же — обработчики видят новые данные")
        self.assertGreaterEqual(server.S.loaded_at, before)
        self.assertEqual(len(server.S.orders), server.S.meta["counts"]["orders"] + server.S.live_count)
        code, h = self.api("director").call("/health")
        self.assertEqual(code, 200)
        self.assertIsNone(h["reload_error"])

    def test_live_orders_simulation(self):
        """Каждые 15 с поступают новые заказы: они видны в KPI, сохраняются в базе и переживают перечитывание."""
        if server.now().date().isoformat() != server.S.meta["today"]:
            self.skipTest("набор данных сгенерирован на другую дату")
        d = self.api("director")
        _, p0 = d.call("/pulse?chart=orders")
        rev0 = next(k for k in p0["kpis"] if k["id"] == "revenue")["fact"]
        n0 = len(server.S.orders)
        added = server.simulate_tick(3)
        self.assertEqual(len(added), 3)
        self.assertEqual(len(server.S.orders), n0 + 3)
        _, p1 = d.call("/pulse?chart=orders")
        rev1 = next(k for k in p1["kpis"] if k["id"] == "revenue")["fact"]
        self.assertAlmostEqual(rev1 - rev0, sum(o["amount"] for o in added), places=1)
        code, card = d.call("/orders/" + added[0]["id"])
        self.assertEqual(code, 200, "новый заказ открывается в сквозной карточке")
        with open(server.LIVE_PATH, encoding="utf-8") as f:
            self.assertGreaterEqual(len(json.load(f)["orders"]), 3, "заказы записаны в базу")
        self.assertFalse(server.reload_data(), "свои изменения не вызывают полной перезагрузки")
        self.assertTrue(server.reload_data(force=True))
        self.assertIn(added[-1]["id"], server.S.order, "после перечитывания базы новые заказы на месте")
        # данные меняются у каждого: производство (этапы, выпуск) и продажи (воронка сайта)
        prod, sales = self.api("prod"), self.api("sales")
        _, pr0 = prod.call("/production")
        _, sa0 = sales.call("/sales")
        for _ in range(6):
            server.simulate_tick()
        _, pr1 = prod.call("/production")
        _, sa1 = sales.call("/sales")
        self.assertNotEqual([(s["output"], s["queue"]) for s in pr0["sections"]], [(s["output"], s["queue"]) for s in pr1["sections"]], "у производства меняются выпуск и очередь")
        self.assertNotEqual([f["value"] for f in sa0["funnel"]], [f["value"] for f in sa1["funnel"]], "у продаж меняется воронка")
        moved = dict(server.load_live(server.S.meta["today"])["updates"])
        self.assertTrue(moved, "смена этапов записана в базу")
        server.reload_data(force=True)
        oid, upd = next(iter(moved.items()))
        self.assertEqual(server.S.order[oid]["status"], upd["status"], "этапы сохраняются после перечитывания базы")

    def test_ot07_timezone_currency_and_volumes(self):
        S = server.S
        self.assertTrue(all(o["created_at"].endswith("+03:00") for o in S.orders[:200]))
        self.assertTrue(all(o["currency"] == "BYN" for o in S.orders[:200]))
        self.assertGreaterEqual(len(S.orders), 500)
        self.assertGreaterEqual(len({c["id"] for c in S.customers}), 200)
        self.assertGreaterEqual(len(S.tickets), 300)


if __name__ == "__main__":
    unittest.main(verbosity=2)
