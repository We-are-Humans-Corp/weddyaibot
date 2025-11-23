"""
Smart Breakfast/Lunch Search для Бали
Поиск кафе для завтраков и ланчей в Airtable
"""

from pyairtable import Api
import logging

logger = logging.getLogger(__name__)


class SmartBreakfastBot:
    def __init__(self, airtable_token: str, airtable_base_id: str, breakfast_table_name: str):
        """Инициализация бота для поиска кафе для завтраков"""
        self.airtable_api = Api(airtable_token)
        self.breakfast_table = self.airtable_api.table(airtable_base_id, breakfast_table_name)
        self.cafes_db = {}
        self._load_cafes_from_airtable()
    def _normalize_area(self, area: str) -> str:
        """Нормализует название района к стандартному виду"""
        area_lower = area.lower()
        if any(x in area_lower for x in ['canggu', 'berawa', 'pererenan']):
            return 'canggu'
        elif any(x in area_lower for x in ['uluwatu', 'bingin']):
            return 'uluwatu'
        elif any(x in area_lower for x in ['seminyak', 'kerobokan']):
            return 'seminyak'
        elif 'ubud' in area_lower:
            return 'ubud'
        else:
            return area_lower


    def _load_cafes_from_airtable(self):
        """Загружает кафе из Airtable"""
        try:
            records = self.breakfast_table.all()
            db = {}

            for record in records:
                fields = record['fields']

                area_raw = fields.get('area', 'unknown')
                area = self._normalize_area(area_raw)
                if area not in db:
                    db[area] = []

                cafe = {
                    "name": fields.get('restaurant_name_en', 'Unknown'),
                    "name_ru": fields.get('restaurant_name_ru', ''),
                    "category": fields.get('category_en', ''),
                    "category_ru": fields.get('category_ru', ''),
                    "cuisine_ru": fields.get('cuisine_style_ru', ''),
                    "vibe_ru": fields.get('vibe_short_ru', ''),
                    "awards_ru": fields.get('awards_ru', ''),
                    "price_level": fields.get('price_level', ''),
                    "prestige_tier": fields.get('prestige_tier', ''),
                    "instagram_link": fields.get('instagram_link', ''),
                    "phone": fields.get('phone', '')
                }

                db[area].append(cafe)

            self.cafes_db = db
            logger.info(f"✅ Loaded {sum(len(cafes) for cafes in db.values())} breakfast cafes from Airtable")

        except Exception as e:
            logger.error(f"❌ Error loading breakfast cafes from Airtable: {e}")
            self.cafes_db = {}

    async def search_cafes(self, query: str, location: str = None) -> dict:
        """
        Поиск кафе для завтраков в Airtable

        Args:
            query: Текстовый запрос пользователя
            location: Локация (ubud, canggu, etc.)

        Returns:
            dict с результатами поиска
        """
        results = []

        # Если указана локация, ищем только там
        if location:
            cafes = self.cafes_db.get(location, [])
            for cafe in cafes:
                results.append({
                    "cafe": cafe,
                    "location": location.capitalize(),
                    "relevance_score": 1.0
                })
        else:
            # Ищем во всех локациях
            for loc, cafes in self.cafes_db.items():
                for cafe in cafes:
                    results.append({
                        "cafe": cafe,
                        "location": loc.capitalize(),
                        "relevance_score": 1.0
                    })

        # Форматируем результаты
        return {
            "query": query,
            "curated_cafes": [
                {
                    "name": r["cafe"]["name"],
                    "name_ru": r["cafe"].get("name_ru"),
                    "location": r["location"],
                    "category_ru": r["cafe"].get("category_ru"),
                    "cuisine_ru": r["cafe"].get("cuisine_ru"),
                    "vibe_ru": r["cafe"].get("vibe_ru"),
                    "awards_ru": r["cafe"].get("awards_ru"),
                    "price_level": r["cafe"].get("price_level"),
                    "prestige_tier": r["cafe"].get("prestige_tier"),
                    "instagram_link": r["cafe"].get("instagram_link"),
                    "phone": r["cafe"].get("phone"),
                    "relevance": r["relevance_score"]
                }
                for r in results
            ]
        }