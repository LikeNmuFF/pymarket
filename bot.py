from datetime import datetime

BOT_NAME = "PyMarket Bot 🤖"
BOT_REPLY_DELAY_MINUTES = 5

def get_greeting():
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Good morning! ☀️"
    elif 12 <= hour < 18:
        return "Good afternoon! 🌤️"
    elif 18 <= hour < 22:
        return "Good evening! 🌙"
    else:
        return "Hello, night owl! 🌟"

def bot_should_reply(db, user_id, order_id=None):
    last_admin = db.execute(
        "SELECT created_at FROM chats WHERE user_id=? AND is_admin_reply=1 AND (order_id=? OR (order_id IS NULL AND ? IS NULL)) ORDER BY created_at DESC LIMIT 1",
        (user_id, order_id, order_id)).fetchone()
    last_user = db.execute(
        "SELECT created_at FROM chats WHERE user_id=? AND is_admin_reply=0 AND (order_id=? OR (order_id IS NULL AND ? IS NULL)) ORDER BY created_at DESC LIMIT 1",
        (user_id, order_id, order_id)).fetchone()
    if not last_user:
        return False
    if last_admin and last_admin['created_at'] >= last_user['created_at']:
        return False
    try:
        elapsed = (datetime.now() - datetime.fromisoformat(last_user['created_at'])).total_seconds() / 60
    except:
        return False
    return elapsed >= BOT_REPLY_DELAY_MINUTES

def bot_get_reply(db, user_id, message, order_id=None):
    msg = message.lower().strip()
    greeting = get_greeting()

    greet_words = ['hi', 'hello', 'hey', 'sup', 'yo', 'helo', 'hii', 'hiii',
                   'good morning', 'good afternoon', 'good evening', 'good night',
                   'kumusta', 'kamusta']
    if any(w in msg for w in greet_words):
        user = db.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
        name = user['username'] if user else 'there'
        lines = [
            greeting + " " + name + "! 😊",
            "I'm PyMarket Bot, your automated assistant! 🤖",
            "Our admin is currently away but will reply soon! 💬",
            "I can help with projects, pricing, payments, or auctions.",
            "What can I help you with? 🚀"
        ]
        return "\n".join(lines)

    if any(w in msg for w in ['price', 'cost', 'how much', 'magkano', 'presyo',
                               'project', 'available', 'list', 'sell', 'ano meron']):
        projects = db.execute(
            "SELECT title, price, category FROM projects WHERE is_active=1 ORDER BY price ASC"
        ).fetchall()
        if projects:
            items = ["Here are our available Python projects! 🐍✨", ""]
            for p in projects:
                cat = p['category'] or 'General'
                items.append("• " + p['title'] + " (" + cat + ") — ₱" + "{:.2f}".format(p['price']))
            items += ["", "All prices include 0.5% VAT. Full source code, lifetime access, one buyer only! 🔒"]
            return "\n".join(items)
        return "We're still adding projects! 🛠️ Check back soon or ask admin for the latest listings. 😊"

    if any(w in msg for w in ['gcash', 'pay', 'payment', 'bayad', 'how to pay',
                               'reference', 'receipt', 'screenshot', 'send money']):
        lines = [
            "Here's how to pay via GCash! 💳💙", "",
            "1️⃣ Go to the project page and click Buy via GCash",
            "2️⃣ Open GCash app and tap Send Money",
            "3️⃣ Enter our GCash number and exact amount shown",
            "4️⃣ Screenshot your receipt 📸",
            "5️⃣ Submit your GCash ref number + screenshot",
            "6️⃣ Admin verifies — usually within a few hours! ⏳", "",
            "Once approved, download your project instantly! 🎉"
        ]
        return "\n".join(lines)

    if any(w in msg for w in ['order', 'status', 'approved', 'pending', 'rejected',
                               'when', 'kailan', 'download', 'my order', 'nasaan']):
        if order_id:
            order = db.execute(
                "SELECT o.status, o.order_ref, p.title FROM orders o JOIN projects p ON o.project_id=p.id WHERE o.id=?",
                (order_id,)).fetchone()
            if order:
                status_map = {
                    'pending':  '⏳ Pending — admin is reviewing your payment. Please wait!',
                    'approved': '✅ Approved! Go to My Orders to download your project.',
                    'rejected': '❌ Rejected — please check payment details and resubmit.'
                }
                status_msg = status_map.get(order['status'], 'Status: ' + order['status'])
                return "Order for " + order['title'] + " (#" + order['order_ref'] + "):\n\n" + status_msg + " 📦"
        lines = [
            "Check your order status in My Orders anytime! 📦", "",
            "⏳ Pending = admin reviewing payment",
            "✅ Approved = ready to download!",
            "❌ Rejected = payment issue, please resubmit", "",
            "Admin usually approves within a few hours! 🙏"
        ]
        return "\n".join(lines)

    if any(w in msg for w in ['auction', 'bid', 'bidding', 'winner', 'win',
                               'highest', 'how to bid', 'paano mag bid']):
        lines = [
            "Here's how auctions work! 🏷️🔨", "",
            "1️⃣ Go to Auctions page to see live and upcoming auctions",
            "2️⃣ Wait for the auction to go LIVE 🟢",
            "3️⃣ Place your bid — must be above current bid + min increment",
            "4️⃣ Highest bidder when timer ends WINS 🏆",
            "5️⃣ Winner pays via GCash at their winning bid price",
            "6️⃣ Project delivered after payment! 🎉", "",
            "Tip: Use the quick-bid buttons for faster bidding! ⚡"
        ]
        return "\n".join(lines)

    if any(w in msg for w in ['download', 'get project', 'where', 'link', 'file', 'source']):
        lines = [
            "To download your project: 📥", "",
            "1️⃣ Go to My Orders",
            "2️⃣ Find your approved order ✅",
            "3️⃣ Click Download or View Source", "",
            "If still pending, wait for admin approval first! ⏳"
        ]
        return "\n".join(lines)

    if any(w in msg for w in ['admin', 'contact', 'talk', 'human', 'real person', 'owner']):
        lines = [
            "I'm PyMarket Bot 🤖 — your automated assistant!",
            "Our admin will personally read and reply to your message soon! 👨‍💻",
            "Is there anything I can help you with in the meantime? 😊"
        ]
        return "\n".join(lines)

    if any(w in msg for w in ['thank', 'thanks', 'ty', 'salamat', 'thx']):
        return "You're welcome! 😊🙏 Happy to help! Ask anything anytime! 💬✨"

    lines = [
        "Thanks for your message! 😊 Our admin will reply soon. 💬",
        "While you wait, I can help with:", "",
        "🐍 Available projects & pricing",
        "💳 How to pay via GCash",
        "📦 Order status",
        "🏷️ Auction questions", "",
        "Just ask! 🚀"
    ]
    return "\n".join(lines)

def maybe_bot_reply(db, user_id, message, order_id=None):
    if not bot_should_reply(db, user_id, order_id):
        return
    reply = bot_get_reply(db, user_id, message, order_id)
    db.execute(
        "INSERT INTO chats (user_id, order_id, is_admin_reply, message) VALUES (?,?,1,?)",
        (user_id, order_id, "🤖 " + BOT_NAME + ":\n" + reply))
    db.commit()
