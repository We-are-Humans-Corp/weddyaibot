"""
Smart Hotels Search для Бали
Поиск отелей в Airtable
"""

from pyairtable import Api
import logging

logger = logging.getLogger(__name__)


class SmartHotelsBot:
    def __init__(self, airtable_token: str, airtable_base_id: str, hotels_table_name: str):
        """Инициализация бота для поиска отелей"""
        self.airtable_api = Api(airtable_token)
        self.hotels_table = self.airtable_api.table(airtable_base_id, hotels_table_name)
        self.hotels_db = {}
        self._load_hotels_from_airtable()
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


    def _load_hotels_from_airtable(self):
        """Загружает отели из Airtable"""
        try:
            records = self.hotels_table.all()
            db = {}

            for record in records:
                fields = record['fields']

                area_raw = fields.get('area', 'unknown')
                area = self._normalize_area(area_raw)
                if area not in db:
                    db[area] = []

                hotel = {
                    "name": fields.get('hotel_name_en', 'Unknown'),
                    "name_ru": fields.get('hotel_name_ru', ''),
                    "type": fields.get('type_en', ''),
                    "type_ru": fields.get('type_ru', ''),
                    "style": fields.get('style_en', ''),
                    "style_ru": fields.get('style_ru', ''),
                    "vibe": fields.get('vibe_short_en', ''),
                    "vibe_ru": fields.get('vibe_short_ru', ''),
                    "price_level": fields.get('price_level', ''),
                    "phone": fields.get('phone', ''),
                    "instagram_handle": fields.get('instagram_handle', ''),
                    "booking_link": fields.get('booking_link', ''),
                    "year_opened": fields.get('year_opened', ''),
                    "rating": fields.get('rating', ''),
                    "description_ru_short": fields.get('description_ru_short', '')
                }

                db[area].append(hotel)

            self.hotels_db = db
            logger.info(f"✅ Loaded {sum(len(hotels) for hotels in db.values())} hotels from Airtable")

        except Exception as e:
            logger.error(f"❌ Error loading hotels from Airtable: {e}")
            self.hotels_db = {}

    async def search_hotels(self, query: str, location: str = None) -> dict:
        """
        Поиск отелей в Airtable

        Args:
            query: Текстовый запрос пользователя
            location: Локация (ubud, canggu, etc.)

        Returns:
            dict с результатами поиска
        """
        results = []

        # Если указана локация, ищем только там
        if location:
            hotels = self.hotels_db.get(location, [])
            for hotel in hotels:
                results.append({
                    "hotel": hotel,
                    "location": location.capitalize(),
                    "relevance_score": 1.0
                })
        else:
            # Ищем во всех локациях
            for loc, hotels in self.hotels_db.items():
                for hotel in hotels:
                    results.append({
                        "hotel": hotel,
                        "location": loc.capitalize(),
                        "relevance_score": 1.0
                    })

        # Форматируем результаты
        return {
            "query": query,
            "curated_hotels": [
                {
                    "name": r["hotel"]["name"],
                    "name_ru": r["hotel"].get("name_ru"),
                    "location": r["location"],
                    "type_ru": r["hotel"].get("type_ru"),
                    "style_ru": r["hotel"].get("style_ru"),
                    "vibe_ru": r["hotel"].get("vibe_ru"),
                    "price_level": r["hotel"].get("price_level"),
                    "phone": r["hotel"].get("phone"),
                    "instagram_handle": r["hotel"].get("instagram_handle"),
                    "booking_link": r["hotel"].get("booking_link"),
                    "year_opened": r["hotel"].get("year_opened"),
                    "rating": r["hotel"].get("rating"),
                    "description_ru_short": r["hotel"].get("description_ru_short"),
                    "relevance": r["relevance_score"]
                }
                for r in results
            ]
        }