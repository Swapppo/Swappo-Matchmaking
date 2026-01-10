from contextlib import asynccontextmanager
from typing import List, Optional

import grpc
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pybreaker import CircuitBreakerError
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db, init_db

# Import gRPC client
from grpc_client import get_catalog_client

# Import HTTP resilience utilities
from http_client import create_chat_room_resilient, send_notification_resilient
from models import (
    ErrorResponse,
    MatchStatistics,
    TradeOfferCreate,
    TradeOfferDB,
    TradeOfferResponse,
    TradeOfferStatus,
    TradeOfferUpdate,
)

# Service URLs
NOTIFICATION_SERVICE_URL = "http://notifications_service:8000"
CHAT_SERVICE_URL = "http://chat_service:8000"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    # Startup: Initialize database
    init_db()
    yield
    # Shutdown: Cleanup if needed
    pass


# Initialize FastAPI app
app = FastAPI(
    title="Swappo Matchmaking Service",
    description=(
        "Microservice for managing trade offers and matches in the Swappo app - "
        "a Tinder-like platform for item swapping"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def create_chat_room(offer: TradeOfferDB):
    """
    Create a chat room for an accepted trade offer (with retry and circuit breaker).

    Args:
        offer: The accepted trade offer
    """
    chat_room_data = {
        "trade_offer_id": offer.id,
        "user1_id": offer.proposer_id,
        "user2_id": offer.receiver_id,
    }

    print(f"💬 Attempting to create chat room for offer {offer.id}")
    return await create_chat_room_resilient(
        f"{CHAT_SERVICE_URL}/api/v1/chat-rooms", chat_room_data
    )


async def send_trade_notification(
    offer: TradeOfferDB, new_status: TradeOfferStatus, actor_id: str
):
    """
    Send notification when a trade offer status changes.

    Args:
        offer: The trade offer that was updated
        new_status: The new status of the offer
        actor_id: The user ID who performed the action
    """
    # Determine recipient (opposite of actor)
    recipient_id = (
        offer.proposer_id if actor_id == offer.receiver_id else offer.receiver_id
    )

    # Create notification data based on status
    notification_data = {
        "user_id": recipient_id,
        "related_offer_id": offer.id,
        "related_user_id": actor_id,
    }

    if new_status == TradeOfferStatus.accepted:
        notification_data["type"] = "trade_offer_accepted"
        notification_data["title"] = "Trade Offer Accepted! 🎉"
        notification_data["body"] = "Great news! Your trade offer has been accepted."
    elif new_status == TradeOfferStatus.rejected:
        notification_data["type"] = "trade_offer_rejected"
        notification_data["title"] = "Trade Offer Declined"
        notification_data["body"] = "Your trade offer was declined. Keep exploring!"
    elif new_status == TradeOfferStatus.cancelled:
        notification_data["type"] = "trade_offer_cancelled"
        notification_data["title"] = "Trade Offer Cancelled"
        notification_data["body"] = "A trade offer you received has been cancelled."
    elif new_status == TradeOfferStatus.completed:
        notification_data["type"] = "trade_completed"
        notification_data["title"] = "Trade Completed! ✅"
        notification_data["body"] = "Congratulations! Your trade has been completed."
    else:
        print(f"ℹ️ No notification needed for status: {new_status.value}")
        return  # No notification for other statuses

    print(
        f"📤 Attempting to send notification to user {recipient_id} for offer {offer.id}"
    )

    # Send notification with retry and circuit breaker
    await send_notification_resilient(
        f"{NOTIFICATION_SERVICE_URL}/api/v1/notifications", notification_data
    )


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint"""
    return {
        "service": "Swappo Matchmaking Service",
        "status": "running",
        "version": "1.0.0",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check endpoint"""
    return {"status": "healthy", "service": "matchmaking", "version": "1.0.0"}


@app.post(
    "/api/v1/offers",
    response_model=TradeOfferResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Trade Offers"],
    responses={
        201: {"description": "Trade offer created successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request data"},
        404: {"model": ErrorResponse, "description": "Items or users not found"},
    },
)
async def create_trade_offer(
    offer_data: TradeOfferCreate, db: Session = Depends(get_db)
):
    """
    Create a new trade offer.

    This endpoint allows a user (proposer) to create a trade offer to another user (receiver).
    The offer can include:
    - Single item for single item
    - Multiple items for single item
    - Multiple items for multiple items

    Args:
        offer_data: Trade offer data including proposer, receiver, offered items, and requested items

    Returns:
        TradeOfferResponse: Created trade offer with ID and timestamps
    """
    # Validate that proposer and receiver are different
    if offer_data.proposer_id == offer_data.receiver_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create trade offer with yourself",
        )

    # Validate no duplicate item IDs in offered items
    if len(offer_data.offered_item_ids) != len(set(offer_data.offered_item_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate item IDs in offered items",
        )

    # Validate no duplicate item IDs in requested items
    if len(offer_data.requested_item_ids) != len(set(offer_data.requested_item_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate item IDs in requested items",
        )

    # Validate no overlap between offered and requested items
    offered_set = set(offer_data.offered_item_ids)
    requested_set = set(offer_data.requested_item_ids)
    if offered_set.intersection(requested_set):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Same item cannot be both offered and requested",
        )

    # ✨ Validate items exist via gRPC
    catalog_client = get_catalog_client()
    all_item_ids = offer_data.offered_item_ids + offer_data.requested_item_ids

    try:
        validations = catalog_client.validate_items(all_item_ids)

        # Check if all items exist
        invalid_items = [v for v in validations if not v["exists"]]
        if invalid_items:
            invalid_ids = [v["item_id"] for v in invalid_items]
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Items not found: {invalid_ids}",
            )

        # Check if all items are active
        inactive_items = [v for v in validations if not v["is_active"]]
        if inactive_items:
            inactive_ids = [v["item_id"] for v in inactive_items]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Items are not active: {inactive_ids}",
            )

        # Validate ownership: offered items must belong to proposer
        offered_validations = [v for v in validations if v["item_id"] in offered_set]
        wrong_owner = [
            v for v in offered_validations if v["owner_id"] != offer_data.proposer_id
        ]
        if wrong_owner:
            wrong_ids = [v["item_id"] for v in wrong_owner]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Proposer does not own offered items: {wrong_ids}",
            )

        # Validate ownership: requested items must belong to receiver
        requested_validations = [
            v for v in validations if v["item_id"] in requested_set
        ]
        wrong_owner = [
            v for v in requested_validations if v["owner_id"] != offer_data.receiver_id
        ]
        if wrong_owner:
            wrong_ids = [v["item_id"] for v in wrong_owner]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Receiver does not own requested items: {wrong_ids}",
            )

        print("✅ All items validated via gRPC for trade offer")
    except CircuitBreakerError:
        print("⚠️ Circuit breaker is OPEN - Catalog service is unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Catalog service unavailable - circuit breaker open",
        )
    except grpc.RpcError as e:
        print(f"❌ gRPC error during item validation: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Catalog service unavailable",
        )

    # Create trade offer in database
    db_offer = TradeOfferDB(
        proposer_id=offer_data.proposer_id,
        receiver_id=offer_data.receiver_id,
        offered_item_ids=offer_data.offered_item_ids,
        requested_item_ids=offer_data.requested_item_ids,
        message=offer_data.message,
        status=TradeOfferStatus.pending.value,
    )

    db.add(db_offer)
    db.commit()
    db.refresh(db_offer)

    return db_offer


@app.get(
    "/api/v1/offers/{offer_id}",
    response_model=TradeOfferResponse,
    tags=["Trade Offers"],
    responses={
        200: {"description": "Trade offer retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Trade offer not found"},
    },
)
async def get_trade_offer(offer_id: int, db: Session = Depends(get_db)):
    """
    Get a specific trade offer by ID.

    Args:
        offer_id: ID of the trade offer

    Returns:
        TradeOfferResponse: Trade offer details
    """
    db_offer = db.query(TradeOfferDB).filter(TradeOfferDB.id == offer_id).first()

    if not db_offer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade offer with ID {offer_id} not found",
        )

    return db_offer


@app.get(
    "/api/v1/offers",
    response_model=List[TradeOfferResponse],
    tags=["Trade Offers"],
    responses={200: {"description": "Trade offers retrieved successfully"}},
)
async def list_trade_offers(
    user_id: str = Query(..., description="User ID to filter by"),
    status: Optional[TradeOfferStatus] = Query(None, description="Filter by status"),
    as_proposer: Optional[bool] = Query(
        None, description="Filter offers where user is proposer"
    ),
    as_receiver: Optional[bool] = Query(
        None, description="Filter offers where user is receiver"
    ),
    limit: int = Query(20, ge=1, le=100, description="Number of offers to retrieve"),
    offset: int = Query(0, ge=0, description="Number of offers to skip"),
    db: Session = Depends(get_db),
):
    """
    List trade offers for a specific user with optional filters.

    This endpoint allows filtering trade offers by:
    - User role (proposer/receiver)
    - Offer status
    - Pagination (limit/offset)

    Args:
        user_id: User ID to filter by
        status: Optional status filter
        as_proposer: If True, return offers where user is proposer
        as_receiver: If True, return offers where user is receiver
        limit: Number of offers to return
        offset: Number of offers to skip

    Returns:
        List[TradeOfferResponse]: List of trade offers
    """
    query = db.query(TradeOfferDB)

    # Build user filter (proposer or receiver)
    user_filters = []
    if as_proposer is True:
        user_filters.append(TradeOfferDB.proposer_id == user_id)
    if as_receiver is True:
        user_filters.append(TradeOfferDB.receiver_id == user_id)

    # If neither flag is set or both are set, include both
    if not user_filters or (as_proposer and as_receiver):
        query = query.filter(
            or_(
                TradeOfferDB.proposer_id == user_id, TradeOfferDB.receiver_id == user_id
            )
        )
    else:
        query = query.filter(or_(*user_filters))

    # Apply status filter if provided
    if status:
        query = query.filter(TradeOfferDB.status == status.value)

    # Apply ordering (most recent first)
    query = query.order_by(TradeOfferDB.created_at.desc())

    # Apply pagination
    query = query.offset(offset).limit(limit)

    return query.all()


@app.patch(
    "/api/v1/offers/{offer_id}",
    response_model=TradeOfferResponse,
    tags=["Trade Offers"],
    responses={
        200: {"description": "Trade offer updated successfully"},
        400: {"model": ErrorResponse, "description": "Invalid status transition"},
        404: {"model": ErrorResponse, "description": "Trade offer not found"},
    },
)
async def update_trade_offer_status(
    offer_id: int,
    update_data: TradeOfferUpdate,
    user_id: str = Query(..., description="User ID performing the action"),
    db: Session = Depends(get_db),
):
    """
    Update the status of a trade offer.

    Status transitions:
    - Proposer can cancel pending offers
    - Receiver can accept or reject pending offers
    - Either party can mark accepted offers as completed

    Args:
        offer_id: ID of the trade offer
        update_data: New status for the offer
        user_id: ID of user performing the action

    Returns:
        TradeOfferResponse: Updated trade offer
    """
    db_offer = db.query(TradeOfferDB).filter(TradeOfferDB.id == offer_id).first()

    if not db_offer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade offer with ID {offer_id} not found",
        )

    # Validate status transitions and permissions
    current_status = TradeOfferStatus(db_offer.status)
    new_status = update_data.status

    # Proposer can only cancel
    if user_id == db_offer.proposer_id:
        if (
            current_status == TradeOfferStatus.pending
            and new_status == TradeOfferStatus.cancelled
        ):
            pass  # Valid transition
        elif (
            current_status == TradeOfferStatus.accepted
            and new_status == TradeOfferStatus.completed
        ):
            pass  # Valid transition
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status transition for proposer",
            )

    # Receiver can accept or reject pending offers
    elif user_id == db_offer.receiver_id:
        if current_status == TradeOfferStatus.pending and new_status in [
            TradeOfferStatus.accepted,
            TradeOfferStatus.rejected,
        ]:
            pass  # Valid transition
        elif (
            current_status == TradeOfferStatus.accepted
            and new_status == TradeOfferStatus.completed
        ):
            pass  # Valid transition
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status transition for receiver",
            )

    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not authorized to modify this trade offer",
        )

    # Update status
    db_offer.status = new_status.value

    # Set responded_at timestamp for accept/reject
    if new_status in [TradeOfferStatus.accepted, TradeOfferStatus.rejected]:
        from datetime import datetime, timezone

        db_offer.responded_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(db_offer)

    # Send notification to the other party
    await send_trade_notification(db_offer, new_status, user_id)

    # Create chat room if offer is accepted
    if new_status == TradeOfferStatus.accepted:
        await create_chat_room(db_offer)

    return db_offer


@app.delete(
    "/api/v1/offers/{offer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Trade Offers"],
    responses={
        204: {"description": "Trade offer deleted successfully"},
        403: {
            "model": ErrorResponse,
            "description": "Not authorized to delete this offer",
        },
        404: {"model": ErrorResponse, "description": "Trade offer not found"},
    },
)
async def delete_trade_offer(
    offer_id: int,
    user_id: str = Query(..., description="User ID performing the action"),
    db: Session = Depends(get_db),
):
    """
    Delete a trade offer (only by proposer and only if pending).

    Args:
        offer_id: ID of the trade offer
        user_id: ID of user performing the action
    """
    db_offer = db.query(TradeOfferDB).filter(TradeOfferDB.id == offer_id).first()

    if not db_offer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade offer with ID {offer_id} not found",
        )

    # Only proposer can delete
    if user_id != db_offer.proposer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the proposer can delete a trade offer",
        )

    # Can only delete pending offers
    if db_offer.status != TradeOfferStatus.pending.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only delete pending trade offers",
        )

    db.delete(db_offer)
    db.commit()

    return None


@app.get(
    "/api/v1/offers/received/{user_id}",
    response_model=List[TradeOfferResponse],
    tags=["Trade Offers"],
    responses={200: {"description": "Received offers retrieved successfully"}},
)
async def get_received_offers(
    user_id: str,
    status: Optional[TradeOfferStatus] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Get all trade offers received by a user.

    Args:
        user_id: User ID
        status: Optional status filter
        limit: Number of offers to return
        offset: Number of offers to skip

    Returns:
        List[TradeOfferResponse]: List of received trade offers
    """
    query = db.query(TradeOfferDB).filter(TradeOfferDB.receiver_id == user_id)

    if status:
        query = query.filter(TradeOfferDB.status == status.value)

    query = query.order_by(TradeOfferDB.created_at.desc()).offset(offset).limit(limit)

    return query.all()


@app.get(
    "/api/v1/offers/sent/{user_id}",
    response_model=List[TradeOfferResponse],
    tags=["Trade Offers"],
    responses={200: {"description": "Sent offers retrieved successfully"}},
)
async def get_sent_offers(
    user_id: str,
    status: Optional[TradeOfferStatus] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Get all trade offers sent by a user.

    Args:
        user_id: User ID
        status: Optional status filter
        limit: Number of offers to return
        offset: Number of offers to skip

    Returns:
        List[TradeOfferResponse]: List of sent trade offers
    """
    query = db.query(TradeOfferDB).filter(TradeOfferDB.proposer_id == user_id)

    if status:
        query = query.filter(TradeOfferDB.status == status.value)

    query = query.order_by(TradeOfferDB.created_at.desc()).offset(offset).limit(limit)

    return query.all()


@app.get(
    "/api/v1/statistics/{user_id}",
    response_model=MatchStatistics,
    tags=["Statistics"],
    responses={200: {"description": "Statistics retrieved successfully"}},
)
async def get_user_statistics(user_id: str, db: Session = Depends(get_db)):
    """
    Get statistics about a user's trade offers.

    Args:
        user_id: User ID

    Returns:
        MatchStatistics: Statistics about trade offers
    """
    # Get all offers where user is involved (as proposer or receiver)
    offers = (
        db.query(TradeOfferDB)
        .filter(
            or_(
                TradeOfferDB.proposer_id == user_id, TradeOfferDB.receiver_id == user_id
            )
        )
        .all()
    )

    total_offers = len(offers)
    pending_offers = sum(
        1 for o in offers if o.status == TradeOfferStatus.pending.value
    )
    accepted_offers = sum(
        1 for o in offers if o.status == TradeOfferStatus.accepted.value
    )
    rejected_offers = sum(
        1 for o in offers if o.status == TradeOfferStatus.rejected.value
    )
    completed_offers = sum(
        1 for o in offers if o.status == TradeOfferStatus.completed.value
    )

    return MatchStatistics(
        total_offers=total_offers,
        pending_offers=pending_offers,
        accepted_offers=accepted_offers,
        rejected_offers=rejected_offers,
        completed_offers=completed_offers,
    )


@app.get(
    "/api/v1/offers/by-item/{item_id}",
    response_model=List[TradeOfferResponse],
    tags=["Trade Offers"],
    responses={200: {"description": "Offers involving item retrieved successfully"}},
)
async def get_offers_by_item(
    item_id: int,
    status: Optional[TradeOfferStatus] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
):
    """
    Get all trade offers that involve a specific item (either offered or requested).

    Args:
        item_id: Item ID
        status: Optional status filter

    Returns:
        List[TradeOfferResponse]: List of trade offers involving the item
    """
    query = db.query(TradeOfferDB).filter(
        or_(
            TradeOfferDB.offered_item_ids.contains([item_id]),
            TradeOfferDB.requested_item_ids.contains([item_id]),
        )
    )

    if status:
        query = query.filter(TradeOfferDB.status == status.value)

    query = query.order_by(TradeOfferDB.created_at.desc())

    return query.all()
