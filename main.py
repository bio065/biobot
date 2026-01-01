import os
import asyncio
import logging
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject # <-- MUHIM: CommandObject qo'shildi
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import FSInputFile

# --- SOZLAMALAR ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DB_URL")

# KANALINGIZNI YOZING
KANAL_ID = "chekbotttt"
KANAL_URL = "https://t.me/chekbotttt"

if not BOT_TOKEN or not DB_URL:
    logger.critical("❌ Token yoki DB_URL topilmadi!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- BAZA BILAN ISHLASH ---
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

# --- USER RO'YXATGA OLISH ---
async def register_user(user_id, full_name, username, referrer_id, pool):
    if not pool: return "error"
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # User bormi?
                exists = await conn.fetchval("SELECT 1 FROM users WHERE id = $1", user_id)
                if exists:
                    return "old_user"

                # Yangi userni qo'shish
                await conn.execute("""
                    INSERT INTO users (id, full_name, username, referrer_id) 
                    VALUES ($1, $2, $3, $4)
                """, user_id, full_name, username, referrer_id)

                # Referalga ball berish
                if referrer_id:
                    await conn.execute("""
                        UPDATE users SET referral_count = referral_count + 1 WHERE id = $1
                    """, referrer_id)
                    return "referral_success"
                
                return "new_user_no_ref"
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return "error"

# --- TUGMALAR ---
def sub_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Kanalga a'zo bo'lish", url=KANAL_URL)
    kb.button(text="✅ Obunani tekshirish", callback_data="check_subscription")
    kb.adjust(1)
    return kb.as_markup()

def main_menu_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="↗️ Do'stlarni taklif qilish", callback_data="referral_menu")
    kb.button(text="📊 Statistika", callback_data="my_stats")
    kb.adjust(1)
    return kb.as_markup()

# --- HANDLERLAR ---

# --- TUZATILGAN JOYI SHU YERDA ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject, db_pool):
    user = message.from_user
    
    # Argumentni to'g'ri olish
    args = command.args 
    
    referrer_id = None
    if args and args.isdigit():
        potential_ref = int(args)
        if potential_ref != user.id:
            referrer_id = potential_ref

    # Kanalga obuna tekshirish
    try:
        member = await bot.get_chat_member(KANAL_ID, user.id)
        is_sub = member.status in ['member', 'administrator', 'creator']
    except:
        is_sub = False

    if not is_sub:
        await message.answer(
            f"👋 Salom {user.full_name}! Botdan foydalanish uchun kanalga a'zo bo'ling:",
            reply_markup=sub_keyboard()
        )
        return

    # Bazaga yozish
    status = await register_user(user.id, user.full_name, user.username, referrer_id, db_pool)

    if status == "referral_success":
        try:
            await bot.send_message(referrer_id, f"🎉 Sizda yangi referal: <b>{user.full_name}</b>", parse_mode="HTML")
        except: pass

    await message.answer(f"✅ Xush kelibsiz! Menyu:", reply_markup=main_menu_keyboard())

# --- QOLGAN HANDLERLAR (REFERAL MENYU) ---
@dp.callback_query(F.data == "check_subscription")
async def on_check(call: types.CallbackQuery):
    try:
        member = await bot.get_chat_member(KANAL_ID, call.from_user.id)
        if member.status in ['member', 'administrator', 'creator']:
            await call.message.delete()
            await call.message.answer("✅ Obuna tasdiqlandi!", reply_markup=main_menu_keyboard())
        else:
            await call.answer("❌ Hali a'zo bo'lmadingiz!", show_alert=True)
    except:
        await call.answer("Xatolik", show_alert=True)

@dp.callback_query(F.data == "referral_menu")
async def show_ref(call: types.CallbackQuery, db_pool):
    if not db_pool: return
    user = call.from_user
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user.id}"

    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT referral_count FROM users WHERE id = $1", user.id) or 0

    share_url = f"https://t.me/share/url?url={ref_link}&text=Zo'r%20bot%20ekan!"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="↗️ Do'stlarga ulashish", url=share_url)
    kb.button(text="🔙 Orqaga", callback_data="back_home")
    kb.adjust(1)

    await call.message.edit_text(
        f"🔗 <b>Sizning havolangiz:</b>\n<code>{ref_link}</code>\n\n👥 <b>Takliflaringiz:</b> {count} ta",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data == "my_stats")
async def my_stats(call: types.CallbackQuery, db_pool):
    if not db_pool: return
    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT referral_count FROM users WHERE id = $1", call.from_user.id) or 0
    await call.answer(f"Siz {count} ta odam chaqirgansiz.", show_alert=True)

@dp.callback_query(F.data == "back_home")
async def back(call: types.CallbackQuery):
    await call.message.edit_text("🏠 Menyu:", reply_markup=main_menu_keyboard())

# --- ISHGA TUSHIRISH ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True) # Bu eski connectionlarni o'chiradi
    pool = await create_db_pool()
    await dp.start_polling(bot, db_pool=pool)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): pass
