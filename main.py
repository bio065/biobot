import os
import asyncio
import logging
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import FSInputFile
from aiogram.exceptions import TelegramBadRequest

# --- 1. SOZLAMALAR ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Render Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DB_URL")

# ---------------------------------------------------------
# !!! DIQQAT: KANAL SOZLAMALARI !!!
# 1. Agar kanalingiz ochiq bo'lsa (usernamesi bor): "@KanalUsername"
# 2. Agar yopiq bo'lsa (linkli): "-100..." bilan boshlanadigan ID raqam (Int)
# ---------------------------------------------------------
KANAL_ID = "-1003504661215" 
KANAL_URL = "https://t.me/chekbotttt"

if not BOT_TOKEN or not DB_URL:
    logger.critical("❌ BOT_TOKEN yoki DB_URL topilmadi!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- 2. BAZA BILAN ISHLASH ---
async def create_db_pool():
    try:
        pool = await asyncpg.create_pool(
            DB_URL, min_size=1, max_size=5, command_timeout=60, statement_cache_size=0
        )
        logger.info("✅ Baza ulandi!")
        return pool
    except Exception as e:
        logger.error(f"❌ Baza xatosi: {e}")
        return None

# --- 3. KANAL TEKSHIRISH (DIAGNOSTIKA BILAN) ---
async def check_subscription(user_id):
    """
    Foydalanuvchi kanalga a'zo ekanligini aniq tekshiradi
    va xatolik bo'lsa logga yozadi.
    """
    try:
        # KANAL_ID ni to'g'irlash (String yoki Integer masalasi)
        chat_id = KANAL_ID
        
        # Agar ID raqam bo'lsa (-100...), uni songa aylantiramiz
        if str(chat_id).startswith("-100"):
            chat_id = int(chat_id)
        
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        
        # Logga yozamiz (tekshirish uchun)
        logger.info(f"User: {user_id} | Status: {member.status}")
        
        if member.status in ['member', 'administrator', 'creator']:
            return True, None # (A'zo, Xatolik yo'q)
        else:
            return False, None # (A'zo emas, Xatolik yo'q)

    except TelegramBadRequest as e:
        # Telegram qaytargan aniq xatoni ushlaymiz
        logger.error(f"Telegram API Xatosi: {e}")
        if "chat not found" in str(e).lower():
            return False, "Kanal topilmadi! ID xato yozilgan."
        if "bot is not a member" in str(e).lower(): # Ba'zan admin bo'lmasa shunday deydi
            return False, "Bot kanalga Admin qilinmagan!"
        return False, f"Texnik xato: {e}"
    except Exception as e:
        logger.error(f"Boshqa xato: {e}")
        return False, f"Noma'lum xato: {e}"

# --- 4. USER RO'YXATGA OLISH ---
async def register_user(user_id, full_name, username, referrer_id, pool):
    if not pool: return "db_error"
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                exists = await conn.fetchval("SELECT 1 FROM users WHERE id = $1", user_id)
                if exists: return "old_user"

                await conn.execute("""
                    INSERT INTO users (id, full_name, username, referrer_id) 
                    VALUES ($1, $2, $3, $4)
                """, user_id, full_name, username, referrer_id)

                if referrer_id:
                    await conn.execute("UPDATE users SET referral_count = referral_count + 1 WHERE id = $1", referrer_id)
                    return "referral_success"
                return "new_user"
    except Exception as e:
        logger.error(f"DB Insert Error: {e}")
        return "db_error"

# --- 5. TUGMALAR ---
def sub_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Kanalga a'zo bo'lish", url=KANAL_URL)
    kb.button(text="✅ A'zolikni tekshirish", callback_data="check_subscription")
    kb.adjust(1)
    return kb.as_markup()

def main_menu_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔗 Referal (Do'stlarni chaqirish)", callback_data="referral_menu")
    kb.button(text="📊 Statistika", callback_data="my_stats")
    kb.adjust(1)
    return kb.as_markup()

# --- 6. HANDLERLAR ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject, db_pool):
    user = message.from_user
    
    # 1. Obunani tekshirish
    is_sub, error_msg = await check_subscription(user.id)

    # Agar botda sozlash xatosi bo'lsa, adminga (sizga) aytadi
    if error_msg: 
        await message.answer(f"⚠️ <b>BOTDA SOZLASH XATOSI BOR:</b>\n{error_msg}\n\nIltimos, KANAL_ID ni tekshiring va Bot Admin ekanligiga ishonch hosil qiling.", parse_mode="HTML")
        return

    # Agar obuna bo'lmasa
    if not is_sub:
        await message.answer(
            f"👋 Assalomu alaykum, {user.full_name}!\nBotdan foydalanish uchun kanalimizga obuna bo'ling:",
            reply_markup=sub_keyboard()
        )
        return

    # 2. Referal va Ro'yxatdan o'tish
    args = command.args
    referrer_id = int(args) if args and args.isdigit() and int(args) != user.id else None
    
    status = await register_user(user.id, user.full_name, user.username, referrer_id, db_pool)

    if status == "referral_success":
        try:
            await bot.send_message(referrer_id, f"🎉 <b>{user.full_name}</b> sizning havolangiz orqali qo'shildi!", parse_mode="HTML")
        except: pass
    
    await message.answer(f"✅ Xush kelibsiz, <b>{user.full_name}</b>!", reply_markup=main_menu_keyboard(), parse_mode="HTML")

# Obunani tekshirish tugmasi bosilganda
@dp.callback_query(F.data == "check_subscription")
async def on_check(call: types.CallbackQuery, db_pool):
    is_sub, error_msg = await check_subscription(call.from_user.id)
    
    if error_msg:
        await call.answer(f"Xatolik: {error_msg}", show_alert=True)
        return

    if is_sub:
        await call.message.delete()
        # Bazaga qo'shib qo'yamiz (ehtiyot shart)
        user = call.from_user
        await register_user(user.id, user.full_name, user.username, None, db_pool)
        await call.message.answer("✅ Rahmat! Siz muvaffaqiyatli a'zo bo'ldingiz.", reply_markup=main_menu_keyboard())
    else:
        await call.answer("❌ Siz hali kanalga a'zo bo'lmadingiz!", show_alert=True)

# Referal menyusi
@dp.callback_query(F.data == "referral_menu")
async def referral_menu(call: types.CallbackQuery, db_pool):
    if not db_pool: return
    user = call.from_user
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={user.id}"
    
    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT referral_count FROM users WHERE id = $1", user.id) or 0
    
    share_url = f"https://t.me/share/url?url={link}&text=Zo'r%20bot%20ekan!"
    kb = InlineKeyboardBuilder()
    kb.button(text="↗️ Do'stlarga yuborish", url=share_url)
    kb.button(text="🔙 Orqaga", callback_data="back_home")
    kb.adjust(1)
    
    await call.message.edit_text(
        f"🔗 <b>Referal havolangiz:</b>\n<code>{link}</code>\n\n👥 <b>Takliflaringiz:</b> {count} ta",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data == "back_home")
async def back_home(call: types.CallbackQuery):
    await call.message.edit_text("🏠 Asosiy menyu:", reply_markup=main_menu_keyboard())

@dp.callback_query(F.data == "my_stats")
async def my_stats(call: types.CallbackQuery, db_pool):
    if not db_pool: return
    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT referral_count FROM users WHERE id = $1", call.from_user.id) or 0
    await call.answer(f"📊 Sizning natijangiz: {count} ta referal", show_alert=True)

# Admin statistikasi
@dp.message(Command("stat"))
async def cmd_stat(message: types.Message, db_pool):
    if not db_pool: return
    msg = await message.answer("⏳ ...")
    try:
        async with db_pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM users")
            users = await conn.fetch("SELECT full_name, username, referral_count FROM users ORDER BY referral_count DESC")
        
        with open("stat.txt", "w", encoding="utf-8") as f:
            f.write(f"JAMI: {count}\n\n")
            for i, u in enumerate(users, 1):
                f.write(f"{i}. {u['full_name']} (@{u['username']}) - Ref: {u['referral_count']}\n")
        
        await message.answer_document(FSInputFile("stat.txt"), caption=f"Jami: {count}")
        await msg.delete()
        os.remove("stat.txt")
    except Exception as e:
        await message.answer(f"Xato: {e}")

# --- 7. ISHGA TUSHIRISH ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    pool = await create_db_pool()
    await dp.start_polling(bot, db_pool=pool)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): pass
