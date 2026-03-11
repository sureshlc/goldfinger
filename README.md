# Agent Goldfinger

A production feasibility analysis platform for Eagle Beverage, integrating with NetSuite ERP to provide real-time Bill of Materials (BOM) analysis, inventory tracking, and manufacturing capacity planning.

## Tech Stack

| Layer      | Technology                                      |
| ---------- | ----------------------------------------------- |
| Frontend   | Next.js 15 (Turbopack), React 19, TypeScript 5, Tailwind CSS 4 |
| Backend    | FastAPI (Python 3.9+), Uvicorn ASGI              |
| Database   | PostgreSQL 14+ with SQLAlchemy 2.0 (async) + asyncpg |
| Auth       | JWT (HS256) with role-based access control        |
| ERP        | NetSuite REST API (OAuth 1.0a, SuiteQL)           |
| Migrations | Alembic                                           |

## Architecture

```
┌─────────────────┐       ┌──────────────────┐       ┌─────────────┐
│  Next.js 15     │──────▶│  FastAPI :8000    │──────▶│  PostgreSQL │
│  Frontend :3000 │◀──────│  REST API        │◀──────│  goldfinger │
└─────────────────┘       └────────┬─────────┘       └─────────────┘
                                   │
                                   ▼
                          ┌──────────────────┐
                          │  NetSuite ERP    │
                          │  (SuiteQL API)   │
                          └──────────────────┘
```

**Key architectural features:**
- **In-memory caching** — BOM & item details (1h TTL), inventory (5min TTL), configurable per-resource
- **Background log writer** — async queue drains request logs to PostgreSQL without blocking responses
- **Identifier resolution** — accepts both SKU and NetSuite internal ID for all item lookups
- **SuiteQL sanitization** — prevents injection in dynamically built NetSuite queries

## API Endpoints

Base URL: `/api/v1`

### Authentication (`/auth`)

| Method | Path             | Description                     | Auth     |
| ------ | ---------------- | ------------------------------- | -------- |
| POST   | `/auth/login`    | Login, returns JWT              | Public   |
| POST   | `/auth/logout`   | End session, blacklist token    | Bearer   |
| GET    | `/auth/me`       | Current user info               | Bearer   |
| PUT    | `/auth/profile`  | Update username / password      | Bearer   |

### Items (`/items`)

| Method | Path                       | Description                  | Auth   |
| ------ | -------------------------- | ---------------------------- | ------ |
| GET    | `/items/sku/{sku}`         | Item details by SKU          | Bearer |
| GET    | `/items/sku/{sku}/bom`     | Multi-level Bill of Materials | Bearer |

### Inventory (`/inventory`)

| Method | Path                          | Description                     | Auth   |
| ------ | ----------------------------- | ------------------------------- | ------ |
| GET    | `/inventory/{item_identifier}` | Inventory level (SKU or ID)    | Bearer |

Query params: `location_name` (optional)

### Production (`/production`)

| Method | Path                                    | Description                        | Auth   |
| ------ | --------------------------------------- | ---------------------------------- | ------ |
| GET    | `/production/feasibility/{identifier}`  | Full feasibility analysis          | Bearer |
| GET    | `/production/capacity/{identifier}`     | Max producible quantity            | Bearer |
| GET    | `/production/shortages/{identifier}`    | Component shortage report          | Bearer |
| GET    | `/production/cache/stats`               | Cache statistics                   | Admin  |
| POST   | `/production/cache/invalidate/{id}`     | Invalidate specific item cache     | Admin  |
| POST   | `/production/cache/clear`               | Clear all caches                   | Admin  |

Query params: `desired_quantity` (int), `location_name` (optional)

### Admin (`/admin`)

| Method | Path                     | Description                  | Auth  |
| ------ | ------------------------ | ---------------------------- | ----- |
| GET    | `/admin/users`           | List all users (paginated)   | Admin |
| POST   | `/admin/users`           | Create user                  | Admin |
| PUT    | `/admin/users/{id}`      | Update user                  | Admin |
| DELETE | `/admin/users/{id}`      | Delete user                  | Admin |
| GET    | `/admin/items`           | List items (search/paginate) | Admin |
| POST   | `/admin/items`           | Create item                  | Admin |
| PUT    | `/admin/items/{id}`      | Update item                  | Admin |
| DELETE | `/admin/items/{id}`      | Delete item                  | Admin |
| GET    | `/admin/audit-logs`      | Request logs (paginated)     | Admin |
| POST   | `/admin/reload-items`    | Reload item cache from DB    | Admin |

### Analytics (`/analytics`)

| Method | Path                     | Description                       | Auth   |
| ------ | ------------------------ | --------------------------------- | ------ |
| GET    | `/analytics/top-items`   | Most frequently analyzed items    | Bearer |

### Health

| Method | Path       | Description   |
| ------ | ---------- | ------------- |
| GET    | `/`        | Root check    |
| GET    | `/health`  | Health status |

## Environment Variables

### Backend (`Backend/.env`)

```env
# Application
APP_NAME="Production Agent API"
ENVIRONMENT=development          # development | production
DEBUG=true
API_VERSION=v1

# Server
HOST=127.0.0.1
PORT=8000

# Database
DATABASE_URL=postgresql+asyncpg://goldfinger:goldfinger@localhost:5432/goldfinger

# Security
SECRET_KEY=<generate-a-random-key>    # openssl rand -base64 32
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# NetSuite API (OAuth 1.0a)
NETSUITE_ACCOUNT_ID=<account-id>
NETSUITE_CONSUMER_KEY=<consumer-key>
NETSUITE_CONSUMER_SECRET=<consumer-secret>
NETSUITE_TOKEN_ID=<token-id>
NETSUITE_TOKEN_SECRET=<token-secret>
NETSUITE_BASE_URL=https://<account-id>.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql
NETSUITE_REALM=<account-id>

# CORS
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

### Frontend (`frontend/.env.local`)

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

## Database Setup

### 1. Create PostgreSQL user and database

```bash
psql -U postgres
```

```sql
CREATE USER goldfinger WITH PASSWORD 'goldfinger';
CREATE DATABASE goldfinger OWNER goldfinger;
GRANT ALL PRIVILEGES ON DATABASE goldfinger TO goldfinger;
\q
```

### 2. Run migrations

```bash
cd Backend
source .venv/bin/activate
alembic upgrade head
```

### 3. Seed users (optional)

The seed script creates 7 users including an admin account. Run it after migrations:

```bash
python -m app.database.seed   # if a seed script exists, or create users via admin API
```

### Database Schema

| Table          | Description                                    |
| -------------- | ---------------------------------------------- |
| `users`        | User accounts (email, username, role, etc.)    |
| `items`        | Product catalog (NetSuite ID, SKU, name)       |
| `sessions`     | Login sessions with duration tracking          |
| `request_logs` | Audit trail of all production analysis requests |

## User Credentials (Development)

| Email                        | Password     | Role  |
| ---------------------------- | ------------ | ----- |
| `admin@eaglebeverage.com`    | `admin1234`  | admin |
| Other seeded users           | `test1234`   | user  |

## Local Development Setup

### Prerequisites

- Python 3.9+
- Node.js 18+
- PostgreSQL 14+

### Backend

```bash
cd Backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env   # then edit with your values

# Run database migrations
alembic upgrade head

# Start server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
echo 'NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1' > .env.local

# Start dev server
npm run dev
```

The app will be available at `http://localhost:3000`.

## AWS Deployment

See the [`deploy/aws`](../../tree/deploy/aws) branch for full AWS deployment instructions covering:

- EC2 instance setup (Amazon Linux 2 / Ubuntu)
- PostgreSQL (RDS) provisioning
- Nginx reverse proxy configuration
- systemd service files for backend
- PM2 / standalone Next.js for frontend
- SSL/TLS with Let's Encrypt
- Environment variable management
- Security group configuration

## Project Structure

```
Agent Goldfinger/
├── Backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI entry point
│   │   ├── config.py               # Settings (pydantic-settings)
│   │   ├── background/             # Async DB log writer
│   │   ├── database/
│   │   │   ├── connection.py       # Async engine & session
│   │   │   ├── models.py           # SQLAlchemy ORM models
│   │   │   └── repositories/       # Data access layer
│   │   ├── routers/                # API route handlers
│   │   ├── services/               # Business logic & NetSuite integration
│   │   ├── models/                 # Pydantic schemas
│   │   ├── dependencies/           # Auth & DI
│   │   ├── middleware/             # Logging & security headers
│   │   └── utils/                  # Cache, auth, sanitization
│   ├── alembic/                    # Database migrations
│   └── requirements.txt
├── frontend/
│   ├── src/app/
│   │   ├── page.tsx                # Home (search + analytics)
│   │   ├── login/page.tsx          # Login
│   │   ├── item/[sku]/page.tsx     # Item details (BOM, inventory, production)
│   │   ├── profile/page.tsx        # User profile
│   │   ├── admin/page.tsx          # Admin dashboard
│   │   ├── components/             # Reusable UI components
│   │   ├── services/               # API client functions
│   │   └── contexts/               # React auth context
│   ├── package.json
│   └── tailwind.config.js
└── README.md
```

## License

Proprietary — Eagle Beverage. All rights reserved.
