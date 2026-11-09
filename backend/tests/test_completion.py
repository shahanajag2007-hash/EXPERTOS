"""
Accounts, saved conversations, file uploads and document analysis, context
management, image routing and request limits. AI providers are mocked; every
test gets an empty temporary database and upload folder.

Run from the backend directory:
    python -m unittest discover -s tests -v
"""
import _testenv  # noqa: F401  (must come before app imports)
import io
import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from unittest import mock

import app as app_module
from app import app
from providers.provider_router import ProviderRouter
from services import context, files
from services.errors import AIServiceError, TIMEOUT, UNSUPPORTED

RECOMMENDATION = {"title": "T", "recommendation": "Use Postgres", "description": "D", "metrics": []}
ANALYSIS = {k: f"{k} text" for k in
            ("architecture", "tech_stack", "database", "security", "deployment", "recommendation")}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def minimal_pdf(text):
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return out.getvalue()


def office_zip(entries):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, body in entries.items():
            zf.writestr(name, body)
    return out.getvalue()


DOCX = office_zip({"word/document.xml": (
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
    "<w:p><w:r><w:t>Revenue grew 40% in Q3.</w:t></w:r></w:p></w:body></w:document>")})

XLSX = office_zip({
    "xl/workbook.xml": (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sales" sheetId="1" r:id="rId1"/></sheets></workbook>'),
    "xl/_rels/workbook.xml.rels": (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>'),
    "xl/sharedStrings.xml": (
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<si><t>Region</t></si><si><t>North</t></si></sst>"),
    "xl/worksheets/sheet1.xml": (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        '<row><c t="s"><v>0</v></c><c><v>2024</v></c></row>'
        '<row><c t="s"><v>1</v></c><c><v>1500</v></c></row></sheetData></worksheet>'),
})


class Base(unittest.TestCase):

    def setUp(self):
        self.db_path = _testenv.fresh_database()
        self.upload_dir = tempfile.mkdtemp(dir=os.path.dirname(self.db_path))
        os.environ["EXPERTOS_UPLOAD_DIR"] = self.upload_dir
        self.addCleanup(os.environ.pop, "EXPERTOS_UPLOAD_DIR", None)
        self.client = _testenv.client(app)
        for limiter in (app_module.ai_limiter, app_module.login_limiter, app_module.register_limiter,
                        app_module.upload_limiter):
            limiter.hits.clear()

    def rows(self, sql, *params):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def upload(self, name, data, client=None, conversation_id=None):
        form = {"files": (io.BytesIO(data), name)}
        if conversation_id:
            form["conversation_id"] = conversation_id
        return (client or self.client).post("/files", data=form, content_type="multipart/form-data")

    def start_consultation(self, client=None, prompt="A booking app", file_ids=None):
        with mock.patch("services.ai_provider.generate", return_value=json.dumps(ANALYSIS)):
            res = (client or self.client).post("/analyze", json={"prompt": prompt, "file_ids": file_ids or []})
        self.assertEqual(res.status_code, 200, res.get_json())
        return res.get_json()["conversation_id"]


# ─── Accounts ────────────────────────────────────────────────────────────────

class AccountTests(Base):

    def register(self, email="ana@example.com", password="correct horse", name="Ana", client=None):
        return (client or self.client).post("/auth/register", json={"email": email, "password": password,
                                                                    "name": name})

    def test_register_login_me_logout(self):
        res = self.register()
        self.assertEqual(res.status_code, 201)
        token = res.get_json()["token"]
        self.assertEqual(res.get_json()["user"]["email"], "ana@example.com")

        stored = self.rows("SELECT password_hash FROM users")[0][0]
        self.assertNotIn("correct horse", stored)

        me = self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.get_json()["user"]["name"], "Ana")

        login = self.client.post("/auth/login", json={"email": "ANA@example.com", "password": "correct horse"})
        self.assertEqual(login.status_code, 200)

        self.client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code, 401)

    def test_validation_and_duplicates(self):
        res = self.register(email="not-an-email", password="short")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(set(res.get_json()["fields"]), {"email", "password"})

        self.register()
        self.assertEqual(self.register().status_code, 409)

    def test_wrong_password_and_unknown_email_look_the_same(self):
        self.register()
        wrong = self.client.post("/auth/login", json={"email": "ana@example.com", "password": "wrong pass"})
        unknown = self.client.post("/auth/login", json={"email": "bob@example.com", "password": "wrong pass"})
        self.assertEqual((wrong.status_code, unknown.status_code), (401, 401))
        self.assertEqual(wrong.get_json()["error"], unknown.get_json()["error"])

    def test_invalid_session_is_401_not_silent_anonymous_access(self):
        res = self.client.get("/conversations", headers={"Authorization": "Bearer bogus"})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.get_json()["code"], "unauthorized")

    def test_signing_in_claims_this_browsers_conversations(self):
        conversation_id = self.start_consultation()
        token = self.register().get_json()["token"]

        # Same account from another browser sees the conversation.
        other_browser = _testenv.client(app, client_id="another-browser-0123456789abcdef")
        listed = other_browser.get("/conversations", headers={"Authorization": f"Bearer {token}"}).get_json()
        self.assertEqual([c["id"] for c in listed["conversations"]], [conversation_id])
        self.assertTrue(listed["signed_in"])

    def test_login_is_rate_limited(self):
        codes = [self.client.post("/auth/login", json={"email": "x@example.com", "password": "nope nope"}).status_code
                 for _ in range(11)]
        self.assertEqual(codes[-1], 429)


# ─── Start Consultation conversations ────────────────────────────────────────

class ConsultationConversationTests(Base):

    def chat(self, conversation_id, message, client=None, reply="Answer", file_ids=None):
        with mock.patch("services.consultation_engine.ask_ai", return_value=reply) as ask, \
             mock.patch("services.router.generate", return_value='{"switch": false}'):
            res = (client or self.client).post("/chat", json={
                "conversation_id": conversation_id, "message": message, "file_ids": file_ids or []})
        return res, ask

    def test_follow_ups_keep_context_and_persist(self):
        conversation_id = self.start_consultation()
        self.chat(conversation_id, "What should we build first?", reply="Postgres.")
        res, ask = self.chat(conversation_id, "Why?", reply="Because of transactions.")

        self.assertEqual(res.status_code, 200)
        history = ask.call_args.kwargs["history"]
        self.assertEqual([m["message"] for m in history], ["What should we build first?", "Postgres.", "Why?"])

        saved = self.client.get(f"/conversations/{conversation_id}").get_json()
        self.assertEqual(saved["report"], ANALYSIS)
        self.assertEqual([m["message"] for m in saved["messages"]],
                         ["What should we build first?", "Postgres.", "Why?", "Because of transactions."])

    def test_two_browsers_do_not_share_a_consultation(self):
        mine = self.start_consultation(prompt="My shop")
        other = _testenv.client(app, client_id="someone-else-0123456789abcdef")
        theirs = self.start_consultation(client=other, prompt="Their clinic")

        self.chat(mine, "Mine?")
        self.assertEqual(self.client.get(f"/conversations/{theirs}").status_code, 404)
        res, _ = self.chat(mine, "Hijack", client=other)
        self.assertEqual(res.status_code, 404)
        self.assertEqual(len(other.get(f"/conversations/{theirs}").get_json()["messages"]), 0)

    def test_failed_answer_stores_nothing(self):
        conversation_id = self.start_consultation()
        with mock.patch("services.consultation_engine.ask_ai", side_effect=AIServiceError("down", TIMEOUT)), \
             mock.patch("services.router.generate", return_value='{"switch": false}'):
            res = self.client.post("/chat", json={"conversation_id": conversation_id, "message": "Hello?"})
        self.assertEqual(res.status_code, 503)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM conversation_messages")[0][0], 0)

    def test_handover_is_saved_and_new_expert_continues(self):
        conversation_id = self.start_consultation()
        res, _ = self.chat(conversation_id, "Can Sarah join?", reply="Security view.")
        self.assertTrue(res.get_json()["switch"])
        saved = self.client.get(f"/conversations/{conversation_id}").get_json()
        self.assertEqual(saved["active_expert"], "Security Expert")
        self.assertEqual(saved["messages"][-1]["expert_key"], "Security Expert")

    def test_chat_requires_a_known_conversation(self):
        res, _ = self.chat("missing", "Hi")
        self.assertEqual(res.status_code, 404)

    def test_list_and_delete(self):
        conversation_id = self.start_consultation()
        listed = self.client.get("/conversations?kind=quick_consultation").get_json()["conversations"]
        self.assertEqual(listed[0]["title"], "A booking app")
        self.assertEqual(self.client.delete(f"/conversations/{conversation_id}").status_code, 200)
        self.assertEqual(self.client.get(f"/conversations/{conversation_id}").status_code, 404)


# ─── Expert Room conversations ───────────────────────────────────────────────

class ExpertRoomConversationTests(Base):

    def recommend(self, conversation_id=None, file_ids=None, description="Inventory system"):
        body = {"expert": "Database Engineer", "answers": {"description": description, "project_name": "Stock"},
                "file_ids": file_ids or []}
        if conversation_id:
            body["conversation_id"] = conversation_id
        with mock.patch("services.expert_recommendation.generate", return_value=json.dumps(RECOMMENDATION)) as gen:
            res = self.client.post("/expert/recommend", json=body)
        self.assertEqual(res.status_code, 200, res.get_json())
        return res.get_json(), gen

    def test_recommendation_creates_a_conversation_and_revising_reuses_it(self):
        first, _ = self.recommend()
        second, _ = self.recommend(conversation_id=first["conversation_id"], description="Inventory v2")
        self.assertEqual(first["conversation_id"], second["conversation_id"])
        saved = self.client.get(f"/conversations/{first['conversation_id']}").get_json()
        self.assertEqual(saved["answers"]["description"], "Inventory v2")
        self.assertEqual(saved["report"]["recommendation"], "Use Postgres")
        self.assertEqual(saved["title"], "Stock")

    def test_streamed_chat_uses_saved_history_and_saves_the_exchange(self):
        conversation_id = self.recommend()[0]["conversation_id"]
        seen = []

        def fake_stream(prompt, **kwargs):
            seen.append(prompt)
            yield "Index "
            yield "the SKU."

        with mock.patch("services.ai_provider.stream", side_effect=fake_stream):
            for question in ("How to index?", "And for search?"):
                res = self.client.post("/expert/chat/stream", json={
                    "expert": "Database Engineer", "conversation_id": conversation_id, "message": question,
                    "history": [{"sender": "user", "message": "FORGED CLIENT HISTORY"}],
                })
                self.assertIn(b'"saved": true', res.data)

        self.assertNotIn("FORGED CLIENT HISTORY", seen[1])
        self.assertIn("How to index?", seen[1])
        self.assertIn("Use Postgres", seen[1])
        messages = self.client.get(f"/conversations/{conversation_id}").get_json()["messages"]
        self.assertEqual([m["message"] for m in messages],
                         ["How to index?", "Index the SKU.", "And for search?", "Index the SKU."])

    def test_conversation_is_used_only_in_its_own_room(self):
        conversation_id = self.recommend()[0]["conversation_id"]
        res = self.client.post("/expert/chat", json={"expert": "Security Expert",
                                                     "conversation_id": conversation_id, "message": "Hi"})
        self.assertEqual(res.status_code, 400)
        with mock.patch("services.expert_recommendation.generate", return_value=json.dumps(RECOMMENDATION)):
            res = self.client.post("/expert/recommend", json={
                "expert": "Security Expert", "conversation_id": conversation_id,
                "answers": {"description": "x"}})
        self.assertEqual(res.status_code, 400)

    def test_list_filters_by_expert(self):
        self.recommend()
        self.assertEqual(len(self.client.get("/conversations?expert=Database%20Engineer").get_json()["conversations"]), 1)
        self.assertEqual(len(self.client.get("/conversations?expert=Security%20Expert").get_json()["conversations"]), 0)


# ─── Files ───────────────────────────────────────────────────────────────────

class UploadTests(Base):

    def test_supported_formats_are_extracted(self):
        cases = {
            "notes.md": (b"# Goals\nShip in June", "Ship in June"),
            "report.pdf": (minimal_pdf("Churn is 12 percent"), "Churn is 12 percent"),
            "plan.docx": (DOCX, "Revenue grew 40% in Q3."),
            "sales.xlsx": (XLSX, "North, 1500"),
            "code.zip": (office_zip({"src/app.py": "print('hello')", "logo.bin": "\x00\x01"}), "print('hello')"),
        }
        for name, (data, expected) in cases.items():
            with self.subTest(name):
                res = self.upload(name, data)
                self.assertEqual(res.status_code, 201, res.get_json())
                file_id = res.get_json()["files"][0]["id"]
                text = self.rows("SELECT extracted_text FROM uploaded_files WHERE id = ?", file_id)[0][0]
                self.assertIn(expected, text)

    def test_image_upload(self):
        info = self.upload("screen.png", PNG).get_json()["files"][0]
        self.assertEqual((info["kind"], info["content_type"]), ("image", "image/png"))

    def test_invalid_files_are_rejected_with_reasons(self):
        cases = {
            "virus.exe": (b"MZ....", "isn't supported"),
            "fake.pdf": (b"hello", "not a valid PDF"),
            "fake.png": (b"hello", "not a valid image"),
            "empty.txt": (b"", "empty"),
            "old.doc": (b"\xd0\xcf\x11\xe0", ".docx"),
            "binary.txt": (b"abc\x00def", "binary"),
        }
        for name, (data, message) in cases.items():
            with self.subTest(name):
                res = self.upload(name, data)
                self.assertEqual(res.status_code, 400)
                self.assertIn(message, res.get_json()["error"])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM uploaded_files")[0][0], 0)
        self.assertEqual(os.listdir(self.upload_dir), [])

    def test_oversized_file(self):
        with mock.patch.object(files, "MAX_FILE_BYTES", 100):
            res = self.upload("big.txt", b"a" * 200)
        self.assertEqual(res.status_code, 400)
        self.assertIn("larger than", res.get_json()["error"])

    def test_no_files(self):
        res = self.client.post("/files", data={}, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)

    def test_files_are_private_to_their_owner(self):
        file_id = self.upload("notes.txt", b"secret plan").get_json()["files"][0]["id"]
        other = _testenv.client(app, client_id="someone-else-0123456789abcdef")

        self.assertEqual(other.delete(f"/files/{file_id}").status_code, 404)
        with mock.patch("services.ai_provider.generate", return_value=json.dumps(ANALYSIS)):
            res = other.post("/analyze", json={"prompt": "x", "file_ids": [file_id]})
        self.assertEqual(res.status_code, 404)

        self.assertEqual(self.client.delete(f"/files/{file_id}").status_code, 200)
        self.assertEqual(os.listdir(self.upload_dir), [])

    def test_document_content_reaches_the_expert(self):
        file_id = self.upload("brief.txt", b"The client needs HIPAA compliance.").get_json()["files"][0]["id"]
        with mock.patch("services.ai_provider.generate", return_value=json.dumps(ANALYSIS)) as gen:
            res = self.client.post("/analyze", json={"prompt": "Clinic app", "file_ids": [file_id]})
        self.assertEqual(res.status_code, 200)
        prompt = gen.call_args.args[0]
        self.assertIn("--- FILE: brief.txt ---", prompt)
        self.assertIn("HIPAA compliance", prompt)

        # Attached to the conversation, so later follow-ups still see it.
        conversation_id = res.get_json()["conversation_id"]
        with mock.patch("services.ai_provider.generate", return_value="Noted") as gen, \
             mock.patch("services.router.generate", return_value='{"switch": false}'):
            self.client.post("/chat", json={"conversation_id": conversation_id, "message": "Any compliance needs?"})
        self.assertIn("HIPAA compliance", gen.call_args.args[0])

    def test_images_are_sent_to_the_ai_as_images(self):
        file_id = self.upload("screen.png", PNG).get_json()["files"][0]["id"]
        with mock.patch("services.expert_recommendation.generate", return_value=json.dumps(RECOMMENDATION)) as gen:
            self.client.post("/expert/recommend", json={
                "expert": "Design Advisor", "answers": {"description": "Review my signup page"},
                "file_ids": [file_id]})
        images = gen.call_args.kwargs["images"]
        self.assertEqual(images, [{"mime": "image/png", "data": PNG}])
        self.assertIn("IMAGE 1: screen.png", gen.call_args.args[0])

    def test_upload_into_a_conversation(self):
        conversation_id = self.start_consultation()
        self.upload("extra.csv", b"a,b\n1,2", conversation_id=conversation_id)
        saved = self.client.get(f"/conversations/{conversation_id}").get_json()
        self.assertEqual([f["filename"] for f in saved["files"]], ["extra.csv"])

        other = _testenv.client(app, client_id="someone-else-0123456789abcdef")
        self.assertEqual(self.upload("x.txt", b"x", client=other, conversation_id=conversation_id).status_code, 404)


# ─── Context management ──────────────────────────────────────────────────────

class ContextTests(unittest.TestCase):

    def test_long_history_is_condensed_not_silently_dropped(self):
        history = [{"type": "chat", "sender": "user" if i % 2 == 0 else "expert",
                    "expert": {"name": "Alex"}, "message": f"message {i} " + "x" * 500} for i in range(200)]
        text = context.format_history(history)
        self.assertIn("message 199", text)                 # newest kept in full
        self.assertIn("Earlier in the conversation (condensed)", text)
        self.assertIn("earliest message(s) of this conversation are not shown", text)
        self.assertLess(len(text), context.HISTORY_BUDGET_CHARS + 2000)

    def test_short_history_is_verbatim(self):
        text = context.format_history([{"type": "chat", "sender": "user", "message": "Hello"}])
        self.assertEqual(text, "User: Hello")

    def test_long_documents_are_marked_as_cut(self):
        row = {"kind": "document", "filename": "big.txt", "extracted_text": "y" * 100_000, "extraction_note": None}
        text = context.documents_section([row])
        self.assertIn("only the first 40,000 of 100,000 characters are included", text)


# ─── Providers ───────────────────────────────────────────────────────────────

def provider(name, vision=False, result="ok"):
    def generate(prompt, max_tokens=None, temperature=None, images=None):
        if isinstance(result, Exception):
            raise result
        return f"{result} from {name}"
    return {"name": name, "generate": generate, "enabled": True, "vision": vision}


class ProviderImageTests(unittest.TestCase):

    def router(self, *providers):
        router = ProviderRouter()
        router.providers = list(providers)
        return router

    def test_images_skip_text_only_providers(self):
        router = self.router(provider("Groq"), provider("Gemini", vision=True))
        with mock.patch("providers.provider_router.metrics.record_ai_call"):
            self.assertEqual(router.generate("q", images=[{"mime": "image/png", "data": PNG}]), "ok from Gemini")
            self.assertEqual(router.generate("q"), "ok from Groq")

    def test_no_vision_provider_gives_a_clear_error(self):
        router = self.router(provider("Groq"), provider("Ollama"))
        with mock.patch("providers.provider_router.metrics.record_ai_call"), \
             self.assertRaises(AIServiceError) as ctx:
            router.generate("q", images=[{"mime": "image/png", "data": PNG}])
        self.assertEqual(ctx.exception.category, UNSUPPORTED)
        self.assertIn("can read images", str(ctx.exception))

    def test_real_failure_is_reported_over_vision_skips(self):
        router = self.router(provider("Groq"), provider("Gemini", vision=True, result=TimeoutError("slow")))
        with mock.patch("providers.provider_router.metrics.record_ai_call"), \
             self.assertRaises(AIServiceError) as ctx:
            router.generate("q", images=[{"mime": "image/png", "data": PNG}])
        self.assertEqual(ctx.exception.category, TIMEOUT)

    def test_cut_off_stream_is_marked(self):
        from services import openrouter_client as oc

        class Chunk:
            def __init__(self, text, reason=None):
                delta = type("D", (), {"content": text})()
                self.choices = [type("C", (), {"delta": delta, "finish_reason": reason})()]
                self.model_extra = {}

        with mock.patch.object(oc, "OPENROUTER_API_KEY", "k"), \
             mock.patch.object(oc._client.chat.completions, "create",
                               return_value=iter([Chunk("Part one"), Chunk("", "length")])):
            text = "".join(oc.stream("q"))
        self.assertTrue(text.endswith(oc.TRUNCATION_NOTE))


# ─── Limits ──────────────────────────────────────────────────────────────────

class LimitTests(Base):

    def test_ai_requests_are_rate_limited(self):
        with mock.patch.object(app_module.ai_limiter, "limit", 2), \
             mock.patch("services.ai_provider.generate", return_value=json.dumps(ANALYSIS)):
            codes = [self.client.post("/analyze", json={"prompt": "x"}).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])

    def test_requests_without_a_browser_id_cannot_create_conversations(self):
        anonymous = _testenv.client(app, client_id=None)
        res = anonymous.post("/analyze", json={"prompt": "x"})
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
