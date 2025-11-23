"""
Smart Spa Search для Бали
Поиск спа-центров в Airtable
"""

from pyairtable import Api
import logging

logger = logging.getLogger(__name__)


class SmartSpaBot:
    def __init__(self, airtable_token: str, airtable_base_id: str, spa_table_name: str):
        """Инициализация бота для поиска спа-центров"""
        self.airtable_api = Api(airtable_token)
        self.spa_table = self.airtable_api.table(airtable_base_id, spa_table_name)
        self.spas_db = {}
        self._load_spas_from_airtable()
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


    def _load_spas_from_airtable(self):
        """Загружает спа-центры из Airtable"""
        try:
            records = self.spa_table.all()
            db = {}

            for record in records:
                fields = record['fields']

                area_raw = fields.get('area', 'unknown')
                area = self._normalize_area(area_raw)
                if area not in db:
                    db[area] = []

                spa = {
                    "name": fields.get('spa_name_en', 'Unknown'),
                    "name_ru": fields.get('spa_name_ru', ''),
                    "category": fields.get('category_en', ''),
                    "category_ru": fields.get('category_ru', ''),
                    "massage_type_ru": fields.get('massage_type_ru', ''),
                    "vibe_ru": fields.get('vibe_short_ru', ''),
                    "awards_ru": fields.get('awards_ru', ''),
                    "price_level": fields.get('price_level', ''),
                    "prestige_tier": fields.get('prestige_tier', ''),
                    "instagram_link": fields.get('instagram_link', ''),
                    "phone": fields.get('phone', '')
                }

                db[area].append(spa)

            self.spas_db = db
            logger.info(f"✅ Loaded {sum(len(spas) for spas in db.values())} spa/shopping/art places from Airtable")

        except Exception as e:
            logger.error(f"❌ Error loading spa places from Airtable: {e}")
            self.spas_db = {}

    async def search_spas(self, query: str, location: str = None) -> dict:
        """
        Поиск спа-центров в Airtable

        Args:
            query: Текстовый запрос пользователя
            location: Локация (ubud, canggu, etc.)

        Returns:
            dict с результатами поиска
        """
        results = []

        # Если указана локация, ищем только там
        if location:
            spas = self.spas_db.get(location, [])
            for spa in spas:
                results.append({
                    "spa": spa,
                    "location": location.capitalize(),
                    "relevance_score": 1.0
                })
        else:
            # Ищем во всех локациях
            for loc, spas in self.spas_db.items():
                for spa in spas:
                    results.append({
                        "spa": spa,
                        "location": loc.capitalize(),
                        "relevance_score": 1.0
                    })

        # Форматируем результаты
        return {
            "query": query,
            "curated_spas": [
                {
                    "name": r["spa"]["name"],
                    "name_ru": r["spa"].get("name_ru"),
                    "location": r["location"],
                    "category_ru": r["spa"].get("category_ru"),
                    "massage_type_ru": r["spa"].get("massage_type_ru"),
                    "vibe_ru": r["spa"].get("vibe_ru"),
                    "awards_ru": r["spa"].get("awards_ru"),
                    "price_level": r["spa"].get("price_level"),
                    "prestige_tier": r["spa"].get("prestige_tier"),
                    "instagram_link": r["spa"].get("instagram_link"),
                    "phone": r["spa"].get("phone"),
                    "relevance": r["relevance_score"]
                }
                for r in results
            ]
        }