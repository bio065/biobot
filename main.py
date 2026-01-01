import os
import asyncio
import logging
import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

# Loglarni sozlash
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DB_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def create_db_pool():
    logger.info("Bazaga ulanish...")
    try:
        # statement_cache_size=0 BU JUDA MUHIM!
        # Busiz Supabase Transaction Mode ishlamaydi.
        pool = await asyncpg.create_pool(
            DB_URL,
            min_size=1,
            max_size=2,
            command_timeout=60,
            statement_cache_size=0 
        )
        logger.info("✅ Baza ulandi!")
        return pool
    except Exception as e:
        logger.error(f"❌ Ulanish xatosi: {e}")
        return None

@dp.message(CommandStart())
async def cmd_start(message: types.Message, db_pool):
    if not db_pool:
        await message.answer("Baza bilan aloqa yo'q.")
        return

    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (id, full_name) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING",
                message.from_user.id, message.from_user.full_name
            )
        await message.answer(f"Salom, {message.from_user.full_name}! Bazaga yozildingiz.")
        logger.info("User qo'shildi.")
    except Exception as e:
        logger.error(f"Xato: {e}")
        # Agar xato bo'lsa ham userga bildirmaymiz, logga yozamiz xolos
        await message.answer("Xush kelibsiz!")

async def main():
    # Eski update'larni o'chiramiz (Conflictni oldini oladi)
    await bot.delete_webhook(drop_pending_updates=True)

    pool = await create_db_pool()
    
    # Jadvalni kod orqali emas, Supabase saytidan yaratgan ma'qul.
    # Lekin har ehtimolga qarshi oddiy so'rov:
    if pool:
        try:
            async with pool.acquire() as conn:
                await conn.execute("CREATE TABLE IF NOT EXISTS users (id BigInt PRIMARY KEY, full_name Text);")
        except:
            pass # Jadval bor deb faraz qilamiz

    await dp.start_polling(bot, db_pool=pool)

if __name__ == "__main__":
    asyncio.run(main())
