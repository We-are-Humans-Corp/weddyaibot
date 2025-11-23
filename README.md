# Weddy AI Bot

Telegram bot assistant for Fedor & Polina's wedding in Bali (08.01.2026)

## Features

- Guest registration with Airtable integration
- AI-powered wedding information assistant (Claude)
- Curated database of 128+ places in Bali:
  - Restaurants
  - Hotels
  - Yoga studios
  - Cafes
  - Spa
  - Shopping
  - Art venues
- Interactive map integration
- Smart search with Perplexity AI
- Conversation history/context memory

## Deployment

### Environment Variables

Create a `.env.wedding` file with:

```
WEDDING_BOT_TOKEN=your_telegram_bot_token
CLAUDE_API_KEY=your_claude_api_key
AIRTABLE_TOKEN=your_airtable_token
AIRTABLE_BASE_ID=your_base_id
AIRTABLE_TABLE_NAME=Wedding Guests
AIRTABLE_RESTAURANTS_TABLE=Restaurants
AIRTABLE_YOGA_TABLE=yoga_fitness_studios
AIRTABLE_HOTELS_TABLE=Hotels
AIRTABLE_BREAKFAST_TABLE=Breakfast/lunch
AIRTABLE_SPA_TABLE=Spa
AIRTABLE_SHOPPING_TABLE=Shopping
AIRTABLE_ART_TABLE=Art
PERPLEXITY_API_KEY=your_perplexity_key
```

### Run locally

```bash
pip install -r requirements.txt
python wedding_bot_v2.py
```

### Deploy to Render.com

1. Push code to GitHub
2. Create new Web Service on Render
3. Connect GitHub repository
4. Add environment variables
5. Deploy

## Commands

- `/start` - Main menu
- `/form` - Guest registration
- `/menu` - Browse places by category
- `/tips` - Useful Bali tips
- `/contacts` - Important contacts
- `/clear` - Clear conversation history
- `/help` - Help

## Admin Commands

- `/admin` - Admin panel
- `/stats` - Guest statistics
- `/export` - Export guests to CSV
- `/getguests` - List registered guests
- `/text2all <message>` - Broadcast to all users

## Tech Stack

- Python 3.13
- aiogram 3.15 (Telegram Bot API)
- Claude 3.5 Haiku (AI assistant)
- Perplexity AI (search)
- Airtable (database)
- Mapbox GL JS (interactive map)