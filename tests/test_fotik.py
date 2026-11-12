"""
Тесты ИИ-ассистента «Фотик». Claude API подменяется локальным заглушечным сервером,
поэтому ключ и интернет не нужны; проверяется, что сервер отправляет и чего не отправляет.
"""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server  # noqa: E402
from test_acceptance import Api  # noqa: E402

FAKE_KEY = "sk-ant-test-key-never-leaks"
CAPTURED = []


class MockClaude(BaseHTTPRequestHandler):
    status = 200

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        CAPTURED.append({"headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
        if MockClaude.status != 200:
            self.send_response(MockClaude.status)
            self.end_headers()
            return
        out = json.dumps({"content": [{"type": "text", "text": "Оборот за неделю вырос."}], "usage": {"input_tokens": 10, "output_tokens": 5}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


class Fotik(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.STATE = tempfile.mkdtemp(prefix="fotoprint-fotik-")
        server.LIVE_PATH = os.path.join(server.STATE, "live_orders.json")
        server.S.load()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.mock = ThreadingHTTPServer(("127.0.0.1", 0), MockClaude)
        threading.Thread(target=cls.mock.serve_forever, daemon=True).start()
        server.FOTIK_API_URL = f"http://127.0.0.1:{cls.mock.server_address[1]}/v1/messages"
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.mock.shutdown()
        os.environ.pop("ANTHROPIC_API_KEY", None)

    def setUp(self):
        CAPTURED.clear()
        MockClaude.status = 200
        server.FOTIK_RATE.clear()
        os.environ["ANTHROPIC_API_KEY"] = FAKE_KEY

    def ask(self, who="director", **body):
        return Api(self.base).login(who).call("/fotik", "POST", {"question": "Что изменилось за неделю?", **body})

    def test_answer_and_request_shape(self):
        hist = [{"role": "assistant", "content": "Привет!"}, {"role": "user", "content": "Как дела?"}, {"role": "assistant", "content": "Всё в норме."}]
        code, data = self.ask(filters={"period": "last28", "dept": "all", "product": "PRD-BOOK"}, history=hist)
        self.assertEqual(code, 200, data)
        self.assertEqual(data["answer"], "Оборот за неделю вырос.")
        self.assertEqual(data["context"]["product"], "Фотокниги")
        req = CAPTURED[0]
        self.assertEqual(req["headers"]["x-api-key"], FAKE_KEY)
        self.assertIn("Ты Фотик, аналитик этого дашборда", req["body"]["system"])
        msgs = req["body"]["messages"]
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant", "user"])  # приветствие ассистента отброшено
        self.assertEqual(msgs[-1]["content"], "Что изменилось за неделю?")
        ctx = json.loads(req["body"]["system"].split("Данные дашборда (JSON):\n", 1)[1])
        self.assertEqual(ctx["filters"]["period"], "Последние 4 недели")
        for m in ("revenue", "orders", "output"):
            tr = ctx["trend"][m]
            lo, hi = tr["next_30_days"]["range_80"]
            self.assertLessEqual(lo, tr["next_30_days"]["regression"])
            self.assertGreaterEqual(hi, tr["next_30_days"]["regression"])
            self.assertLessEqual(len(ctx["weekly_series_8w"][m]), 8)  # длинные ряды — агрегатами

    def test_key_never_returned(self):
        api = Api(self.base).login("director")
        for path in ("/fotik", "/fotik/context", "/meta"):
            code, data = api.call(path)
            self.assertEqual(code, 200)
            self.assertNotIn(FAKE_KEY, json.dumps(data))
        code, data = self.ask()
        self.assertNotIn(FAKE_KEY, json.dumps(data))
        with open(os.path.join(server.STATE, "audit.jsonl"), encoding="utf-8") as f:
            self.assertNotIn(FAKE_KEY, f.read())

    def test_locked_kpis_not_sent(self):
        self.ask("prod")
        ctx = json.loads(CAPTURED[0]["body"]["system"].split("Данные дашборда (JSON):\n", 1)[1])
        # руководителю производства передаются только KPI производства, без чужих рядов
        self.assertEqual({k["dept"] for k in ctx["kpis"]}, {"Производство"})
        self.assertNotIn("Валовая маржа", [k["name"] for k in ctx["kpis"]])
        self.assertNotIn("Валовая маржа", [k["name"] for k in ctx["week"]["kpis"]])
        self.assertNotIn("revenue", ctx["weekly_series_8w"])
        self.assertIsNotNone(ctx["capacity_forecast"])
        CAPTURED.clear()
        self.ask("sales")
        ctx = json.loads(CAPTURED[0]["body"]["system"].split("Данные дашборда (JSON):\n", 1)[1])
        self.assertNotIn("Затраты на перепечатку", [k["name"] for k in ctx["kpis"]])
        self.assertIsNone(ctx["capacity_forecast"])
        self.assertIsNone(ctx["capacity_load_by_section"])

    def test_errors(self):
        os.environ.pop("ANTHROPIC_API_KEY")
        code, data = self.ask()
        self.assertEqual(code, 503)
        self.assertIn("ANTHROPIC_API_KEY", data["error"])
        os.environ["ANTHROPIC_API_KEY"] = FAKE_KEY
        MockClaude.status = 401
        code, data = self.ask()
        self.assertEqual(code, 502)
        code, data = self.ask(question="  ")
        self.assertEqual(code, 422)
        code, data = Api(self.base).call("/fotik", "POST", {"question": "x"})
        self.assertEqual(code, 401)


if __name__ == "__main__":
    unittest.main()
