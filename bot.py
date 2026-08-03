#!/usr/bin/env python3

import logging
import re
import uuid
import requests
import asyncio
import threading
from datetime import datetime
import pytz
import html
from flask import Flask, request as flask_request, jsonify

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.error import BadRequest

BOT_TOKEN = "8708910035:AAEeJDLHhwGyuyEkfpuznDrXa0rJncdfhzw"
API_BASE_URL = "https://gold-newt-367030.hostingersite.com/api.php"
ADMIN_IDS = [8093002631]
GROUP_CHAT_ID = "-1003877823088"
FLASK_PORT = 5001
FLASK_SECRET = "usagi-hit-forward-secret"
MANDATORY_CHANNELS = [-1004417835945, -1003724886499]
CHANNEL_DISPLAY_NAMES = ["Stirpe bins", "UsagiAutoX Chat"]
CHANNEL_LINKS = ["https://t.me/stripebinssss", "https://t.me/+r_pyAH7kBRZmOTlk"]
NO_PFP_MESSAGE = """
<b>Profile Picture Required
━━━━━━━━━━━━━━━━━━━━━━
You need to set a Telegram profile picture before using UsagiAutoX.

How to set it:
1. Go to Telegram Settings
2. Tap your profile photo area
3. Set a profile picture

Then come back and tap /start again.</b>
"""

CURRENCY_SYMBOLS = {
    'usd': '$', 'eur': '€', 'gbp': '£', 'jpy': '¥', 'cny': '¥',
    'inr': '₹', 'krw': '₩', 'rub': '₽', 'brl': 'R$', 'aud': 'A$',
    'cad': 'C$', 'chf': 'CHF', 'hkd': 'HK$', 'sgd': 'S$', 'sek': 'kr',
    'nok': 'kr', 'dkk': 'kr', 'pln': 'zł', 'thb': '฿', 'mxn': 'MX$',
    'idr': 'Rp', 'try': '₺', 'zar': 'R', 'php': '₱', 'myr': 'RM',
    'vnd': '₫', 'aed': 'د.إ', 'sar': '﷼', 'ils': '₪', 'egp': 'E£',
    'ngn': '₦', 'cop': 'CO$', 'ars': 'AR$', 'clp': 'CL$', 'pen': 'S/',
    'czk': 'Kč', 'huf': 'Ft', 'ron': 'lei', 'bgn': 'лв', 'hrk': 'kn',
    'pkr': '₨', 'bdt': '৳', 'lkr': 'Rs', 'nzd': 'NZ$', 'twd': 'NT$',
}

JOIN_MESSAGE = f"""
<b>Welcome to UsagiAutoX
To start using the bot, please join our official channels first:

<a href="{CHANNEL_LINKS[0]}"><b>{CHANNEL_DISPLAY_NAMES[0]}</b></a>
<a href="{CHANNEL_LINKS[1]}"><b>{CHANNEL_DISPLAY_NAMES[1]}</b></a>

After joining both, click the button below to verify your membership.</b>
"""

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

flask_app = Flask(__name__)
flask_app.logger.setLevel(logging.WARNING)
_bot_instance = None
_event_loop = None

def _send_via_bot(coro):
    if _event_loop and _bot_instance:
        future = asyncio.run_coroutine_threadsafe(coro, _event_loop)
        try:
            future.result(timeout=15)
        except Exception as e:
            logger.error(f"Hit-forward send error: {e}")

@flask_app.route('/hit-forward', methods=['POST'])
def hit_forward_endpoint():
    try:
        secret = flask_request.headers.get('X-Secret', '')
        if secret != FLASK_SECRET:
            return jsonify({'success': False, 'error': 'unauthorized'}), 401

        data = flask_request.get_json(silent=True) or {}

        chat_id = data.get('chat_id') or data.get('userId')
        if not chat_id:
            return jsonify({'success': False, 'error': 'missing chat_id'}), 400

        card = data.get('card', 'N/A')
        mm = data.get('mm', '??')
        yy = data.get('yy', '??')
        cvv = data.get('cvv', '???')
        email = data.get('email', 'N/A')
        attempt = data.get('attempt', 'N/A')
        currency_code = (data.get('currency', 'usd')).lower()
        currency_symbol = CURRENCY_SYMBOLS.get(currency_code, currency_code.upper() + ' ')
        amount_value = data.get('amount', '0') or '0'
        amount_display = f"{currency_symbol}{amount_value}"
        business_url = data.get('businessUrl', 'N/A')
        success_url = data.get('successUrl', business_url)
        time_taken = data.get('timeTaken', 'N/A')
        user_name = html.escape(data.get('userName', 'User'))

        if str(attempt) in ('0', '', 'N/A', 'null', 'undefined'):
            return jsonify({'success': False, 'error': 'invalid attempt'}), 400

        dm_message = f"""<b>New Hit
Card: <code>{card}|{mm}|{yy}|{cvv}</code>
Email: <code>{email}</code>
Attempt: <code>{attempt}</code>
Amount: <code>{amount_display}</code>
Business: <code>{business_url}</code>
Time: <code>{time_taken}</code>
Link: <a href="{success_url}">Open Success URL</a>
Thanks For Using UsagiAutoX.</b>"""

        group_message = f"""<b>New Hit
User: <a href="tg://user?id={chat_id}">{user_name}</a>
Attempt: <code>{attempt}</code>
Amount: <code>{amount_display}</code>
Thanks For Using UsagiAutoX.</b>"""

        async def send_dm():
            try:
                await _bot_instance.send_message(
                    chat_id=chat_id,
                    text=dm_message,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.error(f"Hit-forward DM failed for {chat_id}: {e}")

        async def send_group():
            try:
                if GROUP_CHAT_ID:
                    await _bot_instance.send_message(
                        chat_id=GROUP_CHAT_ID,
                        text=group_message,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
            except Exception as e:
                logger.error(f"Hit-forward group failed: {e}")

        _send_via_bot(send_dm())
        _send_via_bot(send_group())

        return jsonify({'success': True}), 200

    except Exception as e:
        logger.error(f"Hit-forward endpoint error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@flask_app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'bot': _bot_instance is not None}), 200

def run_flask():
    flask_app.run(host='0.0.0.0', port=FLASK_PORT, debug=False, use_reloader=False)

pending_actions = {}
pending_bin_submissions = {}

def _sync_api_request(action, params=None, method='GET'):
    try:
        url = f"{API_BASE_URL}?action={action}"
        if method == 'GET':
            response = requests.get(url, params=params, timeout=10)
        elif method == 'POST':
            response = requests.post(url, json=params, timeout=10)
        elif method == 'DELETE':
            response = requests.delete(url, params=params, timeout=10)
        else:
            response = requests.get(url, params=params, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"API request failed: {e}")
        return {"success": False, "error": str(e)}

def api_request(action, params=None, method='GET'):
    return _sync_api_request(action, params, method)

async def async_api_request(action, params=None, method='GET'):
    return await asyncio.to_thread(_sync_api_request, action, params, method)

def create_user(user_id, username, first_name, pfp_url=''):
    return _sync_api_request('create-user', {'user_id': str(user_id), 'username': username or '', 'first_name': first_name or '', 'pfp_url': pfp_url or ''}, 'POST')

def get_user_token(user_id, force_new=False):
    params = {'user_id': str(user_id)}
    if force_new:
        params['force_new'] = 'true'
    return _sync_api_request('generate-token', params, 'POST')

def get_user_stats(user_id):
    return _sync_api_request('user', {'user_id': str(user_id)})

def get_global_stats():
    return _sync_api_request('stats')

def get_leaderboard(limit=10):
    return _sync_api_request('leaderboard', {'limit': limit})

def get_user_hits(token, limit=5):
    return _sync_api_request('user-hits', {'token': token, 'limit': limit})

def admin_generate_key(version):
    return _sync_api_request('admin-genkey', {'version': version}, 'POST')

def admin_list_keys():
    return _sync_api_request('admin-listkeys')

def admin_revoke_key(key):
    return _sync_api_request('admin-revokekey', {'key': key}, 'POST')

def admin_activate_key(key):
    return _sync_api_request('admin-activatekey', {'key': key}, 'POST')

def admin_delete_key(key):
    return _sync_api_request('admin-deletekey', {'key': key}, 'POST')

def admin_set_setting(name, value):
    return _sync_api_request('admin-setsetting', {'name': name, 'value': value}, 'POST')

def admin_get_settings():
    return _sync_api_request('admin-getsettings')

def admin_clear_tokens():
    return _sync_api_request('admin-cleartokens', {}, 'POST')

def admin_clean_fake_hits():
    return _sync_api_request('admin-cleanfakehits', {}, 'POST')

def admin_reset_db():
    return _sync_api_request('admin-resetdb', {'confirm': 'yes'}, 'POST')

def admin_ban_user(user_id):
    return _sync_api_request('admin-banuser', {'user_id': str(user_id)}, 'POST')

def admin_unban_user(user_id):
    return _sync_api_request('admin-unbanuser', {'user_id': str(user_id)}, 'POST')

def admin_get_all_users():
    return _sync_api_request('admin-allusers')

def admin_keyinfo(version=None):
    params = {}
    if version:
        params['version'] = version
    return _sync_api_request('admin-keyinfo', params)

def admin_get_stats():
    return _sync_api_request('admin-stats')

def admin_get_all_hits():
    return _sync_api_request('admin-allhits')

async def async_create_user(user_id, username, first_name, pfp_url=''):
    return await asyncio.to_thread(create_user, user_id, username, first_name, pfp_url)

async def async_get_user_token(user_id, force_new=False):
    return await asyncio.to_thread(get_user_token, user_id, force_new)

async def async_get_user_stats(user_id):
    return await asyncio.to_thread(get_user_stats, user_id)

async def async_get_global_stats():
    return await asyncio.to_thread(get_global_stats)

async def async_get_leaderboard(limit=10):
    return await asyncio.to_thread(get_leaderboard, limit)

async def async_get_user_hits(token, limit=5):
    return await asyncio.to_thread(get_user_hits, token, limit)

async def async_admin_generate_key(version):
    return await asyncio.to_thread(admin_generate_key, version)

async def async_admin_list_keys():
    return await asyncio.to_thread(admin_list_keys)

async def async_admin_revoke_key(key):
    return await asyncio.to_thread(admin_revoke_key, key)

async def async_admin_activate_key(key):
    return await asyncio.to_thread(admin_activate_key, key)

async def async_admin_delete_key(key):
    return await asyncio.to_thread(admin_delete_key, key)

async def async_admin_set_setting(name, value):
    return await asyncio.to_thread(admin_set_setting, name, value)

async def async_admin_get_settings():
    return await asyncio.to_thread(admin_get_settings)

async def async_admin_clear_tokens():
    return await asyncio.to_thread(admin_clear_tokens)

async def async_admin_clean_fake_hits():
    return await asyncio.to_thread(admin_clean_fake_hits)

async def async_admin_reset_db():
    return await asyncio.to_thread(admin_reset_db)

async def async_admin_ban_user(user_id):
    return await asyncio.to_thread(admin_ban_user, user_id)

async def async_admin_unban_user(user_id):
    return await asyncio.to_thread(admin_unban_user, user_id)

async def async_admin_get_all_users():
    return await asyncio.to_thread(admin_get_all_users)

async def async_admin_keyinfo(version=None):
    return await asyncio.to_thread(admin_keyinfo, version)

async def async_admin_get_stats():
    return await asyncio.to_thread(admin_get_stats)

async def async_admin_get_all_hits():
    return await asyncio.to_thread(admin_get_all_hits)

user_tokens = {}

IMGBB_API_KEY = "3f1dcabc6797c58da97c62b5d2b71938"

async def upload_to_imgbb(image_bytes):
    import base64, httpx
    b64 = base64.b64encode(image_bytes).decode('utf-8')
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_API_KEY, "image": b64}
        )
        result = resp.json()
        if result.get("success"):
            return result["data"]["url"]
    return None

async def get_user_pfp_url(bot, user_id):
    import asyncio, httpx
    try:
        profile_photos = await asyncio.wait_for(
            bot.get_user_profile_photos(user_id=user_id, limit=1),
            timeout=3.0
        )
        if profile_photos and profile_photos.total_count > 0:
            biggest = profile_photos.photos[0][-1]
            file = await asyncio.wait_for(
                bot.get_file(biggest.file_id),
                timeout=3.0
            )
            file_url = file.file_path
            if not file_url.startswith("http"):
                file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_url}"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(file_url)
                if resp.status_code == 200:
                    imgbb_url = await upload_to_imgbb(resp.content)
                    if imgbb_url:
                        logger.info(f"Uploaded pfp to imgBB for {user_id}: {imgbb_url}")
                        return imgbb_url
    except asyncio.TimeoutError:
        logger.warning(f"Profile photo fetch timed out for {user_id}")
    except Exception as e:
        logger.warning(f"Could not get profile photo for {user_id}: {e}")
    return None

async def _update_pfp_background(bot, user_id, username, first_name):
    pfp_url = await get_user_pfp_url(bot, user_id)
    if pfp_url:
        await async_create_user(user_id, username, first_name, pfp_url)
        logger.info(f"Updated pfp for {user_id}: {pfp_url}")

async def has_profile_photo(bot, user_id):
    try:
        photos = await asyncio.wait_for(
            bot.get_user_profile_photos(user_id=user_id, limit=1),
            timeout=3.0
        )
        return photos and photos.total_count > 0
    except Exception as e:
        logger.warning(f"Failed to check profile photo for {user_id}: {e}")
        return False

async def get_or_create_user(user_id, username, first_name, bot=None):
    if bot and not await has_profile_photo(bot, user_id):
        return None

    await async_create_user(user_id, username, first_name, '')
    if bot:
        asyncio.create_task(_update_pfp_background(bot, user_id, username, first_name))
    if user_id not in user_tokens:
        result = await async_get_user_token(user_id)
        if result.get('success'):
            user_tokens[user_id] = result.get('token')
    return user_tokens.get(user_id)

async def is_member_of_all_channels(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        for channel in MANDATORY_CHANNELS:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ['left', 'kicked', 'restricted']:
                return False
        return True
    except Exception as e:
        logger.warning(f"Failed to check membership for user {user_id}: {e}")
        return False

async def show_join_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(f"{CHANNEL_DISPLAY_NAMES[0]}", url=CHANNEL_LINKS[0]),
         InlineKeyboardButton(f"{CHANNEL_DISPLAY_NAMES[1]}", url=CHANNEL_LINKS[1])],
        [InlineKeyboardButton("I've Joined Both – Verify", callback_data="verify_join")]
    ]
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=JOIN_MESSAGE,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML',
        disable_web_page_preview=True
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return

    if not await is_member_of_all_channels(context, update.effective_user.id):
        await show_join_channels(update, context)
        return

    user = update.effective_user
    user_id = user.id

    token_result = await get_or_create_user(user_id, user.username, user.first_name, bot=context.bot)

    if token_result is None:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=NO_PFP_MESSAGE,
            parse_mode='HTML'
        )
        return

    token = user_tokens.get(user_id, "Not generated yet")

    global_stats = await async_get_global_stats()
    user_data = await async_get_user_stats(user_id)
    user_hits = user_data.get('hits', 0) if user_data.get('success') else 0
    total_hits = global_stats.get('total_hits', 0) if global_stats.get('success') else 0

    keyboard = [
        [InlineKeyboardButton("Regenerate Token", callback_data="get_token")],
        [InlineKeyboardButton("My Stats", callback_data="my_stats"), InlineKeyboardButton("My Hits", callback_data="my_hits")],
        [InlineKeyboardButton("Scoreboard", callback_data="scoreboard")],
        [InlineKeyboardButton("Submit BIN", callback_data="submit_bin")],
        [InlineKeyboardButton("Profile", callback_data="my_profile"), InlineKeyboardButton("Help", callback_data="help")]
    ]

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"""
<b>UsagiAutoX
━━━━━━━━━━━━━━━━━━━━━━
Welcome {html.escape(user.first_name or '')}!
Token: <code>{token}</code>

Your Hits: <code>{user_hits}</code>
Global Hits: <code>{total_hits}</code>

Select an option below:</b>
""",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML',
        disable_web_page_preview=True
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("You are not authorized to use admin panel.")
        return
    keyboard = [
        [InlineKeyboardButton("Generate Key", callback_data="admin_genkey")],
        [InlineKeyboardButton("List Keys", callback_data="admin_listkeys")],
        [InlineKeyboardButton("Revoke Key", callback_data="admin_revokekey_prompt"), InlineKeyboardButton("Activate Key", callback_data="admin_activatekey_prompt")],
        [InlineKeyboardButton("Delete Key", callback_data="admin_deletekey_prompt")],
        [InlineKeyboardButton("BIN Library", callback_data="admin_binlibrary")],
        [InlineKeyboardButton("Set Channel", callback_data="admin_setchannel_prompt"), InlineKeyboardButton("Set Version", callback_data="admin_setversion_prompt")],
        [InlineKeyboardButton("Clear Tokens & Stats", callback_data="admin_cleartokens")],
        [InlineKeyboardButton("Clean Fake Hits", callback_data="admin_cleanfakehits")],
        [InlineKeyboardButton("Reset Database", callback_data="admin_resetdb")],
        [InlineKeyboardButton("Ban User", callback_data="admin_banuser_prompt"), InlineKeyboardButton("Unban User", callback_data="admin_unbanuser_prompt")],
        [InlineKeyboardButton("View Settings", callback_data="admin_viewsettings")]
    ]
    await update.message.reply_text(
        """<b>Admin Panel
━━━━━━━━━━━━━━━━━━━━━━
Choose an action:</b>""",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_chat.type != 'private':
        return

    user_id = query.from_user.id
    data = query.data

    async def safe_edit(text, reply_markup=None, parse_mode='HTML', disable_web_page_preview=False):
        try:
            await query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                await query.answer("Already up to date", show_alert=False)
            elif "Message to edit not found" in str(e):
                pass
            else:
                logger.warning(f"Edit failed: {e}")
                await query.answer("Cannot update message", show_alert=True)

    if data == "verify_join":
        if await is_member_of_all_channels(context, user_id):
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="""<b>Verified! Welcome to UsagiAutoX.
Tap /start to begin</b>""",
                parse_mode='HTML'
            )
        else:
            await query.answer("You still need to join both channels.", show_alert=True)
        return

    if data == "get_token":
        if not await has_profile_photo(context.bot, user_id):
            await safe_edit(NO_PFP_MESSAGE, parse_mode='HTML')
            return
        result = await async_get_user_token(user_id, force_new=True)
        if result.get('success'):
            token = result.get('token')
            user_tokens[user_id] = token
            keyboard = [
                [InlineKeyboardButton("Regenerate Again", callback_data="get_token")],
                [InlineKeyboardButton("Back", callback_data="back_main")]
            ]
            await safe_edit(
                f"""<b>Token Regenerated

New token: <code>{token}</code>

Old token is no longer valid.
Copy & use this new one.</b>
""",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
        else:
            await query.answer(f"Error: {result.get('error', 'Unknown')}", show_alert=True)

    elif data == "my_stats":
        user_data = await async_get_user_stats(user_id)
        if user_data.get('success'):
            hits = user_data.get('hits', 0)
            attempts = user_data.get('attempts', 0)
            success_rate = round((hits / max(attempts, 1)) * 100, 2)
            keyboard = [
                [InlineKeyboardButton("Refresh", callback_data="my_stats")],
                [InlineKeyboardButton("Back", callback_data="back_main")]
            ]
            await safe_edit(
                f"""<b>Statistics
━━━━━━━━━━━━━━━━━━━━━━
Hits: {hits}
Attempts: {attempts}
Success Rate: {success_rate}%</b>""",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )

    elif data == "my_hits":
        token = user_tokens.get(user_id)
        if not token:
            result = await async_get_user_token(user_id)
            if result.get('success'):
                token = result.get('token')
                user_tokens[user_id] = token
        if token:
            result = await async_get_user_hits(token, 5)
            if result.get('success') and result.get('hits'):
                hits_text = ""
                for i, h in enumerate(result['hits'], 1):
                    card = h.get('full_card', '—')
                    amount_raw = h.get('amount', '—')
                    curr = (h.get('currency') or 'usd').lower()
                    merch = h.get('merchant', '—')
                    symbol = CURRENCY_SYMBOLS.get(curr, '')
                    amount_str = str(amount_raw).strip()
                    if symbol and amount_str.startswith(symbol):
                        price = amount_str
                    else:
                        price = f"{amount_str}{symbol}" if symbol else f"{amount_str} {curr.upper()}"
                    hits_text += f"{i}. <code>{card}</code>\n  • {price} • {merch}\n\n"
            else:
                hits_text = "No successful hits yet."
            keyboard = [
                [InlineKeyboardButton("Refresh", callback_data="my_hits")],
                [InlineKeyboardButton("Back", callback_data="back_main")]
            ]
            await safe_edit(
                f"""<b>Recent Hits
━━━━━━━━━━━━━━━━━━━━━━
{hits_text}</b>""",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
        else:
            await query.answer("No token available.", show_alert=True)

    elif data == "scoreboard":
        result = await async_get_leaderboard(10)
        global_stats = await async_get_global_stats()
        sb_text = ""
        if result.get('success') and result.get('leaderboard'):
            for i, u in enumerate(result['leaderboard']):
                name = u.get('first_name') or u.get('username') or 'User'
                uid = u.get('user_id', '')
                hits = u.get('hits', 0)
                sb_text += f"{i+1}. <a href=\"tg://user?id={uid}\">{name}</a> — {hits}\n"
        else:
            sb_text = "No users yet"
        total_hits = global_stats.get('total_hits', 0) if global_stats.get('success') else 0
        keyboard = [
            [InlineKeyboardButton("Refresh", callback_data="scoreboard")],
            [InlineKeyboardButton("Back", callback_data="back_main")]
        ]
        await safe_edit(
            f"""<b>Leaderboard
━━━━━━━━━━━━━━━━━━━━━━
{sb_text}
━━━━━━━━━━━━━━━━━━━━━━
Total Hits: <code>{total_hits}</code></b>""",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
            disable_web_page_preview=True
        )

    elif data == "my_profile":
        token = user_tokens.get(user_id, 'Not generated')
        user_data = await async_get_user_stats(user_id)
        hits = user_data.get('hits', 0) if user_data.get('success') else 0
        keyboard = [
            [InlineKeyboardButton("Regenerate Token", callback_data="get_token")],
            [InlineKeyboardButton("Back", callback_data="back_main")]
        ]
        await safe_edit(
            f"""<b>Profile
━━━━━━━━━━━━━━━━━━━━━━
User ID: <code>{user_id}</code>
Name: {html.escape(query.from_user.full_name or '')}
Token: <code>{token}</code>
Hits: <code>{hits}</code></b>""",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
            disable_web_page_preview=True
        )

    elif data == "update_pfp":
        pfp_url = await get_user_pfp_url(context.bot, user_id)
        if pfp_url:
            await async_create_user(user_id, query.from_user.username, query.from_user.first_name, pfp_url)
            await query.answer("Profile photo updated!", show_alert=True)
        else:
            await query.answer("No profile photo found. Please set one in Telegram settings.", show_alert=True)

        token = user_tokens.get(user_id, 'Not generated')
        user_data = await async_get_user_stats(user_id)
        hits = user_data.get('hits', 0) if user_data.get('success') else 0
        keyboard = [
            [InlineKeyboardButton("Regenerate Token", callback_data="get_token")],
            [InlineKeyboardButton("Back", callback_data="back_main")]
        ]
        await safe_edit(
            f"""<b>Profile
━━━━━━━━━━━━━━━━━━━━━━
User ID: <code>{user_id}</code>
Name: {html.escape(query.from_user.full_name or '')}
Token: <code>{token}</code>
Hits: <code>{hits}</code></b>""",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
            disable_web_page_preview=True
        )

    elif data == "help":
        keyboard = [[InlineKeyboardButton("Back", callback_data="back_main")]]
        await safe_edit(
            """<b>How to Use UsagiAutoX
━━━━━━━━━━━━━━━━━━━━━━
1. Generate your token
2. download extension from web
   — UsagiAutoX.com
3. Install the Chrome extension
4. Paste token & activate
5. /start hit forward bot
   — @UsagiAutoBot 
6. Start capturing — hits appear here

Keep token private
Join both channels
Check hits & leaderboard regularly</b>""",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    elif data == "back_main":
        global_stats = await async_get_global_stats()
        user_data = await async_get_user_stats(user_id)
        user_hits = user_data.get('hits', 0) if user_data.get('success') else 0
        total_hits = global_stats.get('total_hits', 0) if global_stats.get('success') else 0
        keyboard = [
            [InlineKeyboardButton("Regenerate Token", callback_data="get_token")],
            [InlineKeyboardButton("My Stats", callback_data="my_stats"), InlineKeyboardButton("My Hits", callback_data="my_hits")],
            [InlineKeyboardButton("Scoreboard", callback_data="scoreboard")],
            [InlineKeyboardButton("Submit BIN", callback_data="submit_bin")],
            [InlineKeyboardButton("Profile", callback_data="my_profile"), InlineKeyboardButton("Help", callback_data="help")]
        ]
        await safe_edit(
            f"""<b>UsagiAutoX
━━━━━━━━━━━━━━━━━━━━━━
Welcome {html.escape(query.from_user.first_name or '')}!

Your Hits: <code>{user_hits}</code>
Global Hits: <code>{total_hits}</code>

Select an option below:</b>""",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    elif data == "submit_bin":
        pending_actions[user_id] = {'action': 'submit_bin'}
        keyboard = [[InlineKeyboardButton("Back", callback_data="back_main")]]
        await safe_edit(
            """<b>Submit a New BIN
━━━━━━━━━━━━━━━━━━━━━━
Forward hit log message from @UsagiAutoBot.
Forward the message now:</b>""",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    elif data.startswith("approve_bin_"):
        if user_id not in ADMIN_IDS:
            await query.answer("Unauthorized", show_alert=True)
            return
        submission_id = data.replace("approve_bin_", "")
        if submission_id not in pending_bin_submissions:
            await query.answer("Submission expired or not found", show_alert=True)
            return
        submission = pending_bin_submissions.pop(submission_id)
        result = await async_api_request('admin-addbin', {
            'site': submission['site'],
            'bin': submission['bin'],
            'credit': submission['credit']
        }, 'POST')
        if result.get('success'):
            bin_data = result.get('bin', {})
            bin_id = bin_data.get('id', 'N/A') if isinstance(bin_data, dict) else 'N/A'
            try:
                await context.bot.send_message(
                    chat_id=submission['submitter_id'],
                    text=f"""<b>BIN Approved

Your BIN submission has been approved and added to the library.

BIN: <code>{submission['bin']}</code>
Site: {submission['site']}
Credit: {submission['credit']}

Thank you for your contribution.</b>""",
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.warning(f"Failed to notify submitter: {e}")
            await safe_edit(
                f"""<b>BIN Approved & Added

ID: <code>{bin_id}</code>
BIN: <code>{submission['bin']}</code>
Site: {submission['site']}
Credit: {submission['credit']}
Submitted by: <a href="tg://user?id={submission['submitter_id']}">{submission['submitter_name']}</a>

To remove: /removebin {bin_id}</b>""",
                parse_mode='HTML',
                disable_web_page_preview=True
            )
        else:
            await safe_edit(f"Failed to add BIN: {result.get('error', 'Unknown error')}", parse_mode='HTML')

    elif data.startswith("reject_bin_"):
        if user_id not in ADMIN_IDS:
            await query.answer("Unauthorized", show_alert=True)
            return
        submission_id = data.replace("reject_bin_", "")
        if submission_id not in pending_bin_submissions:
            await query.answer("Submission expired or not found", show_alert=True)
            return
        submission = pending_bin_submissions.pop(submission_id)
        try:
            await context.bot.send_message(
                chat_id=submission['submitter_id'],
                text=f"""<b>BIN Rejected

Your BIN submission was not approved.

BIN: <code>{submission['bin']}</code>
Site: {submission['site']}

This could be due to:
Duplicate BIN already in library
Invalid or incorrect BIN
Site not supported

Feel free to submit another BIN.</b>""",
                parse_mode='HTML'
            )
        except Exception as e:
            logger.warning(f"Failed to notify submitter: {e}")
        await safe_edit(
            f"""<b>BIN Rejected

BIN: <code>{submission['bin']}</code>
Site: {submission['site']}
Credit: {submission['credit']}
Submitted by: <a href="tg://user?id={submission['submitter_id']}">{submission['submitter_name']}</a></b>""",
            parse_mode='HTML',
            disable_web_page_preview=True
        )

    elif data.startswith("admin_"):
        if user_id not in ADMIN_IDS:
            await query.answer("Unauthorized", show_alert=True)
            return

        if data == "admin_genkey":
            pending_actions[user_id] = {'action': 'genkey'}
            await safe_edit("Send the version number (e.g. 1.3.7):", parse_mode='HTML')

        elif data == "admin_listkeys":
            result = await async_admin_list_keys()
            if result.get('success') and result.get('keys'):
                text = """<b>License Keys
━━━━━━━━━━━━━━━━━━━━━━
"""
                for i, k in enumerate(result['keys'], 1):
                    status = "Active" if k.get('active') else "Inactive"
                    text += f"{i}. <code>{k['key']}</code>\n   v{k['version']} — {status}\n\n"
            else:
                text = "No keys found."
            keyboard = [[InlineKeyboardButton("Back", callback_data="admin_back")]]
            await safe_edit(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

        elif data == "admin_revokekey_prompt":
            pending_actions[user_id] = {'action': 'revokekey'}
            await safe_edit("Send the key to revoke:", parse_mode='HTML')

        elif data == "admin_activatekey_prompt":
            pending_actions[user_id] = {'action': 'activatekey'}
            await safe_edit("Send the key to activate:", parse_mode='HTML')

        elif data == "admin_deletekey_prompt":
            pending_actions[user_id] = {'action': 'deletekey'}
            await safe_edit("Send the key to delete:", parse_mode='HTML')

        elif data == "admin_setchannel_prompt":
            settings = await async_admin_get_settings()
            current = settings.get('settings', {}).get('telegram_channel', 'Not set')
            pending_actions[user_id] = {'action': 'setchannel'}
            await safe_edit(f"Current: {current}\n\nSend new channel link:", parse_mode='HTML')

        elif data == "admin_setversion_prompt":
            settings = await async_admin_get_settings()
            current = settings.get('settings', {}).get('latest_version', 'Not set')
            pending_actions[user_id] = {'action': 'setversion'}
            await safe_edit(f"Current: {current}\n\nSend new version:", parse_mode='HTML')

        elif data == "admin_cleartokens":
            keyboard = [
                [InlineKeyboardButton("Yes, Clear All", callback_data="cleartokens_confirm")],
                [InlineKeyboardButton("Back", callback_data="admin_back")]
            ]
            await safe_edit("Clear Tokens & Stats?\n\nAre you sure?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

        elif data == "admin_cleanfakehits":
            keyboard = [
                [InlineKeyboardButton("Yes, Clean", callback_data="cleanfakehits_confirm")],
                [InlineKeyboardButton("Back", callback_data="admin_back")]
            ]
            await safe_edit("Clean Fake Hits?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

        elif data == "admin_resetdb":
            keyboard = [
                [InlineKeyboardButton("Proceed", callback_data="resetdb_step2")],
                [InlineKeyboardButton("Back", callback_data="admin_back")]
            ]
            await safe_edit("RESET DATABASE?\n\nThis will delete ALL data!", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

        elif data == "admin_banuser_prompt":
            pending_actions[user_id] = {'action': 'banuser'}
            await safe_edit("Send the user ID to ban:", parse_mode='HTML')

        elif data == "admin_unbanuser_prompt":
            pending_actions[user_id] = {'action': 'unbanuser'}
            await safe_edit("Send the user ID to unban:", parse_mode='HTML')

        elif data == "admin_viewsettings":
            result = await async_admin_get_settings()
            if result.get('success'):
                settings = result.get('settings', {})
                text = """<b>Current Settings
━━━━━━━━━━━━━━━━━━━━━━
"""
                for key, value in settings.items():
                    text += f"{key}: {value}\n"
                if not settings:
                    text += "No settings configured"
            else:
                text = "Failed to load settings"
            keyboard = [[InlineKeyboardButton("Back", callback_data="admin_back")]]
            await safe_edit(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

        elif data == "admin_back":
            keyboard = [
                [InlineKeyboardButton("Generate Key", callback_data="admin_genkey")],
                [InlineKeyboardButton("List Keys", callback_data="admin_listkeys")],
                [InlineKeyboardButton("Revoke Key", callback_data="admin_revokekey_prompt"), InlineKeyboardButton("Activate Key", callback_data="admin_activatekey_prompt")],
                [InlineKeyboardButton("Delete Key", callback_data="admin_deletekey_prompt")],
                [InlineKeyboardButton("BIN Library", callback_data="admin_binlibrary")],
                [InlineKeyboardButton("Set Channel", callback_data="admin_setchannel_prompt"), InlineKeyboardButton("Set Version", callback_data="admin_setversion_prompt")],
                [InlineKeyboardButton("Clear Tokens & Stats", callback_data="admin_cleartokens")],
                [InlineKeyboardButton("Clean Fake Hits", callback_data="admin_cleanfakehits")],
                [InlineKeyboardButton("Reset Database", callback_data="admin_resetdb")],
                [InlineKeyboardButton("Ban User", callback_data="admin_banuser_prompt"), InlineKeyboardButton("Unban User", callback_data="admin_unbanuser_prompt")],
                [InlineKeyboardButton("View Settings", callback_data="admin_viewsettings")]
            ]
            await safe_edit(
                """<b>Admin Panel
━━━━━━━━━━━━━━━━━━━━━━
Choose an action:</b>""",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )

        elif data == "admin_binlibrary":
            keyboard = [
                [InlineKeyboardButton("Add BIN", callback_data="admin_addbin_prompt")],
                [InlineKeyboardButton("List BINs", callback_data="admin_listbins")],
                [InlineKeyboardButton("Remove BIN", callback_data="admin_removebin_prompt")],
                [InlineKeyboardButton("Clear All BINs", callback_data="admin_clearbins_prompt")],
                [InlineKeyboardButton("Back", callback_data="admin_back")]
            ]
            await safe_edit(
                """<b>BIN Library Management
━━━━━━━━━━━━━━━━━━━━━━
Manage BINs shown to all users:</b>""",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )

        elif data == "admin_addbin_prompt":
            pending_actions[user_id] = {'action': 'addbin'}
            await safe_edit("""Send BIN details in format:
site|bin|credit

Example:
Amazon|453201511283|VISA""", parse_mode='HTML')

        elif data == "admin_listbins":
            result = await async_api_request('bin-library')
            if result.get('success') and result.get('bins'):
                text = """<b>BIN Library
━━━━━━━━━━━━━━━━━━━━━━
"""
                for i, b in enumerate(result['bins'], 1):
                    text += f"{i}. <code>{b.get('bin', 'N/A')}</code>\n   {b.get('site', 'N/A')} • {b.get('credit', 'N/A')}\n\n"
            else:
                text = "No BINs in library."
            keyboard = [[InlineKeyboardButton("Back", callback_data="admin_binlibrary")]]
            await safe_edit(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

        elif data == "admin_removebin_prompt":
            pending_actions[user_id] = {'action': 'removebin'}
            await safe_edit("Send the BIN number to remove:", parse_mode='HTML')

        elif data == "admin_clearbins_prompt":
            keyboard = [
                [InlineKeyboardButton("Yes, Clear All", callback_data="admin_clearbins_confirm")],
                [InlineKeyboardButton("Back", callback_data="admin_binlibrary")]
            ]
            await safe_edit("Clear ALL BINs from library?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    elif data == "cleartokens_confirm":
        if user_id not in ADMIN_IDS:
            return
        result = await async_admin_clear_tokens()
        await safe_edit(
            f"""Cleared!

{result.get('message', 'Done')}""",
            parse_mode='HTML'
        )

    elif data == "cleanfakehits_confirm":
        if user_id not in ADMIN_IDS:
            return
        result = await async_admin_clean_fake_hits()
        await safe_edit(
            f"Cleaned {result.get('deleted', 0)} fake records",
            parse_mode='HTML'
        )

    elif data == "resetdb_step2":
        if user_id not in ADMIN_IDS:
            return
        keyboard = [
            [InlineKeyboardButton("FINAL CONFIRM", callback_data="resetdb_confirm")],
            [InlineKeyboardButton("Back", callback_data="admin_back")]
        ]
        await safe_edit(
            """LAST WARNING

This cannot be undone!""",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    elif data == "resetdb_confirm":
        if user_id not in ADMIN_IDS:
            return
        result = await async_admin_reset_db()
        deleted = result.get('deleted', {})
        await safe_edit(
            f"""Database Reset Complete

Users: {deleted.get('users', 0)}
Hits: {deleted.get('hits', 0)}
Keys: {deleted.get('keys', 0)}""",
            parse_mode='HTML'
        )

    elif data == "admin_clearbins_confirm":
        if user_id not in ADMIN_IDS:
            return
        result = await async_api_request('admin-clearbin', {}, 'POST')
        if result.get('success'):
            await safe_edit("BIN Library Cleared!", parse_mode='HTML')
        else:
            await safe_edit(f"Error: {result.get('error', 'Failed to clear')}", parse_mode='HTML')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return

    if not update.effective_user or not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()
    if user_id not in pending_actions:
        return
    action_data = pending_actions.pop(user_id)
    action = action_data.get('action')

    if action == 'genkey':
        result = await async_admin_generate_key(text)
        if result.get('success'):
            await update.message.reply_text(
                f"""Key Generated!

Key: {result['key']}
Version: {result['version']}""",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(f"Error: {result.get('error', 'Unknown')}")

    elif action == 'revokekey':
        result = await async_admin_revoke_key(text)
        if result.get('success'):
            await update.message.reply_text("Key Revoked!", parse_mode='HTML')
        else:
            await update.message.reply_text(f"Error: {result.get('error', 'Key not found')}")

    elif action == 'activatekey':
        result = await async_admin_activate_key(text)
        if result.get('success'):
            await update.message.reply_text("Key Activated!", parse_mode='HTML')
        else:
            await update.message.reply_text(f"Error: {result.get('error', 'Key not found')}")

    elif action == 'deletekey':
        result = await async_admin_delete_key(text)
        if result.get('success'):
            await update.message.reply_text("Key Deleted!", parse_mode='HTML')
        else:
            await update.message.reply_text(f"Error: {result.get('error', 'Key not found')}")

    elif action == 'setchannel':
        result = await async_admin_set_setting('telegram_channel', text)
        if result.get('success'):
            await update.message.reply_text("Channel Updated!", parse_mode='HTML')

    elif action == 'setversion':
        result = await async_admin_set_setting('latest_version', text)
        if result.get('success'):
            await update.message.reply_text(
                f"Version Updated to {text}!",
                parse_mode='HTML'
            )

    elif action == 'banuser':
        result = await async_admin_ban_user(text)
        if result.get('success'):
            await update.message.reply_text("User Banned!", parse_mode='HTML')
        else:
            await update.message.reply_text(f"Error: {result.get('error', 'User not found')}")

    elif action == 'unbanuser':
        result = await async_admin_unban_user(text)
        if result.get('success'):
            await update.message.reply_text("User Unbanned!", parse_mode='HTML')
        else:
            await update.message.reply_text(f"Error: {result.get('error', 'User not found')}")

    elif action == 'addbin':
        parts = text.split('|')
        if len(parts) < 2:
            await update.message.reply_text("Invalid format. Use: site|bin|credit", parse_mode='HTML')
            return
        site = parts[0].strip() if len(parts) > 0 else 'Unknown'
        bin_number = parts[1].strip() if len(parts) > 1 else ''
        credit = parts[2].strip() if len(parts) > 2 else 'Unknown'
        if not bin_number:
            await update.message.reply_text("BIN number is required", parse_mode='HTML')
            return
        result = await async_api_request('admin-addbin', {
            'site': site,
            'bin': bin_number,
            'credit': credit
        }, 'POST')
        if result.get('success'):
            await update.message.reply_text(
                f"""BIN Added!

Site: {site}
BIN: {bin_number}
Type: {credit}""",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(f"Error: {result.get('error', 'Failed to add BIN')}")

    elif action == 'removebin':
        bin_number = text.strip()
        if not bin_number:
            await update.message.reply_text("BIN number is required", parse_mode='HTML')
            return
        result = await async_api_request('admin-removebin', {'bin': bin_number}, 'POST')
        if result.get('success'):
            await update.message.reply_text(f"BIN Removed!\n\n{bin_number}", parse_mode='HTML')
        else:
            await update.message.reply_text(f"Error: {result.get('error', 'BIN not found')}")

    elif action == 'submit_bin':
        message = update.message
        is_valid_forward = False

        if hasattr(message, 'forward_origin') and message.forward_origin:
            origin = message.forward_origin
            if hasattr(origin, 'sender_user') and origin.sender_user:
                username = origin.sender_user.username
                if username and username.lower() == 'usagiautobot':
                    is_valid_forward = True
            elif hasattr(origin, 'chat') and origin.chat:
                username = origin.chat.username
                if username and username.lower() == 'usagiautobot':
                    is_valid_forward = True

        if not is_valid_forward:
            await update.message.reply_text(
                """Invalid Message

Please forward a hit log message from @UsagiAutoBot only.
Try again: Forward a message from @UsagiAutoBot""",
                parse_mode='HTML'
            )
            pending_actions[user_id] = {'action': 'submit_bin'}
            return

        parsed_data = parse_hit_log(text)
        if not parsed_data['bin']:
            await update.message.reply_text(
                """Could not parse BIN

Unable to find a valid BIN in your message.
Please make sure the message is forwarded from hit log bot.

Try again: Forward another hit log message.""",
                parse_mode='HTML'
            )
            pending_actions[user_id] = {'action': 'submit_bin'}
            return

        bin_to_check = parsed_data['bin'][:6]
        bin_to_store = parsed_data['bin'][:10]
        site_to_check = (parsed_data['site'] or '').lower().strip()
        library_result = await async_api_request('bin-library')
        existing_bins = library_result.get('bins', []) if library_result.get('success') else []
        is_duplicate = False
        for existing in existing_bins:
            existing_bin = str(existing.get('bin', '')).strip()[:6]
            existing_site = str(existing.get('site', '')).lower().strip()
            bin_match = existing_bin == bin_to_check
            site_match = False
            if site_to_check and existing_site:
                clean_new = site_to_check.replace('www.', '').replace('http://', '').replace('https://', '')
                clean_existing = existing_site.replace('www.', '').replace('http://', '').replace('https://', '')
                site_match = clean_new == clean_existing
            if bin_match and site_match:
                is_duplicate = True
                break

        if is_duplicate:
            await update.message.reply_text(
                f"""Duplicate BIN

This BIN already exists in the library for this site.

BIN: {bin_to_check}xxx
Site: {parsed_data['site'] or 'Unknown'}

You can submit a different BIN for this site, or a new site.""",
                parse_mode='HTML'
            )
            return

        submission_id = str(uuid.uuid4())[:8]
        submitter_name = html.escape(update.effective_user.first_name or update.effective_user.username or 'User')
        submitter_username = html.escape(update.effective_user.username or update.effective_user.first_name or 'User')
        credit = f"@{submitter_username}" if update.effective_user.username else submitter_name
        pending_bin_submissions[submission_id] = {
            'bin': bin_to_store,
            'site': parsed_data['site'] or 'Unknown',
            'credit': credit,
            'submitter_id': user_id,
            'submitter_name': submitter_name,
            'raw_message': text[:500]
        }
        await update.message.reply_text(
            f"""BIN Submission Received

BIN: {bin_to_store}
Site: {parsed_data['site'] or 'Unknown'}
Credit: {credit}

Your submission has been sent to admins for review. You'll be notified when it's approved or rejected.""",
            parse_mode='HTML'
        )
        keyboard = [
            [InlineKeyboardButton("Accept", callback_data=f"approve_bin_{submission_id}"),
             InlineKeyboardButton("Block", callback_data=f"reject_bin_{submission_id}")]
        ]
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"""New BIN Submission
━━━━━━━━━━━━━━━━━━━━━━
BIN: {bin_to_store}
Site: {parsed_data['site'] or 'Unknown'}
Credit: {credit}

Submitted by: <a href="tg://user?id={user_id}">{submitter_name}</a>

Raw Message:
{text[:300]}...""",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.warning(f"Failed to notify admin {admin_id}: {e}")

def parse_hit_log(text: str) -> dict:
    result = {'bin': None, 'site': None}
    card_pattern = r'(\d{13,19})\|'
    match = re.search(card_pattern, text)
    if match:
        full_card = match.group(1)
        result['bin'] = full_card[:10] if len(full_card) >= 10 else full_card[:6]
    if not result['bin']:
        card_prefix_pattern = r'(?:card|cc|bin)[:\s]+(\d{6,16})'
        match = re.search(card_prefix_pattern, text, re.IGNORECASE)
        if match:
            full_card = match.group(1)
            result['bin'] = full_card[:10] if len(full_card) >= 10 else full_card[:6]
    if not result['bin']:
        standalone_card = r'\b(\d{13,16})\b'
        match = re.search(standalone_card, text)
        if match:
            full_card = match.group(1)
            result['bin'] = full_card[:10] if len(full_card) >= 10 else full_card[:6]
    if not result['bin']:
        masked_card = r'(\d{6})[xX\*]+\d*'
        match = re.search(masked_card, text)
        if match:
            result['bin'] = match.group(1)
    url_pattern = r'https?://(?:www\.)?([a-zA-Z0-9-]+(?:\.[a-zA-Z]{2,})+)'
    match = re.search(url_pattern, text)
    if match:
        result['site'] = match.group(1)
    if not result['site']:
        site_prefix = r'(?:site|business|merchant|store|url)[:\s]+([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        match = re.search(site_prefix, text, re.IGNORECASE)
        if match:
            result['site'] = match.group(1)
    if not result['site']:
        domain_pattern = r'\b([a-zA-Z0-9-]+\.(?:com|net|org|io|co|shop|store))\b'
        match = re.search(domain_pattern, text, re.IGNORECASE)
        if match:
            result['site'] = match.group(1)
    return result

async def remove_bin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /removebin <bin_id>\n\nExample: /removebin abc123", parse_mode='HTML')
        return
    bin_id = context.args[0]
    result = await async_api_request('admin-removebin', {'bin_id': bin_id}, 'POST')
    if result.get('success'):
        await update.message.reply_text(f"""BIN Removed!

ID: {bin_id}
BIN: {result.get('bin', 'N/A')}
Site: {result.get('site', 'N/A')}

BIN has been removed from the library.""", parse_mode='HTML')
    else:
        await update.message.reply_text(f"Failed to remove BIN: {result.get('error', 'BIN not found')}", parse_mode='HTML')

async def genkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /genkey <version>\n\nExample: /genkey 1.3.7", parse_mode='HTML')
        return
    version = context.args[0]
    result = await async_admin_generate_key(version)
    if result.get('success'):
        await update.message.reply_text(f"""Key Generated!

Key: {result['key']}
Version: {result['version']}""", parse_mode='HTML')
    else:
        await update.message.reply_text(f"Error: {result.get('error', 'Unknown')}", parse_mode='HTML')

async def listkeys_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    result = await async_admin_list_keys()
    if result.get('success') and result.get('keys'):
        text = """<b>License Keys
━━━━━━━━━━━━━━━━━━━━━━
"""
        for i, k in enumerate(result['keys'], 1):
            status = "Active" if k.get('active') else "Inactive"
            text += f"{i}. <code>{k['key']}</code>\n   v{k['version']} — {status}\n\n"
    else:
        text = "No keys found."
    await update.message.reply_text(text, parse_mode='HTML')

async def revokekey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /revokekey <key>\n\nExample: /revokekey USAGI-105-ABCD1234EFGH5678IJKL", parse_mode='HTML')
        return
    key = context.args[0]
    result = await async_admin_revoke_key(key)
    if result.get('success'):
        await update.message.reply_text(f"Key Revoked!\n\n{key}", parse_mode='HTML')
    else:
        await update.message.reply_text(f"Error: {result.get('error', 'Key not found')}", parse_mode='HTML')

async def activatekey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /activatekey <key>\n\nExample: /activatekey USAGI-105-ABCD1234EFGH5678IJKL", parse_mode='HTML')
        return
    key = context.args[0]
    result = await async_admin_activate_key(key)
    if result.get('success'):
        await update.message.reply_text(f"Key Activated!\n\n{key}", parse_mode='HTML')
    else:
        await update.message.reply_text(f"Error: {result.get('error', 'Key not found')}", parse_mode='HTML')

async def deletekey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /deletekey <key>\n\nExample: /deletekey USAGI-105-ABCD1234EFGH5678IJKL", parse_mode='HTML')
        return
    key = context.args[0]
    result = await async_admin_delete_key(key)
    if result.get('success'):
        await update.message.reply_text(f"Key Deleted!\n\n{key}", parse_mode='HTML')
    else:
        await update.message.reply_text(f"Error: {result.get('error', 'Key not found')}", parse_mode='HTML')

async def setchannel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /setchannel <link>\n\nExample: /setchannel https://t.me/MyChannel", parse_mode='HTML')
        return
    channel = context.args[0]
    result = await async_admin_set_setting('telegram_channel', channel)
    if result.get('success'):
        await update.message.reply_text(f"Channel Updated!\n\n{channel}", parse_mode='HTML')
    else:
        await update.message.reply_text(f"Error: {result.get('error', 'Failed')}", parse_mode='HTML')

async def setversion_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /setversion <version>\n\nExample: /setversion 1.3.8", parse_mode='HTML')
        return
    version = context.args[0]
    result = await async_admin_set_setting('latest_version', version)
    if result.get('success'):
        await update.message.reply_text(f"Version Updated!\n\n{version}", parse_mode='HTML')
    else:
        await update.message.reply_text(f"Error: {result.get('error', 'Failed')}", parse_mode='HTML')

async def banuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /ban <user_id>\n\nExample: /ban 123456789", parse_mode='HTML')
        return
    target_id = context.args[0]
    result = await async_admin_ban_user(target_id)
    if result.get('success'):
        await update.message.reply_text(f"User Banned!\n\n{target_id}", parse_mode='HTML')
    else:
        await update.message.reply_text(f"Error: {result.get('error', 'User not found')}", parse_mode='HTML')

async def unbanuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /unban <user_id>\n\nExample: /unban 123456789", parse_mode='HTML')
        return
    target_id = context.args[0]
    result = await async_admin_unban_user(target_id)
    if result.get('success'):
        await update.message.reply_text(f"User Unbanned!\n\n{target_id}", parse_mode='HTML')
    else:
        await update.message.reply_text(f"Error: {result.get('error', 'User not found')}", parse_mode='HTML')

async def cleartokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    result = await async_admin_clear_tokens()
    if result.get('success'):
        await update.message.reply_text(f"Tokens & Stats Cleared!\n\n{result.get('message', 'Done')}", parse_mode='HTML')
    else:
        await update.message.reply_text(f"Error: {result.get('error', 'Failed')}", parse_mode='HTML')

async def cleanfakehits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    result = await async_admin_clean_fake_hits()
    if result.get('success'):
        await update.message.reply_text(f"Cleaned {result.get('deleted', 0)} fake records", parse_mode='HTML')
    else:
        await update.message.reply_text(f"Error: {result.get('error', 'Failed')}", parse_mode='HTML')

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    result = await async_admin_get_settings()
    if result.get('success'):
        settings = result.get('settings', {})
        text = """<b>Current Settings
━━━━━━━━━━━━━━━━━━━━━━
"""
        for key, value in settings.items():
            text += f"{key}: {value}\n"
        if not settings:
            text += "No settings configured"
    else:
        text = "Failed to load settings"
    await update.message.reply_text(text, parse_mode='HTML')

async def keyinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return

    version = context.args[0] if context.args else None
    result = await async_admin_keyinfo(version)

    if result.get('success'):
        stats = result.get('stats', {})
        total_keys = stats.get('total_keys', 0)
        active_keys = stats.get('active_keys', 0)
        revoked_keys = stats.get('revoked_keys', 0)
        total_users = stats.get('total_users', 0)

        text = f"""<b>Key Info
━━━━━━━━━━━━━━━━━━━━━━

License Keys:
Total Keys: {total_keys}
Active: {active_keys}
Revoked: {revoked_keys}

Users:
Total Registered: {total_users}
"""

        versions = stats.get('versions', {})
        if versions:
            text += "\nUsers by Version:\n"
            for ver, count in versions.items():
                text += f"v{ver}: {count} users\n"

        top_users = stats.get('top_users', [])
        if top_users:
            text += "\nTop 5 Users:\n"
            for i, u in enumerate(top_users[:5], 1):
                name = u.get('username') or u.get('first_name') or 'User'
                hits = u.get('hits', 0)
                text += f"{i}. {name} — {hits} hits\n"

        await update.message.reply_text(text, parse_mode='HTML')
    else:
        await update.message.reply_text(f"Error: {result.get('error', 'Failed to get key info')}", parse_mode='HTML')

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>\n\nExample: /broadcast Hello everyone! New update available.", parse_mode='HTML')
        return

    message = ' '.join(context.args)

    result = await async_admin_get_all_users()
    if not result.get('success'):
        await update.message.reply_text(f"Error: {result.get('error', 'Failed to get users')}", parse_mode='HTML')
        return

    users = result.get('users', [])
    if not users:
        await update.message.reply_text("No users found to broadcast.")
        return

    progress_msg = await update.message.reply_text(f"Broadcasting to {len(users)} users...")

    success_count = 0
    fail_count = 0

    broadcast_text = f"""<b>{message}</b>"""

    for user in users:
        target_id = user.get('user_id')
        if not target_id:
            continue
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=broadcast_text,
                parse_mode='HTML'
            )
            success_count += 1
        except Exception as e:
            fail_count += 1
            logger.warning(f"Failed to send broadcast to {target_id}: {e}")
        await asyncio.sleep(0.05)

    await progress_msg.edit_text(f"""Broadcast Complete!

Sent: {success_count}
Failed: {fail_count}
Total: {len(users)}""", parse_mode='HTML')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Owner only command.")
        return
    
    result = await async_admin_get_stats()
    if result.get('success'):
        stats = result.get('stats', {})
        text = f"""<b>Global Statistics
━━━━━━━━━━━━━━━━━━━━━━

Users:
Total Users: {stats.get('total_users', 0)}
Active Today: {stats.get('active_today', 0)}

License Keys:
Total Keys: {stats.get('total_keys', 0)}
Active Keys: {stats.get('active_keys', 0)}
Revoked Keys: {stats.get('revoked_keys', 0)}

Hits:
Total Hits: {stats.get('total_hits', 0)}
Hits Today: {stats.get('hits_today', 0)}
Hits This Week: {stats.get('hits_week', 0)}

BIN Library:
Total BINs: {stats.get('total_bins', 0)}
"""
        await update.message.reply_text(text, parse_mode='HTML')
    else:
        await update.message.reply_text(f"Error: {result.get('error', 'Failed to get stats')}", parse_mode='HTML')

async def addbin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /addbin <site> <bin> [credit]\n\nExample: /addbin Amazon 453201511 VISA", parse_mode='HTML')
        return
    site = context.args[0]
    bin_number = context.args[1]
    credit = context.args[2] if len(context.args) > 2 else 'Unknown'
    result = await async_api_request('admin-addbin', {'site': site, 'bin': bin_number, 'credit': credit}, 'POST')
    if result.get('success'):
        bin_data = result.get('bin', {})
        bin_id = bin_data.get('id', 'N/A') if isinstance(bin_data, dict) else 'N/A'
        await update.message.reply_text(f"""BIN Added!

ID: {bin_id}
Site: {site}
BIN: {bin_number}
Type: {credit}""", parse_mode='HTML')
    else:
        await update.message.reply_text(f"Error: {result.get('error', 'Failed to add BIN')}", parse_mode='HTML')

async def listbins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    result = await async_api_request('bin-library')
    if result.get('success') and result.get('bins'):
        text = """<b>BIN Library
━━━━━━━━━━━━━━━━━━━━━━
"""
        for i, b in enumerate(result['bins'], 1):
            text += f"{i}. <code>{b.get('bin', 'N/A')}</code>\n   ID {b.get('id', 'N/A')}\n   {b.get('site', 'N/A')} • {b.get('credit', 'N/A')}\n\n"
    else:
        text = "No BINs in library."
    await update.message.reply_text(text, parse_mode='HTML')

async def clearbins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    result = await async_api_request('admin-clearbin', {}, 'POST')
    if result.get('success'):
        await update.message.reply_text("BIN Library Cleared!", parse_mode='HTML')
    else:
        await update.message.reply_text(f"Error: {result.get('error', 'Failed to clear')}", parse_mode='HTML')

async def resetdb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    if not context.args or context.args[0] != 'CONFIRM':
        await update.message.reply_text("WARNING: This will delete ALL data!\n\nTo confirm, use: /resetdb CONFIRM", parse_mode='HTML')
        return
    result = await async_admin_reset_db()
    if result.get('success'):
        deleted = result.get('deleted', {})
        await update.message.reply_text(f"""Database Reset Complete

Users: {deleted.get('users', 0)}
Hits: {deleted.get('hits', 0)}
Keys: {deleted.get('keys', 0)}""", parse_mode='HTML')
    else:
        await update.message.reply_text(f"Error: {result.get('error', 'Failed')}", parse_mode='HTML')

async def adminhelp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized. Admin only command.")
        return
    
    await update.message.reply_text(
        """<b>Admin Commands
━━━━━━━━━━━━━━━━━━━━━━

License Keys:
/genkey <version> - Generate new key
/listkeys - List all keys
/revokekey <key> - Revoke a key
/activatekey <key> - Activate a key
/deletekey <key> - Delete a key
/keyinfo - View key stats & users by version

BIN Library:
/addbin <site> <bin> [credit] - Add BIN
/listbins - List all BINs
/removebin <id> - Remove BIN by ID
/clearbins - Clear all BINs

User Management:
/ban <user_id> - Ban user
/unban <user_id> - Unban user
/broadcast <message> - Send message to all users

Stats:
/stats - View global statistics

Settings:
/setchannel <link> - Set channel
/setversion <version> - Set version
/settings - View settings

Maintenance:
/cleartokens - Clear all tokens
/cleanfakehits - Clean fake hits
/resetdb CONFIRM - Reset database

Help:
/adminhelp - Show this help""",
        parse_mode='HTML'
    )

async def post_init(app):
    global _bot_instance, _event_loop
    _bot_instance = app.bot
    _event_loop = asyncio.get_running_loop()
    logger.info(f"Flask hit-forward server ready on port {FLASK_PORT}")

def main():
    print("=" * 50)
    print("UsagiAutoX Bot")
    print("=" * 50)

    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("adminhelp", adminhelp_command))
    application.add_handler(CommandHandler("genkey", genkey_command))
    application.add_handler(CommandHandler("listkeys", listkeys_command))
    application.add_handler(CommandHandler("revokekey", revokekey_command))
    application.add_handler(CommandHandler("activatekey", activatekey_command))
    application.add_handler(CommandHandler("deletekey", deletekey_command))
    application.add_handler(CommandHandler("setchannel", setchannel_command))
    application.add_handler(CommandHandler("setversion", setversion_command))
    application.add_handler(CommandHandler("ban", banuser_command))
    application.add_handler(CommandHandler("unban", unbanuser_command))
    application.add_handler(CommandHandler("banuser", banuser_command))
    application.add_handler(CommandHandler("unbanuser", unbanuser_command))
    application.add_handler(CommandHandler("cleartokens", cleartokens_command))
    application.add_handler(CommandHandler("cleanfakehits", cleanfakehits_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("keyinfo", keyinfo_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("addbin", addbin_command))
    application.add_handler(CommandHandler("listbins", listbins_command))
    application.add_handler(CommandHandler("removebin", remove_bin_command))
    application.add_handler(CommandHandler("clearbins", clearbins_command))
    application.add_handler(CommandHandler("resetdb", resetdb_command))

    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print(f"Hit-forward server on port {FLASK_PORT}")

    print("Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()