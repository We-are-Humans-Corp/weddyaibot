"""
Smart Yoga & Fitness Search для Бали
Поиск студий йоги и фитнеса в Airtable
"""

from pyairtable import Api
import logging

logger = logging.getLogger(__name__)


class SmartYogaBot:
    def __init__(self, airtable_token: str, airtable_base_id: str, yoga_table_name: str):
        """Инициализация бота для поиска йога-студий"""
        self.airtable_api = Api(airtable_token)
        self.yoga_table = self.airtable_api.table(airtable_base_id, yoga_table_name)
        self.studios_db = {}
        self._load_studios_from_airtable()

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

    def _load_studios_from_airtable(self):
        """Загружает студии из Airtable"""
        try:
            records = self.yoga_table.all()
            db = {}

            for record in records:
                fields = record['fields']

                area_raw = fields.get('area', 'unknown')
                area = self._normalize_area(area_raw)
                if area not in db:
                    db[area] = []

                studio = {
                    "name": fields.get('studio_name_en', 'Unknown'),
                    "category": fields.get('category_en', ''),
                    "category_ru": fields.get('category_ru', ''),
                    "specialties": fields.get('specialties_en', ''),
                    "specialties_ru": fields.get('specialties_ru', ''),
                    "highlights": fields.get('highlights_en', ''),
                    "highlights_ru": fields.get('highlights_ru', ''),
                    "booking_type": fields.get('booking_type', ''),
                    "instagram_link": fields.get('instagram_link', ''),
                    "prestige_tier": fields.get('prestige_tier', ''),
                    "rating_stars": fields.get('rating_stars', '')
                }

                db[area].append(studio)

            self.studios_db = db
            logger.info(f"✅ Loaded {sum(len(studios) for studios in db.values())} yoga studios from Airtable")

        except Exception as e:
            logger.error(f"❌ Error loading yoga studios from Airtable: {e}")
            self.studios_db = {}

    async def search_studios(self, query: str, location: str = None) -> dict:
        """
        Поиск йога-студий в Airtable

        Args:
            query: Текстовый запрос пользователя
            location: Локация (ubud, canggu, etc.)

        Returns:
            dict с результатами поиска
        """
        results = []

        # Если указана локация, ищем только там
        if location:
            studios = self.studios_db.get(location, [])
            for studio in studios:
                results.append({
                    "studio": studio,
                    "location": location.capitalize(),
                    "relevance_score": 1.0
                })
        else:
            # Ищем во всех локациях
            for loc, studios in self.studios_db.items():
                for studio in studios:
                    results.append({
                        "studio": studio,
                        "location": loc.capitalize(),
                        "relevance_score": 1.0
                    })

        # Форматируем результаты
        return {
            "query": query,
            "curated_studios": [
                {
                    "name": r["studio"]["name"],
                    "location": r["location"],
                    "category_ru": r["studio"].get("category_ru"),
                    "specialties_ru": r["studio"].get("specialties_ru"),
                    "highlights_ru": r["studio"].get("highlights_ru"),
                    "booking_type": r["studio"].get("booking_type"),
                    "instagram_link": r["studio"].get("instagram_link"),
                    "prestige_tier": r["studio"].get("prestige_tier"),
                    "rating_stars": r["studio"].get("rating_stars"),
                    "relevance": r["relevance_score"]
                }
                for r in results
            ]
        }