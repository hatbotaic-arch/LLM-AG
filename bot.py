import os
import logging
import datetime
import aiohttp
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
POST_TEXT = os.getenv("POST_TEXT", "Это автоматический пост от вашего бота!")

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")  # теперь должно быть b1gcmthe4ko2mjni5rol
# ============================

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_conversations = {}

async def call_yandex_gpt(messages):
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    model_uri = f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite/latest"
    payload = {
        "modelUri": model_uri,
        "completionOptions": {
            "stream": False,
            "temperature": 0.7,
            "maxTokens": 500
        },
        "messages": messages
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"YandexGPT API error {resp.status}: {error_text}")
                    return f"❌ Ошибка YandexGPT: {resp.status}\n{error_text[:200]}"
                result = await resp.json()
                return result["result"]["alternatives"][0]["message"]["text"]
    except Exception as e:
        logger.error(f"YandexGPT exception: {e}")
        return "❌ Ошибка при обращении к YandexGPT"

async def send_post_to_channel(context):
    try:
        await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=POST_TEXT)
        logger.info(f"Пост отправлен в канал {TELEGRAM_CHAT_ID}")
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки в канал: {e}")
        return False

async def post_command(update, context):
    if update.effective_chat.type != "private":
        await update.message.reply_text("Используй /post в личных сообщениях.")
        return
    ok = await send_post_to_channel(context)
    await update.message.reply_text("✅ Пост отправлен!" if ok else "❌ Ошибка отправки.")

async def set_post_text(update, context):
    if update.effective_chat.type != "private":
        return
    if not context.args:
        await update.message.reply_text("Пример: /setpost Новый текст поста")
        return
    global POST_TEXT
    POST_TEXT = " ".join(context.args)
    await update.message.reply_text(f"✅ Текст поста изменён:\n{POST_TEXT}")

async def test_channel(update, context):
    if update.effective_chat.type != "private":
        return
    try:
        await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="Тестовое сообщение от бота")
        await update.message.reply_text(f"✅ Бот может писать в канал {TELEGRAM_CHAT_ID}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка доступа к каналу: {e}")

async def chat_id(update, context):
    await update.message.reply_text(f"ID этого чата: `{update.effective_chat.id}`", parse_mode='Markdown')

async def handle_private_message(update, context):
    if update.effective_chat.type != "private":
        return
    if update.message.text.startswith('/'):
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    user_id = update.effective_user.id

    if user_id not in user_conversations:
        user_conversations[user_id] = [
            {"role": "system", "text": "Ты дружелюбный помощник. Отвечай кратко и по делу."}
        ]

    user_conversations[user_id].append({"role": "user", "text": user_text})
    if len(user_conversations[user_id]) > 11:
        user_conversations[user_id] = [user_conversations[user_id][0]] + user_conversations[user_id][-10:]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    reply = await call_yandex_gpt(user_conversations[user_id])
    user_conversations[user_id].append({"role": "assistant", "text": reply})
    await update.message.reply_text(reply)

def main():
    if not TELEGRAM_BOT_TOKEN or not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        logger.error("Ошибка: не заданы переменные окружения.")
        return

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("post", post_command))
    app.add_handler(CommandHandler("setpost", set_post_text))
    app.add_handler(CommandHandler("test_channel", test_channel))
    app.add_handler(CommandHandler("chatid", chat_id))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_private_message))

    if app.job_queue:
        app.job_queue.run_daily(send_post_to_channel, time=datetime.time(hour=10, minute=0), days=tuple(range(7)))
        logger.info("Планировщик постов запущен (ежедневно в 10:00)")
    else:
        logger.warning("JobQueue не установлен. Автопостинг не будет работать.")

    app.run_polling()

if __name__ == "__main__":
    main()