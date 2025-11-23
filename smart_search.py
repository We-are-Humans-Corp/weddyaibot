"""
Умная двухслойная система поиска ресторанов на Бали
Слой 1: Кураторская база из Airtable (приоритет)
Слой 2: Perplexity API (дополнение + свежие данные)
"""

import httpx
from typing import List, Dict, Optional
from fuzzywuzzy import fuzz
from pyairtable import Api


class SmartBaliBot:
    def __init__(self, perplexity_api_key: str, airtable_token: str, airtable_base_id: str, restaurants_table_name: str):
        self.perplexity_api_key = perplexity_api_key
        self.airtable_api = Api(airtable_token)
        self.restaurants_table = self.airtable_api.table(airtable_base_id, restaurants_table_name)
        self.curated_db = {}  # Будет загружен из Airtable
        self.restaurants_db = self._load_restaurants_from_airtable()  # Инициализируем сразу
        self.config = {
            "excluded_domains": ["tripadvisor.com", "timeout.com"],
            "preferred_domains": [
                "google.com/maps", "thenomadexperience.com", "instagram.com",
                "theworlds50best.com", "eater.com", "seriouseats.com",
                "balibible.com", "thehoneycombers.com"
            ]
        }

    def _normalize_area(self, area: str) -> str:
        """Нормализует название района к стандартному виду"""
        area_lower = area.lower()

        # Canggu включает: canggu, berawa, pererenan
        if any(x in area_lower for x in ['canggu', 'berawa', 'pererenan']):
            return 'canggu'
        # Uluwatu включает: uluwatu, bingin
        elif any(x in area_lower for x in ['uluwatu', 'bingin']):
            return 'uluwatu'
        # Seminyak включает: seminyak, kerobokan
        elif any(x in area_lower for x in ['seminyak', 'kerobokan']):
            return 'seminyak'
        # Ubud остается как есть
        elif 'ubud' in area_lower:
            return 'ubud'
        else:
            return area_lower

    def _load_restaurants_from_airtable(self):
        """Загружает рестораны из Airtable при каждом запросе"""
        try:
            records = self.restaurants_table.all()
            print(f"🔍 DEBUG Airtable: Загружено {len(records)} записей")

            # Группируем по area (location)
            db = {}
            for record in records:
                fields = record['fields']

                # DEBUG: Печатаем ВСЕ поля первой записи
                if len(db) == 0:
                    print(f"🔍 DEBUG: Доступные поля в Airtable: {list(fields.keys())}")
                    print(f"🔍 DEBUG: Пример записи: {fields}")

                area_raw = fields.get('area', 'unknown')
                area = self._normalize_area(area_raw)

                if area not in db:
                    db[area] = []

                # Преобразуем в формат нашей системы
                vibe_tags = fields.get('vibe_tags', [])
                # Если vibe_tags строка - разбиваем, если список - используем как есть
                if isinstance(vibe_tags, str):
                    tags_list = vibe_tags.split(',') if vibe_tags else []
                elif isinstance(vibe_tags, list):
                    tags_list = vibe_tags
                else:
                    tags_list = []

                restaurant = {
                    "name": fields.get('restaurant_name_en', 'Unknown'),
                    "type": fields.get('category_en', ''),
                    "cuisine": fields.get('cuisine_style_en', ''),  # Английская версия для поиска
                    "cuisine_ru": fields.get('cuisine_style_ru', ''),  # Русская версия для отображения
                    "price_range": fields.get('price_level', ''),
                    "vibe": fields.get('vibe_short_en', ''),  # Английская версия для поиска
                    "vibe_ru": fields.get('vibe_short_ru', ''),  # Русская версия для отображения
                    "instagram_link": fields.get('instagram_link', ''),  # Instagram ссылка
                    "tags": tags_list,
                    "keywords": []  # Создадим из других полей
                }

                # Генерируем keywords для поиска
                keywords = []
                if restaurant["type"]:
                    keywords.append(restaurant["type"].lower())
                if restaurant["cuisine"]:
                    keywords.extend(restaurant["cuisine"].lower().split())
                if restaurant["vibe"]:
                    keywords.extend(restaurant["vibe"].lower().split())
                # tags_list уже список, не нужно вызывать split()
                if restaurant["tags"]:
                    keywords.extend([tag.strip().lower() for tag in restaurant["tags"]])

                restaurant["keywords"] = list(set(keywords))  # Убираем дубликаты

                db[area].append(restaurant)

            print(f"🔍 DEBUG Airtable: Сгруппировано по локациям: {list(db.keys())}")
            for loc, rests in db.items():
                print(f"  - {loc}: {len(rests)} ресторанов")

            return db

        except Exception as e:
            print(f"Error loading restaurants from Airtable: {e}")
            import traceback
            traceback.print_exc()
            return {}

    async def search_restaurants(self, user_query: str, location: Optional[str] = None) -> Dict:
        """
        Главная функция поиска:
        1. Проверяет кураторскую базу
        2. Если нужно - дополняет через Perplexity API
        """

        # ШАГ 1: Поиск в кураторской базе
        curated_results = self._search_curated_db(user_query, location)

        # ШАГ 2: Определяем, нужен ли API запрос
        needs_api_search = self._should_use_api(user_query, curated_results)

        api_results = None
        if needs_api_search:
            # ШАГ 3: Дополняем через Perplexity API
            api_results = await self._search_with_perplexity(user_query, location, curated_results)

        # ШАГ 4: Объединяем результаты
        final_response = self._merge_results(curated_results, api_results, user_query)

        return final_response

    def _search_curated_db(self, query: str, location: Optional[str] = None) -> List[Dict]:
        """Поиск по кураторской базе из Airtable"""

        # Загружаем свежие данные из Airtable
        self.curated_db = self._load_restaurants_from_airtable()

        print(f"🔍 DEBUG _search_curated_db: query='{query}', location='{location}'")

        query_lower = query.lower()
        results = []

        # Определяем локации для поиска
        locations_to_search = [location.lower()] if location else self.curated_db.keys()

        print(f"🔍 DEBUG locations_to_search: {list(locations_to_search)}")

        # Проверяем, это общий запрос или специфичный
        general_queries = [
            "ресторан", "restaurant", "где поесть", "where to eat",
            "поесть", "eat", "кафе", "cafe", "еда", "food"
        ]
        # Пустой query или общие запросы считаются общим запросом
        is_general_query = (not query_lower.strip()) or (any(gq in query_lower for gq in general_queries) and len(query_lower.split()) <= 5)

        for loc in locations_to_search:
            if loc not in self.curated_db:
                continue

            for restaurant in self.curated_db[loc]:
                score = self._calculate_relevance_score(query_lower, restaurant)

                # Если общий запрос - показываем ВСЕ рестораны из локации
                if is_general_query:
                    results.append({
                        "restaurant": restaurant,
                        "location": loc,
                        "relevance_score": score,
                        "source": "curated"
                    })
                # Если специфичный запрос - применяем порог релевантности
                elif score > 40:  # Снизил порог с 60 до 40
                    results.append({
                        "restaurant": restaurant,
                        "location": loc,
                        "relevance_score": score,
                        "source": "curated"
                    })

        # Сортируем по релевантности
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        return results  # Возвращаем ВСЕ результаты (без ограничения топ-10)

    def _calculate_relevance_score(self, query: str, restaurant: Dict) -> int:
        """Рассчитываем релевантность ресторана к запросу"""

        score = 0

        # Проверяем название
        name_match = fuzz.partial_ratio(query, restaurant["name"].lower())
        score += name_match * 0.4  # 40% веса

        # Проверяем кухню
        if "cuisine" in restaurant:
            cuisine_match = fuzz.partial_ratio(query, restaurant["cuisine"].lower())
            score += cuisine_match * 0.2

        # Проверяем ключевые слова
        if "keywords" in restaurant:
            for keyword in restaurant["keywords"]:
                if keyword in query:
                    score += 20

        # Проверяем тип заведения
        if "type" in restaurant:
            type_match = fuzz.partial_ratio(query, restaurant["type"].lower())
            score += type_match * 0.2

        # Специальные термины
        special_terms = {
            "michelin": ["michelin", "starred", "star"],
            "fine dining": ["fine dining", "tasting menu", "degustation"],
            "romantic": ["romantic", "date", "anniversary"],
            "view": ["view", "ocean", "sunset", "cliff"],
            "новый": ["new", "2024", "2025", "opening"],
            "дешевый": ["cheap", "budget", "affordable"],
            "дорогой": ["expensive", "luxury", "premium"]
        }

        for term_category, terms in special_terms.items():
            if any(term in query for term in terms):
                if any(term in str(restaurant.get("highlights", "")).lower() or
                       term in str(restaurant.get("distinction", "")).lower() or
                       term in str(restaurant.get("keywords", "")).lower()
                       for term in terms):
                    score += 15

        return min(score, 100)  # Максимум 100

    def _should_use_api(self, query: str, curated_results: List[Dict]) -> bool:
        """Решаем, нужен ли запрос к Perplexity API"""

        # API ТОЛЬКО для специфичных запросов:
        specific_triggers = [
            "новый", "new", "2024", "2025", "открыли", "opened",
            "актуальн", "current", "сейчас", "now",
            "цена", "price", "стоимость", "сколько стоит",
            "работает", "открыто", "open", "hours",
            "забронировать", "booking", "reservation"
        ]

        query_lower = query.lower()

        # Если есть специфичные триггерные слова - идем в API
        if any(trigger in query_lower for trigger in specific_triggers):
            return True

        # Если в базе НЕТ результатов - дополняем через API
        if len(curated_results) == 0:
            return True

        # Если есть результаты в базе - НЕ используем API (показываем только базу)
        return False

    async def _search_with_perplexity(
        self,
        query: str,
        location: Optional[str],
        curated_results: List[Dict]
    ) -> Optional[Dict]:
        """Поиск через Perplexity API с учетом кураторской базы"""

        # Формируем контекст из кураторской базы
        context = self._build_context_from_curated(curated_results)

        # Улучшаем запрос
        enhanced_query = self._enhance_query_for_api(query, location, context)

        # System prompt учитывает твою базу
        system_prompt = f"""You are an expert Bali restaurant curator with access to a curated database of acclaimed restaurants.

PRIORITY RESTAURANTS (check these first):
{context}

Your task:
1. If the user asks about restaurants from the priority list above, provide CURRENT information:
   - Current opening hours
   - Latest prices
   - Recent reviews/ratings
   - Booking information
   - Any changes since 2024-2025

2. If asking about NEW restaurants not in the priority list:
   - Focus on places opened in 2024-2025
   - Prioritize quality establishments similar to the curated list
   - Include practical details: location, prices, contact

3. Always provide:
   - Exact address and contact
   - Current price range
   - Opening hours
   - Reservation requirements
   - What makes it special
   - Recent updates or changes

STRICT WRITING RULES:
- NEVER use clichés: "настоящий рай", "гастрономический рай", "райское место"
- NEVER use: "топовые рекомендации", "это настоящий...", "расслабленная атмосфера"
- NEVER use: "круто", "супер", "мега", "клёво", "прикольно"
- Be concise and factual
- No excessive enthusiasm or marketing language
- Use "хорошие", "проверенные", "интересные" instead of "топовые"

Respond in Russian with insider knowledge."""

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.perplexity_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "sonar",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": enhanced_query}
                        ],
                        "temperature": 0.2,
                        "max_tokens": 1000,
                        "top_p": 0.9,
                        "frequency_penalty": 1.0,
                        "stream": False
                    },
                    timeout=20.0
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "content": data['choices'][0]['message']['content'],
                        "citations": data.get('citations', []),
                        "images": data.get('images', []),
                        "search_results": data.get('search_results', [])
                    }
                else:
                    print(f"Perplexity API Error: {response.status_code}")
                    return None

        except Exception as e:
            print(f"Perplexity API Error: {e}")
            return None

    def _build_context_from_curated(self, curated_results: List[Dict]) -> str:
        """Создаем контекст для API из кураторской базы"""

        if not curated_results:
            return "No specific priority restaurants for this query."

        context_parts = []
        for result in curated_results[:5]:  # Топ-5
            rest = result["restaurant"]
            context_parts.append(
                f"- {rest['name']} ({result['location']}): {rest.get('cuisine', 'N/A')}, "
                f"{rest.get('distinction', rest.get('philosophy', 'Acclaimed restaurant'))}"
            )

        return "\n".join(context_parts)

    def _enhance_query_for_api(
        self,
        query: str,
        location: Optional[str],
        context: str
    ) -> str:
        """Улучшаем запрос пользователя для API"""

        parts = []

        # Основной запрос
        parts.append(query)

        # Добавляем локацию если не упомянута
        if location:
            if location.lower() not in query.lower():
                parts.append(f"in {location} area, Bali")
        elif "bali" not in query.lower():
            parts.append("in Bali, Indonesia")

        # Если в контексте есть рестораны - просим обновить их данные
        if context and "No specific priority" not in context:
            parts.append(
                "\nProvide CURRENT information (2024-2025) for these restaurants: "
                "opening hours, prices, booking details, recent changes."
            )

        # Всегда просим практическую информацию
        parts.append(
            "\nInclude: exact address, contact info, current prices, "
            "opening hours, reservation requirements."
        )

        return " ".join(parts)

    def _merge_results(
        self,
        curated_results: List[Dict],
        api_results: Optional[Dict],
        original_query: str
    ) -> Dict:
        """Объединяем результаты из базы и API"""

        response = {
            "query": original_query,
            "curated_restaurants": [],
            "api_content": None,
            "sources": [],
            "images": []
        }

        # Добавляем кураторские результаты (ВСЕ!)
        if curated_results:
            response["curated_restaurants"] = [
                {
                    "name": r["restaurant"]["name"],
                    "location": r["location"],
                    "cuisine_ru": r["restaurant"].get("cuisine_ru"),  # Русская версия
                    "vibe_ru": r["restaurant"].get("vibe_ru"),  # Русская версия
                    "instagram_link": r["restaurant"].get("instagram_link"),  # Instagram ссылка
                    "price_range": r["restaurant"].get("price_range"),
                    "relevance": r["relevance_score"]
                }
                for r in curated_results  # Показываем ВСЕ результаты
            ]

        # Добавляем результаты API
        if api_results:
            response["api_content"] = api_results["content"]
            response["sources"] = api_results.get("citations", [])
            response["images"] = api_results.get("images", [])

        return response

    def format_telegram_response(self, results: Dict) -> str:
        """Форматируем финальный ответ для Telegram"""

        message_parts = []

        # Если есть кураторские рестораны - показываем ВСЕ!
        if results["curated_restaurants"]:
            message_parts.append("🌟 **Проверенные рестораны:**\n")

            for i, rest in enumerate(results["curated_restaurants"], 1):  # ВСЕ рестораны
                message_parts.append(f"**{i}. {rest['name']}** ({rest['location'].title()})")

                if rest.get('cuisine'):
                    message_parts.append(f"└ {rest['cuisine']}")

                if rest.get('vibe'):
                    message_parts.append(f"└ {rest['vibe']}")

                if rest.get('price_range'):
                    message_parts.append(f"└ 💰 {rest['price_range']}")

                message_parts.append("")  # Пустая строка

        # Добавляем контент от API (актуальные данные)
        if results["api_content"]:
            if results["curated_restaurants"]:
                message_parts.append("📍 **Актуальная информация:**\n")
            message_parts.append(results["api_content"])
            message_parts.append("")

        # Источники
        if results["sources"]:
            message_parts.append("📚 **Источники:**")
            for i, source in enumerate(results["sources"][:3], 1):
                message_parts.append(f"{i}. {source}")

        return "\n".join(message_parts)