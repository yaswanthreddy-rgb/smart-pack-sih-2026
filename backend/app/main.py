import os
import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

BASE = Path(__file__).resolve().parent.parent
UPLOADS = BASE / "data" / "uploads"
REPORTS = BASE / "reports"
ANNOTATED = BASE / "data" / "annotated"
for p in (UPLOADS, REPORTS, ANNOTATED):
    p.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE / 'smartpack.db'}")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

JWT_SECRET = os.getenv("JWT_SECRET", "change-this-secret-in-production")
JWT_ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), default="INSPECTOR")

class Inspection(Base):
    __tablename__ = "inspections"
    id = Column(Integer, primary_key=True)
    inspection_code = Column(String(80), unique=True, nullable=False)
    product_name = Column(String(255), default="Packaged Commodity")
    category = Column(String(80), default="Unknown")
    language = Column(String(30), default="en")
    status = Column(String(50), nullable=False)
    score = Column(Float, default=0)
    ocr_confidence = Column(Float, default=0)
    raw_text = Column(Text, default="")
    fields_json = Column(Text, default="{}")
    checks_json = Column(Text, default="[]")
    violations_json = Column(Text, default="[]")
    evidence_json = Column(Text, default="[]")
    image_path = Column(String(500))
    annotated_path = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100), default="demo-inspector")

Base.metadata.create_all(engine)

def seed_admin():
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(username="inspector").first():
            db.add(User(username="inspector", password_hash=pwd_context.hash("Inspector@123"), role="INSPECTOR"))
            db.commit()
    finally:
        db.close()
seed_admin()

app = FastAPI(title="Smart Pack - Legal Metrology Compliance API", version="2.0.0")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
app.mount("/annotated", StaticFiles(directory=ANNOTATED), name="annotated")
FRONTEND_DIST = BASE.parent / "frontend" / "dist"

ocr_cache = {}

class LoginRequest(BaseModel):
    username: str
    password: str
class RegisterRequest(BaseModel):
    username: str
    password: str


def token_for(user: User):
    payload = {"sub": user.username, "role": user.role, "exp": datetime.utcnow() + timedelta(hours=12)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def current_user(authorization: Optional[str] = Header(default=None)):
    if os.getenv("DEMO_MODE", "false").lower() == "true" and not authorization:
        return {"username": "demo-inspector", "role": "INSPECTOR"}
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authentication required")
    token = authorization.split(" ", 1)[1]
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {"username": data["sub"], "role": data.get("role", "INSPECTOR")}
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")


def get_ocr(lang: str):
    key = lang if lang in {"en", "hi", "ta", "te"} else "en"
    if key in ocr_cache:
        return ocr_cache[key]
    try:
        from paddleocr import PaddleOCR
        # PP-OCRv5 supports English plus the selected Indian language.
        engine = PaddleOCR(lang=key)
        ocr_cache[key] = engine
        return engine
    except Exception:
        ocr_cache[key] = False
        return False


def preprocess_image(path: Path):
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError("Unable to read image")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoise = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(denoise)
    out = path.with_name(path.stem + "_preprocessed.jpg")
    cv2.imwrite(str(out), enhanced)
    return out, img


def extract_ocr(path: Path, lang: str):
    ocr = get_ocr(lang)
    if not ocr:
        return "", 0.0, []
    try:
        pre, _ = preprocess_image(path)
        result = ocr.predict(str(pre))
        texts, scores, boxes = [], [], []
        for res in result:
            data = getattr(res, "json", None)
            if callable(data):
                data = data()
            if isinstance(data, str):
                data = json.loads(data)
            if isinstance(data, dict):
                payload = data.get("res", data)
                texts.extend([str(x) for x in (payload.get("rec_texts") or [])])
                scores.extend([float(x) for x in (payload.get("rec_scores") or [])])
                boxes.extend(payload.get("rec_boxes") or [])
        lines = []
        for idx, text in enumerate(texts):
            score = scores[idx] if idx < len(scores) else 0.0
            box = boxes[idx] if idx < len(boxes) else None
            lines.append({"text": text, "confidence": round(score, 4), "box": box})
        joined = "\n".join(texts)
        confidence = sum(scores) / len(scores) if scores else 0.0
        return joined, float(confidence), lines
    except Exception:
        return "", 0.0, []


def detect_category(text: str):
    t = text.lower()
    categories = {
        "Food": ["food", "rice", "flour", "wheat", "biscuit", "snack", "sugar", "salt", "spice"],
        "Beverage": ["juice", "drink", "water", "beverage", "tea", "coffee", "milk"],
        "Cosmetics": ["shampoo", "soap", "cream", "cosmetic", "lotion", "face wash"],
        "Household": ["detergent", "cleaner", "dishwash", "toilet", "floor cleaner"],
        "Personal Care": ["toothpaste", "toothbrush", "sanitary", "body wash"],
    }
    for name, words in categories.items():
        if any(w in t for w in words):
            return name
    return "General Packaged Commodity"


def field(patterns, text):
    for pattern in patterns:
        m = re.search(pattern, text, re.I | re.M)
        if m:
            return m.group(1).strip() if m.groups() else m.group(0).strip()
    return ""


def analyze_rules(text: str, category: str):
    t = text or ""
    fields = {
        "manufacturer_or_packer": field([r"(?:manufacturer|manufactured|man\w{2,}|mfg|mfd)\s+by\s*[:\-]?\s*([^\n]+)", r"(?:packer|importer)\s*[:\-]?\s*([^\n]+)"], t),
        "address": field([r"(?:address|addr\.?|registered office)\s*[:\-]?\s*(.+)"], t),
        "net_quantity": field([r"(?:net quantity|net qty|quantity|net wt\.?|net volume)\s*[:\-]?\s*([\w. ]+(?:kg|g|mg|l|ml|cm|m)?)[\s$]*"], t),
        "mrp": field([r"(?:mrp|maximum retail price)[^\n]*(?:see|refer)\s+([^\n]+)", r"(?:mrp|maximum retail price)\s*[:\-]?\s*(?:rs\.?|₹)?\s*([\d,.]+)"], t),
        "date": field([r"(?:for\s+)?date of manufacture[^\n]*(?:see|refer)\s+([^\n]+)", r"(?:best before|expiry date|use by|mfg\.?\s*date|mfd\.?\s*date|packed on|packing date)\s*[:\-]?\s*(.+)", r"\b(?:mfg|mfd|pkd)\.?\s*(?:on|date)?\s*[:\-]\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}[/-]\d{2,4}|[A-Za-z]{3,9}\s+\d{4})"], t),
        "consumer_care": field([r"(?:contact\s+)?consumer\s+(?:response\s+)?(?:coordinator|care|complaints?)[^\n]*\n\s*([^\n]+)", r"(?:consumer care|customer care|consumer complaints|care)\s*[:\-]?\s*([^\n]+)"], t),
        "country_of_origin": field([r"(?:country of origin|made in|country)\s*[:\-]?\s*(.+)"], t),
        "calories": field([r"(?:calories|energy)\s*[:\-]?\s*([\d,.]+\s*(?:kcal|calories|kj)?)"], t),
    }
    if not fields["mrp"] and re.search(r"\bmrp\b[\s\S]{0,160}(?:see|refer)\s+neck", t, re.I):
        fields["mrp"] = "See neck"
    if re.search(r"date of manufacture[\s\S]{0,160}(?:see|refer)\s+neck", t, re.I) and (not fields["date"] or "batch" in fields["date"].lower()):
        fields["date"] = "See neck"
    checks, violations = [], []
    required = [
        ("manufacturer_or_packer", "Manufacturer / Packer / Importer details"),
        ("address", "Name and address"),
        ("net_quantity", "Net quantity"),
        ("mrp", "Maximum Retail Price (MRP)"),
        ("date", "Month / year information"),
        ("consumer_care", "Consumer care details"),
    ]
    for key, title in required:
        if fields[key]:
            checks.append({"code": key, "title": title, "status": "PASS", "message": "Declaration detected by OCR."})
        else:
            checks.append({"code": key, "title": title, "status": "REVIEW", "message": "Not detected by OCR; manual verification required."})
            violations.append({"title": f"{title} not detected", "message": "OCR did not find the expected declaration. This is a review flag, not a legal conclusion.", "rule": "Configurable mandatory-declaration rule"})

    if fields["mrp"]:
        try:
            if float(fields["mrp"].replace(",", "")) <= 0:
                raise ValueError()
        except Exception:
            violations.append({"title": "MRP value requires review", "message": "An MRP field was detected but the numeric value could not be validated reliably.", "rule": "MRP validation rule"})
    else:
        pass

    if fields["net_quantity"] and not re.search(r"\b(?:kg|g|mg|l|ml|m|cm|mm|N|U)\b", fields["net_quantity"], re.I):
        violations.append({"title": "Net quantity unit requires review", "message": "A quantity was detected but a recognizable unit was not found.", "rule": "Net quantity unit rule"})

    score = round(100 * sum(c["status"] == "PASS" for c in checks) / len(checks), 1)
    status = "PASS" if not violations and score >= 90 else "LOW CONFIDENCE"
    return fields, checks, violations, score, status


def annotate_image(path: Path, lines, inspection_code):
    img = cv2.imread(str(path))
    if img is None:
        return None
    for item in lines:
        box = item.get("box")
        if not box or len(box) < 4:
            continue
        try:
            arr = np.array(box).reshape(-1, 2).astype(int)
            x1, y1 = arr[:, 0].min(), arr[:, 1].min()
            x2, y2 = arr[:, 0].max(), arr[:, 1].max()
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 160, 255), 2)
            label = f"{item['confidence']:.2f}"
            cv2.putText(img, label, (x1, max(18, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 90, 220), 1, cv2.LINE_AA)
        except Exception:
            continue
    out = ANNOTATED / f"{inspection_code}.jpg"
    cv2.imwrite(str(out), img)
    return out


def make_pdf(i: Inspection):
    path = REPORTS / f"inspection_{i.id}.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    y = h - 48
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, y, "Smart Pack - Compliance Assessment Report")
    y -= 24
    c.setFont("Helvetica", 9)
    for line in [
        f"Inspection: {i.inspection_code}",
        f"Created: {i.created_at.isoformat()} UTC",
        f"Category: {i.category}",
        f"Status: {i.status} | Score: {i.score}% | OCR confidence: {i.ocr_confidence:.0%}",
    ]:
        c.drawString(40, y, line); y -= 14
    y -= 8
    c.setFont("Helvetica-Bold", 12); c.drawString(40, y, "Extracted declarations"); y -= 18
    c.setFont("Helvetica", 9)
    for k, v in json.loads(i.fields_json).items():
        c.drawString(50, y, f"{k.replace('_', ' ').title()}: {v or 'Not detected'}"); y -= 13
        if y < 70:
            c.showPage(); y = h - 48; c.setFont("Helvetica", 9)
    y -= 8; c.setFont("Helvetica-Bold", 12); c.drawString(40, y, "Compliance checks"); y -= 18; c.setFont("Helvetica", 9)
    for x in json.loads(i.checks_json):
        c.drawString(50, y, f"{x['status']} - {x['title']}: {x['message']}"); y -= 13
        if y < 70:
            c.showPage(); y = h - 48; c.setFont("Helvetica", 9)
    y -= 8; c.setFont("Helvetica-Bold", 12); c.drawString(40, y, "Violations / review items"); y -= 18; c.setFont("Helvetica", 9)
    violations = json.loads(i.violations_json)
    if not violations:
        c.drawString(50, y, "No configured review flags detected."); y -= 13
    for x in violations:
        c.drawString(50, y, f"- {x['title']} [{x['rule']}]"); y -= 13
        if y < 70:
            c.showPage(); y = h - 48; c.setFont("Helvetica", 9)
    y -= 15; c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 35, "AI-assisted preliminary assessment. Verify the current applicable Legal Metrology requirements before enforcement action.")
    c.save()
    return path


def serialize(i: Inspection):
    return {
        "id": i.id,
        "inspection_code": i.inspection_code,
        "product_name": i.product_name,
        "category": i.category,
        "language": i.language,
        "status": i.status,
        "score": i.score,
        "ocr_confidence": i.ocr_confidence,
        "raw_text": i.raw_text,
        "fields": json.loads(i.fields_json),
        "checks": json.loads(i.checks_json),
        "violations": json.loads(i.violations_json),
        "evidence": json.loads(i.evidence_json),
        "image_url": f"/uploads/{i.image_path}" if i.image_path else None,
        "annotated_url": f"/annotated/{i.annotated_path}" if i.annotated_path else None,
        "created_at": i.created_at.isoformat(),
        "created_by": i.created_by,
    }

@app.get("/health")
def health():
    return {"status": "ok", "service": "smart-pack-compliance-api", "version": "2.0.0"}

@app.post("/api/auth/login")
def login(body: LoginRequest):
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username=body.username).first()
        if not user or not pwd_context.verify(body.password, user.password_hash):
            raise HTTPException(401, "Invalid username or password")
        return {"access_token": token_for(user), "token_type": "bearer", "role": user.role, "username": user.username}
    finally:
        db.close()

@app.get("/api/auth/login")
def login_info():
    return {"message": "Use POST /api/auth/login with username and password."}

@app.post("/api/auth/register")
def register(body: RegisterRequest):
    username = body.username.strip()
    if len(username) < 3 or len(username) > 100:
        raise HTTPException(400, "Username must be between 3 and 100 characters.")
    if len(body.password) < 8:
        raise HTTPException(400, "Password must contain at least 8 characters.")
    db = SessionLocal()
    try:
        if db.query(User).filter_by(username=username).first():
            raise HTTPException(409, "Username already exists.")
        user = User(username=username, password_hash=pwd_context.hash(body.password), role="INSPECTOR")
        db.add(user)
        db.commit()
        return {"message": "Account created. You can now sign in."}
    finally:
        db.close()

@app.get("/api/auth/register")
def register_info():
    return {"message": "Use POST /api/auth/register with username and password."}

@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return user

@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), lang: str = "en", user=Depends(current_user)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Please upload JPG, PNG or WEBP package images.")
    if lang not in {"en", "hi", "ta", "te"}:
        lang = "en"
    raw = await file.read()
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(413, "Image is too large. Maximum 12 MB.")
    ext = Path(file.filename or ".jpg").suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ext = ".jpg"
    code = "SP-" + uuid.uuid4().hex[:10].upper()
    path = UPLOADS / f"{code}{ext}"
    path.write_bytes(raw)
    if cv2.imread(str(path)) is None:
        path.unlink(missing_ok=True)
        raise HTTPException(400, "This image format could not be read. Please choose JPG or PNG.")

    text, conf, lines = extract_ocr(path, lang)
    category = detect_category(text)
    fields, checks, violations, score, status = analyze_rules(text, category)
    annotated = annotate_image(path, lines, code)
    evidence = [{"type": "original_image", "path": f"/uploads/{path.name}"}]
    if annotated:
        evidence.append({"type": "ocr_annotated_image", "path": f"/annotated/{annotated.name}"})

    db = SessionLocal()
    try:
        i = Inspection(
            inspection_code=code,
            product_name=fields.get("manufacturer_or_packer") or "Packaged Commodity",
            category=category,
            language=lang,
            status=status,
            score=score,
            ocr_confidence=conf,
            raw_text=text,
            fields_json=json.dumps(fields, ensure_ascii=False),
            checks_json=json.dumps(checks, ensure_ascii=False),
            violations_json=json.dumps(violations, ensure_ascii=False),
            evidence_json=json.dumps(evidence, ensure_ascii=False),
            image_path=path.name,
            annotated_path=annotated.name if annotated else None,
            created_by=user["username"],
        )
        db.add(i); db.commit(); db.refresh(i); make_pdf(i)
        return serialize(i)
    finally:
        db.close()

@app.get("/api/inspections")
def inspections(user=Depends(current_user)):
    db = SessionLocal()
    try:
        return [serialize(x) for x in db.query(Inspection).order_by(Inspection.id.desc()).all()]
    finally:
        db.close()

@app.get("/api/inspections/{inspection_id}")
def inspection(inspection_id: int, user=Depends(current_user)):
    db = SessionLocal()
    try:
        i = db.get(Inspection, inspection_id)
        if not i: raise HTTPException(404, "Inspection not found")
        return serialize(i)
    finally:
        db.close()

@app.get("/api/reports/{inspection_id}/pdf")
def report(inspection_id: int, user=Depends(current_user)):
    db = SessionLocal()
    try:
        i = db.get(Inspection, inspection_id)
        if not i: raise HTTPException(404, "Inspection not found")
        path = make_pdf(i)
        return FileResponse(path, media_type="application/pdf", filename=f"inspection_{i.inspection_code}.pdf")
    finally:
        db.close()

# The Docker image copies the Vite build into /app/frontend/dist.
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
