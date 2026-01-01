import os
import asyncio
import logging
import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

# Loglarni formatlash: vaqti, darajasi va xabari
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# O'zgaruvchilarni olish
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DB_URL")

# Xavfsizlik tekshiruvi
if not BOT_TOKEN:
    logger.error("BOT_TOKEN topilmadi! Render Environment Variables'ni tekshiring.")
if not DB_URL:
    logger.error("DB_URL topilmadi! Render Environment Variables'ni tekshiring.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def create_db_pool():
    try:
        # DB_URL ichida maxsus belgilar bo'lsa ham ulanishga harakat qiladi
        pool = await asyncpg.create_pool(DB_URL, timeout=30)
        logger.info("✅ Ma'lumotlar bazasiga muvaffaqiyatli ulanish hovuzi yaratildi.")
        return pool
    except Exception as e:
        logger.error(f"❌ Bazaga ulanishda xatolik: {type(e).__name__}: {e}")
        return None

@dp.message(CommandStart())
async def cmd_start(message: types.Message, db_pool):
    if not db_pool:
        await message.answer("Baza bilan aloqa yo'q.")
        return

    user_id = message.from_user.id
    full_name = message.from_user.full_name

    try:
        async with db_pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO users (id, full_name) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING",
                user_id, full_name
            )
        await message.answer(f"Salom, {full_name}! Siz muvaffaqiyatli ro'yxatga olindingiz.")
        logger.info(f"User {user_id} bazaga qo'shildi/bor edi.")
    except Exception as e:
        logger.error(f"INSERT xatosi: {e}")
        await message.answer("Ma'lumotni saqlashda xatolik yuz berdi.")

async def main():
    logger.info("Bot ishga tushmoqda...")
    
    # Pool yaratamiz
    pool = await create_db_pool()
    
    if pool:
        # Jadval borligini tekshirish/yaratish
        try:
            async with pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id BigInt PRIMARY KEY,
                        full_name Text,
                        created_at Timestamptz DEFAULT NOW()
                    );
                """)
                logger.info("✅ Foydalanuvchilar jadvali tekshirildi.")
        except Exception as e:
            logger.error(f"Jadval yaratishda xato: {e}")

    # Botni ishga tushirish (poolni har bir handlerga uzatamiz)
    await dp.start_polling(bot, db_pool=pool)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
