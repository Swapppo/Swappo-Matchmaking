from sqlalchemy import Column, Integer, String, DateTime, Text, ARRAY, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

Base = declarative_base()


class TradeOfferStatus(str, Enum):
    """Trade offer status enum"""
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    cancelled = "cancelled"
    completed = "completed"


# SQLAlchemy Models (Database)
class TradeOfferDB(Base):
    """SQLAlchemy model for trade_offers table"""
    __tablename__ = "trade_offers"

    id = Column(Integer, primary_key=True, index=True)
    
    # Proposer information (user making the offer)
    proposer_id = Column(String(100), nullable=False, index=True)
    
    # Receiver information (user receiving the offer)
    receiver_id = Column(String(100), nullable=False, index=True)
    
    # Items being offered (from proposer)
    offered_item_ids = Column(ARRAY(Integer), nullable=False)
    
    # Items being requested (from receiver)
    requested_item_ids = Column(ARRAY(Integer), nullable=False)
    
    # Trade status
    status = Column(String(20), nullable=False, default=TradeOfferStatus.pending.value, index=True)
    
    # Optional message from proposer
    message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Response timestamp (when accepted/rejected)
    responded_at = Column(DateTime(timezone=True), nullable=True)


# Pydantic Models (Request/Response)
class TradeOfferBase(BaseModel):
    """Base trade offer schema"""
    proposer_id: str = Field(..., min_length=1, max_length=100, description="User ID of the proposer")
    receiver_id: str = Field(..., min_length=1, max_length=100, description="User ID of the receiver")
    offered_item_ids: List[int] = Field(..., min_items=1, description="List of item IDs being offered")
    requested_item_ids: List[int] = Field(..., min_items=1, description="List of item IDs being requested")
    message: Optional[str] = Field(None, max_length=1000, description="Optional message to receiver")


class TradeOfferCreate(TradeOfferBase):
    """Schema for creating a trade offer"""
    pass


class TradeOfferUpdate(BaseModel):
    """Schema for updating a trade offer (status change)"""
    status: TradeOfferStatus = Field(..., description="New status for the trade offer")


class TradeOfferResponse(TradeOfferBase):
    """Schema for trade offer response"""
    id: int
    status: str
    created_at: datetime
    updated_at: datetime
    responded_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TradeOfferListParams(BaseModel):
    """Schema for listing trade offers with filters"""
    user_id: str = Field(..., min_length=1, description="User ID to filter by")
    status: Optional[TradeOfferStatus] = Field(default=None, description="Filter by status")
    as_proposer: Optional[bool] = Field(default=None, description="Filter offers where user is proposer")
    as_receiver: Optional[bool] = Field(default=None, description="Filter offers where user is receiver")
    limit: int = Field(default=20, ge=1, le=100, description="Number of offers to retrieve")
    offset: int = Field(default=0, ge=0, description="Number of offers to skip")


class MatchStatistics(BaseModel):
    """Statistics about matches and trade offers"""
    total_offers: int
    pending_offers: int
    accepted_offers: int
    rejected_offers: int
    completed_offers: int


class ErrorResponse(BaseModel):
    """Standard error response"""
    detail: str
