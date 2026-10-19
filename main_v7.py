"""
SmartHazri v5 - Attendance App + Supabase cloud (Kivy, single file)
(upgrade of main_v4.py: same look, tabs and features; Firebase replaced by Supabase)

Cloud  : Supabase Auth + Postgres with Row Level Security, called over HTTPS with urllib (no SDK needed).
Offline: SQLite cache + outbox. Anything done offline is uploaded automatically when internet returns.
Sync   : runs in background threads while the app is open (UI never freezes).
APK    : copy this file as main.py in Buildozer. requirements = see requirements.txt
SETUP  : 1) run supabase_setup.sql in Supabase SQL Editor  2) paste your sb_publishable_ key below.
"""
import os, re, csv, io, time, json, ssl, uuid, socket, threading, sqlite3, calendar, base64, traceback
import urllib.request, urllib.error, urllib.parse, email.utils, datetime as dt
from kivy.app import App
from kivy.base import ExceptionHandler, ExceptionManager
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.metrics import dp, sp
from kivy.core.window import Window
from kivy.utils import get_color_from_hex as hx
from kivy.graphics import Color, Line, Rectangle, Ellipse
from kivy.properties import ListProperty, NumericProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

# ===================== CONFIGURATION =====================
SUPABASE_URL = "https://hgbrpdwefbpyyrzdnuka.supabase.co"
SUPABASE_KEY = "sb_publishable_i5m8noyZi1yDKf0i_w_j6A_9BsSSjTk"      # publishable key (safe to ship; never use a secret/service_role key)
APP_VERSION = "5.0.0"
# =========================================================

def configured():
    return "PUT_" not in SUPABASE_KEY and len(SUPABASE_KEY) > 20


# ---------- colors (same palette as SmartHazri v4) ----------
WHITE = [1, 1, 1, 1]
BG, AC, OK, NO, LV = hx("#f4f5fb"), hx("#4f46e5"), hx("#16a34a"), hx("#dc2626"), hx("#d97706")
MU, TX, GR = hx("#6b7280"), hx("#161a26"), hx("#e5e7eb")
CARD, IN = WHITE, hx("#f4f4fa")
ST_COL = {"P": OK, "A": NO, "L": LV}
ST_TXT = {"P": "Present", "A": "Absent", "L": "Leave"}
BRANCHES = ["CSE", "IT", "AI", "AIML", "DS", "ECE", "EE", "ME", "CE", "Other"]
YEARS = ["1st", "2nd", "3rd", "4th"]
SEMS = ["1", "2", "3", "4", "5", "6", "7", "8"]
SECS = ["A", "B", "C", "D", "E", "F"]
BATCHES = ["B1", "B2", "B3", "B4"]
CLASSES = ["Nursery", "LKG", "UKG"] + [str(i) for i in range(1, 13)]
SSECS = ["-", "A", "B", "C", "D", "E"]
NS = uuid.UUID("6f1f3c5e-0b7a-4a43-9a0e-5b2f0c1d7a11")   # namespace for deterministic ids

KV = """
<Panel>:
    canvas.before:
        Color:
            rgba: self.bg
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(self.rad)]
<RBtn>:
    canvas.before:
        Color:
            rgba: self.bg if self.state == 'normal' else [self.bg[0]*.78, self.bg[1]*.78, self.bg[2]*.78, 1]
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]
<Cell>:
    canvas.before:
        Color:
            rgba: self.bg
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(8)]
<Bar>:
    canvas:
        Color:
            rgba: self.track
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(5)]
        Color:
            rgba: self.col
        RoundedRectangle:
            pos: self.pos
            size: self.width * min(max(self.value, 0), 100) / 100., self.height
            radius: [dp(5)]
<Ring>:
    canvas:
        Color:
            rgba: self.track
        Line:
            circle: (self.center_x, self.center_y, min(self.width, self.height) / 2 - dp(8))
            width: dp(9)
        Color:
            rgba: self.col
        Line:
            circle: (self.center_x, self.center_y, min(self.width, self.height) / 2 - dp(8), 0, max(0.5, self.value * 3.6))
            width: dp(9)
            cap: 'round'
    Label:
        text: '%d%%' % root.value
        font_size: sp(24)
        bold: True
        color: root.tx
<Initials>:
    canvas.before:
        Color:
            rgba: self.col
        Ellipse:
            pos: self.pos
            size: self.size
    Label:
        text: root.text
        font_size: self.parent.height * .38 if self.parent else sp(20)
        bold: True
        color: 1, 1, 1, 1
<Loader>:
    canvas.before:
        Color:
            rgba: 0, 0, 0, .45
        Rectangle:
            pos: self.pos
            size: self.size
        Color:
            rgba: root.card
        RoundedRectangle:
            pos: self.center_x - dp(110), self.center_y - dp(60)
            size: dp(220), dp(120)
            radius: [dp(18)]
        Color:
            rgba: root.col
        Line:
            circle: (self.center_x, self.center_y + dp(20), dp(16), root.angle, root.angle + 260)
            width: dp(3)
            cap: 'round'
    Label:
        text: root.text
        size_hint: None, None
        size: dp(200), dp(40)
        pos: root.center_x - dp(100), root.center_y - dp(52)
        color: root.tx
        font_size: sp(13)
"""


# ---------- widgets ----------
class Panel(BoxLayout):
    bg = ListProperty([1, 1, 1, 1])
    rad = NumericProperty(16)

    def __init__(self, **k):
        k.setdefault("bg", list(CARD))
        super().__init__(**k)


class Card(Panel):
    def __init__(self, **k):
        k.setdefault("orientation", "vertical")
        k.setdefault("padding", dp(14))
        k.setdefault("spacing", dp(6))
        super().__init__(size_hint_y=None, **k)
        self.bind(minimum_height=self.setter("height"))


class RBtn(ButtonBehavior, Label):
    bg = ListProperty([0, 0, 0, 1])

    def __init__(self, **k):
        k.setdefault("size_hint_y", None)
        k.setdefault("height", dp(46))
        k.setdefault("bold", True)
        k.setdefault("font_size", sp(14))
        k.setdefault("bg", list(AC))
        super().__init__(**k)


class Cell(Label):
    bg = ListProperty([.9, .9, .9, 1])


class DayCell(ButtonBehavior, Cell):
    pass


class Bar(Widget):
    value = NumericProperty(0)
    col = ListProperty([0, .6, .2, 1])
    track = ListProperty([.9, .91, .94, 1])

    def __init__(self, **k):
        k.setdefault("track", list(GR))
        super().__init__(**k)


class Ring(FloatLayout):
    value = NumericProperty(0)
    col = ListProperty([0, .6, .2, 1])
    track = ListProperty([.9, .91, .94, 1])
    tx = ListProperty([0, 0, 0, 1])

    def __init__(self, **k):
        k.setdefault("track", list(GR))
        k.setdefault("tx", list(TX))
        super().__init__(**k)


class Initials(FloatLayout):
    text = StringProperty("")
    col = ListProperty([.49, .23, .93, 1])


class Loader(FloatLayout):
    text = StringProperty("Please wait...")
    angle = NumericProperty(0)
    card = ListProperty([1, 1, 1, 1])
    col = ListProperty([.3, .2, .8, 1])
    tx = ListProperty([0, 0, 0, 1])

    def __init__(self, **k):
        super().__init__(card=list(CARD), col=list(AC), tx=list(TX), **k)
        self.anim = Animation(angle=360, d=.9) + Animation(angle=0, d=0)
        self.anim.repeat = True

    def start(self):
        self.anim.start(self)

    def stop(self):
        self.anim.cancel(self)

    def on_touch_down(self, t):
        return True

    def on_touch_move(self, t):
        return True

    def on_touch_up(self, t):
        return True


# ---------- small ui helpers ----------
def lbl(t, size=14, color=None, bold=False, align="left", w=None):
    l = Label(text=str(t), font_size=sp(size), color=color or TX, bold=bold, halign=align, valign="middle", size_hint_y=None)
    if w:
        l.size_hint_x = None
        l.width = dp(w)
    l.bind(width=lambda i, v: setattr(i, "text_size", (v, None)))
    l.bind(texture_size=lambda i, s: setattr(i, "height", s[1] + dp(6)))
    return l


def inp(hint, text="", password=False, h=46):
    return TextInput(hint_text=hint, text=text, multiline=False, password=password, size_hint_y=None, height=dp(h),
                     padding=[dp(12), dp(13)], font_size=sp(15), write_tab=False, background_normal="", background_active="",
                     background_color=list(IN), foreground_color=TX, cursor_color=AC, hint_text_color=MU)


def tin(st, key, hint, password=False, num=False):
    t = inp(hint, st.get(key, ""), password)
    if num:
        t.input_filter = "int"
    t.bind(text=lambda i, v: st.__setitem__(key, v))
    return t


def spin(st, key, values, cb=None):
    values = list(values) or ["-"]
    s = Spinner(text=st.get(key) if st.get(key) in values else values[0], values=values, size_hint_y=None, height=dp(46),
                font_size=sp(15), background_normal="", background_color=list(IN), color=TX)
    st[key] = s.text
    s.bind(text=lambda i, v: (st.__setitem__(key, v), cb and Clock.schedule_once(lambda d: cb(), 0)))
    return s


def row(*ws, h=46, gap=8):
    r = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(h), spacing=dp(gap))
    for w in ws:
        r.add_widget(w)
    return r


KINDS = {"primary": ("AC", "W"), "muted": ("MU", "W"), "ghost": ("GR", "AC"), "danger": ("NO", "W"), "ok": ("OK", "W"),
         "warn": ("LV", "W"), "plain": ("CARD", "MU"), "plaindanger": ("CARD", "NO")}


def btn(text, cb, kind="primary", **k):
    bgk, fgk = KINDS[kind]
    g = globals()
    b = RBtn(text=text, bg=list(g[bgk]), color=WHITE if fgk == "W" else g[fgk], **k)
    b.bind(on_release=lambda *_: cb())
    return b


def small(text, cb, kind="muted", w=48, **k):
    return btn(text, cb, kind, size_hint_x=None, width=dp(w), **k)


def pop(title, content, h=None, w=.92):
    return Popup(title=title, content=content, size_hint=(w, None if h else .8), height=dp(h or 100), background="",
                 background_color=list(CARD), title_color=TX, separator_color=AC, auto_dismiss=False)


def msg(title, text, h=None):
    b = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
    b.add_widget(lbl(text, 14))
    n = len(text) // 38 + text.count("\n") + 1
    p = pop(title, b, h or min(max(190, 130 + n * 24), 480))
    b.add_widget(btn("OK", p.dismiss))
    p.open()
    return p


def ask(title, text, yes, yes_text="Yes", kind="danger"):
    b = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
    b.add_widget(lbl(text, 14))
    n = len(text) // 38 + text.count("\n") + 1
    p = pop(title, b, min(max(210, 150 + n * 24), 500))
    b.add_widget(row(btn("Cancel", p.dismiss, "muted"), btn(yes_text, lambda: (p.dismiss(), yes()), kind)))
    p.open()


def prompt(title, hint, done, password=True, text=""):
    b = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
    t = inp(hint, text, password=password)
    b.add_widget(t)
    p = pop(title, b, 220)
    b.add_widget(row(btn("Cancel", p.dismiss, "muted"), btn("OK", lambda: (p.dismiss(), done(t.text)))))
    p.open()


def info(title, text):
    b = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
    sv = ScrollView()
    sv.add_widget(lbl(text, 13))
    b.add_widget(sv)
    p = pop(title, b)
    b.add_widget(btn("Close", p.dismiss))
    p.open()


def grow(bar, val, delay=.2):
    Clock.schedule_once(lambda d: Animation(value=val, d=.8, t="out_cubic").start(bar), delay)


# ---------- pure helpers ----------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(s):
    return bool(EMAIL_RE.match(s or ""))


def valid_mobile(s):
    return bool(re.fullmatch(r"\+?\d{10,15}", s or ""))


def valid_enroll(s):
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-_/.]{2,29}", s or ""))


def vd(x):
    try:
        dt.date.fromisoformat(x)
        return True
    except Exception:
        return False


def today():
    return dt.date.today().isoformat()


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def calc(p, a, l, mode="total"):
    """Return (total, percent). mode 'total': leave counts in total (Present/(P+A+L)); 'excluded': old SmartHazri (P/(P+A))."""
    t = p + a + l if mode == "total" else p + a
    return t, (p * 100.0 / t if t else 0.0)


def pstr(pc, t):
    return "%.2f%%" % pc if t else "-"


def class_label(c, batch=None):
    if (c.get("kind") or "college") == "school":
        s = str(c.get("branch") or "")
        s += "" if c.get("section") in (None, "", "-") else " | Sec " + str(c["section"])
    else:
        s = "%s | %s Year | Sem %s | Sec %s" % (c.get("branch"), c.get("year"), c.get("semester"), c.get("section"))
    b = batch if batch is not None else c.get("batch")
    return s + (" | " + b if b else "")


def initials(name):
    p = (name or "?").split()
    return ((p[0][:1] + (p[-1][:1] if len(p) > 1 else "")) or "?").upper()


def sid_for(class_id, subject_id, date, batch):
    return str(uuid.uuid5(NS, "%s|%s|%s|%s" % (class_id, subject_id, date, batch)))


def rid_for(session_id, student_id):
    return str(uuid.uuid5(NS, "%s|%s" % (session_id, student_id)))


class NetError(Exception):
    pass


class ApiError(Exception):
    def __init__(self, status, msg, code=""):
        super().__init__(msg)
        self.status, self.msg, self.code = status, msg, code


def friendly(e):
    if isinstance(e, NetError):
        return "Server se connect nahi ho paaya (internet / SSL / permission). Changes phone me safe hain, net aate hi sync honge.\n\nDetail: %s" % str(e)[:160]
    if isinstance(e, ApiError):
        m, c = (e.msg or "").lower(), str(e.code or "")
        if c == "PGRST202" or "could not find the function" in m:
            return "Supabase me database setup adhura hai. supabase_setup.sql ko Supabase SQL Editor me poora run karo."
        if "invalid login" in m or c == "invalid_credentials":
            return "Wrong email/ID or password."
        if "already registered" in m or c in ("user_already_exists", "email_exists"):
            return "This email is already registered."
        if c == "23505" or "duplicate key" in m:
            return "This record already exists (duplicate)."
        if c == "23503":
            return "This item is linked to other records, so it cannot be removed."
        if c == "42501" or e.status == 403:
            return "You do not have permission for this action."
        if e.status == 429 or "rate limit" in m:
            return "Too many attempts. Please wait a few minutes and try again."
        if "not confirmed" in m:
            return "Please confirm your email first (check your inbox), then login."
        if "password" in m and any(x in m for x in ("least", "weak", "short", "characters")):
            return "Password is too weak. Use at least 6 characters."
        if "token" in m and any(x in m for x in ("expired", "invalid")):
            return "The code is wrong or expired. Request a new one."
        if "database error saving new user" in m:
            return "Could not create the account. Email or enrollment number may already be in use."
        if "same" in m and "password" in m:
            return "New password must be different from the old one."
        if "sending" in m and "email" in m or c in ("unexpected_failure", "over_email_send_rate_limit"):
            return ("Supabase email bhej nahi paa raha. Supabase > Authentication > Sign In / Providers > Email me 'Confirm email' OFF karo "
                    "(ya email rate limit ruk ka intezaar karo).\n\nServer: %s" % (e.msg or "")[:140])
        if e.status >= 500:
            return "Server problem. Dobara try karo.\n\nServer: %s" % (e.msg or c or e.status)[:160]
        return e.msg or "Something went wrong."
    return "Something went wrong: %s" % e


def make_csv(head, rows):
    o = io.StringIO()
    w = csv.writer(o)
    w.writerow(head)
    w.writerows(rows)
    return o.getvalue().encode("utf-8-sig")


def _pe(s):
    return str(s).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1", "replace").decode("latin-1")


def make_pdf(title, sub, head, rows, widths=None):
    """Tiny dependency-free PDF table writer (A4 landscape, Helvetica)."""
    W, H, M, per = 842, 595, 36, 27
    n = len(head)
    widths = widths or [1] * n
    tot, xs, x = float(sum(widths)), [], float(M)
    for w in widths:
        xs.append(x)
        x += (W - 2 * M) * w / tot
    cw = [(W - 2 * M) * w / tot for w in widths]
    pages = [rows[i:i + per] for i in range(0, len(rows), per)] or [[]]
    out, offs = [b"%PDF-1.4\n"], []

    def add(body):
        offs.append(sum(len(z) for z in out))
        out.append(("%d 0 obj\n" % len(offs)).encode() + body + b"\nendobj\n")

    kids = " ".join("%d 0 R" % (5 + 2 * i) for i in range(len(pages)))
    add(b"<< /Type /Catalog /Pages 2 0 R >>")
    add(("<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(pages))).encode())
    add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    for pi, pg in enumerate(pages):
        ops = ["BT /F2 15 Tf %d %d Td (%s) Tj ET" % (M, H - 36, _pe(title)),
               "BT /F1 9 Tf %d %d Td (%s  -  page %d/%d) Tj ET" % (M, H - 52, _pe(sub), pi + 1, len(pages))]
        y = H - 78

        def line(vals, font, y):
            for i, v in enumerate(vals):
                s = str(v)
                mx = max(3, int(cw[i] / 4.7))
                s = s if len(s) <= mx else s[:mx - 1] + "."
                ops.append("BT /%s 9 Tf %.1f %d Td (%s) Tj ET" % (font, xs[i], y, _pe(s)))

        line(head, "F2", y)
        ops.append("%d %d m %d %d l S" % (M, y - 4, W - M, y - 4))
        for r in pg:
            y -= 16
            line(r, "F1", y)
        st = "\n".join(ops).encode("latin-1", "replace")
        add(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>"
             % (W, H, 6 + 2 * pi)).encode())
        add(b"<< /Length %d >>\nstream\n" % len(st) + st + b"\nendstream")
    xo = sum(len(z) for z in out)
    out.append(("xref\n0 %d\n0000000000 65535 f \n" % (len(offs) + 1)).encode())
    for o in offs:
        out.append(("%010d 00000 n \n" % o).encode())
    out.append(("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(offs) + 1, xo)).encode())
    return b"".join(out)


# ---------- local database (SQLite cache + outbox) ----------
SCHEMA = {
    "profiles": ["id", "role", "first_name", "last_name", "full_name", "email", "mobile", "is_active", "created_at", "updated_at"],
    "classes": ["id", "kind", "branch", "year", "semester", "section", "created_at", "updated_at"],
    "subjects": ["id", "code", "name", "created_at", "updated_at"],
    "students": ["id", "enrollment", "class_id", "batch", "college_name", "mentor_id", "created_at", "updated_at"],
    "teachers": ["id", "employee_id", "department", "subject_note", "created_at", "updated_at"],
    "class_subjects": ["id", "class_id", "subject_id", "teacher_id", "created_at", "updated_at"],
    "student_subjects": ["id", "student_id", "subject_id", "created_at", "updated_at"],
    "attendance_sessions": ["id", "class_id", "subject_id", "date", "batch", "marked_by", "created_at", "updated_at"],
    "attendance_records": ["id", "session_id", "student_id", "status", "remark", "marked_by", "created_at", "updated_at"],
    "notifications": ["id", "user_id", "title", "body", "kind", "is_read", "created_at", "updated_at"],
    "leave_requests": ["id", "student_id", "from_date", "to_date", "reason", "status", "decided_by", "created_at", "updated_at"],
}
INT_COLS = {"is_active", "is_read"}
SYS_COLS = ("created_at", "updated_at")


def wcols(t):
    return [c for c in SCHEMA[t] if c not in SYS_COLS]


class Db:
    def __init__(self, path):
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        for t, cols in SCHEMA.items():
            defs = ["id TEXT PRIMARY KEY"] + ["%s %s" % (c, "INTEGER" if c in INT_COLS else "TEXT") for c in cols if c != "id"]
            self.con.execute("CREATE TABLE IF NOT EXISTS %s(%s)" % (t, ",".join(defs)))
        self.con.executescript("""
        CREATE UNIQUE INDEX IF NOT EXISTS u_classes ON classes(kind,branch,year,semester,section);
        CREATE UNIQUE INDEX IF NOT EXISTS u_sess ON attendance_sessions(class_id,subject_id,date,batch);
        CREATE UNIQUE INDEX IF NOT EXISTS u_rec ON attendance_records(session_id,student_id);
        CREATE UNIQUE INDEX IF NOT EXISTS u_csub ON class_subjects(class_id,subject_id);
        CREATE UNIQUE INDEX IF NOT EXISTS u_ssub ON student_subjects(student_id,subject_id);
        CREATE INDEX IF NOT EXISTS i_stu_class ON students(class_id,batch);
        CREATE INDEX IF NOT EXISTS i_rec_stu ON attendance_records(student_id,status);
        CREATE INDEX IF NOT EXISTS i_sess_date ON attendance_sessions(date);
        CREATE INDEX IF NOT EXISTS i_notif ON notifications(user_id,created_at);
        CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE IF NOT EXISTS avatars(id TEXT PRIMARY KEY, b64 TEXT);
        CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, target TEXT, payload TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS sync_errors(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, what TEXT, err TEXT);
        """)
        self.con.commit()

    def q(self, sql, a=()):
        with self.lock:
            c = self.con.execute(sql, a)
            self.con.commit()
            return c.fetchall()

    def rows(self, sql, a=()):
        with self.lock:
            c = self.con.execute(sql, a)
            cols = [d[0] for d in c.description] if c.description else []
            r = c.fetchall()
        return [dict(zip(cols, x)) for x in r]

    def one(self, sql, a=()):
        r = self.rows(sql, a)
        return r[0] if r else None

    def kget(self, k, d=""):
        r = self.q("SELECT v FROM kv WHERE k=?", (k,))
        return r[0][0] if r else d

    def kset(self, k, v):
        self.q("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, str(v)))

    def kdel(self, k):
        self.q("DELETE FROM kv WHERE k=?", (k,))

    @staticmethod
    def _v(v):
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, (dict, list)):
            return json.dumps(v)
        return v

    def put(self, t, rows):
        """Insert or replace rows unconditionally."""
        if not rows:
            return
        cols = SCHEMA[t]
        with self.lock:
            self.con.executemany("INSERT OR REPLACE INTO %s(%s) VALUES(%s)" % (t, ",".join(cols), ",".join("?" * len(cols))),
                                 [tuple(self._v(r.get(c)) for c in cols) for r in rows])
            self.con.commit()

    def put_new(self, t, rows):
        """Insert/replace only rows whose updated_at differs from local copy. Returns number of changed rows."""
        if not rows:
            return 0
        have, ids = {}, [r["id"] for r in rows]
        with self.lock:
            for i in range(0, len(ids), 400):
                ch = ids[i:i + 400]
                for rid, ua in self.con.execute("SELECT id,updated_at FROM %s WHERE id IN (%s)" % (t, ",".join("?" * len(ch))), ch):
                    have[rid] = ua
        todo = [r for r in rows if have.get(r["id"]) != r.get("updated_at")]
        self.put(t, todo)
        return len(todo)

    def delete_ids(self, t, ids):
        ids = list(ids)
        with self.lock:
            for i in range(0, len(ids), 400):
                ch = ids[i:i + 400]
                self.con.execute("DELETE FROM %s WHERE id IN (%s)" % (t, ",".join("?" * len(ch))), ch)
            self.con.commit()

    def wipe(self):
        with self.lock:
            for t in SCHEMA:
                self.con.execute("DELETE FROM " + t)
            self.con.execute("DELETE FROM avatars")
            self.con.execute("DELETE FROM outbox")
            self.con.execute("DELETE FROM sync_errors")
            self.con.execute("DELETE FROM kv WHERE k LIKE 'cur:%'")
            self.con.commit()

    def enqueue(self, kind, target, payload):
        self.q("INSERT INTO outbox(kind,target,payload,created) VALUES(?,?,?,?)", (kind, target, json.dumps(payload), now_iso()))

    def pending(self):
        return self.q("SELECT COUNT(*) FROM outbox")[0][0]


# ---------- Supabase REST/Auth client (no SDK, plain urllib) ----------
def make_ctx():
    """TLS context WITH certificate verification. Android Python often has no CA bundle, so try certifi, then system CAs."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    ctx = ssl.create_default_context()
    for p in ("/system/etc/security/cacerts", "/apex/com.android.conscrypt/cacerts"):
        try:
            if os.path.isdir(p):
                ctx.load_verify_locations(capath=p)
                break
        except Exception:
            pass
    return ctx


CTX = make_ctx()


class Api:
    def __init__(self, db):
        self.db = db
        self.lock = threading.Lock()
        self.sess = None
        try:
            s = db.kget("session")
            self.sess = json.loads(s) if s else None
        except Exception:
            self.sess = None

    # ----- low level -----
    def _req(self, method, path, body=None, token=None, headers=None, timeout=20):
        h = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
        if token:
            h["Authorization"] = "Bearer " + token
        h.update(headers or {})
        data = None if body is None else json.dumps(body).encode("utf-8")
        for attempt in range(3):
            try:
                return self._send(method, path, data, h, timeout)
            except urllib.error.HTTPError:
                raise
            except urllib.error.URLError as e:
                if attempt < 2 and isinstance(e.reason, (ConnectionRefusedError, socket.gaierror)):
                    time.sleep(1.0 + attempt)
                    continue
                raise NetError(str(e))
            except (OSError, socket.timeout, ssl.SSLError) as e:
                raise NetError(str(e))

    def _send(self, method, path, data, h, timeout):
        req = urllib.request.Request(SUPABASE_URL + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                txt = r.read().decode("utf-8")
                return (json.loads(txt) if txt else None), r.headers
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                j = json.loads(raw)
            except Exception:
                j = {}
            if not isinstance(j, dict):
                j = {}
            m = j.get("message") or j.get("msg") or j.get("error_description") or j.get("error") or raw[:200]
            raise ApiError(e.code, str(m), str(j.get("code") or j.get("error_code") or ""))
        except ValueError as e:
            raise ApiError(0, "Bad response from server: %s" % e)

    # ----- session -----
    def save(self, s):
        self.sess = s
        if s:
            self.db.kset("session", json.dumps(s))
        else:
            self.db.kdel("session")

    def store(self, d):
        u = d.get("user") or {}
        self.save({"access_token": d["access_token"], "refresh_token": d.get("refresh_token", ""),
                   "expires_at": time.time() + int(d.get("expires_in", 3600)), "user_id": u.get("id", ""), "email": u.get("email", "")})

    def refresh(self):
        s = self.sess
        if not s or not s.get("refresh_token"):
            self.save(None)
            raise ApiError(401, "Session expired. Please login again.", "session_expired")
        try:
            d, _ = self._req("POST", "/auth/v1/token?grant_type=refresh_token", {"refresh_token": s["refresh_token"]})
        except ApiError as e:
            if e.status in (400, 401, 403):
                self.save(None)
                raise ApiError(401, "Session expired. Please login again.", "session_expired")
            raise
        self.store(d)

    def token(self):
        with self.lock:
            if not self.sess:
                raise ApiError(401, "Please login first.", "session_expired")
            if self.sess["expires_at"] - time.time() < 90:
                self.refresh()
            return self.sess["access_token"]

    def rest(self, method, path, body=None, headers=None):
        """Authenticated request to /rest/v1/... Returns (data, response_headers)."""
        for attempt in (0, 1):
            tok = self.token()
            try:
                return self._req(method, path, body, tok, headers)
            except ApiError as e:
                if e.status == 401 and attempt == 0:
                    with self.lock:
                        self.refresh()
                    continue
                if e.status == 401:
                    self.save(None)
                    raise ApiError(401, "Session expired. Please login again.", "session_expired")
                raise

    def rpc(self, fn, args):
        return self.rest("POST", "/rest/v1/rpc/" + fn, args)[0]

    def rpc_anon(self, fn, args):
        return self._req("POST", "/rest/v1/rpc/" + fn, args)[0]

    # ----- auth -----
    def login(self, email, pw):
        d, _ = self._req("POST", "/auth/v1/token?grant_type=password", {"email": email.strip().lower(), "password": pw})
        self.store(d)
        return d

    def signup(self, email, pw, meta):
        d, _ = self._req("POST", "/auth/v1/signup", {"email": email.strip().lower(), "password": pw, "data": meta})
        return d or {}

    def recover(self, email):
        self._req("POST", "/auth/v1/recover", {"email": email.strip().lower()})

    def verify_recovery(self, email, token):
        d, _ = self._req("POST", "/auth/v1/verify", {"type": "recovery", "email": email.strip().lower(), "token": token.strip()})
        self.store(d)

    def set_password(self, pw):
        self.rest_auth("PUT", "/auth/v1/user", {"password": pw})

    def rest_auth(self, method, path, body):
        tok = self.token()
        return self._req(method, path, body, tok)

    def logout(self):
        try:
            if self.sess:
                self._req("POST", "/auth/v1/logout", None, self.sess["access_token"], timeout=6)
        except Exception:
            pass
        self.save(None)


# ===================== SmartHazri v4 helpers (kept, extended for Supabase) =====================
NONE_T = "(koi nahi)"
SQ = ("SELECT s.id, p.full_name, p.first_name, p.last_name, p.email, p.mobile, p.is_active, s.enrollment AS roll, s.batch, "
      "s.college_name, s.mentor_id, s.class_id, c.kind AS inst, c.branch, c.year, c.semester AS sem, c.section AS sec, c.branch AS cls "
      "FROM students s JOIN profiles p ON p.id=s.id JOIN classes c ON c.id=s.class_id")
PULL_ORDER = ["classes", "subjects", "profiles", "students", "teachers", "class_subjects", "student_subjects",
              "attendance_sessions", "attendance_records", "notifications", "leave_requests"]


def log(e=None, where=""):
    try:
        path = os.path.join(App.get_running_app().user_data_dir, "error.log")
        if os.path.exists(path) and os.path.getsize(path) > 120000:
            os.remove(path)
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s %s\n%s\n" % (now_iso(), where, "".join(traceback.format_exception(type(e), e, e.__traceback__)) if e else traceback.format_exc()))
    except Exception:
        pass


class Guard(ExceptionHandler):
    """Last line of defence: an unexpected error shows a message instead of closing the app."""

    def handle_exception(self, inst):
        try:
            app = App.get_running_app()
            log(inst, "guard")
            app.toast("Kuch gadbad hui: %s" % str(inst)[:80], NO)
        except Exception:
            pass
        return ExceptionManager.PASS


def fullname(u):
    return (u.get("full_name") or ("%s %s" % (u.get("first_name", ""), u.get("last_name", ""))).strip() or "?")


def bval(d):
    return d.get("branch_o", "").strip().upper() if d.get("branch") == "Other" else d.get("branch", "")


def cname(d):
    c = str(d.get("cls") or "")
    return c if c.startswith("Class") else "Class " + c


def glabel(d):
    if (d.get("inst") or "college") == "college":
        s = "%s | %s Year | Sem %s | Sec %s" % (bval(d), d.get("year"), d.get("sem"), d.get("sec"))
        b = d.get("batch")
        return s + ("" if not b or b == "All" else " | " + b)
    s = cname(d)
    sec = d.get("sec")
    return s + (" | All sections" if sec == "All" else "" if sec in ("-", "", None) else " | Sec " + sec)


def gwhere(d):
    """SQL filter on SQ (aliases s, c) for the class selected in state d. 'All' = no filter."""
    w, a = ["c.kind=?"], [d.get("inst", "college")]

    def add(col, v):
        if v and v != "All":
            w.append(col + "=?")
            a.append(v)

    if d.get("inst", "college") == "college":
        add("c.branch", bval(d))
        add("c.year", d.get("year"))
        add("c.semester", d.get("sem"))
        add("c.section", d.get("sec"))
        add("s.batch", d.get("batch"))
    else:
        add("c.branch", None if d.get("cls") == "All" else cname(d))
        add("c.section", d.get("sec"))
    return " AND ".join(w), a


def new_state():
    return dict(inst="college", branch="CSE", branch_o="", year="1st", sem="1", sec="A", batch="All", cls="1")


def all_state():
    return dict(new_state(), branch="All", year="All", sem="All", sec="All", batch="All", cls="All")


def reg_state():
    return dict(new_state(), role="student", photo_src="", email="", pw="", pw2="", name="", surname="", mobile="", roll="",
                college_name="", subject="", dept="", empid="", tcode="", batch="B1")


def class_fields(st, sel, rebuild):
    """College: branch/year/semester/section/batch. School: class/section.
    sel=False: no 'All' | 'batch': 'All' only for batch | 'all': 'All' everywhere."""
    ws = []

    def add(label, key, values, allow, cb=None):
        ws.append(lbl(label, 12, MU))
        ws.append(spin(st, key, (["All"] if allow else []) + list(values), cb))

    a_all, a_b = sel == "all", sel in ("all", "batch")
    if st["inst"] == "college":
        add("Branch", "branch", BRANCHES, a_all, rebuild)
        if st["branch"] == "Other":
            ws.append(tin(st, "branch_o", "Apni branch likho (jaise CIVIL)"))
        add("Year", "year", YEARS, a_all)
        add("Semester", "sem", SEMS, a_all)
        add("Section", "sec", SECS, a_all)
        add("Batch", "batch", BATCHES, a_b)
    else:
        add("Class", "cls", CLASSES, a_all)
        add("Section", "sec", SSECS, a_all)
    return ws


def fld(c, st, label, key, **k):
    c.add_widget(lbl(label, 12, MU))
    c.add_widget(tin(st, key, label, **k))


class SmartHazri(App):
    title = "SmartHazri"

    # ---------- setup ----------
    def build(self):
        Window.clearcolor = BG
        Window.softinput_mode = "below_target"
        Builder.load_string(KV)
        calendar.setfirstweekday(calendar.SUNDAY)
        ExceptionManager.add_handler(Guard())
        self.d = Db(os.path.join(self.user_data_dir, "smarthazri_cloud.db"))
        self.api = Api(self.d)
        self.lm = self.d.kget("lm", "total")
        self.thr = int(self.d.kget("thr", "75") or 75)
        self.every = int(self.d.kget("every", "30") or 30)
        self.status, self.sync_msg, self.syncing, self.recon = "offline", "", False, set()
        self.me, self.tab, self.sub, self.hz, self.rep, self.chip = None, 0, None, False, False, None
        self.grp, self.sf, self.ns, self.ed = new_state(), all_state(), reg_state(), None
        self.rf = dict(subject="All", d1=today()[:8] + "01", d2=today(), q="")
        self.mk = dict(date=today(), subject="")
        self.hf = dict(subject="All", d1="", d2="", st="All")
        self.show_add, self.q, self.tex, self.last_unread = False, "", {}, -1
        t0 = dt.date.today()
        self.cm = (t0.year, t0.month)
        self.root_fl = FloatLayout()
        self.main = BoxLayout(orientation="vertical")
        self.root_fl.add_widget(self.main)
        self.loader = Loader()
        Window.bind(on_keyboard=self.on_key)
        u = self.load_me() if (self.api.sess and configured()) else None
        if u:
            self.portal()
        else:
            self.login_screen()
        self.timer = Clock.schedule_interval(self.tick, self.every)
        Clock.schedule_once(self.tick, 1.5)
        return self.root_fl

    def on_pause(self):
        return True

    def on_resume(self):
        Clock.schedule_once(self.tick, .5)

    def on_stop(self):
        try:
            if self.d.kget("remember", "1") == "0":
                self.api.save(None)
        except Exception:
            pass

    def on_key(self, w, key, *a):
        if key == 27:
            if self.sub:
                self.sub = None
                self.refresh()
                return True
            if self.me and self.tab != 0:
                self.go(0)
                return True
        return False

    # ---------- small data helpers ----------
    def rows(self, sql, a=()):
        return self.d.rows(sql, a)

    def db(self, sql, a=()):
        return self.d.q(sql, a)

    def uid(self):
        return self.me["id"] if self.me else ""

    def staff(self):
        return bool(self.me) and self.me["role"] in ("teacher", "admin")

    def load_me(self):
        uid = self.api.sess["user_id"] if self.api.sess else ""
        p = self.d.one("SELECT * FROM profiles WHERE id=?", (uid,)) if uid else None
        if not p:
            return None
        extra = self.d.one(SQ + " WHERE s.id=?", (uid,)) if p["role"] == "student" else self.d.one("SELECT * FROM teachers WHERE id=?", (uid,))
        self.me = dict(extra or {}, **p)
        return self.me

    def stat(self, sid, sub=None, d1=None, d2=None):
        sql = "SELECT r.status,COUNT(*) FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id WHERE r.student_id=?"
        a = [sid]
        if sub and sub != "All":
            sql += " AND s.subject_id=?"
            a.append(sub)
        if d1:
            sql += " AND s.date>=?"
            a.append(d1)
        if d2:
            sql += " AND s.date<=?"
            a.append(d2)
        r = dict(self.db(sql + " GROUP BY r.status", a))
        return self.mkstat(r.get("P", 0), r.get("A", 0), r.get("L", 0))

    def mkstat(self, p, a, l):
        t, pc = calc(p, a, l, self.lm)
        return p, a, l, t, pc

    def students(self, d, q="", active=None):
        w, a = gwhere(d)
        sql = SQ + " WHERE p.role='student' AND " + w
        if q.strip():
            x = "%" + q.strip().lower() + "%"
            sql += " AND (lower(p.full_name) LIKE ? OR lower(s.enrollment) LIKE ? OR lower(p.email) LIKE ? OR p.mobile LIKE ?)"
            a += [x, x, x, x]
        return self.rows(sql + " ORDER BY length(s.enrollment), s.enrollment, p.full_name", a)

    def find_class(self, d):
        if d.get("inst", "college") == "college":
            k = ("college", bval(d), d["year"], d["sem"], d["sec"])
        else:
            k = ("school", cname(d), "-", "-", d["sec"] if d["sec"] != "All" else "-")
        return self.d.one("SELECT * FROM classes WHERE kind=? AND branch=? AND year=? AND semester=? AND section=?", k)

    def ensure_class(self, d):
        c = self.find_class(d)
        if c:
            return c["id"]
        col = d.get("inst", "college") == "college"
        c = dict(id=str(uuid.uuid4()), kind="college" if col else "school", branch=bval(d) if col else cname(d),
                 year=d["year"] if col else "-", semester=d["sem"] if col else "-", section=d["sec"] if d["sec"] != "All" else "-",
                 created_at=now_iso(), updated_at=now_iso())
        self.d.put("classes", [c])
        self.d.enqueue("upsert", "classes", {k: c[k] for k in wcols("classes")})
        return c["id"]

    def subjects_for(self, class_id):
        r = []
        if class_id:
            r = self.rows("SELECT s.* FROM class_subjects cs JOIN subjects s ON s.id=cs.subject_id WHERE cs.class_id=? ORDER BY s.name", (class_id,))
        return r or self.rows("SELECT * FROM subjects ORDER BY name")

    def sname(self, sid):
        r = self.d.one("SELECT code,name FROM subjects WHERE id=?", (sid,))
        return ("%s - %s" % (r["code"], r["name"])) if r else "?"

    def pending_leaves(self):
        return self.db("SELECT COUNT(*) FROM leave_requests WHERE status='pending'")[0][0]

    def unread(self):
        return self.db("SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (self.uid(),))[0][0]

    # ---------- threads, loader, toast ----------
    def bg(self, fn, done):
        def run():
            try:
                r, e = fn(), None
            except Exception as ex:
                r, e = None, ex
            Clock.schedule_once(lambda d: done(r, e))
        threading.Thread(target=run, daemon=True).start()

    def loading(self, on, text="Please wait..."):
        if on:
            self.loader.text = text
            if not self.loader.parent:
                self.root_fl.add_widget(self.loader)
                self.loader.start()
        elif self.loader.parent:
            self.loader.stop()
            self.root_fl.remove_widget(self.loader)

    def net(self, fn, ok, text="Please wait...", err=None):
        """Run fn() in a background thread with a loading indicator; ok(result) on success, friendly message on error."""
        if text:
            self.loading(True, text)

        def done(r, e):
            self.loading(False)
            if e:
                log(e, "net")
                if isinstance(e, ApiError) and e.code == "session_expired":
                    return self.session_lost()
                return err(e) if err else msg("Error", friendly(e))
            try:
                ok(r)
            except Exception as ex:
                log(ex, "net-ok")
                msg("Error", "Kuch gadbad hui: %s" % ex)
        self.bg(fn, done)

    def toast(self, text, col=None):
        c = Cell(text=text, bg=list(col or TX), color=WHITE, size_hint=(.92, None), pos_hint={"center_x": .5}, y=dp(74),
                 padding=[dp(12), dp(8)], font_size=sp(13), halign="center", valign="middle")
        c.bind(width=lambda i, v: setattr(i, "text_size", (v - dp(24), None)))
        c.bind(texture_size=lambda i, s: setattr(i, "height", s[1] + dp(16)))
        self.root_fl.add_widget(c)
        Clock.schedule_once(lambda d: Animation(opacity=0, d=.5).start(c), 3)
        Clock.schedule_once(lambda d: self.root_fl.remove_widget(c) if c.parent else None, 3.6)

    # ---------- background sync (Supabase) ----------
    def set_status(self, s):
        self.status = s
        if self.chip:
            lab, col = {"online": ("Online", OK), "offline": ("Offline", MU), "syncing": ("Syncing...", AC),
                        "synced": ("Synced", OK), "failed": ("Sync Failed", NO)}[s]
            self.chip.text, self.chip.bg = lab, list(col)

    def tick(self, *_):
        self.sync_now()

    def sync_now(self):
        if self.syncing or not self.api.sess or not configured():
            return
        self.syncing = True
        self.set_status("syncing")
        self.bg(self.sync_job, self.sync_done)

    def sync_job(self):
        sent, errs = self.flush_outbox()
        if self.recon and not self.d.pending():
            for t in list(self.recon):
                self.reconcile(t)
                self.recon.discard(t)
        ch = self.pull_all()
        me = self.d.one("SELECT is_active FROM profiles WHERE id=?", (self.api.sess["user_id"],)) if self.api.sess else None
        if self.api.sess and not self.d.one("SELECT 1 FROM avatars WHERE id=?", (self.api.sess["user_id"],)):
            self.fetch_avatar(self.api.sess["user_id"])
        return dict(sent=sent, errs=errs, changed=ch, disabled=bool(me) and not me["is_active"])

    def sync_done(self, r, e):
        self.syncing = False
        if e:
            if isinstance(e, NetError):
                self.set_status("offline")
                self.sync_msg = "Offline - internet aate hi apne aap sync hoga."
            elif isinstance(e, ApiError) and e.code == "session_expired":
                return self.session_lost()
            else:
                log(e, "sync")
                self.set_status("failed")
                self.sync_msg = "Sync fail: " + friendly(e)
            return
        if r["disabled"]:
            return self.force_logout("Aapka account disable kar diya gaya hai. Teacher se baat karo.")
        if r["errs"]:
            self.set_status("failed")
            self.toast("%d change cloud ne accept nahi kiya (Profile > Sync me dekho)." % r["errs"], NO)
        else:
            self.set_status("synced")
        self.sync_msg = "Last sync: " + dt.datetime.now().strftime("%I:%M:%S %p")
        if r["changed"] or r["sent"]:
            self.after_sync()


    def any_popup(self):
        return any(isinstance(w, Popup) for w in Window.children)

    def after_sync(self):
        if not self.me:
            return
        self.load_me()
        self.paint_nav()
        n = self.unread()
        if self.last_unread >= 0 and n > self.last_unread:
            r = self.d.one("SELECT title,body FROM notifications WHERE user_id=? AND is_read=0 ORDER BY created_at DESC LIMIT 1", (self.uid(),))
            if r:
                self.toast("%s: %s" % (r["title"], r["body"]), AC)
        self.last_unread = n
        if self.tab == 0 and not self.sub and not self.any_popup():
            self.refresh()

    def flush_outbox(self):
        sent = errs = 0
        while True:
            ops = self.rows("SELECT * FROM outbox ORDER BY id LIMIT 50")
            if not ops:
                break
            for op in ops:
                try:
                    self.run_op(op["kind"], op["target"], json.loads(op["payload"]))
                except ApiError as e:
                    if e.code == "session_expired":
                        raise
                    if e.status >= 500 or e.status in (408, 425, 429):
                        raise NetError(e.msg)
                    errs += 1
                    self.db("INSERT INTO sync_errors(at,what,err) VALUES(?,?,?)", (now_iso(), "%s %s" % (op["kind"], op["target"]), friendly(e)))
                    self.recon.add("attendance_sessions" if op["target"] == "save_attendance" else op["target"])
                    if op["target"] == "save_attendance":
                        self.recon.add("attendance_records")
                self.db("DELETE FROM outbox WHERE id=?", (op["id"],))
                sent += 1
        return sent, errs

    def run_op(self, kind, tgt, p):
        r = self.api.rest
        if kind == "upsert":
            r("POST", "/rest/v1/%s?on_conflict=id" % tgt, p, {"Prefer": "resolution=merge-duplicates,return=minimal"})
        elif kind == "insert":
            r("POST", "/rest/v1/%s?on_conflict=id" % tgt, p, {"Prefer": "resolution=ignore-duplicates,return=minimal"})
        elif kind == "patch":
            r("PATCH", "/rest/v1/%s?%s" % (tgt, p["q"]), p["values"], {"Prefer": "return=minimal"})
        elif kind == "delete":
            r("DELETE", "/rest/v1/%s?%s" % (tgt, p["q"]))
        elif kind == "rpc":
            self.api.rpc(tgt, p)

    @staticmethod
    def cursor(hdr):
        try:
            t = email.utils.parsedate_to_datetime(hdr.get("Date"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.timezone.utc)
        except Exception:
            t = dt.datetime.now(dt.timezone.utc)
        return (t - dt.timedelta(minutes=10)).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    def fetch_pages(self, path, first_hdr=None):
        out, off, hdr0 = [], 0, None
        while True:
            data, hdr = self.api.rest("GET", path + ("&" if "?" in path else "?") + "limit=1000&offset=%d" % off)
            hdr0 = hdr0 or hdr
            out += data or []
            if not data or len(data) < 1000:
                return out, hdr0
            off += 1000

    def pull_all(self):
        changed = 0
        cur = self.d.kget("cur:tomb")
        if cur:
            try:
                age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(cur)
                if age.days > 150 and not self.d.pending():
                    self.d.wipe()
                    cur = ""
            except Exception:
                pass
        if cur:
            rows, hdr = self.fetch_pages("/rest/v1/tombstones?select=table_name,row_id&order=id.asc&deleted_at=gte." + urllib.parse.quote(cur, safe=""))
        else:
            rows, hdr = [], self.api.rest("GET", "/rest/v1/tombstones?select=id&limit=1")[1]
        if cur:
            by = {}
            for r in rows:
                by.setdefault(r["table_name"], []).append(r["row_id"])
            for t, ids in by.items():
                if t in SCHEMA:
                    self.d.delete_ids(t, ids)
                    changed += len(ids)
                if t == "profiles":
                    self.d.delete_ids("avatars", ids)
        self.d.kset("cur:tomb", self.cursor(hdr))
        for t in PULL_ORDER:
            cur = self.d.kget("cur:" + t)
            path = "/rest/v1/%s?select=%s&order=updated_at.asc,id.asc" % (t, ",".join(SCHEMA[t]))
            if cur:
                path += "&updated_at=gte." + urllib.parse.quote(cur, safe="")
            rows, hdr = self.fetch_pages(path)
            changed += self.d.put_new(t, rows)
            self.d.kset("cur:" + t, self.cursor(hdr))
        return changed

    def reconcile(self, t):
        """After a rejected upload: make the local copy of table t equal to the server again."""
        if t not in SCHEMA:
            return
        rows, _ = self.fetch_pages("/rest/v1/%s?select=%s&order=id.asc" % (t, ",".join(SCHEMA[t])))
        self.d.put(t, rows)
        keep = {r["id"] for r in rows}
        self.d.delete_ids(t, [r[0] for r in self.db("SELECT id FROM %s" % t) if r[0] not in keep])

    def fetch_avatar(self, uid):
        try:
            r, _ = self.api.rest("GET", "/rest/v1/profiles?id=eq.%s&select=avatar" % uid)
            self.db("INSERT OR REPLACE INTO avatars VALUES(?,?)", (uid, (r[0].get("avatar") if r else "") or ""))
        except (NetError, ApiError):
            pass

    # ---------- page scaffolding (same as v4) ----------
    def new_page(self):
        sv = ScrollView(bar_width=dp(3))
        g = GridLayout(cols=1, size_hint_y=None, spacing=dp(10), padding=[dp(12), dp(10), dp(12), dp(16)])
        g.bind(minimum_height=g.setter("height"))
        sv.add_widget(g)
        return sv, g

    def fade(self, g):
        for i, w in enumerate(reversed(g.children)):
            w.opacity = 0
            Clock.schedule_once(lambda d, w=w: Animation(opacity=1, d=.4, t="out_quad").start(w), min(i, 10) * .06)

    def show(self, fn, anim=True):
        self.holder.clear_widgets()
        sv, g = self.new_page()
        try:
            fn(g)
        except Exception as e:
            log(e, "page")
            g.clear_widgets()
            c = Card()
            c.add_widget(lbl("Ye page nahi khul paya", 16, NO, True))
            c.add_widget(lbl(str(e)[:160], 12, MU))
            c.add_widget(btn("Home par jao", lambda: self.go(0)))
            g.add_widget(c)
        self.holder.add_widget(sv)
        if anim:
            self.fade(g)

    def refresh(self):
        if self.me:
            self.show(self.sub or self.tabs[self.tab][1], anim=False)

    def open_sub(self, fn):
        self.sub = fn
        self.show(fn)

    def back_card(self, g, text="< Wapas"):
        g.add_widget(btn(text, lambda: (setattr(self, "sub", None), self.refresh()), "ghost", size_hint_y=None, height=dp(40)))

    # ---------- portal / navigation ----------
    def portal(self):
        self.main.clear_widgets()
        T = self.staff()
        self.tabs = ([("Home", self.t_home), ("Hazri", self.t_mark), ("Students", self.t_students), ("Report", self.t_report),
                      ("Setup", self.t_setup), ("Me", self.profile)] if T else
                     [("Home", self.s_home), ("History", self.s_history), ("Subjects", self.s_subjects), ("Leave", self.s_leave), ("Me", self.profile)])
        self.tab, self.sub, self.hz, self.rep = 0, None, False, False
        h = Panel(orientation="horizontal", bg=AC, rad=0, size_hint_y=None, height=dp(58), padding=[dp(14), dp(8)], spacing=dp(8))
        t = Label(text="SmartHazri", font_size=sp(18), bold=True, color=WHITE, halign="left", valign="middle")
        t.bind(size=lambda i, v: setattr(i, "text_size", v))
        h.add_widget(t)
        self.chip = RBtn(text="Offline", bg=list(MU), size_hint=(None, None), size=(dp(92), dp(28)), font_size=sp(11),
                         pos_hint={"center_y": .5}, on_release=lambda *_: self.chip_tap())
        h.add_widget(self.chip)
        h.add_widget(RBtn(text="Logout", bg=[1, 1, 1, .2], size_hint_x=None, width=dp(74), on_release=lambda *_: self.logout()))
        self.main.add_widget(h)
        self.holder = BoxLayout()
        self.main.add_widget(self.holder)
        nav = Panel(orientation="horizontal", bg=WHITE, rad=0, size_hint_y=None, height=dp(54))
        self.nbtn = []
        for i, (name, fn) in enumerate(self.tabs):
            b = RBtn(text=name, bg=WHITE, height=dp(54), font_size=sp(12 if len(self.tabs) > 4 else 14), on_release=lambda *_, i=i: self.go(i))
            self.nbtn.append(b)
            nav.add_widget(b)
        self.main.add_widget(nav)
        self.set_status(self.status)
        self.paint_nav()
        self.show(self.tabs[self.tab][1])

    def chip_tap(self):
        self.sync_now()
        self.toast(self.sync_msg or "Sync shuru ho gaya...", AC)

    def paint_nav(self):
        n = self.unread()
        for i, b in enumerate(self.nbtn):
            name = self.tabs[i][0]
            badge = n if name == "Me" else (self.pending_leaves() if (name == "Setup" and self.staff()) else (0))
            b.text = name + (" (%d)" % badge if badge else "")
            b.color = AC if i == self.tab else MU

    def go(self, i):
        self.tab, self.sub = i, None
        self.paint_nav()
        self.show(self.tabs[i][1])

    def hero(self, g, u, top, name, sub=""):
        p = Panel(orientation="horizontal", bg=AC, size_hint_y=None, height=dp(116), padding=dp(14), spacing=dp(12))
        p.add_widget(self.avatar(u, 80))
        c = BoxLayout(orientation="vertical", spacing=dp(2))
        c.add_widget(lbl(top, 13, [.88, .9, 1, 1]))
        c.add_widget(lbl(name, 20, WHITE, True))
        if sub:
            c.add_widget(lbl(sub, 12, [.88, .9, 1, 1]))
        p.add_widget(c)
        g.add_widget(p)

    def selector(self, g, label, cb, st=None, sel="batch", extra=None):
        st = st if st is not None else self.grp
        c = Card()
        c.add_widget(lbl("Class chuno", 17, bold=True))
        tb = {k: RBtn(text=t, bg=list(AC if st["inst"] == k else GR), color=WHITE if st["inst"] == k else MU,
                      on_release=lambda *_, k=k: (st.__setitem__("inst", k), self.refresh())) for k, t in (("college", "College"), ("school", "School"))}
        c.add_widget(row(tb["college"], tb["school"]))
        for w in class_fields(st, sel, self.refresh):
            c.add_widget(w)
        for w in (extra() if extra else []):
            c.add_widget(w)
        c.add_widget(btn(label, cb))
        g.add_widget(c)

    # ---------- login / session ----------
    def after_auth(self):
        """Runs in a thread right after Supabase Auth succeeded (session already stored)."""
        uid = self.api.sess["user_id"]
        if self.d.kget("last_user", "") not in ("", uid):
            self.d.wipe()                      # different person on this phone: never mix their data
        self.d.kset("last_user", uid)
        p = self.bootstrap_me(uid)           # own profile first, so login never depends on the big sync
        if not p:
            self.api.save(None)
            raise ApiError(400, "Is account ka profile nahi mila. Admin se baat karo.", "no_profile")
        if not p["is_active"]:
            self.api.save(None)
            raise ApiError(400, "Aapka account disable hai. Teacher se baat karo.", "disabled")
        self.boot_err = ""
        try:
            self.sync_job()
        except NetError as e:
            self.boot_err = str(e)
        except ApiError as e:
            if e.code == "session_expired":
                raise
            log(e, "first-sync")
            self.boot_err = friendly(e)
        return uid

    def bootstrap_me(self, uid):
        """Download only the logged-in user's own rows (profile + student/teacher row + class) into the local cache."""
        def one(t, val):
            r, _ = self.api.rest("GET", "/rest/v1/%s?id=eq.%s&select=%s" % (t, val, ",".join(SCHEMA[t])))
            self.d.put(t, r or [])
            return r[0] if r else None
        p = one("profiles", uid)
        if p:
            if p["role"] == "student":
                st = one("students", uid)
                if st:
                    one("classes", st["class_id"])
            else:
                one("teachers", uid)
        return p

    def finish_login(self, _=None):
        if not self.load_me():
            return msg("Error", "Profile load nahi ho paya. Dobara try karo.")
        self.last_unread = -1
        err = getattr(self, "boot_err", "")
        if err:
            self.status, self.sync_msg = "failed", "Pehla sync adhura raha: %s" % err[:140]
        else:
            self.status, self.sync_msg = "synced", "Last sync: " + dt.datetime.now().strftime("%I:%M:%S %p")
        self.portal()
        if err:
            self.toast("Data poora load nahi hua, thodi der me apne aap try karega.", LV)
        ph = getattr(self, "pend_photo", "")
        if ph:
            self.pend_photo = ""
            self.new_photo(ph, quiet=True)
        self.last_unread = self.unread()
        Clock.schedule_once(self.tick, .5)

    def session_lost(self):
        self.api.save(None)
        self.force_logout("Session khatam ho gaya. Dobara login karo.")

    def force_logout(self, text):
        self.me, self.sub = None, None
        self.login_screen()
        msg("Login", text)

    def logout(self):
        n = self.d.pending()
        txt = "Logout karne par dobara login karna padega."
        if n:
            txt += "\n\n%d changes abhi cloud par upload nahi hue. Logout karoge to wo chali jayengi." % n
        ask("Logout", txt, self.do_logout)

    def do_logout(self):
        def work():
            try:
                if self.d.pending():
                    self.flush_outbox()
            except Exception:
                pass
            self.api.logout()
            self.d.wipe()
            self.d.kdel("last_user")

        def ok(_):
            self.me, self.sub, self.tex = None, None, {}
            self.login_screen()
        self.net(work, ok, "Logout ho raha hai...", err=lambda e: ok(None))

    def login_screen(self):
        self.chip = None
        self.main.clear_widgets()
        sv, g = self.new_page()
        if not hasattr(self, "lg"):
            self.lg = dict(u="", p="")
        g.add_widget(lbl("SmartHazri", 34, AC, True, "center"))
        g.add_widget(lbl("Digital Attendance System", 14, MU, False, "center"))
        if not configured():
            w = Card(bg=[1, .93, .93, 1])
            w.add_widget(lbl("Supabase key set nahi hai. main_v4.py ke upar SUPABASE_KEY me apni sb_publishable_ key daalo.", 13, NO, True))
            g.add_widget(w)
        c = Card()
        c.add_widget(lbl("Login", 18, bold=True))
        u = tin(self.lg, "u", "Email ya Enrollment No. / Employee ID")
        p = tin(self.lg, "p", "Password", password=True)
        c.add_widget(u)
        c.add_widget(row(p, small("Show", lambda: setattr(p, "password", not p.password), "ghost", 62)))
        rm = btn("", lambda: flip(), "ghost", size_hint_y=None, height=dp(40))

        def paint_rm():
            rm.text = "Login yaad rakho: " + ("ON" if self.d.kget("remember", "1") == "1" else "OFF")

        def flip():
            self.d.kset("remember", "0" if self.d.kget("remember", "1") == "1" else "1")
            paint_rm()
        paint_rm()
        c.add_widget(rm)
        c.add_widget(btn("Login", self.do_login))
        c.add_widget(btn("Naya account banao (Register)", self.start_register, "ghost"))
        c.add_widget(btn("Password bhool gaye?", self.forgot, "plain"))
        c.add_widget(btn("Connection check", self.conn_test, "plain"))
        g.add_widget(c)
        self.main.add_widget(sv)
        self.fade(g)

    def conn_test(self):
        def work():
            return self.api._req("GET", "/auth/v1/health", timeout=15)[0]

        def ok(d):
            msg("Connection OK", "Supabase se connection ho gaya.\n%s" % json.dumps(d)[:150])

        def err(e):
            msg("Connection fail", "%s\n\nType: %s\nDetail: %s" % (friendly(e), type(e).__name__, str(e)[:300]))
        self.net(work, ok, "Check ho raha hai...", err=err)

    def do_login(self):
        ident, pw = self.lg["u"].strip(), self.lg["p"]
        if not configured():
            return msg("Setup baki hai", "main_v4.py me SUPABASE_KEY daalo (sb_publishable_...).")
        if not ident or not pw:
            return msg("Dhyan do", "Email/Enrollment aur password dono bharo.")

        def work():
            self.syncing = True
            try:
                em = ident if "@" in ident else self.api.rpc_anon("login_email", {"p_identifier": ident})
                if not em:
                    raise ApiError(400, "Invalid login credentials", "invalid_credentials")
                self.api.login(em, pw)
                return self.after_auth()
            finally:
                self.syncing = False
        self.lg["p"] = ""
        self.net(work, self.finish_login, "Login ho raha hai...")

    # ---------- forgot / reset password (Supabase Auth e-mail code) ----------
    def forgot(self):
        b = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        e = inp("Registered email")
        b.add_widget(lbl("Apna registered email likho. Us par 6 digit ka reset code aayega.", 13, MU))
        b.add_widget(e)
        p = pop("Password reset", b, 330)

        def send():
            em = e.text.strip().lower()
            if not valid_email(em):
                return msg("Dhyan do", "Sahi email likho.")

            def work():
                self.api.recover(em)
            self.net(work, lambda _: stage2(em), "Code bhej rahe hain...")

        def stage2(em):
            b.clear_widgets()
            c, n1, n2 = inp("Email ka 6 digit code"), inp("Naya password (6+ akshar)", password=True), inp("Password dobara", password=True)
            b.add_widget(lbl("Email check karo (spam bhi). Code yahan likho aur naya password set karo.", 13, MU))
            for w in (c, n1, n2):
                b.add_widget(w)

            def go():
                if len(c.text.strip()) < 6:
                    return msg("Dhyan do", "Email ka code likho.")
                if len(n1.text) < 6 or n1.text != n2.text:
                    return msg("Dhyan do", "Password 6+ akshar ka ho aur dono baar same ho.")

                def work2():
                    self.syncing = True
                    try:
                        self.api.verify_recovery(em, c.text)
                        self.api.set_password(n1.text)
                    finally:
                        self.api.save(None)
                        self.syncing = False
                self.net(work2, lambda _: (p.dismiss(), msg("Done", "Password badal gaya. Ab naye password se login karo.")), "Password badal rahe hain...")
            b.add_widget(btn("Password badlo", go))
            b.add_widget(btn("Cancel", p.dismiss, "muted"))
            p.height = dp(440)

        b.add_widget(btn("Code bhejo", send))
        b.add_widget(btn("Cancel", p.dismiss, "muted"))
        p.open()

    # ---------- register ----------
    def start_register(self):
        self.rg = reg_state()
        self.register_screen(True)

    def register_screen(self, anim=False):
        st = self.rg
        self.main.clear_widgets()
        sv, g = self.new_page()
        g.add_widget(lbl("Naya Account", 26, AC, True, "center"))
        c = Card()
        c.add_widget(lbl("Main kaun hu?", 12, MU))
        tb = {k: RBtn(text=t, bg=list(AC if st["role"] == k else GR), color=WHITE if st["role"] == k else MU,
                      on_release=lambda *_, k=k: (st.__setitem__("role", k), self.register_screen())) for k, t in (("student", "Student"), ("teacher", "Teacher"))}
        c.add_widget(row(tb["student"], tb["teacher"]))
        c.add_widget(row(self.avatar({"photo_src": st["photo_src"], "full_name": st["name"] or "?"}, 84),
                         btn("Profile photo chuno", lambda: self.pick_photo(lambda p: (st.__setitem__("photo_src", p), self.register_screen())), "muted", pos_hint={"center_y": .5}), h=90))

        def f(label, key, hint="", **k):
            c.add_widget(lbl(label, 12, MU))
            c.add_widget(tin(st, key, hint or label, **k))

        f("Naam (First name)", "name")
        f("Surname (Last name)", "surname")
        f("Email (login aur password reset ke liye)", "email", "name@example.com")
        f("Mobile number (10 digit)", "mobile", num=True)
        if st["role"] == "teacher":
            f("Kaun sa subject padhate ho?", "subject")
            f("Department", "dept")
            f("Employee ID (optional)", "empid")
            f("Teacher access code (admin se lo)", "tcode", password=True)
        else:
            f("Enrollment / Roll number", "roll")
            f("College / School ka naam", "college_name")
            c.add_widget(lbl("Padhai ka level", 12, MU))
            ib = {k: RBtn(text=t, bg=list(AC if st["inst"] == k else GR), color=WHITE if st["inst"] == k else MU,
                          on_release=lambda *_, k=k: (st.__setitem__("inst", k), self.register_screen())) for k, t in (("college", "College"), ("school", "School"))}
            c.add_widget(row(ib["college"], ib["school"]))
            for w in class_fields(st, False, self.register_screen):
                c.add_widget(w)
        f("Password (6+ akshar)", "pw", password=True)
        f("Password dobara likho", "pw2", password=True)
        c.add_widget(btn("Register karo", self.do_register))
        c.add_widget(btn("Wapas Login par", self.login_screen, "muted"))
        g.add_widget(c)
        self.main.add_widget(sv)
        if anim:
            self.fade(g)

    def check_form(self, st, t, add):
        """Returns an error text or '' if the form is valid."""
        if not st["name"].strip() or not st["surname"].strip():
            return "Naam aur surname zaroori hain."
        if not valid_email(st["email"].strip()):
            return "Sahi email likho (jaise name@gmail.com)."
        if not valid_mobile(st["mobile"].strip()):
            return "Mobile number 10 digit ka ho."
        if len(st["pw"]) < 6 or st["pw"] != st["pw2"]:
            return "Password 6+ akshar ka ho aur dono baar same ho."
        if t:
            if not st["subject"].strip():
                return "Subject likhna zaroori hai."
            if not st["tcode"].strip():
                return "Teacher access code zaroori hai."
        else:
            if not valid_enroll(st["roll"].strip()):
                return "Enrollment number 3-30 akshar ka ho (letters, numbers, - _ / .)."
            if st["inst"] == "college" and st["branch"] == "Other" and not st["branch_o"].strip():
                return "Apni branch ka naam likho."
        return ""

    def do_register(self, st=None, add=False):
        st = st or self.rg
        t = st["role"] == "teacher"
        bad = self.check_form(st, t, add)
        if bad:
            return msg("Dhyan do", bad)
        if not configured():
            return msg("Setup baki hai", "main_v4.py me SUPABASE_KEY daalo (sb_publishable_...).")
        em, col = st["email"].strip().lower(), st["inst"] == "college"
        meta = dict(first_name=st["name"].strip(), last_name=st["surname"].strip(), mobile=st["mobile"].strip())
        if t:
            meta.update(teacher_code=st["tcode"].strip(), employee_id=st["empid"].strip(), department=st["dept"].strip(), subject_note=st["subject"].strip())
        else:
            meta.update(enrollment=st["roll"].strip(), kind=st["inst"], college_name=st["college_name"].strip(),
                        branch=bval(st) if col else cname(st), year=st["year"] if col else "-", semester=st["sem"] if col else "-",
                        section=st["sec"] if st["sec"] != "All" else "-", batch=st["batch"] if col and st["batch"] != "All" else "")

        def work():
            r = self.api.rpc_anon("check_available", {"p_email": em, "p_enrollment": None if t else meta["enrollment"]})
            if r and r.get("email_taken"):
                raise ApiError(400, "Ye email pehle se registered hai.", "email_exists")
            if r and r.get("enrollment_taken"):
                raise ApiError(400, "Ye enrollment number pehle se registered hai.", "dup_enroll")
            d = self.api.signup(em, st["pw"], meta)
            if add:
                return d
            if d.get("access_token"):
                self.syncing = True
                try:
                    self.api.store(d)
                    self.after_auth()
                finally:
                    self.syncing = False
            return d

        def ok(d):
            if add:
                nid = (d.get("user") or {}).get("id") or d.get("id")
                if nid:
                    self.d.enqueue("patch", "students", {"q": "id=eq." + nid, "values": {"mentor_id": self.uid()}})
                keep = {k: st[k] for k in ("inst", "branch", "branch_o", "year", "sem", "sec", "batch", "cls", "college_name")}
                self.ns = dict(reg_state(), **keep)
                self.show_add = False
                self.sync_now()
                msg("Done", "Student add ho gaya. Wo apne email/enrollment aur password se login kar sakta hai.")
                return self.refresh()
            if d.get("access_token"):
                self.pend_photo = st["photo_src"]
                return self.finish_login()
            self.login_screen()
            msg("Account ban gaya", "Email confirm karne ka link bheja gaya hai. Confirm karke login karo.")

        def err(e):
            if t and isinstance(e, ApiError) and "database error" in (e.msg or "").lower():
                return msg("Register nahi hua", "Teacher access code galat hai ya ye email pehle se registered hai.")
            msg("Register nahi hua", friendly(e))
        self.net(work, ok, "Account ban raha hai...", err=err)

    # ---------- photo ----------
    def avatar(self, u, size=80):
        kw = dict(size_hint=(None, None), size=(dp(size), dp(size)), pos_hint={"center_y": .5})
        src = u.get("photo_src") or ""
        if src and os.path.exists(src):
            return Image(source=src, **kw)
        uid = u.get("id")
        r = self.d.one("SELECT b64 FROM avatars WHERE id=?", (uid,)) if uid else None
        if r and r["b64"]:
            key = (uid, len(r["b64"]))
            try:
                if key not in self.tex:
                    from kivy.core.image import Image as CoreImage
                    self.tex[key] = CoreImage(io.BytesIO(base64.b64decode(r["b64"])), ext="jpg").texture
                return Image(texture=self.tex[key], **kw)
            except Exception as e:
                log(e, "avatar")
        return Initials(text=initials(fullname(u)), **kw)

    def pick_photo(self, done):
        from kivy.uix.filechooser import FileChooserIconView
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])
        except Exception:
            pass
        start = "/storage/emulated/0" if os.path.isdir("/storage/emulated/0") else os.path.expanduser("~")
        fc = FileChooserIconView(path=start, filters=["*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"])
        b = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(6))
        b.add_widget(fc)
        p = pop("Photo chuno", b, w=.96)
        p.size_hint = (.96, .9)

        def ok():
            if fc.selection:
                p.dismiss()
                done(fc.selection[0])
            else:
                msg("Dhyan do", "Pehle koi photo chuno.")
        b.add_widget(row(btn("Cancel", p.dismiss, "muted"), btn("Select", ok)))
        p.open()

    def photo_b64(self, src):
        try:
            try:
                from PIL import Image as PI
                im = PI.open(src).convert("RGB")
                im.thumbnail((256, 256))
                bio = io.BytesIO()
                im.save(bio, "JPEG", quality=80)
                raw = bio.getvalue()
            except ImportError:
                raw = open(src, "rb").read()
                if len(raw) > 120000:
                    return ""
            return base64.b64encode(raw).decode()
        except Exception as e:
            log(e, "photo")
            return ""

    def new_photo(self, src, quiet=False):
        b = self.photo_b64(src)
        if not b:
            return None if quiet else msg("Error", "Photo save nahi ho payi (chhoti JPG/PNG chuno).")
        self.db("INSERT OR REPLACE INTO avatars VALUES(?,?)", (self.uid(), b))
        self.d.enqueue("patch", "profiles", {"q": "id=eq." + self.uid(), "values": {"avatar": b}})
        self.sync_now()
        if not quiet:
            self.refresh()

    # ---------- notifications ----------
    def notif_card(self, g):
        rs = self.rows("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 6", (self.uid(),))
        if not rs:
            return
        c = Card()
        c.add_widget(lbl("Notifications", 16, bold=True))
        for r in rs:
            c.add_widget(lbl(("* " if not r["is_read"] else "") + r["title"], 14, TX if r["is_read"] else AC, True))
            c.add_widget(lbl("%s  (%s)" % (r["body"], (r["created_at"] or "")[:10]), 12, MU))
        if any(not r["is_read"] for r in rs):
            c.add_widget(btn("Sab padh liye", self.read_all, "ghost"))
        g.add_widget(c)

    def read_all(self):
        self.db("UPDATE notifications SET is_read=1 WHERE user_id=?", (self.uid(),))
        self.d.enqueue("patch", "notifications", {"q": "user_id=eq.%s&is_read=eq.false" % self.uid(), "values": {"is_read": True}})
        self.sync_now()
        self.paint_nav()
        self.refresh()

    # ---------- shared month calendar ----------
    def mv(self, n):
        y, m = self.cm
        m += n
        if m < 1:
            m, y = 12, y - 1
        if m > 12:
            m, y = 1, y + 1
        self.cm = (y, m)
        self.refresh()

    def cal_card(self, g, title, colfn, click=None, legend=""):
        y, m = self.cm
        c = Card()
        if title:
            c.add_widget(lbl(title, 16, bold=True))
        c.add_widget(row(small("<", lambda: self.mv(-1)), lbl("%s %d" % (calendar.month_name[m], y), 17, TX, True, "center"), small(">", lambda: self.mv(1))))
        weeks = calendar.monthcalendar(y, m)
        grid = GridLayout(cols=7, size_hint_y=None, height=dp(38) * (len(weeks) + 1), spacing=dp(4))
        for dn in "SMTWTFS":
            grid.add_widget(Label(text=dn, color=MU, bold=True))
        for wk in weeks:
            for d in wk:
                if not d:
                    grid.add_widget(Widget())
                    continue
                k = "%04d-%02d-%02d" % (y, m, d)
                col = colfn(k)
                kw = dict(text=str(d), bg=list(col or [.93, .94, .97, 1]), color=WHITE if col else TX, font_size=sp(13))
                grid.add_widget(DayCell(on_release=lambda *_, k=k: click(k), **kw) if click else Cell(**kw))
        c.add_widget(grid)
        if legend:
            c.add_widget(lbl(legend, 12, MU, align="center"))
        g.add_widget(c)

    # ---------- student: home ----------
    def s_home(self, g):
        u = self.me
        uid = u["id"]
        p, a, l, t, pc = self.stat(uid)
        self.hero(g, u, "Welcome", fullname(u), "Enrollment %s  |  %s" % (u.get("roll", ""), glabel(u)))
        col = NO if pc < self.thr and t else OK
        c = Card(orientation="horizontal", spacing=dp(14))
        ring = Ring(size_hint=(None, None), size=(dp(120), dp(120)), col=list(col))
        Clock.schedule_once(lambda d: Animation(value=pc, d=1.1, t="out_cubic").start(ring), .3)
        c.add_widget(ring)
        inf = BoxLayout(orientation="vertical", spacing=dp(2))
        inf.add_widget(lbl("Present: %d" % p, 15, OK, True))
        inf.add_widget(lbl("Absent: %d" % a, 15, NO, True))
        inf.add_widget(lbl("Leave: %d" % l, 15, LV, True))
        inf.add_widget(lbl("Total classes: %d" % t, 13, MU))
        inf.add_widget(lbl("Percentage: %s" % pstr(pc, t), 13, col, True))
        c.add_widget(inf)
        g.add_widget(c)
        if pc < self.thr and t and self.thr < 100:
            need = max(1, -(-(self.thr * t - 100 * p) // (100 - self.thr)))
            w = Card(bg=[1, .93, .93, 1])
            w.add_widget(lbl("Attendance %d%% se kam hai! Lagataar %d class attend karo to %d%% ho jayegi." % (self.thr, need, self.thr), 14, NO, True))
            g.add_widget(w)
        td = self.rows("SELECT s.subject_id, r.status FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id "
                       "WHERE r.student_id=? AND s.date=?", (uid, today()))
        c = Card()
        c.add_widget(lbl("Aaj ki attendance", 16, bold=True))
        if not td:
            c.add_widget(lbl("Aaj abhi koi attendance mark nahi hui.", 13, MU))
        for r in td:
            c.add_widget(row(lbl(self.sname(r["subject_id"]), 14, TX, True), lbl(ST_TXT[r["status"]], 14, ST_COL[r["status"]], True, "right", 80), h=28))
        g.add_widget(c)
        self.subject_card(g, uid)
        self.notif_card(g)
        dd = {}
        for d, s in self.db("SELECT s.date, r.status FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id WHERE r.student_id=?", (uid,)):
            dd.setdefault(d, set()).add(s)
        ld = set()
        for fd, td_ in self.db("SELECT from_date,to_date FROM leave_requests WHERE student_id=? AND status='approved'", (uid,)):
            d, e = dt.date.fromisoformat(fd), dt.date.fromisoformat(td_)
            while d <= e and len(ld) < 800:
                ld.add(d.isoformat())
                d += dt.timedelta(days=1)

        def colfn(k):
            s = dd.get(k)
            s = ("A" if "A" in s else "P" if "P" in s else "L") if s else ("L" if k in ld else None)
            return ST_COL.get(s)
        self.cal_card(g, "", colfn, None, "Hara = Present   Laal = Absent   Narangi = Leave")

    def subject_card(self, g, uid):
        per = {}
        for sid, s, n in self.db("SELECT s.subject_id,r.status,COUNT(*) FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id "
                                 "WHERE r.student_id=? GROUP BY s.subject_id,r.status", (uid,)):
            per.setdefault(sid, {})[s] = n
        if not per:
            return
        c = Card()
        c.add_widget(lbl("Subject-wise attendance", 16, bold=True))
        for sid, v in per.items():
            tp, ta, tl, tt, ppc = self.mkstat(v.get("P", 0), v.get("A", 0), v.get("L", 0))
            c.add_widget(row(lbl(self.sname(sid), 14, TX, True), lbl("%d%%" % ppc, 14, NO if ppc < self.thr else OK, True, "right", 56), h=28))
            c.add_widget(lbl("Present %d  |  Absent %d  |  Leave %d  |  Total %d" % (tp, ta, tl, tt), 12, MU))
            b = Bar(size_hint_y=None, height=dp(8), col=list(NO if ppc < self.thr else OK))
            grow(b, ppc)
            c.add_widget(b)
        g.add_widget(c)

    # ---------- student: history / subjects / leave ----------
    def s_history(self, g):
        uid, hf = self.uid(), self.hf
        subs = self.subjects_for(self.me.get("class_id"))
        labels = {"%s - %s" % (s["code"], s["name"]): s["id"] for s in subs}
        c = Card()
        c.add_widget(lbl("Attendance History", 17, bold=True))
        c.add_widget(lbl("Subject", 12, MU))
        c.add_widget(spin(hf, "subject", ["All"] + list(labels), self.refresh))
        c.add_widget(lbl("Status", 12, MU))
        c.add_widget(spin(hf, "st", ["All", "Present", "Absent", "Leave"], self.refresh))
        c.add_widget(row(tin(hf, "d1", "Se (YYYY-MM-DD)"), tin(hf, "d2", "Tak (YYYY-MM-DD)")))
        c.add_widget(btn("Filter lagao", self.refresh))
        g.add_widget(c)
        sub = labels.get(hf["subject"])
        d1, d2 = (hf["d1"] if vd(hf["d1"]) else None), (hf["d2"] if vd(hf["d2"]) else None)
        p, a, l, t, pc = self.stat(uid, sub, d1, d2)
        c = Card()
        c.add_widget(lbl("Present %d  |  Absent %d  |  Leave %d  |  Total %d" % (p, a, l, t), 13, MU, True))
        col = NO if pc < self.thr and t else OK
        c.add_widget(lbl("Percentage: %s" % pstr(pc, t), 16, col, True))
        b = Bar(size_hint_y=None, height=dp(10), col=list(col))
        grow(b, pc)
        c.add_widget(b)
        g.add_widget(c)
        sql = "SELECT s.date,s.subject_id,r.status FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id WHERE r.student_id=?"
        args = [uid]
        for cond, v in ((" AND s.subject_id=?", sub), (" AND s.date>=?", d1), (" AND s.date<=?", d2),
                        (" AND r.status=?", {"Present": "P", "Absent": "A", "Leave": "L"}.get(hf["st"]))):
            if v:
                sql += cond
                args.append(v)
        rs = self.rows(sql + " ORDER BY s.date DESC LIMIT 150", args)
        if not rs:
            c = Card()
            c.add_widget(lbl("Koi record nahi mila.", 14, MU))
            g.add_widget(c)
        for r in rs:
            c = Card()
            c.add_widget(row(lbl(dt.date.fromisoformat(r["date"]).strftime("%d %b %Y, %a"), 14, TX, True),
                             lbl(ST_TXT[r["status"]], 14, ST_COL[r["status"]], True, "right", 80), h=28))
            c.add_widget(lbl(self.sname(r["subject_id"]), 12, MU))
            g.add_widget(c)

    def s_subjects(self, g):
        u = self.me
        c = Card()
        c.add_widget(lbl("Mere Subjects", 17, bold=True))
        c.add_widget(lbl(glabel(u), 13, AC, True))
        g.add_widget(c)
        subs = self.subjects_for(u.get("class_id"))
        subs += self.rows("SELECT s.* FROM student_subjects ss JOIN subjects s ON s.id=ss.subject_id WHERE ss.student_id=?", (u["id"],))
        seen = set()
        for s in subs:
            if s["id"] in seen:
                continue
            seen.add(s["id"])
            tr = self.d.one("SELECT p.full_name FROM class_subjects cs JOIN profiles p ON p.id=cs.teacher_id WHERE cs.class_id=? AND cs.subject_id=?", (u.get("class_id"), s["id"]))
            p, a, l, t, pc = self.stat(u["id"], s["id"])
            col = NO if pc < self.thr and t else OK
            c = Card()
            c.add_widget(row(lbl(s["name"], 16, TX, True), lbl(pstr(pc, t) if t else "-", 15, col, True, "right", 80), h=30))
            c.add_widget(lbl("Code: %s   |   Teacher: %s" % (s["code"], tr["full_name"] if tr else "-"), 12, MU))
            c.add_widget(lbl("Present %d  |  Absent %d  |  Leave %d  |  Total %d" % (p, a, l, t), 12, MU))
            b = Bar(size_hint_y=None, height=dp(8), col=list(col))
            grow(b, pc)
            c.add_widget(b)
            g.add_widget(c)
        if not seen:
            c = Card()
            c.add_widget(lbl("Abhi aapki class ke liye koi subject assign nahi hua.", 14, MU))
            g.add_widget(c)

    def s_leave(self, g):
        c = Card()
        c.add_widget(lbl("Leave ke liye apply karo", 16, bold=True))
        f, t, r = inp("Se (YYYY-MM-DD)", today()), inp("Tak (YYYY-MM-DD)", today()), inp("Reason")
        for w in (f, t, r):
            c.add_widget(w)

        def send():
            if not (vd(f.text) and vd(t.text)) or t.text < f.text or not r.text.strip():
                return msg("Dhyan do", "Dates (YYYY-MM-DD) aur reason sahi bharo.")
            row_ = dict(id=str(uuid.uuid4()), student_id=self.uid(), from_date=f.text, to_date=t.text, reason=r.text.strip(),
                        status="pending", decided_by=None, created_at=now_iso(), updated_at=now_iso())
            self.d.put("leave_requests", [row_])
            self.d.enqueue("insert", "leave_requests", {k: row_[k] for k in wcols("leave_requests")})
            self.sync_now()
            msg("Done", "Request bhej di gayi (internet na ho to baad me apne aap chali jayegi).")
            self.refresh()
        c.add_widget(btn("Request bhejo", send))
        g.add_widget(c)
        for x in self.rows("SELECT * FROM leave_requests WHERE student_id=? ORDER BY created_at DESC", (self.uid(),)):
            c = Card()
            c.add_widget(row(lbl("%s  to  %s" % (x["from_date"], x["to_date"]), 14, TX, True),
                             lbl(x["status"].upper(), 13, {"pending": LV, "approved": OK, "rejected": NO}[x["status"]], True, "right", 100), h=30))
            c.add_widget(lbl(x["reason"], 13, MU))
            g.add_widget(c)

    # ---------- profile (teacher + student) ----------
    def profile(self, g):
        u = self.me
        c = Card()
        c.add_widget(row(self.avatar(u, 90), btn("Photo badlo", lambda: self.pick_photo(self.new_photo), "muted", pos_hint={"center_y": .5}), h=96))
        c.add_widget(lbl(fullname(u), 20, TX, True))
        lines = ["Email: " + (u.get("email") or "-"), "Mobile: " + (u.get("mobile") or "-")]
        if self.staff():
            lines += ["Role: " + u["role"].title(), "Subject: " + (u.get("subject_note") or "-"), "Department: " + (u.get("department") or "-"),
                      "Employee ID: " + (u.get("employee_id") or "-")]
        else:
            m = self.d.one("SELECT full_name FROM profiles WHERE id=?", (u.get("mentor_id"),)) if u.get("mentor_id") else None
            lines += ["Enrollment: " + (u.get("roll") or "-"), "College: " + (u.get("college_name") or "-"), "Class: " + glabel(u),
                      "Mentor: " + (m["full_name"] if m else "-")]
            p, a, l, t, pc = self.stat(u["id"])
            lines.append("Attendance: %s  (P %d / A %d / L %d)" % (pstr(pc, t), p, a, l))
        for x in lines:
            c.add_widget(lbl(x, 14, MU))
        g.add_widget(c)
        self.notif_card(g)
        # edit profile
        pe = self.__dict__.setdefault("pe", {})
        if pe.get("uid") != u["id"]:
            pe.clear()
            pe.update(uid=u["id"], first=u.get("first_name", ""), last=u.get("last_name", ""), mobile=u.get("mobile", ""))
        c = Card()
        c.add_widget(lbl("Profile edit karo", 16, bold=True))
        fld(c, pe, "Naam (First name)", "first")
        fld(c, pe, "Surname", "last")
        fld(c, pe, "Mobile number", "mobile", num=True)
        c.add_widget(btn("Save profile", self.save_profile))
        g.add_widget(c)
        # change password
        pw = self.__dict__.setdefault("pwst", dict(o="", n="", n2=""))
        c = Card()
        c.add_widget(lbl("Password badlo", 16, bold=True))
        for k, h in (("o", "Purana password"), ("n", "Naya password (6+ akshar)"), ("n2", "Naya password dobara")):
            c.add_widget(tin(pw, k, h, password=True))
        c.add_widget(btn("Update", self.change_pw))
        g.add_widget(c)
        self.settings_card(g)
        self.sync_card(g)

    def save_profile(self):
        pe, u = self.pe, self.me
        if not pe["first"].strip() or not pe["last"].strip() or not valid_mobile(pe["mobile"].strip()):
            return msg("Dhyan do", "Naam, surname aur 10 digit ka mobile number sahi bharo.")
        full = ("%s %s" % (pe["first"].strip(), pe["last"].strip())).strip()
        vals = dict(first_name=pe["first"].strip(), last_name=pe["last"].strip(), full_name=full, mobile=pe["mobile"].strip())
        self.db("UPDATE profiles SET first_name=?,last_name=?,full_name=?,mobile=?,updated_at=? WHERE id=?",
                (vals["first_name"], vals["last_name"], full, vals["mobile"], now_iso(), u["id"]))
        self.d.enqueue("patch", "profiles", {"q": "id=eq." + u["id"], "values": vals})
        self.sync_now()
        self.load_me()
        msg("Done", "Profile save ho gaya.")
        self.refresh()

    def change_pw(self):
        pw = self.pwst
        if not pw["o"]:
            return msg("Dhyan do", "Purana password likho.")
        if len(pw["n"]) < 6 or pw["n"] != pw["n2"]:
            return msg("Dhyan do", "Naya password 6+ akshar ka ho aur dono baar same ho.")
        o, n, em = pw["o"], pw["n"], self.me["email"]

        def work():
            self.api.login(em, o)
            self.api.set_password(n)

        def ok(_):
            pw.update(o="", n="", n2="")
            msg("Done", "Password badal gaya.")
            self.refresh()
        self.net(work, ok, "Password badal rahe hain...")

    def settings_card(self, g):
        modes = {"total": "Leave bhi total me ginti hai (P / (P+A+L))", "excluded": "Leave ginti nahi (purana: P / (P+A))"}
        st = self.__dict__.setdefault("setst", {})
        st["lm"] = modes[self.lm]
        st["thr"] = str(self.thr)
        st["every"] = "%d sec" % self.every
        c = Card()
        c.add_widget(lbl("Settings", 16, bold=True))
        c.add_widget(lbl("Attendance percentage kaise nikale", 12, MU))
        c.add_widget(spin(st, "lm", list(modes.values()), lambda: (self.d.kset("lm", [k for k, v in modes.items() if v == st["lm"]][0]),
                                                                  setattr(self, "lm", [k for k, v in modes.items() if v == st["lm"]][0]))))
        c.add_widget(lbl("Low attendance warning (%)", 12, MU))
        c.add_widget(spin(st, "thr", ["60", "65", "70", "75", "80", "85"], lambda: (self.d.kset("thr", st["thr"]), setattr(self, "thr", int(st["thr"])))))
        c.add_widget(lbl("Auto sync interval", 12, MU))
        c.add_widget(spin(st, "every", ["15 sec", "30 sec", "60 sec", "300 sec"], lambda: self.set_every(int(st["every"].split()[0]))))
        g.add_widget(c)

    def set_every(self, n):
        if n == self.every:
            return
        self.every = n
        self.d.kset("every", n)
        self.timer.cancel()
        self.timer = Clock.schedule_interval(self.tick, n)

    def sync_card(self, g):
        n = self.d.pending()
        col = {"online": OK, "synced": OK, "syncing": AC, "offline": MU, "failed": NO}[self.status]
        c = Card()
        c.add_widget(lbl("Cloud Sync (Supabase)", 16, bold=True))
        c.add_widget(lbl("Status: %s   |   Upload baki: %d" % ({"online": "Online", "synced": "Synced", "syncing": "Syncing...", "offline": "Offline", "failed": "Sync Failed"}[self.status], n), 13, col, True))
        c.add_widget(lbl(self.sync_msg or "Abhi sync nahi hua", 12, MU))
        errs = self.rows("SELECT * FROM sync_errors ORDER BY id DESC LIMIT 3")
        for e in errs:
            c.add_widget(lbl("! %s: %s" % (e["what"], e["err"]), 12, NO))
        c.add_widget(btn("Abhi sync karo", lambda: (self.sync_now(), self.toast("Sync shuru ho gaya...", AC))))
        if errs:
            c.add_widget(btn("Errors saaf karo", lambda: (self.db("DELETE FROM sync_errors"), self.refresh()), "ghost"))
        c.add_widget(btn("Error log dekho", self.show_log, "plain"))
        c.add_widget(lbl("SmartHazri v%s   |   Server: %s" % (APP_VERSION, SUPABASE_URL.split("//")[-1].split(".")[0]), 11, MU, align="center"))
        g.add_widget(c)

    def show_log(self):
        try:
            with open(os.path.join(self.user_data_dir, "error.log"), encoding="utf-8") as f:
                t = f.read()[-3500:]
        except Exception:
            t = ""
        info("Error log", t or "Koi error nahi.")

    # ---------- teacher: home ----------
    def state_from_class(self, c, batch=""):
        st = new_state()
        st["inst"], st["sec"], st["batch"] = c["kind"], c["section"], batch or "All"
        if c["kind"] == "college":
            if c["branch"] in BRANCHES:
                st["branch"] = c["branch"]
            else:
                st["branch"], st["branch_o"] = "Other", c["branch"]
            st["year"], st["sem"] = c["year"], c["semester"]
        else:
            st["cls"] = str(c["branch"]).replace("Class ", "", 1)
        return st

    def avg_all(self):
        m = {}
        for sid, s, n in self.db("SELECT student_id,status,COUNT(*) FROM attendance_records GROUP BY student_id,status"):
            m.setdefault(sid, {})[s] = n
        pcs = [x[4] for x in (self.mkstat(v.get("P", 0), v.get("A", 0), v.get("L", 0)) for v in m.values()) if x[3]]
        return sum(pcs) / len(pcs) if pcs else 0

    def t_home(self, g):
        u = self.me
        self.hero(g, u, "Namaste", fullname(u), "Subject: " + (u.get("subject_note") or "-"))
        r = dict(self.db("SELECT r.status,COUNT(*) FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id WHERE s.date=? GROUP BY r.status", (today(),)))
        ns = self.db("SELECT COUNT(*) FROM students")[0][0]
        ses = self.db("SELECT COUNT(*) FROM attendance_sessions WHERE date=?", (today(),))[0][0]
        grid = GridLayout(cols=2, size_hint_y=None, height=dp(270), spacing=dp(10))
        for v, t, col in ((ns, "Registered students", TX), (ses, "Aaj ki classes li", AC), (r.get("P", 0), "Aaj present", OK),
                          (r.get("A", 0), "Aaj absent", NO), (r.get("L", 0), "Aaj leave", LV), ("%.1f%%" % self.avg_all(), "Average attendance", AC)):
            p = Panel(orientation="vertical", padding=dp(14), spacing=dp(2))
            p.add_widget(lbl(v, 28, col, True))
            p.add_widget(lbl(t, 13, MU))
            grid.add_widget(p)
        g.add_widget(grid)
        n = self.pending_leaves()
        if n:
            c = Card(bg=[1, .96, .88, 1])
            c.add_widget(lbl("%d leave request pending hai" % n, 15, LV, True))
            c.add_widget(btn("Leave requests dekho", lambda: self.open_sub(self.t_leaves), "warn"))
            g.add_widget(c)
        rs = self.rows("SELECT s.id AS sid,s.date,s.subject_id,s.batch,c.kind,c.branch,c.year,c.semester,c.section FROM attendance_sessions s JOIN classes c ON c.id=s.class_id "
                       "ORDER BY s.date DESC, s.updated_at DESC LIMIT 6")
        c = Card()
        c.add_widget(lbl("Recent attendance", 16, bold=True))
        if not rs:
            c.add_widget(lbl("Abhi koi attendance nahi li gayi. Hazri tab se shuru karo.", 13, MU))
        for x in rs:
            cnt = dict(self.db("SELECT status,COUNT(*) FROM attendance_records WHERE session_id=? GROUP BY status", (x["sid"],)))
            c.add_widget(row(lbl("%s  |  %s" % (dt.date.fromisoformat(x["date"]).strftime("%d %b"), self.sname(x["subject_id"])), 14, TX, True),
                             small("Edit", lambda sid=x["sid"]: self.open_session(sid), "ghost", 60), h=34))
            c.add_widget(lbl(class_label(dict(x, semester=x["semester"]), x["batch"]), 12, MU))
            c.add_widget(lbl("Present %d  |  Absent %d  |  Leave %d" % (cnt.get("P", 0), cnt.get("A", 0), cnt.get("L", 0)), 12, AC, True))
        g.add_widget(c)
        self.notif_card(g)
        c = Card()
        c.add_widget(lbl("Kaise use karein", 16, bold=True))
        c.add_widget(lbl("Setup tab me subject banao aur class se jodo.\nHazri tab me class, subject aur date chuno, Present/Absent/Leave mark karke Save dabao. Purani date ki hazri bhi badal sakte ho.\nReport tab me har student ke present/absent/leave aur percentage milenge.\nInternet na ho tab bhi kaam chalega, net aate hi sab upload ho jayega.", 13, MU))
        g.add_widget(c)
        self.t_cal(g)

    def open_session(self, sid):
        s = self.d.one("SELECT * FROM attendance_sessions WHERE id=?", (sid,))
        c = self.d.one("SELECT * FROM classes WHERE id=?", (s["class_id"],)) if s else None
        if not c:
            return
        self.grp = self.state_from_class(c, s["batch"])
        self.mk = dict(date=s["date"], subject="%s" % self.sname(s["subject_id"]))
        self.tab, self.sub = 1, None
        self.paint_nav()
        self.show(self.t_mark, anim=False)
        self.start_mark()

    def t_cal(self, g):
        y, m = self.cm
        pre = "%04d-%02d-" % (y, m)
        agg = {}
        for d, s, n in self.db("SELECT s.date,r.status,COUNT(*) FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id "
                               "WHERE s.date LIKE ? GROUP BY s.date,r.status", (pre + "%",)):
            agg.setdefault(d, {})[s] = n

        def colfn(k):
            v = agg.get(k)
            if not v:
                return None
            t = v.get("P", 0) + v.get("A", 0)
            pc = v.get("P", 0) * 100 / t if t else 50
            return OK if pc >= 75 else LV if pc >= 50 else NO
        self.cal_card(g, "Attendance Calendar", colfn, self.day_info,
                      "Hara: 75%+ present   Narangi: 50-75%   Laal: 50% se kam   Dhusar: hazri nahi li.\nKisi din ko dabao to uski detail milegi.")

    def day_info(self, k):
        ss = self.rows("SELECT s.id AS sid,s.subject_id,s.batch,c.kind,c.branch,c.year,c.semester,c.section FROM attendance_sessions s JOIN classes c ON c.id=s.class_id WHERE s.date=? ORDER BY c.branch,c.year,c.section", (k,))
        title = dt.date.fromisoformat(k).strftime("%d %B %Y, %A")
        if not ss:
            return msg(title, "Is din koi hazri nahi li gayi.")
        out = []
        for x in ss:
            rs = self.rows("SELECT r.status,p.full_name,s.enrollment FROM attendance_records r JOIN profiles p ON p.id=r.student_id JOIN students s ON s.id=r.student_id WHERE r.session_id=?", (x["sid"],))
            n = lambda z: sum(1 for r in rs if r["status"] == z)
            out.append("%s\n%s\nPresent %d | Absent %d | Leave %d" % (self.sname(x["subject_id"]), class_label(x, x["batch"]), n("P"), n("A"), n("L")))
            ab = ["%s (%s)" % (r["full_name"], r["enrollment"]) for r in rs if r["status"] == "A"]
            if ab:
                out.append("Absent: " + ", ".join(ab))
            out.append("")
        info(title, "\n".join(out))

    # ---------- teacher: attendance (Hazri) ----------
    def sub_widgets(self):
        cls = self.find_class(self.grp)
        subs = self.subjects_for(cls["id"] if cls else None)
        self.sub_map = {"%s - %s" % (s["code"], s["name"]): s["id"] for s in subs}
        ws = [lbl("Subject", 12, MU), spin(self.mk, "subject", list(self.sub_map) or ["(koi subject nahi)"]),
              lbl("Date", 12, MU),
              row(small("<", lambda: self.shift_day(-1)), tin(self.mk, "date", "YYYY-MM-DD"), small(">", lambda: self.shift_day(1)),
                  small("Aaj", lambda: self.shift_day(0), "ghost", 58))]
        return ws

    def shift_day(self, n):
        try:
            d = dt.date.fromisoformat(self.mk["date"]) + dt.timedelta(days=n) if n else dt.date.today()
        except Exception:
            d = dt.date.today()
        self.mk["date"] = d.isoformat()
        self.refresh()

    def start_mark(self):
        mk = self.mk
        if not vd(mk["date"]):
            return msg("Dhyan do", "Date YYYY-MM-DD me sahi likho (jaise 2026-10-18).")
        cls = self.find_class(self.grp)
        if not cls:
            return msg("Class nahi mili", "Is branch/year/semester/section ki class abhi nahi hai. Setup tab me class banao ya student add karo.")
        self.sub_widgets()
        subj = self.sub_map.get(mk["subject"])
        if not subj:
            return msg("Subject chuno", "Pehle Setup tab me subject banao aur use is class se assign karo.")
        studs = self.students(self.grp)
        if not studs:
            return msg("Koi student nahi", "Is class me abhi koi student registered nahi hai.")
        batch = "" if self.grp["inst"] != "college" or self.grp["batch"] == "All" else self.grp["batch"]
        other = [o[0] for o in self.db("SELECT batch FROM attendance_sessions WHERE class_id=? AND subject_id=? AND date=? AND batch<>?", (cls["id"], subj, mk["date"], batch))]
        if other and (batch == "" or "" in other):
            return msg("Pehle se hai", "Is date par isi subject ki doosri batch/poori class ki attendance pehle se bani hui hai. Duplicate nahi ban sakta.")
        self.sess_key = (cls["id"], subj, mk["date"], batch)
        sess = self.d.one("SELECT id FROM attendance_sessions WHERE class_id=? AND subject_id=? AND date=? AND batch=?", self.sess_key)
        saved = dict(self.db("SELECT student_id,status FROM attendance_records WHERE session_id=?", (sess["id"],))) if sess else {}
        day = mk["date"]
        lv = {x[0] for x in self.db("SELECT student_id FROM leave_requests WHERE status='approved' AND from_date<=? AND to_date>=?", (day, day))}
        self.studs, self.day = studs, day
        self.pend = {s["id"]: saved.get(s["id"]) or ("L" if s["id"] in lv else None) for s in studs}
        self.saved = any(s["id"] in saved for s in studs)
        self.hz = True
        self.refresh()

    def paint(self, btns, cur):
        for v, b in btns.items():
            on = v == cur
            b.bg = list(ST_COL[v] if on else GR)
            b.color = WHITE if on else MU

    def upd(self):
        n = sum(1 for s in self.studs if self.pend.get(s["id"]))
        self.cnt.text = "Marked: %d / %d   |   %s" % (n, len(self.studs), "Saved hai" if self.saved else "Abhi SAVE nahi hua")
        self.cnt.color = OK if self.saved else LV

    def setm(self, sid, v):
        self.pend[sid] = v
        self.saved = False
        self.paint(self.mw[sid], v)
        self.upd()

    def markall(self, v):
        for s in self.studs:
            self.setm(s["id"], v)

    def save_att(self):
        miss = sum(1 for s in self.studs if not self.pend.get(s["id"]))
        if miss:
            return msg("Adhuri hazri", "%d students ka Present/Absent/Leave mark baki hai." % miss)
        cid, subj, day, batch = self.sess_key
        sid = sid_for(cid, subj, day, batch)
        old = self.d.one("SELECT id FROM attendance_sessions WHERE class_id=? AND subject_id=? AND date=? AND batch=?", self.sess_key)
        if old and old["id"] != sid:
            self.d.delete_ids("attendance_records", [r[0] for r in self.db("SELECT id FROM attendance_records WHERE session_id=?", (old["id"],))])
            self.d.delete_ids("attendance_sessions", [old["id"]])
        ts = now_iso()
        self.d.put("attendance_sessions", [dict(id=sid, class_id=cid, subject_id=subj, date=day, batch=batch, marked_by=self.uid(), created_at=ts, updated_at=ts)])
        recs = [dict(id=rid_for(sid, s["id"]), session_id=sid, student_id=s["id"], status=self.pend[s["id"]], remark="", marked_by=self.uid(),
                     created_at=ts, updated_at=ts) for s in self.studs]
        self.d.put("attendance_records", recs)
        self.d.enqueue("rpc", "save_attendance", dict(p_session_id=sid, p_class_id=cid, p_subject_id=subj, p_date=day, p_batch=batch,
                                                      p_records=[{"id": r["id"], "student_id": r["student_id"], "status": r["status"], "remark": ""} for r in recs]))
        self.saved = True
        self.upd()
        self.sync_now()
        msg("Saved", "Attendance save ho gayi (%d students)." % len(self.studs) +
            ("" if self.status in ("synced", "syncing", "online") else "\nInternet aate hi cloud par upload ho jayegi."))

    def delete_att(self):
        def go():
            s = self.d.one("SELECT id FROM attendance_sessions WHERE class_id=? AND subject_id=? AND date=? AND batch=?", self.sess_key)
            if s:
                self.d.delete_ids("attendance_records", [r[0] for r in self.db("SELECT id FROM attendance_records WHERE session_id=?", (s["id"],))])
                self.d.delete_ids("attendance_sessions", [s["id"]])
                self.d.enqueue("delete", "attendance_sessions", {"q": "id=eq." + s["id"]})
                self.sync_now()
            self.hz = False
            self.refresh()
        ask("Attendance delete?", "Is class/subject/date ki poori attendance delete ho jayegi.", go, "Delete")

    def t_mark(self, g):
        if not self.hz:
            return self.selector(g, "Students dikhao", self.start_mark, extra=self.sub_widgets)
        c = Card()
        c.add_widget(lbl("Hazri", 18, bold=True))
        c.add_widget(lbl(dt.date.fromisoformat(self.day).strftime("%d %B %Y, %A"), 14, MU))
        c.add_widget(lbl(self.sname(self.sess_key[1]), 14, TX, True))
        c.add_widget(lbl(glabel(self.grp), 14, AC, True))
        self.cnt = lbl("", 13, MU, True)
        c.add_widget(self.cnt)
        c.add_widget(row(btn("Sab Present", lambda: self.markall("P"), "ok"), btn("Sab Absent", lambda: self.markall("A"), "danger")))
        c.add_widget(btn("Save Attendance", self.save_att))
        if self.saved:
            c.add_widget(btn("Ye attendance delete karo", self.delete_att, "plaindanger"))
        c.add_widget(btn("Class badlo", lambda: (setattr(self, "hz", False), self.refresh()), "muted"))
        g.add_widget(c)
        self.mw = {}
        for s in self.studs:
            c = Card()
            c.add_widget(row(lbl(s["roll"], 13, MU, True, w=96), lbl(fullname(s), 16, TX, True), h=30))
            btns = {v: RBtn(text=ST_TXT[v], font_size=sp(13)) for v in "PAL"}
            for v, b in btns.items():
                b.bind(on_release=lambda *_, sid=s["id"], v=v: self.setm(sid, v))
            self.mw[s["id"]] = btns
            self.paint(btns, self.pend.get(s["id"]))
            c.add_widget(row(*btns.values()))
            g.add_widget(c)
        c = Card()
        c.add_widget(btn("Save Attendance", self.save_att))
        g.add_widget(c)
        self.upd()

    # ---------- teacher: students ----------
    def student_fields(self, c, st, edit=False):
        fld(c, st, "Naam (First name)", "name")
        fld(c, st, "Surname", "surname")
        if edit:
            c.add_widget(lbl("Email: " + st.get("email", ""), 13, MU))
        else:
            fld(c, st, "Email (student ka login)", "email")
            fld(c, st, "Password (6+ akshar)", "pw", password=True)
        fld(c, st, "Mobile number (10 digit)", "mobile", num=True)
        fld(c, st, "Enrollment / Roll number", "roll")
        fld(c, st, "College / School ka naam", "college_name")
        c.add_widget(lbl("Padhai ka level", 12, MU))
        ib = {k: RBtn(text=t, bg=list(AC if st["inst"] == k else GR), color=WHITE if st["inst"] == k else MU,
                      on_release=lambda *_, k=k: (st.__setitem__("inst", k), self.refresh())) for k, t in (("college", "College"), ("school", "School"))}
        c.add_widget(row(ib["college"], ib["school"]))
        for w in class_fields(st, False, self.refresh):
            c.add_widget(w)

    def t_students(self, g):
        sf = self.sf
        sf.setdefault("q", "")
        c = Card()
        c.add_widget(lbl("Students", 18, bold=True))
        c.add_widget(btn("Form band karo" if self.show_add else "+ Naya student add karo", lambda: (setattr(self, "show_add", not self.show_add), self.refresh())))
        g.add_widget(c)
        if self.show_add:
            st = self.ns
            c = Card()
            c.add_widget(lbl("Naya student add karo", 17, bold=True))
            self.student_fields(c, st)
            c.add_widget(btn("+ Student add karo", self.add_student))
            g.add_widget(c)
        self.selector(g, "Filter lagao", self.refresh, st=sf, sel="all",
                      extra=lambda: [lbl("Search (naam / enrollment / email / mobile)", 12, MU), tin(sf, "q", "Search...")])
        studs = self.students(sf, sf["q"])
        c = Card()
        c.add_widget(lbl("Students (%d)" % len(studs), 16, bold=True))
        if len(studs) > 60:
            c.add_widget(lbl("Pehle 60 dikh rahe hain. Filter ya search se aur dekho.", 12, MU))
        g.add_widget(c)
        for s in studs[:60]:
            ok_ = bool(s["is_active"])
            c = Card()
            c.add_widget(row(lbl(s["roll"], 13, MU, True, w=96), lbl(fullname(s), 16, TX if ok_ else MU, True), h=30))
            c.add_widget(lbl("%s   |   %s" % (s["email"], s["mobile"]), 12, MU))
            c.add_widget(lbl(glabel(s) + ("" if ok_ else "   [DISABLED]"), 12, AC if ok_ else NO, True))
            c.add_widget(row(btn("View", lambda sid=s["id"]: self.view_student(sid)), btn("Edit", lambda sid=s["id"]: self.edit_student(sid), "ghost")))
            c.add_widget(row(btn("Password", lambda u=s: self.reset_pw(u), "muted"),
                             btn("Disable" if ok_ else "Enable", lambda u=s: self.toggle_active(u), "warn"),
                             btn("Hatao", lambda u=s: self.rm_student(u), "danger")))
            g.add_widget(c)

    def add_student(self):
        st = self.ns
        st["pw2"], st["role"] = st["pw"], "student"
        self.do_register(st, True)

    def get_avatar_async(self, sid):
        tried = self.__dict__.setdefault("av_try", set())
        if sid in tried:
            return
        tried.add(sid)
        self.bg(lambda: self.fetch_avatar(sid), lambda r, e: self.refresh() if self.sub else None)

    def view_student(self, sid):
        def page(g):
            self.back_card(g)
            s = self.d.one(SQ + " WHERE s.id=?", (sid,))
            if not s:
                c = Card()
                c.add_widget(lbl("Student nahi mila (shayad delete ho gaya).", 14, MU))
                g.add_widget(c)
                return
            if not self.d.one("SELECT 1 FROM avatars WHERE id=?", (sid,)):
                self.get_avatar_async(sid)
            self.hero(g, s, "Student", fullname(s), "Enrollment %s" % s["roll"])
            c = Card()
            for x in ("Email: " + s["email"], "Mobile: " + s["mobile"], "College: " + (s["college_name"] or "-"), "Class: " + glabel(s),
                      "Account: " + ("Active" if s["is_active"] else "DISABLED")):
                c.add_widget(lbl(x, 14, MU))
            g.add_widget(c)
            p, a, l, t, pc = self.stat(sid)
            col = NO if pc < self.thr and t else OK
            c = Card()
            c.add_widget(lbl("Attendance: %s" % pstr(pc, t), 17, col, True))
            c.add_widget(lbl("Present %d  |  Absent %d  |  Leave %d  |  Total %d" % (p, a, l, t), 13, MU))
            b = Bar(size_hint_y=None, height=dp(10), col=list(col))
            grow(b, pc)
            c.add_widget(b)
            g.add_widget(c)
            self.subject_card(g, sid)
            c = Card()
            c.add_widget(row(btn("Edit", lambda: self.edit_student(sid), "ghost"), btn("Password", lambda: self.reset_pw(s), "muted")))
            c.add_widget(row(btn("Disable" if s["is_active"] else "Enable", lambda: self.toggle_active(s), "warn"), btn("Hatao", lambda: self.rm_student(s), "danger")))
            g.add_widget(c)
            rs = self.rows("SELECT r.id,s.date,s.subject_id,r.status FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id "
                           "WHERE r.student_id=? ORDER BY s.date DESC LIMIT 40", (sid,))
            c = Card()
            c.add_widget(lbl("Attendance history (last 40)", 16, bold=True))
            if not rs:
                c.add_widget(lbl("Abhi koi record nahi.", 13, MU))
            g.add_widget(c)
            for r in rs:
                c = Card()
                c.add_widget(row(lbl("%s | %s" % (r["date"], self.sname(r["subject_id"])), 13, TX, True),
                                 lbl(ST_TXT[r["status"]], 13, ST_COL[r["status"]], True, "right", 70),
                                 small("Del", lambda rid=r["id"]: self.del_rec(rid), "danger", 46, height=dp(34)), h=34))
                g.add_widget(c)
        self.open_sub(page)

    def del_rec(self, rid):
        def go():
            self.d.delete_ids("attendance_records", [rid])
            self.d.enqueue("delete", "attendance_records", {"q": "id=eq." + rid})
            self.sync_now()
            self.refresh()
        ask("Record delete?", "Is student ka ye ek attendance record delete hoga.", go, "Delete")

    def edit_student(self, sid):
        s = self.d.one(SQ + " WHERE s.id=?", (sid,))
        if not s:
            return
        c0 = self.d.one("SELECT * FROM classes WHERE id=?", (s["class_id"],))
        st = dict(self.state_from_class(c0, s["batch"]), name=s["first_name"], surname=s["last_name"], mobile=s["mobile"], roll=s["roll"],
                  college_name=s["college_name"], email=s["email"], sid=sid)
        if not s["batch"]:
            st["batch"] = BATCHES[0]

        def page(g):
            self.back_card(g)
            c = Card()
            c.add_widget(lbl("Student edit karo", 17, bold=True))
            self.student_fields(c, st, True)
            c.add_widget(btn("Save changes", lambda: self.save_student(st)))
            g.add_widget(c)
        self.open_sub(page)

    def save_student(self, st):
        if not st["name"].strip() or not st["surname"].strip():
            return msg("Dhyan do", "Naam aur surname zaroori hain.")
        if not valid_mobile(st["mobile"].strip()):
            return msg("Dhyan do", "Mobile number 10 digit ka ho.")
        if not valid_enroll(st["roll"].strip()):
            return msg("Dhyan do", "Enrollment number 3-30 akshar ka ho.")
        if st["inst"] == "college" and st["branch"] == "Other" and not st["branch_o"].strip():
            return msg("Dhyan do", "Apni branch ka naam likho.")
        sid = st["sid"]
        if self.d.one("SELECT 1 FROM students WHERE lower(enrollment)=lower(?) AND id<>?", (st["roll"].strip(), sid)):
            return msg("Duplicate", "Ye enrollment number kisi aur student ka hai.")
        cid = self.ensure_class(st)
        batch = st["batch"] if st["inst"] == "college" and st["batch"] != "All" else ""
        full = ("%s %s" % (st["name"].strip(), st["surname"].strip())).strip()
        pv = dict(first_name=st["name"].strip(), last_name=st["surname"].strip(), full_name=full, mobile=st["mobile"].strip())
        sv = dict(enrollment=st["roll"].strip(), class_id=cid, batch=batch, college_name=st["college_name"].strip())
        self.db("UPDATE profiles SET first_name=?,last_name=?,full_name=?,mobile=?,updated_at=? WHERE id=?", (pv["first_name"], pv["last_name"], full, pv["mobile"], now_iso(), sid))
        self.db("UPDATE students SET enrollment=?,class_id=?,batch=?,college_name=?,updated_at=? WHERE id=?", (sv["enrollment"], cid, batch, sv["college_name"], now_iso(), sid))
        self.d.enqueue("patch", "profiles", {"q": "id=eq." + sid, "values": pv})
        self.d.enqueue("patch", "students", {"q": "id=eq." + sid, "values": sv})
        self.sync_now()
        self.sub, self.hz = None, False
        msg("Done", "Student update ho gaya.")
        self.refresh()

    def reset_pw(self, s):
        def done(p):
            if len(p) < 6:
                return msg("Dhyan do", "Password kam se kam 6 akshar ka ho.")
            self.net(lambda: self.api.rpc("admin_set_password", {"p_id": s["id"], "p_password": p}),
                     lambda _: msg("Done", "%s ka naya (temporary) password set ho gaya.\nStudent login karke Profile me apna password badal le." % fullname(s)),
                     "Password badal rahe hain...")
        prompt("Naya password", "Naya password (6+ akshar)", done)

    def toggle_active(self, s):
        on = not s["is_active"]

        def go():
            def ok(_):
                self.db("UPDATE profiles SET is_active=? WHERE id=?", (1 if on else 0, s["id"]))
                self.refresh()
            self.net(lambda: self.api.rpc("admin_set_active", {"p_id": s["id"], "p_active": on}), ok, "Update ho raha hai...")
        ask("Account %s?" % ("enable" if on else "disable"),
            "%s ka account %s ho jayega." % (fullname(s), "chalu" if on else "band (wo login nahi kar paayega)"), go, "Haan", "warn")

    def rm_student(self, s):
        def go():
            def ok(_):
                sid = s["id"]
                self.d.delete_ids("attendance_records", [r[0] for r in self.db("SELECT id FROM attendance_records WHERE student_id=?", (sid,))])
                self.d.delete_ids("leave_requests", [r[0] for r in self.db("SELECT id FROM leave_requests WHERE student_id=?", (sid,))])
                self.d.delete_ids("students", [sid])
                self.d.delete_ids("profiles", [sid])
                self.d.delete_ids("avatars", [sid])
                self.sub, self.hz = None, False
                self.refresh()
            self.net(lambda: self.api.rpc("admin_delete_student", {"p_id": s["id"]}), ok, "Student hata rahe hain...")
        ask("Student hatao?", "%s aur uski saari attendance hamesha ke liye delete ho jayegi. Ye wapas nahi aa sakta." % fullname(s), go, "Delete")

    # ---------- teacher: report ----------
    def stat_map(self, sub=None, d1=None, d2=None):
        sql = "SELECT r.student_id,r.status,COUNT(*) FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id WHERE 1=1"
        a = []
        for cond, v in ((" AND s.subject_id=?", sub), (" AND s.date>=?", d1), (" AND s.date<=?", d2)):
            if v:
                sql += cond
                a.append(v)
        m = {}
        for sid, s, n in self.db(sql + " GROUP BY r.student_id,r.status", a):
            m.setdefault(sid, {})[s] = n
        return m

    def show_rep(self):
        self.rep = True
        self.refresh()

    def report_data(self):
        rf, rs = self.rf, self.__dict__.setdefault("rs", all_state())
        labels = {"%s - %s" % (s["code"], s["name"]): s["id"] for s in self.rows("SELECT * FROM subjects ORDER BY name")}
        sub = labels.get(rf["subject"])
        d1, d2 = (rf["d1"] if vd(rf["d1"]) else None), (rf["d2"] if vd(rf["d2"]) else None)
        m = self.stat_map(sub, d1, d2)
        return labels, [(s, self.mkstat(m.get(s["id"], {}).get("P", 0), m.get(s["id"], {}).get("A", 0), m.get(s["id"], {}).get("L", 0)))
                        for s in self.students(rs, rf["q"])]

    def t_report(self, g):
        rf, rs = self.rf, self.__dict__.setdefault("rs", all_state())
        labels = {"%s - %s" % (s["code"], s["name"]): s["id"] for s in self.rows("SELECT * FROM subjects ORDER BY name")}

        def extra():
            return [lbl("Subject", 12, MU), spin(rf, "subject", ["All"] + list(labels)),
                    lbl("Date range (YYYY-MM-DD)", 12, MU), row(tin(rf, "d1", "Se"), tin(rf, "d2", "Tak")),
                    lbl("Student (naam / enrollment / email)", 12, MU), tin(rf, "q", "Search...")]
        self.selector(g, "Report dikhao", self.show_rep, st=rs, sel="all", extra=extra)
        if not self.rep:
            return self.del_card(g)
        labels, data = self.report_data()
        c = Card()
        c.add_widget(lbl("Attendance Report", 18, bold=True))
        c.add_widget(lbl(glabel(rs), 13, AC, True))
        c.add_widget(lbl("Subject: %s   |   %s se %s" % (rf["subject"], rf["d1"] or "shuru", rf["d2"] or "aaj tak"), 12, MU))
        done = [d for d in data if d[1][3]]
        avg = sum(d[1][4] for d in done) / len(done) if done else 0
        c.add_widget(lbl("Students: %d   |   Class average: %.1f%%   |   %d%% se kam: %d" % (len(data), avg, self.thr, sum(1 for d in done if d[1][4] < self.thr)), 13, MU))
        c.add_widget(row(btn("CSV export", lambda: self.export(data, "csv")), btn("PDF export", lambda: self.export(data, "pdf"), "ghost")))
        g.add_widget(c)
        if not data:
            c = Card()
            c.add_widget(lbl("Is filter me koi student nahi.", 14, MU))
            g.add_widget(c)
        for s, (p, a, l, t, pc) in data[:150]:
            col = NO if pc < self.thr and t else OK
            c = Card()
            c.add_widget(row(lbl(s["roll"], 13, MU, True, w=96), lbl(fullname(s), 16, TX, True), lbl(pstr(pc, t), 15, col, True, "right", 78), h=30))
            c.add_widget(lbl("Present: %d   |   Absent: %d   |   Leave: %d   |   Total: %d" % (p, a, l, t), 13, MU))
            b = Bar(size_hint_y=None, height=dp(10), col=list(col))
            grow(b, pc)
            c.add_widget(b)
            g.add_widget(c)
        if len(data) > 150:
            c = Card()
            c.add_widget(lbl("Screen par pehle 150 dikh rahe hain. Export me sab milenge.", 12, MU))
            g.add_widget(c)
        self.del_card(g)

    def save_export(self, name, data, mime):
        try:
            from jnius import autoclass
            if autoclass("android.os.Build$VERSION").SDK_INT >= 29:
                act = autoclass("org.kivy.android.PythonActivity").mActivity
                cv = autoclass("android.content.ContentValues")()
                cv.put("_display_name", name)
                cv.put("mime_type", mime)
                cv.put("relative_path", "Download/")
                cr = act.getContentResolver()
                uri = cr.insert(autoclass("android.provider.MediaStore$Downloads").EXTERNAL_CONTENT_URI, cv)
                os_ = cr.openOutputStream(uri)
                os_.write(bytearray(data))
                os_.close()
                return "Download/" + name
        except Exception as e:
            log(e, "mediastore")
        for base in ("/storage/emulated/0/Download", os.path.join(self.user_data_dir, "exports")):
            try:
                os.makedirs(base, exist_ok=True)
                path = os.path.join(base, name)
                with open(path, "wb") as f:
                    f.write(data)
                return path
            except Exception:
                continue
        return ""

    def export(self, data, fmt):
        head = ["Enrollment", "Name", "Present", "Absent", "Leave", "Total Classes", "Percentage"]
        rows = [[s["roll"], fullname(s), p, a, l, t, pstr(pc, t)] for s, (p, a, l, t, pc) in data]
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        if fmt == "csv":
            name, blob, mime = "attendance_report_%s.csv" % stamp, make_csv(head, rows), "text/csv"
        else:
            name, mime = "attendance_report_%s.pdf" % stamp, "application/pdf"
            blob = make_pdf("Attendance Report", "%s | Subject: %s | %s to %s" % (glabel(self.rs), self.rf["subject"], self.rf["d1"] or "start", self.rf["d2"] or "today"),
                            head, rows, [1.3, 3, .9, .9, .9, 1.3, 1.3])
        path = self.save_export(name, blob, mime)
        msg("Ho gaya", "File save hui:\n" + path) if path else msg("Error", "File save nahi ho payi. Storage permission check karo.")

    def del_card(self, g):
        mn = self.db("SELECT MIN(date) FROM attendance_sessions")[0][0] or today()
        old = (dt.date.today() - dt.timedelta(days=365)).isoformat()
        c = Card()
        c.add_widget(lbl("Purani attendance delete karo", 16, bold=True))
        c.add_widget(lbl("Upar chuni hui class (aur subject) ki attendance, is date range me delete hogi (cloud se bhi). Default: 1 saal se purani.", 12, MU))
        f, t = inp("Se (YYYY-MM-DD)", mn), inp("Tak (YYYY-MM-DD)", max(min(old, today()), mn))
        c.add_widget(f)
        c.add_widget(t)

        def go():
            if not (vd(f.text) and vd(t.text)) or t.text < f.text:
                return msg("Dhyan do", "Dates (YYYY-MM-DD) sahi bharo, 'Tak' date 'Se' se baad ki ho.")
            cids = {s["class_id"] for s in self.students(self.rs)}
            if not cids:
                return msg("Koi student nahi", "Is filter me koi class nahi mili.")
            labels = {"%s - %s" % (s["code"], s["name"]): s["id"] for s in self.rows("SELECT * FROM subjects")}
            sub = labels.get(self.rf["subject"])
            sql = "SELECT id FROM attendance_sessions WHERE date BETWEEN ? AND ? AND class_id IN (%s)" % ",".join("?" * len(cids))
            a = [f.text, t.text] + list(cids)
            if sub:
                sql += " AND subject_id=?"
                a.append(sub)
            ids = [r[0] for r in self.db(sql, a)]
            if not ids:
                return msg("Kuch nahi mila", "Is range me koi attendance nahi hai.")
            ask("Pakka delete?", "%s\n%s se %s tak ki %d class-sessions delete hongi. Ye wapas nahi aa sakti." % (glabel(self.rs), f.text, t.text, len(ids)),
                lambda: self.do_del(ids))
        c.add_widget(btn("Delete karo", go, "danger"))
        g.add_widget(c)

    def do_del(self, ids):
        for i in range(0, len(ids), 40):
            ch = ids[i:i + 40]
            for sid in ch:
                self.d.delete_ids("attendance_records", [r[0] for r in self.db("SELECT id FROM attendance_records WHERE session_id=?", (sid,))])
            self.d.delete_ids("attendance_sessions", ch)
            self.d.enqueue("delete", "attendance_sessions", {"q": "id=in.(%s)" % ",".join(ch)})
        self.sync_now()
        self.hz = False
        msg("Ho gaya", "Purani attendance delete ho gayi.")
        self.refresh()

    # ---------- teacher: leaves ----------
    def t_leaves(self, g):
        self.back_card(g)
        rs = self.rows("SELECT l.*, p.full_name, s.enrollment AS roll, c.kind AS inst, c.branch, c.year, c.semester AS sem, c.section AS sec, c.branch AS cls, s.batch "
                       "FROM leave_requests l JOIN students s ON s.id=l.student_id JOIN profiles p ON p.id=l.student_id JOIN classes c ON c.id=s.class_id "
                       "ORDER BY CASE l.status WHEN 'pending' THEN 0 ELSE 1 END, l.created_at DESC LIMIT 100")
        if not rs:
            c = Card()
            c.add_widget(lbl("Koi leave request nahi.", 14, MU))
            g.add_widget(c)
        for r in rs:
            c = Card()
            c.add_widget(row(lbl(r["full_name"], 16, TX, True), lbl(r["status"].upper(), 13, {"pending": LV, "approved": OK, "rejected": NO}[r["status"]], True, "right", 100), h=30))
            c.add_widget(lbl("Enrollment %s  |  %s" % (r["roll"], glabel(r)), 12, MU))
            c.add_widget(lbl("%s  to  %s" % (r["from_date"], r["to_date"]), 13, AC, True))
            c.add_widget(lbl(r["reason"], 14))
            if r["status"] == "pending":
                c.add_widget(row(btn("Approve", lambda i=r["id"]: self.decide(i, True), "ok"), btn("Reject", lambda i=r["id"]: self.decide(i, False), "danger")))
            g.add_widget(c)

    def decide(self, lid, ok):
        r = self.d.one("SELECT * FROM leave_requests WHERE id=?", (lid,))
        if not r:
            return
        st = "approved" if ok else "rejected"
        self.db("UPDATE leave_requests SET status=?,decided_by=?,updated_at=? WHERE id=?", (st, self.uid(), now_iso(), lid))
        self.d.enqueue("patch", "leave_requests", {"q": "id=eq." + lid, "values": {"status": st, "decided_by": self.uid()}})
        nid = str(uuid.uuid4())
        self.d.enqueue("insert", "notifications", {"id": nid, "user_id": r["student_id"], "title": "Leave %s" % st,
                                                  "body": "%s se %s ki leave request %s." % (r["from_date"], r["to_date"], st), "kind": "leave", "is_read": False})
        self.sync_now()
        self.paint_nav()
        self.refresh()

    # ---------- teacher: setup (subjects, classes, notice) ----------
    def t_setup(self, g):
        self.__dict__.setdefault("asg", dict(new_state(), batch="B1", code="", sname="", subject="", teacher=""))
        self.__dict__.setdefault("nt", dict(all_state(), title="", body=""))
        sj, asg = self.rows("SELECT * FROM subjects ORDER BY name"), self.asg
        c = Card()
        c.add_widget(lbl("Subjects", 17, bold=True))
        c.add_widget(lbl("Naya subject", 12, MU))
        c.add_widget(tin(asg, "code", "Subject code (jaise CS101)"))
        c.add_widget(tin(asg, "sname", "Subject ka naam"))
        c.add_widget(btn("+ Subject add karo", self.add_subject))
        g.add_widget(c)
        n = self.pending_leaves()
        c = Card()
        c.add_widget(btn("Leave requests%s" % (" (%d pending)" % n if n else ""), lambda: self.open_sub(self.t_leaves), "warn" if n else "ghost"))
        g.add_widget(c)
        labels = {"%s - %s" % (s["code"], s["name"]): s["id"] for s in sj}
        teachers = self.rows("SELECT id,full_name,email FROM profiles WHERE role IN ('teacher','admin') ORDER BY full_name")
        tl = {"%s (%s)" % (t["full_name"], t["email"]): t["id"] for t in teachers}
        c = Card()
        c.add_widget(lbl("Class banao / Subject assign karo", 16, bold=True))
        ib = {k: RBtn(text=t, bg=list(AC if asg["inst"] == k else GR), color=WHITE if asg["inst"] == k else MU,
                      on_release=lambda *_, k=k: (asg.__setitem__("inst", k), self.refresh())) for k, t in (("college", "College"), ("school", "School"))}
        c.add_widget(row(ib["college"], ib["school"]))
        for w in class_fields(asg, False, self.refresh):
            c.add_widget(w)
        c.add_widget(btn("Sirf class banao", self.add_class, "ghost"))
        if labels:
            c.add_widget(lbl("Subject", 12, MU))
            c.add_widget(spin(asg, "subject", list(labels)))
            c.add_widget(lbl("Teacher", 12, MU))
            if not asg.get("teacher"):
                asg["teacher"] = next((k for k, v in tl.items() if v == self.uid()), "")
            c.add_widget(spin(asg, "teacher", list(tl) or ["-"]))
            c.add_widget(btn("Is class me subject assign karo", lambda: self.assign_subject(labels, tl)))
        g.add_widget(c)
        for s in sj:
            c = Card()
            c.add_widget(row(lbl("%s - %s" % (s["code"], s["name"]), 15, TX, True), small("Edit", lambda x=s: self.edit_subject(x), "ghost", 56, height=dp(36)),
                             small("Del", lambda x=s: self.del_subject(x), "danger", 50, height=dp(36)), h=36))
            for a in self.rows("SELECT cs.id AS csid, p.full_name, c.kind,c.branch,c.year,c.semester,c.section FROM class_subjects cs JOIN classes c ON c.id=cs.class_id "
                               "LEFT JOIN profiles p ON p.id=cs.teacher_id WHERE cs.subject_id=? ORDER BY c.branch,c.year,c.section", (s["id"],)):
                c.add_widget(row(lbl("%s  (%s)" % (class_label(dict(a, semester=a["semester"])), a["full_name"] or "-"), 12, MU),
                                 small("x", lambda i=a["csid"]: self.unassign(i), "plaindanger", 40, height=dp(32)), h=32))
            g.add_widget(c)
        c = Card()
        c.add_widget(lbl("Classes", 17, bold=True))
        cl = self.rows("SELECT * FROM classes ORDER BY kind,branch,year,semester,section")
        if not cl:
            c.add_widget(lbl("Abhi koi class nahi. Upar se class banao.", 13, MU))
        for k in cl:
            ns_ = self.db("SELECT COUNT(*) FROM students WHERE class_id=?", (k["id"],))[0][0]
            c.add_widget(row(lbl("%s   [%d students]" % (class_label(dict(k, semester=k["semester"])), ns_), 13, TX, True),
                             small("Del", lambda x=k, n=ns_: self.del_class(x, n), "plaindanger", 50, height=dp(34)), h=34))
        g.add_widget(c)
        nt = self.nt
        self.selector(g, "Notice bhejo", self.send_notice, st=nt, sel="all",
                      extra=lambda: [lbl("Class ko notice (upar se class chuno)", 12, MU), tin(nt, "title", "Title"), tin(nt, "body", "Message")])

    def add_subject(self):
        asg = self.asg
        code, name = asg["code"].strip(), asg["sname"].strip()
        if not code or not name:
            return msg("Dhyan do", "Subject code aur naam dono likho.")
        if self.d.one("SELECT 1 FROM subjects WHERE lower(code)=lower(?)", (code,)):
            return msg("Duplicate", "Ye subject code pehle se hai.")
        r = dict(id=str(uuid.uuid4()), code=code, name=name, created_at=now_iso(), updated_at=now_iso())
        self.d.put("subjects", [r])
        self.d.enqueue("upsert", "subjects", {k: r[k] for k in wcols("subjects")})
        asg["code"] = asg["sname"] = ""
        self.sync_now()
        self.refresh()

    def edit_subject(self, s):
        b = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        c, n = inp("Code", s["code"]), inp("Naam", s["name"])
        b.add_widget(c)
        b.add_widget(n)
        p = pop("Subject edit", b, 260)

        def ok():
            if not c.text.strip() or not n.text.strip():
                return msg("Dhyan do", "Code aur naam likho.")
            if self.d.one("SELECT 1 FROM subjects WHERE lower(code)=lower(?) AND id<>?", (c.text.strip(), s["id"])):
                return msg("Duplicate", "Ye code kisi aur subject ka hai.")
            p.dismiss()
            self.db("UPDATE subjects SET code=?,name=?,updated_at=? WHERE id=?", (c.text.strip(), n.text.strip(), now_iso(), s["id"]))
            self.d.enqueue("upsert", "subjects", {"id": s["id"], "code": c.text.strip(), "name": n.text.strip()})
            self.sync_now()
            self.refresh()
        b.add_widget(row(btn("Cancel", p.dismiss, "muted"), btn("Save", ok)))
        p.open()

    def del_subject(self, s):
        if self.db("SELECT COUNT(*) FROM attendance_sessions WHERE subject_id=?", (s["id"],))[0][0]:
            return msg("Delete nahi ho sakta", "Is subject ki attendance bani hui hai. Pehle wo attendance delete karo.")

        def go():
            self.d.delete_ids("class_subjects", [r[0] for r in self.db("SELECT id FROM class_subjects WHERE subject_id=?", (s["id"],))])
            self.d.delete_ids("subjects", [s["id"]])
            self.d.enqueue("delete", "subjects", {"q": "id=eq." + s["id"]})
            self.sync_now()
            self.refresh()
        ask("Subject hatao?", "%s delete ho jayega (class assignments bhi)." % s["name"], go, "Delete")

    def add_class(self):
        asg = self.asg
        if asg["inst"] == "college" and asg["branch"] == "Other" and not asg["branch_o"].strip():
            return msg("Dhyan do", "Apni branch ka naam likho.")
        if self.find_class(asg):
            return msg("Pehle se hai", "Ye class pehle se bani hui hai.")
        self.ensure_class(asg)
        self.sync_now()
        self.refresh()

    def assign_subject(self, labels, tl):
        asg = self.asg
        sub = labels.get(asg["subject"])
        if not sub:
            return msg("Dhyan do", "Subject chuno.")
        if asg["inst"] == "college" and asg["branch"] == "Other" and not asg["branch_o"].strip():
            return msg("Dhyan do", "Apni branch ka naam likho.")
        cid = self.ensure_class(asg)
        r = dict(id=str(uuid.uuid5(NS, "cs|%s|%s" % (cid, sub))), class_id=cid, subject_id=sub, teacher_id=tl.get(asg.get("teacher")),
                 created_at=now_iso(), updated_at=now_iso())
        old = self.d.one("SELECT id FROM class_subjects WHERE class_id=? AND subject_id=?", (cid, sub))
        if old:
            r["id"] = old["id"]
        self.d.put("class_subjects", [r])
        self.d.enqueue("upsert", "class_subjects", {k: r[k] for k in wcols("class_subjects")})
        self.sync_now()
        self.toast("Subject assign ho gaya.", OK)
        self.refresh()

    def unassign(self, i):
        self.d.delete_ids("class_subjects", [i])
        self.d.enqueue("delete", "class_subjects", {"q": "id=eq." + i})
        self.sync_now()
        self.refresh()

    def del_class(self, k, n):
        if n or self.db("SELECT COUNT(*) FROM attendance_sessions WHERE class_id=?", (k["id"],))[0][0]:
            return msg("Delete nahi ho sakta", "Is class me students ya attendance hai. Pehle unhe hatao/shift karo.")

        def go():
            self.d.delete_ids("class_subjects", [r[0] for r in self.db("SELECT id FROM class_subjects WHERE class_id=?", (k["id"],))])
            self.d.delete_ids("classes", [k["id"]])
            self.d.enqueue("delete", "classes", {"q": "id=eq." + k["id"]})
            self.sync_now()
            self.refresh()
        ask("Class hatao?", "Ye class delete ho jayegi.", go, "Delete")

    def send_notice(self):
        nt = self.nt
        if not nt["title"].strip() or not nt["body"].strip():
            return msg("Dhyan do", "Title aur message likho.")
        studs = self.students(nt)
        if not studs:
            return msg("Koi student nahi", "Is class me koi student nahi hai.")
        rows = [{"id": str(uuid.uuid4()), "user_id": s["id"], "title": nt["title"].strip(), "body": nt["body"].strip(), "kind": "message", "is_read": False}
                for s in studs]
        for i in range(0, len(rows), 100):
            self.d.enqueue("insert", "notifications", rows[i:i + 100])
        nt["title"] = nt["body"] = ""
        self.sync_now()
        msg("Bhej diya", "Notice %d students ko bhej diya gaya (internet na ho to baad me)." % len(rows))
        self.refresh()


if __name__ == "__main__":
    SmartHazri().run()
