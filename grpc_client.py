"""
gRPC Client for Catalog Service
Used by Matchmaking service to fetch item details
Includes Circuit Breaker and Retry patterns for resilience
"""

import time
from typing import Any, Dict, List, Optional

import grpc
from pybreaker import CircuitBreaker, CircuitBreakerError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import catalog_pb2
import catalog_pb2_grpc

# Import metrics
from metrics import (
    circuit_breaker_failures_total,
    record_circuit_breaker_state,
    record_grpc_request,
)

# Circuit breaker for gRPC calls
# Opens after 5 failures, stays open for 60s, then half-open
catalog_circuit_breaker = CircuitBreaker(
    fail_max=5, reset_timeout=60, exclude=[], name="catalog_grpc"
)


class CatalogClient:
    """Client for communicating with Catalog Service via gRPC"""

    def __init__(self, catalog_service_url: str = "catalog-service:50051"):
        """
        Initialize the gRPC client

        Args:
            catalog_service_url: URL of the catalog service (default: catalog-service:50051)
        """
        self.catalog_service_url = catalog_service_url
        self.channel = None
        self.stub = None

    def connect(self):
        """Establish connection to the catalog service"""
        if not self.channel:
            self.channel = grpc.insecure_channel(self.catalog_service_url)
            self.stub = catalog_pb2_grpc.CatalogServiceStub(self.channel)
            print(f"✅ Connected to Catalog gRPC service at {self.catalog_service_url}")

    def close(self):
        """Close the gRPC channel"""
        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None
            print("✅ Closed Catalog gRPC connection")

    @retry(
        retry=retry_if_exception_type(grpc.RpcError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def get_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a single item by ID (with retry on failure)

        Args:
            item_id: The ID of the item to fetch

        Returns:
            Dictionary with item details, or None if not found
        """
        self.connect()

        try:
            request = catalog_pb2.GetItemRequest(item_id=item_id)
            response = catalog_circuit_breaker.call(self.stub.GetItem, request)

            return {
                "id": response.id,
                "name": response.name,
                "description": response.description,
                "category": response.category,
                "image_urls": list(response.image_urls),
                "location_lat": response.location_lat,
                "location_lon": response.location_lon,
                "owner_id": response.owner_id,
                "status": response.status,
                "created_at": response.created_at,
                "updated_at": response.updated_at,
            }
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                print(f"⚠️ Item {item_id} not found via gRPC")
                return None
            else:
                print(f"❌ gRPC error getting item {item_id}: {e}")
                raise

    @retry(
        retry=retry_if_exception_type(grpc.RpcError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def get_items(self, item_ids: List[int]) -> Dict[str, Any]:
        """
        Get multiple items by IDs (batch request with retry)

        Args:
            item_ids: List of item IDs to fetch

        Returns:
            Dictionary with 'items' (list of item dicts) and 'not_found_ids' (list of IDs)
        """
        self.connect()

        try:
            request = catalog_pb2.GetItemsRequest(item_ids=item_ids)
            response = catalog_circuit_breaker.call(self.stub.GetItems, request)

            items = [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "category": item.category,
                    "image_urls": list(item.image_urls),
                    "location_lat": item.location_lat,
                    "location_lon": item.location_lon,
                    "owner_id": item.owner_id,
                    "status": item.status,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                }
                for item in response.items
            ]

            return {"items": items, "not_found_ids": list(response.not_found_ids)}
        except grpc.RpcError as e:
            print(f"❌ gRPC error getting items: {e}")
            raise

    @retry(
        retry=retry_if_exception_type(grpc.RpcError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def validate_items(self, item_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Validate that items exist and check if they're active (with retry)

        Args:
            item_ids: List of item IDs to validate

        Returns:
            List of validation results with item_id, exists, is_active, owner_id
        """
        self.connect()
        start_time = time.time()
        status = "success"

        try:
            request = catalog_pb2.ValidateItemsRequest(item_ids=item_ids)
            response = catalog_circuit_breaker.call(self.stub.ValidateItems, request)

            return [
                {
                    "item_id": validation.item_id,
                    "exists": validation.exists,
                    "is_active": validation.is_active,
                    "owner_id": validation.owner_id,
                }
                for validation in response.validations
            ]
        except CircuitBreakerError:
            status = "circuit_breaker_open"
            circuit_breaker_failures_total.labels(circuit_name="catalog_grpc").inc()
            record_circuit_breaker_state("catalog_grpc", "open")
            print("⚠️ Circuit breaker is OPEN - Catalog service is unavailable")
            raise
        except grpc.RpcError as e:
            status = "grpc_error"
            print(f"❌ gRPC error validating items: {e}")
            raise
        finally:
            duration = time.time() - start_time
            record_grpc_request("ValidateItems", status, duration)


# Global client instance (singleton pattern)
_catalog_client = None


def get_catalog_client() -> CatalogClient:
    """
    Get or create the global catalog client instance

    Returns:
        CatalogClient instance
    """
    global _catalog_client
    if _catalog_client is None:
        _catalog_client = CatalogClient()
    return _catalog_client
