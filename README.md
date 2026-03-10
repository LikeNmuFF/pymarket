# 🐍 PyMarket — Python Projects Marketplace

A Flask + SQLite marketplace where you sell Python projects via GCash.

---

## 📁 Project Structure

```
pymarket/
├── app.py                  # Main Flask app
├── wsgi.py                 # PythonAnywhere WSGI config
├── requirements.txt
├── market.db               # Auto-created on first run
├── templates/
│   ├── base.html
│   ├── index.html          # Browse page (public)
│   ├── project_detail.html
│   ├── register.html
│   ├── login.html
│   ├── buy.html            # GCash payment page
│   ├── my_orders.html
│   ├── view_source.html
│   └── admin/
│       ├── dashboard.html
│       ├── projects.html
│       ├── add_project.html
│       ├── edit_project.html
│       └── orders.html
└── static/uploads/
    ├── screenshots/        # Project preview images
    ├── projects/           # Actual project files (zip/py)
    └── payments/           # GCash payment screenshots
```

---

## 🚀 PythonAnywhere Deployment

### 1. Upload Files
Upload this entire folder to `/home/YOUR_USERNAME/pymarket/`

### 2. Install Dependencies
In PythonAnywhere Bash console:
```bash
pip install flask werkzeug --user
```

### 3. Set Up Web App
- Go to **Web** tab → **Add a new web app**
- Choose **Manual configuration** → **Python 3.10**
- Set **Source code**: `/home/YOUR_USERNAME/pymarket`
- Set **WSGI file**: Click on the WSGI file link and replace ALL contents with your `wsgi.py` content

### 4. Update wsgi.py
Change `YOUR_PYTHONANYWHERE_USERNAME` to your actual username.

### 5. Static Files
In the Web tab → **Static Files**:
- URL: `/static/` → Directory: `/home/YOUR_USERNAME/pymarket/static`

### 6. Change Secret Key
In `app.py`, change:
```python
app.secret_key = 'your-secret-key-change-this-in-production'
```
To a long random string.

### 7. Update GCash Number
In `templates/buy.html`, replace:
```
09XX-XXX-XXXX
Your Name Here
```
With your actual GCash number and name.

### 8. Reload
Click **Reload** on the Web tab. Visit your site!

---

## 🔑 Default Admin Login
- **Email**: admin@pymarket.com
- **Password**: admin123
- ⚠️ Change these after first login!

---

## 💡 Usage

### As Admin:
1. Go to `/admin` and log in
2. Add projects with files, screenshots, price
3. When buyers submit payment → go to Dashboard → Approve/Reject

### As Buyer:
1. Browse projects (no login needed)
2. Click a project → login popup appears
3. Register/login → Buy via GCash
4. Submit GCash ref + screenshot
5. Wait for admin approval
6. Download + view source from My Orders
