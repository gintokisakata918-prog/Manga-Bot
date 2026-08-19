import asyncio as aio
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from bot import bot, manga_updater, chapter_creation
from models import DB


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


def start_health_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


async def async_main():
    db = DB()
    await db.connect()


if __name__ == '__main__':
    # Koyeb health check server
    threading.Thread(target=start_health_server, daemon=True).start()

    loop = aio.get_event_loop_policy().get_event_loop()
    loop.run_until_complete(async_main())

    loop.create_task(manga_updater())

    for i in range(10):
        loop.create_task(chapter_creation(i + 1))

    bot.run()
