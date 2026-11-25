"""AG Realty - Flask application.

Run locally:  python app.py
Production:   gunicorn app:app   (see README for media storage notes)
"""
import hashlib
import math
import os
import re
import secrets
import sqlite3
import time
import uuid
from functools import wraps
from urllib.parse import quote

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from database import BASE, get_db, init_db


def _secret_key():
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    path = os.path.join(BASE, ".secret_key")
    if not os.path.exists(path):
        with open(path, "w") as fh:
            fh.write(secrets.token_hex(32))
    with open(path) as fh:
        return fh.read().strip()


app = Flask(__name__)
app.config.update(
    SECRET_KEY=_secret_key(),
    MAX_CONTENT_LENGTH=300 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("HTTPS") == "1",
)
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(BASE, "static", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
init_db()

# ----------------------------------------------------------------- constants
PROPERTY_TYPES = ["Apartment", "Villa", "House", "Plot / Land", "Commercial",
                  "Office", "Farmhouse", "Penthouse", "Studio"]
STATUSES = ["available", "sold", "rented"]
IMAGE_KINDS = {  # kind -> public label (None = real photo, no badge)
    "photo": None,
    "3d_render": "3D Visualization",
    "interior_3d": "3D Visualization",
    "proposed": "Proposed View",
    "panorama": "360° Panorama",
}
VISUAL_CHOICES = [("3d_render", "3D rendered exterior"), ("interior_3d", "3D rendered interior"),
                  ("proposed", "Proposed / future building view"), ("panorama", "360° panorama (equirectangular)")]
VIDEO_KINDS = {"video": "Property video", "walkthrough": "Walkthrough", "visualization": "3D Visualization"}
FACILITY_CATS = [("school", "Schools"), ("hospital", "Hospitals"), ("supermarket", "Supermarkets"),
                 ("restaurant", "Restaurants"), ("bank", "Banks"), ("gym", "Gyms"),
                 ("bus_stop", "Bus stops"), ("metro", "Metro stations"), ("other", "Other useful places")]
IMG_EXT = {"jpg", "jpeg", "png", "webp", "gif"}
VID_EXT = {"mp4", "webm", "mov", "m4v"}
PER_PAGE = 9
SORTS = {"newest": "p.created_at DESC, p.id DESC", "price_asc": "p.price ASC", "price_desc": "p.price DESC"}


# ----------------------------------------------------------------- database
def db():
    if "db" not in g:
        g.db = get_db()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    d = g.pop("db", None)
    if d is not None:
        d.close()


# ----------------------------------------------------------------- file storage
# To move to S3 / Cloudinary later, only change these three helpers.
def store_file(fs, allowed):
    if not fs or not fs.filename or "." not in fs.filename:
        return None
    ext = fs.filename.rsplit(".", 1)[-1].lower()
    if ext not in allowed:
        return None
    name = f"{uuid.uuid4().hex}.{ext}"
    fs.save(os.path.join(UPLOAD_DIR, name))
    return name


def delete_file(name):
    if name and not name.startswith("http"):
        try:
            os.remove(os.path.join(UPLOAD_DIR, os.path.basename(name)))
        except OSError:
            pass


def media_url(name):
    if name.startswith("http"):
        return name
    return url_for("static", filename="uploads/" + name) if UPLOAD_DIR.startswith(BASE) \
        else url_for("uploaded_file", name=name)


@app.route("/media/<path:name>")
def uploaded_file(name):
    from flask import send_from_directory
    return send_from_directory(UPLOAD_DIR, name)


# ----------------------------------------------------------------- security helpers
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


@app.before_request
def csrf_protect():
    if request.method == "POST":
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
        expected = session.get("csrf")
        if not expected or not sent or not secrets.compare_digest(sent, expected):
            abort(400, "Your security token expired. Go back, refresh the page and try again.")


@app.after_request
def headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resp


_attempts = {}


def too_many(key):
    now = time.time()
    _attempts[key] = [t for t in _attempts.get(key, []) if now - t < 600]
    return len(_attempts[key]) >= 10


def note_fail(key):
    _attempts.setdefault(key, []).append(time.time())


def safe_next(url):
    return url if url and url.startswith("/") and not url.startswith("//") else None


def current_user():
    if "cu" not in g:
        g.cu = None
        if session.get("user_id"):
            g.cu = db().execute("SELECT * FROM users WHERE id=? AND is_active=1", (session["user_id"],)).fetchone()
            if not g.cu:
                session.pop("user_id", None)
    return g.cu


def current_admin():
    if "ca" not in g:
        g.ca = None
        if session.get("admin_id"):
            g.ca = db().execute("SELECT * FROM admins WHERE id=?", (session["admin_id"],)).fetchone()
    return g.ca


def login_required(fn):
    @wraps(fn)
    def wrap(*a, **kw):
        if not current_user():
            flash("Log in to continue.", "info")
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return fn(*a, **kw)
    return wrap


def admin_required(fn):
    @wraps(fn)
    def wrap(*a, **kw):
        if not current_admin():
            return redirect(url_for("admin_login", next=request.path))
        return fn(*a, **kw)
    return wrap


# ----------------------------------------------------------------- template helpers
def digits(s):
    d = re.sub(r"\D", "", s or "")
    return "91" + d if len(d) == 10 else d


@app.context_processor
def inject():
    d = db()
    site = {r["key"]: r["value"] for r in d.execute("SELECT key, value FROM settings")}
    socials = d.execute("SELECT * FROM social_links WHERE active=1 AND url!='' ORDER BY sort_order, id").fetchall()

    def wa_link(text=""):
        return f"https://wa.me/{digits(site.get('whatsapp'))}?text={quote(text)}"

    return dict(now_year=time.strftime('%Y'), site=site, socials=socials, current_user=current_user(), current_admin=current_admin(),
                csrf_token=csrf_token, media_url=media_url, wa_link=wa_link, IMAGE_KINDS=IMAGE_KINDS,
                VIDEO_KINDS=VIDEO_KINDS, FACILITY_CATS=FACILITY_CATS, PROPERTY_TYPES=PROPERTY_TYPES,
                VISUAL_CHOICES=VISUAL_CHOICES)


@app.template_filter("inr")
def inr(v):
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return ""
    s = str(abs(n))
    if len(s) > 3:
        s = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", s[:-3]) + "," + s[-3:]
    return "₹" + s


@app.template_filter("price_short")
def price_short(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return ""
    if n >= 1e7:
        return "₹" + f"{n / 1e7:.2f}".rstrip("0").rstrip(".") + " Cr"
    if n >= 1e5:
        return "₹" + f"{n / 1e5:.2f}".rstrip("0").rstrip(".") + " L"
    return inr(n)


@app.template_filter("embed")
def embed(url):
    m = re.search(r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})", url or "")
    if m:
        return "https://www.youtube.com/embed/" + m.group(1)
    m = re.search(r"vimeo\.com/(\d+)", url or "")
    return "https://player.vimeo.com/video/" + m.group(1) if m else None


@app.template_filter("datefmt")
def datefmt(v):
    return (v or "")[:10]


# ----------------------------------------------------------------- property queries
PROP_SELECT = """
SELECT p.*,
 (SELECT filename FROM property_images i WHERE i.property_id=p.id ORDER BY (i.kind='photo') DESC, i.sort_order, i.id LIMIT 1) AS cover,
 (SELECT kind FROM property_images i WHERE i.property_id=p.id ORDER BY (i.kind='photo') DESC, i.sort_order, i.id LIMIT 1) AS cover_kind,
 EXISTS(SELECT 1 FROM favorites f WHERE f.property_id=p.id AND f.user_id=?) AS is_fav
FROM properties p"""


def query_props(where="p.approved=1", params=(), order=SORTS["newest"], limit=None, offset=0):
    uid = session.get("user_id") or 0
    sql = f"{PROP_SELECT} WHERE {where} ORDER BY {order}"
    args = [uid, *params]
    if limit:
        sql += " LIMIT ? OFFSET ?"
        args += [limit, offset]
    return db().execute(sql, args).fetchall()


def filter_clause(args, force_type=None):
    w, v = ["p.approved=1"], []
    lt = force_type or args.get("listing_type")
    if lt in ("buy", "rent"):
        w.append("p.listing_type=?"); v.append(lt)
    q = args.get("q", "").strip()
    if q:
        w.append("(p.location LIKE ? OR p.title LIKE ?)"); v += [f"%{q}%"] * 2
    if args.get("property_type") in PROPERTY_TYPES:
        w.append("p.property_type=?"); v.append(args["property_type"])
    lo, hi = args.get("min_price", ""), args.get("max_price", "")
    if args.get("budget"):
        lo, _, hi = args["budget"].partition("-")
    for val, op in ((lo, ">="), (hi, "<=")):
        try:
            w.append(f"p.price {op} ?"); v.append(float(val))
        except ValueError:
            w.pop()
    if args.get("bedrooms", "").isdigit():
        w.append("p.bedrooms>=?"); v.append(int(args["bedrooms"]))
    if args.get("status") in STATUSES:
        w.append("p.status=?"); v.append(args["status"])
    return " AND ".join(w), v


def listing(force_type):
    where, params = filter_clause(request.args, force_type)
    total = db().execute(f"SELECT COUNT(*) FROM properties p WHERE {where}", params).fetchone()[0]
    page = max(1, request.args.get("page", 1, type=int))
    order = SORTS.get(request.args.get("sort"), SORTS["newest"])
    items = query_props(where, params, order, PER_PAGE, (page - 1) * PER_PAGE)
    keep = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template("properties.html", items=items, total=total, page=page,
                           pages=max(1, math.ceil(total / PER_PAGE)), mode=force_type, keep=keep,
                           endpoint=request.endpoint)


def public_point(p):
    """Return (lat, lng, exact). Private homes get a deterministic offset so the true spot is never revealed."""
    if p["lat"] is None or p["lng"] is None:
        return None
    if p["show_exact"]:
        return p["lat"], p["lng"], True
    h = hashlib.sha256(f"agr-{p['id']}".encode()).digest()
    ang, dist = h[0] / 255 * 2 * math.pi, 120 + h[1] / 255 * 200
    dlat = dist * math.cos(ang) / 111320
    dlng = dist * math.sin(ang) / (111320 * math.cos(math.radians(p["lat"])))
    return round(p["lat"] + dlat, 5), round(p["lng"] + dlng, 5), False


# ----------------------------------------------------------------- public pages
@app.route("/")
def index():
    d = db()
    stats = dict(
        buy=d.execute("SELECT COUNT(*) FROM properties WHERE approved=1 AND listing_type='buy' AND status='available'").fetchone()[0],
        rent=d.execute("SELECT COUNT(*) FROM properties WHERE approved=1 AND listing_type='rent' AND status='available'").fetchone()[0],
        sold=d.execute("SELECT COUNT(*) FROM properties WHERE approved=1 AND status IN ('sold','rented')").fetchone()[0],
    )
    return render_template("index.html",
                           featured=query_props("p.approved=1 AND p.featured=1 AND p.status='available'", limit=6),
                           recent=query_props("p.approved=1", limit=6), stats=stats)


@app.route("/properties")
def properties():
    return listing(None)


@app.route("/buy")
def buy():
    return listing("buy")


@app.route("/rent")
def rent():
    return listing("rent")


@app.route("/property/<int:pid>")
def property_detail(pid):
    rows = query_props("p.id=?", (pid,))
    if not rows:
        abort(404)
    p = rows[0]
    u = current_user()
    if not p["approved"] and not current_admin() and not (u and p["owner_user_id"] == u["id"]):
        abort(404)
    d = db()
    imgs = d.execute("SELECT * FROM property_images WHERE property_id=? ORDER BY sort_order, id", (pid,)).fetchall()
    pt = public_point(p)
    facilities = [dict(r) for r in d.execute("SELECT category,name,distance_m,lat,lng FROM nearby_facilities WHERE property_id=?", (pid,))]
    similar = query_props("p.approved=1 AND p.id!=? AND p.listing_type=?", (pid, p["listing_type"]), limit=3)
    return render_template(
        "property_detail.html", p=p,
        photos=[i for i in imgs if i["kind"] == "photo"],
        visuals=[i for i in imgs if i["kind"] not in ("photo", "panorama")],
        panoramas=[i for i in imgs if i["kind"] == "panorama"],
        videos=d.execute("SELECT * FROM property_videos WHERE property_id=?", (pid,)).fetchall(),
        amenities=[a.strip() for a in (p["amenities"] or "").split(",") if a.strip()],
        point=pt, facilities=facilities, similar=similar,
        share_url=request.url_root.rstrip("/") + url_for("property_detail", pid=pid))


@app.route("/api/favorite/<int:pid>", methods=["POST"])
def toggle_favorite(pid):
    u = current_user()
    if not u:
        return jsonify(error="login"), 401
    d = db()
    if not d.execute("SELECT 1 FROM properties WHERE id=?", (pid,)).fetchone():
        abort(404)
    row = d.execute("SELECT id FROM favorites WHERE user_id=? AND property_id=?", (u["id"], pid)).fetchone()
    if row:
        d.execute("DELETE FROM favorites WHERE id=?", (row["id"],))
    else:
        d.execute("INSERT INTO favorites (user_id, property_id) VALUES (?,?)", (u["id"], pid))
    d.commit()
    return jsonify(favorited=not row)


@app.route("/favorites")
@login_required
def favorites():
    items = query_props("p.approved=1 AND p.id IN (SELECT property_id FROM favorites WHERE user_id=?)",
                        (current_user()["id"],))
    return render_template("favorites.html", items=items)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/enquiry", methods=["POST"])
def enquiry():
    f = request.form
    back = safe_next(f.get("next")) or url_for("contact")
    if f.get("website"):  # honeypot
        return redirect(back)
    name, email, phone, msg = (f.get(k, "").strip() for k in ("name", "email", "phone", "message"))
    if not name or not msg or not (email or phone):
        flash("Enter your name, a message, and either a phone number or an email.", "error")
        return redirect(back)
    pid = f.get("property_id", type=int)
    u = current_user()
    db().execute("INSERT INTO enquiries (property_id, user_id, name, email, phone, message) VALUES (?,?,?,?,?,?)",
                 (pid, u["id"] if u else None, name[:120], email[:160], phone[:30], msg[:3000]))
    db().commit()
    flash("Thanks, your enquiry is with AG Realty. We will contact you shortly.", "success")
    return redirect(back)


# ----------------------------------------------------------------- user accounts
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        name, email, phone, pw = f.get("name", "").strip(), f.get("email", "").strip().lower(), f.get("phone", "").strip(), f.get("password", "")
        if not name or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            flash("Enter your name and a valid email address.", "error")
        elif len(pw) < 8:
            flash("Use a password with at least 8 characters.", "error")
        elif pw != f.get("confirm"):
            flash("The two passwords do not match.", "error")
        else:
            try:
                cur = db().execute("INSERT INTO users (name,email,phone,password_hash) VALUES (?,?,?,?)",
                                   (name, email, phone, generate_password_hash(pw)))
                db().commit()
                session.clear()
                session["user_id"] = cur.lastrowid
                flash("Welcome to AG Realty.", "success")
                return redirect(safe_next(f.get("next")) or url_for("dashboard"))
            except sqlite3.IntegrityError:
                flash("An account with this email already exists. Log in instead.", "error")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email, key = request.form.get("email", "").strip().lower(), "u:" + request.remote_addr
        if too_many(key):
            flash("Too many attempts. Wait a few minutes and try again.", "error")
        else:
            u = db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if u and u["is_active"] and check_password_hash(u["password_hash"], request.form.get("password", "")):
                session.clear()
                session["user_id"] = u["id"]
                return redirect(safe_next(request.form.get("next")) or url_for("dashboard"))
            note_fail(key)
            flash("Email or password is incorrect.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    u = current_user()
    d = db()
    return render_template(
        "dashboard.html",
        mine=query_props("p.owner_user_id=?", (u["id"],)),
        enquiries=d.execute("""SELECT e.*, p.title FROM enquiries e LEFT JOIN properties p ON p.id=e.property_id
                               WHERE e.user_id=? OR (e.email!='' AND e.email=?) ORDER BY e.id DESC""", (u["id"], u["email"])).fetchall(),
        fav_count=d.execute("SELECT COUNT(*) FROM favorites WHERE user_id=?", (u["id"],)).fetchone()[0])


@app.route("/dashboard/profile", methods=["POST"])
@login_required
def update_profile():
    u, f = current_user(), request.form
    name = f.get("name", "").strip()
    if not name:
        flash("Name cannot be empty.", "error")
        return redirect(url_for("dashboard"))
    db().execute("UPDATE users SET name=?, phone=? WHERE id=?", (name, f.get("phone", "").strip(), u["id"]))
    if f.get("new_password"):
        if not check_password_hash(u["password_hash"], f.get("current_password", "")):
            flash("Current password is incorrect.", "error")
            return redirect(url_for("dashboard"))
        if len(f["new_password"]) < 8:
            flash("New password needs at least 8 characters.", "error")
            return redirect(url_for("dashboard"))
        db().execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(f["new_password"]), u["id"]))
    db().commit()
    flash("Profile saved.", "success")
    return redirect(url_for("dashboard"))


# ----------------------------------------------------------------- property create/update (shared)
def parse_property_form(f, admin):
    def num(k):
        try:
            return float(f.get(k, "").replace(",", "").strip())
        except ValueError:
            return None
    errors = []
    data = dict(
        title=f.get("title", "").strip(), listing_type=f.get("listing_type"),
        property_type=f.get("property_type", "").strip() or "Other", price=num("price"),
        location=f.get("location", "").strip(), address_private=f.get("address_private", "").strip(),
        lat=num("lat"), lng=num("lng"), bedrooms=int(num("bedrooms") or 0), bathrooms=int(num("bathrooms") or 0),
        area_sqft=num("area_sqft"),
        amenities=", ".join(a.strip() for a in f.get("amenities", "").split(",") if a.strip()),
        description=f.get("description", "").strip())
    if not data["title"]:
        errors.append("Enter a property title.")
    if data["listing_type"] not in ("buy", "rent"):
        errors.append("Choose Buy or Rent.")
    if data["price"] is None or data["price"] < 0:
        errors.append("Enter a valid price.")
    if not data["location"]:
        errors.append("Enter the area or city.")
    if admin:
        data.update(status=f.get("status") if f.get("status") in STATUSES else "available",
                    featured=1 if f.get("featured") else 0, show_exact=1 if f.get("show_exact") else 0,
                    approved=1 if f.get("approved") else 0)
    return data, errors


def save_property(data, pid=None, owner=None):
    d = db()
    if pid:
        cols = ", ".join(f"{k}=?" for k in data)
        d.execute(f"UPDATE properties SET {cols}, updated_at=CURRENT_TIMESTAMP WHERE id=?", [*data.values(), pid])
    else:
        if owner:
            data["owner_user_id"], data["approved"] = owner, 0
        cur = d.execute(f"INSERT INTO properties ({', '.join(data)}) VALUES ({', '.join('?' * len(data))})", list(data.values()))
        pid = cur.lastrowid
    d.commit()
    return pid


def handle_media(pid, admin):
    d, f = db(), request.form
    n = d.execute("SELECT COALESCE(MAX(sort_order),0) FROM property_images WHERE property_id=?", (pid,)).fetchone()[0]
    for fs in request.files.getlist("photos"):
        name = store_file(fs, IMG_EXT)
        if name:
            n += 1
            d.execute("INSERT INTO property_images (property_id, filename, kind, sort_order) VALUES (?,?,?,?)", (pid, name, "photo", n))
    if admin:
        kind = f.get("visual_kind") if f.get("visual_kind") in IMAGE_KINDS and f.get("visual_kind") != "photo" else "3d_render"
        for fs in request.files.getlist("visuals"):
            name = store_file(fs, IMG_EXT)
            if name:
                n += 1
                d.execute("INSERT INTO property_images (property_id, filename, kind, sort_order) VALUES (?,?,?,?)", (pid, name, kind, n))
    vkind = f.get("video_kind") if f.get("video_kind") in VIDEO_KINDS else "video"
    if admin:
        for fs in request.files.getlist("videos"):
            name = store_file(fs, VID_EXT)
            if name:
                d.execute("INSERT INTO property_videos (property_id, filename, kind) VALUES (?,?,?)", (pid, name, vkind))
    url = f.get("video_url", "").strip()
    if url.startswith(("http://", "https://")):
        d.execute("INSERT INTO property_videos (property_id, url, kind) VALUES (?,?,?)", (pid, url, vkind))
    d.commit()


def remove_property_files(pid):
    d = db()
    for r in d.execute("SELECT filename FROM property_images WHERE property_id=?", (pid,)):
        delete_file(r["filename"])
    for r in d.execute("SELECT filename FROM property_videos WHERE property_id=?", (pid,)):
        delete_file(r["filename"])


# ----------------------------------------------------------------- sell / submit
@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    p = {}
    if request.method == "POST":
        data, errors = parse_property_form(request.form, admin=False)
        p = dict(request.form)
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            pid = save_property(data, owner=current_user()["id"])
            handle_media(pid, admin=False)
            flash("Your property is submitted. AG Realty will review it and contact you before it goes live.", "success")
            return redirect(url_for("dashboard"))
    return render_template("sell.html", p=p)


# ----------------------------------------------------------------- admin
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if current_admin():
        return redirect(url_for("admin_home"))
    if request.method == "POST":
        key = "a:" + request.remote_addr
        if too_many(key):
            flash("Too many attempts. Wait a few minutes and try again.", "error")
        else:
            a = db().execute("SELECT * FROM admins WHERE email=?", (request.form.get("email", "").strip().lower(),)).fetchone()
            if a and check_password_hash(a["password_hash"], request.form.get("password", "")):
                session.clear()
                session["admin_id"] = a["id"]
                return redirect(safe_next(request.form.get("next")) or url_for("admin_home"))
            note_fail(key)
            flash("Email or password is incorrect.", "error")
    return render_template("admin/login.html")


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_home():
    d = db()
    count = lambda sql: d.execute(sql).fetchone()[0]
    stats = dict(
        properties=count("SELECT COUNT(*) FROM properties WHERE approved=1"),
        available=count("SELECT COUNT(*) FROM properties WHERE approved=1 AND status='available'"),
        pending=count("SELECT COUNT(*) FROM properties WHERE approved=0"),
        users=count("SELECT COUNT(*) FROM users"),
        new_enq=count("SELECT COUNT(*) FROM enquiries WHERE status='new'"),
        favs=count("SELECT COUNT(*) FROM favorites"))
    latest = d.execute("""SELECT e.*, p.title FROM enquiries e LEFT JOIN properties p ON p.id=e.property_id
                          ORDER BY e.id DESC LIMIT 5""").fetchall()
    return render_template("admin/home.html", stats=stats, latest=latest,
                           pending=query_props("p.approved=0", limit=5))


@app.route("/admin/properties")
@admin_required
def admin_properties():
    q, st = request.args.get("q", "").strip(), request.args.get("state", "")
    w, v = ["1=1"], []
    if q:
        w.append("(p.title LIKE ? OR p.location LIKE ?)"); v += [f"%{q}%"] * 2
    if st == "pending":
        w.append("p.approved=0")
    elif st in STATUSES:
        w.append("p.status=?"); v.append(st)
    return render_template("admin/properties.html", items=query_props(" AND ".join(w), v), q=q, state=st)


def _form_page(p, errors=None, pid=None):
    d = db()
    ctx = dict(p=p, pid=pid, errors=errors or [], images=[], videos=[], facilities=[])
    if pid:
        ctx.update(images=d.execute("SELECT * FROM property_images WHERE property_id=? ORDER BY sort_order,id", (pid,)).fetchall(),
                   videos=d.execute("SELECT * FROM property_videos WHERE property_id=?", (pid,)).fetchall(),
                   facilities=d.execute("SELECT * FROM nearby_facilities WHERE property_id=? ORDER BY category, distance_m", (pid,)).fetchall())
    return render_template("admin/property_form.html", **ctx)


@app.route("/admin/property/new", methods=["GET", "POST"])
@admin_required
def admin_property_new():
    if request.method == "POST":
        data, errors = parse_property_form(request.form, admin=True)
        if not errors:
            pid = save_property(data)
            handle_media(pid, admin=True)
            flash("Property added.", "success")
            return redirect(url_for("admin_property_edit", pid=pid))
        return _form_page({**request.form.to_dict()}, errors)
    return _form_page({"approved": 1, "listing_type": "buy", "status": "available"})


@app.route("/admin/property/<int:pid>/edit", methods=["GET", "POST"])
@admin_required
def admin_property_edit(pid):
    row = db().execute("SELECT * FROM properties WHERE id=?", (pid,)).fetchone()
    if not row:
        abort(404)
    if request.method == "POST":
        data, errors = parse_property_form(request.form, admin=True)
        if errors:
            return _form_page({**request.form.to_dict(), "id": pid}, errors, pid)
        save_property(data, pid)
        handle_media(pid, admin=True)
        flash("Property saved.", "success")
        return redirect(url_for("admin_property_edit", pid=pid))
    return _form_page(dict(row), pid=pid)


@app.route("/admin/property/<int:pid>/delete", methods=["POST"])
@admin_required
def admin_property_delete(pid):
    remove_property_files(pid)
    db().execute("DELETE FROM properties WHERE id=?", (pid,))
    db().commit()
    flash("Property deleted.", "success")
    return redirect(url_for("admin_properties"))


@app.route("/admin/property/<int:pid>/quick", methods=["POST"])
@admin_required
def admin_property_quick(pid):
    f = request.form
    if f.get("status") in STATUSES:
        db().execute("UPDATE properties SET status=? WHERE id=?", (f["status"], pid))
    if f.get("approve"):
        db().execute("UPDATE properties SET approved=1 WHERE id=?", (pid,))
    if f.get("feature") is not None and f.get("feature") != "":
        db().execute("UPDATE properties SET featured=? WHERE id=?", (1 if f["feature"] == "1" else 0, pid))
    db().commit()
    flash("Updated.", "success")
    return redirect(safe_next(f.get("next")) or url_for("admin_properties"))


@app.route("/admin/media/<kind>/<int:mid>/delete", methods=["POST"])
@admin_required
def admin_media_delete(kind, mid):
    table = {"image": "property_images", "video": "property_videos"}.get(kind)
    if not table:
        abort(404)
    row = db().execute(f"SELECT * FROM {table} WHERE id=?", (mid,)).fetchone()
    if not row:
        abort(404)
    delete_file(row["filename"])
    db().execute(f"DELETE FROM {table} WHERE id=?", (mid,))
    db().commit()
    flash("Media removed.", "success")
    return redirect(url_for("admin_property_edit", pid=row["property_id"]))


@app.route("/admin/property/<int:pid>/facility", methods=["POST"])
@admin_required
def admin_facility_add(pid):
    f = request.form
    cat = f.get("category") if f.get("category") in dict(FACILITY_CATS) else "other"
    if f.get("name", "").strip():
        def n(k, cast=float):
            try:
                return cast(f.get(k, ""))
            except ValueError:
                return None
        db().execute("INSERT INTO nearby_facilities (property_id,category,name,distance_m,lat,lng) VALUES (?,?,?,?,?,?)",
                     (pid, cat, f["name"].strip(), n("distance_m", int), n("lat"), n("lng")))
        db().commit()
        flash("Facility added.", "success")
    return redirect(url_for("admin_property_edit", pid=pid) + "#facilities")


@app.route("/admin/facility/<int:fid>/delete", methods=["POST"])
@admin_required
def admin_facility_delete(fid):
    row = db().execute("SELECT property_id FROM nearby_facilities WHERE id=?", (fid,)).fetchone()
    if not row:
        abort(404)
    db().execute("DELETE FROM nearby_facilities WHERE id=?", (fid,))
    db().commit()
    return redirect(url_for("admin_property_edit", pid=row["property_id"]) + "#facilities")


@app.route("/admin/enquiries", methods=["GET", "POST"])
@admin_required
def admin_enquiries():
    if request.method == "POST":
        eid, act = request.form.get("id", type=int), request.form.get("action")
        if act == "delete":
            db().execute("DELETE FROM enquiries WHERE id=?", (eid,))
        elif act in ("new", "contacted", "closed"):
            db().execute("UPDATE enquiries SET status=? WHERE id=?", (act, eid))
        db().commit()
        return redirect(url_for("admin_enquiries", status=request.args.get("status", "")))
    st = request.args.get("status", "")
    where, v = ("WHERE e.status=?", [st]) if st in ("new", "contacted", "closed") else ("", [])
    rows = db().execute(f"""SELECT e.*, p.title FROM enquiries e LEFT JOIN properties p ON p.id=e.property_id
                            {where} ORDER BY e.id DESC""", v).fetchall()
    return render_template("admin/enquiries.html", rows=rows, status=st)


@app.route("/admin/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    if request.method == "POST":
        uid, act = request.form.get("id", type=int), request.form.get("action")
        if act == "toggle":
            db().execute("UPDATE users SET is_active=1-is_active WHERE id=?", (uid,))
        elif act == "delete":
            db().execute("DELETE FROM users WHERE id=?", (uid,))
        db().commit()
        return redirect(url_for("admin_users"))
    rows = db().execute("""SELECT u.*, (SELECT COUNT(*) FROM favorites f WHERE f.user_id=u.id) AS favs,
                           (SELECT COUNT(*) FROM properties p WHERE p.owner_user_id=u.id) AS subs
                           FROM users u ORDER BY u.id DESC""").fetchall()
    return render_template("admin/users.html", rows=rows)


@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    d, f, a = db(), request.form, current_admin()
    if request.method == "POST":
        part = f.get("part")
        if part == "contact":
            for k in ("phone1", "phone2", "whatsapp", "email", "address", "hours"):
                d.execute("INSERT INTO settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                          (k, f.get(k, "").strip()))
            flash("Contact details saved.", "success")
        elif part == "social":
            for sid in f.getlist("id"):
                d.execute("UPDATE social_links SET label=?, url=?, active=? WHERE id=?",
                          (f.get(f"label_{sid}", "").strip(), f.get(f"url_{sid}", "").strip(), 1 if f.get(f"active_{sid}") else 0, sid))
                if f.get(f"remove_{sid}"):
                    d.execute("DELETE FROM social_links WHERE id=?", (sid,))
            if f.get("new_label", "").strip():
                d.execute("INSERT INTO social_links (platform,label,url,active,sort_order) VALUES (?,?,?,?,99)",
                          (f.get("new_platform", "link"), f["new_label"].strip(), f.get("new_url", "").strip(), 1))
            flash("Social links saved.", "success")
        elif part == "account":
            if not check_password_hash(a["password_hash"], f.get("current_password", "")):
                flash("Current password is incorrect.", "error")
            else:
                email = f.get("email", "").strip().lower()
                try:
                    d.execute("UPDATE admins SET name=?, email=? WHERE id=?", (f.get("name", "").strip() or a["name"], email or a["email"], a["id"]))
                    if f.get("new_password"):
                        if len(f["new_password"]) < 8:
                            flash("New password needs at least 8 characters.", "error")
                            return redirect(url_for("admin_settings"))
                        d.execute("UPDATE admins SET password_hash=? WHERE id=?", (generate_password_hash(f["new_password"]), a["id"]))
                    flash("Account saved.", "success")
                except sqlite3.IntegrityError:
                    flash("That email is used by the other admin.", "error")
        d.commit()
        return redirect(url_for("admin_settings"))
    return render_template("admin/settings.html",
                           links=d.execute("SELECT * FROM social_links ORDER BY sort_order,id").fetchall())


# ----------------------------------------------------------------- errors
@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(413)
@app.errorhandler(500)
def error(e):
    code = getattr(e, "code", 500)
    msg = {404: "We could not find that page.", 413: "That upload is too large. Keep the total under 300 MB."}.get(
        code, getattr(e, "description", "Something went wrong on our side."))
    return render_template("error.html", code=code, msg=msg), code


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", 5000)))
