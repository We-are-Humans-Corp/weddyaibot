"""
Smart Art Search для Бали
Поиск арт-галерей в Airtable
"""

from pyairtable import Api
import logging

logger = logging.getLogger(__name__)


class SmartArtBot:
    def __init__(self, airtable_token: str, airtable_base_id: str, art_table_name: str):
        """Инициализация бота для поиска арт-галерей"""
        self.airtable_api = Api(airtable_token)
        self.art_table = self.airtable_api.table(airtable_base_id, art_table_name)
        self.art_db = {}
        self._load_art_from_airtable()
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


    def _load_art_from_airtable(self):
        """Загружает арт-галереи из Airtable"""
        try:
            records = self.art_table.all()
            db = {}

            for record in records:
                fields = record['fields']

                area_raw = fields.get('area', 'unknown')
                area = self._normalize_area(area_raw)
                if area not in db:
                    db[area] = []

                art = {
                    "name": fields.get('art_name_en', 'Unknown'),
                    "name_ru": fields.get('art_name_ru', ''),
                    "category": fields.get('category_en', ''),
                    "category_ru": fields.get('category_ru', ''),
                    "specialty_ru": fields.get('specialty_ru', ''),
                    "vibe_ru": fields.get('vibe_short_ru', ''),
                    "price_level": fields.get('price_level', ''),
                    "instagram_link": fields.get('instagram_link', ''),
                    "phone": fields.get('phone', '')
                }

                db[area].append(art)

            self.art_db = db
            logger.info(f"✅ Loaded {sum(len(art) for art in db.values())} art places from Airtable")

        except Exception as e:
            logger.error(f"❌ Error loading art places from Airtable: {e}")
            self.art_db = {}

    async def search_art(self, query: str, location: str = None) -> dict:
        """
        Поиск арт-галерей в Airtable

        Args:
            query: Текстовый запрос пользователя
            location: Локация (ubud, canggu, etc.)

        Returns:
            dict с результатами поиска
        """
        results = []

        # Если указана локация, ищем только там
        if location:
            art = self.art_db.get(location, [])
            for item in art:
                results.append({
                    "art": item,
                    "location": location.capitalize(),
                    "relevance_score": 1.0
                })
        else:
            # Ищем во всех локациях
            for loc, art in self.art_db.items():
                for item in art:
                    results.append({
                        "art": item,
                        "location": loc.capitalize(),
                        "relevance_score": 1.0
                    })

        # Форматируем результаты
        return {
            "query": query,
            "curated_art": [
                {
                    "name": r["art"]["name"],
                    "name_ru": r["art"].get("name_ru"),
                    "location": r["location"],
                    "category_ru": r["art"].get("category_ru"),
                    "specialty_ru": r["art"].get("specialty_ru"),
                    "vibe_ru": r["art"].get("vibe_ru"),
                    "price_level": r["art"].get("price_level"),
                    "instagram_link": r["art"].get("instagram_link"),
                    "phone": r["art"].get("phone"),
                    "relevance": r["relevance_score"]
                }
                for r in results
            ]
        }