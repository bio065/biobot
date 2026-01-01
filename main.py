import os
import asyncio
import logging
import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

# Loglarni yoqish
logging.basicConfig(level=logging.INFO)

# O'zgaruvchilarni "Environment"dan olamiz (Xavfsizlik uchun)
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DB_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Bazaga ulanish hovuzi (Pool)
async def create_db_pool():
    return await asyncpg.create_pool(DB_URL)

@dp.message(CommandStart())
async def cmd_start(message: types.Message, db_pool):
    user_id = message.from_user.id
    full_name = message.from_user.full_name

    try:
        # Bazaga yozish (INSERT)
        # ON CONFLICT DO NOTHING -> Agar user bor bo'lsa, xatolik bermaydi
        await db_pool.execute(
            "INSERT INTO users (id, full_name) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING",
            user_id, full_name
        )
        await message.answer(f"Salom, {full_name}! Ma'lumotingiz saqlandi.")
    except Exception as e:
        logging.error(f"DB Error: {e}")
        await message.answer("Tizimda xatolik yuz berdi.")

async def main():
    pool = await create_db_pool()
    # Botga db_pool ni uzatamiz
    await dp.start_polling(bot, db_pool=pool)

if __name__ == "__main__":
    asyncio.run(main())
