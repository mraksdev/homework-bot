import logging
import os
import sys
import time
from http import HTTPStatus
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

ASSETS = Path(__file__).parent / 'assets'
STATUS_MEDIA = {
    'approved': {
        'emoji': '💀',
        'quote': 'Жизнь за Нер\'зула',
        'avatar': ASSETS / 'acolyte.gif',
    },
    'reviewing': {
        'emoji': '👁',
        'quote': 'Работа — не волк',
        'avatar': ASSETS / 'peon.gif',
    },
    'rejected': {
        'emoji': '🪦',
        'quote': 'Опять работа',
        'avatar': ASSETS / 'peasant.gif',
    },
}


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


def check_tokens():
    """Check environment variables availability."""
    tokens = (
        ('PRACTICUM_TOKEN', PRACTICUM_TOKEN),
        ('TELEGRAM_TOKEN', TELEGRAM_TOKEN),
        ('TELEGRAM_CHAT_ID', TELEGRAM_CHAT_ID),
    )
    missing = [name for name, value in tokens if not value]
    if missing:
        missing_vars = ', '.join(missing)
        logger.critical(
            f'Missing environment variable(s): {missing_vars}'
        )
        return False
    return True


def send_message(bot, message):
    """Send message to Telegram chat."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except telebot.apihelper.ApiException:
        logger.exception(
            'Failed to send message to Telegram'
        )
        raise
    else:
        logger.debug(f'Bot sent message: {message}')


def get_api_answer(timestamp):
    """Make request to API and return response as dict."""
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
    except requests.RequestException as error:
        raise NotCorrectResponseError(
            f'Request to API failed: {error}'
        ) from error
    if response.status_code != HTTPStatus.OK:
        raise NotCorrectResponseError(
            f'Endpoint {ENDPOINT} unavailable. '
            f'API response code: {response.status_code}'
        )
    return response.json()


def check_response(response):
    """Validate API response structure."""
    if not isinstance(response, dict):
        response_type = type(response).__name__
        raise TypeError(
            f'API response must be a dict, got {response_type}'
        )
    homeworks = response.get('homeworks')
    if homeworks is None:
        raise KeyError('Missing "homeworks" key in API response')
    if not isinstance(homeworks, list):
        homeworks_type = type(homeworks).__name__
        raise TypeError(
            f'"homeworks" must be a list, got {homeworks_type}'
        )
    return homeworks


def send_worker_photo(bot, homework):
    """Send worker avatar with quote caption."""
    status = homework.get('status')
    media = STATUS_MEDIA.get(status)
    if not media:
        return
    caption = f'{media["emoji"]} "{media["quote"]}"'
    try:
        with open(media['avatar'], 'rb') as photo:
            bot.send_photo(
                chat_id=TELEGRAM_CHAT_ID,
                photo=photo,
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
        sys.exit(1)

    bot = telebot.TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error_message = None

    while True:
        try:
            api_response = get_api_answer(timestamp)
            homeworks = check_response(api_response)
            if homeworks:
                for homework in homeworks:
                    message = parse_status(homework)
                    send_message(bot, message)
                    send_worker_photo(bot, homework)
            else:
                logger.debug('No new homework statuses in API response')
            timestamp = api_response.get('current_date', timestamp)
            last_error_message = None

        except Exception as error:
            message = f'Program failure: {error}'
            logger.exception(message)
            if message != last_error_message:
                try:
                    send_message(bot, message)
                except Exception:
                    logger.exception('Failed to send error message')
                last_error_message = message

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
