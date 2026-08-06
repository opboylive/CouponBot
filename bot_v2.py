from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import sqlite3
import random
from datetime import datetime

import os

TOKEN = os.environ.get("TOKEN")
ADMIN_ID = 6427806986
APPROVAL_ADMIN = 7892718908
MAINTENANCE_MODE = False

async def approve_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != APPROVAL_ADMIN:
        return

    data = query.data.split("_")
    user_id = int(data[1])
    reward_name = "_".join(data[2:])

    conn = sqlite3.connect("users.db")
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

    conn.commit()
    conn.close()

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

    if query.from_user.id != APPROVAL_ADMIN:
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
        referrals INTEGER DEFAULT 0,
        referred_by INTEGER,
        verified_referrals INTEGER DEFAULT 0,
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

    cur.execute("SELECT COUNT(*) FROM rewards")
    if cur.fetchone()[0] == 0:
        rewards_data = [
            ("Gemini Link", 25, 0),
            ("BigBasket Cashback", 15, 0),
            ("Play Store Redeem Code", 9, 0),
            ("Amazon Gift Card", 9, 0),
            ("Spotify Premium", 5, 0),
            ("Netflix 1 Month", 9, 0),
            ("Myntra 5% OFF Coupon", 6, 10),
            ("Domino's ₹100 Gift Voucher", 60, 10)
        ]

        cur.executemany(
            "INSERT INTO rewards(name, points, stock) VALUES(?,?,?)",
            rewards_data
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
    CREATE TABLE IF NOT EXISTS referral_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_user_id INTEGER,
        referral_time TEXT
    )
    """)
    conn.commit()
    conn.close()
async def human_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    a = random.randint(2, 9)
    b = random.randint(1, 9)

    answer = a + b
    options = [
        answer,
        answer + 2,
        answer - 2
    ]

    random.shuffle(options)

    context.user_data["captcha_answer"] = answer

    buttons = []
    for option in options:
        buttons.append([
            InlineKeyboardButton(
                str(option),
                callback_data=f"captcha_{option}"
            )
        ])

    await query.edit_message_text(
        f"🤖 Human Verification\n\n"
        f"Solve this:\n\n"
        f"{a} + {b} = ?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
async def captcha_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected = int(query.data.replace("captcha_", ""))

    correct = context.user_data.get("captcha_answer")

    if selected == correct:

        conn = sqlite3.connect("users.db")
        cur = conn.cursor()

        cur.execute(
            "UPDATE users SET verified = 1 WHERE user_id=?",
            (query.from_user.id,)
        )

        conn.commit()
        conn.close()

        buttons = [

            [InlineKeyboardButton("🎁 Claim Reward", callback_data="claim")],
            [
                InlineKeyboardButton("👥 Refer & Earn", callback_data="refer"),
                InlineKeyboardButton("👤 Account Info", callback_data="account")
            ],
            [
                InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")
            ],
            [
                InlineKeyboardButton("📜 Claim History", callback_data="history"),
                InlineKeyboardButton("🆘 Support", callback_data="help")
            ]
        ]

        await query.edit_message_text(
            "🎉 WELCOME TO COUPON REWARD HUB 🎉\n\n"
            "👇 Select an option below to proceed:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    else:
        await query.answer(
            "❌ Wrong Answer! Try Again",
            show_alert=True
        )
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")

    cur.execute(
        """
        SELECT u.username, COUNT(*) 
        FROM referral_history r
        JOIN users u ON u.user_id = r.referrer_id
        WHERE r.referral_time LIKE ?
        GROUP BY r.referrer_id
        ORDER BY COUNT(*) DESC
        LIMIT 10
        """,
        (today + "%",)
    )

    users = cur.fetchall()

    if not users:
        text = (
            "🏆 TODAY'S TOP 10 REFERRERS\n\n"
            "😔 No referrals today."
        )
    else:
        text = "🏆 TODAY'S TOP 10 REFERRERS\n\n"

        medals = ["🥇", "🥈", "🥉"]

        for i, (username, referrals) in enumerate(users, start=1):
            name = username[:5] + "****" if username else "User"
            rank = medals[i-1] if i <= 3 else f"{i}️⃣"
            text += f"{rank} {name} — {referrals} Referrals\n"

    cur.execute(
        "SELECT verified_referrals FROM users WHERE user_id=?",
        (query.from_user.id,)
    )

    data = cur.fetchone()
    my_referrals = data[0] if data else 0

    text += (
        "\n━━━━━━━━━━━━━━\n"
        f"👤 Your Referrals: {my_referrals}"
    )

    conn.close()

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
        ])
    )

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("VERIFY CLICKED")

    query = update.callback_query
    await query.answer()

    user = query.from_user

    channels = [
        "@opboyLive",
        "@opboydeals",
        "@OpBoyLive_Chat"
    ]

    print("CHANNEL CHECK START")

    for channel in channels:
        print("Checking:", channel)

        member = await context.bot.get_chat_member(
            chat_id=channel,
            user_id=user.id
        )
        print(channel, member.status)

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
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT referred_by, verified_referrals, verified FROM users WHERE user_id=?",
        (user.id,)
    )

    data = cur.fetchone()

    if (
    data
    and data[0]
    and data[1] == 0
    and data[2] == 0
    and data[0] != user.id
):
        referrer_id = data[0]

        cur.execute(
            "UPDATE users SET points = points + 1, referrals = referrals + 1, verified_referrals = verified_referrals + 1 WHERE user_id=?",
            (referrer_id,)
        )
        cur.execute(
            "INSERT INTO referral_history(referrer_id, referred_user_id, referral_time) VALUES(?,?,?)",
            (
                referrer_id,
                user.id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )

        await context.bot.send_message(
            chat_id=referrer_id,
            text="🎉 New Referral Completed!\n\n💎 You earned +1 point."
        )

        cur.execute(
            "UPDATE users SET verified_referrals = 1, verified = 1 WHERE user_id=?",
            (user.id,)
        )

    conn.commit()
    conn.close()

    await human_verify(update, context)
    return

    buttons = [
        [InlineKeyboardButton("🎁 Claim Reward", callback_data="claim")],
        [
            InlineKeyboardButton("👥 Refer & Earn", callback_data="refer"),
            InlineKeyboardButton("👤 Account Info", callback_data="account")
        ],
        [
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")
        ],
        [
            InlineKeyboardButton("📜 Claim History", callback_data="history"),
            InlineKeyboardButton("🆘 Support", callback_data="help")
        ]
    ]

    await query.edit_message_text(
        "🎉 WELCOME TO COUPON REWARD HUB 🎉\n\n👇 Select an option below to proceed:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def addpoints(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
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
    if update.effective_user.id != ADMIN_ID:
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
    if update.effective_user.id != ADMIN_ID:
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
    if update.effective_user.id != ADMIN_ID:
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
async def addcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
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
    if update.effective_user.id != 6427806986:
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Use: /setstock RewardName Stock"
        )
        return

    stock = int(context.args[-1])
    name = " ".join(context.args[:-1])

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "UPDATE rewards SET stock=? WHERE name=?",
        (stock, name)
    )

    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ {name} stock updated to {stock}"
    )
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text(
            "Use: /broadcast message"
        )
        return

    message = " ".join(context.args)

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()

    conn.close()

    sent = 0

    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user[0],
                text=message
            )
            sent += 1
        except:
            pass

    await update.message.reply_text(
        f"✅ Broadcast sent to {sent} users"
    )
async def requests_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
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
    if update.effective_user.id != ADMIN_ID:
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
    if update.effective_user.id != ADMIN_ID:
        return

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM rewards")
    total_rewards = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM claim_history")
    total_claims = cur.fetchone()[0]

    cur.execute("SELECT SUM(points) FROM claim_history")
    total_points = cur.fetchone()[0] or 0

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

    if daily_claims >= 5:
        conn.close()

        await query.edit_message_text(
            "🚫 Daily Claim Limit Reached\n\n"
            "You have reached your daily limit of 5 claims.\n\n"
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
        chat_id=APPROVAL_ADMIN,
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

async def help_center(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    buttons = [
        [InlineKeyboardButton("📌 How to Claim Reward", callback_data="help_claim")],
        [InlineKeyboardButton("💎 How to Earn Points", callback_data="help_points")],
        [InlineKeyboardButton("👥 Referral System", callback_data="help_referral")],
        [InlineKeyboardButton("📞 Contact Support", url="https://t.me/BeyondGravityX")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
    ]

    await query.edit_message_text(
    "🆘 Help Center\n\n"
    "Choose your option:",
    reply_markup=InlineKeyboardMarkup(buttons)
)


async def help_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "💎 HOW TO EARN POINTS\n\n"
        "👥 Invite friends using your referral link.\n"
        "✅ Friend joins all channels and verifies.\n"
        "🎉 You receive +1 point for every successful referral.\n\n"
        "📈 More referrals = More points = More rewards.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅ Back", callback_data="main_menu")]
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
        ])
    )

async def help_claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "🎁 How to Claim Rewards\n\n"
        "1️⃣ Collect enough points.\n"
        "2️⃣ Open Reward Catalog.\n"
        "3️⃣ Select your reward.\n"
        "4️⃣ Follow the claim process.\n\n"
        "For any issue, contact support.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅ Back", callback_data="main_menu")]
        ])
    )

async def help_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "👥 Referral System\n\n"
        "Share your referral link.\n"
        "When a user joins and verifies successfully, you receive referral points.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅ Back", callback_data="main_menu")]
        ])
        )

    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
    "🎁 How to Claim Reward\n\n"
    "1️⃣ Earn enough points.\n"
    "2️⃣ Open Reward Catalog.\n"
    "3️⃣ Select your reward.\n"
    "4️⃣ Press Claim.\n\n"
    "Your points will be deducted automatically.",
    reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Back", callback_data="main_menu")]
    ])
)

    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "💎 How to Earn Points\n\n"
        "• Invite friends.\n"
        "• Complete referrals.\n"
        "• Participate in future events and offers.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅ Back", callback_data="main_menu")]
        ])
    )




async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    buttons = [
    [InlineKeyboardButton("🎁 Claim Reward", callback_data="claim")],
    [InlineKeyboardButton("👤 Account Info", callback_data="account")],
    [InlineKeyboardButton("🔔 Refer & Earn", callback_data="refer")],
    [InlineKeyboardButton("💎 My Points", callback_data="points")],
    [InlineKeyboardButton("🆘 Help Center", callback_data="help")]
]

    await query.edit_message_text(
        "🎉 Welcome To Coupon Reward Hub",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
async def rewards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute("SELECT name, points, stock FROM rewards")
    rewards_list = cur.fetchall()
    print("Rewards DB:", rewards_list)

    conn.close()

    buttons = []

    for name, points, stock in rewards_list:
        status = f"📦 {stock} Left" if stock > 0 else "❌ Out of Stock"

        buttons.append([
            InlineKeyboardButton(
                f"🎁 {name} ({points} Pts) {status}",
                callback_data=f"confirm_{name}"
            )
        ])

    buttons.append([
        InlineKeyboardButton("🏠 Main Menu", callback_data="main")
    ])

    reply_markup = InlineKeyboardMarkup(buttons)

    await query.edit_message_text(
        "🎁 Reward Catalog\n\n👇 Select your reward:",
        reply_markup=reply_markup
    )
async def refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={user.id}"

    await query.edit_message_text(
        f"🔔 Refer & Earn\n\n"
        f"👥 Invite friends and earn points!\n\n"
        f"🔗 Your Referral Link:\n{link}\n\n"
        f"💎 Reward: +1 Point per verified referral",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
        ])
    )

async def account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT points, verified_referrals FROM users WHERE user_id=?",
        (user.id,)
    )

    data = cur.fetchone()
    conn.close()

    if data:
        points, referrals = data
    else:
        points = 0
        referrals = 0

    await query.edit_message_text(
        f"👤 Account Info\n\n"
        f"Username: @{user.username}\n"
        f"🆔 User ID: {user.id}\n"
        f"💰 Balance: {points} Points\n"
        f"👥 Active Referrals: {referrals} Users",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
        ])
    )

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT reward_name, points, claim_time FROM claim_history WHERE user_id=?",
        (user.id,)
    )

    data = cur.fetchall()
    conn.close()

    if not data:
        text = "📜 No claim history found."
    else:
        text = "📜 Your Claim History:\n\n"
        for reward, points, time in data:
            text += f"🎁 {reward}\n💎 {points} Points\n🕒 {time}\n\n"

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
        ])
    )
async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT points, referrals, verified_referrals FROM users WHERE user_id=?",
        (user.id,)
    )

    result = cur.fetchone()
    conn.close()

    if result:
        points, referrals, verified_referrals = result
    else:
        points = 0
        referrals = 0
        verified_referrals = 0

    await query.edit_message_text(
        f"💎 Your Stats\n\n"
        f"💰 Your Points: {points}\n"
        f"👥 Your Referrals: {referrals}\n"
        f"✅ Verified Referrals: {verified_referrals}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
        ])
    )
async def add_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

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
    print("START USER:", user.id, user.username)
    referrer_id = None
    referrer_id = None

    if context.args:
        try:
            referrer_id = int(context.args[0])

            # Anti self referral
            if referrer_id == user.id:
                referrer_id = None

        except:
            referrer_id = None
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO users(user_id, username, referred_by) VALUES(?, ?, ?)",
        (user.id, user.username, referrer_id)
    )

    conn.commit()
    conn.close()

    channels = [
        ("📢 Join Main Channel", "https://t.me/opboyLive", "@opboyLive"),
        ("📢 Join Deals Channel", "https://t.me/opboydeals", "@opboydeals"),
        ("💬 Join Chat", "https://t.me/OpBoyLive_Chat", "@OpBoyLive_Chat")
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

    if left_buttons:
        left_buttons.append(
            [InlineKeyboardButton("✅ Verify", callback_data="verify")]
        )

        reply_markup = InlineKeyboardMarkup(left_buttons)

    else:
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎁 Claim Reward", callback_data="claim")],
            [
                InlineKeyboardButton("👥 Refer & Earn", callback_data="refer"),
                InlineKeyboardButton("👤 Account Info", callback_data="account")
            ],
            [
                InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")
            ],
            [
                InlineKeyboardButton("📜 Claim History", callback_data="history"),
                InlineKeyboardButton("🆘 Support", callback_data="help")
            ]
        ])

    if left_buttons:
        await update.message.reply_text(
            "❌ Please join the missing channel(s) first 👇",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "🎉 Welcome To Coupon Reward Hub 🎉\n\n"
            "👇 Select an option below to proceed:",
            reply_markup=reply_markup
        )

init_db()
app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addpoints", add_points))
app.add_handler(CallbackQueryHandler(verify, pattern="verify"))
app.add_handler(CallbackQueryHandler(captcha_check, pattern="^captcha_"))
app.add_handler(CallbackQueryHandler(menu, pattern="main"))
app.add_handler(CallbackQueryHandler(leaderboard, pattern="leaderboard"))

app.add_handler(CallbackQueryHandler(account, pattern="account"))
app.add_handler(CallbackQueryHandler(points, pattern="points"))
app.add_handler(CallbackQueryHandler(history, pattern="history"))
app.add_handler(CallbackQueryHandler(help_center, pattern="^help$"))
app.add_handler(CallbackQueryHandler(help_claim, pattern="help_claim"))
app.add_handler(CallbackQueryHandler(help_points, pattern="help_points"))
app.add_handler(CallbackQueryHandler(help_referral, pattern="help_referral"))
app.add_handler(CallbackQueryHandler(refer, pattern="refer"))
app.add_handler(CallbackQueryHandler(rewards, pattern="claim"))
app.add_handler(CallbackQueryHandler(confirm_claim, pattern="^confirm_"))
app.add_handler(CallbackQueryHandler(claim_reward, pattern="^reward_"))
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
app.run_polling()

