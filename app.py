from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3, os, uuid, urllib.parse
from datetime import datetime
from functools import wraps
from bot import maybe_bot_reply

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'market.db')

UPLOAD_SCREENSHOTS = os.path.join(BASE_DIR, 'static', 'uploads', 'screenshots')
UPLOAD_PROJECTS    = os.path.join(BASE_DIR, 'static', 'uploads', 'projects')
UPLOAD_PAYMENTS    = os.path.join(BASE_DIR, 'static', 'uploads', 'payments')
UPLOAD_AVATARS     = os.path.join(BASE_DIR, 'static', 'uploads', 'avatars')

for folder in [UPLOAD_SCREENSHOTS, UPLOAD_PROJECTS, UPLOAD_PAYMENTS, UPLOAD_AVATARS]:
    os.makedirs(folder, exist_ok=True)

ALLOWED_IMG     = {'png','jpg','jpeg','gif','webp'}
ALLOWED_PROJECT = {'zip','rar','tar','gz','py'}
VAT_RATE        = 0.005
GCASH_NUMBER    = '09XX-XXX-XXXX'
GCASH_NAME      = 'Your Name Here'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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
        try: db.execute("ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''")
        except: pass
        try: db.execute("ALTER TABLE users ADD COLUMN avatar TEXT DEFAULT ''")
        except: pass
        try: db.execute("ALTER TABLE auctions ADD COLUMN start_price REAL NOT NULL DEFAULT 0")
        except: pass
        try: db.execute("ALTER TABLE auctions ADD COLUMN min_increment REAL NOT NULL DEFAULT 10")
        except: pass
        try: db.execute("ALTER TABLE auctions ADD COLUMN starts_at TEXT")
        except: pass
        try: db.execute("ALTER TABLE auctions ADD COLUMN ends_at TEXT")
        except: pass
        try: db.execute("ALTER TABLE auctions ADD COLUMN status TEXT DEFAULT 'upcoming'")
        except: pass
        try: db.execute("ALTER TABLE auctions ADD COLUMN winner_id INTEGER")
        except: pass
        try: db.execute("ALTER TABLE auctions ADD COLUMN winning_bid REAL")
        except: pass
        try:
            db.execute("INSERT INTO users (username,email,password,is_admin) VALUES (?,?,?,1)",
                ('admin','admin@pymarket.com', generate_password_hash('admin123')))
            db.commit()
        except: pass

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
    return '.' in filename and filename.rsplit('.',1)[1].lower() in allowed

def gcash_qr_url(amount, note=''):
    data = f"Send PHP {amount} to {GCASH_NUMBER} ({GCASH_NAME}) via GCash. Ref: {note}"
    encoded = urllib.parse.quote(data)
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded}"

def auction_status(a):
    now = datetime.now().isoformat()
    starts = a['starts_at'] or ''
    ends   = a['ends_at'] or ''
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
    search   = request.args.get('q','')
    category = request.args.get('cat','')
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
             LIMIT 1) as active_auction_id
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
    projects   = db.execute(query, params).fetchall()
    categories = db.execute("SELECT DISTINCT category FROM projects WHERE is_active=1 AND category IS NOT NULL").fetchall()
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
    project = db.execute("SELECT * FROM projects WHERE id=? AND is_active=1", (pid,)).fetchone()
    if not project:
        return redirect(url_for('index'))
    screenshots = db.execute("SELECT * FROM screenshots WHERE project_id=?", (pid,)).fetchall()
    buyers = db.execute("""
        SELECT u.username, o.approved_at FROM orders o
        JOIN users u ON o.user_id=u.id
        WHERE o.project_id=? AND o.status='approved'
    """, (pid,)).fetchall()
    user_bought = False
    user_order  = None
    if session.get('user_id'):
        user_order = db.execute(
            "SELECT * FROM orders WHERE user_id=? AND project_id=? AND status='approved'",
            (session['user_id'], pid)).fetchone()
        user_bought = user_order is not None
    sold_out    = len(buyers) >= 1
    base_price  = project['price']
    vat_amount  = round(base_price * VAT_RATE, 2)
    total_price = round(base_price + vat_amount, 2)
    active_auction = get_active_auction(db, pid)
    ended_auction  = get_ended_auction_winner(db, pid) if not active_auction else None
    return render_template('project_detail.html', project=project,
                           screenshots=screenshots, buyers=buyers,
                           user_bought=user_bought, user_order=user_order,
                           sold_out=sold_out, vat_amount=vat_amount, total_price=total_price,
                           active_auction=active_auction, ended_auction=ended_auction)

# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email    = request.form['email'].strip()
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
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    next_url = request.args.get('next', url_for('index'))
    if request.method == 'POST':
        email    = request.form['email'].strip()
        password = request.form['password']
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id']  = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])
            session['avatar']   = user['avatar'] or ''
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
    user = db.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    orders = db.execute("""
        SELECT o.*, p.title, p.category FROM orders o
        JOIN projects p ON o.project_id=p.id
        WHERE o.user_id=? ORDER BY o.created_at DESC
    """, (session['user_id'],)).fetchall()
    total_spent = sum(o['amount'] for o in orders if o['status']=='approved')
    return render_template('profile.html', user=user, orders=orders, total_spent=total_spent)

@app.route('/profile/edit', methods=['GET','POST'])
@login_required
def profile_edit():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if request.method == 'POST':
        username = request.form['username'].strip()
        bio      = request.form.get('bio','').strip()
        avatar   = user['avatar']
        if 'avatar' in request.files:
            f = request.files['avatar']
            if f and f.filename and allowed_file(f.filename, ALLOWED_IMG):
                fn = secure_filename(f'{uuid.uuid4()}_{f.filename}')
                f.save(os.path.join(UPLOAD_AVATARS, fn))
                avatar = fn
        new_pass = request.form.get('new_password','').strip()
        if new_pass:
            if not check_password_hash(user['password'], request.form.get('current_password','')):
                flash('Current password is incorrect.', 'error')
                return render_template('profile_edit.html', user=user)
            db.execute("UPDATE users SET username=?,bio=?,avatar=?,password=? WHERE id=?",
                (username, bio, avatar, generate_password_hash(new_pass), session['user_id']))
        else:
            db.execute("UPDATE users SET username=?,bio=?,avatar=? WHERE id=?",
                (username, bio, avatar, session['user_id']))
        db.commit()
        session['username'] = username
        session['avatar']   = avatar or ''
        flash('Profile updated!', 'success')
        return redirect(url_for('profile'))
    return render_template('profile_edit.html', user=user)

@app.route('/profile/avatar/<filename>')
def serve_avatar(filename):
    return send_from_directory(UPLOAD_AVATARS, filename)

# ── Orders ────────────────────────────────────────────────────────────────────

@app.route('/buy/<int:pid>', methods=['GET','POST'])
@login_required
def buy(pid):
    if session.get('is_admin'):
        flash('Admins cannot purchase projects.', 'error')
        return redirect(url_for('project_detail', pid=pid))
    db = get_db()
    project = db.execute("SELECT * FROM projects WHERE id=? AND is_active=1", (pid,)).fetchone()
    if not project:
        return redirect(url_for('index'))

    # Block if project is on active auction
    active_auction = get_active_auction(db, pid)
    if active_auction:
        flash('This project is currently in an active auction — join the auction to get it!', 'error')
        return redirect(url_for('auction_detail', aid=active_auction['id']))

    # Handle ended auction — only winner can buy, at winning price
    ended_auction = get_ended_auction_winner(db, pid)
    is_auction_winner = (
        ended_auction is not None and
        ended_auction['winner_id'] is not None and
        int(ended_auction['winner_id']) == int(session['user_id'])
    )
    if ended_auction and not is_auction_winner:
        flash(f'This project was won at auction by {ended_auction["winner_username"]}. Waiting for their payment.', 'error')
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

    # Use winning bid amount if auction winner, otherwise normal price
    if is_auction_winner:
        base_price  = ended_auction['winning_amount']
        vat_amount  = round(base_price * VAT_RATE, 2)
        total_price = round(base_price + vat_amount, 2)
        note        = f"AuctionWin-{project['title'][:15]}"
    else:
        base_price  = project['price']
        vat_amount  = round(base_price * VAT_RATE, 2)
        total_price = round(base_price + vat_amount, 2)
        note        = f"PyMarket-{project['title'][:20]}"

    qr_url = gcash_qr_url(total_price, note)
    if request.method == 'POST':
        gcash_ref  = request.form.get('gcash_ref','').strip()
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
        flash(f'Payment submitted! Order ref: {order_ref}. Admin will verify shortly.', 'success')
        return redirect(url_for('my_orders'))
    return render_template('buy.html', project=project, existing=existing,
                           base_price=base_price, vat_amount=vat_amount, total_price=total_price,
                           qr_url=qr_url, gcash_number=GCASH_NUMBER, gcash_name=GCASH_NAME,
                           is_auction_winner=is_auction_winner, ended_auction=ended_auction)

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
    project = db.execute("SELECT * FROM projects WHERE id=?", (order['project_id'],)).fetchone()
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
    project = db.execute("SELECT * FROM projects WHERE id=?", (order['project_id'],)).fetchone()
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
    min_bid = round((a['current_bid'] or a['start_price']) + a['min_increment'], 2)
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
    current = db.execute("SELECT MAX(amount) as m FROM auction_bids WHERE auction_id=?", (aid,)).fetchone()['m']
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
    count = db.execute("SELECT COUNT(*) as c FROM auction_bids WHERE auction_id=?", (aid,)).fetchone()['c']
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
    count = db.execute("SELECT COUNT(*) as c FROM auction_bids WHERE auction_id=?", (aid,)).fetchone()['c']
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

# ── Chat ──────────────────────────────────────────────────────────────────────

@app.route('/chat', methods=['GET','POST'])
@login_required
def chat_general():
    db = get_db()
    if request.method == 'POST':
        msg = request.form.get('message','').strip()
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

@app.route('/chat/order/<int:order_id>', methods=['GET','POST'])
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
        msg = request.form.get('message','').strip()
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
        'projects':     db.execute("SELECT COUNT(*) as c FROM projects").fetchone()['c'],
        'users':        db.execute("SELECT COUNT(*) as c FROM users WHERE is_admin=0").fetchone()['c'],
        'pending':      db.execute("SELECT COUNT(*) as c FROM orders WHERE status='pending'").fetchone()['c'],
        'revenue':      db.execute("SELECT COALESCE(SUM(amount),0) as s FROM orders WHERE status='approved'").fetchone()['s'],
        'unread_chats': db.execute("SELECT COUNT(DISTINCT user_id) as c FROM chats WHERE is_admin_reply=0").fetchone()['c'],
        'auctions':     db.execute("SELECT COUNT(*) as c FROM auctions").fetchone()['c'],
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

@app.route('/admin/project/add', methods=['GET','POST'])
@login_required
@admin_required
def admin_add_project():
    if request.method == 'POST':
        title=request.form['title']; description=request.form['description']
        price=float(request.form['price']); tech_stack=request.form.get('tech_stack','')
        category=request.form.get('category',''); file_path=None
        if 'project_file' in request.files:
            f=request.files['project_file']
            if f and allowed_file(f.filename, ALLOWED_PROJECT):
                fn=secure_filename(f'{uuid.uuid4()}_{f.filename}')
                f.save(os.path.join(UPLOAD_PROJECTS,fn)); file_path=fn
        db=get_db()
        cur=db.execute("INSERT INTO projects (title,description,price,tech_stack,category,file_path) VALUES (?,?,?,?,?,?)",
            (title,description,price,tech_stack,category,file_path))
        pid=cur.lastrowid
        for ss in request.files.getlist('screenshots'):
            if ss and allowed_file(ss.filename,ALLOWED_IMG):
                fn=secure_filename(f'{uuid.uuid4()}_{ss.filename}')
                ss.save(os.path.join(UPLOAD_SCREENSHOTS,fn))
                db.execute("INSERT INTO screenshots (project_id,filename) VALUES (?,?)",(pid,fn))
        db.commit(); flash('Project added!','success')
        return redirect(url_for('admin_projects'))
    return render_template('admin/add_project.html')

@app.route('/admin/project/edit/<int:pid>', methods=['GET','POST'])
@login_required
@admin_required
def admin_edit_project(pid):
    db=get_db()
    project=db.execute("SELECT * FROM projects WHERE id=?",(pid,)).fetchone()
    screenshots=db.execute("SELECT * FROM screenshots WHERE project_id=?",(pid,)).fetchall()
    if request.method == 'POST':
        db.execute("UPDATE projects SET title=?,description=?,price=?,tech_stack=?,category=?,is_active=? WHERE id=?",
            (request.form['title'],request.form['description'],float(request.form['price']),
             request.form.get('tech_stack',''),request.form.get('category',''),
             1 if request.form.get('is_active') else 0, pid))
        if 'project_file' in request.files:
            f=request.files['project_file']
            if f and f.filename and allowed_file(f.filename,ALLOWED_PROJECT):
                fn=secure_filename(f'{uuid.uuid4()}_{f.filename}')
                f.save(os.path.join(UPLOAD_PROJECTS,fn))
                db.execute("UPDATE projects SET file_path=? WHERE id=?",(fn,pid))
        for ss in request.files.getlist('screenshots'):
            if ss and ss.filename and allowed_file(ss.filename,ALLOWED_IMG):
                fn=secure_filename(f'{uuid.uuid4()}_{ss.filename}')
                ss.save(os.path.join(UPLOAD_SCREENSHOTS,fn))
                db.execute("INSERT INTO screenshots (project_id,filename) VALUES (?,?)",(pid,fn))
        db.commit(); flash('Project updated!','success')
        return redirect(url_for('admin_projects'))
    return render_template('admin/edit_project.html', project=project, screenshots=screenshots)

@app.route('/admin/screenshot/delete/<int:sid>')
@login_required
@admin_required
def delete_screenshot(sid):
    db=get_db()
    ss=db.execute("SELECT * FROM screenshots WHERE id=?",(sid,)).fetchone()
    if ss:
        try: os.remove(os.path.join(UPLOAD_SCREENSHOTS,ss['filename']))
        except: pass
        db.execute("DELETE FROM screenshots WHERE id=?",(sid,)); db.commit()
    return jsonify({'ok':True})

@app.route('/admin/orders')
@login_required
@admin_required
def admin_orders():
    db=get_db()
    orders=db.execute('''
        SELECT o.*, u.username, u.email, p.title, p.category FROM orders o
        JOIN users u ON o.user_id=u.id JOIN projects p ON o.project_id=p.id
        ORDER BY o.created_at DESC
    ''').fetchall()
    return render_template('admin/orders.html', orders=orders)

@app.route('/admin/order/<int:oid>/approve')
@login_required
@admin_required
def approve_order(oid):
    db=get_db()
    db.execute("UPDATE orders SET status='approved', approved_at=? WHERE id=?",(datetime.now().isoformat(),oid))
    db.commit(); flash('Order approved!','success')
    return redirect(url_for('admin_orders'))

@app.route('/admin/order/<int:oid>/reject')
@login_required
@admin_required
def reject_order(oid):
    db=get_db()
    db.execute("UPDATE orders SET status='rejected' WHERE id=?",(oid,))
    db.commit(); flash('Order rejected.','success')
    return redirect(url_for('admin_orders'))

@app.route('/admin/payment-proof/<filename>')
@login_required
@admin_required
def view_payment_proof(filename):
    return send_from_directory(UPLOAD_PAYMENTS, filename)

@app.route('/admin/auctions', methods=['GET','POST'])
@login_required
@admin_required
def admin_auctions():
    db=get_db()
    if request.method=='POST':
        pid         = int(request.form['project_id'])
        title       = request.form['title']
        desc        = request.form['description']
        start_price = float(request.form['start_price'])
        min_inc     = float(request.form.get('min_increment', 10))
        starts_at   = request.form['starts_at']
        ends_at     = request.form['ends_at']
        db.execute("""INSERT INTO auctions
            (project_id,title,description,start_price,min_increment,starts_at,ends_at,status)
            VALUES (?,?,?,?,?,?,?,'upcoming')""",
            (pid,title,desc,start_price,min_inc,starts_at,ends_at))
        db.commit(); flash('Auction created!','success')
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
    projects = db.execute("SELECT id,title FROM projects WHERE is_active=1").fetchall()
    return render_template('admin/auctions.html', auctions=auctions_list, projects=projects)

@app.route('/admin/auction/<int:aid>/delete')
@login_required
@admin_required
def delete_auction(aid):
    db=get_db()
    db.execute("DELETE FROM auction_bids WHERE auction_id=?",(aid,))
    db.execute("DELETE FROM auctions WHERE id=?",(aid,))
    db.commit(); flash('Auction deleted.','success')
    return redirect(url_for('admin_auctions'))

@app.route('/admin/chats')
@login_required
@admin_required
def admin_chats():
    db=get_db()
    conversations=db.execute("""
        SELECT u.id, u.username, u.email, MAX(c.created_at) as last_message,
            (SELECT message FROM chats WHERE user_id=u.id ORDER BY created_at DESC LIMIT 1) as last_text,
            SUM(CASE WHEN c.is_admin_reply=0 THEN 1 ELSE 0 END) as unread
        FROM chats c JOIN users u ON c.user_id=u.id
        WHERE u.is_admin=0 GROUP BY u.id ORDER BY last_message DESC
    """).fetchall()
    return render_template('admin/chats.html', conversations=conversations)

@app.route('/admin/chat/<int:user_id>', methods=['GET','POST'])
@login_required
@admin_required
def admin_chat_user(user_id):
    db=get_db()
    user=db.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
    if not user: return redirect(url_for('admin_chats'))
    if request.method=='POST':
        msg=request.form.get('message','').strip()
        order_id=request.form.get('order_id') or None
        if msg:
            db.execute("INSERT INTO chats (user_id,order_id,is_admin_reply,message) VALUES (?,?,1,?)",
                (user_id,order_id,msg))
            db.commit()
        return redirect(url_for('admin_chat_user', user_id=user_id))
    messages=db.execute("""
        SELECT c.*, u.username, o.order_ref, p.title as project_title
        FROM chats c JOIN users u ON c.user_id=u.id
        LEFT JOIN orders o ON c.order_id=o.id
        LEFT JOIN projects p ON o.project_id=p.id
        WHERE c.user_id=? ORDER BY c.created_at ASC
    """,(user_id,)).fetchall()
    orders=db.execute("""
        SELECT o.id,o.order_ref,p.title FROM orders o
        JOIN projects p ON o.project_id=p.id WHERE o.user_id=?
    """,(user_id,)).fetchall()
    return render_template('admin/chat_user.html', user=user, messages=messages, orders=orders)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)