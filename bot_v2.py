import os
from html import escape
import asyncio
from telegram import CopyTextButton, Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters, TypeHandler, ApplicationHandlerStop
import sqlite3
import random
from datetime import datetime

TOKEN = os.getenv("BOT_TOKEN")
ACTIVITY_CHAT_ID = -1004427505737
ADMIN_ID = 6427806986

def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM bot_admins WHERE user_id=?", (user_id,))
    result = cur.fetchone()
    conn.close()

    return result is not None

APPROVAL_ADMIN = 6427806986
MAINTENANCE_MODE = False

async def send_activity_log(context, text):
    try:
        await context.bot.send_message(
            chat_id=ACTIVITY_CHAT_ID,
            text=text
        )
    except Exception as e:
        print(f"⚠️ Activity log failed: {e}")


async def approve_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != get_approval_admin():
        return

    data = query.data.split("_")
    user_id = int(data[1])
    reward_name = "_".join(data[2:])

    conn = conn = conn = sqlite3.connect("users.db", timeout=30)
    cur = conn.cursor()

    cur.execute(
        "SELECT points FROM rewards WHERE name=?",
        (reward_name,)
    )
    reward = cur.fetchone()

    if not reward:
        conn.close()
        await query.edit_message_text("❌ Reward not found")
        return

    points = reward[0]

    cur.execute(
        "UPDATE users SET points = points - ? WHERE user_id=?",
        (points, user_id)
    )

    cur.execute(
        "UPDATE rewards SET stock = stock - 1 WHERE name=?",
        (reward_name,)
    )

    cur.execute(
        "UPDATE claim_requests SET status='Approved' WHERE user_id=? AND reward_name=? AND status='Pending'",
        (user_id, reward_name)
    )
    cur.execute(
        "INSERT INTO claim_history(user_id, reward_name, points, claim_time) VALUES(?,?,?,?)",
    (
        user_id,
        reward_name,
        points,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
)

    cur.execute(
        "SELECT code FROM reward_codes WHERE reward_name=? AND used=0 LIMIT 1",
        (reward_name,)
    )
    code_data = cur.fetchone()

    reward_code = code_data[0] if code_data else "Code will be added soon"

    if code_data:
        cur.execute(
            "UPDATE reward_codes SET used=1 WHERE code=?",
            (reward_code,)
        )

    cur.execute(
        "SELECT COUNT(*) FROM reward_codes WHERE reward_name=? AND used=0",
        (reward_name,)
    )
    remaining_codes = cur.fetchone()[0]

    cur.execute("""
    CREATE TABLE IF NOT EXISTS paid_orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT UNIQUE,
        user_id INTEGER,
        reward_id INTEGER,
        reward_name TEXT,
        quantity INTEGER,
        price REAL,
        total REAL,
        utr TEXT,
        screenshot_file_id TEXT,
        status TEXT DEFAULT 'Pending',
        order_time TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS shop_settings(
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    cur.execute(
        "INSERT OR IGNORE INTO shop_settings(key, value) VALUES(?, ?)",
        ("shop_upi", "opboyliveraj@fam")
    )

    cur.execute(
        "INSERT OR IGNORE INTO shop_settings(key, value) VALUES(?, ?)",
        ("shop_qr", "")
    )
    conn.commit()
    conn.close()

    await send_activity_log(
        context,
        "🎁 New Redeem Code Claimed\n\n"
        f"👤 User: {user_id}\n"
        f"🆔 User ID: {user_id}\n"
        f"💰 Redeem Price: {float(points):.1f}\n"
        f"🎟 Redeem Code: **********\n"
        f"📦 Remaining Codes: {remaining_codes}"
    )

    if "spotify" in reward_name.lower() and reward_code.lower().startswith(("http://", "https://")):
        delivery_text = (
            "🎉 CLAIM APPROVED & DELIVERED! 🎉\n\n"
            f"🎁 Reward: {reward_name}\n"
            f'🔑 Code/Link: <a href="{escape(reward_code, quote=True)}">{escape(reward_code)}</a>\n'
            f"💎 Points Deducted: -{points} Pts\n\n"
            "🙏 Thank you for using OpBoy Live Bot!"
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=delivery_text,
            parse_mode=ParseMode.HTML
        )
    else:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "🎉 CLAIM APPROVED & DELIVERED! 🎉\n\n"
                f"🎁 Reward: {reward_name}\n"
                f"🔑 Code/Link: {reward_code}\n"
                f"💎 Points Deducted: -{points} Pts\n\n"
                "🙏 Thank you for using OpBoy Live Bot!"
            )
        )

    await query.edit_message_text(
        "✅ Reward Approved Successfully"
    )


async def reject_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != get_approval_admin():
        return

    data = query.data.split("_")
    user_id = int(data[1])
    reward_name = "_".join(data[2:])

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "UPDATE claim_requests SET status='Rejected' WHERE user_id=? AND reward_name=? AND status='Pending'",
        (user_id, reward_name)
    )

    conn.commit()
    conn.close()

    await context.bot.send_message(
        chat_id=user_id,
        text=(
            "❌ REWARD REQUEST REJECTED\n\n"
            f"🎁 Reward: {reward_name}\n\n"
            "Contact support for help."
        )
    )

    await query.edit_message_text(
        "❌ Reward Request Rejected"
    )

def init_db():
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        points INTEGER DEFAULT 0,
        verified INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS rewards(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    points INTEGER,
    stock INTEGER
)
""")

    rewards_data = [
        ("Gemini Link", 25, 0),
        ("BigBasket Cashback", 15, 0),
        ("Play Store Redeem Code", 9, 0),
        ("Amazon Gift Card", 9, 0),
        ("Spotify Premium", 5, 0),
        ("Netflix 1 Month", 9, 0),
        ("Myntra", 6, 0),
        ("Domino's", 60, 0)
    ]

    for name, points, stock in rewards_data:
        cur.execute(
            "SELECT COUNT(*) FROM rewards WHERE name = ?",
            (name,)
        )
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO rewards(name, points, stock) VALUES(?,?,?)",
                (name, points, stock)
            )

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reward_codes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reward_name TEXT,
        code TEXT,
        used INTEGER DEFAULT 0
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS promo_codes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        points INTEGER,
        max_uses INTEGER,
        used_count INTEGER DEFAULT 0
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS claim_requests(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        reward_name TEXT,
        points INTEGER,
        reward_code TEXT,
        claim_time TEXT
        
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS claim_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        reward_name TEXT,
        points INTEGER,
        claim_time TEXT
    )
    """)
    conn.commit()
    conn.close()
async def human_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query:
        await query.answer()

    operators = ["+", "-", "×", "÷"]
    operator = random.choice(operators)

    if operator == "+":
        a = random.randint(2, 9)
        b = random.randint(1, 9)
        answer = a + b

    elif operator == "-":
        a = random.randint(3, 12)
        b = random.randint(1, a)
        answer = a - b

    elif operator == "×":
        a = random.randint(2, 9)
        b = random.randint(2, 9)
        answer = a * b

    else:
        b = random.randint(2, 9)
        answer = random.randint(1, 9)
        a = b * answer

    wrong1 = answer + random.choice([-3, -2, 2, 3])
    wrong2 = answer + random.choice([-5, -1, 1, 5])

    while wrong1 == answer or wrong1 == wrong2:
        wrong1 = answer + random.choice([-4, -3, -2, 2, 3, 4])

    while wrong2 == answer or wrong2 == wrong1:
        wrong2 = answer + random.choice([-6, -5, -2, 2, 5, 6])

    options = [answer, wrong1, wrong2]
    random.shuffle(options)

    context.user_data["captcha_answer"] = answer

    buttons = [
        [InlineKeyboardButton(str(option), callback_data=f"captcha_{option}")]
        for option in options
    ]

    text = (
        "🤖 Human Verification\n\n"
        f"Solve this:\n\n"
        f"{a} {operator} {b} = ?"
    )

    if query:
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    elif update.message:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )




async def captcha_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    try:
        selected = int(query.data.replace("captcha_", ""))
    except ValueError:
        await query.answer("❌ Invalid captcha.", show_alert=True)
        return

    correct = context.user_data.get("captcha_answer")

    if selected != correct:
        await query.answer("❌ Wrong answer. Try again.", show_alert=True)
        return

    await query.answer("✅ Correct!", show_alert=False)

    user_id = query.from_user.id

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET verified = 1 WHERE user_id=?",
        (user_id,)
    )
    conn.commit()
    conn.close()

    # Show the same normal bottom keyboard
    normal_keyboard = ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("🛍️ Browse Product"),
                KeyboardButton("📦 My Orders")
            ],
            [
                KeyboardButton("📞 Support"),
                KeyboardButton("ℹ️ How It Works")
            ]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

    await context.bot.send_message(
        chat_id=user_id,
        text=(
            "Welcome to OPx Shop 🙏🏻\n\n"
            "📊 Limited Stock Available! 📊\n\n"
            "🛍️ Choose an option below to continue: 👇"
        ),
        reply_markup=normal_keyboard
    )

    # Show the exact same shop screen

    context.user_data.pop("captcha_answer", None)
    return

async def point_packages_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    packages = get_point_packages()

    keyboard = []

    for package_id, points, amount in packages:
        keyboard.append([
            InlineKeyboardButton(
                f"📦 {points} Points → ₹{amount}",
                callback_data=f"pm_package_{package_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton("➕ Add Package", callback_data="pm_add_package")
    ])

    keyboard.append([
        InlineKeyboardButton("⬅️ Point Management", callback_data="admin_point_management")
    ])

    await query.edit_message_text(
        "📦 MANAGE POINT PACKAGES\n\n"
        "👇 Select a package to edit or delete:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def point_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    keyboard = [
        [InlineKeyboardButton("💳 Change UPI", callback_data="pm_change_upi")],
        [InlineKeyboardButton("⏱️ Verification Time", callback_data="pm_change_time")],
        [InlineKeyboardButton("📦 Manage Packages", callback_data="pm_packages")],
        [InlineKeyboardButton("👁️ Current Settings", callback_data="pm_current")],
        [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_back")]
    ]

    await query.edit_message_text(
        "💰 POINT MANAGEMENT\n\n"
        "Manage UPI, verification time and point packages.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def point_package_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    try:
        package_id = int(query.data.split("_")[-1])
    except ValueError:
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT points, amount, active FROM point_packages WHERE id=?",
        (package_id,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        await query.answer("❌ Package not found.", show_alert=True)
        return

    points, amount, active = row

    keyboard = [
        [InlineKeyboardButton("✏️ Change Points", callback_data=f"pm_edit_points_{package_id}")],
        [InlineKeyboardButton("💵 Change Amount", callback_data=f"pm_edit_amount_{package_id}")],
        [InlineKeyboardButton("🗑️ Delete Package", callback_data=f"pm_delete_{package_id}")],
        [InlineKeyboardButton("⬅️ Packages", callback_data="pm_packages")]
    ]

    await query.edit_message_text(
        f"📦 PACKAGE SETTINGS\n\n"
        f"Points: {points}\n"
        f"Amount: ₹{amount}\n\n"
        "Choose what you want to change:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def point_package_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    try:
        package_id = int(query.data.split("_")[-1])
    except ValueError:
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute(
        "UPDATE point_packages SET active=0 WHERE id=?",
        (package_id,)
    )
    conn.commit()
    conn.close()

    await query.answer("✅ Package deleted.")
    await point_packages_menu(update, context)


async def point_management_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    data = query.data

    if data == "pm_change_upi":
        context.user_data["point_admin_action"] = "set_upi"
        await query.edit_message_text(
            "💳 CHANGE UPI\n\n"
            "Send the new UPI ID.\n\n"
            "Example:\n"
            "example@upi"
        )
        return

    if data == "pm_change_time":
        context.user_data["point_admin_action"] = "set_time"
        await query.edit_message_text(
            "⏱️ CHANGE VERIFICATION TIME\n\n"
            "Send maximum verification time in hours.\n\n"
            "Example:\n"
            "12"
        )
        return

    if data.startswith("pm_edit_points_"):
        package_id = int(data.split("_")[-1])
        context.user_data["point_admin_action"] = f"pkg_points_{package_id}"

        await query.edit_message_text(
            "✏️ CHANGE PACKAGE POINTS\n\n"
            "Send the new points value.\n\n"
            "Example: 25"
        )
        return

    if data.startswith("pm_edit_amount_"):
        package_id = int(data.split("_")[-1])
        context.user_data["point_admin_action"] = f"pkg_amount_{package_id}"

        await query.edit_message_text(
            "💵 CHANGE PACKAGE AMOUNT\n\n"
            "Send the new price in ₹.\n\n"
            "Example: 20"
        )
        return

    if data == "pm_add_package":
        context.user_data["point_admin_action"] = "add_package"
        await query.edit_message_text(
            "➕ ADD NEW PACKAGE\n\n"
            "Send Points and Amount separated by a space.\n\n"
            "Example:\n"
            "150 100\n\n"
            "This creates:\n"
            "150 Points → ₹100"
        )
        return


async def point_management_current(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    upi = get_point_setting("buy_upi", "Ankitgupta@fam")
    hours = get_point_setting("verification_hours", "12")
    packages = get_point_packages()

    text = (
        "👁️ CURRENT POINT SETTINGS\n\n"
        f"💳 UPI: {upi}\n"
        f"⏱️ Verification: Up to {hours} hours\n\n"
        "📦 Packages:\n"
    )

    for _, points, amount in packages:
        text += f"• {points} Points → ₹{amount}\n"

    keyboard = [
        [InlineKeyboardButton("⬅️ Point Management", callback_data="admin_point_management")]
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def point_management_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    action = context.user_data.get("point_admin_action")

    if not action:
        return

    value = update.message.text.strip()

    if action == "set_upi":
        if len(value) < 3 or " " in value:
            await update.message.reply_text(
                "❌ Invalid UPI ID.\n\nPlease send a valid UPI ID."
            )
            return

        set_point_setting("buy_upi", value)

        context.user_data.pop("point_admin_action", None)

        await update.message.reply_text(
            f"✅ UPI UPDATED\n\n"
            f"💳 New UPI: {value}\n\n"
            "This will now be shown automatically on Buy Points."
        )
        return

    if action == "set_time":
        try:
            hours = int(value)
            if hours <= 0 or hours > 168:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid time.\n\n"
                "Send hours between 1 and 168.\n\n"
                "Example: 12"
            )
            return

        set_point_setting("verification_hours", hours)
        context.user_data.pop("point_admin_action", None)

        await update.message.reply_text(
            f"✅ VERIFICATION TIME UPDATED\n\n"
            f"⏱️ Maximum time: {hours} hours"
        )
        return

    if action.startswith("pkg_points_"):
        try:
            package_id = int(action.split("_")[-1])
            points = int(value)

            if points <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid points.\n\nSend a positive number."
            )
            return

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()
        cur.execute(
            "UPDATE point_packages SET points=? WHERE id=?",
            (points, package_id)
        )
        conn.commit()
        conn.close()

        context.user_data.pop("point_admin_action", None)

        await update.message.reply_text(
            f"✅ PACKAGE POINTS UPDATED\n\n"
            f"💎 New Points: {points}"
        )
        return

    if action.startswith("pkg_amount_"):
        try:
            package_id = int(action.split("_")[-1])
            amount = int(value)

            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid amount.\n\nSend a positive number."
            )
            return

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()
        cur.execute(
            "UPDATE point_packages SET amount=? WHERE id=?",
            (amount, package_id)
        )
        conn.commit()
        conn.close()

        context.user_data.pop("point_admin_action", None)

        await update.message.reply_text(
            f"✅ PACKAGE AMOUNT UPDATED\n\n"
            f"💵 New Amount: ₹{amount}"
        )
        return

    if action == "add_package":
        parts = value.split()

        if len(parts) != 2:
            await update.message.reply_text(
                "❌ Invalid format.\n\n"
                "Use:\n"
                "POINTS AMOUNT\n\n"
                "Example:\n"
                "150 100"
            )
            return

        try:
            points = int(parts[0])
            amount = int(parts[1])

            if points <= 0 or amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "❌ Points and amount must be positive numbers."
            )
            return

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO point_packages(points,amount,active) VALUES(?,?,1)",
            (points, amount)
        )
        conn.commit()
        conn.close()

        context.user_data.pop("point_admin_action", None)

        await update.message.reply_text(
            f"✅ PACKAGE ADDED\n\n"
            f"📦 {points} Points → ₹{amount}"
        )
        return


async def buy_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if get_feature_setting("buy_points_enabled", "1") != "1":
        await query.edit_message_text(
            "💰 BUY POINTS\n\n"
            "🔴 Buy Points is currently OFF.\n\n"
            "Please try again later.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
            ])
        )
        return

    packages = get_point_packages()
    upi = get_point_setting("buy_upi", "Ankitgupta@fam")

    buttons = []

    for package_id, points, amount in packages:
        buttons.append([
            InlineKeyboardButton(
                f"{points} Points (₹{amount})",
                callback_data=f"buy_pkg_{points}_{amount}"
            )
        ])

    buttons.append([
        InlineKeyboardButton("🏠 Main Menu", callback_data="main")
    ])

    text = (
        "💰 BUY POINTS\n\n"
        "Choose a package below and pay via UPI.\n\n"
        "📦 Packages:\n"
    )

    if packages:
        for _, points, amount in packages:
            text += f"• {points} Points – ₹{amount}\n"
    else:
        text += "• No packages available.\n"

    text += (
        "\n💳 Payment Details (UPI):\n"
        f"UPI ID: {upi}\n"
        "Bot: @Opboylive_bot\n\n"
        "📌 After selecting a package, payment instructions will be shown."
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def buy_submit_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    points = context.user_data.get("buy_points_package")
    amount = context.user_data.get("buy_points_amount")

    if not points or not amount:
        await query.edit_message_text(
            "❌ Package session expired. Please select a package again.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
            ])
        )
        return

    context.user_data["buy_screenshot_pending"] = True

    await query.edit_message_text(
        f"📸 SUBMIT PAYMENT SCREENSHOT\n\n"
        f"📦 Package: {points} Points\n"
        f"💰 Amount: ₹{amount}\n"
        f"🆔 User ID: {query.from_user.id}\n\n"
        "Please send your payment screenshot here."
    )


async def buy_screenshot_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo:
        return

    if not context.user_data.get("buy_screenshot_pending"):
        return

    user = update.effective_user
    points = context.user_data.get("buy_points_package")
    amount = context.user_data.get("buy_points_amount")

    if not points or not amount:
        context.user_data.pop("buy_screenshot_pending", None)
        await update.message.reply_text(
            "❌ Package session expired. Please select Buy Points again."
        )
        return

    file_id = update.message.photo[-1].file_id

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO point_purchase_requests "
        "(user_id, package_points, amount, screenshot_file_id, status) "
        "VALUES (?, ?, ?, ?, 'Pending')",
        (user.id, points, amount, file_id)
    )

    request_id = cur.lastrowid
    conn.commit()
    conn.close()

    context.user_data.pop("buy_screenshot_pending", None)
    context.user_data.pop("buy_points_package", None)
    context.user_data.pop("buy_points_amount", None)

    # Send payment screenshot to admin for verification
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=file_id,
        caption=(
            "💰 POINT PURCHASE REQUEST\n\n"
            f"🆔 Request ID: {request_id}\n"
            f"👤 User ID: {user.id}\n"
            f"📦 Package: {points} Points\n"
            f"💵 Amount: ₹{amount}\n"
            "⏳ Status: Pending"
        ),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Approve",
                    callback_data=f"approve_purchase_{request_id}"
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=f"reject_purchase_{request_id}"
                )
            ]
        ])
    )

    await update.message.reply_text(
        "✅ PAYMENT SCREENSHOT SUBMITTED\n\n"
        f"📦 Package: {points} Points\n"
        f"💰 Amount: ₹{amount}\n"
        f"🆔 Request ID: {request_id}\n\n"
        "⏳ Admin will verify your payment and credit the points.\n"
        f"🕐 Verification may take up to {get_point_setting('verification_hours', '12')} hours.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
        ])
    )


async def buy_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, _, points, amount = query.data.split("_")
    points = int(points)
    amount = int(amount)

    context.user_data["buy_points_package"] = points
    context.user_data["buy_points_amount"] = amount

    text = (
        f"📦 PACKAGE SELECTED: {points} Points\n\n"
        f"💰 Amount: ₹{amount}\n"
        "💳 Pay to UPI: <code>" + get_point_setting("buy_upi", "Ankitgupta@fam") + "</code>\n\n"
        "After payment, send your payment screenshot using the button below.\n\n"
        f"🆔 Your User ID: {query.from_user.id}"
    )

    keyboard = [
        [InlineKeyboardButton("📸 Submit Screenshot", callback_data="buy_submit_screenshot")],
        [InlineKeyboardButton("⬅️ Back to Plans", callback_data="buy_points")]
    ]

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )



async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("VERIFY CLICKED")

    query = update.callback_query
    await query.answer()

    user = query.from_user

    channels = [
        username
        for name, username, url in get_active_channels()
    ]

    print("CHANNEL CHECK START")

    for channel in channels:
        print("Checking:", channel)

        member = await context.bot.get_chat_member(
            chat_id=channel,
            user_id=user.id
        )

        if member.status in ["left", "kicked"]:
            join_buttons = [
                [InlineKeyboardButton("📢 Join Main Channel", url="https://t.me/opboyLive")],
                [InlineKeyboardButton("📢 Join Deals Channel", url="https://t.me/opboydeals")],
                [InlineKeyboardButton("💬 Join Chat", url="https://t.me/OpBoyLive_Chat")],
                [InlineKeyboardButton("✅ Verify", callback_data="verify")]
            ]

            await query.edit_message_text(
                "❌ Please join all channels first!\n\n"
                "1️⃣ Join Main Channel\n"
                "2️⃣ Join Deals Channel\n"
                "3️⃣ Join Chat\n\n"
                "👇 After joining all channels, tap Verify again.",
                reply_markup=InlineKeyboardMarkup(join_buttons)
            )
            return

    print("ALL CHANNELS VERIFIED")

    await human_verify(update, context)



async def addpoints(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Use: /addpoints user_id points"
        )
        return

    user_id = int(context.args[0])
    amount = int(context.args[1])

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "UPDATE users SET points = points + ? WHERE user_id=?",
        (amount, user_id)
    )

    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Added {amount} points to {user_id}"
    )
async def createpromo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if len(context.args) != 3:
        await update.message.reply_text(
            "Use: /createpromo CODE POINTS MAXUSES"
        )
        return

    code = context.args[0].upper()
    points = int(context.args[1])
    max_uses = int(context.args[2])

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    try:
        cur.execute(
            "INSERT INTO promo_codes(code, points, max_uses) VALUES(?,?,?)",
            (code, points, max_uses)
        )
        conn.commit()

        await update.message.reply_text(
            f"✅ Promo {code} created."
        )

    except sqlite3.IntegrityError:
        await update.message.reply_text(
            "❌ Promo code already exists."
        )

    conn.close()
async def listpromo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT code, points, used_count, max_uses FROM promo_codes"
    )

    promos = cur.fetchall()
    conn.close()

    if not promos:
        await update.message.reply_text(
            "❌ No promo codes found."
        )
        return

    text = "🎟️ Active Promo Codes\n\n"

    for code, points, used, maximum in promos:
        text += (
            f"🔹 {code}\n"
            f"💎 {points} Points\n"
            f"👥 Uses: {used}/{maximum}\n\n"
        )

    await update.message.reply_text(text)
async def deletepromo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if len(context.args) != 1:
        await update.message.reply_text(
            "Use: /deletepromo CODE"
        )
        return

    code = context.args[0].upper()

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM promo_codes WHERE code=?",
        (code,)
    )

    conn.commit()

    if cur.rowcount == 0:
        await update.message.reply_text(
            "❌ Promo code not found."
        )
    else:
        await update.message.reply_text(
            f"✅ Promo {code} deleted."
        )

    conn.close()

async def reward_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    if not is_admin(query.from_user.id):
        return
    context.user_data["reward_action"] = "add"
    await query.edit_message_text(
        "➕ ADD PRODUCT\n\n"
        "Format:\nProduct Name | Price | Stock\n\n"
        "Example:\nMyntra 5% Off Coupon | 7 | 5\n\n"
        "❌ Cancel: /cancel"
    )


async def reward_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    context.user_data["reward_action"] = "edit"
    await query.edit_message_text(
        "✏️ EDIT PRODUCT\n\n"
        "Format:\nOld Name | New Name | Price | Stock\n\n"
        "Example:\nMyntra 5% Off Coupon | Myntra 5% Off Coupon | 8 | 10\n\n"
        "❌ Cancel: /cancel"
    )


async def reward_delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    context.user_data["reward_action"] = "delete"
    await query.edit_message_text(
        "🗑️ DELETE REWARD\n\n"
        "Exact reward name bhejo.\n\n"
        "Example:\nDomino's Gift Card ₹100\n\n"
        "❌ Cancel: /cancel"
    )


async def reward_reorder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, sort_order FROM rewards "
        "WHERE mode='paid' ORDER BY sort_order, id"
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await query.edit_message_text(
            "🔀 REORDER PRODUCTS\n\n❌ No paid products found."
        )
        return

    keyboard = []

    for product_id, name, sort_order in rows:
        keyboard.append([
            InlineKeyboardButton(
                f"📍 {sort_order}. {name}",
                callback_data=f"reorder_view_{product_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Product Management",
            callback_data="admin_rewards"
        )
    ])

    await query.edit_message_text(
        "🔀 REORDER PRODUCTS\n\n"
        "Select a product to move it up or down:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def reorder_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    try:
        reward_id = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT id, name, sort_order FROM rewards "
        "WHERE id=? AND mode='paid'",
        (reward_id,)
    )
    row = cur.fetchone()

    if not row:
        conn.close()
        await query.answer("❌ Product not found.", show_alert=True)
        return

    cur.execute(
        "SELECT id, name, sort_order FROM rewards "
        "WHERE mode='paid' ORDER BY sort_order, id"
    )
    rows = cur.fetchall()
    conn.close()

    position = next(
        (i for i, item in enumerate(rows) if item[0] == reward_id),
        None
    )

    if position is None:
        return

    product_id, name, sort_order = row

    keyboard = []

    if position > 0:
        keyboard.append([
            InlineKeyboardButton(
                "⬆️ Move Up",
                callback_data=f"reorder_up_{product_id}"
            )
        ])

    if position < len(rows) - 1:
        keyboard.append([
            InlineKeyboardButton(
                "⬇️ Move Down",
                callback_data=f"reorder_down_{product_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "🔙 Back to Products",
            callback_data="reward_reorder"
        )
    ])

    await query.edit_message_text(
        f"🔀 REORDER PRODUCT\n\n"
        f"📍 Position: {position + 1}\n"
        f"🛍️ {name}\n\n"
        "Choose a direction:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def reorder_move_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    parts = query.data.split("_")
    if len(parts) != 3:
        return

    direction = parts[1]

    try:
        reward_id = int(parts[2])
    except ValueError:
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT id, name, sort_order FROM rewards "
        "WHERE id=? AND mode='paid'",
        (reward_id,)
    )
    current = cur.fetchone()

    if not current:
        conn.close()
        return

    cur.execute(
        "SELECT id, name, sort_order FROM rewards "
        "WHERE mode='paid' ORDER BY sort_order, id"
    )
    rows = cur.fetchall()

    position = next(
        (i for i, row in enumerate(rows) if row[0] == reward_id),
        None
    )

    if position is None:
        conn.close()
        return

    target_position = position - 1 if direction == "up" else position + 1

    if target_position < 0 or target_position >= len(rows):
        conn.close()
        await query.answer("❌ Cannot move further.", show_alert=True)
        return

    current_id, current_name, current_order = rows[position]
    target_id, target_name, target_order = rows[target_position]

    cur.execute(
        "UPDATE rewards SET sort_order=? WHERE id=?",
        (target_order, current_id)
    )
    cur.execute(
        "UPDATE rewards SET sort_order=? WHERE id=?",
        (current_order, target_id)
    )

    conn.commit()
    conn.close()

    await query.edit_message_text(
        f"🔀 REORDER PRODUCT\n\n"
        f"📍 Position: {target_position + 1}\n"
        f"🛍️ {current_name}\n\n"
        "Choose a direction:",
        reply_markup=InlineKeyboardMarkup([
            *(
                [[InlineKeyboardButton(
                    "⬆️ Move Up",
                    callback_data=f"reorder_up_{current_id}"
                )]]
                if target_position > 0 else []
            ),
            *(
                [[InlineKeyboardButton(
                    "⬇️ Move Down",
                    callback_data=f"reorder_down_{current_id}"
                )]]
                if target_position < len(rows) - 1 else []
            ),
            [InlineKeyboardButton(
                "🔙 Back to Products",
                callback_data="reward_reorder"
            )]
        ])
    )


async def reward_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT id, name, price, stock FROM rewards WHERE mode='paid' ORDER BY id")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        text = "📋 PRODUCT LIST\n\n❌ No products found."
    else:
        text = "📋 PRODUCT LIST\n\n"
        for product_id, name, price, stock in rows:
            text += (
                f"🆔 {product_id}\n"
                f"🛍️ {name}\n"
                f"💰 Price: ₹{float(price):g} / code\n"
                f"📦 Stock: {stock}\n"
                f"━━━━━━━━━━━━━━\n"
            )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "⬅️ Product Management",
                callback_data="admin_rewards"
            )]
        ])
    )


async def reward_control_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    action = context.user_data.get("reward_action")
    if not action:
        return

    text = update.message.text.strip()

    if text == "/cancel":
        context.user_data.pop("reward_action", None)
        await update.message.reply_text("❌ Reward action cancelled.")
        return

    parts = [x.strip() for x in text.split("|")]

    if action == "add":
        if len(parts) != 3:
            await update.message.reply_text(
                "❌ Format:\nProduct Name | Price | Stock\n\n"
                "Example:\nMyntra 5% Off Coupon | 7 | 5"
            )
            return

        name = parts[0]

        try:
            price = float(parts[1])
            stock = int(parts[2])
        except ValueError:
            await update.message.reply_text(
                "❌ Price aur Stock numbers hone chahiye."
            )
            return

        if price <= 0 or stock < 0:
            await update.message.reply_text(
                "❌ Price 0 se zyada aur Stock 0 ya usse zyada hona chahiye."
            )
            return

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute(
            "SELECT id FROM rewards WHERE name=?",
            (name,)
        )

        if cur.fetchone():
            conn.close()
            await update.message.reply_text(
                "❌ Product already exists."
            )
            return

        cur.execute(
            """
            INSERT INTO rewards(name, points, stock, mode, price)
            VALUES(?,?,?,?,?)
            """,
            (name, 0, stock, "paid", price)
        )

        conn.commit()
        conn.close()

        context.user_data.pop("reward_action", None)

        await update.message.reply_text(
            "✅ PRODUCT ADDED\n\n"
            f"🛍️ {name}\n"
            f"💰 Price: ₹{price:g}\n"
            f"📦 Stock: {stock}"
        )
        return

    elif action == "edit":
        if len(parts) != 4:
            await update.message.reply_text(
                "❌ Format:\nOld Name | New Name | Price | Stock\n\n"
                "Example:\nMyntra 5% Off Coupon | Myntra 5% Off Coupon | 8 | 10"
            )
            return

        old_name, new_name = parts[0], parts[1]

        try:
            price = float(parts[2])
            stock = int(parts[3])
        except ValueError:
            await update.message.reply_text(
                "❌ Price aur Stock numbers hone chahiye."
            )
            return

        if price <= 0 or stock < 0:
            await update.message.reply_text(
                "❌ Price 0 se zyada aur Stock 0 ya usse zyada hona chahiye."
            )
            return

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE rewards
            SET name=?, points=0, stock=?, mode='paid', price=?
            WHERE name=?
            """,
            (new_name, stock, price, old_name)
        )

        changed = cur.rowcount

        conn.commit()
        conn.close()

        if not changed:
            await update.message.reply_text(
                "❌ Product not found."
            )
            return

        context.user_data.pop("reward_action", None)

        await update.message.reply_text(
            "✅ PRODUCT UPDATED\n\n"
            f"🛍️ {new_name}\n"
            f"💰 Price: ₹{price:g}\n"
            f"📦 Stock: {stock}"
        )
        return

    elif action == "delete":
        if len(parts) != 1:
            await update.message.reply_text("❌ Exact reward name bhejo.")
            return

        name = parts[0]

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()
        cur.execute("DELETE FROM rewards WHERE name=?", (name,))
        deleted = cur.rowcount
        conn.commit()
        conn.close()

        if not deleted:
            await update.message.reply_text("❌ Reward not found.")
            return

        context.user_data.pop("reward_action", None)

        await update.message.reply_text(
            f"🗑️ PRODUCT DELETED\n\n🎁 {name}"
        )


async def addreward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if len(context.args) < 5:
        await update.message.reply_text(
            "Use:\n/addreward Reward Name POINTS STOCK MODE PRICE\n\n"
            "Example:\n/addreward Domino Gift Card 60 10 points 0"
        )
        return

    try:
        price = float(context.args[-1])
        mode = context.args[-2].lower()
        stock = int(context.args[-3])
        points = int(context.args[-4])
    except ValueError:
        await update.message.reply_text("❌ Points, Stock aur Price numbers hone chahiye.")
        return

    if mode not in ("points", "paid"):
        await update.message.reply_text("❌ Mode must be points or paid.")
        return

    name = " ".join(context.args[:-4])

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute("SELECT id FROM rewards WHERE name=?", (name,))
    if cur.fetchone():
        conn.close()
        await update.message.reply_text("❌ Reward already exists.")
        return

    cur.execute(
          "INSERT INTO rewards(name, points, stock, mode, price) VALUES(?,?,?,?,?)",
          (name, points, stock, mode, price)
      )

    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Reward Added\n\n"
        f"🎁 {name}\n"
        f"💎 Points: {points}\n"
          f"📦 Stock: {stock}\n"
          f"⚙️ Mode: {mode}\n"
          f"💰 Price: ₹{price:g}"
    )


async def editreward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if len(context.args) < 5:
        await update.message.reply_text(
            "Use:\n/editreward Reward Name POINTS STOCK MODE PRICE"
        )
        return

    try:
        price = float(context.args[-1])
        mode = context.args[-2].lower()
        stock = int(context.args[-3])
        points = int(context.args[-4])
    except ValueError:
        await update.message.reply_text("❌ Points, Stock aur Price numbers hone chahiye.")
        return

    if mode not in ("points", "paid"):
        await update.message.reply_text("❌ Mode must be points or paid.")
        return

    name = " ".join(context.args[:-4])

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "UPDATE rewards SET points=?, stock=?, mode=?, price=? WHERE name=?",
        (points, stock, mode, price, name)
    )

    changed = cur.rowcount
    conn.commit()
    conn.close()

    if not changed:
        await update.message.reply_text("❌ Reward not found.")
        return

    await update.message.reply_text(
        f"✅ Reward Updated\n\n"
        f"🎁 {name}\n"
        f"💎 Points: {points}\n"
        f"📦 Stock: {stock}"
    )


async def delreward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Use:\n/delreward Reward Name"
        )
        return

    name = " ".join(context.args)

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute("DELETE FROM rewards WHERE name=?", (name,))

    deleted = cur.rowcount
    conn.commit()
    conn.close()

    if not deleted:
        await update.message.reply_text("❌ Reward not found.")
        return

    await update.message.reply_text(
        f"🗑️ Reward Deleted\n\n🎁 {name}"
    )


async def rewardlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT id, name, points, stock FROM rewards ORDER BY id"
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("❌ No rewards found.")
        return

    text = "🎁 REWARD MANAGEMENT\n\n"

    for reward_id, name, points, stock in rows:
        text += (
            f"🆔 {reward_id}\n"
            f"🎁 {name}\n"
            f"💎 {points} Points\n"
            f"📦 Stock: {stock}\n"
            f"━━━━━━━━━━━━━━\n"
        )

    await update.message.reply_text(text)


async def addcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Use: /addcode Reward Name Code"
        )
        return

    code = context.args[-1]
    reward_name = " ".join(context.args[:-1])

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO reward_codes(reward_name, code) VALUES(?,?)",
        (reward_name, code)
    )

    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Code Added\n\n🎁 Reward: {reward_name}\n🔑 Code: {code}"
    )
async def setstock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Use:\n/setstock Reward Name STOCK\n\n"
            "Example:\n/setstock Domino's Gift Card ₹100 20"
        )
        return

    try:
        stock = int(context.args[-1])
    except ValueError:
        await update.message.reply_text("❌ Stock must be a number.")
        return

    name = " ".join(context.args[:-1])

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "UPDATE rewards SET stock=? WHERE name=?",
        (stock, name)
    )

    changed = cur.rowcount
    conn.commit()
    conn.close()

    if not changed:
        await update.message.reply_text("❌ Reward not found.")
        return

    await update.message.reply_text(
        f"✅ Stock Updated\n\n"
        f"🎁 {name}\n"
        f"📦 New Stock: {stock}"
    )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "📢 BROADCAST\n\n"
            "Use:\n"
            "/broadcast Your message here"
        )
        return

    message = " ".join(context.args)

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE blocked=0")
    users = cur.fetchall()
    conn.close()

    await update.message.reply_text(
        f"📢 Broadcast started...\n\n"
        f"👥 Recipients: {len(users)}"
    )

    success = 0
    failed = 0

    for (user_id,) in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=message
            )
            success += 1
        except Exception as e:
            failed += 1
            print(f"⚠️ Broadcast failed for {user_id}: {e}")

    await update.message.reply_text(
        "📢 BROADCAST COMPLETED\n\n"
        f"👥 Total: {len(users)}\n"
        f"✅ Sent: {success}\n"
        f"❌ Failed: {failed}"
    )

async def requests_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id, reward_name, points FROM claim_requests WHERE status='Pending'"
    )

    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(
            "✅ No pending requests."
        )
        return

    text = "📋 Pending Requests\n\n"

    for i, row in enumerate(rows, start=1):
        text += (
            f"{i}) 🆔 ID: {row[0]}\n"
            f"🎁 Reward: {row[1]}\n"
            f"💎 Points: {row[2]}\n\n"
        )

    await update.message.reply_text(text)
async def users_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]

    conn.close()

    await update.message.reply_text(
        f"👥 Total Users: {total}"
    )
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM rewards")
    total_rewards = cur.fetchone()[0]

    try:
        cur.execute("SELECT COUNT(*) FROM claim_history")
        total_claims = cur.fetchone()[0]

        cur.execute("SELECT SUM(points) FROM claim_history")
        total_points = cur.fetchone()[0] or 0
    except sqlite3.OperationalError:
        total_claims = 0
        total_points = 0

    conn.close()

    await update.message.reply_text(
        f"📊 Bot Stats\n\n"
        f"👥 Users: {total_users}\n"
        f"🎁 Rewards: {total_rewards}\n"
        f"📜 Claims: {total_claims}\n"
        f"💎 Points Used: {total_points}"
    )

async def confirm_claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    print("CONFIRM PRESSED:", query.data)

    reward_name = query.data.replace("confirm_", "", 1)

    await query.edit_message_text(
        f"⚠️ Confirm Claim\n\n"
        f"🎁 Reward: {reward_name}\n\n"
        f"Are you sure you want to claim this reward?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Confirm Claim",
                    callback_data=f"reward_{reward_name}"
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Cancel",
                    callback_data="catalog"
                )
            ]
        ])
    )
async def claim_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if get_feature_setting("claim_reward_enabled", "1") != "1":
        await query.edit_message_text(
            "🎁 CLAIM REWARD\n\n"
            "🔴 Claim Reward is currently OFF.\n\n"
            "Please try again later.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
            ])
        )
        return

    print("CLAIM BUTTON PRESSED:", query.data)

    reward_name = query.data.replace("reward_", "", 1)
    user = query.from_user

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")

    cur.execute(
        "SELECT COUNT(*) FROM claim_requests WHERE user_id=? AND claim_time LIKE ?",
        (user.id, today + "%")
    )

    daily_claims = cur.fetchone()[0]

    # Admin has unlimited claims
    if user.id != ADMIN_ID:
        try:
            claim_limit = int(get_point_setting("daily_claim_limit", "5"))
        except (ValueError, TypeError):
            claim_limit = 5

        # Limit 0 means unlimited for everyone
        if claim_limit > 0 and daily_claims >= claim_limit:
            conn.close()
            await query.edit_message_text(
                "🚫 Daily Claim Limit Reached\n\n"
                f"You have reached your daily limit of {claim_limit} claims.\n\n"
                "⏳ Come back tomorrow and try again."
            )
            return

    cur.execute(
        "SELECT points, stock FROM rewards WHERE name=?",
        (reward_name,)
    )
    reward = cur.fetchone()

    cur.execute(
        "SELECT points FROM users WHERE user_id=?",
        (user.id,)
    )
    user_data = cur.fetchone()

    if not reward:
        conn.close()
        await query.edit_message_text("❌ Reward not found")
        return

    points, stock = reward
    user_points = user_data[0] if user_data else 0

    if user_points < points:
        conn.close()
        await query.edit_message_text(
            f"❌ You need {points} points.\n💰 Balance: {user_points} points"
        )
        return

    if stock <= 0:
        conn.close()
        await query.edit_message_text("❌ Reward out of stock")
        return

    cur.execute(
        "INSERT INTO claim_requests(user_id, reward_name, points, status, claim_time) VALUES(?,?,?,?,?)",
        (
            user.id,
            reward_name,
            points,
            "Pending",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )

    conn.commit()
    conn.close()

    await query.edit_message_text(
        f"🎉 REWARD REQUEST SUBMITTED 🎉\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"🎁 Reward: {reward_name}\n"
        f"💎 Points: -{points}\n\n"
        f"⏳ Status: Pending Approval\n\n"
        f"👨‍💻 Admin will approve shortly.\n"
        f"⚡ Maximum time: 3 hours\n\n"
        f"🙏 Thanks for using OpBoy Live Bot!"
    )

    await context.bot.send_message(
        chat_id=get_approval_admin(),
        text=(
            "🔔 NEW REWARD REQUEST\n\n"
            f"👤 User: @{user.username}\n"
            f"🆔 ID: {user.id}\n\n"
            f"🎁 Reward: {reward_name}\n"
            f"💎 Points: {points}\n\n"
            "⏳ Status: Pending"
        ),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Approve",
                    callback_data=f"approve_{user.id}_{reward_name}"
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=f"reject_{user.id}_{reward_name}"
                )
            ]
        ])
    )



async def send_shop_screen(bot, chat_id, reply_keyboard=None):
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT id, name, price, stock FROM rewards "
        "WHERE mode='paid' ORDER BY sort_order, id"
    )
    products = cur.fetchall()
    conn.close()

    buttons = []
    available_count = 0
    out_of_stock_count = 0

    for rid, name, price, stock in products:
        if stock > 0:
            available_count += 1
        else:
            out_of_stock_count += 1
        emoji = "🛍️"
        lname = name.lower()

        if "myntra" in lname:
            emoji = "👗"
        elif "netflix" in lname:
            emoji = "🎬"
        elif "bigbasket" in lname:
            emoji = "🛒"
        elif "lenskart" in lname:
            emoji = "👓"
        elif "cinepolis" in lname:
            emoji = "🎥"
        elif "kfc" in lname:
            emoji = "🍗"
        elif "domino" in lname:
            emoji = "🍕"
        elif "spotify" in lname:
            emoji = "🎵"

        label = (
            f"{emoji} {name} .₹{price:g}. Stock {stock}"
            if stock > 0
            else f"{emoji} {name} OUT OF STOCK"
        )

        buttons.append([
            InlineKeyboardButton(
                label,
                callback_data=f"shop_product_{rid}"
            )
        ])

    if buttons:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "🛍️ OPx SHOP\n"
                "━━━━━━━━━━━━━━━━\n\n"
                "✨ COUPON STORE ✨\n\n"
                f"📦 Products Available: {available_count}\n"
                f"⚠️ Out of Stock: {out_of_stock_count}\n\n"
                "👇 Choose your product below"
            ),
            reply_markup=InlineKeyboardMarkup(buttons)
        )


async def user_menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    if text == "🛍️ Browse Product":
        await send_shop_screen(
            context.bot,
            update.effective_user.id
        )
        return


    if text == "📦 My Orders":
        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute(
            """
            SELECT order_id, reward_name, quantity, total, status, order_time, delivered_codes
            FROM paid_orders
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT 10
            """,
            (update.effective_user.id,)
        )

        orders = cur.fetchall()
        conn.close()

        if not orders:
            await update.message.reply_text(
                "📦 MY ORDERS\n\n"
                "You have no orders yet."
            )
            return

        text_out = "📦 MY ORDERS\n\n"

        for order_id, name, quantity, total, status, order_time, delivered_codes in orders:
            text_out += (
                f"🆔 {order_id}\n"
                f"🛍️ {name}\n"
                f"📦 Quantity: {quantity}\n"
                f"💰 Amount: ₹{float(total):g}\n"
                f"📌 Status: {status}\n"
                f"🕒 {order_time}\n"
                "━━━━━━━━━━━━━━━━\n"
            )

        await update.message.reply_text(text_out)
        return

    if text == "📞 Support":
        await update.message.reply_text(
            "📞 Support\n\n"
            "Need help? Contact us here:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📞 Contact Support",
                        url="https://t.me/BeyondGravityX"
                    )
                ]
            ])
        )
        return

    if text == "ℹ️ How It Works":
        await update.message.reply_text(
            "ℹ️ HOW TO BUY\n\n"
            "1. Browse product\n"
            "2. Choose quantity\n"
            "3. Pay total amount\n"
            "4. Send UTR + screenshot\n"
            "5. Admin approves\n"
            "6. Codes are delivered automatically."
        )
        return



async def help_center(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    buttons = [
        [InlineKeyboardButton("📖 How to Buy", callback_data="help_how_to_buy")],
        [InlineKeyboardButton("📋 My Orders", callback_data="help_my_orders")],
        [InlineKeyboardButton("📞 Contact Support", url="https://t.me/BeyondGravityX")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
    ]

    await query.edit_message_text(
        "🆘 HELP CENTER\n\n"
        "Choose an option:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def help_how_to_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "📖 HOW TO BUY\n\n"
        "1️⃣ Browse Product\n"
        "2️⃣ Select quantity\n"
        "3️⃣ Pay the total amount\n"
        "4️⃣ Tap 💳 I Have Paid\n"
        "5️⃣ Send your 12-digit UTR\n"
        "6️⃣ Send payment screenshot\n"
        "7️⃣ Admin verifies your payment\n"
        "8️⃣ Coupon code(s) are delivered automatically.\n\n"
        "⏳ Payment verification may take up to 3 hours.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Help Center", callback_data="help")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
        ])
    )


async def help_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "SELECT order_id, reward_name, quantity, total, status, order_time "
        "FROM paid_orders WHERE user_id=? ORDER BY id DESC LIMIT 10",
        (user_id,)
    )
    orders = cur.fetchall()
    conn.close()

    if not orders:
        text = (
            "📋 MY ORDERS\n\n"
            "You have no orders yet.\n\n"
            "🛍️ Browse products and place your first order."
        )
    else:
        text = "📋 MY ORDERS\n━━━━━━━━━━━━━━\n\n"

        for order_id, reward_name, quantity, total, status, order_time in orders:
            text += (
                f"🆔 {order_id}\n"
                f"🛍️ {reward_name}\n"
                f"📦 Quantity: {quantity}\n"
                f"💰 Amount: ₹{float(total):g}\n"
                f"📌 Status: {status}\n"
                f"🕒 {order_time}\n\n"
            )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Help Center", callback_data="help")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
        ])
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT id, name, price, stock FROM rewards WHERE mode='paid' ORDER BY id"
    )
    shop_rewards = cur.fetchall()

    conn.close()

    shop_buttons = []
    for rid, name, price, stock in shop_rewards:
        if stock > 0:
            label = f"{name} .₹{price:g}. Stock {stock}"
        else:
            label = f"{name} OUT OF STOCK"

    shop_buttons.append([
            InlineKeyboardButton(
                label,
                callback_data=f"shop_product_{rid}"
            )
        ])

    await query.edit_message_text(
        "Welcome to OPx Shop 🙏🏻\n\n"
        "📊 Limited Stock Available! 📊\n\n"
        "Select Product:",
        reply_markup=InlineKeyboardMarkup(shop_buttons)
    )

async def rewards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT id, name, price, stock FROM rewards WHERE mode='paid' ORDER BY id"
    )
    products = cur.fetchall()
    conn.close()

    buttons = []

    for rid, name, price, stock in products:
        emoji = "🛍️"
        lname = name.lower()

        if "myntra" in lname:
            emoji = "👗"
        elif "netflix" in lname:
            emoji = "🎬"
        elif "bigbasket" in lname:
            emoji = "🛒"
        elif "lenskart" in lname:
            emoji = "👓"
        elif "cinepolis" in lname:
            emoji = "🎥"
        elif "kfc" in lname:
            emoji = "🍗"
        elif "domino" in lname:
            emoji = "🍕"
        elif "spotify" in lname:
            emoji = "🎵"

        if stock > 0:
            label = f"{emoji} {name} .₹{price:g}. Stock {stock}"
        else:
            label = f"{emoji} {name} OUT OF STOCK"

        buttons.append([
            InlineKeyboardButton(
                label,
                callback_data=f"shop_product_{rid}"
            )
        ])

    await query.edit_message_text(
        "Welcome to OPx Shop 🙏🏻\n\n"
        "📊 Limited Stock Available! 📊\n\n"
        "👇 Select a product from the buttons below:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def shop_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        reward_id = int(query.data.replace("shop_product_", ""))
    except (ValueError, AttributeError):
        await query.edit_message_text("❌ Invalid product.")
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT name, price, stock FROM rewards WHERE id=?",
        (reward_id,)
    )
    product = cur.fetchone()
    conn.close()

    if not product:
        await query.edit_message_text("❌ Product not found.")
        return

    name, price, stock = product
    price = float(price)

    max_buy = min(5, stock)

    if stock <= 0:
        await query.edit_message_text(
            f"🛍️ {name}\n\n"
            "📦 Available Stock: 0 code(s)\n\n"
            "❌ Currently Out of Stock.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Products", callback_data="shop")]
            ])
        )
        return

    buttons = []
    row = []

    for quantity in range(1, max_buy + 1):
        total = price * quantity

        row.append(
            InlineKeyboardButton(
                f"{quantity}️⃣ {quantity} Code{'s' if quantity != 1 else ''} — ₹{total:g}",
                callback_data=f"shop_qty_{reward_id}_{quantity}"
            )
        )

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("🔙 Back to Products", callback_data="shop")
    ])

    await query.edit_message_text(
        f"🛍️ {name}\n\n"
        f"📦 Available Stock: {stock} code(s)\n\n"
        f"💰 Price: ₹{price:g} / code\n\n"
        f"🔢 Maximum Buy: {max_buy}\n\n"
        "🛒 Select Quantity:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def shop_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        _, _, reward_id, quantity = query.data.split("_")
        reward_id = int(reward_id)
        quantity = int(quantity)
    except (ValueError, AttributeError):
        await query.edit_message_text("❌ Invalid quantity.")
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT name, price, stock FROM rewards WHERE id=?",
        (reward_id,)
    )
    product = cur.fetchone()

    if not product:
        conn.close()
        await query.edit_message_text("❌ Product not found.")
        return

    name, price, stock = product
    price = float(price)

    if stock <= 0:
        conn.close()
        await query.edit_message_text("❌ Product is out of stock.")
        return

    if quantity < 1 or quantity > 5 or quantity > stock:
        conn.close()
        await query.edit_message_text(
            "❌ Invalid quantity or insufficient stock."
        )
        return

    cur.execute(
        "SELECT value FROM shop_settings WHERE key=?",
        ("shop_upi",)
    )
    row = cur.fetchone()
    upi = row[0] if row and row[0] else "Not Set"

    cur.execute(
        "SELECT value FROM shop_settings WHERE key=?",
        ("shop_qr",)
    )
    row = cur.fetchone()
    qr_file_id = row[0] if row and row[0] else ""

    total = price * quantity

    cur.execute("""
        SELECT MAX(CAST(SUBSTR(order_id, 5) AS INTEGER))
        FROM paid_orders
        WHERE order_id LIKE 'OPX-%'
    """)
    row = cur.fetchone()
    last_order_number = row[0] if row and row[0] else 1000
    order_id = f"OPX-{last_order_number + 1}"

    order_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute(
        """
        INSERT INTO paid_orders(
            order_id,
            user_id,
            reward_id,
            reward_name,
            quantity,
            price,
            total,
            status,
            order_time
        )
        VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (
            order_id,
            query.from_user.id,
            reward_id,
            name,
            quantity,
            price,
            total,
            "Pending",
            order_time
        )
    )

    conn.commit()
    conn.close()

    context.user_data["paid_order"] = {
        "order_id": order_id,
        "reward_id": reward_id,
        "reward_name": name,
        "quantity": quantity,
        "price": price,
        "total": total
    }

    context.user_data["paid_utr_pending"] = False
    context.user_data["paid_screenshot_pending"] = False

    payment_text = (
        f"🛍️ Order Payment\n\n"
        f"You Selected: {name} "
        f"({quantity} code{'s' if quantity != 1 else ''})\n\n"
        f"💳 Pay ₹{total:g}\n\n"
        f"Price per Code: ₹{price:g}\n"
        f"📊 Available Stock: {stock}\n\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"🆔 Order ID: `{order_id}`\n\n"
        f"💳 UPI ID: `{upi}`\n"
        f"🕒 Time: {datetime.now().strftime('%d %b %Y, %I:%M %p')}\n"
        f"📞 Support: @beyondgravityX\n\n"
        f"⚠️ Payment request valid for 10 mins, so pay first!\n\n"
        f"Scan the QR above or pay to UPI ID.\n\n"
        f"After payment, press the button below."
    )

    # PAYMENT BUTTONS
    payment_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💳 I Have Paid",
                callback_data=f"paid_done_{order_id}"
            )
        ]
    ])

    payment_message = None

    if qr_file_id:
        try:
            await query.message.delete()
        except Exception:
            pass

        payment_message = await context.bot.send_photo(
            chat_id=query.from_user.id,
            photo=qr_file_id,
            caption=payment_text,
            reply_markup=payment_markup
        )
    else:
        payment_message = await query.edit_message_text(
            payment_text,
            reply_markup=payment_markup
        )

    # Auto-cancel after 10 minutes if user has not confirmed payment.
    if payment_message:
        old_task = context.user_data.pop("paid_expiry_task", None)
        if old_task:
            try:
                old_task.cancel()
            except Exception:
                pass

        context.user_data["paid_expiry_task"] = asyncio.create_task(
            expire_paid_order(
                context,
                order_id,
                query.from_user.id,
                payment_message.message_id
            )
        )



async def expire_paid_order(
    context,
    order_id,
    user_id,
    message_id
):
    # Wait exactly 10 minutes from payment message.
    await asyncio.sleep(600)

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        """
        SELECT status
        FROM paid_orders
        WHERE order_id=? AND user_id=?
        """,
        (order_id, user_id)
    )

    row = cur.fetchone()

    if not row:
        conn.close()
        return

    # Screenshot submission permanently stops the timer.
    if row[0] not in ("Pending", "UTR Submitted"):
        conn.close()

        # Cleanup only if this is still the same active order.
        if context.user_data.get("paid_order", {}).get("order_id") == order_id:
            context.user_data.pop("paid_order", None)
            context.user_data.pop("paid_utr_pending", None)
            context.user_data.pop("paid_screenshot_pending", None)
            context.user_data.pop("paid_expiry_task", None)

        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute(
        """
        UPDATE paid_orders
        SET status=?,
            rejection_reason=?,
            rejected_at=?
        WHERE order_id=?
          AND user_id=?
          AND status IN ('Pending', 'UTR Submitted')
        """,
        (
            "Cancelled",
            "Payment timeout",
            now,
            order_id,
            user_id
        )
    )

    conn.commit()
    conn.close()

    # Stop and clear all payment-input state.
    if context.user_data.get("paid_order", {}).get("order_id") == order_id:
        context.user_data.pop("paid_order", None)
        context.user_data.pop("paid_utr_pending", None)
        context.user_data.pop("paid_screenshot_pending", None)
        context.user_data.pop("paid_expiry_task", None)

    # Delete old payment QR/payment message.
    try:
        await context.bot.delete_message(
            chat_id=user_id,
            message_id=message_id
        )
    except Exception as e:
        print(f"⚠️ Payment message delete failed: {e}")

    # Tell user that the order expired.
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "❌ ORDER CANCELLED\n\n"
                f"🆔 Order ID: `{order_id}`\n\n"
                "⏰ Your payment window has expired.\n\n"
                "💸 If any amount is deducted, it will be refunded.\n\n"
                "📞 Contact Support for refund."
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"⚠️ Cancellation message failed: {e}")

async def paid_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🔥 PAID_DONE CALLBACK RECEIVED")
    print(
        "🔥 CALLBACK DATA:",
        update.callback_query.data if update.callback_query else None
    )

    query = update.callback_query
    await query.answer()

    order = context.user_data.get("paid_order")

    if not order:
        await query.answer(
            "❌ No active order found.",
            show_alert=True
        )
        return

    order_id = order["order_id"]

    if query.data != f"paid_done_{order_id}":
        await query.answer(
            "❌ Invalid order.",
            show_alert=True
        )
        return

    # Make sure the 10-minute expiry has not cancelled the order.
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        """
        SELECT status
        FROM paid_orders
        WHERE order_id=? AND user_id=?
        """,
        (order_id, query.from_user.id)
    )

    row = cur.fetchone()
    conn.close()

    if not row:
        await query.answer(
            "❌ Order not found.",
            show_alert=True
        )
        return

    if row[0] == "Cancelled":
        await query.answer(
            "⏰ This order has expired.",
            show_alert=True
        )
        return

    if row[0] != "Pending":
        await query.answer(
            f"⚠️ Order is already {row[0]}.",
            show_alert=True
        )
        return

    # Delete the original payment message immediately.
    # The 10-minute expiry timer continues until screenshot submission.
    try:
        await query.message.delete()
    except Exception as e:
        print(f"⚠️ Payment message delete failed: {e}")

    context.user_data["paid_utr_pending"] = True
    context.user_data["paid_screenshot_pending"] = False

    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=(
            "💳 Payment Confirmation\n\n"
            f"🆔 Order ID: `{order_id}`\n"
            f"💰 Amount: ₹{order['total']:g}\n\n"
            "🔢 Please send your 12-digit UTR here."
        ),
        parse_mode="Markdown"
    )

    print("🔥 PAID_DONE COMPLETED SUCCESSFULLY")


async def paid_order_utr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    if not context.user_data.get("paid_utr_pending"):
        return

    order = context.user_data.get("paid_order")

    if not order:
        context.user_data.pop("paid_utr_pending", None)
        return

    order_id = order["order_id"]
    user_id = update.effective_user.id

    # Always verify the real DB status before accepting UTR.
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        """
        SELECT status
        FROM paid_orders
        WHERE order_id=? AND user_id=?
        """,
        (order_id, user_id)
    )

    row = cur.fetchone()
    conn.close()

    if not row:
        context.user_data.pop("paid_order", None)
        context.user_data.pop("paid_utr_pending", None)
        context.user_data.pop("paid_screenshot_pending", None)
        return

    if row[0] == "Cancelled":
        context.user_data.pop("paid_order", None)
        context.user_data.pop("paid_utr_pending", None)
        context.user_data.pop("paid_screenshot_pending", None)

        await update.message.reply_text(
            "⏰ This order has expired.\n\n"
            f"🆔 Order ID: {order_id}\n\n"
            "❌ UTR can no longer be submitted."
        )
        return

    if row[0] != "Pending":
        context.user_data.pop("paid_utr_pending", None)
        return

    utr = update.message.text.strip()
    utr = "".join(ch for ch in utr if ch.isdigit())

    if len(utr) != 12:
        await update.message.reply_text(
            "❌ Invalid UTR.\n\n"
            "Please send your 12-digit UTR."
        )
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE paid_orders
        SET utr=?, status=?
        WHERE order_id=?
          AND user_id=?
          AND status='Pending'
        """,
        (utr, "UTR Submitted", order_id, user_id)
    )

    conn.commit()
    conn.close()

    order["utr"] = utr
    context.user_data["paid_order"] = order
    context.user_data["paid_utr_pending"] = False
    context.user_data["paid_screenshot_pending"] = True

    await update.message.reply_text(
        "✅ UTR RECEIVED\n\n"
        f"🆔 Order ID: `{order_id}`\n"
        f"🔢 UTR: {utr}\n\n"
        "📸 Now send your payment screenshot here.",
        parse_mode="Markdown"
    )

async def paid_order_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo:
        return

    if not context.user_data.get("paid_screenshot_pending"):
        return

    order = context.user_data.get("paid_order")

    if not order:
        context.user_data.pop("paid_screenshot_pending", None)
        return

    screenshot_file_id = update.message.photo[-1].file_id
    order_id = order["order_id"]
    user_id = update.effective_user.id

    # Always verify the real order status before accepting screenshot.
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        """
        SELECT status, utr
        FROM paid_orders
        WHERE order_id=? AND user_id=?
        """,
        (order_id, user_id)
    )

    row = cur.fetchone()

    if not row:
        conn.close()

        context.user_data.pop("paid_order", None)
        context.user_data.pop("paid_utr_pending", None)
        context.user_data.pop("paid_screenshot_pending", None)

        return

    status, db_utr = row

    # Screenshot is accepted ONLY after UTR submission.
    if status != "UTR Submitted":
        conn.close()

        context.user_data.pop("paid_order", None)
        context.user_data.pop("paid_utr_pending", None)
        context.user_data.pop("paid_screenshot_pending", None)

        if status == "Cancelled":
            await update.message.reply_text(
                "⏰ This order has expired.\n\n"
                f"🆔 Order ID: {order_id}\n\n"
                "❌ Screenshot can no longer be submitted."
            )

        return

    # Make sure a UTR actually exists in DB.
    if not db_utr:
        conn.close()
        return

    cur.execute(
        """
        UPDATE paid_orders
        SET screenshot_file_id=?, status=?
        WHERE order_id=?
          AND user_id=?
          AND status='UTR Submitted'
        """,
        (
            screenshot_file_id,
            "Payment Verification",
            order_id,
            user_id
        )
    )

    conn.commit()
    conn.close()

    order["utr"] = db_utr
    order["screenshot_file_id"] = screenshot_file_id

    context.user_data["paid_order"] = order
    context.user_data.pop("paid_screenshot_pending", None)
    context.user_data.pop("paid_utr_pending", None)

    # Screenshot successfully submitted.
    # Stop the 10-minute timer permanently.
    expiry_task = context.user_data.pop("paid_expiry_task", None)

    if expiry_task:
        try:
            expiry_task.cancel()
        except Exception:
            pass

    admin_text = (
        "💳 NEW PAYMENT VERIFICATION\n\n"
        f"🆔 Order ID: `{order_id}`\n"
        f"👤 User ID: {user_id}\n"
        f"🛍️ Product: {order['reward_name']}\n"
        f"📦 Quantity: {order['quantity']}\n"
        f"💰 Amount: ₹{order['total']:g}\n"
        f"🔢 UTR: {db_utr}\n\n"
        "👇 Verify this payment:"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Approve",
                callback_data=f"paid_approve_{order_id}"
            ),
            InlineKeyboardButton(
                "❌ Reject",
                callback_data=f"paid_reject_{order_id}"
            )
        ]
    ])

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=screenshot_file_id,
        caption=admin_text,
        reply_markup=keyboard
    )

    await update.message.reply_text(
        "💳 PAYMENT SUBMITTED\n"
        "━━━━━━━━━━━━━━\n\n"
        f"🆔 Order ID: `{order_id}`\n"
        f"🔢 UTR: {db_utr}\n\n"
        "⏳ Your payment is now under admin verification.\n\n"
        "👨‍💻 Admin will approve shortly.\n"
        "⚡ Maximum time: 3 hours\n\n"
        "🙏 Thank you for using OpBoy Live Bot!"
    )


async def paid_order_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    order_id = query.data.replace("paid_approve_", "", 1)

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        """
        SELECT user_id, reward_id, reward_name, quantity, status
        FROM paid_orders
        WHERE order_id=?
        """,
        (order_id,)
    )
    order = cur.fetchone()

    if not order:
        conn.close()
        await query.edit_message_caption("❌ Order not found.")
        return

    user_id, reward_id, reward_name, quantity, status = order

    if status == "Approved":
        conn.close()
        await query.edit_message_caption(
            f"⚠️ This order is already approved.\n\n"
            f"🆔 Order ID: {order_id}"
        )
        return

    if status == "Rejected":
        conn.close()
        await query.edit_message_caption(
            f"⚠️ This order is already rejected.\n\n"
            f"🆔 Order ID: {order_id}"
        )
        return

    if status == "Cancelled":
        conn.close()
        await query.edit_message_caption(
            f"⏰ This order has been cancelled.\n\n"
            f"🆔 Order ID: {order_id}\n\n"
            "❌ Cancelled orders cannot be approved."
        )
        return

    cur.execute(
        """
        SELECT id, code
        FROM reward_codes
        WHERE reward_name=? AND used=0
        ORDER BY id
        LIMIT ?
        """,
        (reward_name, quantity)
    )
    code_rows = cur.fetchall()

    if len(code_rows) < quantity:
        conn.close()
        await query.edit_message_caption(
            f"📦 INSUFFICIENT STOCK\n\n"
            f"🆔 Order ID: {order_id}\n"
            f"🛍️ Product: {reward_name}\n"
            f"📦 Required: {quantity}\n"
            f"📦 Available: {len(code_rows)}\n\n"
            f"Please reject this order using:\n"
            f"📦 Insufficient Stock"
        )
        return

    codes = [row[1] for row in code_rows]

    # Mark exact codes as used
    for code_id, code in code_rows:
        cur.execute(
            "UPDATE reward_codes SET used=1 WHERE id=?",
            (code_id,)
        )

    # Update reward stock
    cur.execute(
        """
        UPDATE rewards
        SET stock = stock - ?
        WHERE id=? AND stock >= ?
        """,
        (quantity, reward_id, quantity)
    )

    if cur.rowcount != 1:
        conn.rollback()
        conn.close()

        await query.edit_message_caption(
            f"❌ Stock update failed.\n\n"
            f"🆔 Order ID: {order_id}\n"
            f"Please reject the order as Insufficient Stock."
        )
        return

    # Save exact delivered codes + delivery time
    delivered_codes = "\n".join(codes)

    cur.execute(
        """
        UPDATE paid_orders
        SET status=?,
            delivered_codes=?,
            delivered_at=datetime('now','localtime')
        WHERE order_id=?
        """,
        ("Approved", delivered_codes, order_id)
    )

    conn.commit()
    conn.close()

    code_text = "\n".join(
        f"{i + 1}. `{code}`"
        for i, code in enumerate(codes)
    )

    customer_text = (
        "✅ CODE HAS BEEN DELIVERED\n\n"
        f"🆔 Order ID: `{order_id}`\n"
        f"🛍️ Product: {reward_name}\n"
        f"📦 Quantity: {quantity}\n\n"
        "🎁 Your Code(s):\n"
        f"{code_text}\n\n"
        "🙏 Thank you for your purchase!\n"
        "Please keep your code safe."
    )

    await context.bot.send_message(
        chat_id=user_id,
        text=customer_text,
        parse_mode="Markdown"
    )

    await query.edit_message_caption(
        f"✅ PAYMENT APPROVED\n\n"
        f"🆔 Order ID: `{order_id}`\n"
        f"🛍️ Product: {reward_name}\n"
        f"📦 Quantity: {quantity}\n\n"
        "📦 Code has been delivered to the customer."
    )


async def paid_order_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not query or not query.data.startswith("paid_reject_"):
        return

    # Reason/Other callbacks must go to their own handlers
    if query.data.startswith("paid_reject_reason_") or query.data.startswith("paid_reject_other_"):
        return

    print("🔥 PAID_REJECT CALLBACK RECEIVED")
    print("🔥 CALLBACK DATA:", query.data)

    await query.answer()

    if not is_admin(query.from_user.id):
        return

    order_id = query.data.replace("paid_reject_", "", 1)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "❌ Payment Not Received",
                callback_data=f"paid_reject_reason_{order_id}_payment_not_received"
            )
        ],
        [
            InlineKeyboardButton(
                "⚠️ Invalid UTR",
                callback_data=f"paid_reject_reason_{order_id}_invalid_utr"
            )
        ],
        [
            InlineKeyboardButton(
                "📸 Screenshot Not Clear",
                callback_data=f"paid_reject_reason_{order_id}_screenshot_not_clear"
            )
        ],
        [
            InlineKeyboardButton(
                "💰 Wrong Amount",
                callback_data=f"paid_reject_reason_{order_id}_wrong_amount"
            )
        ],
        [
            InlineKeyboardButton(
                "📦 Insufficient Stock",
                callback_data=f"paid_reject_reason_{order_id}_insufficient_stock"
            )
        ],
        [
            InlineKeyboardButton(
                "🚫 Other",
                callback_data=f"paid_reject_other_{order_id}"
            )
        ]
    ])

    await query.edit_message_caption(
        f"❌ SELECT REJECTION REASON\n\n"
        f"🆔 Order ID: `{order_id}`\n\n"
        "Choose the reason for rejecting this order:",
        reply_markup=keyboard
    )


async def paid_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    data = query.data

    prefix = "paid_reject_reason_"
    if not data.startswith(prefix):
        return

    remaining = data[len(prefix):]

    parts = remaining.split("_", 1)
    if len(parts) != 2:
        await query.answer("❌ Invalid rejection data.", show_alert=True)
        return

    order_id, reason_key = parts

    reasons = {
        "payment_not_received": "Payment Not Received",
        "invalid_utr": "Invalid UTR",
        "screenshot_not_clear": "Screenshot Not Clear",
        "wrong_amount": "Wrong Amount",
        "insufficient_stock": "Insufficient Stock"
    }

    reason = reasons.get(reason_key)

    if not reason:
        await query.answer("❌ Invalid rejection reason.", show_alert=True)
        return

    await finalize_paid_rejection(
        query,
        context,
        order_id,
        reason
    )


async def paid_reject_other(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    order_id = query.data.replace("paid_reject_other_", "", 1)

    context.user_data["paid_reject_other_pending"] = True
    context.user_data["paid_reject_other_order_id"] = order_id

    await query.edit_message_caption(
        f"🚫 OTHER REJECTION REASON\n\n"
        f"🆔 Order ID: `{order_id}`\n\n"
        "Please type the reason for rejecting this order."
    )


async def paid_reject_other_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    if not is_admin(update.effective_user.id):
        return

    if not context.user_data.get("paid_reject_other_pending"):
        return

    reason = update.message.text.strip()

    if not reason:
        await update.message.reply_text(
            "❌ Reason cannot be empty.\n\n"
            "Please type the rejection reason."
        )
        return

    order_id = context.user_data.get("paid_reject_other_order_id")

    if not order_id:
        context.user_data.pop("paid_reject_other_pending", None)
        return

    context.user_data.pop("paid_reject_other_pending", None)
    context.user_data.pop("paid_reject_other_order_id", None)

    await finalize_paid_rejection(
        None,
        context,
        order_id,
        reason,
        admin_chat_id=update.effective_chat.id
    )


async def finalize_paid_rejection(
    query,
    context,
    order_id,
    reason,
    admin_chat_id=None
):
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        """
        SELECT user_id, reward_name, quantity, status
        FROM paid_orders
        WHERE order_id=?
        """,
        (order_id,)
    )

    order = cur.fetchone()

    if not order:
        conn.close()

        if query:
            await query.edit_message_caption("❌ Order not found.")
        else:
            await context.bot.send_message(
                chat_id=admin_chat_id,
                text=f"❌ Order not found.\n\n🆔 Order ID: {order_id}"
            )
        return

    user_id, reward_name, quantity, status = order

    if status == "Approved":
        conn.close()

        if query:
            await query.edit_message_caption(
                f"⚠️ This order is already approved.\n\n"
                f"🆔 Order ID: `{order_id}`"
            )
        else:
            await context.bot.send_message(
                chat_id=admin_chat_id,
                text=f"⚠️ Order already approved.\n\n🆔 Order ID: {order_id}"
            )
        return

    if status == "Rejected":
        conn.close()

        if query:
            await query.edit_message_caption(
                f"⚠️ This order is already rejected.\n\n"
                f"🆔 Order ID: `{order_id}`"
            )
        else:
            await context.bot.send_message(
                chat_id=admin_chat_id,
                text=f"⚠️ Order already rejected.\n\n🆔 Order ID: {order_id}"
            )
        return

    cur.execute(
        """
        UPDATE paid_orders
        SET status=?,
            rejection_reason=?,
            rejected_at=datetime('now','localtime')
        WHERE order_id=?
        """,
        ("Rejected", reason, order_id)
    )

    conn.commit()
    conn.close()

    if reason == "Insufficient Stock":
        customer_text = (
            "📦 ORDER UPDATE\n\n"
            f"🆔 Order ID: `{order_id}`\n"
            f"🛍️ Product: {reward_name}\n"
            f"📦 Quantity: {quantity}\n\n"
            "Unfortunately, your order could not be completed "
            "because the required stock became unavailable.\n\n"
            "💰 REFUND\n"
            "Please contact Support for your refund.\n\n"
            "🔄 You can also contact Support if you want "
            "another available code instead.\n\n"
            "📞 Support: @beyondgravityX"
        )
    else:
        customer_text = (
            "❌ PAYMENT REJECTED\n\n"
            f"🆔 Order ID: `{order_id}`\n"
            f"🛍️ Product: {reward_name}\n"
            f"📦 Quantity: {quantity}\n\n"
            f"📌 Reason: {reason}\n\n"
            "If you believe this was a mistake, please contact Support.\n\n"
            "📞 Support: @beyondgravityX"
        )

    await context.bot.send_message(
        chat_id=user_id,
        text=customer_text,
        parse_mode="Markdown"
    )

    admin_text = (
        "✅ ORDER REJECTED\n\n"
        f"🆔 Order ID: `{order_id}`\n"
        f"🛍️ Product: {reward_name}\n"
        f"📦 Quantity: {quantity}\n"
        f"❌ Reason: {reason}\n\n"
        "📨 Customer has been notified."
    )

    if query:
        await query.edit_message_caption(admin_text)
    else:
        await context.bot.send_message(
            chat_id=admin_chat_id,
            text=admin_text
        )


async def setapprovaladmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if len(context.args) != 1:
        await update.message.reply_text(
            "Use:\n/setapprovaladmin USER_ID"
        )
        return

    try:
        new_admin = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid User ID.")
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO bot_settings(key,value) VALUES('approval_admin',?)",
        (str(new_admin),)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Approval Admin Updated\n\n"
        f"👤 New Approval Admin ID: {new_admin}"
    )


async def approvaladmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    current_admin = get_approval_admin()

    await update.message.reply_text(
        f"🔐 Current Approval Admin\n\n"
        f"🆔 User ID: {current_admin}"
    )


async def add_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    try:
        user_id = int(context.args[0])
        amount = int(context.args[1])

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute(
            "UPDATE users SET points = points + ? WHERE user_id = ?",
            (amount, user_id)
        )

        conn.commit()
        conn.close()

        await update.message.reply_text(
            f"✅ Added {amount} points to {user_id}"
        )

    except:
        await update.message.reply_text(
            "Use: /addpoints USER_ID POINTS"
        )

def get_active_channels():
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT name, username, url FROM bot_channels WHERE active=1 ORDER BY id"
    )
    channels = cur.fetchall()

    conn.close()
    return channels


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("START COMMAND RECEIVED")
    print("STEP 1 PASSED")

    user = update.effective_user

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT blocked FROM users WHERE user_id=?", (user.id,))
    row = cur.fetchone()
    conn.close()

    if row and row[0] == 1:
        blocked_buttons = [
            [InlineKeyboardButton("🆘 Contact Support", callback_data="help")]
        ]

        await update.message.reply_text(
            "🚫 YOU ARE BLOCKED\n\n"
            "You are blocked by the admin.\n"
            "Please contact support if you think this is a mistake.",
            reply_markup=InlineKeyboardMarkup(blocked_buttons)
        )
        return
    if MAINTENANCE_MODE:

        await update.message.reply_text(
            "🤖 OPBOY LIVE BOT\n"
            "━━━━━━━━━━━━━━\n\n"
            "🛠️ BOT UNDER MAINTENANCE\n\n"
            "✨ We are upgrading our bot\n"
            "🚀 Adding new features & improvements\n\n"
            "⏳ Please try again later.\n\n"
            "🙏 Thanks for your patience ❤️\n"
            "━━━━━━━━━━━━━━"
        )
        return

    user = update.effective_user

    conn = sqlite3.connect("users.db", timeout=30)
    conn = sqlite3.connect("users.db", timeout=30)
    cur = conn.cursor()

    cur.execute(
        "SELECT 1 FROM users WHERE user_id=?",
        (user.id,)
    )
    is_new_user = cur.fetchone() is None

    cur.execute(
        "INSERT OR IGNORE INTO users(user_id, username) VALUES(?, ?)",
            (user.id, user.username)
    )

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]

    conn.close()

    if is_new_user:
        await send_activity_log(
            context,
            "🙂 New User Started Bot\n\n"
            f"👉 User: {user.id}\n\n"
            f"🧾 Total User: {total_users}"
        )
    channels = [
        (f"📢 {name}", url, username)
        for name, username, url in get_active_channels()
    ]

    left_buttons = []

    for text, url, channel in channels:
        member = await context.bot.get_chat_member(
            chat_id=channel,
            user_id=user.id
        )

        if member.status in ["left", "kicked"]:
            left_buttons.append(
                [InlineKeyboardButton(text, url=url)]
            )

    print("CHANNEL CHECK DONE")
    print("ABOUT TO SEND START REPLY")
    if left_buttons:
        left_buttons.append([
            InlineKeyboardButton(
                "✅ Verify",
                callback_data="verify"
            )
        ])
        reply_markup = InlineKeyboardMarkup(left_buttons)
        await update.message.reply_text(
            "👋 Welcome to OPx Bot!\n\n"
            "📢 Please join all required channels and then press Verify.",
            reply_markup=reply_markup
        )
        return

    # User has joined all required channels
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT verified FROM users WHERE user_id=?",
        (user.id,)
    )
    verified_row = cur.fetchone()
    conn.close()

    if not verified_row or verified_row[0] != 1:
        await human_verify(update, context)
        return

    normal_keyboard = ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("🛍️ Browse Product"),
                KeyboardButton("📦 My Orders")
            ],
            [
                KeyboardButton("📞 Support"),
                KeyboardButton("ℹ️ How It Works")
            ]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

    await context.bot.send_message(
        chat_id=user.id,
        text=(
            "Welcome to OPx Shop 🙏🏻\n\n"
            "📊 Limited Stock Available! 📊\n\n"
            "🛍️ Choose an option below to continue: 👇"
        ),
        reply_markup=normal_keyboard
    )
    print("START REPLY FUNCTION COMPLETED")
init_db()
app = Application.builder().token(TOKEN).build()

async def admin_points_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query=update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    context.user_data["admin_points_action"]=query.data
    text="💰 ADD POINTS\n\nSend: USER_ID POINTS\n\nExample: 6427806986 25" if query.data=="admin_addpoints" else "💸 REMOVE POINTS\n\nSend: USER_ID POINTS\n\nExample: 6427806986 10"
    await query.edit_message_text(text)

async def admin_points_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id): return
    action=context.user_data.get("admin_points_action")
    if not action: return
    try:
        user_id,amount=map(int,update.message.text.strip().split())
        if amount<=0: raise ValueError
        if action=="admin_removepoints": amount=-amount
        conn=sqlite3.connect("users.db"); cur=conn.cursor()
        cur.execute("UPDATE users SET points=points+? WHERE user_id=?",(amount,user_id))
        if cur.rowcount==0:
            conn.close(); await update.message.reply_text("❌ User not found."); return
        conn.commit(); cur.execute("SELECT points FROM users WHERE user_id=?",(user_id,)); balance=cur.fetchone()[0]; conn.close()
        context.user_data.pop("admin_points_action",None)
        await update.message.reply_text(f"✅ POINTS UPDATED\n\n🆔 User ID: {user_id}\n💎 New Balance: {balance} Points")
    except Exception:
        await update.message.reply_text("❌ Invalid format.\n\nUse: USER_ID POINTS\nExample: 6427806986 25")


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    buttons = [
        [
            InlineKeyboardButton("👥 Users", callback_data="admin_usermanage"),
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats")
        ],
        [
            InlineKeyboardButton("🛍️ Products", callback_data="admin_rewards"),
            InlineKeyboardButton("📦 Stock & Codes", callback_data="admin_stock")
        ],
        [
            InlineKeyboardButton("📋 Orders", callback_data="admin_requests"),
            InlineKeyboardButton("📋 Pending Orders", callback_data="admin_pending_orders")
        ],
        [
            InlineKeyboardButton("🔐 Approval Admin", callback_data="admin_approval")
        ],
        [
            InlineKeyboardButton("💳 Payment Settings", callback_data="admin_payment_settings"),
            InlineKeyboardButton("💸 Cost Settings", callback_data="admin_cost_settings")
        ],
        [
            InlineKeyboardButton("🛠️ Maintenance", callback_data="admin_maintenance")
        ],
        [
            InlineKeyboardButton("📢 Channel Management", callback_data="admin_channels"),
            InlineKeyboardButton("👑 Admin Management", callback_data="admin_management")
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton("🏠 Main Menu", callback_data="main")
        ]
    ]

    await update.message.reply_text(
        "👑 OPx SHOP ADMIN PANEL\n\n"
        "👇 Select an option:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def claim_limit_control(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    limit = get_point_setting("daily_claim_limit", "5")

    if str(limit) == "0":
        status = "♾️ Unlimited"
    else:
        status = f"🔢 {limit} claims/day"

    keyboard = [
        [InlineKeyboardButton("🔢 Set Limit", callback_data="claim_limit_set")],
        [InlineKeyboardButton("♾️ Unlimited", callback_data="claim_limit_unlimited")],
        [InlineKeyboardButton("📊 Current Limit", callback_data="claim_limit_current")],
        [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_back")]
    ]

    await query.edit_message_text(
        "⚙️ DAILY CLAIM LIMIT\n\n"
        f"Current: {status}\n\n"
        "Yahan se daily claim limit control karo.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def claim_limit_set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    context.user_data["claim_limit_action"] = True

    await query.edit_message_text(
        "🔢 SET DAILY CLAIM LIMIT\n\n"
        "Sirf number bhejo.\n\n"
        "Example: 10\n\n"
        "♾️ Unlimited ke liye 0 bhejo.\n\n"
        "❌ Cancel: /cancel"
    )


async def claim_limit_unlimited(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    set_point_setting("daily_claim_limit", "0")

    await query.edit_message_text(
        "♾️ DAILY CLAIM LIMIT\n\n"
        "✅ Unlimited enabled."
    )


async def claim_limit_current(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    limit = get_point_setting("daily_claim_limit", "5")

    if str(limit) == "0":
        text = "📊 CURRENT LIMIT\n\n♾️ Unlimited"
    else:
        text = f"📊 CURRENT LIMIT\n\n🔢 {limit} claims/day"

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Claim Limit", callback_data="claim_limit_control")]
        ])
    )


async def claim_limit_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if not context.user_data.get("claim_limit_action"):
        return

    text = update.message.text.strip()

    if text == "/cancel":
        context.user_data.pop("claim_limit_action", None)
        await update.message.reply_text("❌ Claim limit change cancelled.")
        return

    try:
        limit = int(text)
    except ValueError:
        await update.message.reply_text("❌ Sirf number bhejo. Example: 10")
        return

    if limit < 0:
        await update.message.reply_text("❌ Limit 0 ya usse bada hona chahiye.")
        return

    set_point_setting("daily_claim_limit", str(limit))
    context.user_data.pop("claim_limit_action", None)

    if limit == 0:
        await update.message.reply_text("✅ Daily claim limit: ♾️ Unlimited")
    else:
        await update.message.reply_text(
            f"✅ Daily claim limit set to {limit} claims/day."
        )


async def admin_unblock_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    context.user_data["admin_user_action"] = "unblock"

    await query.edit_message_text(
        "✅ UNBLOCK USER\n\n"
        "Send USER ID to unblock.\n\n"
        "Example: 6427806986"
    )


async def admin_unblock_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if context.user_data.get("admin_user_action") != "unblock":
        return

    try:
        user_id = int(update.message.text.strip())

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute(
            "SELECT user_id, username, blocked FROM users WHERE user_id=?",
            (user_id,)
        )
        user = cur.fetchone()

        if not user:
            conn.close()
            await update.message.reply_text("❌ User not found.")
            return

        uid, username, blocked = user

        if not blocked:
            conn.close()
            await update.message.reply_text("ℹ️ This user is already unblocked.")
            context.user_data.pop("admin_user_action", None)
            return

        cur.execute(
            "UPDATE users SET blocked=0 WHERE user_id=?",
            (user_id,)
        )
        conn.commit()
        conn.close()

        username_text = f"@{username}" if username else "Not set"

        await update.message.reply_text(
            "✅ USER UNBLOCKED\n\n"
            f"🆔 ID: {uid}\n"
            f"👤 Username: {username_text}\n\n"
            "This user can use the bot again."
        )

        context.user_data.pop("admin_user_action", None)

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid User ID.\n\n"
            "Send only the numeric User ID."
        )


async def admin_blocked_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, username FROM users WHERE blocked=1 ORDER BY user_id"
    )
    users = cur.fetchall()
    conn.close()

    if not users:
        text = "📋 BLOCKED USERS\n\n✅ No blocked users."
    else:
        lines = ["📋 BLOCKED USERS", ""]
        for user_id, username in users:
            username_text = f"@{username}" if username else "No username"
            lines.append(f"🆔 {user_id} — {username_text}")

        text = "\n".join(lines)

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ User Management", callback_data="admin_usermanage")]
        ])
    )


async def admin_block_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    context.user_data["admin_user_action"] = "block"

    await query.edit_message_text(
        "🚫 BLOCK USER\n\n"
        "Send USER ID to block.\n\n"
        "Example: 6427806986"
    )


async def admin_block_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if context.user_data.get("admin_user_action") != "block":
        return

    try:
        user_id = int(update.message.text.strip())

        if user_id == ADMIN_ID:
            await update.message.reply_text("❌ You cannot block the main admin.")
            context.user_data.pop("admin_user_action", None)
            return

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute(
            "SELECT user_id, username, blocked FROM users WHERE user_id=?",
            (user_id,)
        )
        user = cur.fetchone()

        if not user:
            conn.close()
            await update.message.reply_text("❌ User not found.")
            return

        uid, username, blocked = user

        if blocked:
            conn.close()
            await update.message.reply_text("⚠️ This user is already blocked.")
            context.user_data.pop("admin_user_action", None)
            return

        cur.execute(
            "UPDATE users SET blocked=1 WHERE user_id=?",
            (user_id,)
        )
        conn.commit()
        conn.close()

        username_text = f"@{username}" if username else "Not set"

        await update.message.reply_text(
            "🚫 USER BLOCKED\n\n"
            f"🆔 ID: {uid}\n"
            f"👤 Username: {username_text}\n\n"
            "This user is now blocked."
        )

        context.user_data.pop("admin_user_action", None)

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid User ID.\n\n"
            "Send only the numeric User ID."
        )


async def admin_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    action = context.user_data.get("admin_user_action")

    if action == "details":
        await admin_user_details_message(update, context)
    elif action == "block":
        await admin_block_user_message(update, context)
    elif action == "unblock":
        await admin_unblock_user_message(update, context)
    elif action == "reset_points":
        await admin_reset_points_message(update, context)
    elif action in ("addcodes_reward", "addcodes_codes"):
        await admin_addcodes_message(update, context)

async def blocked_user_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user:
        return

    if user.id == ADMIN_ID:
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT blocked FROM users WHERE user_id=?", (user.id,))
    row = cur.fetchone()
    conn.close()

    if not row or row[0] != 1:
        return

    # Allow blocked users to contact support.
    if update.callback_query and update.callback_query.data == "help":
        return

    if update.callback_query:
        await update.callback_query.answer(
            "🚫 You are blocked by the admin.",
            show_alert=True
        )
    elif update.message:
        await update.message.reply_text(
            "🚫 YOU ARE BLOCKED\n\n"
            "You are blocked by the admin.\n"
            "Please contact support if you think this is a mistake.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🆘 Contact Support", callback_data="help")]
            ])
        )

    raise ApplicationHandlerStop



async def admin_user_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    context.user_data["admin_user_action"] = "details"

    await query.edit_message_text(
        "🔎 USER DETAILS\n\n"
        "Send USER ID\n\n"
        "Example: 6427806986"
    )


async def admin_user_details_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if context.user_data.get("admin_user_action") != "details":
        return

    try:
        user_id = int(update.message.text.strip())

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, username, points, verified, blocked "
            "FROM users WHERE user_id=?",
            (user_id,)
        )
        user = cur.fetchone()
        conn.close()

        if not user:
            await update.message.reply_text("❌ User not found.")
            return

        uid, username, points, verified, blocked = user

        username_text = f"@{username}" if username else "Not set"
        verified_text = "Yes" if verified else "No"
        status_text = "🚫 Blocked" if blocked else "🟢 Active"

        await update.message.reply_text(
            "👤 USER DETAILS\n\n"
            f"🆔 ID: {uid}\n"
            f"👤 Username: {username_text}\n"
            f"💎 Points: {points}\n"

            f"🔐 Verified: {verified_text}\n"
            f"📌 Status: {status_text}"
        )

        context.user_data.pop("admin_user_action", None)

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid User ID.\n\n"
            "Please send only the numeric User ID."
        )



async def admin_reset_points_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    context.user_data["admin_user_action"] = "reset_points"

    await query.edit_message_text(
        "💰 RESET POINTS\n\n"
        "Send USER ID to reset points.\n\n"
        "Example: 6427806986"
    )


async def admin_reset_points_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if context.user_data.get("admin_user_action") != "reset_points":
        return

    try:
        user_id = int(update.message.text.strip())

        if user_id == ADMIN_ID:
            await update.message.reply_text("❌ You cannot reset the main admin's points.")
            context.user_data.pop("admin_user_action", None)
            return

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute(
            "SELECT username, points FROM users WHERE user_id=?",
            (user_id,)
        )
        user = cur.fetchone()

        if not user:
            conn.close()
            await update.message.reply_text("❌ User not found.")
            context.user_data.pop("admin_user_action", None)
            return

        username, old_points = user

        cur.execute(
            "UPDATE users SET points=0 WHERE user_id=?",
            (user_id,)
        )

        conn.commit()
        conn.close()

        context.user_data.pop("admin_user_action", None)

        username_text = f"@{username}" if username else "Not set"

        await update.message.reply_text(
            "✅ POINTS RESET SUCCESSFULLY\n\n"
            f"🆔 User ID: {user_id}\n"
            f"👤 Username: {username_text}\n"
            f"💎 Previous Points: {old_points}\n"
            "💰 New Points: 0"
        )

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid User ID.\n\n"
            "Send only the numeric User ID."
        )


async def admin_user_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    buttons = [
        [
            InlineKeyboardButton("🔎 User Details", callback_data="admin_user_details"),
            InlineKeyboardButton("🚫 Block User", callback_data="admin_block_user")
        ],
        [
            InlineKeyboardButton("✅ Unblock User", callback_data="admin_unblock_user"),
            InlineKeyboardButton("📋 Blocked Users", callback_data="admin_blocked_users")
        ],
        [
            InlineKeyboardButton("💰 Reset Points", callback_data="admin_reset_points")
        ],
        [
            InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_back")
        ]
    ]

    await query.edit_message_text(
        "👤 USER MANAGEMENT\n\n👇 Select an option:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )



async def admin_addcodes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM rewards ORDER BY id")
    rewards = cur.fetchall()
    conn.close()

    if not rewards:
        await query.edit_message_text(
            "❌ No rewards found.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_back")]
            ])
        )
        return

    keyboard = []

    for reward_id, name in rewards:
        keyboard.append([
            InlineKeyboardButton(
                f"🎁 {name}",
                callback_data=f"admin_addcodes_reward_{reward_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton("⬅️ Stock", callback_data="admin_stock")
    ])

    await query.edit_message_text(
        "➕ ADD CODES\n\n"
        "Select the Reward:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def admin_addcodes_reward_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    try:
        reward_id = int(query.data.rsplit("_", 1)[1])
    except ValueError:
        await query.answer("❌ Invalid reward.", show_alert=True)
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT name FROM rewards WHERE id=?", (reward_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await query.answer("❌ Reward not found.", show_alert=True)
        return

    reward_name = row[0]

    context.user_data["admin_addcodes_reward"] = reward_name
    context.user_data["admin_user_action"] = "addcodes_codes"

    await query.edit_message_text(
        f"🎁 Reward: {reward_name}\n\n"
        "📦 Now send the codes.\n"
        "Send ONE CODE per line.\n\n"
        "Example:\n"
        "CODE001\n"
        "CODE002\n"
        "CODE003"
    )

async def admin_addcodes_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    action = context.user_data.get("admin_user_action")

    if action == "addcodes_reward":
        entered_name = update.message.text.strip()

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute(
            "SELECT id, name FROM rewards WHERE name=? AND mode='paid'",
            (entered_name,)
        )
        reward = cur.fetchone()

        if not reward:
            cur.execute(
                """
                SELECT id, name
                FROM rewards
                WHERE mode='paid'
                  AND LOWER(name) LIKE ?
                ORDER BY id
                LIMIT 1
                """,
                (f"%{entered_name.lower()}%",)
            )
            reward = cur.fetchone()

        conn.close()

        if not reward:
            await update.message.reply_text(
                "❌ Paid product not found.\n\n"
                "Please send the product name."
            )
            return

        reward_id, reward_name = reward

        context.user_data["admin_addcodes_reward"] = reward_name
        context.user_data["admin_user_action"] = "addcodes_codes"

        await update.message.reply_text(
            f"🎁 Reward: {reward_name}\n\n"
            "📦 Now send the codes.\n"
            "Send ONE CODE per line.\n\n"
            "Example:\n"
            "CODE001\n"
            "CODE002\n"
            "CODE003"
        )
        return

    if action != "addcodes_codes":
        return

    reward_name = context.user_data.get("admin_addcodes_reward")

    if not reward_name:
        context.user_data.pop("admin_user_action", None)
        await update.message.reply_text(
            "❌ Session expired. Please start again."
        )
        return

    codes = [
        line.strip()
        for line in update.message.text.splitlines()
        if line.strip()
    ]

    if not codes:
        await update.message.reply_text("❌ No codes found.")
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    added = 0
    duplicate = 0

    for code in codes:
        cur.execute(
            "SELECT 1 FROM reward_codes WHERE reward_name=? AND code=? AND used=0",
            (reward_name, code)
        )

        if cur.fetchone():
            duplicate += 1
            continue

        cur.execute(
            """
            INSERT INTO reward_codes(reward_name, code, used)
            VALUES(?,?,0)
            """,
            (reward_name, code)
        )
        added += 1

    cur.execute(
        """
        SELECT COUNT(*)
        FROM reward_codes
        WHERE reward_name=? AND used=0
        """,
        (reward_name,)
    )
    total_available = cur.fetchone()[0]

    cur.execute(
        """
        UPDATE rewards
        SET stock=?
        WHERE name=? AND mode='paid'
        """,
        (total_available, reward_name)
    )

    conn.commit()
    conn.close()

    context.user_data.pop("admin_user_action", None)
    context.user_data.pop("admin_addcodes_reward", None)

    await update.message.reply_text(
        "✅ CODES ADDED\n\n"
        f"🎁 Reward: {reward_name}\n"
        f"📥 Added: {added}\n"
        f"♻️ Duplicate: {duplicate}\n"
        f"📦 Total Available: {total_available}"
    )


async def admin_request_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    data = query.data
    parts = data.split("_", 3)

    if len(parts) < 4:
        await query.answer("❌ Invalid request.", show_alert=True)
        return

    try:
        user_id = int(parts[2])
    except ValueError:
        await query.answer("❌ Invalid User ID.", show_alert=True)
        return

    reward_name = parts[3]

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT points, status FROM claim_requests "
        "WHERE user_id=? AND reward_name=? AND status='Pending' "
        "ORDER BY claim_time DESC LIMIT 1",
        (user_id, reward_name)
    )
    request = cur.fetchone()

    conn.close()

    if not request:
        await query.edit_message_text(
            "❌ This request is no longer pending.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Requests", callback_data="admin_requests")]
            ])
        )
        return

    points, status = request

    await query.edit_message_text(
        "📋 CLAIM REQUEST\n\n"
        f"🆔 User ID: {user_id}\n"
        f"🎁 Reward: {reward_name}\n"
        f"💎 Points: {points}\n"
        f"⏳ Status: {status}\n\n"
        "Choose an action:",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Approve",
                    callback_data=f"approve_{user_id}_{reward_name}"
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=f"reject_{user_id}_{reward_name}"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Requests",
                    callback_data="admin_requests"
                )
            ]
        ])
    )

async def admin_point_purchase_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    try:
        request_id = int(query.data.split("_")[-1])
    except ValueError:
        await query.answer("❌ Invalid request.", show_alert=True)
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id, package_points, amount, screenshot_file_id, status "
        "FROM point_purchase_requests WHERE id=?",
        (request_id,)
    )
    request = cur.fetchone()
    conn.close()

    if not request:
        await query.edit_message_text("❌ Purchase request not found.")
        return

    user_id, points, amount, screenshot_file_id, status = request

    if status != "Pending":
        await query.edit_message_text(
            f"⚠️ This request is already {status}."
        )
        return

    caption = (
        "💰 POINT PURCHASE REQUEST\n\n"
        f"🆔 Request ID: {request_id}\n"
        f"👤 User ID: {user_id}\n"
        f"📦 Package: {points} Points\n"
        f"💵 Amount: ₹{amount}\n"
        f"⏳ Status: Pending"
    )

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=screenshot_file_id,
        caption=caption,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Approve",
                    callback_data=f"approve_purchase_{request_id}"
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=f"reject_purchase_{request_id}"
                )
            ]
        ])
    )

    await query.edit_message_text(
        "✅ Payment screenshot submitted successfully.\n\n"
        "⏳ Admin will verify your payment and credit the points."
    )


async def approve_point_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    try:
        request_id = int(query.data.split("_")[-1])
    except ValueError:
        await query.answer("❌ Invalid request.", show_alert=True)
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id, package_points, amount, status "
        "FROM point_purchase_requests WHERE id=?",
        (request_id,)
    )
    request = cur.fetchone()

    if not request:
        conn.close()
        await query.edit_message_caption(caption="❌ Request not found.")
        return

    user_id, points, amount, status = request

    if status != "Pending":
        conn.close()
        await query.answer(
            f"⚠️ Already {status}.",
            show_alert=True
        )
        return

    cur.execute(
        "UPDATE users SET points = points + ? WHERE user_id=?",
        (points, user_id)
    )

    cur.execute(
        "UPDATE point_purchase_requests SET status='Approved' WHERE id=?",
        (request_id,)
    )

    conn.commit()
    conn.close()

    await query.edit_message_caption(
        caption=(
            "✅ PAYMENT APPROVED\n\n"
            f"🆔 Request ID: {request_id}\n"
            f"👤 User ID: {user_id}\n"
            f"📦 Points Added: {points}\n"
            f"💵 Amount: ₹{amount}\n\n"
            "💎 Points have been credited automatically."
        )
    )

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "🎉 PAYMENT APPROVED!\n\n"
                f"📦 Points Added: {points}\n"
                f"💵 Amount: ₹{amount}\n"
                f"🆔 Request ID: {request_id}\n\n"
                "💎 Your points have been added successfully."
            )
        )
    except Exception as e:
        print(f"⚠️ Could not notify user {user_id}: {e}")


async def reject_point_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    try:
        request_id = int(query.data.split("_")[-1])
    except ValueError:
        await query.answer("❌ Invalid request.", show_alert=True)
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id, package_points, amount, status "
        "FROM point_purchase_requests WHERE id=?",
        (request_id,)
    )
    request = cur.fetchone()

    if not request:
        conn.close()
        await query.edit_message_caption(caption="❌ Request not found.")
        return

    user_id, points, amount, status = request

    if status != "Pending":
        conn.close()
        await query.answer(
            f"⚠️ Already {status}.",
            show_alert=True
        )
        return

    cur.execute(
        "UPDATE point_purchase_requests SET status='Rejected' WHERE id=?",
        (request_id,)
    )

    conn.commit()
    conn.close()

    await query.edit_message_caption(
        caption=(
            "❌ PAYMENT REJECTED\n\n"
            f"🆔 Request ID: {request_id}\n"
            f"👤 User ID: {user_id}\n"
            f"📦 Package: {points} Points\n"
            f"💵 Amount: ₹{amount}\n\n"
            "No points were added."
        )
    )

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "❌ PAYMENT REJECTED\n\n"
                f"📦 Package: {points} Points\n"
                f"💵 Amount: ₹{amount}\n"
                f"🆔 Request ID: {request_id}\n\n"
                "Your payment could not be verified.\n\n"
                "💬 For refund or payment inquiry, please contact Support.\n"
                "🕐 Please keep your payment proof and Request ID ready."
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🆘 Support", callback_data="help")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
            ])
        )

    except Exception as e:
        print(f"⚠️ Could not notify user {user_id}: {e}")




async def shop_set_upi_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    context.user_data["shop_setting_action"] = "set_upi"

    await query.edit_message_text(
        "💳 SET UPI\n\n"
        "Send the new UPI ID now.\n\n"
        "Example: yourname@upi"
    )


async def shop_save_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if context.user_data.get("shop_setting_action") != "set_upi":
        return

    upi = update.message.text.strip()

    if "@" not in upi or " " in upi or len(upi) > 100:
        await update.message.reply_text(
            "❌ Invalid UPI ID.\n\n"
            "Please send a valid UPI ID."
        )
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "INSERT OR REPLACE INTO shop_settings(key, value) VALUES(?, ?)",
        ("shop_upi", upi)
    )

    conn.commit()
    conn.close()

    context.user_data.pop("shop_setting_action", None)

    await update.message.reply_text(
        f"✅ UPI UPDATED\n\n"
        f"💳 New UPI: {upi}"
    )



async def shop_set_qr_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    context.user_data["shop_setting_action"] = "set_qr"

    await query.edit_message_text(
        "🖼️ SET PAYMENT QR\n\n"
        "Please send the QR image now."
    )


async def shop_save_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if context.user_data.get("shop_setting_action") != "set_qr":
        return

    if not update.message.photo:
        await update.message.reply_text(
            "❌ Please send the QR as an image/photo."
        )
        return

    qr_file_id = update.message.photo[-1].file_id

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "INSERT OR REPLACE INTO shop_settings(key, value) VALUES(?, ?)",
        ("shop_qr", qr_file_id)
    )

    conn.commit()
    conn.close()

    context.user_data.pop("shop_setting_action", None)

    await update.message.reply_text(
        "✅ PAYMENT QR UPDATED\n\n"
        "The new QR has been saved successfully."
    )


async def admin_payment_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute("SELECT value FROM shop_settings WHERE key=?", ("shop_upi",))
    row = cur.fetchone()
    upi = row[0] if row and row[0] else "Not Set"

    cur.execute("SELECT value FROM shop_settings WHERE key=?", ("shop_qr",))
    row = cur.fetchone()
    qr = row[0] if row and row[0] else ""

    conn.close()

    qr_status = "SET ✅" if qr else "NOT SET ❌"

    keyboard = [
        [InlineKeyboardButton("💳 Set UPI", callback_data="shop_set_upi")],
        [InlineKeyboardButton("🖼️ Set QR", callback_data="shop_set_qr")],
        [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_back")]
    ]

    await query.edit_message_text(
        "💳 PAYMENT SETTINGS\n\n"
        f"UPI: {upi}\n"
        f"QR: {qr_status}\n\n"
        "👇 Choose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def paid_admin_order_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    order_id = query.data.replace("paid_admin_order_", "", 1)

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        """
        SELECT order_id, user_id, reward_name, quantity, price,
               total, utr, screenshot_file_id, status, order_time,
               delivered_codes, delivered_at,
               rejection_reason, rejected_at
        FROM paid_orders
        WHERE order_id=?
        """,
        (order_id,)
    )

    order = cur.fetchone()

    if not order:
        conn.close()

        await query.edit_message_text(
            "❌ Order not found.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Orders",
                        callback_data="admin_requests"
                    )
                ]
            ])
        )
        return

    (
        order_id,
        user_id,
        reward_name,
        quantity,
        price,
        total,
        utr,
        screenshot_file_id,
        status,
        order_time,
        delivered_codes,
        delivered_at,
        rejection_reason,
        rejected_at
    ) = order

    # Get username if available.
    cur.execute(
        "SELECT username FROM users WHERE user_id=?",
        (user_id,)
    )

    user_row = cur.fetchone()
    conn.close()

    username = (
        f"@{user_row[0]}"
        if user_row and user_row[0]
        else "Not available"
    )

    screenshot_status = (
        "✅ Submitted"
        if screenshot_file_id
        else "❌ Not submitted"
    )

    # ---------------- STATUS HANDLING ----------------

    if status == "Approved":
        payment_status = "✅ Approved"
        delivery_status = "✅ Delivered"

        if delivered_codes:
            code_lines = delivered_codes.splitlines()

            delivered_code_text = "\n".join(
                f"{i + 1}. `{code}`"
                for i, code in enumerate(code_lines)
            )
        else:
            delivered_code_text = "⚠️ Code record not found"

        delivery_section = (
            "\n📦 DELIVERY\n"
            "━━━━━━━━━━━━━━━━\n"
            f"Status: {delivery_status}\n"
            f"📊 Codes Delivered: "
            f"{len(delivered_codes.splitlines()) if delivered_codes else 0}\n"
            f"🕒 Delivered At: {delivered_at or 'N/A'}\n\n"
            "🎁 DELIVERED CODE(S)\n"
            "━━━━━━━━━━━━━━━━\n"
            f"{delivered_code_text}\n"
        )

        final_status = (
            "\n📌 FINAL STATUS\n"
            "━━━━━━━━━━━━━━━━\n"
            "✅ Payment Approved\n"
            "✅ Code Delivered"
        )

    elif status == "Payment Verification":
        payment_status = "🔍 Payment Verification"

        delivery_section = (
            "\n📦 DELIVERY\n"
            "━━━━━━━━━━━━━━━━\n"
            "⏳ Waiting for payment approval"
        )

        final_status = (
            "\n📌 FINAL STATUS\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔍 Payment Verification Pending"
        )

    elif status == "Rejected":
        payment_status = "❌ Rejected"

        delivery_section = (
            "\n📦 DELIVERY\n"
            "━━━━━━━━━━━━━━━━\n"
            "❌ Code Not Delivered"
        )

        final_status = (
            "\n📌 FINAL STATUS\n"
            "━━━━━━━━━━━━━━━━\n"
            "❌ Payment Rejected\n"
            f"📌 Reason: {rejection_reason or 'Not recorded'}\n"
            f"🕒 Rejected At: {rejected_at or 'N/A'}"
        )

    elif status == "Cancelled":
        payment_status = "❌ Cancelled"

        delivery_section = (
            "\n📦 DELIVERY\n"
            "━━━━━━━━━━━━━━━━\n"
            "❌ Order Cancelled"
        )

        final_status = (
            "\n📌 FINAL STATUS\n"
            "━━━━━━━━━━━━━━━━\n"
            "❌ Order Cancelled\n"
            f"📌 Reason: {rejection_reason or 'Payment timeout'}\n"
            f"🕒 Cancelled At: {rejected_at or 'N/A'}"
        )

    else:
        payment_status = "⏳ Pending"

        delivery_section = (
            "\n📦 DELIVERY\n"
            "━━━━━━━━━━━━━━━━\n"
            "⏳ Not Delivered Yet"
        )

        final_status = (
            "\n📌 FINAL STATUS\n"
            "━━━━━━━━━━━━━━━━\n"
            "⏳ Payment Pending"
        )

    # ---------------- ORDER DETAILS ----------------

    text = (
        "📋 COMPLETE ORDER DETAILS\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"🆔 Order ID: `{order_id}`\n"
        f"👤 User ID: {user_id}\n"
        f"👤 Username: {username}\n"
        f"🛍️ Product: {reward_name}\n"
        f"📦 Quantity: {quantity}\n"
        f"💰 Price: ₹{float(price):g} / code\n"
        f"💵 Total: ₹{float(total):g}\n\n"
        "💳 PAYMENT DETAILS\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🔢 UTR: {utr or 'Not submitted'}\n"
        f"📸 Screenshot: {screenshot_status}\n"
        f"💳 Payment Status: {payment_status}\n\n"
        "🕒 ORDER TIMELINE\n"
        "━━━━━━━━━━━━━━━━\n"
        f"Created: {order_time or 'N/A'}\n"
    )

    text += delivery_section
    text += final_status

    # ---------------- BUTTONS ----------------

    keyboard = []

    # Approve/Reject ONLY when screenshot is submitted
    # and payment is waiting for verification.
    if status == "Payment Verification":
        keyboard.append([
            InlineKeyboardButton(
                "✅ Approve",
                callback_data=f"paid_approve_{order_id}"
            ),
            InlineKeyboardButton(
                "❌ Reject",
                callback_data=f"paid_reject_{order_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Orders",
            callback_data="admin_requests"
        )
    ])

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def admin_order_search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    context.user_data["admin_order_search"] = True

    await query.edit_message_text(
        "🔎 SEARCH ORDER\n\n"
        "Please send the Order ID:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Orders", callback_data="admin_requests")]
        ])
    )


async def admin_order_search_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if not context.user_data.get("admin_order_search"):
        return

    order_id = update.message.text.strip().upper()
    context.user_data.pop("admin_order_search", None)

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM paid_orders WHERE order_id=?",
        (order_id,)
    )
    found = cur.fetchone()
    conn.close()

    if not found:
        await update.message.reply_text(
            "❌ Order not found.\n\n"
            f"🆔 Order ID: `{order_id}`"
        )
        return

    await update.message.reply_text(
        "✅ Order found.\n\n"
        "👇 Tap below to view full details:",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    f"📋 {order_id}",
                    callback_data=f"paid_admin_order_{order_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Orders",
                    callback_data="admin_requests"
                )
            ]
        ])
    )


async def admin_user_orders_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    context.user_data["admin_user_orders_search"] = True

    await query.edit_message_text(
        "👤 USER ORDER HISTORY\n\n"
        "Please send the User ID:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Orders", callback_data="admin_requests")]
        ])
    )


async def admin_order_input_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("admin_user_orders_search"):
        await admin_user_orders_message(update, context)
        return

    if context.user_data.get("admin_order_search"):
        await admin_order_search_message(update, context)
        return


async def admin_user_orders_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if not context.user_data.get("admin_user_orders_search"):
        return

    user_id_text = update.message.text.strip()

    try:
        user_id = int(user_id_text)
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid User ID.\n\n"
            "Please send a numeric User ID."
        )
        return

    context.user_data.pop("admin_user_orders_search", None)

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        """
        SELECT order_id, reward_name, quantity, total, status, order_time
        FROM paid_orders
        WHERE user_id=?
        ORDER BY id DESC
        """,
        (user_id,)
    )
    orders = cur.fetchall()

    cur.execute(
        "SELECT username FROM users WHERE user_id=?",
        (user_id,)
    )
    user_row = cur.fetchone()

    cur.execute(
        """
        SELECT COALESCE(SUM(total), 0)
        FROM paid_orders
        WHERE user_id=? AND status='Approved'
        """,
        (user_id,)
    )
    total_spent = cur.fetchone()[0] or 0

    conn.close()

    if not orders:
        await update.message.reply_text(
            "👤 USER ORDER HISTORY\n\n"
            f"🆔 User ID: {user_id}\n\n"
            "❌ No orders found."
        )
        return

    username = user_row[0] if user_row and user_row[0] else None

    text = (
        "👤 USER ORDER HISTORY\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"🆔 User ID: {user_id}\n"
    )

    if username:
        text += f"📛 Username: @{username}\n"

    text += (
        f"\n🛒 Total Orders: {len(orders)}\n"
        f"💰 Total Spent: ₹{float(total_spent):g}\n\n"
    )

    keyboard = []

    for order_id, reward_name, quantity, total, status, order_time in orders:
        text += (
            f"🆔 {order_id}\n"
            f"🛍️ {reward_name}\n"
            f"📦 Qty: {quantity}\n"
            f"💰 ₹{float(total):g}\n"
            f"📌 {status}\n"
            f"🕒 {order_time or 'N/A'}\n"
            "━━━━━━━━━━━━━━━━\n"
        )

        keyboard.append([
            InlineKeyboardButton(
                f"📋 {order_id}",
                callback_data=f"paid_admin_order_{order_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton("⬅️ Orders", callback_data="admin_requests")
    ])

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )



async def admin_today_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            COALESCE(SUM(total), 0),
            COALESCE(SUM(quantity), 0)
        FROM paid_orders
        WHERE status='Approved'
        AND date(order_time) = date('now', 'localtime')
        """
    )
    sales, codes = cur.fetchone()

    cur.execute(
        """
        SELECT COALESCE(SUM(po.quantity * COALESCE(pc.cost, 0)), 0)
        FROM paid_orders po
        LEFT JOIN product_costs pc
        ON po.reward_id = pc.reward_id
        WHERE po.status='Approved'
        AND date(po.order_time) = date('now', 'localtime')
        """
    )
    cost = cur.fetchone()[0] or 0

    conn.close()

    profit = float(sales or 0) - float(cost)

    text = (
        "📅 TODAY SALES & PROFIT\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"🛒 Codes Sold: {codes or 0}\n"
        f"💰 Sales: ₹{float(sales or 0):g}\n"
        f"💸 Cost: ₹{float(cost):g}\n"
        f"📈 Profit: ₹{profit:g}"
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔄 Refresh",
                    callback_data="admin_today_sales"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Stats",
                    callback_data="admin_stats"
                )
            ]
        ])
    )


async def admin_lifetime_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            COALESCE(SUM(total), 0),
            COALESCE(SUM(quantity), 0)
        FROM paid_orders
        WHERE status='Approved'
        """
    )
    sales, codes = cur.fetchone()

    cur.execute(
        """
        SELECT COALESCE(SUM(po.quantity * COALESCE(pc.cost, 0)), 0)
        FROM paid_orders po
        LEFT JOIN product_costs pc
        ON po.reward_id = pc.reward_id
        WHERE po.status='Approved'
        """
    )
    cost = cur.fetchone()[0] or 0

    conn.close()

    profit = float(sales or 0) - float(cost)

    text = (
        "♾️ LIFETIME SALES & PROFIT\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"🛒 Codes Sold: {codes or 0}\n"
        f"💰 Sales: ₹{float(sales or 0):g}\n"
        f"💸 Cost: ₹{float(cost):g}\n"
        f"📈 Profit: ₹{profit:g}"
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔄 Refresh",
                    callback_data="admin_lifetime_sales"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Stats",
                    callback_data="admin_stats"
                )
            ]
        ])
    )


async def admin_product_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            po.reward_id,
            po.reward_name,
            COALESCE(SUM(po.quantity), 0),
            COALESCE(SUM(po.total), 0),
            COALESCE(pc.cost, 0)
        FROM paid_orders po
        LEFT JOIN product_costs pc
        ON po.reward_id = pc.reward_id
        WHERE po.status='Approved'
        GROUP BY po.reward_id, po.reward_name
        ORDER BY SUM(po.total) DESC
        """
    )

    rows = cur.fetchall()
    conn.close()

    if not rows:
        text = (
            "🏆 PRODUCT-WISE SALES\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "❌ No approved sales yet."
        )
    else:
        parts = [
            "🏆 PRODUCT-WISE SALES",
            "━━━━━━━━━━━━━━━━",
            ""
        ]

        for reward_id, name, codes_sold, sales, cost_per_code in rows:
            total_cost = float(codes_sold) * float(cost_per_code or 0)
            profit = float(sales or 0) - total_cost

            parts.append(
                f"🛍️ {name}\n"
                f"📦 Codes Sold: {codes_sold}\n"
                f"💰 Sales: ₹{float(sales or 0):g}\n"
                f"📈 Profit: ₹{profit:g}\n"
                "━━━━━━━━━━━━━━━━"
            )

        text = "\n".join(parts)

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔄 Refresh",
                    callback_data="admin_product_sales"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Stats",
                    callback_data="admin_stats"
                )
            ]
        ])
    )



async def admin_cost_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        """
        SELECT r.id, r.name, r.price, COALESCE(pc.cost, 0)
        FROM rewards r
        LEFT JOIN product_costs pc
        ON r.id = pc.reward_id
        WHERE r.mode='paid'
        ORDER BY r.id
        """
    )
    rows = cur.fetchall()
    conn.close()

    keyboard = []

    for reward_id, name, price, cost in rows:
        keyboard.append([
            InlineKeyboardButton(
                f"🛍️ {name} • Cost ₹{float(cost):g}",
                callback_data=f"admin_cost_{reward_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Admin Panel",
            callback_data="admin_back"
        )
    ])

    await query.edit_message_text(
        "💸 COST SETTINGS\n\n"
        "Select a product to set its internal cost price.\n\n"
        "⚠️ Cost price is used only for profit calculation.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def admin_cost_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    try:
        reward_id = int(query.data.replace("admin_cost_", "", 1))
    except (ValueError, AttributeError):
        await query.edit_message_text("❌ Invalid product.")
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT name, price FROM rewards WHERE id=? AND mode='paid'",
        (reward_id,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        await query.edit_message_text("❌ Product not found.")
        return

    name, price = row

    context.user_data["admin_cost_reward_id"] = reward_id

    await query.edit_message_text(
        "💸 SET PRODUCT COST\n\n"
        f"🛍️ Product: {name}\n"
        f"💰 Selling Price: ₹{float(price):g}\n\n"
        "Send the cost price per code.\n\n"
        "Example: 4\n\n"
        "❌ Cancel: /cancel"
    )


async def admin_cost_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    context.user_data.pop("admin_cost_reward_id", None)
    context.user_data.pop("reward_action", None)
    await update.message.reply_text("❌ Action cancelled.")

async def admin_cost_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    reward_id = context.user_data.get("admin_cost_reward_id")

    if not reward_id:
        return

    value = update.message.text.strip()

    if value.lower() == "/cancel":
        context.user_data.pop("admin_cost_reward_id", None)

        await update.message.reply_text(
            "❌ Cost update cancelled."
        )
        return

    try:
        cost = float(value)
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid cost.\n\n"
            "Send only a number.\n"
            "Example: 4"
        )
        return

    if cost < 0:
        await update.message.reply_text(
            "❌ Cost cannot be negative."
        )
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO product_costs(reward_id, cost)
        VALUES(?, ?)
        ON CONFLICT(reward_id)
        DO UPDATE SET cost=excluded.cost
        """,
        (reward_id, cost)
    )

    conn.commit()
    conn.close()

    context.user_data.pop("admin_cost_reward_id", None)

    await update.message.reply_text(
        "✅ COST UPDATED\n\n"
        f"💸 Cost Price: ₹{cost:g} / code\n\n"
        "This cost will be used for profit calculations."
    )

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    data = query.data

    if data == "admin_users":
        conn = sqlite3.connect("users.db")
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        total = cur.fetchone()[0]
        conn.close()

        text = f"👥 TOTAL USERS\n\n{total}"

    elif data == "admin_stats":
        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM users")
        users = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM users WHERE verified=1")
        verified = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM paid_orders")
        total_orders = cur.fetchone()[0]

        cur.execute(
            """
            SELECT COUNT(*)
            FROM paid_orders
            WHERE status IN ('Pending', 'UTR Submitted', 'Payment Verification')
            """
        )
        pending_orders = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM paid_orders WHERE status='Approved'"
        )
        approved_orders = cur.fetchone()[0]

        cur.execute(
            """
            SELECT COALESCE(SUM(total), 0)
            FROM paid_orders
            WHERE status='Approved'
            """
        )
        total_sales = cur.fetchone()[0] or 0

        cur.execute(
            """
            SELECT COALESCE(SUM(total), 0)
            FROM paid_orders
            WHERE status='Approved'
            AND date(order_time) = date('now', 'localtime')
            """
        )
        today_sales = cur.fetchone()[0] or 0

        cur.execute(
            "SELECT COALESCE(SUM(stock), 0) FROM rewards"
        )
        total_stock = cur.fetchone()[0] or 0

        conn.close()

        keyboard = [
            [
                InlineKeyboardButton(
                    "📅 Today Sales",
                    callback_data="admin_today_sales"
                ),
                InlineKeyboardButton(
                    "♾️ Lifetime Sales",
                    callback_data="admin_lifetime_sales"
                )
            ],
            [
                InlineKeyboardButton(
                    "🏆 Product-wise Sales",
                    callback_data="admin_product_sales"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Admin Panel",
                    callback_data="admin_back"
                )
            ]
        ]

        text = (
            "📊 OPx SHOP STATS\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"👥 Total Users: {users}\n"
            f"✅ Verified Users: {verified}\n\n"
            f"🛒 Total Orders: {total_orders}\n"
            f"⏳ Pending Orders: {pending_orders}\n"
            f"✅ Approved Orders: {approved_orders}\n\n"
            f"📅 Today Sales: ₹{float(today_sales):g}\n"
            f"♾️ Lifetime Sales: ₹{float(total_sales):g}\n\n"
            f"📦 Available Stock: {total_stock} codes\n\n"
            "👇 Choose analytics:"
        )

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif data == "admin_rewards":
        keyboard = [
            [
                InlineKeyboardButton(
                    "➕ Add Product",
                    callback_data="reward_add"
                ),
                InlineKeyboardButton(
                    "✏️ Edit Product",
                    callback_data="reward_edit"
                )
            ],
            [
                InlineKeyboardButton(
                    "🗑️ Delete Product",
                    callback_data="reward_delete"
                ),
                InlineKeyboardButton(
                    "📋 Product List",
                    callback_data="reward_list"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔀 Reorder Products",
                    callback_data="reward_reorder"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Admin Panel",
                    callback_data="admin_back"
                )
            ]
        ]

        await query.edit_message_text(
            "🛍️ PRODUCT MANAGEMENT\n\n"
            "Manage your paid products from here.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif data == "admin_stock":
        text = (
            "📦 STOCK CONTROL\n\n"
            "➕ Add multiple reward codes below.\n"
            "📊 Stock can also be updated with /setstock."
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Codes", callback_data="admin_addcodes")],
            [InlineKeyboardButton("📋 Available Codes", callback_data="admin_available_codes")],
            [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_back")]
        ])
        await query.edit_message_text(text, reply_markup=keyboard)
        return

    elif data == "admin_available_codes":
        if not is_admin(query.from_user.id):
            return

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name, stock
            FROM rewards
            WHERE mode='paid'
            ORDER BY id
        """)
        products = cur.fetchall()
        conn.close()

        keyboard = []

        for reward_id, name, stock in products:
            conn2 = sqlite3.connect("users.db")
            cur2 = conn2.cursor()
            cur2.execute("""
                SELECT COUNT(*)
                FROM reward_codes
                WHERE reward_name=? AND used=0
            """, (name,))
            available = cur2.fetchone()[0]
            conn2.close()

            keyboard.append([
                InlineKeyboardButton(
                    f"📦 {name} • {available}",
                    callback_data=f"admin_available_product_{reward_id}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton("⬅️ Stock", callback_data="admin_stock")
        ])

        text = (
            "📋 AVAILABLE CODES\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "Select a paid product:\n\n"
            "Number shown = unused codes"
        )

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif data.startswith("admin_available_product_"):
        if not is_admin(query.from_user.id):
            return

        try:
            reward_id = int(data.rsplit("_", 1)[1])
        except ValueError:
            await query.answer("❌ Invalid product.", show_alert=True)
            return

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute("""
            SELECT name, stock
            FROM rewards
            WHERE id=? AND mode='paid'
        """, (reward_id,))
        product = cur.fetchone()

        if not product:
            conn.close()
            await query.answer("❌ Product not found.", show_alert=True)
            return

        reward_name, stock = product

        cur.execute("""
            SELECT id, code
            FROM reward_codes
            WHERE reward_name=? AND used=0
            ORDER BY id
        """, (reward_name,))
        codes = cur.fetchall()
        conn.close()

        text = (
            f"📦 {reward_name}\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"📊 Available Codes: {len(codes)}\n"
            f"📦 Current Stock: {stock}\n\n"
        )

        if codes:
            text += "🔐 Codes:\n\n"
            for i, (code_id, code) in enumerate(codes, 1):
                text += f"{i}. `{code}`\n"
        else:
            text += "❌ No unused codes available.\n"

        keyboard = []

        for i, (code_id, code) in enumerate(codes, 1):
            label = str(code)
            if len(label) > 25:
                label = label[:22] + "..."
            keyboard.append([
                InlineKeyboardButton(
                    f"✅ Mark Used {i}: {label}",
                    callback_data=f"admin_code_used_{reward_id}_{code_id}"
                )
            ])

        if codes:
            keyboard.append([
                InlineKeyboardButton(
                    "❌ Mark All Used",
                    callback_data=f"admin_code_markall_{reward_id}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "🔄 Refresh",
                callback_data=f"admin_available_product_{reward_id}"
            ),
            InlineKeyboardButton(
                "⬅️ Products",
                callback_data="admin_available_codes"
            )
        ])

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif data.startswith("admin_code_used_"):
        if not is_admin(query.from_user.id):
            return

        parts = data.split("_")
        if len(parts) != 5:
            await query.answer("❌ Invalid code.", show_alert=True)
            return

        try:
            reward_id = int(parts[3])
            code_id = int(parts[4])
        except ValueError:
            await query.answer("❌ Invalid code.", show_alert=True)
            return

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute("""
            SELECT name
            FROM rewards
            WHERE id=? AND mode='paid'
        """, (reward_id,))
        product = cur.fetchone()

        if not product:
            conn.close()
            await query.answer("❌ Product not found.", show_alert=True)
            return

        reward_name = product[0]

        cur.execute("""
            SELECT code
            FROM reward_codes
            WHERE id=? AND reward_name=? AND used=0
        """, (code_id, reward_name))
        code_row = cur.fetchone()

        if not code_row:
            conn.close()
            await query.answer("⚠️ Code already used.", show_alert=True)
            return

        cur.execute("""
            UPDATE reward_codes
            SET used=1
            WHERE id=? AND reward_name=? AND used=0
        """, (code_id, reward_name))

        if cur.rowcount != 1:
            conn.rollback()
            conn.close()
            await query.answer("⚠️ Code already used.", show_alert=True)
            return

        cur.execute("""
            UPDATE rewards
            SET stock = CASE
                WHEN stock > 0 THEN stock - 1
                ELSE 0
            END
            WHERE id=? AND mode='paid'
        """, (reward_id,))

        conn.commit()
        conn.close()

        await query.answer("✅ Code marked as used.")

        # Refresh product screen
        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute("""
            SELECT name, stock
            FROM rewards
            WHERE id=? AND mode='paid'
        """, (reward_id,))
        product = cur.fetchone()

        if not product:
            conn.close()
            await query.edit_message_text(
                "❌ Product not found.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Products", callback_data="admin_available_codes")]
                ])
            )
            return

        reward_name, stock = product

        cur.execute("""
            SELECT id, code
            FROM reward_codes
            WHERE reward_name=? AND used=0
            ORDER BY id
        """, (reward_name,))
        codes = cur.fetchall()
        conn.close()

        text = (
            f"📦 {reward_name}\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"📊 Available Codes: {len(codes)}\n"
            f"📦 Current Stock: {stock}\n\n"
        )

        if codes:
            text += "🔐 Codes:\n\n"
            for i, (unused_id, code) in enumerate(codes, 1):
                text += f"{i}. `{code}`\n"
        else:
            text += "❌ No unused codes available.\n"

        keyboard = []

        for i, (unused_id, code) in enumerate(codes, 1):
            label = str(code)
            if len(label) > 25:
                label = label[:22] + "..."
            keyboard.append([
                InlineKeyboardButton(
                    f"✅ Mark Used {i}: {label}",
                    callback_data=f"admin_code_used_{reward_id}_{unused_id}"
                )
            ])

        if codes:
            keyboard.append([
                InlineKeyboardButton(
                    "❌ Mark All Used",
                    callback_data=f"admin_code_markall_{reward_id}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "🔄 Refresh",
                callback_data=f"admin_available_product_{reward_id}"
            ),
            InlineKeyboardButton(
                "⬅️ Products",
                callback_data="admin_available_codes"
            )
        ])

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif data.startswith("admin_code_markall_"):
        if not is_admin(query.from_user.id):
            return

        try:
            reward_id = int(data.rsplit("_", 1)[1])
        except ValueError:
            await query.answer("❌ Invalid product.", show_alert=True)
            return

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute("""
            SELECT name
            FROM rewards
            WHERE id=? AND mode='paid'
        """, (reward_id,))
        product = cur.fetchone()

        if not product:
            conn.close()
            await query.answer("❌ Product not found.", show_alert=True)
            return

        reward_name = product[0]

        cur.execute("""
            UPDATE reward_codes
            SET used=1
            WHERE reward_name=? AND used=0
        """, (reward_name,))

        marked_count = cur.rowcount

        cur.execute("""
            UPDATE rewards
            SET stock=0
            WHERE id=? AND mode='paid'
        """, (reward_id,))

        conn.commit()
        conn.close()

        await query.answer(
            f"✅ {marked_count} codes marked as used."
        )

        # Show refreshed product screen
        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute("""
            SELECT name, stock
            FROM rewards
            WHERE id=? AND mode='paid'
        """, (reward_id,))
        product = cur.fetchone()

        if not product:
            conn.close()
            await query.edit_message_text(
                "❌ Product not found.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Products", callback_data="admin_available_codes")]
                ])
            )
            return

        reward_name, stock = product

        cur.execute("""
            SELECT id, code
            FROM reward_codes
            WHERE reward_name=? AND used=0
            ORDER BY id
        """, (reward_name,))
        codes = cur.fetchall()
        conn.close()

        text = (
            f"📦 {reward_name}\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"📊 Available Codes: {len(codes)}\n"
            f"📦 Current Stock: {stock}\n\n"
        )

        if codes:
            text += "🔐 Codes:\n\n"
            for i, (unused_id, code) in enumerate(codes, 1):
                text += f"{i}. `{code}`\n"
        else:
            text += "❌ No unused codes available.\n"

        keyboard = []

        for i, (unused_id, code) in enumerate(codes, 1):
            label = str(code)
            if len(label) > 25:
                label = label[:22] + "..."
            keyboard.append([
                InlineKeyboardButton(
                    f"✅ Mark Used {i}: {label}",
                    callback_data=f"admin_code_used_{reward_id}_{unused_id}"
                )
            ])

        if codes:
            keyboard.append([
                InlineKeyboardButton(
                    "❌ Mark All Used",
                    callback_data=f"admin_code_markall_{reward_id}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "🔄 Refresh",
                callback_data=f"admin_available_product_{reward_id}"
            ),
            InlineKeyboardButton(
                "⬅️ Products",
                callback_data="admin_available_codes")
        ])

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif data == "admin_pending_orders":
        if not is_admin(query.from_user.id):
            return

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute(
            """
            SELECT order_id, reward_name, quantity, total
            FROM paid_orders
            WHERE status='Payment Verification'
            ORDER BY id DESC
            """
        )
        rows = cur.fetchall()
        conn.close()

        if not rows:
            await query.answer("📭 No Pending Orders", show_alert=True)

            await query.edit_message_text(
                "📭 NO PENDING ORDERS\n\n"
                "✅ All payment verification orders have been processed.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🔄 Refresh",
                            callback_data="admin_pending_orders"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "⬅️ Admin Panel",
                            callback_data="admin_back"
                        )
                    ]
                ])
            )
            return

        text = (
            "📋 PENDING ORDERS\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"⏳ {len(rows)} order(s) waiting for approval.\n\n"
        )

        keyboard = []

        for order_id, reward_name, quantity, total in rows:
            text += (
                f"🆔 `{order_id}`\n"
                f"🛍️ {reward_name}\n"
                f"📦 Qty: {quantity} • 💰 ₹{float(total):g}\n"
                "━━━━━━━━━━━━━━━━\n"
            )

            keyboard.append([
                InlineKeyboardButton(
                    f"✅ Approve {order_id}",
                    callback_data=f"paid_approve_{order_id}"
                ),
                InlineKeyboardButton(
                    f"❌ Reject {order_id}",
                    callback_data=f"paid_reject_{order_id}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "🔄 Refresh",
                callback_data="admin_pending_orders"
            )
        ])

        keyboard.append([
            InlineKeyboardButton(
                "⬅️ Admin Panel",
                callback_data="admin_back"
            )
        ])

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif data == "admin_requests":
        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute(
            """
            SELECT order_id, reward_name, quantity, total, status
            FROM paid_orders
            WHERE status IN ('Pending', 'UTR Submitted', 'Payment Verification')
            ORDER BY id DESC
            LIMIT 30
            """
        )
        rows = cur.fetchall()
        conn.close()

        keyboard = [
            [
                InlineKeyboardButton(
                    "🔎 Search Order ID",
                    callback_data="admin_order_search"
                )
            ],
            [
                InlineKeyboardButton(
                    "👤 Search User ID",
                    callback_data="admin_user_orders"
                )
            ]
        ]

        for order_id, reward_name, quantity, total, status in rows:
            keyboard.append([
                InlineKeyboardButton(
                    f"🆔 {order_id} • ₹{float(total):g} • {status}",
                    callback_data=f"paid_admin_order_{order_id}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "🔄 Refresh",
                callback_data="admin_requests"
            )
        ])
        keyboard.append([
            InlineKeyboardButton(
                "⬅️ Admin Panel",
                callback_data="admin_back"
            )
        ])

        if rows:
            text = (
                "📋 ORDER MANAGEMENT\n"
                "━━━━━━━━━━━━━━━━\n\n"
                "🔎 Search any Order ID\n"
                "👤 View orders by User ID\n\n"
                "⏳ Pending Orders:\n"
                "👇 Select an order:"
            )
        else:
            text = (
                "📋 ORDER MANAGEMENT\n"
                "━━━━━━━━━━━━━━━━\n\n"
                "🔎 Search any Order ID\n"
                "👤 View orders by User ID\n\n"
                "✅ No pending payment orders."
            )

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif data == "admin_approval":
        text = (
            "🔐 APPROVAL ADMIN\n\n"
            f"Current ID: {get_approval_admin()}\n\n"
            "Change with:\n"
            "/setapprovaladmin USER_ID"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "⬅️ Admin Panel",
                    callback_data="admin_back"
                )
            ]
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif data == "admin_maintenance":
        status = "🟢 ON" if MAINTENANCE_MODE else "🔴 OFF"
        text = (
            "🛠️ MAINTENANCE MODE\n\n"
            f"Current Status: {status}\n\n"
            "Use the buttons below to change maintenance mode."
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🟢 Turn ON", callback_data="maintenance_on"),
                InlineKeyboardButton("🔴 Turn OFF", callback_data="maintenance_off")
            ],
            [
                InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_back")
            ]
        ])
        await query.edit_message_text(text, reply_markup=keyboard)
        return

    else:
        text = "❌ Unknown option."

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_back")]
        ])
    )


async def maintenance_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE

    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    if query.data == "maintenance_on":
        MAINTENANCE_MODE = True
        status = "🟢 ON"
    else:
        MAINTENANCE_MODE = False
        status = "🔴 OFF"

    await query.edit_message_text(
        f"🛠️ MAINTENANCE MODE UPDATED\n\n"
        f"Current Status: {status}\n\n"
        "Admin panel se dobara check kar sakte ho.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_back")]
        ])
    )



async def admin_features(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    buy = get_feature_setting("buy_points_enabled", "1") == "1"
    claim = get_feature_setting("claim_reward_enabled", "1") == "1"

    keyboard = [
        [
            InlineKeyboardButton(
                f"💰 Buy Points: {'🟢 ON' if buy else '🔴 OFF'}",
                callback_data="feature_toggle_buy"
            )
        ],
        [
            InlineKeyboardButton(
                f"🎁 Claim Reward: {'🟢 ON' if claim else '🔴 OFF'}",
                callback_data="feature_toggle_claim"
            )
        ],
        [
            InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_back")
        ]
    ]

    await query.edit_message_text(
        "⚙️ FEATURE CONTROL\n\n"
        "Yahan se user features ON/OFF kar sakte ho.\n\n"
        f"💰 Buy Points: {'🟢 ON' if buy else '🔴 OFF'}\n"
        f"🎁 Claim Reward: {'🟢 ON' if claim else '🔴 OFF'}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def feature_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer()
        return

    mapping = {
        "feature_toggle_buy": "buy_points_enabled",
        "feature_toggle_claim": "claim_reward_enabled"
    }

    key = mapping.get(query.data)

    if not key:
        await query.answer()
        return

    current = get_feature_setting(key, "1")
    new_value = "0" if current == "1" else "1"

    set_feature_setting(key, new_value)

    status = "🟢 ON" if new_value == "1" else "🔴 OFF"

    await query.answer(f"Updated: {status}")

    buy = get_feature_setting("buy_points_enabled", "1") == "1"
    claim = get_feature_setting("claim_reward_enabled", "1") == "1"

    keyboard = [
        [
            InlineKeyboardButton(
                f"💰 Buy Points: {'🟢 ON' if buy else '🔴 OFF'}",
                callback_data="feature_toggle_buy"
            )
        ],
        [
            InlineKeyboardButton(
                f"🎁 Claim Reward: {'🟢 ON' if claim else '🔴 OFF'}",
                callback_data="feature_toggle_claim"
            )
        ],
        [
            InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_back")
        ]
    ]

    await query.edit_message_text(
        "⚙️ FEATURE CONTROL\n\n"
        f"💰 Buy Points: {'🟢 ON' if buy else '🔴 OFF'}\n"
        f"🎁 Claim Reward: {'🟢 ON' if claim else '🔴 OFF'}\n\n"
        f"Last changed: {status}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def admin_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id, username FROM bot_admins ORDER BY user_id")
    admins = cur.fetchall()
    conn.close()
    text = "👑 ADMIN MANAGEMENT\n\n"
    for user_id, username in admins:
        if user_id == ADMIN_ID:
            text += f"👑 OWNER\n🆔 {user_id}\n\n"
        else:
            text += f"👤 ADMIN\n🆔 {user_id}\nUsername: @{username or "Unknown"}\n\n"
    keyboard = [[InlineKeyboardButton("➕ Add Admin", callback_data="admin_add")],[InlineKeyboardButton("🗑️ Remove Admin", callback_data="admin_remove")],[InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    context.user_data["admin_action"] = "add"
    await query.edit_message_text("➕ ADD ADMIN\n\nTelegram User ID bhejo.\n\nExample: 123456789\n\n❌ Cancel: /cancel")


async def admin_remove_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id, username FROM bot_admins WHERE user_id != ? ORDER BY user_id", (ADMIN_ID,))
    admins = cur.fetchall()
    conn.close()
    if not admins:
        await query.edit_message_text("❌ No additional admins found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Management", callback_data="admin_management")]]))
        return
    keyboard = []
    for user_id, username in admins:
        keyboard.append([InlineKeyboardButton(f"🗑️ {user_id} (@{username or "Unknown"})", callback_data=f"admin_delete_{user_id}")])
    keyboard.append([InlineKeyboardButton("⬅️ Admin Management", callback_data="admin_management")])
    await query.edit_message_text("🗑️ REMOVE ADMIN\n\nJis admin ko remove karna hai us par tap karo:", reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    user_id = int(query.data.replace("admin_delete_", ""))
    if user_id == ADMIN_ID:
        await query.answer("🔒 Main owner ko remove nahi kiya ja sakta.", show_alert=True)
        return
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM bot_admins WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    await query.answer("✅ Admin removed.")
    await admin_management(update, context)


async def admin_management_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    if context.user_data.get("admin_action") == "broadcast":
        text = update.message.text.strip()
        if text == "/cancel":
            context.user_data.pop("admin_action", None)
            await update.message.reply_text("Broadcast cancelled.")
            return
        context.user_data.pop("admin_action", None)
        conn = sqlite3.connect("users.db")
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE blocked=0")
        users = cur.fetchall()
        conn.close()
        await update.message.reply_text(f"Broadcast started... Recipients: {len(users)}")
        success = 0
        failed = 0
        for (user_id,) in users:
            try:
                await context.bot.send_message(chat_id=user_id, text=text)
                success += 1
            except Exception:
                failed += 1
        await update.message.reply_text(f"BROADCAST COMPLETED\n\nTotal: {len(users)}\nSent: {success}\nFailed: {failed}")
        return

    if context.user_data.get("admin_action") != "add":
        return
    text = update.message.text.strip()
    if text == "/cancel":
        context.user_data.pop("admin_action", None)
        await update.message.reply_text("❌ Cancelled.")
        return
    try:
        user_id = int(text)
    except ValueError:
        await update.message.reply_text("❌ Valid Telegram User ID bhejo.")
        return
    if user_id == ADMIN_ID:
        await update.message.reply_text("👑 Ye already owner hai.")
        return
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT username FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    username = row[0] if row else None
    cur.execute("INSERT OR IGNORE INTO bot_admins(user_id, username, added_by) VALUES(?,?,?)", (user_id, username, ADMIN_ID))
    conn.commit()
    conn.close()
    context.user_data.pop("admin_action", None)
    await update.message.reply_text(f"✅ ADMIN ADDED\n\n🆔 {user_id}\n👤 @{username or "Unknown"}")


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    context.user_data["admin_action"] = "broadcast"

    await query.edit_message_text(
        "BROADCAST\n\n"
        "Apna message bhejo.\n\n"
        "Cancel: /cancel"
    )



async def admin_start_shop_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT)")
    cur.execute("SELECT value FROM bot_settings WHERE key=?", ("start_shop_enabled",))
    row = cur.fetchone()
    current = row[0] if row else "0"
    new_value = "0" if current == "1" else "1"
    cur.execute("INSERT OR REPLACE INTO bot_settings(key,value) VALUES(?,?)", ("start_shop_enabled", new_value))
    conn.commit()
    conn.close()
    status = "🟢 ON" if new_value == "1" else "🔴 OFF"
    await query.edit_message_text(f"🛍️ START SHOP\n\nStatus: {status}\n\n🟢 ON = /start directly opens OPx Shop\n🔴 OFF = /start shows the normal menu.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Change", callback_data="admin_start_shop")],[InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_back")]]))

async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    buttons = [
        [
            InlineKeyboardButton("👥 Users", callback_data="admin_users"),
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats")
        ],
        [
            InlineKeyboardButton("🛍️ Products", callback_data="admin_rewards"),
            InlineKeyboardButton("📦 Stock & Codes", callback_data="admin_stock")
        ],
        [
            InlineKeyboardButton("📋 Orders", callback_data="admin_requests"),
            InlineKeyboardButton("🔐 Approval Admin", callback_data="admin_approval")
        ],
        [
            InlineKeyboardButton("💳 Payment Settings", callback_data="admin_payment_settings"),
            InlineKeyboardButton("💸 Cost Settings", callback_data="admin_cost_settings")
        ],
        [
            InlineKeyboardButton("🛠️ Maintenance", callback_data="admin_maintenance")
        ],
        [
            InlineKeyboardButton("📢 Channel Management", callback_data="admin_channels"),
            InlineKeyboardButton("👑 Admin Management", callback_data="admin_management")
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton("🏠 Main Menu", callback_data="main")
        ]
    ]

    await query.edit_message_text(
        "👑 OPx SHOP ADMIN PANEL\n\n"
        "👇 Select an option:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

app.add_handler(CallbackQueryHandler(admin_start_shop_toggle, pattern="^admin_start_shop$"))
app.add_handler(CallbackQueryHandler(admin_broadcast, pattern="^admin_broadcast$"))
app.add_handler(CallbackQueryHandler(admin_management, pattern="^admin_management$"))
app.add_handler(CallbackQueryHandler(admin_add_start, pattern="^admin_add$"))
app.add_handler(CallbackQueryHandler(admin_remove_start, pattern="^admin_remove$"))
app.add_handler(CallbackQueryHandler(admin_delete, pattern="^admin_delete_"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_management_message), group=-6)
app.add_handler(TypeHandler(Update, blocked_user_guard), group=-10)

async def admin_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    channels = get_active_channels()

    text = "📢 CHANNEL MANAGEMENT\n\n"

    if channels:
        for i, (name, username, url) in enumerate(channels, 1):
            text += f"{i}️⃣ {name}\n👤 {username}\n🔗 {url}\n━━━━━━━━━━━━━━\n"
    else:
        text += "❌ No channels found.\n"

    keyboard = [
        [InlineKeyboardButton("➕ Add Channel", callback_data="channel_add")],
        [InlineKeyboardButton("🗑️ Remove Channel", callback_data="channel_remove")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_channels")],
        [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_back")]
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def channel_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    context.user_data["adding_channel"] = True

    await query.edit_message_text(
        "➕ ADD CHANNEL\n\n"
        "Is format me ek line me bhejo:\n\n"
        "Channel Name | @username | https://t.me/channel\n\n"
        "Example:\n"
        "New Channel | @mychannel | https://t.me/mychannel\n\n"
        "Cancel ke liye /cancel bhejo."
    )


async def channel_add_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return

    if not context.user_data.get("adding_channel"):
        return

    text = update.message.text.strip()

    if text == "/cancel":
        context.user_data.pop("adding_channel", None)
        await update.message.reply_text("❌ Channel adding cancelled.")
        return

    parts = [x.strip() for x in text.split("|")]

    if len(parts) != 3:
        await update.message.reply_text(
            "❌ Invalid format.\n\n"
            "Use:\n"
            "Channel Name | @username | https://t.me/channel"
        )
        return

    name, username, url = parts

    if not username.startswith("@"):
        await update.message.reply_text("❌ Username must start with @")
        return

    if not url.startswith("https://t.me/"):
        await update.message.reply_text("❌ Invalid Telegram URL.")
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO bot_channels(name, username, url, active) VALUES(?,?,?,1)",
        (name, username, url)
    )
    conn.commit()
    conn.close()

    context.user_data.pop("adding_channel", None)

    await update.message.reply_text(
        f"✅ CHANNEL ADDED\n\n"
        f"📢 {name}\n"
        f"👤 {username}\n"
        f"🔗 {url}\n"
        f"🟢 Status: ON"
    )


async def channel_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT id, name, username FROM bot_channels ORDER BY id")
    channels = cur.fetchall()
    conn.close()

    if not channels:
        await query.edit_message_text(
            "❌ No channels found.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Channel Management", callback_data="admin_channels")]
            ])
        )
        return

    keyboard = []

    for channel_id, name, username in channels:
        keyboard.append([
            InlineKeyboardButton(
                f"🗑️ {name} ({username})",
                callback_data=f"channel_delete_{channel_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton("⬅️ Channel Management", callback_data="admin_channels")
    ])

    await query.edit_message_text(
        "🗑️ REMOVE CHANNEL\n\n"
        "Jis channel ko remove karna hai us par tap karo:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def channel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    try:
        channel_id = int(query.data.split("_")[-1])
    except ValueError:
        await query.answer("❌ Invalid channel.", show_alert=True)
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT name, username FROM bot_channels WHERE id=?",
        (channel_id,)
    )
    channel = cur.fetchone()

    if not channel:
        conn.close()
        await query.answer("❌ Channel not found.", show_alert=True)
        return

    cur.execute("DELETE FROM bot_channels WHERE id=?", (channel_id,))
    conn.commit()
    conn.close()

    await query.answer("🗑️ Channel removed.")
    await admin_channels(update, context)



app.add_handler(CallbackQueryHandler(paid_admin_order_detail, pattern=r"^paid_admin_order_[A-Z0-9-]+$"))
app.add_handler(CallbackQueryHandler(admin_channels, pattern="^admin_channels$"))
app.add_handler(CallbackQueryHandler(shop_product, pattern=r"^shop_product_[0-9]+$"))
app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        paid_order_utr
    ),
    group=-20
)

app.add_handler(
    MessageHandler(
        filters.PHOTO,
        paid_order_screenshot
    ),
    group=-20
)

app.add_handler(
    CallbackQueryHandler(
        paid_order_approve,
        pattern=r"^paid_approve_"
    ),
    group=-999
)

app.add_handler(
    CallbackQueryHandler(
        paid_order_reject,
        pattern=r"^paid_reject_[A-Za-z0-9-]+$"
    ),
    group=-999
)

app.add_handler(
    CallbackQueryHandler(
        paid_done,
        pattern=r"^paid_done_"
    ),
    group=-999
)

app.add_handler(
    CallbackQueryHandler(
        paid_reject_reason,
        pattern=r"^paid_reject_reason_"
    ),
    group=-999
)

app.add_handler(
    CallbackQueryHandler(
        paid_reject_other,
        pattern=r"^paid_reject_other_"
    ),
    group=-999
)

app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        paid_reject_other_message
    ),
    group=-999
)

app.add_handler(CallbackQueryHandler(shop_quantity, pattern=r"^shop_qty_[0-9]+_[0-9]+$"))
app.add_handler(CallbackQueryHandler(rewards, pattern=r"^shop$"))
app.add_handler(CallbackQueryHandler(channel_add, pattern="^channel_add$"))
app.add_handler(CallbackQueryHandler(channel_remove, pattern="^channel_remove$"))
app.add_handler(CallbackQueryHandler(channel_delete, pattern=r"^channel_delete_[0-9]+$"))
app.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, channel_add_message),
    group=-3
)

app.add_handler(CallbackQueryHandler(claim_limit_control, pattern="^claim_limit_control$"))
app.add_handler(CallbackQueryHandler(claim_limit_set_start, pattern="^claim_limit_set$"))
app.add_handler(CallbackQueryHandler(claim_limit_unlimited, pattern="^claim_limit_unlimited$"))
app.add_handler(CallbackQueryHandler(claim_limit_current, pattern="^claim_limit_current$"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, claim_limit_message), group=-5)
app.add_handler(
    MessageHandler(
        filters.Regex(r"^(🛍️ Browse Product|📦 My Orders|📞 Support|ℹ️ How It Works)$"),
        user_menu_router
    ),
    group=-11
)
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin_panel))
app.add_handler(CallbackQueryHandler(admin_points_callback, pattern="^admin_(addpoints|removepoints)$"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_points_message))
app.add_handler(CallbackQueryHandler(admin_user_management, pattern="^admin_usermanage$"))
app.add_handler(CallbackQueryHandler(admin_addcodes_callback, pattern="^admin_addcodes$"))
app.add_handler(CallbackQueryHandler(admin_addcodes_reward_select, pattern=r"^admin_addcodes_reward_[0-9]+$"))
app.add_handler(CallbackQueryHandler(admin_reset_points_callback, pattern="^admin_reset_points$"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_router), group=-2)
app.add_handler(CallbackQueryHandler(admin_user_details_callback, pattern="^admin_user_details$"))
app.add_handler(CallbackQueryHandler(admin_block_user_callback, pattern="^admin_block_user$"))
app.add_handler(CallbackQueryHandler(admin_unblock_user_callback, pattern="^admin_unblock_user$"))
app.add_handler(CallbackQueryHandler(admin_blocked_users_callback, pattern="^admin_blocked_users$"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_user_details_message), group=-1)
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_block_user_message), group=-1)
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_unblock_user_message), group=-1)
app.add_handler(CallbackQueryHandler(admin_request_detail, pattern=r"^admin_request_"))
app.add_handler(CallbackQueryHandler(admin_order_search_start, pattern="^admin_order_search$"))
app.add_handler(CallbackQueryHandler(admin_user_orders_start, pattern="^admin_user_orders$"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_order_input_router), group=-7)
app.add_handler(CommandHandler("cancel", admin_cost_cancel))

app.add_handler(CallbackQueryHandler(admin_today_sales, pattern="^admin_today_sales$"))
app.add_handler(CallbackQueryHandler(admin_lifetime_sales, pattern="^admin_lifetime_sales$"))
app.add_handler(CallbackQueryHandler(admin_product_sales, pattern="^admin_product_sales$"))
app.add_handler(CallbackQueryHandler(admin_cost_settings, pattern="^admin_cost_settings$"))
app.add_handler(CallbackQueryHandler(admin_cost_start, pattern=r"^admin_cost_[0-9]+$"))
app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_cost_message
    ),
    group=-20
)
app.add_handler(CallbackQueryHandler(admin_panel_callback, pattern=r"^admin_(users|stats|rewards|stock|requests|pending_orders|approval|maintenance|available_codes|available_product_[0-9]+|code_used_[0-9]+_[0-9]+|code_markall_[0-9]+)$"))
app.add_handler(
    CallbackQueryHandler(
        admin_payment_settings,
        pattern="^admin_payment_settings$"
    )
)
app.add_handler(
    CallbackQueryHandler(
        shop_set_upi_start,
        pattern="^shop_set_upi$"
    )
)

app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        shop_save_upi
    ),
    group=-50
)

app.add_handler(
    CallbackQueryHandler(
        shop_set_qr_start,
        pattern="^shop_set_qr$"
    )
)

app.add_handler(
    MessageHandler(
        filters.PHOTO,
        shop_save_qr
    ),
    group=-5
)

app.add_handler(CallbackQueryHandler(admin_features, pattern="^admin_features$"))
app.add_handler(CallbackQueryHandler(feature_toggle, pattern="^feature_toggle_(buy|claim)$"))
app.add_handler(CallbackQueryHandler(maintenance_toggle, pattern="^maintenance_(on|off)$"))

app.add_handler(CallbackQueryHandler(point_management_menu, pattern="^admin_point_management$"))
app.add_handler(CallbackQueryHandler(point_packages_menu, pattern="^pm_packages$"))
app.add_handler(CallbackQueryHandler(point_package_edit, pattern=r"^pm_package_[0-9]+$"))
app.add_handler(CallbackQueryHandler(point_package_delete, pattern=r"^pm_delete_[0-9]+$"))
app.add_handler(CallbackQueryHandler(point_management_action, pattern=r"^pm_(change_upi|change_time|edit_points_[0-9]+|edit_amount_[0-9]+|add_package)$"))
app.add_handler(CallbackQueryHandler(point_management_current, pattern="^pm_current$"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, point_management_message, ), group=-3)

app.add_handler(CallbackQueryHandler(admin_back, pattern="^admin_back$"))
app.add_handler(CommandHandler("addpoints", add_points))
app.add_handler(CommandHandler("setapprovaladmin", setapprovaladmin))
app.add_handler(CommandHandler("approvaladmin", approvaladmin))
app.add_handler(CallbackQueryHandler(verify, pattern="verify"))
app.add_handler(CallbackQueryHandler(captcha_check, pattern="^captcha_"))

app.add_handler(CallbackQueryHandler(buy_points, pattern="^buy_points$"))
app.add_handler(CallbackQueryHandler(buy_submit_screenshot, pattern="^buy_submit_screenshot$"))
app.add_handler(CallbackQueryHandler(approve_point_purchase, pattern=r"^approve_purchase_[0-9]+$"))
app.add_handler(CallbackQueryHandler(reject_point_purchase, pattern=r"^reject_purchase_[0-9]+$"))

app.add_handler(MessageHandler(filters.PHOTO, buy_screenshot_message))

app.add_handler(CallbackQueryHandler(buy_package, pattern=r"^buy_pkg_(10|20|60|100)_(8|15|45|70)$"))
app.add_handler(CallbackQueryHandler(menu, pattern="main"))




app.add_handler(CallbackQueryHandler(help_center, pattern="^help$"))


app.add_handler(CallbackQueryHandler(rewards, pattern="claim"))
app.add_handler(CallbackQueryHandler(confirm_claim, pattern="^confirm_"))
app.add_handler(CallbackQueryHandler(reward_add_start, pattern="^reward_add$"))
app.add_handler(CallbackQueryHandler(reward_edit_start, pattern="^reward_edit$"))
app.add_handler(CallbackQueryHandler(reward_delete_start, pattern="^reward_delete$"))
app.add_handler(CallbackQueryHandler(reward_list_callback, pattern="^reward_list$"))
app.add_handler(CallbackQueryHandler(reward_reorder_callback, pattern="^reward_reorder$"))
app.add_handler(CallbackQueryHandler(reorder_view_callback, pattern="^reorder_view_[0-9]+$"))
app.add_handler(CallbackQueryHandler(reorder_move_callback, pattern=r"^reorder_(up|down)_[0-9]+$"))
app.add_handler(CallbackQueryHandler(claim_reward, pattern="^reward_"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reward_control_message), group=-4)
app.add_handler(CommandHandler("addreward", addreward))
app.add_handler(CommandHandler("editreward", editreward))
app.add_handler(CommandHandler("delreward", delreward))
app.add_handler(CommandHandler("rewardlist", rewardlist))
app.add_handler(CommandHandler("addcode", addcode))
app.add_handler(CommandHandler("setstock", setstock))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("requests", requests_list))
app.add_handler(CommandHandler("users", users_count))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("createpromo", createpromo))
app.add_handler(CommandHandler("listpromo", listpromo))
app.add_handler(CommandHandler("deletepromo", deletepromo))
app.add_handler(CallbackQueryHandler(approve_request, pattern="^approve_"))
app.add_handler(CallbackQueryHandler(reject_request, pattern="^reject_"))
app.add_handler(CallbackQueryHandler(rewards, pattern="catalog"))
print("Bot V2 Started...")
from flask import Flask
from threading import Thread
import os

web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "Bot is running!"

def run_web():
    web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

Thread(target=run_web).start()
app.run_polling()

