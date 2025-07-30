from dotenv import load_dotenv
load_dotenv()


import os, logging
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT      = int(os.getenv("PORT", 10000))
WEBHOOK_PATH = f"/{BOT_TOKEN}"          # безопаснее через токен
WEBHOOK_URL  = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()

# ваши хэндлеры
@dp.message()
async def any_msg(msg):
    await msg.answer("Привет от нового aiogram!")

async def on_startup(app: web.Application):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app: web.Application):
    await bot.delete_webhook()

def create_app() -> web.Application:
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_shutdown)
    return app

if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=PORT)
