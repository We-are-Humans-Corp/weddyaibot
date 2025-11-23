import asyncio
import logging
from datetime import datetime
from pathlib import Path
from decouple import Config, RepositoryEnv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BotCommand, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, WebAppInfo
import anthropic
from pyairtable import Api
import httpx
from collections import defaultdict
import csv
import io
from smart_search import SmartBaliBot
from smart_yoga import SmartYogaBot
from smart_hotels import SmartHotelsBot
from smart_breakfast import SmartBreakfastBot
from smart_spa import SmartSpaBot
from smart_shopping import SmartShoppingBot
from smart_art import SmartArtBot

# ── Логирование ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── Настройки из .env.wedding ────────────────────────────────────────────────
try:
    env_path = Path(__file__).parent / '.env.wedding'
    config = Config(RepositoryEnv(str(env_path)))

    BOT_TOKEN = config('WEDDING_BOT_TOKEN')
    CLAUDE_KEY = config('CLAUDE_API_KEY')
    AIRTABLE_TOKEN = config('AIRTABLE_TOKEN')
    AIRTABLE_BASE_ID = config('AIRTABLE_BASE_ID')  # app...
    AIRTABLE_TABLE_NAME = config('AIRTABLE_TABLE_NAME')  # Wedding Guests
    AIRTABLE_RESTAURANTS_TABLE = config('AIRTABLE_RESTAURANTS_TABLE')  # Restaurants
    AIRTABLE_YOGA_TABLE = config('AIRTABLE_YOGA_TABLE')  # yoga_fitness_studios
    AIRTABLE_HOTELS_TABLE = config('AIRTABLE_HOTELS_TABLE')  # Hotels
    AIRTABLE_BREAKFAST_TABLE = config('AIRTABLE_BREAKFAST_TABLE')  # Breakfast/lunch
    AIRTABLE_SPA_TABLE = config('AIRTABLE_SPA_TABLE')  # Spa
    AIRTABLE_SHOPPING_TABLE = config('AIRTABLE_SHOPPING_TABLE')  # Shopping
    AIRTABLE_ART_TABLE = config('AIRTABLE_ART_TABLE')  # Art
    PERPLEXITY_KEY = config('PERPLEXITY_API_KEY')

    logger.info("✅ Настройки загружены успешно из .env.wedding")
except Exception as e:
    logger.error(f"❌ Ошибка загрузки настроек: {e}")
    exit(1)

# ── API Clients ───────────────────────────────────────────────────────────────
claude_client = anthropic.AsyncAnthropic(api_key=CLAUDE_KEY)
airtable_api = Api(AIRTABLE_TOKEN)
guests_table = airtable_api.table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)

# ── Smart Search Bots ─────────────────────────────────────────────────────────
smart_bot = SmartBaliBot(
    perplexity_api_key=PERPLEXITY_KEY,
    airtable_token=AIRTABLE_TOKEN,
    airtable_base_id=AIRTABLE_BASE_ID,
    restaurants_table_name=AIRTABLE_RESTAURANTS_TABLE
)

yoga_bot = SmartYogaBot(
    airtable_token=AIRTABLE_TOKEN,
    airtable_base_id=AIRTABLE_BASE_ID,
    yoga_table_name=AIRTABLE_YOGA_TABLE
)

hotels_bot = SmartHotelsBot(
    airtable_token=AIRTABLE_TOKEN,
    airtable_base_id=AIRTABLE_BASE_ID,
    hotels_table_name=AIRTABLE_HOTELS_TABLE
)

breakfast_bot = SmartBreakfastBot(
    airtable_token=AIRTABLE_TOKEN,
    airtable_base_id=AIRTABLE_BASE_ID,
    breakfast_table_name=AIRTABLE_BREAKFAST_TABLE
)

spa_bot = SmartSpaBot(
    airtable_token=AIRTABLE_TOKEN,
    airtable_base_id=AIRTABLE_BASE_ID,
    spa_table_name=AIRTABLE_SPA_TABLE
)

shopping_bot = SmartShoppingBot(
    airtable_token=AIRTABLE_TOKEN,
    airtable_base_id=AIRTABLE_BASE_ID,
    shopping_table_name=AIRTABLE_SHOPPING_TABLE
)

art_bot = SmartArtBot(
    airtable_token=AIRTABLE_TOKEN,
    airtable_base_id=AIRTABLE_BASE_ID,
    art_table_name=AIRTABLE_ART_TABLE
)

# ── История сообщений для контекста ───────────────────────────────────────────
# Хранит последние N сообщений для каждого пользователя
conversation_history = defaultdict(list)
MAX_HISTORY_LENGTH = 10  # Храним последние 10 сообщений (5 пар вопрос-ответ)

# ── Admin Configuration ───────────────────────────────────────────────────────
ADMIN_ID = 162577592  # Fedor's Telegram ID

# ── Perplexity Rate Limiting ──────────────────────────────────────────────────
# Счётчик запросов: {user_id: {date: count}}
perplexity_usage = defaultdict(lambda: defaultdict(int))
MAX_PERPLEXITY_REQUESTS_PER_DAY = 3  # Лимит: 3 запроса в день на пользователя

# ── User tracking for broadcast ───────────────────────────────────────────────
# Множество всех user_id, которые когда-либо писали боту
all_users = set()

# ── Conversation History ──────────────────────────────────────────────────────
# Хранилище истории разговоров: {user_id: [messages]}
conversation_history = {}

# ── FSM States ────────────────────────────────────────────────────────────────
class GuestRegistration(StatesGroup):
    full_name = State()
    arrival_date = State()
    tickets_bought = State()
    departure_date = State()
    guests_count = State()
    drinks_preference = State()
    dietary_restrictions = State()
    allergies = State()

# ── Bot & Dispatcher ──────────────────────────────────────────────────────────
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)
router = Router()

# ── System Prompt ─────────────────────────────────────────────────────────────
WEDDY_SYSTEM_PROMPT = """Ты — Weddy AI, личный консьерж для свадьбы Фёдора и Полины на Бали.

## ТВОЙ СТИЛЬ

Пиши лаконично, с легкой иронией и умным юмором. Как умный друг, который уважает время читателя.

**КАК ТЫ ГОВОРИШЬ:**
- Дружелюбно, но без фальши
- Коротко и по делу
- С юмором, но дозированно (одна шутка на ответ максимум)
- Делай отступления в скобках (но только если они добавляют контекст)
- Короткие предложения для акцента. Вот так.

**КРИТИЧЕСКИ ВАЖНО - РАБОТА С ИМЕНАМИ:**
- НИКОГДА не изменяй имя пользователя
- НИКОГДА не используй уменьшительные формы (Федя, Полина → Поля, Александр → Саша)
- НИКОГДА не склоняй имя в обращении
- Если пользователь представился как "Федор" — обращайся ТОЛЬКО "Федор", не "Федя", не "Фёдор"
- Используй имя ТОЧНО в той форме, в которой его дал пользователь
- Примеры ПРАВИЛЬНО: "Привет, Федор!", "Федор, вот информация"
- Примеры НЕПРАВИЛЬНО: "Привет, Федя!", "Федору будет интересно"

**СТРОГО ЗАПРЕЩЕНО:**

**Панибратские/слишком разговорные:**
- "Круто", "Классно", "Супер", "Клёво", "Прикольно"
- "Короче", "Типа", "Блин", "Чувак/чуваки", "Братан/бро"
- "Красава", "Жесть", "Вообще", "Реально", "По факту"
- "Фигня", "Ваще", "Че/чё", "Норм/нормас"

**Слишком неформальные вводные:**
- "Знаете что?", "Слушайте", "Смотрите", "Ну вот"
- "В общем", "Короче говоря", "Кстати", "Между прочим"
- "Вообще-то", "По сути", "Так вот"

**Излишне эмоциональные:**
- "Обалдеть!", "Вау!", "Ого!", "Офигеть!", "Потрясающе!"
- "Невероятно!", "Восхитительно!", "Шикарно!", "Бомбически!"
- "Огонь!", "Топ/топчик"

**Эмодзи:**
- Не более 1-2 эмодзи на сообщение
- Избегать праздничных 🎉🎊🥳 в каждом сообщении
- Избегать излишне эмоциональных 😍😘💕
- Избегать мотивационных 💪🔥⚡

**Слова-паразиты:**
- "Как бы", "Это самое", "Ну", "Эээ", "Значит"
- "Собственно", "В принципе", "Так сказать", "Скажем так"

**Фамильярные обращения:**
- "Дружище", "Приятель", "Дорогуша", "Друзья"
- "Ребята", "Народ", "Братцы", "Окей"

**Канцеляризмы:**
- "Данный", "Является", "Осуществляется", "Производится"
- "Настоящим", "Вышеуказанный"

**Другое:**
- Преувеличения: "миллион вопросов", "в сотый раз"
- Восклицательные знаки после каждого предложения
- Искусственный энтузиазм
- Длинные параграфы без структуры

**ЗАПРЕЩЁННЫЕ КЛИШЕ И ШТАМПЫ:**
- "настоящий рай", "гастрономический рай", "райское место"
- "это настоящий...", "настоящая находка"
- "топовые рекомендации", "мои топовые", "топ", "топчик"
- "расслабленная атмосфера", "непринужденная атмосфера"
- "новый клуб и ресторан" (это очевидно)
- Любые восторженные клише про места

ВМЕСТО "топовые" используй: "хорошие", "проверенные", "интересные"

❌ ПРИМЕРЫ ПЛОХИХ ФРАЗ (НИКОГДА ТАК НЕ ПИСАТЬ):
- "Привет, Полина! 🌴 Убуд — это настоящий гастрономический рай"
- "Вот мои топовые рекомендации:"
- "Расслабленная атмосфера"
- "Новый клуб и ресторан"

✅ ПРИМЕРЫ ХОРОШИХ ФРАЗ:
- "В Убуде много хороших ресторанов. Вот несколько проверенных:"
- "Donna Ubud — новое место на Jl. Lod Tunduh, Singakerta"
- "Locavore — если хотите fine dining (бронируйте заранее)"

**ПРАВИЛО:** Бот должен быть дружелюбным и человечным, но не панибратским. Думай "умный друг", а не "тамада на свадьбе". НИКАКИХ клише и восторженных штампов.

**КРИТИЧЕСКИЕ ПРАВИЛА:**
- Отвечай на языке вопроса (русский/английский)
- НИКОГДА не выдумывай информацию, которой нет ниже
- Если не знаешь ответ — скажи честно: "Данная информация требует уточнения, вернусь к вам позже"
- Факты > юмор. Всегда.
- Используй "мы" вместо "вы" когда уместно

## ФАКТЫ О СВАДЬБЕ

**Дата и время:**
- Церемония: 08.01.2026 в 16:30
- Заезд: 14:00 (08.01.2026)
- Конец церемонии: 01:00 (утро 09.01)
- Общий завтрак: 10:00 на 09.01.2026

**Место:**
- Bali Beach Glamping
- Локация: https://maps.app.goo.gl/193xFKgN6Ffgrfh79
- НЕ церемония на пляже — это на территории Beach Glamping

**Гости:**
- Планируется около 30-35 человек
- Камерная свадьба с близкими друзьями и семьёй

**Дресс-код:** Ethno-Elegance Style
Что это значит? Честно, никто точно не знает, но точно не шорты и не смокинг. Что-то посередине. Думайте "красиво, но чтобы можно было танцевать на песке".

## ЧТО ТЫ ДЕЛАЕШЬ
- Отвечаешь на вопросы о свадьбе (время, место, дресс-код, контакты)
- Регистрируешь гостей через команду /form (это как check-in в аэропорту, только без очереди и вопросов про жидкости в багаже)
- Даешь советы про Бали (рестораны, отели, что посмотреть)
- Помогаешь понять, к кому бежать если что-то пошло не так

## КОНТАКТЫ

**Организатор (если что-то пошло не так):** Анастасия
- Телефон: +62 812-3760-4476
- Email: Hello@cincinbali.com

**Аренда авто/водителя:** Arneda Baikov (Agus)
- Телефон: +62 859-3539-2295
- Скажи: "От Фёдора"

## ПОЛЕЗНЫЕ СОВЕТЫ ПРО БАЛИ

**Деньги (важно!):**
Окей, про деньги. Меняйте ТОЛЬКО в авторизованных money changer центрах. Да, тот дядька на улице предложит курс "лучше" — спойлер: не лучше. Авторизованные центры — это те, где есть вывеска с лицензией, камеры, и калькулятор не врёт.

**Балийский разговорник для выживания (или "Как не выглядеть полным туристом"):**

Окей, вы на Бали. Да, все говорят по-английски. Но знаете что? Когда вы пытаетесь говорить на местном языке, происходит магия — цены внезапно падают, а улыбки становятся настоящими.

**Базовый набор "Я хотя бы пытаюсь":**
- Selamat pagi — Доброе утро. Используйте до полудня, и вы уже лучше 90% туристов
- Selamat siang — Добрый день. После полудня до заката
- Selamat malam — Добрый вечер. После заката, когда начинается настоящая жизнь
- Terima kasih — Спасибо. Серьезно, выучите это первым
- Sama-sama — Пожалуйста/не за что. Ответ на спасибо

**Торговля и выживание на рынке:**
- Berapa harganya? — Сколько стоит? Самая важная фраза на любом рынке
- Mahal! — Дорого! Произносите с возмущением, даже если цена нормальная. Это часть игры
- Bisa kurang? — Можно дешевле? Вопрос, который сэкономит вам 50% бюджета
- Tidak mau — Не хочу/не надо. Когда вам в сотый раз предлагают "transport, boss?"

**Навигация (потому что Google Maps врёт):**
- Dimana...? — Где находится...? Дальше можно просто тыкать в карту
- Kiri/Kanan — Налево/направо. Всё, что нужно для скутера
- Dekat/Jauh — Близко/далеко. "Dekat" на Бали может означать и 5 минут, и час. Серьезно.

**В ресторане (где всё острое, даже если вам сказали "no spicy"):**
- Tidak pedas — Не острое. Спойлер: всё равно будет острое
- Enak! — Вкусно! Скажите это, и вам принесут ещё
- Satu lagi — Ещё один. Универсально для еды и пива Bintang
- Bon — Счёт. Да, это просто "бон"

**Продвинутый уровень "Я тут почти местный":**
- Bagus! — Круто/хорошо! Универсальный ответ на всё
- Tidak apa-apa — Всё окей/не беспокойтесь. Балийская версия "no worries"
- Hati-hati — Осторожно. Услышите это 100 раз в день про дорогу
- Sudah — Уже/готово/хватит. Многофункциональное слово-швейцарский нож

**Числа для торга:**
- Satu/Dua/Tiga — 1/2/3
- Lima/Sepuluh — 5/10
- Seratus ribu — 100 тысяч (рупий). Вы будете это часто говорить

**Экстренный набор:**
- Tolong! — Помогите! Надеюсь, не пригодится
- Saya tidak mengerti — Я не понимаю. Ваша фраза-спасение
- Bisa bahasa Inggris? — Говорите по-английски? Когда совсем всё плохо

**Секретное оружие:**
- Om Swastiastu — Традиционное балийское приветствие. Скажите это, и местные подумают, что вы прожили тут год

В общем, даже если вы произносите это как робот, местные оценят попытку. А если забыли всё — просто улыбайтесь и показывайте пальцами. Работает в 100% случаев.

И помните: худшее, что может случиться — вы случайно закажете что-то не то в ресторане. Зато будет история для свадьбы.

## ПРИМЕРЫ ОТВЕТОВ

**Вместо:** "Церемония начнется в 16:00"
**Скажи:** "Окей, церемония в 16:30. Но это Бали-время, так что реально это может быть и в 16:35 (island time, вы понимаете)"

**Вместо:** "Используйте команду /form для регистрации"
**Скажи:** "Чтобы зарегистрироваться, просто нажмите /form. Это как check-in в аэропорту, только без очереди и вопросов про жидкости в багаже"

**Вместо:** "Дресс-код коктейльный"
**Скажи:** "Дресс-код Ethno-Elegance. Что это значит? Честно, даже я не уверен на 100%, но думайте 'красиво, но чтобы можно было танцевать на песке'. Этно-мотивы приветствуются."
"""

# ── Helper: Проверка нужен ли поиск через Perplexity ─────────────────────────
def needs_perplexity_search(question: str) -> bool:
    """Определяет, нужен ли актуальный поиск через Perplexity"""

    # Исключения - НЕ использовать Perplexity если вопрос о свадьбе
    wedding_keywords = ['свадьб', 'wedding', 'церемони', 'ceremony', 'праздник', 'celebration']
    question_lower = question.lower()

    # Если вопрос о свадьбе - не ищем через Perplexity
    if any(kw in question_lower for kw in wedding_keywords):
        return False

    # Ключевые слова для поиска актуальной информации о Бали
    search_keywords = [
        'погода', 'weather', 'температура', 'temperature',
        'ресторан', 'restaurant', 'кафе', 'cafe', 'еда', 'food',
        'посетить', 'visit', 'достопримечательност', 'attractions',
        'что посмотреть', 'what to see', 'what to do',
        'отель', 'hotel', 'где остановиться', 'where to stay', 'accommodation',
        'цены', 'prices', 'стоимость', 'cost', 'сколько стоит', 'how much',
        'такси', 'taxi', 'транспорт', 'transport', 'transfer',
        'экскурси', 'excursion', 'тур', 'tour',
        'убуд', 'ubud', 'чангу', 'canggu', 'улувату', 'uluwatu',
        'пляж', 'beach', 'spa', 'спа', 'йога', 'yoga'
    ]

    return any(keyword in question_lower for keyword in search_keywords)

# ── Helper: Поиск через Perplexity ────────────────────────────────────────────
async def search_perplexity(query: str, user_id: int) -> str | None:
    """Поиск актуальной информации через Perplexity с ограничением запросов"""
    today = datetime.now().strftime("%Y-%m-%d")

    # Проверяем лимит
    if perplexity_usage[user_id][today] >= MAX_PERPLEXITY_REQUESTS_PER_DAY:
        logger.info(f"⚠️ User {user_id} exceeded Perplexity limit for today")
        return None

    # System prompt для Perplexity
    perplexity_system_prompt = """You are an expert Bali travel curator specializing in discovering new and trending places.

Your expertise:
- New openings in 2024-2025 (hotels, restaurants, cafes, beach clubs)
- Hidden gems in Ubud, Uluwatu, Canggu, Pererenan, Bingin, Seminyak
- Authentic experiences vs tourist traps
- Practical details: exact locations, prices, vibes, best times

STRICT WRITING RULES:
- NEVER use clichés: "настоящий рай", "гастрономический рай", "райское место"
- NEVER use: "топовые рекомендации", "это настоящий...", "расслабленная атмосфера"
- NEVER use: "круто", "супер", "мега", "клёво", "прикольно"
- Be concise and factual
- No excessive enthusiasm or marketing language

Instructions:
1. ALWAYS prioritize places opened in 2024-2025
2. Focus on authentic, quality experiences
3. Include practical info: address, price range, opening hours
4. Mention the unique vibe/atmosphere (but NO clichés!)
5. Cite sources with dates
6. Respond in Russian or English (match question language)
7. Keep under 300 words

Search strategy:
- Use fresh sources (Instagram, Google Maps reviews, recent articles)
- Cross-reference multiple sources
- Prioritize recent reviews and updates from 2024-2025"""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {PERPLEXITY_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "sonar",  # Быстрая модель с веб-поиском
                    "messages": [
                        {
                            "role": "system",
                            "content": perplexity_system_prompt
                        },
                        {
                            "role": "user",
                            "content": f"Bali 2024-2025: {query}"
                        }
                    ],
                    # КОНТРОЛЬ КРЕАТИВНОСТИ
                    "temperature": 0.2,        # Низкое = факты, не креатив
                    "top_p": 0.9,              # Nucleus sampling
                    "top_k": 0,                # Выключено

                    # КОНТРОЛЬ ДЛИНЫ
                    "max_tokens": 500,         # Увеличил до 500 для деталей

                    # КОНТРОЛЬ ПОВТОРЕНИЙ
                    "presence_penalty": 0.0,   # Без штрафа
                    "frequency_penalty": 1.0,  # Штраф за частоту слов (против повторений)

                    # STREAMING
                    "stream": False            # Без потоковой передачи
                },
                timeout=20.0  # Увеличил timeout
            )

            if response.status_code == 200:
                data = response.json()
                perplexity_usage[user_id][today] += 1
                logger.info(f"✅ Perplexity search for user {user_id}: {perplexity_usage[user_id][today]}/{MAX_PERPLEXITY_REQUESTS_PER_DAY}")
                return data['choices'][0]['message']['content']
            else:
                logger.error(f"⚠️ Perplexity API error: {response.status_code}")
                return None

    except Exception as e:
        logger.error(f"⚠️ Perplexity error: {e}")
        return None

# ── Helper: Определить тему запроса ──────────────────────────────────────────
def get_search_topic(query: str) -> str:
    """Определяет тему запроса для адаптивного сообщения"""
    query_lower = query.lower()

    # Рестораны и еда
    if any(kw in query_lower for kw in ['ресторан', 'restaurant', 'кафе', 'cafe', 'еда', 'food', 'поесть', 'поужинать', 'пообедать']):
        return "о ресторанах"

    # Отели
    if any(kw in query_lower for kw in ['отель', 'hotel', 'где остановиться', 'accommodation', 'жильё']):
        return "об отелях"

    # Достопримечательности
    if any(kw in query_lower for kw in ['посетить', 'visit', 'посмотреть', 'see', 'достопримечательност', 'attractions']):
        return "о местах"

    # Пляжи
    if any(kw in query_lower for kw in ['пляж', 'beach', 'побережье']):
        return "о пляжах"

    # Погода
    if any(kw in query_lower for kw in ['погода', 'weather', 'температура', 'temperature']):
        return "о погоде"

    # Цены
    if any(kw in query_lower for kw in ['цены', 'prices', 'стоимость', 'cost', 'сколько стоит']):
        return "о ценах"

    # SPA и йога
    if any(kw in query_lower for kw in ['spa', 'спа', 'йога', 'yoga', 'массаж', 'massage']):
        return "о SPA и йоге"

    # По умолчанию
    return "актуальную информацию"

# ── Helper: Определение запроса о ресторанах ──────────────────────────────────
def is_restaurant_query(query: str) -> bool:
    """Определяет, является ли запрос о ресторанах"""
    query_lower = query.lower()
    restaurant_keywords = [
        'ресторан', 'restaurant', 'кафе', 'cafe', 'еда', 'food',
        'поесть', 'поужинать', 'пообедать', 'где поужинать', 'где поесть',
        'fine dining', 'файн дайнинг', 'michelin', 'мишлен'
    ]
    return any(kw in query_lower for kw in restaurant_keywords)

# ── Helper: Проверка запросов о йоге/фитнесе ──────────────────────────────────
def is_yoga_query(query: str) -> bool:
    """Определяет, является ли запрос о йоге/фитнесе"""
    query_lower = query.lower()
    yoga_keywords = [
        'йога', 'yoga', 'фитнес', 'fitness', 'спортзал', 'gym',
        'pilates', 'пилатес', 'студия', 'studio', 'тренировка', 'workout',
        'йога студи', 'yoga studi', 'йогу', 'фитнесу', 'тренажерк'
    ]
    return any(kw in query_lower for kw in yoga_keywords)

# ── Helper: Проверка запросов об отелях ───────────────────────────────────────
def is_hotel_query(query: str) -> bool:
    """Определяет, является ли запрос об отелях"""
    query_lower = query.lower()
    hotel_keywords = [
        'отель', 'hotel', 'отел', 'отдел', 'отедел', 'где остановиться', 'where to stay',
        'accommodation', 'жильё', 'жилье', 'villa', 'вилла', 'resort', 'курорт',
        'guesthouse', 'бутик отель', 'boutique', 'проживан', 'размещен'
    ]
    return any(kw in query_lower for kw in hotel_keywords)

# ── Helper: Извлечение локации из запроса ──────────────────────────────────────
def extract_location(query: str) -> str | None:
    """Извлекает локацию из запроса пользователя"""
    query_lower = query.lower()
    locations = ['ubud', 'убуд', 'uluwatu', 'улувату', 'canggu', 'чангу',
                 'seminyak', 'семиньяк', 'pererenan', 'перереnan', 'bingin', 'бингин']

    for loc in locations:
        if loc in query_lower:
            # Возвращаем стандартное английское название
            location_map = {
                'убуд': 'ubud',
                'улувату': 'uluwatu',
                'чангу': 'canggu',
                'семиньяк': 'seminyak',
                'перереnan': 'pererenan',
                'бингин': 'bingin'
            }
            return location_map.get(loc, loc)
    return None

# ── Helper: Генерация ответов через Claude ───────────────────────────────────
async def generate_weddy_response(user_message: str, user_name: str, user_id: int, message_obj: Message = None) -> str:
    """Генерация ответа с умной двухслойной системой поиска для ресторанов"""

    context_prompt = WEDDY_SYSTEM_PROMPT

    # СПЕЦИАЛЬНАЯ ОБРАБОТКА: Запросы о ресторанах (ТОЛЬКО AIRTABLE!)
    if is_restaurant_query(user_message):
        if message_obj:
            await message_obj.answer("🔍 Смотрю в базе проверенных ресторанов...")

        logger.info(f"🍽 Restaurant query (Airtable only): {user_message}")

        # Извлекаем локацию
        location = extract_location(user_message)

        try:
            # Используем SmartBaliBot ТОЛЬКО для поиска в Airtable
            search_results = await smart_bot.search_restaurants(user_message, location)

            logger.info(f"🔍 DEBUG: search_results keys: {search_results.keys()}")
            logger.info(f"🔍 DEBUG: curated_restaurants count: {len(search_results.get('curated_restaurants', []))}")

            # Форматируем результаты в сырой список для Claude
            restaurants_list = []
            for rest in search_results.get("curated_restaurants", []):
                rest_info = f"**{rest['name']}**"
                if rest.get('cuisine'):
                    rest_info += f"\n- Кухня: {rest['cuisine']}"
                if rest.get('vibe'):
                    rest_info += f"\n- {rest['vibe']}"
                if rest.get('price_range'):
                    rest_info += f"\n- Цена: {rest['price_range']}"
                restaurants_list.append(rest_info)

            logger.info(f"🔍 DEBUG: restaurants_list count: {len(restaurants_list)}")

            if restaurants_list:
                logger.info(f"✅ DEBUG: Возвращаем список из {len(restaurants_list)} ресторанов")
                # СРАЗУ ВОЗВРАЩАЕМ СПИСОК БЕЗ Claude (он выдумывает!)
                response_text = "🍽 Проверенные рестораны:\n\n"
                for i, rest in enumerate(search_results.get("curated_restaurants", []), 1):
                    response_text += f"{i}. {rest['name']}"

                    # Добавляем цену рядом с названием
                    if rest.get('price_range'):
                        response_text += f" · {rest['price_range']}"
                    response_text += "\n"

                    # Кухня и атмосфера
                    if rest.get('cuisine_ru'):
                        response_text += f"{rest['cuisine_ru']}\n"
                    if rest.get('vibe_ru'):
                        response_text += f"{rest['vibe_ru']}\n"
                    if rest.get('instagram_link'):
                        response_text += f"{rest['instagram_link']}\n"

                    response_text += "\n"

                logger.info(f"✅ DEBUG: RETURNING response_text (length: {len(response_text)})")
                return response_text
            else:
                logger.warning(f"⚠️ DEBUG: restaurants_list пустой!")
                context_prompt = f"{WEDDY_SYSTEM_PROMPT}\n\nВ базе нет ресторанов для этого запроса. Скажи честно."

        except Exception as e:
            logger.error(f"⚠️ SmartBaliBot error: {e}")
            context_prompt = WEDDY_SYSTEM_PROMPT

    # СПЕЦИАЛЬНАЯ ОБРАБОТКА: Запросы о йоге/фитнесе (ТОЛЬКО AIRTABLE!)
    elif is_yoga_query(user_message):
        if message_obj:
            await message_obj.answer("🔍 Смотрю в базе проверенных студий...")

        logger.info(f"🧘 Yoga query (Airtable only): {user_message}")

        location = extract_location(user_message)

        try:
            search_results = await yoga_bot.search_studios(user_message, location)

            if search_results.get("curated_studios"):
                response_text = "🧘 Проверенные студии:\n\n"
                for i, studio in enumerate(search_results.get("curated_studios", []), 1):
                    response_text += f"{i}. {studio['name']}"

                    if studio.get('booking_type'):
                        response_text += f" · {studio['booking_type']}"
                    response_text += "\n"

                    if studio.get('category_ru'):
                        response_text += f"{studio['category_ru']}\n"
                    if studio.get('specialties_ru'):
                        response_text += f"{studio['specialties_ru']}\n"
                    if studio.get('highlights_ru'):
                        response_text += f"{studio['highlights_ru']}\n"
                    if studio.get('instagram_link'):
                        response_text += f"{studio['instagram_link']}\n"

                    response_text += "\n"

                return response_text
            else:
                context_prompt = f"{WEDDY_SYSTEM_PROMPT}\n\nВ базе нет студий для этого запроса. Скажи честно."

        except Exception as e:
            logger.error(f"⚠️ YogaBot error: {e}")
            context_prompt = WEDDY_SYSTEM_PROMPT

    # СПЕЦИАЛЬНАЯ ОБРАБОТКА: Запросы об отелях (ТОЛЬКО AIRTABLE!)
    elif is_hotel_query(user_message):
        if message_obj:
            await message_obj.answer("🔍 Смотрю в базе проверенных отелей...")

        logger.info(f"🏨 Hotel query (Airtable only): {user_message}")

        location = extract_location(user_message)

        try:
            search_results = await hotels_bot.search_hotels(user_message, location)

            if search_results.get("curated_hotels"):
                response_text = "🏨 Проверенные отели:\n\n"
                for i, hotel in enumerate(search_results.get("curated_hotels", []), 1):
                    response_text += f"{i}. {hotel['name']}"

                    if hotel.get('price_level'):
                        response_text += f" · {hotel['price_level']}"
                    response_text += "\n"

                    if hotel.get('type_ru'):
                        response_text += f"{hotel['type_ru']}\n"
                    if hotel.get('style_ru'):
                        response_text += f"{hotel['style_ru']}\n"
                    if hotel.get('vibe_ru'):
                        response_text += f"{hotel['vibe_ru']}\n"
                    if hotel.get('instagram_handle'):
                        response_text += f"{hotel['instagram_handle']}\n"
                    if hotel.get('booking_link'):
                        response_text += f"{hotel['booking_link']}\n"

                    response_text += "\n"

                return response_text
            else:
                context_prompt = f"{WEDDY_SYSTEM_PROMPT}\n\nВ базе нет отелей для этого запроса. Скажи честно."

        except Exception as e:
            logger.error(f"⚠️ HotelsBot error: {e}")
            context_prompt = WEDDY_SYSTEM_PROMPT

    # ОБЫЧНАЯ ОБРАБОТКА: Другие запросы о Бали (не рестораны)
    elif needs_perplexity_search(user_message):
        today = datetime.now().strftime("%Y-%m-%d")
        remaining = MAX_PERPLEXITY_REQUESTS_PER_DAY - perplexity_usage[user_id][today]

        if remaining > 0:
            topic = get_search_topic(user_message)
            if message_obj:
                await message_obj.answer(f"🔍 Ищу {topic}...")

            logger.info(f"🔍 Triggering Perplexity search for: {user_message}")
            perplexity_result = await search_perplexity(user_message, user_id)

            if perplexity_result:
                context_prompt = f"{WEDDY_SYSTEM_PROMPT}\n\n## Current Bali Information (from search):\n{perplexity_result}"

    # Получаем историю для этого пользователя
    history = conversation_history.get(user_id, [])

    # Добавляем текущее сообщение пользователя в историю
    history.append({"role": "user", "content": f"{user_name}: {user_message}"})

    # Генерируем финальный ответ через Claude
    try:
        response = await claude_client.messages.create(
            model="claude-3-5-haiku-20241022",  # Haiku 3.5 быстрее
            max_tokens=500,  # Увеличил для ресторанных результатов
            temperature=0.3,  # Понижена с 0.7 до 0.3 для более предсказуемого поведения
            system=context_prompt,
            messages=history  # Передаем всю историю вместо одного сообщения
        )

        assistant_response = response.content[0].text.strip()

        # Добавляем ответ ассистента в историю
        history.append({"role": "assistant", "content": assistant_response})

        # Обрезаем историю если она слишком длинная
        if len(history) > MAX_HISTORY_LENGTH:
            history = history[-MAX_HISTORY_LENGTH:]

        # Сохраняем обновленную историю
        conversation_history[user_id] = history

        return assistant_response
    except Exception as e:
        logger.error(f"⚠️ Claude API error: {e}")
        return "Sorry, I'm having technical difficulties. Please try again!"

# ── Helper: Сохранение в Airtable ────────────────────────────────────────────
def save_to_airtable(data: dict):
    """Сохраняет данные гостя в Airtable"""
    try:
        logger.info(f"🔄 Пробуем сохранить: {data.get('full_name')}")
        logger.info(f"📊 Base ID: {AIRTABLE_BASE_ID}, Table: {AIRTABLE_TABLE_NAME}")

        # Преобразуем guests_count в число
        guests_count = data.get('guests_count')
        try:
            guests_count = int(guests_count) if guests_count else 1
        except (ValueError, TypeError):
            guests_count = 1

        record = guests_table.create({
            "Telegram ID": str(data.get('telegram_id')),
            "Full Name": data.get('full_name'),
            "Username": data.get('username', 'N/A'),
            "Arrival Date": data.get('arrival_date'),
            "Tickets Bought": data.get('tickets_bought'),
            "Departure Date": data.get('departure_date'),
            "Guests Count": guests_count,
            "Drinks Preference": data.get('drinks_preference'),
            "Dietary Restrictions": data.get('dietary_restrictions'),
            "Allergies": data.get('allergies'),
            "Registration Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        logger.info(f"✅ Saved to Airtable: {data.get('full_name')}")
        return True
    except Exception as e:
        logger.error(f"❌ Airtable error: {e}")
        logger.error(f"💡 Проверьте: 1) Права токена 2) Названия полей в таблице 3) BASE_ID и TABLE_NAME")
        return False

# ── Command: /start ───────────────────────────────────────────────────────────
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        # Если пользователь был в процессе регистрации - отменяем её
        await state.clear()
        await message.answer(
            "❌ Регистрация отменена.\n\n",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await state.clear()  # Очищаем любое активное состояние

    user_name = message.from_user.first_name or "Guest"
    welcome_text = (
        f"👋 Привет, {user_name}! Я Weddy, ассистент свадьбы Фёдора и Полины на Бали 08.01.2026!\n\n"
        "Weddy AI — ваш личный консьерж, который никогда не спит и обожает отвечать на одни и те же вопросы по сто раз "
        "о деталях свадьбы, к кому бежать если что-то пошло не так, где поесть, куда сходить и что посмотреть на Бали."
    )

    # Netlify URL интерактивной карты
    MAP_WEB_APP_URL = "https://jolly-cat-97d1fb.netlify.app/"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Регистрация гостя", callback_data="start_registration")],
        [InlineKeyboardButton(text="🗂 Отели, Рестораны, Кафе, Йога, Спа", callback_data="show_menu")],
        [InlineKeyboardButton(text="🗺️ Интерактивная карта мест", web_app=WebAppInfo(url=MAP_WEB_APP_URL))],
        [InlineKeyboardButton(text="📍 Google My Maps", url="https://www.google.com/maps/d/edit?mid=1uycSDIzX2IxUccjnpCCTDn9C0ngQlVc&usp=sharing")],
        [InlineKeyboardButton(text="💡 Полезные советы", callback_data="show_tips")],
        [InlineKeyboardButton(text="📞 Контакты", callback_data="show_contacts")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="show_help")]
    ])

    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="Markdown")

# ── Callback: Start Menu Actions ──────────────────────────────────────────────
@router.callback_query(F.data == "start_registration")
async def callback_start_registration(callback: CallbackQuery, state: FSMContext):
    """Начать регистрацию гостя"""
    await state.clear()
    await state.set_state(GuestRegistration.full_name)
    await callback.message.answer(
        "Отлично! Давайте соберем информацию для организации свадьбы.\n\n"
        "**Как вас зовут?** (Имя и Фамилия)\n\n"
        "_Чтобы отменить регистрацию или вернуться назад, нажмите /cancel_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    await callback.answer()

@router.callback_query(F.data == "show_menu")
async def callback_show_menu(callback: CallbackQuery, state: FSMContext):
    """Показать базу мест на Бали"""
    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍽  Рестораны                              ", callback_data="category_restaurants")],
        [InlineKeyboardButton(text="☕  Завтраки / Ланчи                ", callback_data="category_breakfast")],
        [InlineKeyboardButton(text="🧘  Йога / Фитнес                      ", callback_data="category_yoga")],
        [InlineKeyboardButton(text="🏨  Отели                                      ", callback_data="category_hotels")],
        [InlineKeyboardButton(text="💆  Спа                                          ", callback_data="category_spa")],
        [InlineKeyboardButton(text="🛍  Шоппинг                                ", callback_data="category_shopping")],
        [InlineKeyboardButton(text="🎨  Арт                                          ", callback_data="category_art")]
    ])

    await callback.message.edit_text(
        "🗂 База данных мест на Бали\n\nВыберите категорию:",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "show_tips")
async def callback_show_tips(callback: CallbackQuery, state: FSMContext):
    """Показать полезные советы"""
    await state.clear()

    tips_text = (
        "**📱 Связь и интернет (SIM-карта)**\n"
        "Лучше всего установить приложение [Airalo](https://www.airalo.com) и купить eSIM ещё до вылета — включите интернет сразу по прилёту!\n\n"
        "Также можно приобрести SIM-карты на Бали:\n"
        "• В аэропорту — в телеком магазинах сразу после получения багажа\n"
        "• В любом магазине Telkomsel — попросите настроить вам\n"
        "• Стоимость: 150,000-200,000 индонезийских рупий (~$10-13)\n\n"

        "**🚕 Такси и доставка (обязательное приложение!)**\n"
        "**Gojek** — это must-have приложение для Бали:\n"
        "[Скачать Gojek](https://www.gojek.com/)\n\n"
        "Что можно заказать в Gojek:\n"
        "• GoRide — мототакси (самый быстрый способ)\n"
        "• GoCar — обычное такси\n"
        "• GoFood — доставка еды из ресторанов\n"
        "• GoMart — доставка продуктов из магазинов\n\n"

        "**💰 Деньги**\n"
        "Окей, про деньги. Меняйте ТОЛЬКО в авторизованных money changer центрах. "
        "Да, тот дядька на улице предложит курс \"лучше\" — спойлер: не лучше. "
        "Авторизованные центры — это те, где есть вывеска с лицензией, камеры, и калькулятор не врёт.\n\n"

        "**🗣 Балийский разговорник для выживания**\n"
        "Когда вы пытаетесь говорить на местном языке, происходит магия — цены внезапно падают, а улыбки становятся настоящими.\n\n"

        "**Базовый набор:**\n"
        "• Selamat pagi — Доброе утро\n"
        "• Terima kasih — Спасибо\n"
        "• Sama-sama — Пожалуйста\n\n"

        "**Для рынка:**\n"
        "• Berapa harganya? — Сколько стоит?\n"
        "• Mahal! — Дорого! (часть игры)\n"
        "• Bisa kurang? — Можно дешевле?\n\n"

        "**В ресторане:**\n"
        "• Tidak pedas — Не острое (спойлер: всё равно будет острое)\n"
        "• Enak! — Вкусно!\n"
        "• Bon — Счёт\n\n"

        "**Секретное оружие:**\n"
        "• Om Swastiastu — Традиционное балийское приветствие. "
        "Скажите это, и местные подумают, что вы прожили тут год!\n\n"

        "В общем, даже если произносите как робот — местные оценят попытку. "
        "А если забыли всё — просто улыбайтесь. Работает в 100% случаев.\n\n"

        "Худшее, что может случиться — вы случайно закажете что-то не то в ресторане. "
        "Зато будет история для свадьбы."
    )
    await callback.message.edit_text(tips_text, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "show_contacts")
async def callback_show_contacts(callback: CallbackQuery, state: FSMContext):
    """Показать контакты"""
    await state.clear()

    contacts_text = (
        "**Полезные контакты:**\n\n"
        "👰 **Организатор:**\n"
        "Анастасия\n"
        "📞 +62 812-3760-4476\n"
        "📧 Hello@cincinbali.com\n\n"
        "🚗 **Аренда машины/водителя:**\n"
        "Arneda Baikov\n"
        "📞 +62 859-3539-2295 (Agus)\n"
        "💬 Скажите: \"От Федора\"\n\n"
        "📍 **Место церемонии:**\n"
        "[Bali Beach Glamping](https://maps.app.goo.gl/193xFKgN6Ffgrfh79)\n\n"
        "⏰ **Тайминг:**\n\n"
        "📅 **Дата:** 08/01/2026 - 09/01/2026\n\n"
        "🏨 **Заселение в отель:** 14:00\n"
        "👥 **Время сбора гостей:** 16:00\n"
        "🎉 **Окончание церемонии:** 01:00\n"
        "☕ **Совместный завтрак:** 10:00 | 09/01"
    )
    await callback.message.edit_text(contacts_text, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "show_help")
async def callback_show_help(callback: CallbackQuery, state: FSMContext):
    """Показать помощь"""
    await state.clear()

    help_text = (
        "**Как использовать Weddy:**\n\n"
        "• Просто задавайте вопросы о свадьбе\n"
        "• `/form` - Регистрация гостя\n"
        "• `/menu` - База данных мест на Бали\n"
        "• `/contacts` - Полезные контакты\n"
        "• `/tips` - Полезные советы про Бали\n"
        "• `/cancel` - Отменить регистрацию\n\n"
        "Я говорю на русском и английском!"
    )
    await callback.message.edit_text(help_text, parse_mode="Markdown")
    await callback.answer()

# ── Command: /cancel ──────────────────────────────────────────────────────────
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нечего отменять - вы не в процессе регистрации.")
        return

    await state.clear()
    await message.answer(
        "❌ Регистрация отменена.\n\n"
        "Если захотите зарегистрироваться позже, просто нажмите /form",
        reply_markup=ReplyKeyboardRemove()
    )

# ── Command: /form (and /register for compatibility) ─────────────────────────
@router.message(Command("form", "register"))
async def cmd_register(message: Message, state: FSMContext):
    await state.clear()  # Очищаем предыдущее состояние перед началом новой регистрации
    await state.set_state(GuestRegistration.full_name)
    await message.answer(
        "Отлично! Давайте соберем информацию для организации свадьбы.\n\n"
        "**Как вас зовут?** (Имя и Фамилия)\n\n"
        "_Чтобы отменить регистрацию или вернуться назад, нажмите /cancel_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

# ── FSM: Full Name ────────────────────────────────────────────────────────────
@router.message(GuestRegistration.full_name)
async def process_full_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await state.update_data(telegram_id=message.from_user.id)
    await state.update_data(username=message.from_user.username or "N/A")

    await state.set_state(GuestRegistration.arrival_date)
    await message.answer(
        "Спасибо! Какого числа вы планируете прилететь на Бали?\n"
        "Пример: 03.01.2026"
    )

# ── FSM: Arrival Date ─────────────────────────────────────────────────────────
@router.message(GuestRegistration.arrival_date)
async def process_arrival_date(message: Message, state: FSMContext):
    await state.update_data(arrival_date=message.text)
    await state.set_state(GuestRegistration.tickets_bought)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да"), KeyboardButton(text="Нет")],
            [KeyboardButton(text="Планирую")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "Вы уже купили билеты?",
        reply_markup=keyboard
    )

# ── FSM: Tickets Bought ───────────────────────────────────────────────────────
@router.message(GuestRegistration.tickets_bought)
async def process_tickets(message: Message, state: FSMContext):
    await state.update_data(tickets_bought=message.text)
    await state.set_state(GuestRegistration.departure_date)

    await message.answer(
        "Какого числа планируете вылетать?\nПример: 10.01.2026",
        reply_markup=ReplyKeyboardRemove()
    )

# ── FSM: Departure Date ───────────────────────────────────────────────────────
@router.message(GuestRegistration.departure_date)
async def process_departure_date(message: Message, state: FSMContext):
    await state.update_data(departure_date=message.text)
    await state.set_state(GuestRegistration.guests_count)

    await message.answer(
        "Сколько человек будет с вами (включая вас)?\nНапример: 2"
    )

# ── FSM: Guests Count ─────────────────────────────────────────────────────────
@router.message(GuestRegistration.guests_count)
async def process_guests_count(message: Message, state: FSMContext):
    await state.update_data(guests_count=message.text)
    await state.set_state(GuestRegistration.drinks_preference)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Безалкогольные"), KeyboardButton(text="Не пью")],
            [KeyboardButton(text="Вино"), KeyboardButton(text="Просекко")],
            [KeyboardButton(text="Крепкие напитки"), KeyboardButton(text="Любые")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "Какие напитки предпочитаете?",
        reply_markup=keyboard
    )

# ── FSM: Drinks Preference ────────────────────────────────────────────────────
@router.message(GuestRegistration.drinks_preference)
async def process_drinks(message: Message, state: FSMContext):
    await state.update_data(drinks_preference=message.text)
    await state.set_state(GuestRegistration.dietary_restrictions)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Вегетарианец"), KeyboardButton(text="Веган")],
            [KeyboardButton(text="Без глютена"), KeyboardButton(text="Нет особенностей")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "Есть ли диетические особенности?",
        reply_markup=keyboard
    )

# ── FSM: Dietary Restrictions ─────────────────────────────────────────────────
@router.message(GuestRegistration.dietary_restrictions)
async def process_dietary(message: Message, state: FSMContext):
    await state.update_data(dietary_restrictions=message.text)
    await state.set_state(GuestRegistration.allergies)

    await message.answer(
        "Есть ли аллергии на продукты?\nНапишите или введите 'нет'",
        reply_markup=ReplyKeyboardRemove()
    )

# ── FSM: Allergies (Final) ────────────────────────────────────────────────────
@router.message(GuestRegistration.allergies)
async def process_allergies(message: Message, state: FSMContext):
    await state.update_data(allergies=message.text)

    # Получаем все данные
    data = await state.get_data()

    # Сохраняем в Airtable
    success = save_to_airtable(data)

    if success:
        summary = (
            f"✅ Спасибо, {data['full_name']}! Ваша регистрация завершена.\n\n"
            f"**Ваши данные:**\n"
            f"📅 Прилет: {data['arrival_date']}\n"
            f"🎫 Билеты: {data['tickets_bought']}\n"
            f"📅 Вылет: {data['departure_date']}\n"
            f"👥 Количество: {data['guests_count']}\n"
            f"🍷 Напитки: {data['drinks_preference']}\n"
            f"🥗 Диета: {data['dietary_restrictions']}\n"
            f"⚠️ Аллергии: {data['allergies']}\n\n"
            "Если нужно что-то изменить, напишите /register снова."
        )
        await message.answer(summary, parse_mode="Markdown")
    else:
        await message.answer(
            "❌ Произошла ошибка при сохранении. Попробуйте /register снова."
        )

    await state.clear()

# ── Command: /menu ────────────────────────────────────────────────────────────
@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    """Главное меню с выбором категорий"""
    current_state = await state.get_state()
    if current_state is not None:
        # Если пользователь был в процессе регистрации - отменяем её
        await state.clear()
        await message.answer(
            "❌ Регистрация отменена.\n\n",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await state.clear()  # Очищаем любое активное состояние

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍽  Рестораны                              ", callback_data="category_restaurants")],
        [InlineKeyboardButton(text="☕  Завтраки / Ланчи                ", callback_data="category_breakfast")],
        [InlineKeyboardButton(text="🧘  Йога / Фитнес                      ", callback_data="category_yoga")],
        [InlineKeyboardButton(text="🏨  Отели                                      ", callback_data="category_hotels")],
        [InlineKeyboardButton(text="💆  Спа                                          ", callback_data="category_spa")],
        [InlineKeyboardButton(text="🛍  Шоппинг                                ", callback_data="category_shopping")],
        [InlineKeyboardButton(text="🎨  Арт                                          ", callback_data="category_art")]
    ])

    await message.answer(
        "🗂 База данных мест на Бали\n\nВыберите категорию:",
        reply_markup=keyboard
    )

# ── Callback: Category Selection ──────────────────────────────────────────────
@router.callback_query(F.data.startswith("category_"))
async def category_selected(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора категории"""
    # Отменяем регистрацию, если пользователь был в её процессе
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()

    category = callback.data.split("_")[1]

    # Проверяем наличие мест в каждом регионе для выбранной категории
    available_regions = {}

    if category == "restaurants":
        available_regions = {loc: len(smart_bot.restaurants_db.get(loc, [])) for loc in ["ubud", "canggu", "uluwatu", "seminyak"]}
    elif category == "breakfast":
        available_regions = {loc: len(breakfast_bot.cafes_db.get(loc, [])) for loc in ["ubud", "canggu", "uluwatu", "seminyak"]}
    elif category == "yoga":
        available_regions = {loc: len(yoga_bot.studios_db.get(loc, [])) for loc in ["ubud", "canggu", "uluwatu", "seminyak"]}
    elif category == "hotels":
        available_regions = {loc: len(hotels_bot.hotels_db.get(loc, [])) for loc in ["ubud", "canggu", "uluwatu", "seminyak"]}
    elif category == "spa":
        available_regions = {loc: len(spa_bot.spas_db.get(loc, [])) for loc in ["ubud", "canggu", "uluwatu", "seminyak"]}
    elif category == "shopping":
        available_regions = {loc: len(shopping_bot.shops_db.get(loc, [])) for loc in ["ubud", "canggu", "uluwatu", "seminyak"]}
    elif category == "art":
        available_regions = {loc: len(art_bot.art_db.get(loc, [])) for loc in ["ubud", "canggu", "uluwatu", "seminyak"]}

    # Создаем кнопки только для регионов, где есть места
    region_names = {
        "ubud": "Убуд",
        "canggu": "Чангу",
        "uluwatu": "Улувату",
        "seminyak": "Семиньяк"
    }

    buttons = []
    row = []
    for location, count in available_regions.items():
        if count > 0:
            row.append(InlineKeyboardButton(
                text=region_names[location],
                callback_data=f"{category}_{location}"
            ))
            # Делаем по 2 кнопки в ряд
            if len(row) == 2:
                buttons.append(row)
                row = []

    # Добавляем оставшиеся кнопки
    if row:
        buttons.append(row)

    # Кнопка "Назад"
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    emoji_map = {
        "restaurants": "🍽",
        "breakfast": "☕",
        "yoga": "🧘",
        "hotels": "🏨",
        "spa": "💆",
        "shopping": "🛍",
        "art": "🎨"
    }

    await callback.message.edit_text(
        f"{emoji_map.get(category, '')} Выберите регион:",
        reply_markup=keyboard
    )
    await callback.answer()

# ── Callback: Region Selection ────────────────────────────────────────────────
@router.callback_query(F.data.in_(["back_to_menu"]))
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    # Отменяем регистрацию, если пользователь был в её процессе
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍽  Рестораны                              ", callback_data="category_restaurants")],
        [InlineKeyboardButton(text="☕  Завтраки / Ланчи                ", callback_data="category_breakfast")],
        [InlineKeyboardButton(text="🧘  Йога / Фитнес                      ", callback_data="category_yoga")],
        [InlineKeyboardButton(text="🏨  Отели                                      ", callback_data="category_hotels")],
        [InlineKeyboardButton(text="💆  Спа                                          ", callback_data="category_spa")],
        [InlineKeyboardButton(text="🛍  Шоппинг                                ", callback_data="category_shopping")],
        [InlineKeyboardButton(text="🎨  Арт                                          ", callback_data="category_art")]
    ])

    await callback.message.edit_text(
        "🗂 База данных мест на Бали\n\nВыберите категорию:",
        reply_markup=keyboard
    )
    await callback.answer()

# ── Callback: Show Results ────────────────────────────────────────────────────
@router.callback_query(F.data.contains("_"))
async def show_results(callback: CallbackQuery, state: FSMContext):
    """Показать результаты по выбранной категории и региону"""
    # Отменяем регистрацию, если пользователь был в её процессе
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()

    parts = callback.data.split("_")

    if len(parts) != 2:
        await callback.answer("Ошибка обработки запроса")
        return

    category, location = parts

    await callback.message.edit_text("🔍 Загружаю данные...")

    try:
        if category == "restaurants":
            search_results = await smart_bot.search_restaurants("", location)
            if search_results.get("curated_restaurants"):
                response_text = f"🍽 Рестораны в {location.capitalize()}:\n\n"
                for i, rest in enumerate(search_results.get("curated_restaurants", []), 1):
                    response_text += f"{i}. {rest['name']}"
                    if rest.get('price_range'):
                        response_text += f" · {rest['price_range']}"
                    response_text += "\n"
                    if rest.get('cuisine_ru'):
                        response_text += f"{rest['cuisine_ru']}\n"
                    if rest.get('vibe_ru'):
                        response_text += f"{rest['vibe_ru']}\n"
                    if rest.get('instagram_link'):
                        response_text += f"{rest['instagram_link']}\n"
                    response_text += "\n"
            else:
                response_text = f"В базе нет ресторанов в {location.capitalize()}"

        elif category == "yoga":
            search_results = await yoga_bot.search_studios("", location)
            if search_results.get("curated_studios"):
                response_text = f"🧘 Студии йоги в {location.capitalize()}:\n\n"
                for i, studio in enumerate(search_results.get("curated_studios", []), 1):
                    response_text += f"{i}. {studio['name']}"
                    if studio.get('booking_type'):
                        response_text += f" · {studio['booking_type']}"
                    response_text += "\n"
                    if studio.get('category_ru'):
                        response_text += f"{studio['category_ru']}\n"
                    if studio.get('specialties_ru'):
                        response_text += f"{studio['specialties_ru']}\n"
                    if studio.get('highlights_ru'):
                        response_text += f"{studio['highlights_ru']}\n"
                    if studio.get('instagram_link'):
                        response_text += f"{studio['instagram_link']}\n"
                    response_text += "\n"
            else:
                response_text = f"В базе нет студий йоги в {location.capitalize()}"

        elif category == "hotels":
            search_results = await hotels_bot.search_hotels("", location)
            if search_results.get("curated_hotels"):
                response_text = f"🏨 Отели в {location.capitalize()}:\n\n"
                for i, hotel in enumerate(search_results.get("curated_hotels", []), 1):
                    response_text += f"{i}. {hotel['name']}"
                    if hotel.get('price_level'):
                        response_text += f" · {hotel['price_level']}"
                    response_text += "\n"
                    if hotel.get('type_ru'):
                        response_text += f"{hotel['type_ru']}\n"
                    if hotel.get('style_ru'):
                        response_text += f"{hotel['style_ru']}\n"
                    if hotel.get('vibe_ru'):
                        response_text += f"{hotel['vibe_ru']}\n"
                    if hotel.get('instagram_handle'):
                        response_text += f"{hotel['instagram_handle']}\n"
                    if hotel.get('booking_link'):
                        response_text += f"{hotel['booking_link']}\n"
                    response_text += "\n"
            else:
                response_text = f"В базе нет отелей в {location.capitalize()}"

        elif category == "breakfast":
            search_results = await breakfast_bot.search_cafes("", location)
            if search_results.get("curated_cafes"):
                response_text = f"☕ Завтраки/Ланчи в {location.capitalize()}:\n\n"
                for i, cafe in enumerate(search_results.get("curated_cafes", []), 1):
                    response_text += f"{i}. {cafe['name']}"
                    if cafe.get('price_level'):
                        response_text += f" · {cafe['price_level']}"
                    response_text += "\n"
                    if cafe.get('category_ru'):
                        response_text += f"{cafe['category_ru']}\n"
                    if cafe.get('cuisine_ru'):
                        response_text += f"{cafe['cuisine_ru']}\n"
                    if cafe.get('vibe_ru'):
                        response_text += f"{cafe['vibe_ru']}\n"
                    if cafe.get('instagram_link'):
                        response_text += f"{cafe['instagram_link']}\n"
                    response_text += "\n"
            else:
                response_text = f"В базе нет кафе в {location.capitalize()}"

        elif category == "spa":
            search_results = await spa_bot.search_spas("", location)
            if search_results.get("curated_spas"):
                response_text = f"💆 Спа в {location.capitalize()}:\n\n"
                for i, spa in enumerate(search_results.get("curated_spas", []), 1):
                    response_text += f"{i}. {spa['name']}"
                    if spa.get('price_level'):
                        response_text += f" · {spa['price_level']}"
                    response_text += "\n"
                    if spa.get('category_ru'):
                        response_text += f"{spa['category_ru']}\n"
                    if spa.get('massage_type_ru'):
                        response_text += f"{spa['massage_type_ru']}\n"
                    if spa.get('vibe_ru'):
                        response_text += f"{spa['vibe_ru']}\n"
                    if spa.get('instagram_link'):
                        response_text += f"{spa['instagram_link']}\n"
                    response_text += "\n"
            else:
                response_text = f"В базе нет спа в {location.capitalize()}"

        elif category == "shopping":
            search_results = await shopping_bot.search_shops("", location)
            if search_results.get("curated_shops"):
                response_text = f"🛍 Шоппинг в {location.capitalize()}:\n\n"
                for i, shop in enumerate(search_results.get("curated_shops", []), 1):
                    response_text += f"{i}. {shop['name']}"
                    if shop.get('price_level'):
                        response_text += f" · {shop['price_level']}"
                    response_text += "\n"
                    if shop.get('category_ru'):
                        response_text += f"{shop['category_ru']}\n"
                    if shop.get('specialty_ru'):
                        response_text += f"{shop['specialty_ru']}\n"
                    if shop.get('vibe_ru'):
                        response_text += f"{shop['vibe_ru']}\n"
                    if shop.get('instagram_link'):
                        response_text += f"{shop['instagram_link']}\n"
                    response_text += "\n"
            else:
                response_text = f"В базе нет магазинов в {location.capitalize()}"

        elif category == "art":
            search_results = await art_bot.search_art("", location)
            if search_results.get("curated_art"):
                response_text = f"🎨 Арт в {location.capitalize()}:\n\n"
                for i, art in enumerate(search_results.get("curated_art", []), 1):
                    response_text += f"{i}. {art['name']}"
                    if art.get('price_level'):
                        response_text += f" · {art['price_level']}"
                    response_text += "\n"
                    if art.get('category_ru'):
                        response_text += f"{art['category_ru']}\n"
                    if art.get('specialty_ru'):
                        response_text += f"{art['specialty_ru']}\n"
                    if art.get('vibe_ru'):
                        response_text += f"{art['vibe_ru']}\n"
                    if art.get('instagram_link'):
                        response_text += f"{art['instagram_link']}\n"
                    response_text += "\n"
            else:
                response_text = f"В базе нет арт-мест в {location.capitalize()}"

        else:
            response_text = "Неизвестная категория"

        # Кнопка "Назад в меню"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_menu")]
        ])

        await callback.message.edit_text(response_text, reply_markup=keyboard)
        await callback.answer()

    except Exception as e:
        logger.error(f"❌ Error in show_results: {e}")
        await callback.message.edit_text(f"❌ Ошибка загрузки данных: {str(e)}")
        await callback.answer()

# ── Command: /contacts ────────────────────────────────────────────────────────
@router.message(Command("contacts"))
async def cmd_contacts(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        # Если пользователь был в процессе регистрации - отменяем её
        await state.clear()
        await message.answer(
            "❌ Регистрация отменена.\n\n",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await state.clear()  # Очищаем любое активное состояние

    contacts_text = (
        "**Полезные контакты:**\n\n"
        "👰 **Организатор:**\n"
        "Анастасия\n"
        "📞 +62 812-3760-4476\n"
        "📧 Hello@cincinbali.com\n\n"
        "🚗 **Аренда машины/водителя:**\n"
        "Arneda Baikov\n"
        "📞 +62 859-3539-2295 (Agus)\n"
        "💬 Скажите: \"От Федора\"\n\n"
        "📍 **Место церемонии:**\n"
        "[Bali Beach Glamping](https://maps.app.goo.gl/193xFKgN6Ffgrfh79)\n\n"
        "⏰ **Тайминг:**\n\n"
        "📅 **Дата:** 08/01/2026 - 09/01/2026\n\n"
        "🏨 **Заселение в отель:** 14:00\n"
        "👥 **Время сбора гостей:** 16:00\n"
        "🎉 **Окончание церемонии:** 01:00\n"
        "☕ **Совместный завтрак:** 10:00 | 09/01"
    )
    await message.answer(contacts_text, parse_mode="Markdown")

# ── Command: /help ────────────────────────────────────────────────────────────
@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        # Если пользователь был в процессе регистрации - отменяем её
        await state.clear()
        await message.answer(
            "❌ Регистрация отменена.\n\n",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await state.clear()  # Очищаем любое активное состояние

    help_text = (
        "**Как использовать Weddy:**\n\n"
        "• Просто задавайте вопросы о свадьбе\n"
        "• `/form` - Регистрация гостя\n"
        "• `/menu` - База данных мест на Бали\n"
        "• `/contacts` - Полезные контакты\n"
        "• `/tips` - Полезные советы про Бали\n"
        "• `/cancel` - Отменить регистрацию\n\n"
        "Я говорю на русском и английском!"
    )
    await message.answer(help_text, parse_mode="Markdown")

# ── Command: /map ─────────────────────────────────────────────────────────────
@router.message(Command("map"))
async def cmd_map(message: Message, state: FSMContext):
    """Show Google My Maps link"""
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await message.answer(
            "❌ Регистрация отменена.\n\n",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await state.clear()

    map_text = (
        "🗺️ **Карта рекомендованных мест на Бали**\n\n"
        "Все наши проверенные места на интерактивной карте:\n"
        "🍽️ Рестораны\n"
        "☕ Завтраки\n"
        "🧘 Йога\n"
        "🏨 Отели\n"
        "💆 Спа\n"
        "🛍️ Шоппинг\n"
        "🎨 Арт\n\n"
        "[Открыть карту](https://www.google.com/maps/d/edit?mid=1uycSDIzX2IxUccjnpCCTDn9C0ngQlVc&usp=sharing)"
    )
    await message.answer(map_text, parse_mode="Markdown")

# ── Command: /tips ────────────────────────────────────────────────────────────
@router.message(Command("tips"))
async def cmd_tips(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        # Если пользователь был в процессе регистрации - отменяем её
        await state.clear()
        await message.answer(
            "❌ Регистрация отменена.\n\n",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await state.clear()  # Очищаем любое активное состояние

    tips_text = (
        "**📱 Связь и интернет (SIM-карта)**\n"
        "Лучше всего установить приложение [Airalo](https://www.airalo.com) и купить eSIM ещё до вылета — включите интернет сразу по прилёту!\n\n"
        "Также можно приобрести SIM-карты на Бали:\n"
        "• В аэропорту — в телеком магазинах сразу после получения багажа\n"
        "• В любом магазине Telkomsel — попросите настроить вам\n"
        "• Стоимость: 150,000-200,000 индонезийских рупий (~$10-13)\n\n"

        "**🚕 Такси и доставка (обязательное приложение!)**\n"
        "**Gojek** — это must-have приложение для Бали:\n"
        "[Скачать Gojek](https://www.gojek.com/)\n\n"
        "Что можно заказать в Gojek:\n"
        "• GoRide — мототакси (самый быстрый способ)\n"
        "• GoCar — обычное такси\n"
        "• GoFood — доставка еды из ресторанов\n"
        "• GoMart — доставка продуктов из магазинов\n\n"

        "**💰 Деньги**\n"
        "Окей, про деньги. Меняйте ТОЛЬКО в авторизованных money changer центрах. "
        "Да, тот дядька на улице предложит курс \"лучше\" — спойлер: не лучше. "
        "Авторизованные центры — это те, где есть вывеска с лицензией, камеры, и калькулятор не врёт.\n\n"

        "**🗣 Балийский разговорник для выживания**\n"
        "Когда вы пытаетесь говорить на местном языке, происходит магия — цены внезапно падают, а улыбки становятся настоящими.\n\n"

        "**Базовый набор:**\n"
        "• Selamat pagi — Доброе утро\n"
        "• Terima kasih — Спасибо\n"
        "• Sama-sama — Пожалуйста\n\n"

        "**Для рынка:**\n"
        "• Berapa harganya? — Сколько стоит?\n"
        "• Mahal! — Дорого! (часть игры)\n"
        "• Bisa kurang? — Можно дешевле?\n\n"

        "**В ресторане:**\n"
        "• Tidak pedas — Не острое (спойлер: всё равно будет острое)\n"
        "• Enak! — Вкусно!\n"
        "• Bon — Счёт\n\n"

        "**Секретное оружие:**\n"
        "• Om Swastiastu — Традиционное балийское приветствие. "
        "Скажите это, и местные подумают, что вы прожили тут год!\n\n"

        "В общем, даже если произносите как робот — местные оценят попытку. "
        "А если забыли всё — просто улыбайтесь. Работает в 100% случаев.\n\n"

        "Худшее, что может случиться — вы случайно закажете что-то не то в ресторане. "
        "Зато будет история для свадьбы."
    )
    await message.answer(tips_text, parse_mode="Markdown")

# ── Command: /clear ───────────────────────────────────────────────────────────
@router.message(Command("clear"))
async def cmd_clear(message: Message):
    user_id = message.from_user.id

    if user_id in conversation_history:
        conversation_history[user_id] = []
        await message.answer("🗑 История разговора очищена. Начнём с чистого листа!")
    else:
        await message.answer("История и так пуста.")

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN COMMANDS (Only for ADMIN_ID)
# ══════════════════════════════════════════════════════════════════════════════

# ── Command: /admin ───────────────────────────────────────────────────────────
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return  # Игнорируем не-админов

    admin_text = (
        "🔧 **Админ-панель Weddy Bot**\n\n"
        "**Доступные команды:**\n"
        "• `/stats` — Статистика гостей\n"
        "• `/export` — Выгрузить данные в CSV\n"
        "• `/text2all <текст>` — Рассылка всем пользователям\n"
        "• `/getguests` — Список зарегистрированных гостей\n\n"
        f"👤 Ваш ID: `{ADMIN_ID}`"
    )
    await message.answer(admin_text, parse_mode="Markdown")

# ── Command: /stats ───────────────────────────────────────────────────────────
@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        # Получаем все записи из Airtable
        records = guests_table.all()

        if not records:
            await message.answer("📊 **Статистика:** Пока нет зарегистрированных гостей.")
            return

        total_guests = len(records)
        total_people = sum(record['fields'].get('Guests Count', 1) for record in records)

        # Статистика по билетам
        tickets_yes = sum(1 for r in records if r['fields'].get('Tickets Bought') == 'Да')
        tickets_no = sum(1 for r in records if r['fields'].get('Tickets Bought') == 'Нет')
        tickets_plan = sum(1 for r in records if r['fields'].get('Tickets Bought') == 'Планирую')

        # Топ дат прилёта
        arrival_dates = defaultdict(int)
        for r in records:
            date = r['fields'].get('Arrival Date', 'Не указано')
            arrival_dates[date] += 1

        top_dates = sorted(arrival_dates.items(), key=lambda x: x[1], reverse=True)[:5]

        stats_text = (
            f"📊 **Статистика гостей**\n\n"
            f"👥 Всего зарегистрировано: **{total_guests}** гостей\n"
            f"🧑‍🤝‍🧑 Всего прилетит людей: **{total_people}** человек\n\n"
            f"✈️ **Билеты:**\n"
            f"• ✅ Купили: {tickets_yes}\n"
            f"• ❌ Не купили: {tickets_no}\n"
            f"• 📅 Планируют: {tickets_plan}\n\n"
            f"📅 **Топ дат прилёта:**\n"
        )

        for date, count in top_dates:
            stats_text += f"• {date}: {count} гостей\n"

        await message.answer(stats_text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"❌ Error in /stats: {e}")
        await message.answer(f"❌ Ошибка при получении статистики: {str(e)}")

# ── Command: /export ──────────────────────────────────────────────────────────
@router.message(Command("export"))
async def cmd_export(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        # Получаем все записи
        records = guests_table.all()

        if not records:
            await message.answer("📊 Нет данных для экспорта.")
            return

        # Создаём CSV в памяти
        output = io.StringIO()
        writer = csv.writer(output)

        # Заголовки
        headers = [
            "Telegram ID", "Full Name", "Username", "Arrival Date",
            "Tickets Bought", "Departure Date", "Guests Count",
            "Drinks Preference", "Dietary Restrictions", "Allergies",
            "Registration Date"
        ]
        writer.writerow(headers)

        # Данные
        for record in records:
            fields = record['fields']
            row = [
                fields.get('Telegram ID', ''),
                fields.get('Full Name', ''),
                fields.get('Username', ''),
                fields.get('Arrival Date', ''),
                fields.get('Tickets Bought', ''),
                fields.get('Departure Date', ''),
                fields.get('Guests Count', ''),
                fields.get('Drinks Preference', ''),
                fields.get('Dietary Restrictions', ''),
                fields.get('Allergies', ''),
                fields.get('Registration Date', '')
            ]
            writer.writerow(row)

        # Сохраняем CSV во временный файл
        csv_content = output.getvalue()
        output.close()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"wedding_guests_{timestamp}.csv"
        filepath = Path(f"/tmp/{filename}")

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(csv_content)

        # Отправляем файл
        document = FSInputFile(filepath)
        await message.answer_document(
            document=document,
            caption=f"📊 Экспорт гостей ({len(records)} записей)\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )

        # Удаляем временный файл
        filepath.unlink()

    except Exception as e:
        logger.error(f"❌ Error in /export: {e}")
        await message.answer(f"❌ Ошибка при экспорте: {str(e)}")

# ── Command: /text2all ───────────────────────────────────────────────────────
@router.message(Command("text2all"))
async def cmd_text2all(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    # Извлекаем текст после команды
    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) < 2:
        await message.answer(
            "❌ Использование: `/text2all <текст сообщения>`\n\n"
            "Пример: `/text2all Всем привет! Напоминаю про регистрацию`",
            parse_mode="Markdown"
        )
        return

    broadcast_text = text_parts[1]

    # Получаем все Telegram ID из Airtable
    try:
        records = guests_table.all()
        user_ids = set()
        for record in records:
            tid = record['fields'].get('Telegram ID')
            if tid:
                user_ids.add(int(tid))

        # Добавляем user_id из all_users (те, кто писал боту, но не регистрировался)
        user_ids.update(all_users)

        if not user_ids:
            await message.answer("❌ Нет пользователей для рассылки.")
            return

        # Отправляем сообщение всем
        success_count = 0
        fail_count = 0

        status_msg = await message.answer(f"📤 Начинаю рассылку {len(user_ids)} пользователям...")

        for user_id in user_ids:
            try:
                await bot.send_message(user_id, broadcast_text)
                success_count += 1
            except Exception as e:
                logger.warning(f"Failed to send to {user_id}: {e}")
                fail_count += 1

        await status_msg.edit_text(
            f"✅ Рассылка завершена!\n\n"
            f"📨 Отправлено: {success_count}\n"
            f"❌ Не доставлено: {fail_count}"
        )

    except Exception as e:
        logger.error(f"❌ Error in /text2all: {e}")
        await message.answer(f"❌ Ошибка при рассылке: {str(e)}")

# ── Command: /getguests ───────────────────────────────────────────────────────
@router.message(Command("getguests"))
async def cmd_getguests(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        records = guests_table.all()

        if not records:
            await message.answer("📋 Нет зарегистрированных гостей.")
            return

        guests_text = f"📋 **Зарегистрированные гости ({len(records)}):**\n\n"

        for i, record in enumerate(records, 1):
            fields = record['fields']
            name = fields.get('Full Name', 'N/A')
            arrival = fields.get('Arrival Date', 'N/A')
            count = fields.get('Guests Count', 1)
            tickets = fields.get('Tickets Bought', 'N/A')

            guests_text += (
                f"{i}. **{name}**\n"
                f"   📅 Прилёт: {arrival} | 👥 {count} чел. | 🎫 {tickets}\n\n"
            )

            # Telegram имеет лимит 4096 символов на сообщение
            if len(guests_text) > 3500:
                await message.answer(guests_text, parse_mode="Markdown")
                guests_text = ""

        if guests_text:
            await message.answer(guests_text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"❌ Error in /getguests: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")

# ══════════════════════════════════════════════════════════════════════════════
# END OF ADMIN COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

# ── General Messages (Claude AI) ──────────────────────────────────────────────
@router.message(F.text, StateFilter(None))
async def handle_message(message: Message, state: FSMContext):
    user_name = message.from_user.first_name or "Guest"
    user_id = message.from_user.id

    # Добавляем пользователя в множество (для broadcast)
    all_users.add(user_id)

    logger.info(f"➡️ Message from {user_id}: {message.text}")

    # Если пользователь просто пишет текст, убеждаемся что нет активного FSM
    await state.clear()

    await message.chat.do("typing")
    response = await generate_weddy_response(message.text, user_name, user_id, message)
    await message.answer(response)

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    dp.include_router(router)
    logger.info("🚀 Запускаем Weddy Bot v2 с регистрацией гостей...")

    # Устанавливаем меню команд
    commands = [
        BotCommand(command="start", description="🏠 Главное меню"),
        BotCommand(command="form", description="📝 Регистрация гостя"),
        BotCommand(command="menu", description="🗂 Рекомендованные места на Бали"),
        BotCommand(command="map", description="📍 Посмотреть карту мест"),
        BotCommand(command="tips", description="💡 Полезные советы"),
        BotCommand(command="contacts", description="📞 Контакты"),
        BotCommand(command="clear", description="🗑 Очистить историю"),
        BotCommand(command="help", description="❓ Help")
    ]
    await bot.set_my_commands(commands)
    logger.info("✅ Меню команд установлено")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())