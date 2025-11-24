# Swappo Matchmaking Service

## Overview

The Swappo Matchmaking Service is a RESTful microservice responsible for managing trade offers between users in the Swappo platform. This service handles the creation, tracking, and lifecycle management of item swap proposals, supporting various trade configurations including:

- **Single item for single item trades** (1:1)
- **Multiple items for single item trades** (N:1)
- **Multiple items for multiple items trades** (N:M)

The service is built with FastAPI and PostgreSQL, following the same architectural patterns as the Auth and Catalog services.

## Features

### Trade Offer Management
- Create trade offers with offered and requested items
- View trade offer details
- List trade offers with filtering options
- Update trade offer status (accept, reject, cancel, complete)
- Delete pending trade offers

### User-Centric Views
- Get received offers for a user
- Get sent offers for a user
- Filter offers by status and role (proposer/receiver)
- Pagination support for large offer lists

### Item Tracking
- Find all trade offers involving a specific item
- Prevent duplicate items in offers
- Validate item ownership logic

### Statistics
- User-level trade statistics
- Track pending, accepted, rejected, and completed offers

## Architecture

```
Swappo-Matchmaking/
├── main.py              # FastAPI application and endpoints
├── models.py            # Pydantic and SQLAlchemy models
├── database.py          # Database connection and session management
├── requirements.txt     # Python dependencies
├── Dockerfile          # Container configuration
├── docker-compose.yml  # Multi-container orchestration
├── api_schema.json     # OpenAPI specification
└── README.md           # This file
```

## Data Models

### TradeOffer

The core entity representing a swap proposal between two users.

**Database Schema:**
```sql
CREATE TABLE trade_offers (
    id SERIAL PRIMARY KEY,
    proposer_id VARCHAR(100) NOT NULL,
    receiver_id VARCHAR(100) NOT NULL,
    offered_item_ids INTEGER[],
    requested_item_ids INTEGER[],
    status VARCHAR(20) DEFAULT 'pending',
    message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    responded_at TIMESTAMP WITH TIME ZONE
);
```

**Status Flow:**
- `pending` → Initial state when offer is created
- `accepted` → Receiver accepts the offer
- `rejected` → Receiver rejects the offer
- `cancelled` → Proposer cancels the offer
- `completed` → Trade has been completed by both parties

## API Endpoints

### Health Check

#### `GET /`
Basic health check returning service information.

#### `GET /health`
Detailed health check with service status.

### Trade Offer Management

#### `POST /api/v1/offers`
Create a new trade offer.

**Request Body:**
```json
{
  "proposer_id": "user123",
  "receiver_id": "user456",
  "offered_item_ids": [1, 2],
  "requested_item_ids": [3],
  "message": "I'd love to trade my items for yours!"
}
```

**Response:** `201 Created`
```json
{
  "id": 1,
  "proposer_id": "user123",
  "receiver_id": "user456",
  "offered_item_ids": [1, 2],
  "requested_item_ids": [3],
  "message": "I'd love to trade my items for yours!",
  "status": "pending",
  "created_at": "2025-11-24T10:30:00Z",
  "updated_at": "2025-11-24T10:30:00Z",
  "responded_at": null
}
```

**Validations:**
- Proposer and receiver must be different users
- No duplicate items in offered or requested lists
- No overlap between offered and requested items

---

#### `GET /api/v1/offers/{offer_id}`
Get details of a specific trade offer.

**Response:** `200 OK`

---

#### `GET /api/v1/offers`
List trade offers with filtering options.

**Query Parameters:**
- `user_id` (required): User ID to filter by
- `status` (optional): Filter by status (pending, accepted, etc.)
- `as_proposer` (optional): Filter offers where user is proposer
- `as_receiver` (optional): Filter offers where user is receiver
- `limit` (optional, default: 20): Number of results
- `offset` (optional, default: 0): Pagination offset

**Response:** `200 OK` - Array of trade offers

---

#### `PATCH /api/v1/offers/{offer_id}`
Update the status of a trade offer.

**Query Parameters:**
- `user_id` (required): User performing the action

**Request Body:**
```json
{
  "status": "accepted"
}
```

**Authorization Rules:**
- **Proposer** can:
  - Cancel pending offers
  - Mark accepted offers as completed
- **Receiver** can:
  - Accept or reject pending offers
  - Mark accepted offers as completed

**Response:** `200 OK`

---

#### `DELETE /api/v1/offers/{offer_id}`
Delete a trade offer (only pending offers by proposer).

**Query Parameters:**
- `user_id` (required): User performing the action

**Response:** `204 No Content`

---

### User-Specific Endpoints

#### `GET /api/v1/offers/received/{user_id}`
Get all trade offers received by a user.

**Query Parameters:**
- `status` (optional): Filter by status
- `limit` (optional, default: 20)
- `offset` (optional, default: 0)

---

#### `GET /api/v1/offers/sent/{user_id}`
Get all trade offers sent by a user.

**Query Parameters:**
- `status` (optional): Filter by status
- `limit` (optional, default: 20)
- `offset` (optional, default: 0)

---

### Statistics

#### `GET /api/v1/statistics/{user_id}`
Get statistics about a user's trade offers.

**Response:** `200 OK`
```json
{
  "total_offers": 25,
  "pending_offers": 5,
  "accepted_offers": 10,
  "rejected_offers": 8,
  "completed_offers": 2
}
```

---

### Item Tracking

#### `GET /api/v1/offers/by-item/{item_id}`
Get all trade offers involving a specific item.

**Query Parameters:**
- `status` (optional): Filter by status

**Response:** `200 OK` - Array of trade offers

---

## Running the Service

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)
- PostgreSQL 15+ (for local development)

### Using Docker Compose (Recommended)

1. **Start the service:**
```powershell
cd Swappo-Matchmaking
docker-compose up -d
```

2. **Check service health:**
```powershell
curl http://localhost:8002/health
```

3. **View logs:**
```powershell
docker-compose logs -f matchmaking_service
```

4. **Stop the service:**
```powershell
docker-compose down
```

### Local Development

1. **Create virtual environment:**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

2. **Install dependencies:**
```powershell
pip install -r requirements.txt
```

3. **Set environment variables:**
```powershell
$env:DATABASE_URL = "postgresql://swappo_user:swappo_pass@localhost:5432/swappo_matchmaking"
```

4. **Start PostgreSQL:**
```powershell
docker run -d --name matchmaking-db `
  -e POSTGRES_DB=swappo_matchmaking `
  -e POSTGRES_USER=swappo_user `
  -e POSTGRES_PASSWORD=swappo_pass `
  -p 5432:5432 `
  postgres:15-alpine
```

5. **Run the application:**
```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8002
```

6. **Access API documentation:**
- Swagger UI: http://localhost:8002/docs
- ReDoc: http://localhost:8002/redoc

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://swappo_user:swappo_pass@localhost:5432/swappo_matchmaking` |
| `SQL_ECHO` | Enable SQL query logging | `false` |

### Database Configuration

The service uses SQLAlchemy with connection pooling:
- Pool size: 10 connections
- Max overflow: 20 connections
- Pool pre-ping: Enabled (verifies connections before use)

## Database Schema

The service automatically creates the required tables on startup using SQLAlchemy migrations. The main table is `trade_offers` with the following structure:

- **Primary Key:** `id` (auto-incrementing integer)
- **Indexes:** `proposer_id`, `receiver_id`, `status`
- **Array Fields:** `offered_item_ids`, `requested_item_ids` (PostgreSQL ARRAY type)
- **Timestamps:** Automatic `created_at` and `updated_at` management

## Integration with Other Services

### Auth Service
- User IDs (`proposer_id`, `receiver_id`) should be validated against the Auth service
- Authentication tokens should be verified before creating/updating offers

### Catalog Service
- Item IDs in trade offers reference items from the Catalog service
- Item ownership should be validated before accepting offers
- Item status should be updated to "swapped" when trade is completed

## Error Handling

The service uses standard HTTP status codes:

- `200 OK` - Successful GET/PATCH request
- `201 Created` - Successful POST request
- `204 No Content` - Successful DELETE request
- `400 Bad Request` - Invalid input or business logic violation
- `403 Forbidden` - User not authorized to perform action
- `404 Not Found` - Resource not found

**Error Response Format:**
```json
{
  "detail": "Error message describing what went wrong"
}
```

## Testing

### Manual Testing with curl

**Create a trade offer:**
```powershell
curl -X POST http://localhost:8002/api/v1/offers `
  -H "Content-Type: application/json" `
  -d '{
    "proposer_id": "user1",
    "receiver_id": "user2",
    "offered_item_ids": [1, 2],
    "requested_item_ids": [3],
    "message": "Great items!"
  }'
```

**List offers for a user:**
```powershell
curl "http://localhost:8002/api/v1/offers?user_id=user1&limit=10"
```

**Accept an offer:**
```powershell
curl -X PATCH "http://localhost:8002/api/v1/offers/1?user_id=user2" `
  -H "Content-Type: application/json" `
  -d '{"status": "accepted"}'
```

**Get user statistics:**
```powershell
curl http://localhost:8002/api/v1/statistics/user1
```

## Security Considerations

1. **Authentication:** Implement JWT token validation for all endpoints
2. **Authorization:** Verify user permissions before allowing operations
3. **Input Validation:** All inputs are validated using Pydantic models
4. **SQL Injection:** Protected by SQLAlchemy ORM parameterized queries
5. **CORS:** Configure appropriate origins for production deployment

## Performance Optimization

- Database connection pooling for efficient resource usage
- Indexed columns for fast queries (user IDs, status)
- Pagination support to limit response sizes
- Pre-ping connections to avoid stale connection errors

## Monitoring and Logging

- Health check endpoints for container orchestration
- Structured logging (configure as needed)
- Database query logging (enable with `SQL_ECHO=true`)

## Future Enhancements

- [ ] Real-time notifications for new offers (WebSocket/SSE)
- [ ] Trade offer expiration (TTL)
- [ ] Counter-offer functionality
- [ ] Trade history and audit trail
- [ ] Reputation system integration
- [ ] Automated item validation with Catalog service
- [ ] Rate limiting per user
- [ ] Advanced search and filtering
- [ ] Trade recommendation engine

## Troubleshooting

### Database Connection Issues
```powershell
# Check if PostgreSQL is running
docker ps | Select-String "swappo_matchmaking_db"

# Check database logs
docker logs swappo_matchmaking_db
```

### Service Not Starting
```powershell
# Check service logs
docker logs swappo_matchmaking_service

# Verify database URL
docker exec swappo_matchmaking_service env | Select-String "DATABASE_URL"
```

### Port Already in Use
If port 8002 is already in use, modify `docker-compose.yml`:
```yaml
ports:
  - "8003:8000"  # Change external port
```

## Contributing

When contributing to this service, please:
1. Follow the existing code structure and patterns
2. Add appropriate validation and error handling
3. Update this README with new features
4. Test all endpoints thoroughly
5. Maintain consistency with Auth and Catalog services

## License

This service is part of the Swappo platform.

## Contact

For questions or issues, please refer to the main Swappo repository documentation.
