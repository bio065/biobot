import os
import asyncio
import logging
import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

# Loglarni sozlash
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# O'zgaruvchilarni olish
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DB_URL")

if not BOT_TOKEN:
    logger.critical("BOT_TOKEN topilmadi!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ENG MUHIM QISM (TUZATILDI) ---
async def create_db_pool():
    logger.info("Bazaga ulanishga harakat qilinmoqda...")
    try:
        # statement_cache_size=0 -> Bu Supabase Pooler bilan ishlash uchun SHART!
        pool = await asyncpg.create_pool(
            DB_URL,
            min_size=1,
            max_size=5,
            command_timeout=60,
            statement_cache_size=0  # <--- MANA SHU NARSANI QO'SHDIK, XATOLIKNI YO'QOTADI
        )
        logger.info("✅ Baza bilan aloqa muvaffaqiyatli o'rnatildi!")
        return pool
    except Exception as e:
        logger.error(f"❌ Bazaga ulanishda xato: {e}")
        return None

@dp.message(CommandStart())
async def cmd_start(message: types.Message, db_pool):
    user_id = message.from_user.id
    full_name = message.from_user.full_name

    if not db_pool:
        await message.answer("⚠️ Bot hozircha baza bilan bog'lana olmayapti.")
        return

    try:
        async with db_pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO users (id, full_name) 
                VALUES ($1, $2) 
                ON CONFLICT (id) DO NOTHING
                """,
                user_id, full_name
            )
        await message.answer(f"Assalomu alaykum, {full_name}! ✅\nSiz muvaffaqiyatli bazaga qo'shildingiz.")
        logger.info(f"Yangi foydalanuvchi: {full_name} ({user_id})")
        
    except Exception as e:
        logger.error(f"Ma'lumot saqlashda xato: {e}")
        await message.answer("Texnik xatolik yuz berdi.")

async def main():
    # Webhookni tozalash
    await bot.delete_webhook(drop_pending_updates=True)

    # Bazaga ulanish
    pool = await create_db_pool()

    if pool:
        try:
            # Jadval yaratish
            async with pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id BigInt PRIMARY KEY,
                        full_name Text,
                        created_at Timestamptz DEFAULT NOW()
                    );
                """)
            logger.info("✅ 'users' jadvali tekshirildi/yaratildi.")
        except Exception as e:
            logger.error(f"Jadval yaratishda xato: {e}")
    
    # Botni ishga tushirish
    await dp.start_polling(bot, db_pool=pool)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
