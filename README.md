# Solo RPG Platform

A web application for running old-school tabletop RPGs as solo experiences with Claude as the Dungeon Master. The system uses RAG to ensure the LLM adheres closely to the source material from uploaded PDF rulebooks.

## Features

- **AI Dungeon Master**: Claude runs your solo adventures, handling narrative, NPCs, and combat
- **B/X D&D Support**: Full support for Basic/Expert D&D (1981) rules
- **RAG-Enhanced Rule Adherence**: Upload your PDF rulebooks for accurate rule enforcement
- **Character Management**: Create and manage characters with the classic race-as-class system
- **Real-time Sessions**: WebSocket-based streaming for immersive gameplay
- **Combat Tracking**: THAC0, initiative, morale checks, and more

## Tech Stack

- **Frontend**: React 18, TypeScript, Vite, Zustand, TanStack Query, Tailwind CSS
- **Backend**: FastAPI, Python, SQLAlchemy, Alembic
- **Database**: PostgreSQL with pgvector for embeddings
- **LLM**: Claude API with streaming
- **Real-time**: Socket.IO

## Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 15+ with pgvector extension
- Anthropic API key
- OpenAI API key (for embeddings)

## Setup

### Database

```bash
# Create database
createdb solo_rpg

# Enable pgvector
psql solo_rpg -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:application --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

## Usage

1. **Upload Rulebooks**: Go to Sourcebooks and upload your B/X D&D PDF rulebooks
2. **Create Character**: Use the character creation wizard to roll abilities, choose class, and buy equipment
3. **Start Campaign**: Create a new campaign and begin a session
4. **Play**: Interact with the AI Dungeon Master through natural language

## Project Structure

```
solo-rpg-platform/
├── backend/
│   ├── alembic/              # Database migrations
│   ├── app/
│   │   ├── core/             # Database and security
│   │   ├── domains/          # Feature modules
│   │   │   ├── campaigns/
│   │   │   ├── characters/
│   │   │   ├── combat/
│   │   │   ├── npcs/
│   │   │   ├── sessions/
│   │   │   └── sourcebooks/
│   │   ├── llm/              # Claude integration
│   │   │   ├── prompts/
│   │   │   └── tools/
│   │   └── rag/              # PDF processing & retrieval
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── components/
    │   ├── game-systems/     # Modular RPG system support
    │   │   ├── bx-dnd/       # B/X D&D module
    │   │   ├── registry/
    │   │   └── types/
    │   ├── hooks/
    │   ├── pages/
    │   ├── services/
    │   └── stores/
    └── package.json
```

## B/X D&D Mechanics

The platform implements core B/X D&D (1981) mechanics:

- **Race-as-Class**: Fighter, Cleric, Magic-User, Thief, Elf, Dwarf, Halfling
- **Descending AC**: AC 9 (unarmored) to AC -3 (best)
- **THAC0**: "To Hit Armor Class 0" combat system
- **Saving Throws**: Death Ray, Wands, Paralysis, Breath, Spells
- **XP for Gold**: Primary experience source
- **Morale & Reaction Rolls**: 2d6 based NPC behavior

## API Endpoints

### Characters
- `POST /api/v1/characters` - Create character
- `GET /api/v1/characters/{id}` - Get character
- `POST /api/v1/characters/{id}/level-up` - Level up

### Sessions
- `POST /api/v1/sessions` - Start session
- `WS /socket.io` - Real-time game WebSocket

### Sourcebooks
- `POST /api/v1/sourcebooks/upload` - Upload PDF
- `POST /api/v1/sourcebooks/query` - RAG query

## License

MIT
