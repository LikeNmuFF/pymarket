from email.mime.text import MIMEText
import smtplib
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
import uuid
import urllib.parse
from datetime import datetime
from functools import wraps
from bot import maybe_bot_reply
from flask import g

app = Flask(__name__)
app.secret_key = 'e5c79b13fc865bc5baee6a329f022f89434624b81bbd5119955f610f997e182d'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'market.db')

UPLOAD_SCREENSHOTS = os.path.join(BASE_DIR, 'static', 'uploads', 'screenshots')
UPLOAD_PROJECTS = os.path.join(BASE_DIR, 'static', 'uploads', 'projects')
UPLOAD_PAYMENTS = os.path.join(BASE_DIR, 'static', 'uploads', 'payments')
UPLOAD_AVATARS = os.path.join(BASE_DIR, 'static', 'uploads', 'avatars')

for folder in [UPLOAD_SCREENSHOTS, UPLOAD_PROJECTS, UPLOAD_PAYMENTS, UPLOAD_AVATARS]:
    os.makedirs(folder, exist_ok=True)

ALLOWED_IMG = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_PROJECT = {'zip', 'rar', 'tar', 'gz', 'py'}
VAT_RATE = 0.05
GCASH_NUMBER = '09518346025'
GCASH_NAME = 'RO....O B.'


def get_db():
    """Get a per-request DB connection cached in Flask g, so it is always closed after the request."""
    if 'db' not in g:
        conn = sqlite3.connect(DB_PATH, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def _wants_json_error():
    accept = (request.headers.get('Accept') or '').lower()
    if request.is_json:
        return True
    if request.path in ('/admin/ai', '/promo/check', '/notifications/count', '/chat/widget'):
        return True
    return 'application/json' in accept and 'text/html' not in accept


@app.errorhandler(404)
def not_found(error):
    if _wants_json_error():
        return jsonify({'error': 'not_found'}), 404
    return render_template('404.html', path=request.path), 404


@app.errorhandler(500)
def server_error(error):
    error_id = uuid.uuid4().hex[:10]
    try:
        app.logger.exception("Internal server error %s on %s", error_id, request.path)
    except Exception:
        pass

    if _wants_json_error():
        return jsonify({'error': 'internal_server_error', 'error_id': error_id}), 500
    return render_template('500.html', error_id=error_id, path=request.path), 500


def init_db():
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                bio TEXT DEFAULT '',
                avatar TEXT DEFAULT '',
                is_admin INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                price REAL NOT NULL,
                tech_stack TEXT,
                category TEXT,
                file_path TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_ref TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                project_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                status TEXT DEFAULT "pending",
                gcash_ref TEXT,
                payment_screenshot TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                approved_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                order_id INTEGER,
                is_admin_reply INTEGER DEFAULT 0,
                message TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(order_id) REFERENCES orders(id)
            );
            CREATE TABLE IF NOT EXISTS auctions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                start_price REAL NOT NULL DEFAULT 0,
                min_increment REAL NOT NULL DEFAULT 10,
                starts_at TEXT NOT NULL,
                ends_at TEXT NOT NULL,
                status TEXT DEFAULT 'upcoming',
                winner_id INTEGER,
                winning_bid REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id),
                FOREIGN KEY(winner_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                comment TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, user_id),
                FOREIGN KEY(project_id) REFERENCES projects(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS project_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                viewed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS auction_bids (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                auction_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(auction_id) REFERENCES auctions(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
        ''')
        try:
            db.execute("ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''")
        except:
            pass
        try:
            db.execute("ALTER TABLE users ADD COLUMN avatar TEXT DEFAULT ''")
        except:
            pass
        try:
            db.execute(
                "ALTER TABLE auctions ADD COLUMN start_price REAL NOT NULL DEFAULT 0")
        except:
            pass
        try:
            db.execute(
                "ALTER TABLE auctions ADD COLUMN min_increment REAL NOT NULL DEFAULT 10")
        except:
            pass
        try:
            db.execute("ALTER TABLE auctions ADD COLUMN starts_at TEXT")
        except:
            pass
        try:
            db.execute("ALTER TABLE auctions ADD COLUMN ends_at TEXT")
        except:
            pass
        try:
            db.execute(
                "ALTER TABLE auctions ADD COLUMN status TEXT DEFAULT 'upcoming'")
        except:
            pass
        try:
            db.execute("ALTER TABLE auctions ADD COLUMN winner_id INTEGER")
        except:
            pass
        try:
            db.execute("ALTER TABLE auctions ADD COLUMN winning_bid REAL")
        except:
            pass
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL, rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id, user_id), FOREIGN KEY(project_id) REFERENCES projects(id),
            FOREIGN KEY(user_id) REFERENCES users(id))""")
        except:
            pass
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS project_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
            viewed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id))""")
        except:
            pass
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS faq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        except:
            pass
        # Seed default FAQs if table is empty
        try:
            count = db.execute("SELECT COUNT(*) as c FROM faq").fetchone()['c']
            if count == 0:
                faqs = [
                    ("What is PyMarket?", "PyMarket is a marketplace for ready-made Python projects. Each project is sold exclusively to one buyer — you get full source code, lifetime access, and real ownership.", 1),
                    ("How do I pay?", "All payments are made via GCash. Simply browse a project, click Buy, scan the QR code or send to our GCash number, then submit your reference number and receipt screenshot.", 2),
                    ("How long until my order is approved?",
                     "Admin manually verifies each payment. Approval usually takes a few hours. You'll be able to download your project as soon as it's approved.", 3),
                    ("Can multiple people buy the same project?",
                     "No — each project is sold to exactly ONE buyer only. Once purchased, it shows as Sold Out. This gives you exclusive ownership of the source code.", 4),
                    ("What is an auction?", "Some projects are listed on auction. Registered users can place bids in real time. The highest bidder when the timer ends wins and pays via GCash at their winning bid price.", 5),
                    ("Can I get a refund?", "All sales are final. Please review the project description and screenshots carefully before purchasing. Contact admin via Support Chat if you have concerns.", 6),
                    ("What file formats are included?",
                     "Projects are delivered as .zip, .rar, or .py files containing full source code, ready to run.", 7),
                    ("Do I need an account to browse?",
                     "No — you can browse all projects without an account. You only need to register when you want to buy or bid.", 8),
                ]
                for q, a, s in faqs:
                    db.execute(
                        "INSERT INTO faq (question, answer, sort_order) VALUES (?,?,?)", (q, a, s))
                db.commit()
        except:
            pass
        # New tables
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            discount_type TEXT NOT NULL DEFAULT 'percent',
            discount_value REAL NOT NULL,
            max_uses INTEGER DEFAULT 0,
            used_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            expires_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        except:
            pass
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS promo_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promo_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            order_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        except:
            pass
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            link TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id))""")
        except:
            pass
        # Reservations table
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id),
            FOREIGN KEY(user_id) REFERENCES users(id))""")
        except:
            pass
        # Project discount columns
        try:
            db.execute("ALTER TABLE projects ADD COLUMN original_price REAL")
        except:
            pass
        try:
            db.execute(
                "ALTER TABLE projects ADD COLUMN discount_percent REAL DEFAULT 0")
        except:
            pass
        # View count column (fast)
        try:
            db.execute(
                "ALTER TABLE projects ADD COLUMN view_count INTEGER DEFAULT 0")
        except:
            pass
        try:
            db.execute("INSERT INTO users (username,email,password,is_admin) VALUES (?,?,?,1)",
                       ('admin', 'admin@pymarket.com', generate_password_hash('admin123')))
            db.commit()
        except:
            pass


# ── Email config ─────────────────────────────────────────────────────────────

MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USERNAME = 'kleia6678@gmail.com'   # ← your Gmail address
MAIL_PASSWORD = 'smwqemlpykznlvxh'   # ← your Gmail App Password
MAIL_FROM = 'PyMarket <noreply@pymarket.com>'


def send_email(to, subject, body_html):
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        return  # Email not configured, skip silently
    try:
        msg = MIMEText(body_html, 'html')
        msg['Subject'] = subject
        msg['From'] = MAIL_FROM
        msg['To'] = to
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as s:
            s.starttls()
            s.login(MAIL_USERNAME, MAIL_PASSWORD)
            s.sendmail(MAIL_USERNAME, to, msg.as_string())
    except Exception as e:
        print(f"Email error: {e}")


def notify_user(db, user_id, message, link=None):
    """Create an in-app notification for a user."""
    db.execute("INSERT INTO notifications (user_id, message, link) VALUES (?,?,?)",
               (user_id, message, link))
    db.commit()


def apply_promo(db, code, user_id, base_price):
    """Validate and apply a promo code. Returns (discount_amount, promo_row) or (0, None)."""
    if not code:
        return 0, None
    promo = db.execute("""
        SELECT * FROM promo_codes
        WHERE UPPER(code)=UPPER(?) AND is_active=1
        AND (expires_at IS NULL OR expires_at > ?)
        AND (max_uses=0 OR used_count < max_uses)
    """, (code, datetime.now().isoformat())).fetchone()
    if not promo:
        return 0, None
    # Check if user already used this code
    used = db.execute("SELECT id FROM promo_uses WHERE promo_id=? AND user_id=?",
                      (promo['id'], user_id)).fetchone()
    if used:
        return 0, None
    if promo['discount_type'] == 'percent':
        discount = round(base_price * promo['discount_value'] / 100, 2)
    else:
        discount = min(promo['discount_value'], base_price)
    return discount, promo


def calc_price(project, promo_discount=0):
    """Calculate base, sale, vat, total prices for a project."""
    original = project['price']
    # Project-level discount
    if project['discount_percent'] and project['discount_percent'] > 0:
        sale_price = round(
            original * (1 - project['discount_percent'] / 100), 2)
    else:
        sale_price = original
    after_promo = max(0, sale_price - promo_discount)
    vat = round(after_promo * VAT_RATE, 2)
    total = round(after_promo + vat, 2)
    return {
        'original':     original,
        'sale_price':   sale_price,
        'promo_discount': promo_discount,
        'base_price':   after_promo,
        'vat_amount':   vat,
        'total_price':  total,
        'has_discount': sale_price < original,
        'discount_pct': project['discount_percent'] or 0,
    }


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('login_required')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename, allowed):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


def gcash_qr_url(amount, note=''):
    data = f"Send PHP {amount} to {GCASH_NUMBER} ({GCASH_NAME}) via GCash. Ref: {note}"
    encoded = urllib.parse.quote(data)
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded}"


def auction_status(a):
    now = datetime.now().isoformat()
    starts = a['starts_at'] or ''
    ends = a['ends_at'] or ''
    if not starts or now < starts:
        return 'upcoming'
    if ends and now > ends:
        return 'ended'
    return 'live'


def get_active_auction(db, project_id):
    """Returns auction that is currently live for this project."""
    now = datetime.now().isoformat()
    return db.execute(
        "SELECT id FROM auctions WHERE project_id=? AND starts_at <= ? AND ends_at >= ?",
        (project_id, now, now)).fetchone()


def get_ended_auction_winner(db, project_id):
    """Returns ended auction with winner info. Always returns if auction ended with bids."""
    now = datetime.now().isoformat()
    # Get the most recent ended auction for this project that had bids
    auction = db.execute("""
        SELECT a.*,
            (SELECT MAX(amount) FROM auction_bids WHERE auction_id=a.id) as winning_amount,
            (SELECT COUNT(*) FROM auction_bids WHERE auction_id=a.id) as total_bids
        FROM auctions a
        WHERE a.project_id=? AND a.ends_at < ?
        ORDER BY a.ends_at DESC LIMIT 1
    """, (project_id, now)).fetchone()
    if not auction or not auction['total_bids']:
        return None
    # Get winner separately to avoid subquery type issues
    winner_bid = db.execute(
        "SELECT b.user_id, u.username FROM auction_bids b JOIN users u ON b.user_id=u.id WHERE b.auction_id=? ORDER BY b.amount DESC LIMIT 1",
        (auction['id'],)).fetchone()
    if not winner_bid:
        return None
    # Check if winner already has a pending/approved order for this project
    already_paid = db.execute(
        "SELECT id FROM orders WHERE project_id=? AND user_id=? AND status IN ('pending','approved')",
        (project_id, winner_bid['user_id'])).fetchone()
    if already_paid:
        return None  # Winner already paid, treat as normal sold-out
    result = dict(auction)
    result['winner_id'] = winner_bid['user_id']
    result['winner_username'] = winner_bid['username']
    return result

# ── Public ────────────────────────────────────────────────────────────────────


@app.route('/')
def index():
    db = get_db()
    search = request.args.get('q', '')
    category = request.args.get('cat', '')
    now = datetime.now().isoformat()
    query = """
        SELECT p.*,
            (SELECT filename FROM screenshots WHERE project_id=p.id LIMIT 1) as thumb,
            (SELECT COUNT(*) FROM orders o WHERE o.project_id=p.id AND o.status='approved') as buyer_count,
            (SELECT GROUP_CONCAT(u.username, ', ')
             FROM orders o JOIN users u ON o.user_id=u.id
             WHERE o.project_id=p.id AND o.status='approved') as buyer_names,
            (SELECT COUNT(*) FROM orders o WHERE o.project_id=p.id AND o.status='approved') as is_sold_out,
            (SELECT id FROM auctions a
             WHERE a.project_id=p.id AND a.starts_at <= ? AND a.ends_at >= ?
             LIMIT 1) as active_auction_id,
            (SELECT COUNT(*) FROM project_views v WHERE v.project_id=p.id) as view_count,
            (SELECT ROUND(AVG(r.rating),1) FROM reviews r WHERE r.project_id=p.id) as avg_rating,
            (SELECT COUNT(*) FROM reviews r WHERE r.project_id=p.id) as review_count,
            (SELECT u.username FROM reservations r2 JOIN users u ON r2.user_id=u.id
             WHERE r2.project_id=p.id AND r2.status='approved' LIMIT 1) as reserved_by
        FROM projects p WHERE p.is_active=1
    """
    params = [now, now]
    if search:
        query += " AND (p.title LIKE ? OR p.description LIKE ? OR p.tech_stack LIKE ?)"
        params += [f'%{search}%']*3
    if category:
        query += " AND p.category=?"
        params.append(category)
    query += " ORDER BY p.created_at DESC"
    projects = db.execute(query, params).fetchall()
    categories = db.execute(
        "SELECT DISTINCT category FROM projects WHERE is_active=1 AND category IS NOT NULL").fetchall()
    auction_rows = db.execute("""
        SELECT a.*, p.title as project_title, p.category,
            (SELECT filename FROM screenshots WHERE project_id=p.id LIMIT 1) as thumb,
            (SELECT COUNT(*) FROM auction_bids WHERE auction_id=a.id) as bid_count,
            (SELECT MAX(amount) FROM auction_bids WHERE auction_id=a.id) as current_bid,
            (SELECT u.username FROM auction_bids b JOIN users u ON b.user_id=u.id
             WHERE b.auction_id=a.id ORDER BY b.amount DESC LIMIT 1) as top_bidder
        FROM auctions a JOIN projects p ON a.project_id=p.id
        ORDER BY a.starts_at ASC LIMIT 4
    """).fetchall()
    auctions = []
    for a in auction_rows:
        d = dict(a)
        d['live_status'] = auction_status(a)
        auctions.append(d)
    return render_template('index.html', projects=projects, categories=categories,
                           search=search, selected_cat=category, auctions=auctions)


@app.route('/project/<int:pid>')
def project_detail(pid):
    db = get_db()
    project = db.execute(
        "SELECT * FROM projects WHERE id=? AND is_active=1", (pid,)).fetchone()
    if not project:
        return redirect(url_for('index'))
    # Track view
    db.execute("INSERT INTO project_views (project_id) VALUES (?)", (pid,))
    db.commit()
    screenshots = db.execute(
        "SELECT * FROM screenshots WHERE project_id=?", (pid,)).fetchall()
    buyers = db.execute("""
        SELECT u.username, o.approved_at FROM orders o
        JOIN users u ON o.user_id=u.id
        WHERE o.project_id=? AND o.status='approved'
    """, (pid,)).fetchall()
    user_bought = False
    user_order = None
    user_review = None
    if session.get('user_id'):
        user_order = db.execute(
            "SELECT * FROM orders WHERE user_id=? AND project_id=? AND status='approved'",
            (session['user_id'], pid)).fetchone()
        user_bought = user_order is not None
        user_review = db.execute(
            "SELECT * FROM reviews WHERE project_id=? AND user_id=?",
            (pid, session['user_id'])).fetchone()
    sold_out = len(buyers) >= 1
    pricing = calc_price(project)
    active_auction = get_active_auction(db, pid)
    ended_auction = get_ended_auction_winner(
        db, pid) if not active_auction else None
    reviews = db.execute("""
        SELECT r.*, u.username, u.avatar FROM reviews r
        JOIN users u ON r.user_id=u.id
        WHERE r.project_id=? ORDER BY r.created_at DESC
    """, (pid,)).fetchall()
    avg_rating = db.execute(
        "SELECT AVG(rating) as avg, COUNT(*) as cnt FROM reviews WHERE project_id=?", (pid,)
    ).fetchone()
    view_count = db.execute(
        "SELECT COUNT(*) as c FROM project_views WHERE project_id=?", (pid,)
    ).fetchone()['c']
    # Reservation info
    reservation = db.execute("""
        SELECT r.*, u.username FROM reservations r
        JOIN users u ON r.user_id=u.id
        WHERE r.project_id=?
    """, (pid,)).fetchone()
    user_reservation = None
    if session.get('user_id') and reservation:
        if int(reservation['user_id']) == int(session['user_id']):
            user_reservation = reservation
    return render_template('project_detail.html', project=project,
                           screenshots=screenshots, buyers=buyers,
                           user_bought=user_bought, user_order=user_order,
                           sold_out=sold_out, pricing=pricing,
                           vat_amount=pricing['vat_amount'], total_price=pricing['total_price'],
                           active_auction=active_auction, ended_auction=ended_auction,
                           reviews=reviews, avg_rating=avg_rating, view_count=view_count,
                           user_review=user_review, reservation=reservation,
                           user_reservation=user_reservation)


@app.route('/project/<int:pid>/review', methods=['POST'])
@login_required
def submit_review(pid):
    db = get_db()
    # Only approved buyers can review
    order = db.execute(
        "SELECT id FROM orders WHERE user_id=? AND project_id=? AND status='approved'",
        (session['user_id'], pid)).fetchone()
    if not order:
        flash('You can only review projects you have purchased.', 'error')
        return redirect(url_for('project_detail', pid=pid))
    rating = int(request.form.get('rating', 5))
    comment = request.form.get('comment', '').strip()
    rating = max(1, min(5, rating))
    try:
        db.execute(
            "INSERT INTO reviews (project_id, user_id, rating, comment) VALUES (?,?,?,?)",
            (pid, session['user_id'], rating, comment))
        db.commit()
        flash('Review submitted! Thank you 🌟', 'success')
    except:
        # Already reviewed — update instead
        db.execute(
            "UPDATE reviews SET rating=?, comment=? WHERE project_id=? AND user_id=?",
            (rating, comment, pid, session['user_id']))
        db.commit()
        flash('Review updated!', 'success')
    return redirect(url_for('project_detail', pid=pid) + '#reviews')


@app.route('/project/<int:pid>/review/delete', methods=['POST'])
@login_required
def delete_review(pid):
    db = get_db()
    db.execute("DELETE FROM reviews WHERE project_id=? AND user_id=?",
               (pid, session['user_id']))
    db.commit()
    flash('Review deleted.', 'success')
    return redirect(url_for('project_detail', pid=pid) + '#reviews')

# ── Auth ──────────────────────────────────────────────────────────────────────


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        db = get_db()
        try:
            db.execute("INSERT INTO users (username,email,password) VALUES (?,?,?)",
                       (username, email, generate_password_hash(password)))
            db.commit()
            flash('Account created! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists.', 'error')
        except sqlite3.OperationalError:
            flash('Server is busy, please try again in a moment.', 'error')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = request.args.get('next', url_for('index'))
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email=?",
                          (email,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])
            session['avatar'] = user['avatar'] or ''
            return redirect(next_url)
        flash('Invalid credentials.', 'error')
    return render_template('login.html', next=next_url)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ── Profile ───────────────────────────────────────────────────────────────────


@app.route('/profile')
@login_required
def profile():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?",
                      (session['user_id'],)).fetchone()
    orders = db.execute("""
        SELECT o.*, p.title, p.category FROM orders o
        JOIN projects p ON o.project_id=p.id
        WHERE o.user_id=? ORDER BY o.created_at DESC
    """, (session['user_id'],)).fetchall()
    total_spent = sum(o['amount'] for o in orders if o['status'] == 'approved')
    return render_template('profile.html', user=user, orders=orders, total_spent=total_spent)


@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def profile_edit():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?",
                      (session['user_id'],)).fetchone()
    if request.method == 'POST':
        username = request.form['username'].strip()
        bio = request.form.get('bio', '').strip()
        avatar = user['avatar']
        if 'avatar' in request.files:
            f = request.files['avatar']
            if f and f.filename and allowed_file(f.filename, ALLOWED_IMG):
                fn = secure_filename(f'{uuid.uuid4()}_{f.filename}')
                f.save(os.path.join(UPLOAD_AVATARS, fn))
                avatar = fn
        new_pass = request.form.get('new_password', '').strip()
        if new_pass:
            if not check_password_hash(user['password'], request.form.get('current_password', '')):
                flash('Current password is incorrect.', 'error')
                return render_template('profile_edit.html', user=user)
            db.execute("UPDATE users SET username=?,bio=?,avatar=?,password=? WHERE id=?",
                       (username, bio, avatar, generate_password_hash(new_pass), session['user_id']))
        else:
            db.execute("UPDATE users SET username=?,bio=?,avatar=? WHERE id=?",
                       (username, bio, avatar, session['user_id']))
        db.commit()
        session['username'] = username
        session['avatar'] = avatar or ''
        flash('Profile updated!', 'success')
        return redirect(url_for('profile'))
    return render_template('profile_edit.html', user=user)


@app.route('/profile/avatar/<filename>')
def serve_avatar(filename):
    return send_from_directory(UPLOAD_AVATARS, filename)

# ── Orders ────────────────────────────────────────────────────────────────────


@app.route('/buy/<int:pid>', methods=['GET', 'POST'])
@login_required
def buy(pid):
    if session.get('is_admin'):
        flash('Admins cannot purchase projects.', 'error')
        return redirect(url_for('project_detail', pid=pid))
    db = get_db()
    project = db.execute(
        "SELECT * FROM projects WHERE id=? AND is_active=1", (pid,)).fetchone()
    if not project:
        return redirect(url_for('index'))

    # Block if project is on active auction
    active_auction = get_active_auction(db, pid)
    if active_auction:
        flash('This project is currently in an active auction — join the auction to get it!', 'error')
        return redirect(url_for('auction_detail', aid=active_auction['id']))

    # Block if project is reserved by someone else
    reservation = db.execute(
        "SELECT * FROM reservations WHERE project_id=? AND status='approved'", (pid,)).fetchone()
    if reservation and int(reservation['user_id']) != int(session['user_id']):
        reserver = db.execute(
            "SELECT username FROM users WHERE id=?", (reservation['user_id'],)).fetchone()
        flash(
            f'This project is reserved by {reserver["username"]} and is not available for purchase.', 'error')
        return redirect(url_for('project_detail', pid=pid))

    # Handle ended auction — only winner can buy, at winning price
    ended_auction = get_ended_auction_winner(db, pid)
    is_auction_winner = (
        ended_auction is not None and
        ended_auction['winner_id'] is not None and
        int(ended_auction['winner_id']) == int(session['user_id'])
    )
    if ended_auction and not is_auction_winner:
        flash(
            f'This project was won at auction by {ended_auction["winner_username"]}. Waiting for their payment.', 'error')
        return redirect(url_for('project_detail', pid=pid))

    owner = db.execute(
        "SELECT o.*, u.username FROM orders o JOIN users u ON o.user_id=u.id WHERE o.project_id=? AND o.status='approved'",
        (pid,)).fetchone()
    if owner:
        flash(f'Sorry, already purchased by {owner["username"]}.', 'error')
        return redirect(url_for('project_detail', pid=pid))
    existing = db.execute(
        "SELECT * FROM orders WHERE user_id=? AND project_id=? AND status IN ('pending','approved')",
        (session['user_id'], pid)).fetchone()
    if existing and existing['status'] == 'approved':
        return redirect(url_for('my_orders'))

    # Use winning bid amount if auction winner, otherwise normal price with promo
    promo_code = request.args.get('promo', '').strip(
    ) or request.form.get('promo_code', '').strip()
    promo_discount = 0
    promo_row = None
    promo_error = None

    if is_auction_winner:
        base_price = ended_auction['winning_amount']
        vat_amount = round(base_price * VAT_RATE, 2)
        total_price = round(base_price + vat_amount, 2)
        note = f"AuctionWin-{project['title'][:15]}"
        pricing = {'original': base_price, 'sale_price': base_price, 'base_price': base_price,
                   'vat_amount': vat_amount, 'total_price': total_price,
                   'has_discount': False, 'discount_pct': 0, 'promo_discount': 0}
    else:
        if promo_code:
            promo_discount, promo_row = apply_promo(
                db, promo_code, session['user_id'], project['price'])
            if promo_code and not promo_row:
                promo_error = 'Invalid, expired, or already used promo code.'
                promo_discount = 0
        pricing = calc_price(project, promo_discount)
        base_price = pricing['base_price']
        vat_amount = pricing['vat_amount']
        total_price = pricing['total_price']
        note = f"PyMarket-{project['title'][:20]}"

    qr_url = gcash_qr_url(total_price, note)

    if request.method == 'POST':
        # Re-apply promo on POST
        promo_code = request.form.get('promo_code', '').strip()
        if 'apply_promo' in request.form:
            return redirect(url_for('buy', pid=pid, promo=promo_code))

        gcash_ref = request.form.get('gcash_ref', '').strip()
        payment_ss = None
        if 'payment_screenshot' in request.files:
            f = request.files['payment_screenshot']
            if f and allowed_file(f.filename, ALLOWED_IMG):
                fn = secure_filename(f'{uuid.uuid4()}_{f.filename}')
                f.save(os.path.join(UPLOAD_PAYMENTS, fn))
                payment_ss = fn
        order_ref = str(uuid.uuid4())[:8].upper()
        db.execute(
            "INSERT INTO orders (order_ref,user_id,project_id,amount,gcash_ref,payment_screenshot) VALUES (?,?,?,?,?,?)",
            (order_ref, session['user_id'], pid, total_price, gcash_ref, payment_ss))
        db.commit()
        # Record promo use
        if promo_row:
            last_order = db.execute(
                "SELECT id FROM orders WHERE order_ref=?", (order_ref,)).fetchone()
            db.execute("INSERT INTO promo_uses (promo_id,user_id,order_id) VALUES (?,?,?)",
                       (promo_row['id'], session['user_id'], last_order['id'] if last_order else None))
            db.execute(
                "UPDATE promo_codes SET used_count=used_count+1 WHERE id=?", (promo_row['id'],))
            db.commit()
        flash(
            f'Payment submitted! Order ref: {order_ref}. Admin will verify shortly.', 'success')
        return redirect(url_for('my_orders'))
    return render_template('buy.html', project=project, existing=existing,
                           pricing=pricing, base_price=base_price,
                           vat_amount=vat_amount, total_price=total_price,
                           qr_url=qr_url, gcash_number=GCASH_NUMBER, gcash_name=GCASH_NAME,
                           is_auction_winner=is_auction_winner, ended_auction=ended_auction,
                           promo_code=promo_code, promo_row=promo_row, promo_error=promo_error)


@app.route('/my-orders')
@login_required
def my_orders():
    db = get_db()
    orders = db.execute('''
        SELECT o.*, p.title, p.price, p.category FROM orders o
        JOIN projects p ON o.project_id=p.id
        WHERE o.user_id=? ORDER BY o.created_at DESC
    ''', (session['user_id'],)).fetchall()
    return render_template('my_orders.html', orders=orders)


@app.route('/download/<int:order_id>')
@login_required
def download_project(order_id):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id=? AND user_id=? AND status='approved'",
                       (order_id, session['user_id'])).fetchone()
    if not order:
        flash('Access denied.', 'error')
        return redirect(url_for('my_orders'))
    project = db.execute("SELECT * FROM projects WHERE id=?",
                         (order['project_id'],)).fetchone()
    return send_from_directory(UPLOAD_PROJECTS, project['file_path'], as_attachment=True)


@app.route('/view-source/<int:order_id>')
@login_required
def view_source(order_id):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id=? AND user_id=? AND status='approved'",
                       (order_id, session['user_id'])).fetchone()
    if not order:
        flash('Access denied.', 'error')
        return redirect(url_for('my_orders'))
    project = db.execute("SELECT * FROM projects WHERE id=?",
                         (order['project_id'],)).fetchone()
    source_content = None
    if project['file_path'] and project['file_path'].endswith('.py'):
        with open(os.path.join(UPLOAD_PROJECTS, project['file_path']), 'r', errors='replace') as f:
            source_content = f.read()
    return render_template('view_source.html', project=project, source=source_content, order_id=order_id)

# ── Auctions ──────────────────────────────────────────────────────────────────


@app.route('/auctions')
def auctions():
    db = get_db()
    rows = db.execute("""
        SELECT a.*, p.title as project_title, p.category, p.description as project_desc,
            (SELECT filename FROM screenshots WHERE project_id=p.id LIMIT 1) as thumb,
            (SELECT COUNT(*) FROM auction_bids WHERE auction_id=a.id) as bid_count,
            (SELECT MAX(amount) FROM auction_bids WHERE auction_id=a.id) as current_bid,
            (SELECT u.username FROM auction_bids b JOIN users u ON b.user_id=u.id
             WHERE b.auction_id=a.id ORDER BY b.amount DESC LIMIT 1) as top_bidder
        FROM auctions a JOIN projects p ON a.project_id=p.id
        ORDER BY a.starts_at ASC
    """).fetchall()
    auctions_list = []
    for a in rows:
        d = dict(a)
        d['live_status'] = auction_status(a)
        auctions_list.append(d)
    return render_template('auctions.html', auctions=auctions_list)


@app.route('/auction/<int:aid>')
def auction_detail(aid):
    db = get_db()
    a = db.execute("""
        SELECT a.*, p.title as project_title, p.category, p.description as project_desc,
            p.tech_stack,
            (SELECT filename FROM screenshots WHERE project_id=p.id LIMIT 1) as thumb,
            (SELECT COUNT(*) FROM auction_bids WHERE auction_id=a.id) as bid_count,
            (SELECT MAX(amount) FROM auction_bids WHERE auction_id=a.id) as current_bid,
            (SELECT u.username FROM auction_bids b JOIN users u ON b.user_id=u.id
             WHERE b.auction_id=a.id ORDER BY b.amount DESC LIMIT 1) as top_bidder
        FROM auctions a JOIN projects p ON a.project_id=p.id WHERE a.id=?
    """, (aid,)).fetchone()
    if not a:
        return redirect(url_for('auctions'))
    bids = db.execute("""
        SELECT b.*, u.username FROM auction_bids b
        JOIN users u ON b.user_id=u.id
        WHERE b.auction_id=? ORDER BY b.amount DESC
    """, (aid,)).fetchall()
    live_status = auction_status(a)
    user_bid = None
    if session.get('user_id'):
        user_bid = db.execute(
            "SELECT MAX(amount) as amt FROM auction_bids WHERE auction_id=? AND user_id=?",
            (aid, session['user_id'])).fetchone()
    min_bid = round((a['current_bid'] or a['start_price']) +
                    a['min_increment'], 2)
    # For ended auctions — check if current user is the winner
    is_winner = False
    winner_paid = False
    if live_status == 'ended' and session.get('user_id') and a['bid_count'] and a['bid_count'] > 0:
        top_bid = db.execute(
            "SELECT user_id FROM auction_bids WHERE auction_id=? ORDER BY amount DESC LIMIT 1", (aid,)).fetchone()
        if top_bid and int(top_bid['user_id']) == int(session['user_id']):
            is_winner = True
            # Check if winner already submitted payment
            paid = db.execute(
                "SELECT id FROM orders WHERE project_id=? AND user_id=? AND status IN ('pending','approved')",
                (a['project_id'], session['user_id'])).fetchone()
            winner_paid = paid is not None
    return render_template('auction_detail.html', a=dict(a), bids=bids,
                           live_status=live_status, min_bid=min_bid, user_bid=user_bid,
                           is_winner=is_winner, winner_paid=winner_paid)


@app.route('/auction/<int:aid>/bid', methods=['POST'])
@login_required
def place_bid(aid):
    if session.get('is_admin'):
        return jsonify({'ok': False, 'msg': 'Admins cannot bid.'})
    db = get_db()
    a = db.execute("SELECT * FROM auctions WHERE id=?", (aid,)).fetchone()
    if not a:
        return jsonify({'ok': False, 'msg': 'Auction not found.'})
    now = datetime.now().isoformat()
    if now < a['starts_at']:
        return jsonify({'ok': False, 'msg': 'Auction has not started yet.'})
    if now > a['ends_at']:
        return jsonify({'ok': False, 'msg': 'Auction has already ended.'})
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        return jsonify({'ok': False, 'msg': 'Invalid bid amount.'})
    current = db.execute(
        "SELECT MAX(amount) as m FROM auction_bids WHERE auction_id=?", (aid,)).fetchone()['m']
    floor = (current or a['start_price']) + a['min_increment']
    if amount < floor:
        return jsonify({'ok': False, 'msg': f'Minimum bid is ₱{floor:.2f}'})
    db.execute("INSERT INTO auction_bids (auction_id, user_id, amount) VALUES (?,?,?)",
               (aid, session['user_id'], amount))
    db.commit()
    top = db.execute("""
        SELECT b.amount, u.username FROM auction_bids b JOIN users u ON b.user_id=u.id
        WHERE b.auction_id=? ORDER BY b.amount DESC LIMIT 1
    """, (aid,)).fetchone()
    count = db.execute(
        "SELECT COUNT(*) as c FROM auction_bids WHERE auction_id=?", (aid,)).fetchone()['c']
    bids = db.execute("""
        SELECT b.amount, u.username, b.created_at FROM auction_bids b
        JOIN users u ON b.user_id=u.id WHERE b.auction_id=? ORDER BY b.amount DESC LIMIT 10
    """, (aid,)).fetchall()
    return jsonify({
        'ok': True,
        'current_bid': top['amount'],
        'top_bidder': top['username'],
        'bid_count': count,
        'bids': [{'amount': b['amount'], 'username': b['username'], 'time': b['created_at'][11:16]} for b in bids]
    })


@app.route('/auction/<int:aid>/status')
def auction_status_api(aid):
    db = get_db()
    a = db.execute("SELECT * FROM auctions WHERE id=?", (aid,)).fetchone()
    if not a:
        return jsonify({'ok': False})
    top = db.execute("""
        SELECT b.amount, u.username FROM auction_bids b JOIN users u ON b.user_id=u.id
        WHERE b.auction_id=? ORDER BY b.amount DESC LIMIT 1
    """, (aid,)).fetchone()
    count = db.execute(
        "SELECT COUNT(*) as c FROM auction_bids WHERE auction_id=?", (aid,)).fetchone()['c']
    bids = db.execute("""
        SELECT b.amount, u.username, b.created_at FROM auction_bids b
        JOIN users u ON b.user_id=u.id WHERE b.auction_id=? ORDER BY b.amount DESC LIMIT 10
    """, (aid,)).fetchall()
    return jsonify({
        'ok': True,
        'current_bid': top['amount'] if top else None,
        'top_bidder': top['username'] if top else None,
        'bid_count': count,
        'live_status': auction_status(a),
        'ends_at': a['ends_at'],
        'now': datetime.now().isoformat(),
        'bids': [{'amount': b['amount'], 'username': b['username'], 'time': b['created_at'][11:16]} for b in bids]
    })

# ── FAQ ──────────────────────────────────────────────────────────────────────


@app.route('/faq')
def faq():
    db = get_db()
    faqs = db.execute(
        "SELECT * FROM faq ORDER BY sort_order ASC, id ASC").fetchall()
    return render_template('faq.html', faqs=faqs)

# ── Chat ──────────────────────────────────────────────────────────────────────


@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat_general():
    db = get_db()
    if request.method == 'POST':
        msg = request.form.get('message', '').strip()
        if msg:
            db.execute("INSERT INTO chats (user_id, order_id, is_admin_reply, message) VALUES (?,NULL,0,?)",
                       (session['user_id'], msg))
            db.commit()
            maybe_bot_reply(db, session['user_id'], msg, order_id=None)
        return redirect(url_for('chat_general'))
    messages = db.execute("""
        SELECT c.*, u.username FROM chats c JOIN users u ON c.user_id=u.id
        WHERE c.order_id IS NULL AND c.user_id=? ORDER BY c.created_at ASC
    """, (session['user_id'],)).fetchall()
    return render_template('chat.html', messages=messages, order=None, title='General Support')


@app.route('/chat/widget', methods=['GET', 'POST'])
@login_required
def chat_widget():
    db = get_db()

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        msg = (data.get('message') or '').strip()
        if not msg:
            return jsonify({'ok': False, 'error': 'empty_message'}), 400

        db.execute(
            "INSERT INTO chats (user_id, order_id, is_admin_reply, message) VALUES (?,NULL,0,?)",
            (session['user_id'], msg)
        )
        db.commit()
        maybe_bot_reply(db, session['user_id'], msg, order_id=None)

    messages = db.execute("""
        SELECT c.*, u.username FROM chats c
        JOIN users u ON c.user_id=u.id
        WHERE c.order_id IS NULL AND c.user_id=?
        ORDER BY c.created_at ASC
    """, (session['user_id'],)).fetchall()

    return jsonify({
        'ok': True,
        'messages': [
            {
                'message': m['message'],
                'is_admin_reply': bool(m['is_admin_reply']),
                'is_bot': bool(m['is_admin_reply']) and str(m['message']).startswith('🤖'),
                'created_at': m['created_at'],
            }
            for m in messages
        ]
    })


@app.route('/chat/order/<int:order_id>', methods=['GET', 'POST'])
@login_required
def chat_order(order_id):
    db = get_db()
    order = db.execute("""
        SELECT o.*, p.title as project_title FROM orders o
        JOIN projects p ON o.project_id=p.id WHERE o.id=? AND o.user_id=?
    """, (order_id, session['user_id'])).fetchone()
    if not order:
        return redirect(url_for('my_orders'))
    if request.method == 'POST':
        msg = request.form.get('message', '').strip()
        if msg:
            db.execute("INSERT INTO chats (user_id, order_id, is_admin_reply, message) VALUES (?,?,0,?)",
                       (session['user_id'], order_id, msg))
            db.commit()
            maybe_bot_reply(db, session['user_id'], msg, order_id=order_id)
        return redirect(url_for('chat_order', order_id=order_id))
    messages = db.execute("""
        SELECT c.*, u.username FROM chats c JOIN users u ON c.user_id=u.id
        WHERE c.order_id=? ORDER BY c.created_at ASC
    """, (order_id,)).fetchall()
    return render_template('chat.html', messages=messages, order=order,
                           title=f'Order #{order["order_ref"]} — {order["project_title"]}')

# ── Admin ─────────────────────────────────────────────────────────────────────


@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    db = get_db()
    stats = {
        'projects':      db.execute("SELECT COUNT(*) as c FROM projects").fetchone()['c'],
        'users':         db.execute("SELECT COUNT(*) as c FROM users WHERE is_admin=0").fetchone()['c'],
        'pending':       db.execute("SELECT COUNT(*) as c FROM orders WHERE status='pending'").fetchone()['c'],
        'revenue':       db.execute("SELECT COALESCE(SUM(amount),0) as s FROM orders WHERE status='approved'").fetchone()['s'],
        'unread_chats':  db.execute("SELECT COUNT(DISTINCT user_id) as c FROM chats WHERE is_admin_reply=0").fetchone()['c'],
        'auctions':      db.execute("SELECT COUNT(*) as c FROM auctions").fetchone()['c'],
        'reservations':  db.execute("SELECT COUNT(*) as c FROM reservations WHERE status='pending'").fetchone()['c'],
    }
    pending_orders = db.execute('''
        SELECT o.*, u.username, u.email, p.title, p.category FROM orders o
        JOIN users u ON o.user_id=u.id JOIN projects p ON o.project_id=p.id
        WHERE o.status='pending' ORDER BY o.created_at DESC
    ''').fetchall()
    return render_template('admin/dashboard.html', stats=stats, pending_orders=pending_orders)


@app.route('/admin/projects')
@login_required
@admin_required
def admin_projects():
    db = get_db()
    projects = db.execute('''
        SELECT p.*, COUNT(DISTINCT o.id) as sales, GROUP_CONCAT(DISTINCT u.username) as buyer_names
        FROM projects p
        LEFT JOIN orders o ON p.id=o.project_id AND o.status='approved'
        LEFT JOIN users u ON o.user_id=u.id
        GROUP BY p.id ORDER BY p.created_at DESC
    ''').fetchall()
    return render_template('admin/projects.html', projects=projects)


@app.route('/admin/project/add', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_project():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        price = float(request.form['price'])
        tech_stack = request.form.get('tech_stack', '')
        category = request.form.get('category', '')
        file_path = None
        if 'project_file' in request.files:
            f = request.files['project_file']
            if f and allowed_file(f.filename, ALLOWED_PROJECT):
                fn = secure_filename(f'{uuid.uuid4()}_{f.filename}')
                f.save(os.path.join(UPLOAD_PROJECTS, fn))
                file_path = fn
        db = get_db()
        cur = db.execute("INSERT INTO projects (title,description,price,tech_stack,category,file_path) VALUES (?,?,?,?,?,?)",
                         (title, description, price, tech_stack, category, file_path))
        pid = cur.lastrowid
        for ss in request.files.getlist('screenshots'):
            if ss and allowed_file(ss.filename, ALLOWED_IMG):
                fn = secure_filename(f'{uuid.uuid4()}_{ss.filename}')
                ss.save(os.path.join(UPLOAD_SCREENSHOTS, fn))
                db.execute(
                    "INSERT INTO screenshots (project_id,filename) VALUES (?,?)", (pid, fn))
        db.commit()
        flash('Project added!', 'success')
        return redirect(url_for('admin_projects'))
    return render_template('admin/add_project.html')


@app.route('/admin/project/edit/<int:pid>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_project(pid):
    db = get_db()
    project = db.execute(
        "SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    screenshots = db.execute(
        "SELECT * FROM screenshots WHERE project_id=?", (pid,)).fetchall()
    if request.method == 'POST':
        disc = float(request.form.get('discount_percent') or 0)
        db.execute("UPDATE projects SET title=?,description=?,price=?,tech_stack=?,category=?,is_active=?,discount_percent=? WHERE id=?",
                   (request.form['title'], request.form['description'], float(request.form['price']),
                    request.form.get('tech_stack', ''), request.form.get(
                        'category', ''),
                    1 if request.form.get('is_active') else 0, disc, pid))
        if 'project_file' in request.files:
            f = request.files['project_file']
            if f and f.filename and allowed_file(f.filename, ALLOWED_PROJECT):
                fn = secure_filename(f'{uuid.uuid4()}_{f.filename}')
                f.save(os.path.join(UPLOAD_PROJECTS, fn))
                db.execute(
                    "UPDATE projects SET file_path=? WHERE id=?", (fn, pid))
        for ss in request.files.getlist('screenshots'):
            if ss and ss.filename and allowed_file(ss.filename, ALLOWED_IMG):
                fn = secure_filename(f'{uuid.uuid4()}_{ss.filename}')
                ss.save(os.path.join(UPLOAD_SCREENSHOTS, fn))
                db.execute(
                    "INSERT INTO screenshots (project_id,filename) VALUES (?,?)", (pid, fn))
        db.commit()
        flash('Project updated!', 'success')
        return redirect(url_for('admin_projects'))
    return render_template('admin/edit_project.html', project=project, screenshots=screenshots)


@app.route('/admin/screenshot/delete/<int:sid>')
@login_required
@admin_required
def delete_screenshot(sid):
    db = get_db()
    ss = db.execute("SELECT * FROM screenshots WHERE id=?", (sid,)).fetchone()
    if ss:
        try:
            os.remove(os.path.join(UPLOAD_SCREENSHOTS, ss['filename']))
        except:
            pass
        db.execute("DELETE FROM screenshots WHERE id=?", (sid,))
        db.commit()
    return jsonify({'ok': True})


@app.route('/admin/orders')
@login_required
@admin_required
def admin_orders():
    db = get_db()
    orders = db.execute('''
        SELECT o.*, u.username, u.email, p.title, p.category FROM orders o
        JOIN users u ON o.user_id=u.id JOIN projects p ON o.project_id=p.id
        ORDER BY o.created_at DESC
    ''').fetchall()
    return render_template('admin/orders.html', orders=orders)


@app.route('/admin/order/<int:oid>/approve')
@login_required
@admin_required
def approve_order(oid):
    db = get_db()
    db.execute("UPDATE orders SET status='approved', approved_at=? WHERE id=?",
               (datetime.now().isoformat(), oid))
    db.commit()
    order = db.execute("""SELECT o.*,u.username,u.email,p.title FROM orders o
        JOIN users u ON o.user_id=u.id JOIN projects p ON o.project_id=p.id WHERE o.id=?""", (oid,)).fetchone()
    if order:
        link = url_for('my_orders', _external=True)
        notify_user(db, order['user_id'],
                    f'✅ Your order for "{order["title"]}" has been approved! You can now download your project.',
                    link)
        send_email(order['email'], f'✅ Order Approved — {order["title"]} | PyMarket',
                   f"""<div style="font-family:sans-serif;max-width:500px;margin:auto">
            <h2 style="color:#f848c6">✅ Order Approved!</h2>
            <p>Hi {order['username']}! Your payment for <strong>{order['title']}</strong> has been verified.</p>
            <p>You can now download your project from <a href="{link}">My Orders</a>.</p>
            <p style="color:#888;font-size:12px">Order Ref: {order['order_ref']}</p>
            <p style="color:#888;font-size:12px">PyMarket — Python Project Marketplace 🇵🇭</p></div>""")
    flash('Order approved!', 'success')
    return redirect(url_for('admin_orders'))


@app.route('/admin/order/<int:oid>/reject')
@login_required
@admin_required
def reject_order(oid):
    db = get_db()
    db.execute("UPDATE orders SET status='rejected' WHERE id=?", (oid,))
    db.commit()
    order = db.execute("""SELECT o.*,u.username,u.email,p.title FROM orders o
        JOIN users u ON o.user_id=u.id JOIN projects p ON o.project_id=p.id WHERE o.id=?""", (oid,)).fetchone()
    if order:
        link = url_for('my_orders', _external=True)
        notify_user(db, order['user_id'],
                    f'❌ Your order for "{order["title"]}" was rejected. Please check your payment and resubmit.',
                    link)
        send_email(order['email'], f'❌ Order Rejected — {order["title"]} | PyMarket',
                   f"""<div style="font-family:sans-serif;max-width:500px;margin:auto">
            <h2 style="color:#ff6584">❌ Order Rejected</h2>
            <p>Hi {order['username']}! Unfortunately your payment for <strong>{order['title']}</strong> could not be verified.</p>
            <p>Please double-check your GCash reference number and screenshot, then resubmit via <a href="{link}">My Orders</a>.</p>
            <p>If you believe this is an error, contact us via Support Chat.</p>
            <p style="color:#888;font-size:12px">PyMarket — Python Project Marketplace 🇵🇭</p></div>""")
    flash('Order rejected.', 'success')
    return redirect(url_for('admin_orders'))


@app.route('/admin/payment-proof/<filename>')
@login_required
@admin_required
def view_payment_proof(filename):
    return send_from_directory(UPLOAD_PAYMENTS, filename)


@app.route('/admin/auctions', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_auctions():
    db = get_db()
    if request.method == 'POST':
        pid = int(request.form['project_id'])
        title = request.form['title']
        desc = request.form['description']
        start_price = float(request.form['start_price'])
        min_inc = float(request.form.get('min_increment', 10))
        starts_at = request.form['starts_at']
        ends_at = request.form['ends_at']
        db.execute("""INSERT INTO auctions
            (project_id,title,description,start_price,min_increment,starts_at,ends_at,status)
            VALUES (?,?,?,?,?,?,?,'upcoming')""",
                   (pid, title, desc, start_price, min_inc, starts_at, ends_at))
        db.commit()
        flash('Auction created!', 'success')
        return redirect(url_for('admin_auctions'))
    auction_rows = db.execute("""
        SELECT a.*, p.title as project_title,
            (SELECT COUNT(*) FROM auction_bids WHERE auction_id=a.id) as bid_count,
            (SELECT MAX(amount) FROM auction_bids WHERE auction_id=a.id) as current_bid,
            (SELECT u.username FROM auction_bids b JOIN users u ON b.user_id=u.id
             WHERE b.auction_id=a.id ORDER BY b.amount DESC LIMIT 1) as top_bidder
        FROM auctions a JOIN projects p ON a.project_id=p.id ORDER BY a.starts_at DESC
    """).fetchall()
    auctions_list = []
    for a in auction_rows:
        d = dict(a)
        d['live_status'] = auction_status(a)
        auctions_list.append(d)
    projects = db.execute(
        "SELECT id,title FROM projects WHERE is_active=1").fetchall()
    return render_template('admin/auctions.html', auctions=auctions_list, projects=projects)


@app.route('/admin/auction/<int:aid>/delete')
@login_required
@admin_required
def delete_auction(aid):
    db = get_db()
    db.execute("DELETE FROM auction_bids WHERE auction_id=?", (aid,))
    db.execute("DELETE FROM auctions WHERE id=?", (aid,))
    db.commit()
    flash('Auction deleted.', 'success')
    return redirect(url_for('admin_auctions'))


@app.route('/admin/chats')
@login_required
@admin_required
def admin_chats():
    db = get_db()
    conversations = db.execute("""
        SELECT u.id, u.username, u.email, MAX(c.created_at) as last_message,
            (SELECT message FROM chats WHERE user_id=u.id ORDER BY created_at DESC LIMIT 1) as last_text,
            SUM(CASE WHEN c.is_admin_reply=0 THEN 1 ELSE 0 END) as unread
        FROM chats c JOIN users u ON c.user_id=u.id
        WHERE u.is_admin=0 GROUP BY u.id ORDER BY last_message DESC
    """).fetchall()
    return render_template('admin/chats.html', conversations=conversations)


@app.route('/admin/chat/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_chat_user(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        return redirect(url_for('admin_chats'))
    if request.method == 'POST':
        msg = request.form.get('message', '').strip()
        order_id = request.form.get('order_id') or None
        if msg:
            db.execute("INSERT INTO chats (user_id,order_id,is_admin_reply,message) VALUES (?,?,1,?)",
                       (user_id, order_id, msg))
            db.commit()
        return redirect(url_for('admin_chat_user', user_id=user_id))
    messages = db.execute("""
        SELECT c.*, u.username, o.order_ref, p.title as project_title
        FROM chats c JOIN users u ON c.user_id=u.id
        LEFT JOIN orders o ON c.order_id=o.id
        LEFT JOIN projects p ON o.project_id=p.id
        WHERE c.user_id=? ORDER BY c.created_at ASC
    """, (user_id,)).fetchall()
    orders = db.execute("""
        SELECT o.id,o.order_ref,p.title FROM orders o
        JOIN projects p ON o.project_id=p.id WHERE o.user_id=?
    """, (user_id,)).fetchall()
    return render_template('admin/chat_user.html', user=user, messages=messages, orders=orders)


@app.route('/admin/faq', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_faq():
    db = get_db()
    if request.method == 'POST':
        question = request.form['question'].strip()
        answer = request.form['answer'].strip()
        sort_order = int(request.form.get('sort_order', 0))
        if question and answer:
            db.execute("INSERT INTO faq (question, answer, sort_order) VALUES (?,?,?)",
                       (question, answer, sort_order))
            db.commit()
            flash('FAQ added!', 'success')
        return redirect(url_for('admin_faq'))
    faqs = db.execute(
        "SELECT * FROM faq ORDER BY sort_order ASC, id ASC").fetchall()
    return render_template('admin/faq.html', faqs=faqs)


@app.route('/admin/faq/<int:fid>/edit', methods=['POST'])
@login_required
@admin_required
def admin_faq_edit(fid):
    db = get_db()
    db.execute("UPDATE faq SET question=?, answer=?, sort_order=? WHERE id=?",
               (request.form['question'].strip(), request.form['answer'].strip(),
                int(request.form.get('sort_order', 0)), fid))
    db.commit()
    flash('FAQ updated!', 'success')
    return redirect(url_for('admin_faq'))


@app.route('/admin/faq/<int:fid>/delete')
@login_required
@admin_required
def admin_faq_delete(fid):
    db = get_db()
    db.execute("DELETE FROM faq WHERE id=?", (fid,))
    db.commit()
    flash('FAQ deleted.', 'success')
    return redirect(url_for('admin_faq'))


@app.route('/admin/reviews')
@login_required
@admin_required
def admin_reviews():
    db = get_db()
    reviews = db.execute("""
        SELECT r.*, u.username, p.title as project_title
        FROM reviews r
        JOIN users u ON r.user_id=u.id
        JOIN projects p ON r.project_id=p.id
        ORDER BY r.created_at DESC
    """).fetchall()
    return render_template('admin/reviews.html', reviews=reviews)


@app.route('/admin/review/<int:rid>/delete')
@login_required
@admin_required
def admin_review_delete(rid):
    db = get_db()
    db.execute("DELETE FROM reviews WHERE id=?", (rid,))
    db.commit()
    flash('Review deleted.', 'success')
    return redirect(url_for('admin_reviews'))

# ── Reservations ─────────────────────────────────────────────────────────────


@app.route('/project/<int:pid>/reserve', methods=['POST'])
@login_required
def reserve_project(pid):
    if session.get('is_admin'):
        flash('Admins cannot reserve projects.', 'error')
        return redirect(url_for('project_detail', pid=pid))
    db = get_db()
    project = db.execute(
        "SELECT * FROM projects WHERE id=? AND is_active=1", (pid,)).fetchone()
    if not project:
        return redirect(url_for('index'))
    # Check if already sold
    sold = db.execute(
        "SELECT id FROM orders WHERE project_id=? AND status='approved'", (pid,)).fetchone()
    if sold:
        flash('This project is already sold.', 'error')
        return redirect(url_for('project_detail', pid=pid))
    # Check if already reserved by someone else
    existing = db.execute(
        "SELECT * FROM reservations WHERE project_id=?", (pid,)).fetchone()
    if existing:
        if int(existing['user_id']) == int(session['user_id']):
            flash('You already have a reservation request for this project.', 'error')
        else:
            flash('This project already has a reservation.', 'error')
        return redirect(url_for('project_detail', pid=pid))
    note = request.form.get('note', '').strip()
    db.execute("INSERT INTO reservations (project_id, user_id, note, status) VALUES (?,?,?,'pending')",
               (pid, session['user_id'], note))
    db.commit()
    # Notify admin via in-app notification
    admin = db.execute(
        "SELECT id FROM users WHERE is_admin=1 LIMIT 1").fetchone()
    if admin:
        notify_user(db, admin['id'],
                    f'🔖 {session["username"]} wants to reserve "{project["title"]}"',
                    url_for('admin_reservations'))
    flash('Reservation request sent! Admin will review shortly. 🔖', 'success')
    return redirect(url_for('project_detail', pid=pid))


@app.route('/project/<int:pid>/reserve/cancel', methods=['POST'])
@login_required
def cancel_reservation(pid):
    db = get_db()
    res = db.execute("SELECT * FROM reservations WHERE project_id=? AND user_id=?",
                     (pid, session['user_id'])).fetchone()
    if res:
        db.execute("DELETE FROM reservations WHERE id=?", (res['id'],))
        db.commit()
        flash('Reservation cancelled.', 'success')
    return redirect(url_for('project_detail', pid=pid))


@app.route('/admin/reservations')
@login_required
@admin_required
def admin_reservations():
    db = get_db()
    reservations = db.execute("""
        SELECT r.*, u.username, u.email, p.title, p.category,
            (SELECT filename FROM screenshots WHERE project_id=p.id LIMIT 1) as thumb
        FROM reservations r
        JOIN users u ON r.user_id=u.id
        JOIN projects p ON r.project_id=p.id
        ORDER BY r.created_at DESC
    """).fetchall()
    return render_template('admin/reservations.html', reservations=reservations)


@app.route('/admin/reservation/<int:rid>/approve')
@login_required
@admin_required
def approve_reservation(rid):
    db = get_db()
    res = db.execute(
        "SELECT r.*,p.title,u.username FROM reservations r JOIN projects p ON r.project_id=p.id JOIN users u ON r.user_id=u.id WHERE r.id=?", (rid,)).fetchone()
    if res:
        db.execute("UPDATE reservations SET status='approved' WHERE id=?", (rid,))
        db.commit()
        notify_user(db, res['user_id'],
                    f'✅ Your reservation for "{res["title"]}" has been approved! Project is held for you.',
                    url_for('project_detail', pid=res['project_id']))
        flash(f'Reservation approved for {res["username"]}!', 'success')
    return redirect(url_for('admin_reservations'))


@app.route('/admin/reservation/<int:rid>/release')
@login_required
@admin_required
def release_reservation(rid):
    db = get_db()
    res = db.execute(
        "SELECT r.*,p.title,u.username FROM reservations r JOIN projects p ON r.project_id=p.id JOIN users u ON r.user_id=u.id WHERE r.id=?", (rid,)).fetchone()
    if res:
        db.execute("DELETE FROM reservations WHERE id=?", (rid,))
        db.commit()
        notify_user(db, res['user_id'],
                    f'❌ Your reservation for "{res["title"]}" has been released by admin.',
                    url_for('project_detail', pid=res['project_id']))
        flash('Reservation released.', 'success')
    return redirect(url_for('admin_reservations'))

# ── Notifications ────────────────────────────────────────────────────────────


@app.route('/notifications')
@login_required
def notifications():
    db = get_db()
    notifs = db.execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (session['user_id'],)).fetchall()
    db.execute("UPDATE notifications SET is_read=1 WHERE user_id=?",
               (session['user_id'],))
    db.commit()
    return render_template('notifications.html', notifs=notifs)


@app.route('/notifications/count')
@login_required
def notif_count():
    db = get_db()
    count = db.execute(
        "SELECT COUNT(*) as c FROM notifications WHERE user_id=? AND is_read=0",
        (session['user_id'],)).fetchone()['c']
    return jsonify({'count': count})

# ── About ─────────────────────────────────────────────────────────────────────


@app.route('/about')
def about():
    if session.get('user_id'):
        return redirect(url_for('index'))
    db = get_db()
    stats = {
        'projects': db.execute("SELECT COUNT(*) as c FROM projects WHERE is_active=1").fetchone()['c'],
        'buyers':   db.execute("SELECT COUNT(DISTINCT user_id) as c FROM orders WHERE status='approved'").fetchone()['c'],
        'reviews':  db.execute("SELECT COUNT(*) as c FROM reviews").fetchone()['c'],
        'auctions': db.execute("SELECT COUNT(*) as c FROM auctions").fetchone()['c'],
    }
    testimonials = db.execute("""
        SELECT r.comment, r.rating, u.username, u.avatar, p.title as project_title
        FROM reviews r JOIN users u ON r.user_id=u.id JOIN projects p ON r.project_id=p.id
        WHERE r.comment != '' ORDER BY r.created_at DESC LIMIT 6
    """).fetchall()
    return render_template('about.html', stats=stats, testimonials=testimonials)

# ── Promo codes (admin) ───────────────────────────────────────────────────────


@app.route('/admin/promos', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_promos():
    db = get_db()
    if request.method == 'POST':
        code = request.form['code'].strip().upper()
        discount_type = request.form.get('discount_type', 'percent')
        discount_value = float(request.form['discount_value'])
        max_uses = int(request.form.get('max_uses', 0))
        expires_at = request.form.get('expires_at') or None
        try:
            db.execute("""INSERT INTO promo_codes (code,discount_type,discount_value,max_uses,expires_at)
                VALUES (?,?,?,?,?)""", (code, discount_type, discount_value, max_uses, expires_at))
            db.commit()
            flash(f'Promo code {code} created!', 'success')
        except:
            flash('Code already exists.', 'error')
        return redirect(url_for('admin_promos'))
    promos = db.execute(
        "SELECT * FROM promo_codes ORDER BY created_at DESC").fetchall()
    return render_template('admin/promos.html', promos=promos)


@app.route('/admin/promo/<int:pid>/toggle')
@login_required
@admin_required
def toggle_promo(pid):
    db = get_db()
    db.execute(
        "UPDATE promo_codes SET is_active=CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id=?", (pid,))
    db.commit()
    return redirect(url_for('admin_promos'))


@app.route('/admin/promo/<int:pid>/delete')
@login_required
@admin_required
def delete_promo(pid):
    db = get_db()
    db.execute("DELETE FROM promo_uses WHERE promo_id=?", (pid,))
    db.execute("DELETE FROM promo_codes WHERE id=?", (pid,))
    db.commit()
    flash('Promo code deleted.', 'success')
    return redirect(url_for('admin_promos'))

# ── Project discount (admin) ──────────────────────────────────────────────────


@app.route('/admin/project/<int:pid>/discount', methods=['POST'])
@login_required
@admin_required
def set_discount(pid):
    db = get_db()
    pct = float(request.form.get('discount_percent', 0))
    pct = max(0, min(pct, 90))  # cap at 90%
    db.execute("UPDATE projects SET discount_percent=? WHERE id=?", (pct, pid))
    db.commit()
    flash(f'Discount set to {pct}%!', 'success')
    return redirect(url_for('admin_edit_project', pid=pid))

# ── Promo code check (AJAX) ───────────────────────────────────────────────────


@app.route('/promo/check', methods=['POST'])
@login_required
def check_promo():
    db = get_db()
    code = request.form.get('code', '').strip()
    pid = request.form.get('project_id', 0, type=int)
    project = db.execute(
        "SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not project:
        return jsonify({'ok': False, 'msg': 'Project not found.'})
    discount, promo = apply_promo(
        db, code, session['user_id'], project['price'])
    if not promo:
        return jsonify({'ok': False, 'msg': 'Invalid, expired, or already used promo code.'})
    pricing = calc_price(project, discount)
    return jsonify({
        'ok': True,
        'msg': f'✅ Code applied! You save ₱{discount:.2f}',
        'discount': discount,
        'new_total': pricing['total_price'],
    })


# ── Admin AI Chatbot ──────────────────────────────────────────────────────────

@app.route('/admin/ai', methods=['POST'])
@login_required
@admin_required
def admin_ai():
    """Smart rule-based admin AI that answers questions using live DB data."""
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip().lower()
    if not question:
        return jsonify({'reply': '❓ Please ask me something! I can help with sales, orders, revenue, auctions, and more.'})

    db = get_db()

    # ── Gather core stats ──
    def get_stats():
        return {
            'total_revenue': db.execute("SELECT COALESCE(SUM(amount),0) as r FROM orders WHERE status='approved'").fetchone()['r'],
            'approved_orders': db.execute("SELECT COUNT(*) as c FROM orders WHERE status='approved'").fetchone()['c'],
            'pending_orders': db.execute("SELECT COUNT(*) as c FROM orders WHERE status='pending'").fetchone()['c'],
            'rejected_orders': db.execute("SELECT COUNT(*) as c FROM orders WHERE status='rejected'").fetchone()['c'],
            'total_users': db.execute("SELECT COUNT(*) as c FROM users WHERE is_admin=0").fetchone()['c'],
            'total_projects': db.execute("SELECT COUNT(*) as c FROM projects WHERE is_active=1").fetchone()['c'],
            'sold_projects': db.execute("SELECT COUNT(DISTINCT project_id) as c FROM orders WHERE status='approved'").fetchone()['c'],
            'total_auctions': db.execute("SELECT COUNT(*) as c FROM auctions").fetchone()['c'],
            'active_promos': db.execute("SELECT COUNT(*) as c FROM promo_codes WHERE is_active=1").fetchone()['c'],
        }

    # ── Revenue / Sales summary ──
    if any(k in question for k in ['revenue', 'sales', 'income', 'earned', 'money', 'total sale', 'kumita', 'kita']):
        s = get_stats()
        top = db.execute("""
            SELECT p.title, SUM(o.amount) as rev, COUNT(*) as cnt
            FROM orders o JOIN projects p ON o.project_id=p.id
            WHERE o.status='approved' GROUP BY p.id ORDER BY rev DESC LIMIT 3
        """).fetchall()
        lines = [f"💰 **Sales & Revenue Report**",
                 f"",
                 f"• Total Revenue: **₱{s['total_revenue']:,.2f}**",
                 f"• Approved Sales: **{s['approved_orders']}** orders",
                 f"• Pending: **{s['pending_orders']}** | Rejected: **{s['rejected_orders']}**"]
        if top:
            lines.append(f"\n🏆 **Top Earning Projects:**")
            for i, r in enumerate(top, 1):
                lines.append(f"  {i}. {r['title']} — ₱{r['rev']:,.2f} ({r['cnt']} sale{'s' if r['cnt']!=1 else ''})")
        return jsonify({'reply': '\n'.join(lines)})

    # ── Discounts / Sale prices ──
    if any(k in question for k in ['discount', 'sale price', 'original price', 'promo', 'sale', 'markdown', 'bawas']):
        projects = db.execute("""
            SELECT title, price, original_price, discount_percent
            FROM projects WHERE is_active=1 ORDER BY discount_percent DESC
        """).fetchall()
        discounted = [p for p in projects if p['discount_percent'] and p['discount_percent'] > 0]
        if not discounted:
            return jsonify({'reply': '🏷️ No projects currently have a discount. You can set discounts from the Admin → Projects → Edit page.'})
        lines = [f"🏷️ **Discounted Projects ({len(discounted)} found):**", ""]
        for p in discounted:
            orig = p['original_price'] or p['price']
            sale = round(p['price'] * (1 - p['discount_percent'] / 100), 2)
            savings = round(orig - sale, 2)
            lines.append(f"• **{p['title']}**")
            lines.append(f"  Original: ₱{orig:,.2f} → Sale: ₱{sale:,.2f} ({p['discount_percent']:.0f}% off, save ₱{savings:,.2f})")
        return jsonify({'reply': '\n'.join(lines)})

    # ── Orders ──
    if any(k in question for k in ['order', 'pending', 'approve', 'reject', 'purchase', 'buyer', 'bought']):
        s = get_stats()
        recent = db.execute("""
            SELECT u.username, p.title, o.amount, o.status, o.created_at
            FROM orders o JOIN users u ON o.user_id=u.id JOIN projects p ON o.project_id=p.id
            ORDER BY o.created_at DESC LIMIT 5
        """).fetchall()
        lines = [f"📦 **Orders Summary**", "",
                 f"• ✅ Approved: **{s['approved_orders']}**",
                 f"• ⏳ Pending: **{s['pending_orders']}**",
                 f"• ❌ Rejected: **{s['rejected_orders']}**",
                 f"", "🕐 **Recent Orders:**"]
        for o in recent:
            status_emoji = '✅' if o['status']=='approved' else ('⏳' if o['status']=='pending' else '❌')
            lines.append(f"  {status_emoji} {o['username']} → {o['title']} (₱{o['amount']:,.2f})")
        return jsonify({'reply': '\n'.join(lines)})

    # ── Auctions ──
    if any(k in question for k in ['auction', 'bid', 'bidder', 'winner', 'live', 'bidding']):
        now = datetime.now().isoformat()
        auctions = db.execute("""
            SELECT a.title, a.starts_at, a.ends_at, a.start_price,
                (SELECT MAX(amount) FROM auction_bids WHERE auction_id=a.id) as top_bid,
                (SELECT COUNT(*) FROM auction_bids WHERE auction_id=a.id) as bid_count,
                (SELECT u.username FROM auction_bids b JOIN users u ON b.user_id=u.id
                 WHERE b.auction_id=a.id ORDER BY b.amount DESC LIMIT 1) as top_bidder
            FROM auctions a ORDER BY a.starts_at DESC LIMIT 5
        """).fetchall()
        if not auctions:
            return jsonify({'reply': '🏷️ No auctions found yet. You can create one from Admin → Auctions.'})
        lines = [f"🏷️ **Auction Summary** ({len(auctions)} recent):", ""]
        for a in auctions:
            if a['ends_at'] and now > a['ends_at']:
                status = '🏁 Ended'
            elif a['starts_at'] and now >= a['starts_at']:
                status = '🟢 Live'
            else:
                status = '⏳ Upcoming'
            top = f"₱{a['top_bid']:,.2f} by {a['top_bidder']}" if a['top_bid'] else "No bids yet"
            lines.append(f"• **{a['title']}** [{status}]")
            lines.append(f"  Start: ₱{a['start_price']:,.2f} | Top Bid: {top} | {a['bid_count']} bid(s)")
        return jsonify({'reply': '\n'.join(lines)})

    # ── Projects ──
    if any(k in question for k in ['project', 'item', 'listing', 'product', 'available', 'stock']):
        projects = db.execute("""
            SELECT p.title, p.price, p.category, p.discount_percent,
                (SELECT COUNT(*) FROM orders o WHERE o.project_id=p.id AND o.status='approved') as sold,
                (SELECT COUNT(*) FROM project_views v WHERE v.project_id=p.id) as views
            FROM projects p WHERE p.is_active=1 ORDER BY views DESC LIMIT 8
        """).fetchall()
        s = get_stats()
        lines = [f"📂 **Projects Overview** ({s['total_projects']} total, {s['sold_projects']} sold)", ""]
        for p in projects:
            sold_tag = '🔴 Sold' if p['sold'] else '🟢 Available'
            disc = f" 🏷️{p['discount_percent']:.0f}% off" if p['discount_percent'] and p['discount_percent'] > 0 else ''
            cat = f"[{p['category']}]" if p['category'] else ''
            lines.append(f"• **{p['title']}** {cat} — ₱{p['price']:,.2f}{disc} | {sold_tag} | {p['views']} views")
        return jsonify({'reply': '\n'.join(lines)})

    # ── Customers / Users ──
    if any(k in question for k in ['customer', 'user', 'client', 'member', 'buyer', 'registered']):
        s = get_stats()
        top_buyers = db.execute("""
            SELECT u.username, COUNT(*) as purchases, SUM(o.amount) as spent
            FROM orders o JOIN users u ON o.user_id=u.id
            WHERE o.status='approved' GROUP BY u.id ORDER BY spent DESC LIMIT 5
        """).fetchall()
        lines = [f"👥 **Customer Stats**", "",
                 f"• Total Customers: **{s['total_users']}**",
                 f"", "💎 **Top Buyers:**"]
        if top_buyers:
            for i, b in enumerate(top_buyers, 1):
                lines.append(f"  {i}. {b['username']} — {b['purchases']} purchase(s), ₱{b['spent']:,.2f} spent")
        else:
            lines.append("  No purchases yet.")
        return jsonify({'reply': '\n'.join(lines)})

    # ── Promo codes ──
    if any(k in question for k in ['promo', 'code', 'coupon', 'voucher', 'discount code']):
        promos = db.execute("SELECT * FROM promo_codes ORDER BY created_at DESC").fetchall()
        if not promos:
            return jsonify({'reply': '🎁 No promo codes yet. Create one from Admin → Promos.'})
        lines = [f"🎁 **Promo Codes ({len(promos)} total):**", ""]
        for p in promos:
            status = '✅ Active' if p['is_active'] else '🔴 Inactive'
            val = f"{p['discount_value']:.0f}%" if p['discount_type']=='percent' else f"₱{p['discount_value']:.2f}"
            uses = f"{p['used_count']}/{p['max_uses']}" if p['max_uses'] else f"{p['used_count']} uses"
            lines.append(f"• **{p['code']}** — {val} off | {uses} | {status}")
        return jsonify({'reply': '\n'.join(lines)})

    # ── Total of all products incl VAT ──
    if 'total of all product' in question or ('total' in question and ('product' in question or 'item' in question) and 'vat' in question):
        all_projects = db.execute("SELECT * FROM projects WHERE is_active=1").fetchall()
        total_orig = sum(p['price'] for p in all_projects)
        total_with_vat_and_discounts = sum(calc_price(p)['total_price'] for p in all_projects)
        lines = [
            f"💰 **Total Value of All Listed Products**", "",
            f"• Number of active projects: **{len(all_projects)}**",
            f"• Total Base Price: **₱{total_orig:,.2f}**",
            f"• **Grand Total (including active discounts & 5% VAT): ₱{total_with_vat_and_discounts:,.2f}**"
        ]
        return jsonify({'reply': '\n'.join(lines)})

    # ── Total of all reserve ──
    if 'total of all reserve' in question or 'total reserve' in question or 'total reserved' in question:
        reserves = db.execute("""
            SELECT p.title, p.price, u.username
            FROM project_reservations r 
            JOIN projects p ON r.project_id=p.id 
            JOIN users u ON r.user_id=u.id
            WHERE r.status='approved' AND NOT EXISTS (
                SELECT 1 FROM orders o WHERE o.project_id = p.id AND o.status='approved'
            )
        """).fetchall()
        if not reserves:
            return jsonify({'reply': '🔖 There are currently **0** active reservations.'})
        
        total_reserve = sum(r['price'] for r in reserves)
        total_reserve_vat = sum(calc_price(p)['total_price'] for p in reserves)
        lines = [
            f"🔖 **Total Active Reservations ({len(reserves)})**", "",
            f"• Total Value (Base): **₱{total_reserve:,.2f}**",
            f"• **Total Value (Including VAT): ₱{total_reserve_vat:,.2f}**", "",
            "**Reserved Items:**"
        ]
        for r in reserves:
            lines.append(f"  • {r['title']} (₱{r['price']:,.2f}) — by {r['username']}")
        
        return jsonify({'reply': '\n'.join(lines)})

    # ── Dashboard / General summary ──
    if any(k in question for k in ['summary', 'dashboard', 'overview', 'stats', 'report', 'lahat', 'all', 'hello', 'hi', 'help', 'ano', 'what']):
        s = get_stats()
        lines = [
            "🤖 **PyMarket AI Assistant — Dashboard Summary**", "",
            f"💰 Revenue: **₱{s['total_revenue']:,.2f}**",
            f"📦 Orders: ✅ {s['approved_orders']} approved | ⏳ {s['pending_orders']} pending",
            f"📂 Projects: **{s['total_projects']}** listed, **{s['sold_projects']}** sold",
            f"👥 Customers: **{s['total_users']}**",
            f"🏷️ Auctions: **{s['total_auctions']}**",
            f"🎁 Active Promos: **{s['active_promos']}**",
            "",
            "💡 **Ask me about:**",
            "  • Sales & revenue  • Discounts & sale prices",
            "  • Orders & buyers  • Auctions & bids",
            "  • Customers        • Promo codes",
            "  • Any project      • Full reports"
        ]
        return jsonify({'reply': '\n'.join(lines)})

    # ── Specific project lookup ──
    # Try to match a project title in the question
    all_projects = db.execute("SELECT * FROM projects WHERE is_active=1").fetchall()
    matched = None
    for p in all_projects:
        if p['title'].lower() in question or any(w in question for w in p['title'].lower().split() if len(w) > 3):
            matched = p
            break
    if matched:
        pricing = calc_price(matched)
        sold = db.execute("SELECT COUNT(*) as c FROM orders WHERE project_id=? AND status='approved'", (matched['id'],)).fetchone()['c']
        views = db.execute("SELECT COUNT(*) as c FROM project_views WHERE project_id=?", (matched['id'],)).fetchone()['c']
        lines = [f"📂 **{matched['title']}**", "",
                 f"• Category: {matched['category'] or 'N/A'}",
                 f"• Original Price: ₱{pricing['original']:,.2f}",
                 f"• Sale Price: ₱{pricing['sale_price']:,.2f}" + (f" ({pricing['discount_pct']:.0f}% off! 🏷️)" if pricing['has_discount'] else ""),
                 f"• With VAT (5%): ₱{pricing['total_price']:,.2f}",
                 f"• Status: {'🔴 Sold' if sold else '🟢 Available'}",
                 f"• Views: {views}",
                 f"• Tech Stack: {matched['tech_stack'] or 'N/A'}"]
        return jsonify({'reply': '\n'.join(lines)})

    # ── Fallback ──
    return jsonify({'reply': (
        "🤖 I'm not sure about that one! Try asking me:\n\n"
        "• \"What's my total revenue?\"\n"
        "• \"Show discounts / sale prices\"\n"
        "• \"How many pending orders?\"\n"
        "• \"Auction summary\"\n"
        "• \"Customer stats\"\n"
        "• \"Promo codes\"\n"
        "• \"Project overview\"\n"
        "• \"Dashboard summary\""
    )})


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=False)
#made by @kleian