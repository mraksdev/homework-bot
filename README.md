# homework-bot

Телеграм-бот, который следит за статусом проверки домашних работ на Яндекс.Практикуме
и присылает уведомление, когда статус меняется. Плюс GIF-аватар в зависимости от вердикта.

```
💀 "Жизнь за Нер'зула"        работа проверена, всё понравилось
👁 "Работа — не волк"         работу взяли на проверку
🪦 "Опять работа"             у ревьюера есть замечания
```

---

## Стек

`requests` 2.32.3, `pyTelegramBotAPI` 4.22.1, `python-dotenv` 1.0.1
`pytest` 8.3.3, `pytest-timeout` 2.3.1, `flake8` 7.1.1, `flake8-docstrings` 1.7.0

Требуется **Python 3.9+** (используется `str.removesuffix`). Разрабатывалось на 3.12.

---

## Установка

```bash
git clone git@github.com:mraksdev/homework-bot.git
cd homework-bot
```

```bash
python3 -m venv venv
source venv/bin/activate        # Windows PowerShell: .\venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

### Переменные окружения

| Переменная | Назначение |
|---|---|
| `PRACTICUM_TOKEN` | OAuth-токен Practicum, уходит в заголовке `Authorization: OAuth <token>` |
| `TELEGRAM_TOKEN` | Токен бота от BotFather |
| `TELEGRAM_CHAT_ID` | ID чата, куда слать уведомления |

Создайте `.env` в корне — `python-dotenv` прочитает его при старте:

```dotenv
PRACTICUM_TOKEN=
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=
```

Файл `.env` находится в `.gitignore`. Если переменная не задана, бот пишет
`CRITICAL`-лог и завершается с кодом 1 — молча работать он не будет.

---

## Запуск

```bash
python homework.py
```

Бот опрашивает API каждые 10 минут (`RETRY_PERIOD = 600`) и работает, пока
не остановишь. Для PaaS есть `Procfile`:

```
worker: python homework.py
```

Процесс объявлен как `worker`, а не `web`: бот не слушает порт, и харнесс не
убьёт его по таймауту.

---

## Как это работает

```
main()  →  get_api_answer()  →  check_response()  →  parse_status()  →  send_message()
              requests.get                валидация       текст        + send_worker_photo()
```

1. **Опрос.** `GET https://practicum.yandex.ru/api/user_api/homework_statuses/`
   с курсором `from_date`. Таймаут запроса — 30 секунд.
2. **Дедупликация.** Каждая работа отслеживается по ключу `(id, status)`.
   Уже отправленное уведомление повторно не придёт, даже если API вернёт
   ту же запись в следующем ответе.
3. **Валидация.** `check_response()` проверяет структуру ответа и поднимает
   `KeyError`/`TypeError` с внятным текстом, если схема нарушена.
4. **Уведомление.** `parse_status()` собирает строку вида
   `Изменился статус проверки работы "API Yamdb". Работа проверена: ...`
   и убирает `.zip` из имени. Затем отправляется GIF-аватар.
5. **Сдвиг курсора.** `from_date` двигается на `current_date + 1`, чтобы не
   опрашивать одни и те же записи.

### Обработка ошибок

| Что | Как |
|---|---|
| Сбой SSL или сети при запросе | `NotCorrectResponseError` → сообщение в чат |
| Ответ не 200 | `NotCorrectResponseError` с кодом и телом ответа |
| Telegram недоступен | 3 попытки с задержкой 10 с, затем `TelegramSendError`; уведомление пропускается, чтобы не зациклиться |
| GIF не отправился | Отправляется только текстовая подпись |
| Повторяющиеся ошибки | `notify_error()` не шлёт одинаковый текст повторно |
| Критичное | `check_tokens()` → `CRITICAL`-лог и выход |

Логи идут в `stdout` на уровне `DEBUG` — на PaaS попадут в логи процесса.

---

## Тесты

```bash
pytest
```

**25 тестов** — 21 тест-кейс, два параметризованы по три значения.

Полностью изолированы от сети: `requests.get`, `telebot.TeleBot` и `time.sleep`
подменяются через `monkeypatch`, а в `tests/check_utils.py` есть `MockResponseGET`
и `MockTelegramBot`. Переменные окружения для тестов не нужны — `conftest.py`
подставляет заглушки.

| Область | Что покрыто |
|---|---|
| Константы | Наличие и значения всех констант, `RETRY_PERIOD == 600` |
| Инициализация | `TeleBot` не создаётся на уровне модуля, только в `main()` |
| Запрос | URL, заголовок `Authorization` с `OAuth`, параметр `from_date` |
| Ошибки API | Коды 500, 401, 204; `RequestException` не пробрасывается наружу |
| Разбор статуса | Все 3 вердикта, неизвестный статус, отсутствие `homework_name` |
| Валидация | Ответ без `homeworks`, не-словарь, `homeworks` не список |
| Отправка | Передача `chat_id` и `text`, логирование, `ApiException` не роняет бота |
| `main()` | Запрос к API, вызов `check_response`, уведомление при новом статусе, пустой ответ, обязательный `time.sleep(600)` |
| Линтинг | Наличие `logging` в исходнике, докстринги у всех функций |

Тесты защищены таймаутами: глобальный лимит 2 секунды на тест
(`pytest.ini: timeout = 2`), плюс `with_timeout` на `main()`, чтобы бесконечный
цикл опроса не подвешивал прогон.

### Линтинг

```bash
flake8 homework.py
```

Настройки в `setup.cfg`: линтится только `homework.py`, `max-complexity = 10`,
`flake8-docstrings` с игнорированием `D100`, `D205`, `D401`.

---

## Структура

```
homework-bot/
├── homework.py          # весь бот: константы, 8 функций, main()
├── exceptions.py        # NotCorrectResponseError, TelegramSendError
├── assets/              # 3 GIF-аватара по статусам
├── tests/
│   ├── conftest.py
│   ├── test_bot.py      # 21 тест-кейс
│   ├── check_utils.py   # моки, BreakInfiniteLoop, with_timeout
│   └── fixtures/fixture_data.py
├── Procfile
├── pytest.ini
├── setup.cfg            # секция [flake8]
├── requirements.txt
└── .env                 # не в репозитории
```

---

## Лицензия

MIT — см. [LICENSE](LICENSE).
