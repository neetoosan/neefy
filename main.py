import os
import time
import logging
from functools import wraps
from textwrap import dedent
from urllib.parse import quote
import telebot
from telebot import types
from yt_dlp import YoutubeDL, DownloadError
import threading

# Configuration
TOKEN = os.getenv("7342053757:AAE3ohfeFqQN9zSWxYVoUJaHeOdvpFiX1TQ")
if not TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN environment variable not set")
    exit(1)

MAX_DURATION = 300  # 5 minutes
REQUEST_COOLDOWN = 10  # seconds

YDL_OPTIONS = {
    'format': 'bestaudio[ext=mp3]/bestaudio[ext=m4a]/bestaudio',
    'quiet': True,
    'noplaylist': True,
    'socket_timeout': 10,
    'retries': 3,
    'fragment_retries': 3,
}

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(TOKEN)

# Rate limiter decorator
def rate_limit(cooldown):
    def decorator(func):
        @wraps(func)
        def wrapped(message):
            user_id = message.from_user.id
            user_data = bot.retrieve_data(user_id) or {}
            last_request = user_data.get('last_request', 0)
            
            if time.time() - last_request < cooldown:
                remaining = int(cooldown - (time.time() - last_request))
                bot.send_message(
                    message.chat.id,
                    f"⏳ Please wait {remaining} second(s) between requests"
                )
                return
                
            bot.add_data(user_id, last_request=time.time())
            return func(message)
        return wrapped
    return decorator

# Cleanup old user data
def cleanup_user_data():
    while True:
        try:
            for user_id in bot.get_data():
                data = bot.retrieve_data(user_id) or {}
                if data.get('last_request', 0) < time.time() - 3600:  # 1 hour
                    bot.delete_data(user_id)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        time.sleep(600)  # Run every 10 minutes

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Send welcome message with instructions"""
    help_text = dedent("""
        🎵 Music Bot Commands:
        /play [song name] - Stream audio from YouTube
        /help - Show this help message
    """)
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['play'])
@rate_limit(REQUEST_COOLDOWN)
def play_song(message):
    """Handle play command with rate limiting"""
    try:
        song = ' '.join(message.text.split()[1:])
        if not song:
            bot.reply_to(message, "❌ Usage: /play <song name>")
            return

        # Progress feedback
        status_msg = bot.reply_to(message, "🔍 Searching...")
        
        with YoutubeDL(YDL_OPTIONS) as ydl:
            bot.edit_message_text("⏳ Processing audio...", 
                               message.chat.id, 
                               status_msg.message_id)
            
            info = ydl.extract_info(f"ytsearch1:{song}", download=False)
            if not info.get('entries'):
                bot.edit_message_text("🔍 No results found", 
                                   message.chat.id, 
                                   status_msg.message_id)
                return

            entry = info['entries'][0]
            duration = entry.get('duration', 0)
            if duration > MAX_DURATION:
                bot.edit_message_text("❌ Video too long (max 5 minutes)", 
                                   message.chat.id, 
                                   status_msg.message_id)
                return

            url = entry.get('url')
            title = entry.get('title', 'Unknown Title')
            if not url:
                bot.edit_message_text("❌ No audio URL found", 
                                   message.chat.id, 
                                   status_msg.message_id)
                return

            bot.delete_message(message.chat.id, status_msg.message_id)
            bot.send_audio(
                message.chat.id,
                audio=url,
                title=title,
                performer="YouTube",
                timeout=30
            )
            lyrics_query = quote(title)
            bot.reply_to(
                message,
                f"📝 Lyrics: https://genius.com/search?q={lyrics_query}"
            )

    except DownloadError:
        bot.edit_message_text("❌ Failed to process this video", 
                           message.chat.id, 
                           status_msg.message_id)
        logger.error("DownloadError in play command")
    except telebot.apihelper.ApiException as e:
        bot.edit_message_text("⚠️ Telegram API error", 
                           message.chat.id, 
                           status_msg.message_id)
        logger.error(f"Telegram API error: {e}")
    except Exception as e:
        bot.edit_message_text("⚠️ An error occurred", 
                           message.chat.id, 
                           status_msg.message_id)
        logger.error(f"Error in play command: {str(e)}")

def run_bot():
    """Run the bot with error handling and cleanup"""
    cleanup_thread = threading.Thread(target=cleanup_user_data, daemon=True)
    cleanup_thread.start()
    
    while True:
        try:
            logger.info("Bot starting...")
            bot.infinity_polling(timeout=20, long_polling_timeout=5)
        except Exception as e:
            logger.error(f"Polling crashed: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_bot()
