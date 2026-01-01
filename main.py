import os
import asyncio
import logging
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import FSInputFile

# --- 1. SOZLAMALAR ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Render Environment Variables dan olish
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DB_URL")

# !!! DIQQAT: SHU YERGA KANALINGIZNI YOZING !!!
# Kanal ID raqami (-100 bilan boshlanadi) yoki Usernamesi (@bilan)
KANAL_ID = "@chekbotttt" 
KANAL_URL = "https://t.me/chekbotttt"

# Tekshiruv
if not BOT_TOKEN or not DB_URL:
    logger.critical("❌ BOT_TOKEN yoki DB_URL topilmadi! Render sozlamalarini tekshiring.")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- 2. BAZA BILAN ISHLASH ---
async def create_db_pool():
    logger.info("⏳ Bazaga ulanish...")
    try:
        pool = await asyncpg.create_pool(
            DB_URL,
            min_size=1, max_size=5, command_timeout=60,
            statement_cache_size=0  # Supabase Pooler uchun eng muhim sozlama!
        )
        logger.info("✅ Baza ulandi!")
        return pool
    except Exception as e:
        logger.error(f"❌ Baza ulanish xatosi: {e}")
        return None

# Userni bazaga yozish (Insert/Update)
async def add_user(user_id, full_name, username, pool):
    if not pool: return
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (id, full_name, username) 
                VALUES ($1, $2, $3) 
                ON CONFLICT (id) DO UPDATE 
                SET full_name = $2, username = $3
            """, user_id, full_name, username)
            logger.info(f"User saqlandi: {full_name}")
    except Exception as e:
        logger.error(f"Write Error: {e}")

# --- 3. OBUNA TEKSHIRISH ---
async def check_sub(user_id):
    try:
        member = await bot.get_chat_member(chat_id=KANAL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Kanal tekshirishda xato (Bot adminmi?): {e}")
        return False

def sub_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Kanalga a'zo bo'lish", url=KANAL_URL)
    kb.button(text="✅ Tekshirish", callback_data="check_subscription")
    kb.adjust(1)
    return kb.as_markup()

# --- 4. HANDLERLAR ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, db_pool):
    user = message.from_user
    
    # Obunani tekshirish
    if await check_sub(user.id):
        # Bazaga yozish
        await add_user(user.id, user.full_name, user.username, db_pool)
        await message.answer(f"Assalomu alaykum, {user.full_name}! 👋\nBotdan foydalanishingiz mumkin.")
    else:
        await message.answer(
            f"Hurmatli {user.full_name}, botdan foydalanish uchun kanalimizga a'zo bo'ling!",
            reply_markup=sub_keyboard()
        )

@dp.callback_query(F.data == "check_subscription")
async def on_check(call: types.CallbackQuery, db_pool):
    user = call.from_user
    if await check_sub(user.id):
        await call.message.delete()
        await add_user(user.id, user.full_name, user.username, db_pool)
        await call.message.answer("✅ Rahmat! Siz muvaffaqiyatli ro'yxatdan o'tdingiz.")
    else:
        await call.answer("❌ Siz hali kanalga a'zo bo'lmadingiz!", show_alert=True)

# STATISTIKA VA FAYL YUKLASH
@dp.message(Command("stat"))
async def cmd_stat(message: types.Message, db_pool):
    if not db_pool: 
        await message.answer("Baza bilan aloqa yo'q.")
        return
    
    status_msg = await message.answer("⏳ Ma'lumotlar tayyorlanmoqda...")

    try:
        async with db_pool.acquire() as conn:
            # 1. Jami soni
            count = await conn.fetchval("SELECT COUNT(*) FROM users")
            # 2. Ro'yxatni olish
            rows = await conn.fetch("SELECT full_name, username, created_at FROM users ORDER BY created_at DESC")

        # Faylga yozish
        file_path = "obunachilar_royxati.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"JAMI OBUNACHILAR: {count} ta\n")
            f.write(f"Hozirgi vaqt: {message.date}\n")
            f.write("="*40 + "\n\n")
            
            for i, row in enumerate(rows, 1):
                name = row['full_name'] or "Ism yo'q"
                uname = f"@{row['username']}" if row['username'] else "Usernamesiz"
                time = row['created_at'].strftime("%Y-%m-%d %H:%M") if row['created_at'] else ""
                f.write(f"{i}. {name} | {uname} | {time}\n")

        # Faylni yuborish
        await message.answer_document(
            FSInputFile(file_path),
            caption=f"📊 **Statistika:**\nJami foydalanuvchilar: {count} ta"
        )
        await status_msg.delete()

        # Faylni o'chirish
        os.remove(file_path)

    except Exception as e:
        logger.error(f"Stat error: {e}")
        await message.answer("Xatolik yuz berdi.")

# --- 5. ISHGA TUSHIRISH ---
async def main():
    # Conflict xatosini oldini olish
    await bot.delete_webhook(drop_pending_updates=True)
    
    pool = await create_db_pool()
    
    # Jadvalni avtomatik yaratish
    if pool:
        try:
            async with pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id BIGINT PRIMARY KEY,
                        full_name TEXT,
                        username TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                logger.info("✅ Jadval tekshirildi.")
        except Exception as e:
            logger.error(f"Jadval yaratish xatosi: {e}")

    await dp.start_polling(bot, db_pool=pool)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
