# Swappo-Matchmaking

Trade offer microservice for the Swappo platform managing swap proposals between users with support for 1:1, N:1, and N:M item trades.

## Features

- **Trade Offer Lifecycle**: Create, accept, reject, cancel, complete offers
- **Multi-Item Support**: 1:1, N:1, N:M item trades
- **User Views**: Filter by sent/received, status, pagination
- **gRPC Integration**: Validate items via Catalog service
- **RabbitMQ Messaging**: Async notifications for status changes
- **Circuit Breaker**: Resilient Chat service integration
- **Statistics**: User trade metrics and analytics
- **Prometheus Metrics**: Built-in monitoring

## Quick Start

### Docker (Recommended)

```bash
docker-compose up -d
```

### Local Development

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Service info |
| GET | `/health` | Health check |
| POST | `/api/v1/offers` | Create trade offer |
| GET | `/api/v1/offers` | List offers (filterable) |
| GET | `/api/v1/offers/{id}` | Get offer details |
| PATCH | `/api/v1/offers/{id}` | Update offer status |
| DELETE | `/api/v1/offers/{id}` | Delete pending offer |
| GET | `/api/v1/offers/received/{user_id}` | Get received offers |
| GET | `/api/v1/offers/sent/{user_id}` | Get sent offers |
| GET | `/api/v1/offers/item/{item_id}` | Get offers for item |
| GET | `/api/v1/statistics/{user_id}` | Get user statistics |
| GET | `/metrics` | Prometheus metrics |

## Status Flow

`pending` → `accepted` / `rejected` / `cancelled` → `completed`

- **Proposer**: Can cancel pending, mark accepted as completed
- **Receiver**: Can accept/reject pending, mark accepted as completed

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | - | PostgreSQL connection string |
| `SQL_ECHO` | false | Enable SQL query logging |
| `NOTIFICATION_SERVICE_URL` | http://notifications_service:8000 | Notifications API URL |
| `CHAT_SERVICE_URL` | http://chat_service:8000 | Chat service API URL |
| `RABBITMQ_HOST` | rabbitmq | RabbitMQ host |
| `RABBITMQ_PORT` | 5672 | RabbitMQ port |
| `CATALOG_GRPC_HOST` | catalog_service | Catalog gRPC host |
| `CATALOG_GRPC_PORT` | 50051 | Catalog gRPC port |

## Service Integration

- **Catalog Service (gRPC)**: Validates item existence and ownership
- **Chat Service (HTTP)**: Creates chat rooms on offer acceptance (with circuit breaker)
- **Notification Service (RabbitMQ)**: Async notifications for status changes

## Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

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
