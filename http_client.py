"""
HTTP Client utilities with retry and circuit breaker patterns
Used for resilient inter-service communication
"""

import httpx
from pybreaker import CircuitBreaker
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Circuit breakers for different services
notification_circuit_breaker = CircuitBreaker(
    fail_max=5, timeout_duration=60, exclude=[], name="notifications_http"
)

chat_circuit_breaker = CircuitBreaker(
    fail_max=5, timeout_duration=60, exclude=[], name="chat_http"
)


@retry(
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def http_post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    json_data: dict,
    circuit_breaker: CircuitBreaker,
):
    """
    Make HTTP POST request with retry and circuit breaker

    Args:
        client: HTTPX async client
        url: URL to POST to
        json_data: JSON data to send
        circuit_breaker: Circuit breaker instance to use

    Returns:
        Response object

    Raises:
        CircuitBreakerError: If circuit is open
        httpx.RequestError: If request fails after retries
    """

    def _make_request():
        return client.post(url, json=json_data)

    # Use asyncio to await the circuit breaker call
    import asyncio

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, circuit_breaker.call, _make_request)
    return await response


async def send_notification_resilient(url: str, notification_data: dict) -> bool:
    """
    Send notification with retry and circuit breaker

    Args:
        url: Notification service URL
        notification_data: Notification payload

    Returns:
        True if successful, False otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await http_post_with_retry(
                client, url, notification_data, notification_circuit_breaker
            )

            if response.status_code == 201:
                print("✅ Notification sent successfully")
                return True
            else:
                print(f"⚠️ Notification failed: {response.status_code}")
                return False

    except Exception as e:
        print(f"❌ Failed to send notification: {type(e).__name__}: {e}")
        return False


async def create_chat_room_resilient(url: str, chat_data: dict) -> dict:
    """
    Create chat room with retry and circuit breaker

    Args:
        url: Chat service URL
        chat_data: Chat room payload

    Returns:
        Response JSON or None if failed
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await http_post_with_retry(
                client, url, chat_data, chat_circuit_breaker
            )

            if response.status_code == 201:
                print("✅ Chat room created successfully")
                return response.json()
            else:
                print(f"⚠️ Chat room creation failed: {response.status_code}")
                return None

    except Exception as e:
        print(f"❌ Failed to create chat room: {type(e).__name__}: {e}")
        return None
