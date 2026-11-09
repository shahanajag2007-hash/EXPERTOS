"""
Uploaded files: validation, private storage and text extraction.

Supported:
- Documents: PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx), ZIP
  archives (their text files are read), and plain-text formats (txt, md, csv,
  json, code, config...). The extracted text is what the experts read.
- Images (PNG, JPEG, WebP, GIF): sent as images to AI models that can see
  them (see providers/provider_router.py).

Files are stored under backend/data/uploads with random names, are never
served back to browsers, and can only be used or deleted by their owner
(services/auth.py). The file type is checked from its contents, not only its
name. Anything unsupported is rejected with a message saying so.
"""
import io
import os
import re
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from services import db
from services.consultations import Forbidden, InvalidInput, NotFound

MAX_FILE_BYTES = int(os.getenv("UPLOAD_MAX_MB", "10")) * 1024 * 1024
MAX_FILES_PER_REQUEST = 5
MAX_FILES_PER_OWNER = 200
# Text kept per file. Long documents are cut here and the cut is recorded.
MAX_EXTRACTED_CHARS = 200_000
MAX_PDF_PAGES = 150
MAX_SHEET_ROWS = 2000
MAX_ZIP_MEMBERS = 60
MAX_ZIP_TEXT_BYTES = 5 * 1024 * 1024

TEXT_EXTENSIONS = {
    "txt", "md", "markdown", "csv", "tsv", "json", "log", "yaml", "yml", "xml", "html", "htm",
    "ini", "toml", "cfg", "conf", "sql", "py", "js", "jsx", "ts", "tsx", "java", "kt", "c", "h",
    "cpp", "hpp", "cs", "go", "rs", "rb", "php", "swift", "sh", "ps1", "bat", "css", "scss",
    "vue", "svelte", "dart", "r", "scala", "gradle", "properties", "dockerfile", "tf", "graphql",
    "proto", "rst", "tex",
}
IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
               "webp": "image/webp", "gif": "image/gif"}
OFFICE_EXTENSIONS = {"docx", "xlsx", "pptx"}
SUPPORTED_DESCRIPTION = (
    "PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx), ZIP, text, Markdown, CSV, JSON, "
    "code files, and PNG/JPEG/WebP/GIF images"
)

_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def uploads_dir():
    path = Path(os.getenv("EXPERTOS_UPLOAD_DIR") or (db.db_path().parent / "uploads"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _extension(filename):
    name = filename.lower().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if name in ("dockerfile", "makefile"):
        return "dockerfile"
    return name.rsplit(".", 1)[-1] if "." in name else ""


def _safe_display_name(filename):
    name = re.split(r"[\\/]", filename or "")[-1].strip()
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    return (name or "file")[:200]


def _cap(text, note_parts):
    text = text.strip()
    if len(text) > MAX_EXTRACTED_CHARS:
        note_parts.append(f"only the first {MAX_EXTRACTED_CHARS:,} characters were kept")
        text = text[:MAX_EXTRACTED_CHARS]
    return text


# ─── Extractors ──────────────────────────────────────────────────────────────

def _decode_text(data):
    if b"\x00" in data[:8192]:
        raise InvalidInput("This file looks like a binary file, not text.")
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            if encoding == "utf-16" and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
                continue
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1")


def _pdf_text(data, notes):
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise InvalidInput("This PDF is password-protected. Upload an unprotected copy.") from exc
        pages = reader.pages
        total = len(pages)
        parts = []
        for index in range(min(total, MAX_PDF_PAGES)):
            text = pages[index].extract_text() or ""
            if text.strip():
                parts.append(f"[Page {index + 1}]\n{text.strip()}")
    except InvalidInput:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise InvalidInput("This PDF could not be read. It may be damaged.") from exc

    if total > MAX_PDF_PAGES:
        notes.append(f"only the first {MAX_PDF_PAGES} of {total} pages were read")
    if not parts:
        notes.append("no selectable text was found (it may be a scanned document)")
    return "\n\n".join(parts)


def _xml(zf, name):
    try:
        return ElementTree.fromstring(zf.read(name))
    except KeyError:
        return None


def _docx_text(zf):
    root = _xml(zf, "word/document.xml")
    if root is None:
        raise InvalidInput("This Word document could not be read.")
    lines = []
    for para in root.iter(f"{{{_NS['w']}}}p"):
        text = "".join(t.text or "" for t in para.iter(f"{{{_NS['w']}}}t"))
        if text.strip():
            lines.append(text)
    return "\n".join(lines)


def _xlsx_text(zf, notes):
    shared = []
    sst = _xml(zf, "xl/sharedStrings.xml")
    if sst is not None:
        for si in sst.findall("s:si", _NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['s']}}}t")))

    workbook = _xml(zf, "xl/workbook.xml")
    rels = _xml(zf, "xl/_rels/workbook.xml.rels")
    if workbook is None:
        raise InvalidInput("This Excel workbook could not be read.")
    targets = {}
    if rels is not None:
        for rel in rels:
            targets[rel.get("Id")] = rel.get("Target", "")

    out = []
    for sheet in workbook.iter(f"{{{_NS['s']}}}sheet"):
        target = targets.get(sheet.get(f"{{{_NS['r']}}}id"), "")
        path = "xl/" + target.lstrip("/").removeprefix("xl/") if target else ""
        root = _xml(zf, path) if path else None
        if root is None:
            continue
        out.append(f"[Sheet: {sheet.get('name')}]")
        rows = root.iter(f"{{{_NS['s']}}}row")
        for count, row in enumerate(rows):
            if count >= MAX_SHEET_ROWS:
                notes.append(f"only the first {MAX_SHEET_ROWS} rows of sheet '{sheet.get('name')}' were read")
                break
            cells = []
            for cell in row.findall("s:c", _NS):
                value = cell.find("s:v", _NS)
                inline = cell.find("s:is", _NS)
                if cell.get("t") == "s" and value is not None and value.text and value.text.isdigit():
                    index = int(value.text)
                    cells.append(shared[index] if index < len(shared) else "")
                elif inline is not None:
                    cells.append("".join(t.text or "" for t in inline.iter(f"{{{_NS['s']}}}t")))
                else:
                    cells.append(value.text if value is not None and value.text else "")
            if any(c.strip() for c in cells):
                out.append(", ".join(c.replace("\n", " ") for c in cells))
    return "\n".join(out)


def _pptx_text(zf):
    slides = sorted(
        (n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
        key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[-1]).group(1)),
    )
    out = []
    for number, name in enumerate(slides, 1):
        root = _xml(zf, name)
        texts = [t.text for t in root.iter(f"{{{_NS['a']}}}t") if t.text and t.text.strip()]
        if texts:
            out.append(f"[Slide {number}]\n" + "\n".join(texts))
    return "\n\n".join(out)


def _zip_text(zf, notes):
    out, read_bytes, skipped = [], 0, 0
    members = [m for m in zf.infolist() if not m.is_dir()]
    for member in members[:MAX_ZIP_MEMBERS]:
        ext = _extension(member.filename)
        if ext not in TEXT_EXTENSIONS or member.file_size > MAX_FILE_BYTES:
            skipped += 1
            continue
        if read_bytes + member.file_size > MAX_ZIP_TEXT_BYTES:
            notes.append("the archive's text limit was reached; later files were not read")
            break
        try:
            text = _decode_text(zf.read(member))
        except (InvalidInput, RuntimeError, zipfile.BadZipFile):
            skipped += 1
            continue
        read_bytes += member.file_size
        out.append(f"[File: {member.filename}]\n{text.strip()}")
    if len(members) > MAX_ZIP_MEMBERS:
        notes.append(f"only the first {MAX_ZIP_MEMBERS} of {len(members)} files in the archive were checked")
    if skipped:
        notes.append(f"{skipped} non-text file(s) in the archive were skipped")
    listing = "Archive contents:\n" + "\n".join(f"- {m.filename}" for m in members[:200])
    return listing + ("\n\n" + "\n\n".join(out) if out else "")


def _image_type(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def extract(filename, data):
    """
    Validate a file and extract its text. Returns
    (kind, content_type, text or None, note or None). Raises InvalidInput for
    unsupported, empty, oversized or unreadable files.
    """
    if not data:
        raise InvalidInput(f"{filename} is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise InvalidInput(f"{filename} is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")

    ext = _extension(filename)
    notes = []

    if ext in IMAGE_TYPES:
        content_type = _image_type(data)
        if content_type is None:
            raise InvalidInput(f"{filename} is not a valid image file.")
        return "image", content_type, None, None

    if ext == "pdf":
        if not data.startswith(b"%PDF"):
            raise InvalidInput(f"{filename} is not a valid PDF file.")
        text = _pdf_text(data, notes)
        return "document", "application/pdf", _cap(text, notes), "; ".join(notes) or None

    if ext in OFFICE_EXTENSIONS or ext == "zip":
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
            if ext == "docx":
                text, ctype = _docx_text(zf), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            elif ext == "xlsx":
                text, ctype = _xlsx_text(zf, notes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            elif ext == "pptx":
                text, ctype = _pptx_text(zf), "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            else:
                text, ctype = _zip_text(zf, notes), "application/zip"
        except (zipfile.BadZipFile, ElementTree.ParseError, RuntimeError) as exc:
            raise InvalidInput(f"{filename} could not be read. It may be damaged or password-protected.") from exc
        if not text.strip():
            notes.append("no text was found in this file")
        return "document", ctype, _cap(text, notes), "; ".join(notes) or None

    if ext in TEXT_EXTENSIONS:
        try:
            text = _decode_text(data)
        except InvalidInput as exc:
            raise InvalidInput(f"{filename} {str(exc)[0].lower()}{str(exc)[1:]}") from exc
        if not text.strip():
            raise InvalidInput(f"{filename} contains no text.")
        return "document", "text/plain", _cap(text, notes), "; ".join(notes) or None

    if ext in ("doc", "xls", "ppt"):
        raise InvalidInput(
            f"{filename} uses an old Office format. Save it as .{ext}x (or PDF) and upload that instead."
        )
    raise InvalidInput(f"{filename}: this file type isn't supported. Supported: {SUPPORTED_DESCRIPTION}.")


# ─── Storage ─────────────────────────────────────────────────────────────────

def public(row):
    return {
        "id": row["id"],
        "filename": row["filename"],
        "size_bytes": row["size_bytes"],
        "kind": row["kind"],
        "content_type": row["content_type"],
        "characters": len(row["extracted_text"] or ""),
        "note": row["extraction_note"],
        "conversation_id": row["conversation_id"],
        "created_at": row["created_at"],
    }


def save_upload(owner, filename, data, conversation_id=None):
    filename = _safe_display_name(filename)
    kind, content_type, text, note = extract(filename, data)

    with db.connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM uploaded_files WHERE (user_id IS NOT NULL AND user_id = ?)"
            " OR (user_id IS NULL AND client_hash = ?)",
            (owner.user_id, owner.client_hash),
        ).fetchone()[0]
    if count >= MAX_FILES_PER_OWNER:
        raise InvalidInput("You have reached the upload limit. Remove some files and try again.")

    file_id = str(uuid.uuid4())
    storage_name = uuid.uuid4().hex
    path = uploads_dir() / storage_name
    path.write_bytes(data)

    user_id, client_hash = owner.columns()
    try:
        with db.connection(write=True) as conn:
            conn.execute(
                "INSERT INTO uploaded_files (id, user_id, client_hash, conversation_id, filename, content_type,"
                " size_bytes, kind, storage_name, extracted_text, extraction_note, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (file_id, user_id, client_hash, conversation_id, filename, content_type, len(data), kind,
                 storage_name, text, note, db.utc_now()),
            )
            row = conn.execute("SELECT * FROM uploaded_files WHERE id = ?", (file_id,)).fetchone()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return public(row)


def get_owned(owner, file_ids):
    """Rows for file_ids, all of which must belong to owner."""
    ids = [i for i in dict.fromkeys(file_ids or []) if isinstance(i, str) and i]
    if not ids:
        return []
    if len(ids) > 20:
        raise InvalidInput("Attach at most 20 files to one request.")
    with db.connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM uploaded_files WHERE id IN ({','.join('?' * len(ids))})", ids
        ).fetchall()
    by_id = {r["id"]: r for r in rows}
    out = []
    for file_id in ids:
        row = by_id.get(file_id)
        if row is None or not owner.owns(row):
            raise NotFound("One of the attached files could not be found. Upload it again.")
        out.append(row)
    return out


def attach_to_conversation(owner, file_ids, conversation_id):
    rows = get_owned(owner, file_ids)
    if not rows:
        return
    with db.connection(write=True) as conn:
        conn.executemany(
            "UPDATE uploaded_files SET conversation_id = ? WHERE id = ? AND conversation_id IS NULL",
            [(conversation_id, r["id"]) for r in rows],
        )


def list_for_conversation(conversation_id):
    with db.connection() as conn:
        return conn.execute(
            "SELECT * FROM uploaded_files WHERE conversation_id = ? ORDER BY created_at", (conversation_id,)
        ).fetchall()


def delete(owner, file_id):
    with db.connection(write=True) as conn:
        row = conn.execute("SELECT * FROM uploaded_files WHERE id = ?", (file_id,)).fetchone()
        if row is None or not owner.owns(row):
            raise NotFound("This file could not be found.")
        conn.execute("DELETE FROM uploaded_files WHERE id = ?", (file_id,))
    (uploads_dir() / row["storage_name"]).unlink(missing_ok=True)


def delete_rows_files(rows):
    for row in rows:
        (uploads_dir() / row["storage_name"]).unlink(missing_ok=True)


def image_bytes(row):
    try:
        return (uploads_dir() / row["storage_name"]).read_bytes()
    except OSError as exc:
        raise Forbidden(f"{row['filename']} is no longer available. Upload it again.") from exc
