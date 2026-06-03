import logging
import os
import sys
import time
from pathlib import Path

import requests
import telebot
from dotenv import load_dotenv

from exceptions import NotCorrectResponseError

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

UNDEAD_QUOTES = {
    'approved': 'Жизнь за Нер\'зула',
    'reviewing': 'Работа — не волк',
    'rejected': 'Опять работа'
}

UNDEAD_EMOJIS = {
    'approved': '💀',
    'reviewing': '👁',
    'rejected': '🪦'
}

ASSETS_DIR = Path(__file__).parent / 'assets'
WORKER_AVATARS = {
    'approved': str(ASSETS_DIR / 'acolyte.gif'),
    'reviewing': str(ASSETS_DIR / 'peon.gif'),
    'rejected': str(ASSETS_DIR / 'peasant.gif')
}


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


def check_tokens():
    """Check environment variables availability."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """Send message to Telegram chat."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug(f'Bot sent message: {message}')
    except telebot.apihelper.ApiException as error:
        logger.error(f'Failed to send message to Telegram: {error}')
        raise


def get_api_answer(timestamp):
    """Make request to API and return response as dict."""
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
        if response.status_code != 200:
            raise NotCorrectResponseError(
                f'Endpoint {ENDPOINT} unavailable. '
                f'API response code: {response.status_code}'
            )
        return response.json()
    except requests.RequestException as error:
        raise NotCorrectResponseError(f'Request to API failed: {error}')


def check_response(response):
    """Validate API response structure."""
    if not isinstance(response, dict):
        raise TypeError('API response must be a dict')
    if 'homeworks' not in response:
        raise KeyError('Missing "homeworks" key in API response')
    if not isinstance(response['homeworks'], list):
        raise TypeError('"homeworks" must be a list')
    return response['homeworks']


def send_worker_photo(bot, homework):
    """Send worker avatar with quote caption."""
    status = homework.get('status', 'unknown')
    emoji = UNDEAD_EMOJIS.get(status, '❓')
    quote = UNDEAD_QUOTES.get(status, 'Прикажешь, хозяин')
    image_path = WORKER_AVATARS.get(status)
    if not image_path:
        return
    caption = f'{emoji} "{quote}"'
    try:
        with open(image_path, 'rb') as f:
            bot.send_photo(
                chat_id=TELEGRAM_CHAT_ID,
                photo=f,
                caption=caption
            )
        logger.debug(f'Bot sent worker photo: {caption}')
    except Exception:
        logger.debug('Photo send failed, sending text instead')
        send_message(bot, caption)


def parse_status(homework):
    """Extract homework status and return formatted message."""
    homework_name = homework.get('homework_name', '').removesuffix('.zip')
    if not homework_name:
        raise KeyError('Missing "homework_name" key in homework data')
    status = homework.get('status')
    if not status:
        raise KeyError('Missing "status" key in homework data')
    if status not in HOMEWORK_VERDICTS:
        raise KeyError(f'Unexpected homework status: {status}')
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Main bot logic."""
    if not check_tokens():
        logger.critical('Missing required environment variable')
        sys.exit(1)

    bot = telebot.TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error_message = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                for homework in homeworks:
                    message = parse_status(homework)
                    send_message(bot, message)
                    send_worker_photo(bot, homework)
            else:
                logger.debug('No new homework statuses in API response')
            timestamp = response.get('current_date', int(time.time()))
            last_error_message = None

        except Exception as error:
            message = f'Program failure: {error}'
            logger.error(message)
            if message != last_error_message:
                try:
                    send_message(bot, message)
                except Exception:
                    pass
                last_error_message = message

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
