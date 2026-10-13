import io, json, os, re, uuid
from datetime import datetime
from urllib.parse import quote_plus

import requests
from dotenv import load_dotenv
from flask import (Flask, abort, flash, redirect, render_template, request,
                   send_from_directory, url_for)
from flask_login import (LoginManager, UserMixin, current_user, login_required,
                         login_user, logout_user)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

from analyzer import ROLES, analyze

load_dotenv()
BASE = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE, "uploads")
ALLOWED = {"pdf", "docx", "txt"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-me")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL") or (
    "mysql+pymysql://{u}:{p}@{h}:{port}/{d}?charset=utf8mb4".format(
        u=os.getenv("MYSQL_USER", "root"), p=quote_plus(os.getenv("MYSQL_PASSWORD", "")),
        h=os.getenv("MYSQL_HOST", "localhost"), port=os.getenv("MYSQL_PORT", "3306"),
        d=os.getenv("MYSQL_DB", "resume_analyzer")))
os.makedirs(UPLOAD_DIR, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login" # type: ignore


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resumes = db.relationship("Resume", backref="user", cascade="all, delete-orphan")


class Resume(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(100), nullable=False)
    ats_score = db.Column(db.Integer, nullable=False)
    ai_score = db.Column(db.Integer)
    result_json = db.Column(db.Text(length=16777215), nullable=False)  # MEDIUMTEXT
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))


def extract_text(path, ext):
    if ext == "pdf":
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
    if ext == "docx":
        from docx import Document # type: ignore
        return "\n".join(p.text for p in Document(path).paragraphs)
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


def grok_review(text, role):
    """Ask Grok (xAI API) for a structured review. Returns dict or None."""
    key = os.getenv("AI_API_KEY")
    if not key:
        return None
    prompt = (f"You are an expert recruiter. Review this resume for a '{role}' role. "
              "Reply with ONLY valid JSON: {\"score\": 0-100 integer fit score, \"summary\": "
              "\"2 sentences\", \"strengths\": [3-5 strings], \"improvements\": [5-7 specific, "
              "actionable strings], \"missing_keywords\": [strings], \"rewrite_example\": "
              "\"one weak bullet from the resume rewritten stronger\"}\n\nRESUME:\n" + text[:8000])
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", timeout=90,
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": os.getenv("AI_MODEL", "meta-llama/llama-prompt-guard-2-22m"), "temperature": 0.2,
                                "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"]
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception as e:
        app.logger.warning("Grok review failed: %s", e)
        return None


# ---------- auth ----------
@app.route("/")
def home():
    return redirect(url_for("dashboard" if current_user.is_authenticated else "login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name, email = request.form["name"].strip(), request.form["email"].strip().lower()
        pw = request.form["password"]
        if not name or "@" not in email or len(pw) < 6:
            flash("Enter your name, a valid email and a password of 6+ characters.", "error")
        elif User.query.filter_by(email=email).first():
            flash("That email is already registered. Log in instead.", "error")
        else:
            u = User(name=name, email=email, password_hash=generate_password_hash(pw)) # type: ignore
            db.session.add(u)
            db.session.commit()
            login_user(u)
            return redirect(url_for("dashboard"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(email=request.form["email"].strip().lower()).first()
        if u and check_password_hash(u.password_hash, request.form["password"]):
            login_user(u)
            return redirect(url_for("dashboard"))
        flash("Wrong email or password.", "error")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------- app ----------
@app.route("/dashboard")
@login_required
def dashboard():
    items = Resume.query.filter_by(user_id=current_user.id).order_by(Resume.created_at.desc()).all()
    scores = [r.ats_score for r in items]
    stats = {"count": len(items), "best": max(scores, default=0),
             "avg": round(sum(scores) / len(scores)) if scores else 0}
    return render_template("dashboard.html", items=items, stats=stats)


@app.route("/analyze", methods=["GET", "POST"])
@login_required
def analyze_page():
    if request.method == "GET":
        return render_template("analyze.html", roles=list(ROLES))
    role, file = request.form.get("role", ""), request.files.get("resume")
    if role not in ROLES:
        flash("Choose a target role.", "error")
        return redirect(url_for("analyze_page"))
    ext = file.filename.rsplit(".", 1)[-1].lower() if file and "." in file.filename else "" # type: ignore
    if ext not in ALLOWED:
        flash("Upload a PDF, DOCX or TXT file.", "error")
        return redirect(url_for("analyze_page"))
    stored = f"{current_user.id}_{uuid.uuid4().hex}.{ext}"
    path = os.path.join(UPLOAD_DIR, stored)
    file.save(path) # type: ignore
    try:
        text = extract_text(path, ext)
    except Exception:
        text = ""
    if len(text.split()) < 30:
        os.remove(path)
        flash("Couldn't read text from that file. Use a text-based PDF (not a scan).", "error")
        return redirect(url_for("analyze_page"))
    result = analyze(text, role)
    ai = grok_review(text, role)
    result["ai"] = ai
    r = Resume(user_id=current_user.id, original_name=file.filename, stored_name=stored, role=role, # type: ignore
               ats_score=result["score"], result_json=json.dumps(result), # type: ignore
               ai_score=int(ai["score"]) if ai and str(ai.get("score", "")).isdigit() else None) # type: ignore
    db.session.add(r)
    db.session.commit()
    if not ai:
        flash("AI review unavailable (check GROK_API_KEY). Showing the keyword-based analysis.", "warn")
    return redirect(url_for("report", rid=r.id))


def owned(rid):
    r = db.session.get(Resume, rid)
    if not r or r.user_id != current_user.id:
        abort(404)
    return r


@app.route("/report/<int:rid>")
@login_required
def report(rid):
    r = owned(rid)
    return render_template("report.html", r=r, d=json.loads(r.result_json))


@app.route("/file/<int:rid>")
@login_required
def download(rid):
    r = owned(rid)
    return send_from_directory(UPLOAD_DIR, r.stored_name, as_attachment=True,
                               download_name=r.original_name)


@app.route("/delete/<int:rid>", methods=["POST"])
@login_required
def delete(rid):
    r = owned(rid)
    try:
        os.remove(os.path.join(UPLOAD_DIR, r.stored_name))
    except OSError:
        pass
    db.session.delete(r)
    db.session.commit()
    return redirect(url_for("dashboard"))


with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
