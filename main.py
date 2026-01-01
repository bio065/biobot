import os
import asyncio
import logging
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command

# 1. Loglarni maksimal darajada yoqamiz
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 2. Sozlamalar
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DB_URL")

# Tokenlarni tekshirish
if not BOT_TOKEN:
    logger.critical("❌ BOT_TOKEN topilmadi!")
    exit(1)
if not DB_URL:
    logger.critical("❌ DB_URL topilmadi!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# 3. Baza bilan ideal ulanish (Supabase uchun moslashtirilgan)
async def create_db_pool():
    logger.info("⏳ Bazaga ulanishga harakat qilinmoqda...")
    try:
        pool = await asyncpg.create_pool(
            DB_URL,
            min_size=1,
            max_size=5,
            command_timeout=60,
            statement_cache_size=0  # ⚠️ Supabase uchun eng muhim joyi!
        )
        logger.info("✅ Baza bilan aloqa 100% o'rnatildi!")
        return pool
    except Exception as e:
        logger.error(f"❌ Ulanishda jiddiy xato: {e}")
        return None

# 4. START komandasi (Insert + Verify)
@dp.message(CommandStart())
async def cmd_start(message: types.Message, db_pool):
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username

    if not db_pool:
        await message.answer("⚠️ Baza bilan aloqa yo'q.")
        return

    try:
        async with db_pool.acquire() as conn:
            # Tranzaksiya ochamiz (xavfsiz yozish uchun)
            async with conn.transaction():
                # 1. Yozishga harakat qilamiz
                await conn.execute(
                    """
                    INSERT INTO users (id, full_name, username) 
                    VALUES ($1, $2, $3) 
                    ON CONFLICT (id) DO UPDATE 
                    SET full_name = $2, username = $3
                    """,
                    user_id, full_name, username
                )
                
                # 2. Yozganimizni darhol tekshiramiz (Verification)
                check_user = await conn.fetchval("SELECT id FROM users WHERE id = $1", user_id)
                
        if check_user:
            await message.answer(f"✅ {full_name}, siz bazaga muvaffaqiyatli saqlandingiz!\nBaza tekshirildi: OK.")
            logger.info(f"User saved and verified: {user_id}")
        else:
            await message.answer("❌ G'alati holat: Dastur yozdi, lekin bazadan topilmadi.")
            logger.warning(f"User write failed implicitly: {user_id}")

    except Exception as e:
        logger.error(f"❌ INSERT ERROR: {e}")
        await message.answer(f"Texnik xatolik: {e}")

# 5. STAT komandasi (Bazadagi sonni bilish uchun)
@dp.message(Command("stat"))
async def cmd_stat(message: types.Message, db_pool):
    if not db_pool:
        return
    try:
        async with db_pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM users")
        await message.answer(f"📊 Hozir bazada {count} ta foydalanuvchi bor.")
    except Exception as e:
        await message.answer(f"Xato: {e}")

# 6. Asosiy ishga tushiruvchi
async def main():
    # Conflict xatosini oldini olish
    await bot.delete_webhook(drop_pending_updates=True)

    pool = await create_db_pool()

    # Jadvalni yaratish (Agar bo'lmasa)
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
            logger.info("✅ Jadval strukturasi tekshirildi.")
        except Exception as e:
            logger.error(f"❌ Jadval yaratishda xato: {e}")

    await dp.start_polling(bot, db_pool=pool)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
