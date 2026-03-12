"""
ATM Simulation System — Responsive + Animated Machine Panel + VAT on Bills
Animations:
  - Card Slot: card slides in when "Insert Card" is clicked
  - Cash Dispenser: bills fan out when withdrawal completes
  - Receipt Printer: paper feeds out when receipt is generated
VAT: 12% VAT added to all bill payments (shown in breakdown)
"""

import tkinter as tk
from tkinter import font as tkfont, messagebox
from datetime import datetime
import random
import platform
import math

# ── DPI fix ───────────────────────────────────────────────────────────────────
if platform.system() == "Windows":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try: windll.user32.SetProcessDPIAware()
        except Exception: pass

# ── Constants ─────────────────────────────────────────────────────────────────
VAT_RATE = 0.12

ACCOUNTS = {
    "1234567890": {
        "pin": "1111", "name": "Alice Johnson", "balance": 15_000.00,
        "transactions": [
            {"date": "2025-03-01", "type": "Deposit",    "amount": 5000.00,  "balance": 15000.00},
            {"date": "2025-02-28", "type": "Withdrawal", "amount": 2000.00,  "balance": 10000.00},
            {"date": "2025-02-25", "type": "Bill Pay",   "amount":  500.00,  "balance": 12000.00},
            {"date": "2025-02-20", "type": "Deposit",    "amount": 10000.00, "balance": 12500.00},
            {"date": "2025-02-15", "type": "Withdrawal", "amount": 1500.00,  "balance":  2500.00},
        ],
    },
    "0987654321": {
        "pin": "2222", "name": "Bob Smith", "balance": 8_500.00,
        "transactions": [
            {"date": "2025-03-02", "type": "Deposit",    "amount": 3000.00, "balance": 8500.00},
            {"date": "2025-02-27", "type": "Withdrawal", "amount": 1000.00, "balance": 5500.00},
        ],
    },
}

BILLS = {
    "Electric Bill": {"provider": "City Power Co.",    "account": "EL-2024-001", "icon": "⚡"},
    "Water Bill":    {"provider": "Metro Water Corp.", "account": "WA-2024-002", "icon": "💧"},
    "Internet Bill": {"provider": "FastNet ISP",       "account": "IN-2024-003", "icon": "🌐"},
    "Phone Bill":    {"provider": "TeleCom Services",  "account": "PH-2024-004", "icon": "📱"},
    "Credit Card":   {"provider": "SecureBank Card",   "account": "CC-2024-005", "icon": "💳"},
}

C = {
    "bg": "#0D1117", "machine": "#161B22", "screen": "#0A0E14",
    "panel": "#1C2128", "panel2": "#21262D", "border": "#30363D",
    "accent": "#58A6FF", "accent2": "#1F6FEB",
    "green": "#3FB950", "red": "#F85149", "amber": "#D29922",
    "gold": "#E3B341", "txt": "#E6EDF3", "txt2": "#8B949E",
    "txt3": "#484F58", "purple": "#BC8CFF",
    "paper": "#F5F0E8", "paper2": "#E8E0CC",
    "bill_green": "#85C47A", "bill_dark": "#2D5A27",
}

BP_NARROW = 700
BP_MEDIUM = 900

def scale(base, w):
    return int(base * max(0.70, min(1.25, w / 1100)))

def rrect(cv, x1, y1, x2, y2, r=10, **kw):
    pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
           x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
           x1,y2, x1,y2-r, x1,y1+r, x1,y1]
    return cv.create_polygon(pts, smooth=True, **kw)


# ═════════════════════════════════════════════════════════════════════════════
# ANIMATION CLASSES
# ═════════════════════════════════════════════════════════════════════════════

class CardSlotAnimator:
    """Animates a credit card sliding into the ATM slot."""
    def __init__(self, canvas, slot_x1, slot_y, slot_x2, slot_h, machine_bg, app):
        self.cv = canvas
        self.sx1, self.sy, self.sx2, self.sh = slot_x1, slot_y, slot_x2, slot_h
        self.machine_bg = machine_bg
        self.app = app
        self._job = None
        self._items = []
        self._anim_running = False

        # Draw static slot
        self._slot_bg = canvas.create_rectangle(
            slot_x1, slot_y, slot_x2, slot_y + slot_h,
            fill=C["bg"], outline=C["border"], width=1)
        # slot shadow lines
        self._slot_line1 = canvas.create_line(slot_x1+1, slot_y+2, slot_x2-1, slot_y+2,
                                               fill=C["txt3"], width=1)
        self._slot_line2 = canvas.create_line(slot_x1+1, slot_y+slot_h-2, slot_x2-1, slot_y+slot_h-2,
                                               fill=C["txt3"], width=1)

    def animate_insert(self, callback=None):
        """Card slides in from right → disappears into slot."""
        if self._anim_running:
            return
        self._anim_running = True
        # Clean up any previous card items
        for item in self._items:
            try: self.cv.delete(item)
            except: pass
        self._items = []

        cw, ch = 58, 36   # card dimensions
        slot_mid_y = self.sy + self.sh // 2
        card_y1 = slot_mid_y - ch // 2
        card_y2 = slot_mid_y + ch // 2

        # Create card to the right of slot
        start_x = self.sx2 + cw + 10
        target_x = self.sx1 + 5  # almost fully inserted

        # Card body
        card = self.cv.create_rectangle(start_x, card_y1, start_x + cw, card_y2,
                                         fill="#2563EB", outline="#1D4ED8", width=1)
        # Card chip
        chip = self.cv.create_rectangle(start_x + 6, card_y1 + 8, start_x + 20, card_y2 - 8,
                                         fill=C["gold"], outline=C["amber"], width=1)
        # Chip lines
        chip_l1 = self.cv.create_line(start_x + 11, card_y1 + 8, start_x + 11, card_y2 - 8,
                                       fill=C["amber"], width=1)
        chip_l2 = self.cv.create_line(start_x + 6, slot_mid_y - 1, start_x + 20, slot_mid_y - 1,
                                       fill=C["amber"], width=1)
        # Card stripe
        stripe = self.cv.create_rectangle(start_x + cw - 10, card_y1 + 4,
                                           start_x + cw - 2, card_y2 - 4,
                                           fill="#1E3A8A", outline="")
        self._items = [card, chip, chip_l1, chip_l2, stripe]

        # Flash slot LED green
        led_x = self.sx1 + (self.sx2 - self.sx1) // 2
        led = self.cv.create_oval(led_x - 4, self.sy - 6, led_x + 4, self.sy + 2,
                                   fill=C["green"], outline="")
        self._items.append(led)

        step = [0]
        total_steps = 22
        dx = (target_x - start_x) / total_steps

        def move():
            if step[0] >= total_steps:
                # Card "sucked in" — show partial card disappearing
                self._eject_into_slot(card, chip, chip_l1, chip_l2, stripe, led, callback)
                return
            offset = step[0] * dx
            for item in [card, chip, chip_l1, chip_l2, stripe]:
                try: self.cv.move(item, dx, 0)
                except: pass
            # Clip card behind slot visually: raise slot bg
            self.cv.tag_raise(self._slot_bg)
            self.cv.tag_raise(self._slot_line1)
            self.cv.tag_raise(self._slot_line2)
            step[0] += 1
            self._job = self.app.after(25, move)

        move()

    def _eject_into_slot(self, card, chip, cl1, cl2, stripe, led, callback):
        """Final suck-in: card shrinks into slot, then disappears."""
        step = [0]
        total = 10
        def shrink():
            if step[0] >= total:
                for item in self._items:
                    try: self.cv.delete(item)
                    except: pass
                self._items = []
                self._anim_running = False
                # Flash slot green briefly then reset
                self.cv.itemconfig(self._slot_bg, fill=C["accent2"])
                self.app.after(300, lambda: self.cv.itemconfig(self._slot_bg, fill=C["bg"]))
                if callback:
                    self.app.after(400, callback)
                return
            # shrink card height into slot
            try:
                coords = self.cv.coords(card)
                mid_y = (coords[1] + coords[3]) / 2
                shrink_amt = (coords[3] - coords[1]) / (2 * (total - step[0] + 1))
                self.cv.coords(card, coords[0], mid_y - shrink_amt,
                               coords[2], mid_y + shrink_amt)
            except: pass
            step[0] += 1
            self._job = self.app.after(30, shrink)
        shrink()

    def reset(self):
        for item in self._items:
            try: self.cv.delete(item)
            except: pass
        self._items = []
        self._anim_running = False
        if self._job:
            try: self.app.after_cancel(self._job)
            except: pass


class CashDispenserAnimator:
    """Animates bills coming out of the cash dispenser slot."""
    def __init__(self, canvas, slot_x1, slot_y, slot_x2, slot_h, app):
        self.cv = canvas
        self.sx1, self.sy, self.sx2, self.sh = slot_x1, slot_y, slot_x2, slot_h
        self.app = app
        self._job = None
        self._items = []
        self._anim_running = False

        # Draw static dispenser slot
        self._slot_bg = canvas.create_rectangle(
            slot_x1, slot_y, slot_x2, slot_y + slot_h,
            fill=C["bg"], outline=C["border"], width=1)
        self._slot_shadow = canvas.create_rectangle(
            slot_x1 + 2, slot_y + 1, slot_x2 - 2, slot_y + slot_h - 1,
            fill=C["txt3"], outline="")

    def animate_dispense(self, callback=None):
        if self._anim_running:
            return
        self._anim_running = True
        for item in self._items:
            try: self.cv.delete(item)
            except: pass
        self._items = []

        slot_mid_x = (self.sx1 + self.sx2) // 2
        bill_w, bill_h = 54, 22
        num_bills = 3

        # Bills start hidden inside slot (at slot_y), slide downward
        bills_data = []
        for i in range(num_bills):
            offset_x = (i - 1) * 3
            bx1 = slot_mid_x - bill_w // 2 + offset_x
            bx2 = bx1 + bill_w
            by1 = self.sy - bill_h + 2
            by2 = self.sy + 2
            bill = self.cv.create_rectangle(bx1, by1, bx2, by2,
                                             fill=C["bill_green"], outline=C["bill_dark"], width=1)
            # Bill face lines
            line1 = self.cv.create_line(bx1 + 4, by1 + 4, bx2 - 4, by1 + 4,
                                         fill=C["bill_dark"], width=1)
            line2 = self.cv.create_line(bx1 + 4, by2 - 4, bx2 - 4, by2 - 4,
                                         fill=C["bill_dark"], width=1)
            center_oval = self.cv.create_oval(bx1 + bill_w//2 - 6, by1 + 4,
                                               bx1 + bill_w//2 + 6, by2 - 4,
                                               fill="#5BA358", outline=C["bill_dark"], width=1)
            bills_data.append((bill, line1, line2, center_oval))
            self._items.extend([bill, line1, line2, center_oval])

        # Raise slot bg to clip bills inside slot
        self.cv.tag_raise(self._slot_bg)
        self.cv.tag_raise(self._slot_shadow)

        step = [0]
        total_steps = 28
        target_dy = bill_h + 14  # how far bills protrude below slot

        def dispense():
            if step[0] >= total_steps:
                self._anim_running = False
                # Blink slot green
                self.cv.itemconfig(self._slot_bg, fill=C["green"])
                self.app.after(200, lambda: self.cv.itemconfig(self._slot_bg, fill=C["bg"]))
                self.app.after(500, lambda: self._retract(bills_data, callback))
                return
            # Ease out: fast at start, slow at end
            progress = step[0] / total_steps
            dy = target_dy * (1 - (1 - progress) ** 2) / total_steps * total_steps
            # Just move a bit each frame with easing
            ease = math.sin(progress * math.pi / 2)
            frame_dy = (target_dy / total_steps) * (2 - ease)
            for bd in bills_data:
                for item in bd:
                    try: self.cv.move(item, 0, min(frame_dy, 1.5))
                    except: pass
            step[0] += 1
            self._job = self.app.after(30, dispense)

        dispense()

    def _retract(self, bills_data, callback):
        """Bills slide back into dispenser after being 'taken'."""
        step = [0]
        total = 14
        for bd in bills_data:
            for item in bd:
                try: self.cv.tag_raise(item)
                except: pass
        def retract():
            if step[0] >= total:
                for item in self._items:
                    try: self.cv.delete(item)
                    except: pass
                self._items = []
                if callback:
                    self.app.after(100, callback)
                return
            for bd in bills_data:
                for item in bd:
                    try: self.cv.move(item, 0, -2)
                    except: pass
            step[0] += 1
            self._job = self.app.after(25, retract)
        retract()


class ReceiptPrinterAnimator:
    """Animates a receipt paper feeding out of the printer."""
    def __init__(self, canvas, slot_x1, slot_y, slot_x2, slot_h, app):
        self.cv = canvas
        self.sx1, self.sy, self.sx2, self.sh = slot_x1, slot_y, slot_x2, slot_h
        self.app = app
        self._job = None
        self._items = []
        self._anim_running = False

        # Static printer housing
        hw = slot_x2 - slot_x1
        self._housing = canvas.create_rectangle(
            slot_x1, slot_y - 6, slot_x2, slot_y + slot_h + 4,
            fill=C["panel"], outline=C["border"], width=1)
        # Slot opening
        self._slot_bg = canvas.create_rectangle(
            slot_x1 + 4, slot_y, slot_x2 - 4, slot_y + slot_h,
            fill=C["bg"], outline=C["txt3"], width=1)
        # Printer brand dot
        dot_x = slot_x1 + hw - 8
        self._brand_dot = canvas.create_oval(dot_x - 3, slot_y - 3,
                                              dot_x + 3, slot_y + 3,
                                              fill=C["green"], outline="")

    def animate_print(self, callback=None):
        if self._anim_running:
            return
        self._anim_running = True
        for item in self._items:
            try: self.cv.delete(item)
            except: pass
        self._items = []

        pw = (self.sx2 - self.sx1) - 12  # paper width
        px1 = self.sx1 + 6
        py_start = self.sy  # paper starts at slot top
        paper_color = C["paper"]
        paper_shadow = C["paper2"]

        # Create paper (starts at height 0, grows downward)
        paper_bg = self.cv.create_rectangle(px1, py_start,
                                             px1 + pw, py_start,
                                             fill=paper_color, outline=paper_shadow, width=1)
        # Paper tear edge
        tear_line = self.cv.create_line(px1, py_start, px1 + pw, py_start,
                                         fill=paper_shadow, width=1, dash=(2, 2))
        # Text lines on paper (pre-created, will become visible as paper grows)
        lines_data = []
        line_texts = ["SECUREATM", "─" * 12, "TRANSACTION", "RECEIPT", "─" * 12,
                      "Amount:", "Balance:", "─" * 12, "THANK YOU!"]
        for i, txt in enumerate(line_texts):
            lbl = self.cv.create_text(px1 + pw // 2, py_start + 6 + i * 8,
                                       text=txt, font=("Courier New", 5), fill=C["txt3"],
                                       anchor="center")
            lines_data.append(lbl)
            self._items.append(lbl)
        self._items.extend([paper_bg, tear_line])

        target_height = 80
        step = [0]
        total_steps = 30
        dh_per_step = target_height / total_steps

        # Blink printer dot
        self.cv.itemconfig(self._brand_dot, fill=C["amber"])

        def grow():
            if step[0] >= total_steps:
                self._anim_running = False
                self.cv.itemconfig(self._brand_dot, fill=C["green"])
                # Tear animation
                self.app.after(600, lambda: self._tear(paper_bg, tear_line, lines_data, callback))
                return
            h = (step[0] + 1) * dh_per_step
            try:
                self.cv.coords(paper_bg, px1, py_start, px1 + pw, py_start + h)
                self.cv.coords(tear_line, px1, py_start + h, px1 + pw, py_start + h)
                # Raise paper above housing
                self.cv.tag_raise(paper_bg)
                self.cv.tag_raise(tear_line)
                for lbl in lines_data:
                    self.cv.tag_raise(lbl)
            except: pass
            step[0] += 1
            # Simulate mechanical sound: vary speed
            delay = 18 if step[0] % 3 != 0 else 35
            self._job = self.app.after(delay, grow)

        grow()

    def _tear(self, paper_bg, tear_line, lines_data, callback):
        """Paper tears off — slides down and fades."""
        step = [0]
        total = 12
        def fall():
            if step[0] >= total:
                for item in self._items:
                    try: self.cv.delete(item)
                    except: pass
                self._items = []
                if callback:
                    self.app.after(200, callback)
                return
            dy = 2 + step[0] * 0.5
            for item in [paper_bg, tear_line] + lines_data:
                try: self.cv.move(item, 0, dy)
                except: pass
            step[0] += 1
            self._job = self.app.after(30, fall)
        fall()


# ═════════════════════════════════════════════════════════════════════════════
# MAIN APP
# ═════════════════════════════════════════════════════════════════════════════

class ATMApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SecureATM — Banking Simulation")
        self.configure(bg=C["bg"])
        self.minsize(480, 520)

        self.current_account = None
        self.card_number     = None
        self.pin_attempts    = 0
        self.input_var       = tk.StringVar()
        self._current_screen = "welcome"
        self._screen_kwargs  = {}
        self._last_w         = 0
        self._resize_job     = None

        # Animation controller references
        self._card_anim      = None
        self._cash_anim      = None
        self._receipt_anim   = None

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        W, H = min(1200, sw - 80), min(760, sh - 80)
        self.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

        self._pick_fonts(W)
        self._build_shell()
        self._start_clock()
        self.bind("<Configure>", self._on_resize)
        self.show_screen("welcome")

    # ── Fonts ─────────────────────────────────────────────────────────────────
    def _pick_fonts(self, w=1100):
        if platform.system() == "Windows":
            base, mono = "Segoe UI", "Consolas"
        elif platform.system() == "Darwin":
            base, mono = "Helvetica Neue", "Menlo"
        else:
            base, mono = "Ubuntu", "Ubuntu Mono"
        avail = set(tkfont.families())
        def pick(p, fb):
            for f in [p] + fb:
                if f in avail: return f
            return "TkDefaultFont"
        s = pick(base, ["Helvetica Neue", "Helvetica", "Arial"])
        m = pick(mono, ["DejaVu Sans Mono", "Courier New"])
        r = max(0.72, min(1.20, w / 1100))
        def fs(n): return max(8, int(n * r))
        self.F = {
            "brand":  (s, fs(19), "bold"),
            "h1":     (s, fs(17), "bold"),
            "h2":     (s, fs(13), "bold"),
            "body":   (s, fs(11)),
            "body_b": (s, fs(11), "bold"),
            "small":  (s, fs(10)),
            "small_b":(s, fs(10), "bold"),
            "tiny":   (s, fs(8)),
            "num":    (m, fs(24), "bold"),
            "num_sm": (m, fs(13), "bold"),
            "kpad":   (s, fs(15), "bold"),
            "kpad_sm":(s, fs(10), "bold"),
        }

    # ── Shell ─────────────────────────────────────────────────────────────────
    def _build_shell(self):
        self.header = tk.Frame(self, bg=C["machine"], height=54)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)

        lc = tk.Canvas(self.header, width=36, height=36,
                       bg=C["machine"], highlightthickness=0)
        lc.pack(side="left", padx=(16, 8), pady=9)
        rrect(lc, 2, 2, 34, 34, r=8, fill=C["accent2"], outline="")
        lc.create_text(18, 18, text="$", font=(self.F["brand"][0], 14, "bold"), fill="white")

        tk.Label(self.header, text="SecureATM", font=self.F["brand"],
                 bg=C["machine"], fg=C["txt"]).pack(side="left")
        tk.Label(self.header, text="Personal Banking", font=self.F["tiny"],
                 bg=C["machine"], fg=C["txt3"]).pack(side="left", padx=(4, 0), pady=(14, 0))

        self.clock_lbl = tk.Label(self.header, text="", font=self.F["small"],
                                  bg=C["machine"], fg=C["txt2"])
        self.clock_lbl.pack(side="right", padx=16)
        tk.Label(self.header, text="● ONLINE", font=self.F["small_b"],
                 bg=C["machine"], fg=C["green"]).pack(side="right", padx=4)

        tk.Frame(self, bg=C["accent2"], height=2).pack(fill="x")

        self.body = tk.Frame(self, bg=C["bg"])
        self.body.pack(fill="both", expand=True)

        self.left_panel = tk.Frame(self.body, bg=C["machine"], width=240)
        self.left_panel.pack(side="left", fill="y")
        self.left_panel.pack_propagate(False)
        self._build_machine_panel()

        screen_wrap = tk.Frame(self.body, bg=C["screen"],
                               highlightbackground=C["border"], highlightthickness=1)
        screen_wrap.pack(side="left", fill="both", expand=True)

        self.content = tk.Frame(screen_wrap, bg=C["screen"])
        self.content.pack(fill="both", expand=True)

        self.footer = tk.Frame(self, bg=C["machine"], height=28)
        self.footer.pack(fill="x", side="bottom")
        self.footer.pack_propagate(False)
        tk.Label(self.footer,
                 text="24/7 Banking Service  •  Helpline: 1800-ATM-HELP  •  VAT Reg: 012-345-678",
                 font=self.F["tiny"], bg=C["machine"], fg=C["txt3"]).pack(pady=7)

    # ── Machine Panel with Animated Parts ─────────────────────────────────────
    def _build_machine_panel(self):
        mp = self.left_panel
        for w in mp.winfo_children():
            w.destroy()
        self._card_anim    = None
        self._cash_anim    = None
        self._receipt_anim = None

        tk.Label(mp, text="", bg=C["machine"]).pack(pady=8)

        # ── CARD SLOT ──────────────────────────────────────────────────────
        tk.Label(mp, text="CARD SLOT", font=self.F["tiny"],
                 bg=C["machine"], fg=C["txt3"]).pack()

        card_cv = tk.Canvas(mp, width=170, height=40,
                            bg=C["machine"], highlightthickness=0)
        card_cv.pack(pady=2)

        # Housing frame around slot
        card_cv.create_rectangle(15, 8, 155, 32,
                                  fill=C["panel"], outline=C["border"], width=1)
        # Label arrows indicating card direction
        card_cv.create_text(8, 20, text="→", font=("", 8), fill=C["txt3"])
        card_cv.create_text(162, 20, text="←", font=("", 8), fill=C["txt3"])

        self._card_anim = CardSlotAnimator(
            card_cv, 20, 12, 150, 16, C["machine"], self)

        # ── LEDS ──────────────────────────────────────────────────────────
        tk.Frame(mp, bg=C["border"], height=1).pack(fill="x", padx=16, pady=8)
        lf = tk.Frame(mp, bg=C["machine"])
        lf.pack()
        for lbl, col in [("PWR", C["green"]), ("NET", C["accent"]), ("TXN", C["amber"])]:
            cf2 = tk.Frame(lf, bg=C["machine"])
            cf2.pack(side="left", padx=10)
            dc = tk.Canvas(cf2, width=10, height=10, bg=C["machine"], highlightthickness=0)
            dc.pack()
            dc.create_oval(1, 1, 9, 9, fill=col, outline="")
            tk.Label(cf2, text=lbl, font=self.F["tiny"],
                     bg=C["machine"], fg=C["txt3"]).pack()

        # ── DECORATIVE KEYPAD ─────────────────────────────────────────────
        tk.Frame(mp, bg=C["border"], height=1).pack(fill="x", padx=16, pady=8)
        tk.Label(mp, text="KEYPAD", font=self.F["tiny"],
                 bg=C["machine"], fg=C["txt3"]).pack()
        kc = tk.Canvas(mp, width=160, height=100, bg=C["machine"], highlightthickness=0)
        kc.pack(pady=4)
        for ri, row in enumerate(["1 2 3", "4 5 6", "7 8 9", "* 0 #"]):
            for ci2, key in enumerate(row.split()):
                x, y = 26 + ci2 * 46, 13 + ri * 22
                rrect(kc, x-13, y-8, x+13, y+8, r=4, fill=C["panel2"], outline="")
                kc.create_text(x, y, text=key, font=self.F["kpad_sm"], fill=C["txt2"])

        # ── CASH DISPENSER ─────────────────────────────────────────────────
        tk.Frame(mp, bg=C["border"], height=1).pack(fill="x", padx=16, pady=8)
        tk.Label(mp, text="CASH DISPENSER", font=self.F["tiny"],
                 bg=C["machine"], fg=C["txt3"]).pack()

        cash_cv = tk.Canvas(mp, width=170, height=50,
                            bg=C["machine"], highlightthickness=0)
        cash_cv.pack(pady=2)
        # Housing
        cash_cv.create_rectangle(15, 6, 155, 44,
                                  fill=C["panel"], outline=C["border"], width=1)

        self._cash_anim = CashDispenserAnimator(
            cash_cv, 20, 18, 150, 14, self)

        # ── RECEIPT PRINTER ────────────────────────────────────────────────
        tk.Frame(mp, bg=C["border"], height=1).pack(fill="x", padx=16, pady=8)
        tk.Label(mp, text="RECEIPT PRINTER", font=self.F["tiny"],
                 bg=C["machine"], fg=C["txt3"]).pack()

        rcpt_cv = tk.Canvas(mp, width=170, height=52,
                            bg=C["machine"], highlightthickness=0)
        rcpt_cv.pack(pady=2)
        # Printer body
        rcpt_cv.create_rectangle(10, 4, 160, 48,
                                  fill=C["panel2"], outline=C["border"], width=1)
        # Feed roller hint
        rcpt_cv.create_rectangle(14, 20, 156, 28,
                                  fill=C["machine"], outline=C["txt3"], width=1)

        self._receipt_anim = ReceiptPrinterAnimator(
            rcpt_cv, 25, 20, 145, 8, self)

        tk.Label(mp, text="Emergency: 1800-ATM-HELP",
                 font=self.F["tiny"], bg=C["machine"], fg=C["txt3"]).pack(side="bottom", pady=10)

    # ── Animation triggers ─────────────────────────────────────────────────────
    def trigger_card_insert(self, callback=None):
        if self._card_anim and self.left_panel.winfo_ismapped():
            self._card_anim.animate_insert(callback)
        elif callback:
            callback()

    def trigger_cash_dispense(self, callback=None):
        if self._cash_anim and self.left_panel.winfo_ismapped():
            self._cash_anim.animate_dispense(callback)
        elif callback:
            callback()

    def trigger_receipt_print(self, callback=None):
        if self._receipt_anim and self.left_panel.winfo_ismapped():
            self._receipt_anim.animate_print(callback)
        elif callback:
            callback()

    # ── Clock ─────────────────────────────────────────────────────────────────
    def _start_clock(self):
        def tick():
            try:
                self.clock_lbl.config(text=datetime.now().strftime("%a %d %b  %H:%M:%S"))
                self.after(1000, tick)
            except: pass
        tick()

    # ── Resize ────────────────────────────────────────────────────────────────
    def _on_resize(self, event):
        if event.widget is not self: return
        w = event.width
        if w == self._last_w: return
        self._last_w = w
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, lambda: self._do_reflow(w))

    def _do_reflow(self, w):
        self._pick_fonts(w)
        if w < BP_NARROW:
            self.left_panel.pack_forget()
        else:
            if not self.left_panel.winfo_ismapped():
                for child in self.body.winfo_children():
                    child.pack_forget()
                self.left_panel.pack(side="left", fill="y")
                for child in self.body.winfo_children():
                    if child is not self.left_panel:
                        child.pack(side="left", fill="both", expand=True)
            self.left_panel.config(width=scale(240, w))
            self._build_machine_panel()
        self._update_header_fonts()
        self.show_screen(self._current_screen, **self._screen_kwargs)

    def _update_header_fonts(self):
        for widget in self.header.winfo_children():
            if isinstance(widget, tk.Label):
                txt = widget.cget("text")
                if "SecureATM" in txt: widget.config(font=self.F["brand"])
                elif "Banking" in txt: widget.config(font=self.F["tiny"])
                elif "ONLINE" in txt:  widget.config(font=self.F["small_b"])
                else:                  widget.config(font=self.F["small"])

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _W(self): return self.winfo_width() or 1100
    def _is_narrow(self): return self._W() < BP_NARROW

    def clear_content(self):
        for w in self.content.winfo_children():
            w.destroy()

    def show_screen(self, name, **kwargs):
        self._current_screen = name
        self._screen_kwargs  = kwargs
        self.clear_content()
        pad = scale(28, self._W())
        self.content.config(padx=pad, pady=scale(18, self._W()))
        {
            "welcome":    self._screen_welcome,
            "insert_card":self._screen_insert_card,
            "pin":        self._screen_pin,
            "menu":       self._screen_menu,
            "balance":    self._screen_balance,
            "withdraw":   self._screen_withdraw,
            "deposit":    self._screen_deposit,
            "statement":  self._screen_statement,
            "bills":      self._screen_bills,
            "bill_pay":   self._screen_bill_pay,
            "receipt":    self._screen_receipt,
        }[name](**kwargs)

    def _card_widget(self, parent, padx=16, pady=14, color=C["panel"], border=C["border"]):
        f = tk.Frame(parent, bg=color, highlightbackground=border, highlightthickness=1)
        fi = tk.Frame(f, bg=color)
        fi.pack(fill="both", expand=True, padx=padx, pady=pady)
        return f, fi

    def _btn(self, parent, text, cmd, bg=C["accent"], fg=C["bg"],
             hover=C["accent2"], width=None):
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                      font=self.F["body_b"], relief="flat", cursor="hand2",
                      activebackground=hover, activeforeground=fg,
                      padx=scale(14, self._W()), pady=scale(6, self._W()), bd=0)
        if width: b.config(width=width)
        b.bind("<Enter>", lambda e: b.config(bg=hover))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    def _section_title(self, parent, text, subtitle=None):
        tk.Label(parent, text=text, font=self.F["h1"],
                 bg=C["screen"], fg=C["txt"]).pack(anchor="w", pady=(0, 2))
        if subtitle:
            tk.Label(parent, text=subtitle, font=self.F["small"],
                     bg=C["screen"], fg=C["txt2"]).pack(anchor="w", pady=(0, 10))
        else:
            tk.Frame(parent, bg=C["accent"], height=2, width=36).pack(anchor="w", pady=(2, 10))

    def _sep(self, parent):
        tk.Frame(parent, bg=C["border"], height=1).pack(fill="x", pady=8)

    def _info_row(self, parent, label, value, label_color=None, value_color=None, bg=C["panel"]):
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=label, font=self.F["small"], bg=bg,
                 fg=label_color or C["txt2"], anchor="w", width=18).pack(side="left")
        tk.Label(row, text=value, font=self.F["small_b"], bg=bg,
                 fg=value_color or C["txt"], anchor="e").pack(side="right")

    def _numpad(self, parent, var, on_enter, on_clear,
                show_char="", label="Enter Amount", hint=None):
        w = self._W()
        btn_w = max(3, scale(4, w))
        btn_py = max(6, scale(10, w))

        df = tk.Frame(parent, bg=C["panel"],
                      highlightbackground=C["accent2"], highlightthickness=2)
        df.pack(fill="x", pady=(0, 8))
        if label:
            tk.Label(df, text=label, font=self.F["small"],
                     bg=C["panel"], fg=C["txt2"]).pack(pady=(8, 0))
        entry = tk.Entry(df, textvariable=var, show=show_char,
                         font=self.F["num"], bg=C["panel"], fg=C["accent"],
                         insertbackground=C["accent"], relief="flat",
                         justify="center", width=12, bd=0)
        entry.pack(pady=(4, 8))
        entry.focus_set()
        if hint:
            tk.Label(df, text=hint, font=self.F["tiny"],
                     bg=C["panel"], fg=C["txt3"]).pack(pady=(0, 6))

        kf = tk.Frame(parent, bg=C["screen"])
        kf.pack()
        for row in [("7","8","9"),("4","5","6"),("1","2","3"),("⌫","0","✓")]:
            rf = tk.Frame(kf, bg=C["screen"])
            rf.pack()
            for k in row:
                if k == "⌫":
                    bk, fk, hv = C["amber"], C["bg"], "#B07A1A"
                    act = lambda x=k: on_clear()
                elif k == "✓":
                    bk, fk, hv = C["green"], C["bg"], "#2DA042"
                    act = lambda x=k: on_enter()
                else:
                    bk, fk, hv = C["panel2"], C["txt"], C["border"]
                    act = lambda x=k: var.set(var.get() + x)
                b = tk.Button(kf, text=k, font=self.F["kpad"],
                              bg=bk, fg=fk, relief="flat",
                              width=btn_w, pady=btn_py,
                              cursor="hand2", bd=0, command=act,
                              activebackground=hv, activeforeground=fk)
                b.bind("<Enter>", lambda e, btn=b, h=hv: btn.config(bg=h))
                b.bind("<Leave>", lambda e, btn=b, ob=bk: btn.config(bg=ob))
                b.pack(side="left", padx=3, pady=3)

    def log_tx(self, tx_type, amount):
        acc = self.current_account
        acc["balance"] += amount
        acc["transactions"].insert(0, {
            "date":    datetime.now().strftime("%Y-%m-%d"),
            "type":    tx_type,
            "amount":  abs(amount),
            "balance": acc["balance"],
        })

    # =========================================================================
    # SCREENS
    # =========================================================================

    def _screen_welcome(self):
        narrow = self._is_narrow()

        if narrow:
            center = tk.Frame(self.content, bg=C["screen"])
            center.pack(expand=True)
            ic = tk.Canvas(center, width=80, height=80, bg=C["screen"], highlightthickness=0)
            ic.pack(pady=(20, 8))
            rrect(ic, 4, 4, 76, 76, r=18, fill=C["accent2"], outline="")
            ic.create_text(40, 40, text="$", font=(self.F["brand"][0], 30, "bold"), fill="white")
            tk.Label(center, text="Welcome to SecureATM", font=self.F["h1"],
                     bg=C["screen"], fg=C["txt"]).pack(pady=(4, 2))
            tk.Label(center, text="Secure. Fast. Reliable.", font=self.F["body"],
                     bg=C["screen"], fg=C["txt2"]).pack()
            tk.Label(center, bg=C["screen"]).pack(pady=10)
            self._btn(center, "▶  INSERT CARD",
                      lambda: self._do_insert_card(), width=22).pack()
            tk.Label(center, text="Demo: 1234567890 / PIN 1111",
                     font=self.F["tiny"], bg=C["screen"], fg=C["txt3"]).pack(pady=6)
        else:
            left = tk.Frame(self.content, bg=C["screen"])
            left.pack(side="left", fill="both", expand=True, padx=(0, 20))
            right = tk.Frame(self.content, bg=C["screen"])
            right.pack(side="left", fill="y")

            tk.Label(left, bg=C["screen"]).pack(pady=20)
            ic = tk.Canvas(left, width=90, height=90, bg=C["screen"], highlightthickness=0)
            ic.pack()
            rrect(ic, 4, 4, 86, 86, r=20, fill=C["accent2"], outline="")
            ic.create_text(45, 45, text="$", font=(self.F["brand"][0], 34, "bold"), fill="white")
            tk.Label(left, text="Welcome Back", font=self.F["h1"],
                     bg=C["screen"], fg=C["txt"]).pack(pady=(12, 4))
            tk.Label(left, text="Secure. Fast. Reliable.", font=self.F["body"],
                     bg=C["screen"], fg=C["txt2"]).pack()
            tk.Label(left, bg=C["screen"]).pack(pady=12)

            # INSERT CARD button → triggers card slot animation
            self._btn(left, "  ▶   INSERT YOUR CARD",
                      lambda: self._do_insert_card(), width=26).pack()
            tk.Label(left, text="Touch screen or press INSERT CARD to begin",
                     font=self.F["tiny"], bg=C["screen"], fg=C["txt3"]).pack(pady=4)

            # Demo cards
            tk.Label(right, text="Demo Accounts", font=self.F["body_b"],
                     bg=C["screen"], fg=C["txt2"]).pack(anchor="w", pady=(24, 8))
            for cn, dat in ACCOUNTS.items():
                cf, ci = self._card_widget(right, padx=14, pady=12)
                cf.pack(fill="x", pady=5)
                chc = tk.Canvas(ci, width=28, height=20, bg=C["panel"], highlightthickness=0)
                chc.pack(side="left", padx=(0, 10))
                rrect(chc, 1, 1, 27, 19, r=4, fill=C["gold"], outline="")
                chc.create_line(9,1,9,19, fill=C["amber"], width=1)
                chc.create_line(19,1,19,19, fill=C["amber"], width=1)
                chc.create_line(1,10,27,10, fill=C["amber"], width=1)
                inf = tk.Frame(ci, bg=C["panel"])
                inf.pack(side="left", fill="x", expand=True)
                tk.Label(inf, text=dat["name"], font=self.F["body_b"],
                         bg=C["panel"], fg=C["txt"]).pack(anchor="w")
                tk.Label(inf, text=f"•••• •••• {cn[-4:]}",
                         font=self.F["num_sm"], bg=C["panel"], fg=C["txt2"]).pack(anchor="w")
                pf = tk.Frame(ci, bg=C["panel2"], padx=8, pady=4)
                pf.pack(side="right", padx=(6, 0))
                tk.Label(pf, text="PIN", font=self.F["tiny"],
                         bg=C["panel2"], fg=C["txt3"]).pack()
                tk.Label(pf, text=dat["pin"], font=self.F["num_sm"],
                         bg=C["panel2"], fg=C["gold"]).pack()

    def _do_insert_card(self):
        """Trigger card slot animation then navigate."""
        self.trigger_card_insert(callback=lambda: self.show_screen("insert_card"))

    def _screen_insert_card(self):
        self._section_title(self.content, "Card Insertion",
                            "Enter your 10-digit card number")
        self.input_var.set("")
        narrow = self._is_narrow()

        wrap = tk.Frame(self.content, bg=C["screen"])
        wrap.pack(fill="both", expand=True)
        left = tk.Frame(wrap, bg=C["screen"])
        left.pack(side="left", fill="both", expand=True,
                  padx=(0, 0 if narrow else 24))

        ef = tk.Frame(left, bg=C["panel"],
                      highlightbackground=C["accent2"], highlightthickness=2)
        ef.pack(fill="x", pady=(0, 12))
        entry = tk.Entry(ef, textvariable=self.input_var,
                         font=self.F["num"], bg=C["panel"], fg=C["accent"],
                         insertbackground=C["accent"], relief="flat",
                         justify="center", width=14, bd=0)
        entry.pack(padx=14, pady=10)
        entry.focus_set()

        def verify():
            cn = self.input_var.get().strip()
            if cn in ACCOUNTS:
                self.card_number     = cn
                self.current_account = ACCOUNTS[cn]
                self.pin_attempts    = 0
                self.input_var.set("")
                self.show_screen("pin")
            else:
                ef.config(highlightbackground=C["red"])
                messagebox.showerror("Invalid Card", "Card not recognised. Please try again.")
                ef.config(highlightbackground=C["accent2"])
                self.input_var.set("")

        self._numpad(left, self.input_var, verify,
                     lambda: self.input_var.set(self.input_var.get()[:-1]),
                     show_char="", label="")
        self._btn(left, "← Back",
                  lambda: self.show_screen("welcome"),
                  bg=C["panel"], fg=C["txt2"], hover=C["panel2"]).pack(pady=8, anchor="w")

        if not narrow:
            right = tk.Frame(wrap, bg=C["screen"])
            right.pack(side="left", fill="y")
            cf, ci = self._card_widget(right, padx=16, pady=18)
            cf.pack(pady=(20, 0))
            tk.Label(ci, text="💡  How it works", font=self.F["body_b"],
                     bg=C["panel"], fg=C["gold"]).pack(anchor="w", pady=(0, 10))
            for step, txt in [("1.", "Enter 10-digit card number"),
                               ("2.", "Verify with 4-digit PIN"),
                               ("3.", "Select your transaction"),
                               ("4.", "Collect your receipt")]:
                row = tk.Frame(ci, bg=C["panel"])
                row.pack(fill="x", pady=2)
                tk.Label(row, text=step, font=self.F["small_b"],
                         bg=C["panel"], fg=C["accent"], width=3).pack(side="left")
                tk.Label(row, text=txt, font=self.F["small"],
                         bg=C["panel"], fg=C["txt2"]).pack(side="left")

    def _screen_pin(self):
        self._section_title(self.content, "PIN Verification",
                            f"Card ending ···· {self.card_number[-4:]}")
        self.input_var.set("")

        center = tk.Frame(self.content, bg=C["screen"])
        center.pack(expand=True)

        bf = tk.Frame(center, bg=C["panel"],
                      highlightbackground=C["green"], highlightthickness=1)
        bf.pack(pady=(0, 16), ipadx=12, ipady=6)
        bi = tk.Frame(bf, bg=C["panel"])
        bi.pack(padx=12, pady=8)
        tk.Label(bi, text="🔒  Secure Connection Active",
                 font=self.F["small_b"], bg=C["panel"], fg=C["green"]).pack()
        tk.Label(bi, text=f"{3 - self.pin_attempts} attempt(s) remaining",
                 font=self.F["tiny"], bg=C["panel"], fg=C["txt2"]).pack()

        pf = tk.Frame(center, bg=C["panel"],
                      highlightbackground=C["accent2"], highlightthickness=2)
        pf.pack(fill="x", pady=(0, 8))
        tk.Label(pf, text="Enter PIN", font=self.F["small"],
                 bg=C["panel"], fg=C["txt2"]).pack(pady=(8, 0))
        entry = tk.Entry(pf, textvariable=self.input_var, show="●",
                         font=self.F["num"], bg=C["panel"], fg=C["accent"],
                         insertbackground=C["accent"], relief="flat",
                         justify="center", width=8, bd=0)
        entry.pack(pady=(4, 8))
        entry.focus_set()

        def verify():
            pin = self.input_var.get()
            if len(pin) < 4:
                messagebox.showwarning("Incomplete", "Enter your 4-digit PIN."); return
            if pin == self.current_account["pin"]:
                self.input_var.set("")
                self.show_screen("menu")
            else:
                self.pin_attempts += 1
                self.input_var.set("")
                if self.pin_attempts >= 3:
                    messagebox.showerror("Card Blocked",
                                         "3 incorrect PINs.\nCard blocked for security.")
                    self.card_number = self.current_account = None
                    self.show_screen("welcome")
                else:
                    messagebox.showwarning("Wrong PIN",
                                           f"Incorrect PIN. {3-self.pin_attempts} attempt(s) left.")

        w = self._W()
        btn_w = max(3, scale(4, w))
        btn_py = max(6, scale(10, w))
        kf = tk.Frame(center, bg=C["screen"])
        kf.pack()
        for row in [("7","8","9"),("4","5","6"),("1","2","3"),("⌫","0","✓")]:
            rf = tk.Frame(kf, bg=C["screen"])
            rf.pack()
            for k in row:
                if k == "⌫":
                    bk, fk, hv = C["amber"], C["bg"], "#B07A1A"
                    act = lambda: self.input_var.set(self.input_var.get()[:-1])
                elif k == "✓":
                    bk, fk, hv = C["green"], C["bg"], "#2DA042"
                    act = verify
                else:
                    bk, fk, hv = C["panel2"], C["txt"], C["border"]
                    act = lambda x=k: self.input_var.set((self.input_var.get() + x)[:4])
                b = tk.Button(kf, text=k, font=self.F["kpad"],
                              bg=bk, fg=fk, relief="flat", width=btn_w, pady=btn_py,
                              cursor="hand2", bd=0, command=act,
                              activebackground=hv, activeforeground=fk)
                b.bind("<Enter>", lambda e, btn=b, h=hv: btn.config(bg=h))
                b.bind("<Leave>", lambda e, btn=b, ob=bk: btn.config(bg=ob))
                b.pack(side="left", padx=3, pady=3)

        self._btn(center, "← Cancel / Eject Card",
                  lambda: self.show_screen("welcome"),
                  bg=C["panel"], fg=C["red"], hover=C["panel2"]).pack(pady=10)

    def _screen_menu(self):
        acc = self.current_account
        narrow = self._is_narrow()

        gf = tk.Frame(self.content, bg=C["panel"],
                      highlightbackground=C["border"], highlightthickness=1)
        gf.pack(fill="x", pady=(0, 16))
        gi = tk.Frame(gf, bg=C["panel"])
        gi.pack(fill="x", padx=16, pady=12)

        av = tk.Canvas(gi, width=40, height=40, bg=C["panel"], highlightthickness=0)
        av.pack(side="left", padx=(0, 12))
        rrect(av, 1, 1, 39, 39, r=20, fill=C["accent2"], outline="")
        initials = "".join(n[0] for n in acc["name"].split()[:2])
        av.create_text(20, 20, text=initials,
                       font=(self.F["body_b"][0], 12, "bold"), fill="white")

        inf = tk.Frame(gi, bg=C["panel"])
        inf.pack(side="left", expand=True)
        tk.Label(inf, text=f"Good day, {acc['name'].split()[0]}!",
                 font=self.F["h2"], bg=C["panel"], fg=C["txt"]).pack(anchor="w")
        tk.Label(inf, text=f"Card: •••• •••• {self.card_number[-4:]}",
                 font=self.F["tiny"], bg=C["panel"], fg=C["txt2"]).pack(anchor="w")

        if not narrow:
            bf2 = tk.Frame(gi, bg=C["panel"])
            bf2.pack(side="right")
            tk.Label(bf2, text="Balance", font=self.F["tiny"],
                     bg=C["panel"], fg=C["txt2"]).pack(anchor="e")
            tk.Label(bf2, text=f"₱ {acc['balance']:,.2f}",
                     font=self.F["num_sm"], bg=C["panel"], fg=C["green"]).pack(anchor="e")

        items = [
            ("💰", "Balance Inquiry",   "balance",   C["accent"]),
            ("💸", "Cash Withdrawal",   "withdraw",  C["green"]),
            ("📥", "Cash Deposit",      "deposit",   C["gold"]),
            ("📋", "Mini Statement",    "statement", C["purple"]),
            ("🧾", "Bill Payment",      "bills",     "#FF7B54"),
            ("⏏", "Exit / Eject",      "welcome",   C["txt3"]),
        ]
        cols = 1 if narrow else 2
        grid = tk.Frame(self.content, bg=C["screen"])
        grid.pack(fill="both", expand=True)
        for i, (icon, title, screen, color) in enumerate(items):
            r, c = divmod(i, cols)
            is_exit = screen == "welcome"
            bg_ = C["machine"] if is_exit else C["panel"]
            cf = tk.Frame(grid, bg=bg_,
                          highlightbackground=color if not is_exit else C["border"],
                          highlightthickness=1, cursor="hand2")
            cf.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")
            grid.columnconfigure(c, weight=1)
            grid.rowconfigure(r, weight=1)
            inner = tk.Frame(cf, bg=bg_)
            inner.pack(fill="both", expand=True, padx=12, pady=10 if narrow else 12)
            tk.Frame(inner, bg=color, height=3, width=28).pack(anchor="w", pady=(0, 8))
            tk.Label(inner, text=icon, font=("", 20 if not narrow else 16),
                     bg=bg_).pack(anchor="w")
            tk.Label(inner, text=title, font=self.F["body_b"],
                     bg=bg_, fg=C["red"] if is_exit else C["txt"]).pack(anchor="w", pady=(3, 0))
            for widget in [cf, inner] + list(inner.winfo_children()):
                widget.bind("<Button-1>", lambda e, s=screen: self.show_screen(s))
            cf.bind("<Enter>", lambda e, f=cf, col=color: f.config(highlightbackground=C["txt"]))
            cf.bind("<Leave>", lambda e, f=cf, col=color: f.config(highlightbackground=col))

    def _screen_balance(self):
        acc = self.current_account
        self._section_title(self.content, "Balance Inquiry")
        bf = tk.Frame(self.content, bg=C["accent2"],
                      highlightbackground=C["accent"], highlightthickness=1)
        bf.pack(fill="x", pady=(0, 16))
        bi = tk.Frame(bf, bg=C["accent2"])
        bi.pack(padx=20, pady=16)
        tk.Label(bi, text="Available Balance", font=self.F["body"],
                 bg=C["accent2"], fg="#CCECFF").pack()
        tk.Label(bi, text=f"₱ {acc['balance']:,.2f}", font=self.F["num"],
                 bg=C["accent2"], fg="white").pack(pady=4)
        tk.Label(bi, text=datetime.now().strftime("%B %d, %Y  %I:%M %p"),
                 font=self.F["tiny"], bg=C["accent2"], fg="#AADAFF").pack()
        cf, ci = self._card_widget(self.content, padx=18, pady=14)
        cf.pack(fill="x", pady=(0, 14))
        tk.Label(ci, text="Account Details", font=self.F["body_b"],
                 bg=C["panel"], fg=C["txt2"]).pack(anchor="w", pady=(0, 8))
        for k, v in [
            ("Account Holder", acc["name"]),
            ("Card Number",    f"•••• •••• {self.card_number[-4:]}"),
            ("Account Type",   "Savings Account"),
            ("Date & Time",    datetime.now().strftime("%Y-%m-%d  %H:%M:%S")),
        ]:
            self._info_row(ci, k, v, bg=C["panel"])
        row = tk.Frame(self.content, bg=C["screen"])
        row.pack(anchor="w")
        self._btn(row, "← Menu",
                  lambda: self.show_screen("menu"),
                  bg=C["panel"], fg=C["txt"], hover=C["panel2"]).pack(side="left", padx=(0, 8))
        self._btn(row, "📋 Statement",
                  lambda: self.show_screen("statement")).pack(side="left")

    def _screen_withdraw(self):
        acc = self.current_account
        narrow = self._is_narrow()
        self._section_title(self.content, "Cash Withdrawal",
                            f"Balance: ₱ {acc['balance']:,.2f}")
        self.input_var.set("")

        wrap = tk.Frame(self.content, bg=C["screen"])
        wrap.pack(fill="both", expand=True)

        if not narrow:
            left = tk.Frame(wrap, bg=C["screen"])
            left.pack(side="left", fill="y", padx=(0, 24))
            right = tk.Frame(wrap, bg=C["screen"])
            right.pack(side="left", fill="both", expand=True)
            npad_parent, info_parent = left, right
        else:
            npad_parent = info_parent = self.content

        tk.Label(info_parent, text="Quick Select", font=self.F["small_b"],
                 bg=C["screen"], fg=C["txt2"]).pack(anchor="w", pady=(0, 4))
        qg = tk.Frame(info_parent, bg=C["screen"])
        qg.pack(fill="x", pady=(0, 12))
        amounts = [500, 1000, 2000, 5000] if narrow else [500, 1000, 2000, 3000, 5000, 10000]
        cols_q = 4 if narrow else 3
        for i, amt in enumerate(amounts):
            b = tk.Button(qg, text=f"₱{amt:,}", font=self.F["small_b"],
                          bg=C["panel2"], fg=C["accent"], relief="flat",
                          padx=8, pady=6, cursor="hand2",
                          command=lambda a=amt: self.input_var.set(str(int(a))))
            b.bind("<Enter>", lambda e, btn=b: btn.config(bg=C["border"]))
            b.bind("<Leave>", lambda e, btn=b: btn.config(bg=C["panel2"]))
            b.grid(in_=qg, row=i//cols_q, column=i%cols_q, padx=3, pady=3, sticky="ew")
            qg.columnconfigure(i%cols_q, weight=1)

        cf, ci = self._card_widget(info_parent, padx=12, pady=8)
        cf.pack(fill="x", pady=(0, 8))
        tk.Label(ci, text="ℹ  Multiples of ₱100  |  Max ₱50,000 per transaction",
                 font=self.F["tiny"], bg=C["panel"], fg=C["txt3"]).pack(anchor="w")

        def do_withdraw():
            try: amt = float(self.input_var.get())
            except ValueError:
                messagebox.showerror("Error", "Enter a valid amount."); return
            if amt <= 0:
                messagebox.showerror("Error", "Amount must be positive.")
            elif amt > acc["balance"]:
                messagebox.showerror("Insufficient Funds",
                                     f"Balance ₱{acc['balance']:,.2f} < ₱{amt:,.2f}.")
            elif int(amt) % 100 != 0:
                messagebox.showerror("Invalid", "Withdraw in multiples of ₱100.")
            else:
                self.log_tx("Withdrawal", -amt)
                # Trigger cash dispenser animation, then show receipt
                self.trigger_cash_dispense(
                    callback=lambda: self.show_screen("receipt", tx_type="Withdrawal", amount=amt))

        self._numpad(npad_parent, self.input_var, do_withdraw,
                     lambda: self.input_var.set(self.input_var.get()[:-1]),
                     show_char="", label="Amount to Withdraw (₱)")
        self._btn(info_parent, "← Menu",
                  lambda: self.show_screen("menu"),
                  bg=C["panel"], fg=C["txt2"], hover=C["panel2"]).pack(pady=6, anchor="w")

    def _screen_deposit(self):
        acc = self.current_account
        narrow = self._is_narrow()
        self._section_title(self.content, "Cash Deposit",
                            f"Current balance: ₱ {acc['balance']:,.2f}")
        self.input_var.set("")

        wrap = tk.Frame(self.content, bg=C["screen"])
        wrap.pack(fill="both", expand=True)

        if not narrow:
            left = tk.Frame(wrap, bg=C["screen"])
            left.pack(side="left", fill="y", padx=(0, 24))
            right = tk.Frame(wrap, bg=C["screen"])
            right.pack(side="left", fill="both", expand=True)
        else:
            left = right = self.content

        cf, ci = self._card_widget(right, padx=16, pady=14)
        cf.pack(fill="x", pady=(0, 12))
        tk.Label(ci, text="📥  Insert Cash into Slot", font=self.F["body_b"],
                 bg=C["panel"], fg=C["gold"]).pack(anchor="w", pady=(0, 6))
        tk.Label(ci, text="Insert cash and enter the amount below.",
                 font=self.F["small"], bg=C["panel"], fg=C["txt2"]).pack(anchor="w")
        self._sep(ci)
        for k, v in [("Min deposit", "₱100"), ("Max deposit", "₱500,000")]:
            self._info_row(ci, k, v, bg=C["panel"])

        def do_deposit():
            try: amt = float(self.input_var.get())
            except ValueError:
                messagebox.showerror("Error", "Enter a valid amount."); return
            if amt <= 0:
                messagebox.showerror("Error", "Amount must be positive.")
            else:
                self.log_tx("Deposit", amt)
                # Trigger receipt for deposit
                self.trigger_receipt_print(
                    callback=lambda: self.show_screen("receipt", tx_type="Deposit", amount=amt))

        self._numpad(left, self.input_var, do_deposit,
                     lambda: self.input_var.set(self.input_var.get()[:-1]),
                     show_char="", label="Deposit Amount (₱)")
        self._btn(right, "← Menu",
                  lambda: self.show_screen("menu"),
                  bg=C["panel"], fg=C["txt2"], hover=C["panel2"]).pack(pady=6, anchor="w")

    def _screen_statement(self):
        acc = self.current_account
        narrow = self._is_narrow()
        self._section_title(self.content, "Mini Statement",
                            f"Last {min(8, len(acc['transactions']))} transactions")

        txs = acc["transactions"]
        total_in  = sum(t["amount"] for t in txs if t["type"] == "Deposit")
        total_out = sum(t["amount"] for t in txs if t["type"] != "Deposit")

        sr = tk.Frame(self.content, bg=C["screen"])
        sr.pack(fill="x", pady=(0, 12))
        for label, val, color in [
            ("Total In",  f"₱{total_in:,.0f}",      C["green"]),
            ("Total Out", f"₱{total_out:,.0f}",     C["red"]),
            ("Balance",   f"₱{acc['balance']:,.0f}", C["accent"]),
        ]:
            sf = tk.Frame(sr, bg=C["panel"],
                          highlightbackground=color, highlightthickness=1)
            sf.pack(side="left", expand=True, fill="x", padx=4)
            si = tk.Frame(sf, bg=C["panel"])
            si.pack(padx=10, pady=8)
            tk.Label(si, text=label, font=self.F["tiny"],
                     bg=C["panel"], fg=C["txt2"]).pack()
            tk.Label(si, text=val, font=self.F["num_sm"],
                     bg=C["panel"], fg=color).pack()

        cols = [("Date", 10), ("Type", 13), ("Amount", 11)] if narrow else \
               [("Date", 11), ("Type", 13), ("Amount", 11), ("Balance", 11)]
        hdr = tk.Frame(self.content, bg=C["panel2"])
        hdr.pack(fill="x")
        for col, w in cols:
            tk.Label(hdr, text=col, font=self.F["small_b"],
                     bg=C["panel2"], fg=C["accent"],
                     width=w, anchor="w").pack(side="left", padx=8, pady=6)

        for i, tx in enumerate(acc["transactions"][:8]):
            is_cr  = tx["type"] == "Deposit"
            row_bg = C["panel"] if i % 2 == 0 else C["machine"]
            row    = tk.Frame(self.content, bg=row_bg)
            row.pack(fill="x")
            arrow, clr = ("▲", C["green"]) if is_cr else ("▼", C["red"])
            data = [(tx["date"], 10 if narrow else 11, C["txt2"]),
                    (tx["type"][:12], 13, C["txt"]),
                    (f"{arrow} ₱{tx['amount']:,.0f}", 11, clr)]
            if not narrow:
                data.append((f"₱{tx['balance']:,.0f}", 11, C["txt"]))
            for val, w, fc in data:
                tk.Label(row, text=val, font=self.F["small"],
                         bg=row_bg, fg=fc, width=w, anchor="w").pack(side="left", padx=8, pady=6)

        tk.Label(self.content, bg=C["screen"]).pack(pady=4)
        self._btn(self.content, "← Menu",
                  lambda: self.show_screen("menu"),
                  bg=C["panel"], fg=C["txt"], hover=C["panel2"]).pack(anchor="w")

    def _screen_bills(self):
        narrow = self._is_narrow()
        self._section_title(self.content, "Bill Payment", "Select a bill to pay")

        # VAT notice
        vat_f = tk.Frame(self.content, bg=C["panel2"],
                         highlightbackground=C["amber"], highlightthickness=1)
        vat_f.pack(fill="x", pady=(0, 10))
        tk.Label(vat_f, text=f"⚠  All bill payments include 12% VAT",
                 font=self.F["small_b"], bg=C["panel2"], fg=C["amber"]).pack(
                 side="left", padx=14, pady=8)

        wrap = tk.Frame(self.content, bg=C["screen"])
        wrap.pack(fill="both", expand=True)
        left = tk.Frame(wrap, bg=C["screen"])
        left.pack(side="left", fill="both", expand=True,
                  padx=(0, 0 if narrow else 16))

        for bill_name, info in BILLS.items():
            cf = tk.Frame(left, bg=C["panel"],
                          highlightbackground=C["border"], highlightthickness=1,
                          cursor="hand2")
            cf.pack(fill="x", pady=4)
            ci = tk.Frame(cf, bg=C["panel"])
            ci.pack(fill="x", padx=14, pady=10)
            tk.Label(ci, text=info["icon"], font=("", 18),
                     bg=C["panel"]).pack(side="left", padx=(0, 10))
            inf = tk.Frame(ci, bg=C["panel"])
            inf.pack(side="left", expand=True)
            tk.Label(inf, text=bill_name, font=self.F["body_b"],
                     bg=C["panel"], fg=C["txt"]).pack(anchor="w")
            if not narrow:
                tk.Label(inf, text=info["provider"],
                         font=self.F["tiny"], bg=C["panel"], fg=C["txt2"]).pack(anchor="w")
            # VAT badge
            vb = tk.Frame(ci, bg=C["amber"], padx=6, pady=2)
            vb.pack(side="right", padx=(0, 8))
            tk.Label(vb, text="+VAT", font=self.F["tiny"],
                     bg=C["amber"], fg=C["bg"]).pack()

            tk.Label(ci, text="›", font=(self.F["h1"][0], 16),
                     bg=C["panel"], fg=C["txt3"]).pack(side="right")

            for w in [cf, ci] + list(ci.winfo_children()) + list(inf.winfo_children()):
                w.bind("<Button-1>",
                       lambda e, b=bill_name: self.show_screen("bill_pay", bill=b))
            cf.bind("<Enter>", lambda e, f=cf: f.config(highlightbackground=C["accent"]))
            cf.bind("<Leave>", lambda e, f=cf: f.config(highlightbackground=C["border"]))

        self._btn(left, "← Menu",
                  lambda: self.show_screen("menu"),
                  bg=C["panel"], fg=C["txt2"], hover=C["panel2"]).pack(pady=8, anchor="w")

        if not narrow:
            right = tk.Frame(wrap, bg=C["screen"])
            right.pack(side="left", fill="y")
            cf2, ci2 = self._card_widget(right, padx=14, pady=14)
            cf2.pack()
            tk.Label(ci2, text="Payment Info", font=self.F["body_b"],
                     bg=C["panel"], fg=C["txt2"]).pack(anchor="w", pady=(0, 8))
            for t in ["Instant processing", "12% VAT included",
                      "Official receipt", "All major billers"]:
                row = tk.Frame(ci2, bg=C["panel"])
                row.pack(fill="x", pady=2)
                tk.Label(row, text="✓", font=self.F["small_b"],
                         bg=C["panel"], fg=C["green"]).pack(side="left", padx=(0, 6))
                tk.Label(row, text=t, font=self.F["small"],
                         bg=C["panel"], fg=C["txt2"]).pack(side="left")

    def _screen_bill_pay(self, bill="Electric Bill"):
        acc  = self.current_account
        info = BILLS[bill]
        narrow = self._is_narrow()
        self._section_title(self.content, f"Pay: {bill}", info["provider"])
        self.input_var.set("")

        wrap = tk.Frame(self.content, bg=C["screen"])
        wrap.pack(fill="both", expand=True)

        if not narrow:
            left = tk.Frame(wrap, bg=C["screen"])
            left.pack(side="left", fill="y", padx=(0, 24))
            right = tk.Frame(wrap, bg=C["screen"])
            right.pack(side="left", fill="both", expand=True)
        else:
            left = right = self.content

        # Bill info card
        cf, ci = self._card_widget(right, padx=16, pady=14)
        cf.pack(fill="x", pady=(0, 12))
        tk.Label(ci, text=f"{info['icon']}  {bill}", font=self.F["h2"],
                 bg=C["panel"], fg=C["txt"]).pack(anchor="w", pady=(0, 8))
        for k, v, vc in [
            ("Provider",  info["provider"], C["txt"]),
            ("Account #", info["account"],  C["txt"]),
            ("Balance",   f"₱ {acc['balance']:,.2f}", C["green"]),
        ]:
            self._info_row(ci, k, v, value_color=vc, bg=C["panel"])

        # Live VAT preview frame
        self._sep(ci)
        vat_preview = tk.Frame(ci, bg=C["panel"])
        vat_preview.pack(fill="x")

        base_lbl   = tk.Label(vat_preview, text="Base amount:  ₱ —",
                              font=self.F["small"], bg=C["panel"], fg=C["txt2"])
        base_lbl.pack(anchor="w")
        vat_lbl    = tk.Label(vat_preview, text="VAT (12%):    ₱ —",
                              font=self.F["small"], bg=C["panel"], fg=C["amber"])
        vat_lbl.pack(anchor="w")
        total_lbl  = tk.Label(vat_preview, text="Total:        ₱ —",
                              font=self.F["small_b"], bg=C["panel"], fg=C["txt"])
        total_lbl.pack(anchor="w")

        def update_vat_preview(*_):
            try:
                amt = float(self.input_var.get())
                vat = amt * VAT_RATE
                total = amt + vat
                base_lbl.config(text=f"Base amount:  ₱ {amt:,.2f}")
                vat_lbl.config(text=f"VAT (12%):    ₱ {vat:,.2f}")
                total_lbl.config(text=f"Total:        ₱ {total:,.2f}")
            except (ValueError, TypeError):
                base_lbl.config(text="Base amount:  ₱ —")
                vat_lbl.config(text="VAT (12%):    ₱ —")
                total_lbl.config(text="Total:        ₱ —")

        self.input_var.trace_add("write", update_vat_preview)

        def do_pay():
            try: base_amt = float(self.input_var.get())
            except ValueError:
                messagebox.showerror("Error", "Enter a valid amount."); return
            if base_amt <= 0:
                messagebox.showerror("Error", "Amount must be positive.")
                return
            vat_amt   = base_amt * VAT_RATE
            total_amt = base_amt + vat_amt
            if total_amt > acc["balance"]:
                messagebox.showerror("Insufficient Funds",
                                     f"Total with VAT ₱{total_amt:,.2f} exceeds balance ₱{acc['balance']:,.2f}.")
                return
            self.log_tx(f"Bill: {bill}", -total_amt)
            # Trigger receipt printer animation then show receipt
            self.trigger_receipt_print(
                callback=lambda: self.show_screen(
                    "receipt",
                    tx_type=f"Bill: {bill}",
                    amount=total_amt,
                    base_amount=base_amt,
                    vat_amount=vat_amt))

        self._numpad(left, self.input_var, do_pay,
                     lambda: self.input_var.set(self.input_var.get()[:-1]),
                     show_char="", label="Base Payment Amount (₱)")
        self._btn(right, "← Bills",
                  lambda: self.show_screen("bills"),
                  bg=C["panel"], fg=C["txt2"], hover=C["panel2"]).pack(pady=6, anchor="w")

    def _screen_receipt(self, tx_type="Transaction", amount=0.0,
                        base_amount=None, vat_amount=None):
        acc    = self.current_account
        narrow = self._is_narrow()
        ref    = f"TXN-{datetime.now().strftime('%Y%m%d')}-{random.randint(100000,999999)}"
        is_cr  = tx_type == "Deposit"
        clr    = C["green"] if is_cr else C["red"]
        is_bill = tx_type.startswith("Bill:")

        wrap = tk.Frame(self.content, bg=C["screen"])
        wrap.pack(fill="both", expand=True)

        left = tk.Frame(wrap, bg=C["screen"])
        left.pack(side="left", fill="both", expand=True,
                  padx=(0, 0 if narrow else 20))

        ic = tk.Canvas(left, width=64, height=64, bg=C["screen"], highlightthickness=0)
        ic.pack(pady=(8, 6))
        rrect(ic, 3, 3, 61, 61, r=32, fill=clr, outline="")
        ic.create_text(32, 32, text="✓",
                       font=(self.F["brand"][0], 24, "bold"), fill="white")

        tk.Label(left, text="Transaction Successful", font=self.F["h2"],
                 bg=C["screen"], fg=C["txt"]).pack()
        tk.Label(left, text=tx_type, font=self.F["body"],
                 bg=C["screen"], fg=C["txt2"]).pack(pady=(2, 0))
        tk.Label(left, text=f"₱ {amount:,.2f}", font=self.F["num"],
                 bg=C["screen"], fg=clr).pack(pady=4)

        cf, ci = self._card_widget(left, padx=18, pady=14, color=C["panel"], border=clr)
        cf.pack(fill="x", pady=8)
        tk.Label(ci, text="Transaction Receipt", font=self.F["small_b"],
                 bg=C["panel"], fg=C["txt2"]).pack(anchor="w", pady=(0, 6))

        # Build receipt rows — show VAT breakdown for bills
        rows = [
            ("Reference",  ref,                                            C["txt"]),
            ("Type",       tx_type,                                        C["txt"]),
        ]
        if is_bill and base_amount is not None:
            rows += [
                ("Base Amount", f"₱ {base_amount:,.2f}",   C["txt"]),
                ("VAT (12%)",   f"₱ {vat_amount:,.2f}",    C["amber"]),
                ("Total Paid",  f"₱ {amount:,.2f}",         clr),
            ]
        else:
            rows.append(("Amount", f"₱ {amount:,.2f}", clr))

        rows += [
            ("New Balance", f"₱ {acc['balance']:,.2f}", C["green"]),
            ("Date & Time", datetime.now().strftime("%Y-%m-%d  %H:%M:%S"), C["txt"]),
            ("Card",        f"•••• •••• {self.card_number[-4:]}",          C["txt"]),
        ]

        for k, v, vc in rows:
            self._info_row(ci, k, v, value_color=vc, bg=C["panel"])

        # VAT compliance note for bills
        if is_bill:
            self._sep(ci)
            tk.Label(ci, text="VAT Reg No: 012-345-678  |  BIR Accredited",
                     font=self.F["tiny"], bg=C["panel"], fg=C["txt3"]).pack(anchor="w")

        br = tk.Frame(left, bg=C["screen"])
        br.pack(pady=10, anchor="w")
        self._btn(br, "← Menu",
                  lambda: self.show_screen("menu")).pack(side="left", padx=(0, 8))
        self._btn(br, "⏏ Eject",
                  lambda: self.show_screen("welcome"),
                  bg=C["panel"], fg=C["red"], hover=C["panel2"]).pack(side="left")

        if not narrow:
            right = tk.Frame(wrap, bg=C["screen"])
            right.pack(side="left", fill="y")
            cf2, ci2 = self._card_widget(right, padx=14, pady=14)
            cf2.pack(pady=(20, 0))
            tk.Label(ci2, text="Another Transaction?",
                     font=self.F["body_b"], bg=C["panel"], fg=C["txt"]).pack(pady=(0, 10))
            for lbl, scr in [("💰 Balance","balance"),("💸 Withdraw","withdraw"),
                             ("📥 Deposit","deposit"),("🧾 Pay Bills","bills")]:
                self._btn(ci2, lbl, lambda s=scr: self.show_screen(s),
                          bg=C["panel2"], fg=C["txt"], hover=C["border"],
                          width=16).pack(pady=4)

        # Auto-trigger receipt printer animation on this screen
        self.trigger_receipt_print()


if __name__ == "__main__":
    app = ATMApp()
    app.mainloop()