"""
Smart Shopping Search для Бали
Поиск магазинов в Airtable
"""

from pyairtable import Api
import logging

logger = logging.getLogger(__name__)


class SmartShoppingBot:
    def __init__(self, airtable_token: str, airtable_base_id: str, shopping_table_name: str):
        """Инициализация бота для поиска магазинов"""
        self.airtable_api = Api(airtable_token)
        self.shopping_table = self.airtable_api.table(airtable_base_id, shopping_table_name)
        self.shops_db = {}
        self._load_shops_from_airtable()
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


    def _load_shops_from_airtable(self):
        """Загружает магазины из Airtable"""
        try:
            records = self.shopping_table.all()
            db = {}

            for record in records:
                fields = record['fields']

                area_raw = fields.get('area', 'unknown')
                area = self._normalize_area(area_raw)
                if area not in db:
                    db[area] = []

                shop = {
                    "name": fields.get('shop_name_en', 'Unknown'),
                    "name_ru": fields.get('shop_name_ru', ''),
                    "category": fields.get('category_en', ''),
                    "category_ru": fields.get('category_ru', ''),
                    "specialty_ru": fields.get('specialty_ru', ''),
                    "vibe_ru": fields.get('vibe_short_ru', ''),
                    "price_level": fields.get('price_level', ''),
                    "instagram_link": fields.get('instagram_link', ''),
                    "phone": fields.get('phone', '')
                }

                db[area].append(shop)

            self.shops_db = db
            logger.info(f"✅ Loaded {sum(len(shops) for shops in db.values())} shopping places from Airtable")

        except Exception as e:
            logger.error(f"❌ Error loading shopping places from Airtable: {e}")
            self.shops_db = {}

    async def search_shops(self, query: str, location: str = None) -> dict:
        """
        Поиск магазинов в Airtable

        Args:
            query: Текстовый запрос пользователя
            location: Локация (ubud, canggu, etc.)

        Returns:
            dict с результатами поиска
        """
        results = []

        # Если указана локация, ищем только там
        if location:
            shops = self.shops_db.get(location, [])
            for shop in shops:
                results.append({
                    "shop": shop,
                    "location": location.capitalize(),
                    "relevance_score": 1.0
                })
        else:
            # Ищем во всех локациях
            for loc, shops in self.shops_db.items():
                for shop in shops:
                    results.append({
                        "shop": shop,
                        "location": loc.capitalize(),
                        "relevance_score": 1.0
                    })

        # Форматируем результаты
        return {
            "query": query,
            "curated_shops": [
                {
                    "name": r["shop"]["name"],
                    "name_ru": r["shop"].get("name_ru"),
                    "location": r["location"],
                    "category_ru": r["shop"].get("category_ru"),
                    "specialty_ru": r["shop"].get("specialty_ru"),
                    "vibe_ru": r["shop"].get("vibe_ru"),
                    "price_level": r["shop"].get("price_level"),
                    "instagram_link": r["shop"].get("instagram_link"),
                    "phone": r["shop"].get("phone"),
                    "relevance": r["relevance_score"]
                }
                for r in results
            ]
        }