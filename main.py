import asyncio as aio
import os
from aiohttp import web

from logger import logger
from bot import bot, manga_updater, chapter_creation
from models import DB


async def health_check(request):
    return web.Response(text="OK")


async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", 8000))
    site = web.TCPSite(runner, "0.0.0.0", port)

    await site.start()

    logger.info(f"Health server running on port {port}")


async def async_main():
    # Start health server FIRST
    # so Koyeb can detect port 8000 immediately.
    await start_health_server()

    # Then connect database
    db = DB()
    await db.connect()


if __name__ == '__main__':
    loop = aio.get_event_loop_policy().get_event_loop()

    loop.run_until_complete(async_main())

    loop.create_task(manga_updater())

    for i in range(10):
        loop.create_task(chapter_creation(i + 1))

    bot.run()
