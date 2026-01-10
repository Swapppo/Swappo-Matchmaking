"""
Prometheus metrics for Matchmaking Service
Tracks request latency, throughput, errors, and business metrics
"""

import time

from prometheus_client import Counter, Gauge, Histogram, Info

# ========================================
# HTTP Metrics
# ========================================

# Request counters
http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status_code"]
)

# Request duration histogram
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0),
)

# Error counter
http_errors_total = Counter(
    "http_errors_total", "Total HTTP errors", ["method", "endpoint", "error_type"]
)

# ========================================
# gRPC Metrics
# ========================================

# gRPC call counters
grpc_requests_total = Counter(
    "grpc_requests_total",
    "Total gRPC requests to catalog service",
    ["method", "status"],
)

# gRPC call duration
grpc_request_duration_seconds = Histogram(
    "grpc_request_duration_seconds",
    "gRPC request latency in seconds",
    ["method"],
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5),
)

# ========================================
# Circuit Breaker Metrics
# ========================================

# Circuit breaker state (0=closed, 1=open, 2=half-open)
circuit_breaker_state = Gauge(
    "circuit_breaker_state", "Circuit breaker current state", ["circuit_name"]
)

# Circuit breaker failures
circuit_breaker_failures_total = Counter(
    "circuit_breaker_failures_total", "Total circuit breaker failures", ["circuit_name"]
)

# ========================================
# Business Metrics
# ========================================

# Trade offers created
trade_offers_created_total = Counter(
    "trade_offers_created_total", "Total trade offers created"
)

# Trade offers by status
trade_offers_by_status = Gauge(
    "trade_offers_by_status", "Number of trade offers by status", ["status"]
)

# Match rate (percentage of accepted offers)
trade_offers_accepted_total = Counter(
    "trade_offers_accepted_total", "Total trade offers accepted"
)

trade_offers_rejected_total = Counter(
    "trade_offers_rejected_total", "Total trade offers rejected"
)

# Active users gauge
active_users = Gauge("active_users", "Number of users with active trade offers")

# ========================================
# Retry Metrics
# ========================================

# Retry attempts
retry_attempts_total = Counter(
    "retry_attempts_total", "Total retry attempts", ["operation", "attempt_number"]
)

# Successful retries
retry_success_total = Counter(
    "retry_success_total",
    "Total successful retries after initial failure",
    ["operation"],
)

# ========================================
# Service Info
# ========================================

service_info = Info("matchmaking_service", "Matchmaking service information")

service_info.info(
    {"version": "1.0.0", "service": "matchmaking", "environment": "production"}
)


# ========================================
# Helper Functions
# ========================================


class MetricsTimer:
    """Context manager for timing operations"""

    def __init__(self, histogram, labels=None):
        self.histogram = histogram
        self.labels = labels or {}
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        if self.labels:
            self.histogram.labels(**self.labels).observe(duration)
        else:
            self.histogram.observe(duration)
        return False


def record_http_request(method: str, endpoint: str, status_code: int, duration: float):
    """Record HTTP request metrics"""
    http_requests_total.labels(
        method=method, endpoint=endpoint, status_code=status_code
    ).inc()
    http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(
        duration
    )


def record_grpc_request(method: str, status: str, duration: float):
    """Record gRPC request metrics"""
    grpc_requests_total.labels(method=method, status=status).inc()
    grpc_request_duration_seconds.labels(method=method).observe(duration)


def record_circuit_breaker_state(circuit_name: str, state: str):
    """
    Record circuit breaker state
    state: 'closed' (0), 'open' (1), 'half_open' (2)
    """
    state_map = {"closed": 0, "open": 1, "half_open": 2}
    circuit_breaker_state.labels(circuit_name=circuit_name).set(state_map.get(state, 0))


def update_trade_offer_metrics(db_session):
    """Update trade offer metrics from database"""
    from sqlalchemy import func

    from models import TradeOfferDB, TradeOfferStatus

    # Count by status
    status_counts = (
        db_session.query(TradeOfferDB.status, func.count(TradeOfferDB.id))
        .group_by(TradeOfferDB.status)
        .all()
    )

    for status, count in status_counts:
        trade_offers_by_status.labels(status=status).set(count)

    # Count active users (users with pending/accepted offers)
    active_user_count = (
        db_session.query(func.count(func.distinct(TradeOfferDB.proposer_id)))
        .filter(
            TradeOfferDB.status.in_(
                [TradeOfferStatus.pending.value, TradeOfferStatus.accepted.value]
            )
        )
        .scalar()
    )

    active_users.set(active_user_count or 0)
