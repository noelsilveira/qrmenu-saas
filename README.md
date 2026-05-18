# QR Menu SaaS Platform v2.0

## WhatsApp Acceptance • In-House Delivery • 3rd-Party Fleet • Driver App • Reconciliation

### Quick Start

```bash
# 1. Clone and setup
cd qrmenu_saas
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Copy environment
cp .env.example .env
# Edit .env with your credentials

# 3. Run with Docker Compose
docker-compose up -d

# 4. Run migrations
alembic upgrade head

# 5. Start development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Project Structure

```
qrmenu_saas/
├── app/
│   ├── api/v1/endpoints/      # REST API endpoints
│   ├── core/                  # Config, auth, middleware
│   ├── db/                    # Database session, base class
│   ├── models/                # SQLAlchemy ORM models
│   ├── schemas/               # Pydantic request/response models
│   ├── services/              # Business logic
│   │   ├── delivery/          # Zone, pricing, assignment, tracking
│   │   ├── whatsapp/            # Acceptance, notifications, analytics
│   │   └── third_party/         # Talabat, Zomato, Jahez adapters
│   ├── tasks/                 # Celery background jobs
│   ├── utils/                 # Helpers, validators
│   └── websocket/             # Socket.IO real-time manager
├── alembic/                   # Database migrations
├── tests/                     # Pytest test suite
├── docker/                    # Docker configurations
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

### Key Features

- **Multi-Tenant**: Schema-per-tenant PostgreSQL with Row-Level Security
- **WhatsApp Acceptance**: Interactive buttons for merchant order review
- **Delivery Zones**: GeoJSON polygon editor with distance-based pricing
- **Driver App**: React Native with GPS tracking, proof of delivery, earnings
- **3rd Party**: Talabat, Zomato, Jahez adapters with fallback orchestration
- **Reconciliation**: Auto-match orders with payouts, variance detection
- **Real-Time**: WebSocket KDS, driver tracking, customer live map
- **Smart Algorithms**: ETA prediction, route optimization (OR-Tools), demand forecasting

### API Documentation

Once running, visit: `http://localhost:8000/api/v1/docs`

### WebSocket Endpoints

- `/ws/kds?merchant_id={id}` — Kitchen Display System
- `/ws/tracking?order_id={id}` — Customer delivery tracking
- `/ws/driver?driver_id={id}` — Driver assignment notifications
- `/ws/fleet?merchant_id={id}` — Fleet management live map

### Celery Tasks

- `check_timeouts` — Every 60s, auto-accept/decline expired orders
- `archive_locations` — Hourly, compress old GPS data
- `run_nightly` — Daily 2 AM, reconciliation engine

### Environment Variables

See `.env.example` for all required configuration.

---
*Built with FastAPI, PostgreSQL, Redis, TimescaleDB, Socket.IO, Celery*
