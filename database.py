"""SQLite schema + automatic first-run setup for AG Realty."""
import os
import secrets
import sqlite3

from werkzeug.security import generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE, "realestate.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  phone TEXT DEFAULT '',
  password_hash TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS admins (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'admin',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- Hard limit: the database itself refuses a third admin account.
CREATE TRIGGER IF NOT EXISTS max_two_admins BEFORE INSERT ON admins
WHEN (SELECT COUNT(*) FROM admins) >= 2
BEGIN SELECT RAISE(ABORT, 'Only two admin accounts are allowed'); END;

CREATE TABLE IF NOT EXISTS properties (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  listing_type TEXT NOT NULL CHECK (listing_type IN ('buy','rent')),
  property_type TEXT NOT NULL DEFAULT 'Other',
  price REAL NOT NULL DEFAULT 0,
  location TEXT NOT NULL DEFAULT '',          -- public area / city
  address_private TEXT DEFAULT '',            -- never shown unless show_exact = 1
  lat REAL, lng REAL,
  show_exact INTEGER NOT NULL DEFAULT 0,
  bedrooms INTEGER DEFAULT 0,
  bathrooms INTEGER DEFAULT 0,
  area_sqft REAL,
  amenities TEXT DEFAULT '',
  description TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available','sold','rented')),
  featured INTEGER NOT NULL DEFAULT 0,
  approved INTEGER NOT NULL DEFAULT 1,        -- user submissions wait for admin approval
  owner_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS property_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,                     -- file name in uploads/ or a full https URL
  kind TEXT NOT NULL DEFAULT 'photo',         -- photo | 3d_render | interior_3d | proposed | panorama
  caption TEXT DEFAULT '',
  sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS property_videos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  filename TEXT DEFAULT '',
  url TEXT DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'video',         -- video | walkthrough | visualization
  title TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS favorites (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (user_id, property_id)
);
CREATE TABLE IF NOT EXISTS enquiries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  property_id INTEGER REFERENCES properties(id) ON DELETE SET NULL,
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  email TEXT DEFAULT '',
  phone TEXT DEFAULT '',
  message TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','contacted','closed')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS nearby_facilities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  category TEXT NOT NULL,
  name TEXT NOT NULL,
  distance_m INTEGER,
  lat REAL, lng REAL
);
CREATE TABLE IF NOT EXISTS social_links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL,
  label TEXT NOT NULL,
  url TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_prop_filter ON properties (approved, listing_type, status);
CREATE INDEX IF NOT EXISTS idx_img_prop ON property_images (property_id);
"""

DEFAULT_SETTINGS = {
    "phone1": "9620522047",
    "phone2": "9482714786",
    "whatsapp": "9620522047",
    "email": "",
    "address": "",
    "hours": "Mon–Sat, 9:30 am – 6:30 pm",
}

DEFAULT_SOCIALS = [
    ("instagram", "@m_u_s_u_46", "https://www.instagram.com/m_u_s_u_46/", 1),
    ("instagram", "@mdmusu46", "https://www.instagram.com/mdmusu46/", 1),
    ("facebook", "Facebook", "", 0),
    ("youtube", "YouTube", "", 0),
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables and seed settings + the two admin accounts on first run."""
    conn = get_db()
    conn.executescript(SCHEMA)
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    if conn.execute("SELECT COUNT(*) FROM social_links").fetchone()[0] == 0:
        for i, (pf, label, url, act) in enumerate(DEFAULT_SOCIALS):
            conn.execute(
                "INSERT INTO social_links (platform, label, url, active, sort_order) VALUES (?,?,?,?,?)",
                (pf, label, url, act, i),
            )
    if conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0] == 0:
        accounts = [
            ("Owner", os.environ.get("ADMIN1_EMAIL", "admin1@agrealty.local"), os.environ.get("ADMIN1_PASSWORD")),
            ("Second Admin", os.environ.get("ADMIN2_EMAIL", "admin2@agrealty.local"), os.environ.get("ADMIN2_PASSWORD")),
        ]
        lines = []
        for name, email, pw in accounts:
            generated = pw is None
            pw = pw or secrets.token_urlsafe(9)
            conn.execute(
                "INSERT INTO admins (name, email, password_hash, role) VALUES (?,?,?,?)",
                (name, email.lower(), generate_password_hash(pw), "owner" if name == "Owner" else "admin"),
            )
            lines.append(f"{name}: {email}  /  {pw if generated else '(from environment variable)'}")
        conn.commit()
        text = "\n".join(lines)
        banner = "=" * 62
        print(f"\n{banner}\n AG REALTY - FIRST RUN: ADMIN LOGINS (change them in the admin panel)\n{banner}\n{text}\n{banner}\n")
        with open(os.path.join(BASE, "FIRST_RUN_ADMIN_PASSWORDS.txt"), "w") as fh:
            fh.write(text + "\n\nChange both passwords in Admin > Settings, then delete this file.\n")
    conn.commit()
    conn.close()
