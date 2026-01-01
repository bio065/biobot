import os
import asyncio
import logging
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, CommandObject # <-- CommandObject qo'shildi
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import FSInputFile

# --- 1. SOZLAMALAR ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Render Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DB_URL")

# !!! KANALINGIZNI YOZING !!!
KANAL_ID = "@chekbotttt"
KANAL_URL = "https://t.me/chekbotttt"

if not BOT_TOKEN or not DB_URL:
    logger.critical("❌ Token yoki DB_URL topilmadi!")
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

# --- 3. REFERAL VA USER MANTIQI ---

async def register_user(user_id, full_name, username, referrer_id, pool):
    if not pool: return False

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # 1. User avval bormi tekshiramiz
                exists = await conn.fetchval("SELECT 1 FROM users WHERE id = $1", user_id)
                
                if exists:
                    return "old_user"

                # 2. Yangi userni qo'shamiz
                await conn.execute("""
                    INSERT INTO users (id, full_name, username, referrer_id) 
                    VALUES ($1, $2, $3, $4)
                """, user_id, full_name, username, referrer_id)

                # 3. Agar referrer bo'lsa, uning balini oshiramiz
                if referrer_id:
                    await conn.execute("""
                        UPDATE users SET referral_count = referral_count + 1 WHERE id = $1
                    """, referrer_id)
                    return "referral_success"
                
                return "new_user_no_ref"

    except Exception as e:
        logger.error(f"DB Error: {e}")
        return "error"

# --- 4. YORDAMCHI TUGMALAR ---
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

# --- 5. HANDLERLAR ---

# DIQQAT: Bu yerda 'command: CommandObject' qo'shildi!
@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject, db_pool):
    user = message.from_user
    args = command.args # Endi xato bermaydi, argumentni shu yerdan oladi
    
    referrer_id = None
    if args and args.isdigit():
        potential_referrer = int(args)
        if potential_referrer != user.id: # O'ziga o'zi referal bo'lolmaydi
            referrer_id = potential_referrer

    # 1. Kanalga a'zolikni tekshirish
    try:
        member = await bot.get_chat_member(KANAL_ID, user.id)
        is_sub = member.status in ['member', 'administrator', 'creator']
    except:
        is_sub = False 

    if not is_sub:
        await message.answer(
            f"👋 Salom, {user.full_name}!\nBotdan foydalanish uchun kanalimizga a'zo bo'ling 👇",
            reply_markup=sub_keyboard()
        )
        return

    # 2. Bazaga yozish va Referalni tekshirish
    status = await register_user(user.id, user.full_name, user.username, referrer_id, db_pool)

    # 3. Natijaga qarab javob berish
    if status == "referral_success":
        try:
            await bot.send_message(referrer_id, f"🎉 Tabriklaymiz! Sizning havolangiz orqali <b>{user.full_name}</b> botga qo'shildi.")
        except: pass

    await message.answer(f"✅ Xush kelibsiz, <b>{user.full_name}</b>!\nMenyu tanlang:", reply_markup=main_menu_keyboard(), parse_mode="HTML")

# Obunani qayta tekshirish
@dp.callback_query(F.data == "check_subscription")
async def on_check(call: types.CallbackQuery):
    user = call.from_user
    try:
        member = await bot.get_chat_member(KANAL_ID, user.id)
        if member.status in ['member', 'administrator', 'creator']:
            await call.message.delete()
            await call.message.answer("✅ Obuna tasdiqlandi! Menyu:", reply_markup=main_menu_keyboard())
        else:
            await call.answer("❌ Siz hali a'zo bo'lmadingiz!", show_alert=True)
    except:
        await call.answer("Texnik xatolik", show_alert=True)

# REFERAL MENYUSI
@dp.callback_query(F.data == "referral_menu")
async def show_referral(call: types.CallbackQuery, db_pool):
    user = call.from_user
    if not db_pool: return

    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user.id}"

    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT referral_count FROM users WHERE id = $1", user.id) or 0

    share_url = f"https://t.me/share/url?url={ref_link}&text=Ajoyib%20bot%20topdim,%20kirib%20ko'r!"

    kb = InlineKeyboardBuilder()
    kb.button(text="↗️ Do'stlarga yuborish", url=share_url)
    kb.button(text="🔙 Orqaga", callback_data="back_home")
    kb.adjust(1)

    text = (
        f"🔗 <b>Sizning Referal Havolangiz:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"👥 <b>Taklif qilganlaringiz:</b> {count} ta odam\n\n"
        f"👇 Havolani tarqating va ball yig'ing!"
    )
    
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# STATISTIKA (USER UCHUN)
@dp.callback_query(F.data == "my_stats")
async def my_stats(call: types.CallbackQuery, db_pool):
    user = call.from_user
    if not db_pool: return

    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT referral_count FROM users WHERE id = $1", user.id) or 0
    
    await call.answer(f"📊 Siz jami {count} ta odam taklif qildingiz!", show_alert=True)

@dp.callback_query(F.data == "back_home")
async def go_home(call: types.CallbackQuery):
    await call.message.edit_text("🏠 Asosiy menyu:", reply_markup=main_menu_keyboard())

# --- 6. ADMIN STATISTIKASI (FAYL BILAN) ---
@dp.message(Command("stat"))
async def cmd_stat(message: types.Message, db_pool):
    if not db_pool: return
    
    msg = await message.answer("⏳ Hisoblanmoqda...")
    
    try:
        async with db_pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM users")
            top_users = await conn.fetch("SELECT full_name, referral_count FROM users ORDER BY referral_count DESC LIMIT 10")
            all_users = await conn.fetch("SELECT full_name, username, created_at, referral_count FROM users ORDER BY created_at DESC")

        file_path = "statistika.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"JAMI FOYDALANUVCHILAR: {count} ta\n")
            f.write("="*30 + "\n\n")
            f.write("TOP 10 REFERALLAR:\n")
            for u in top_users:
                f.write(f"- {u['full_name']}: {u['referral_count']} ta\n")
            f.write("\n" + "="*30 + "\n\n")
            f.write("TO'LIQ RO'YXAT:\n")
            for i, u in enumerate(all_users, 1):
                name = u['full_name'] or "NoName"
                uname = f"@{u['username']}" if u['username'] else "NoUser"
                f.write(f"{i}. {name} | {uname} | Ref: {u['referral_count']}\n")

        await message.answer_document(FSInputFile(file_path), caption=f"📊 <b>Jami:</b> {count} ta")
        await msg.delete()
        os.remove(file_path)

    except Exception as e:
        logger.error(e)
        await message.answer("Xatolik.")

# --- 7. START ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    pool = await create_db_pool()
    await dp.start_polling(bot, db_pool=pool)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): pass
