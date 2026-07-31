import uuid
from sqlalchemy import Column, String, Integer, Float, ForeignKey, DateTime, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.session import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sso_id = Column(String(255), nullable=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)

    name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    active_plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=True)
    subscription_status = Column(String(50), default="none")  # "none" | "active" | "expired"
    renewal_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    plan = relationship("SubscriptionPlan")
    purchases = relationship("Purchase", back_populates="user")

class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    features = Column(JSON, nullable=True)  # list of strings in JSON

class Purchase(Base):
    __tablename__ = "purchases"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False)
    whitenet_order_id = Column(String(255), unique=True, index=True, nullable=True)
    amount = Column(Float, nullable=False)
    status = Column(String(50), default="pending")  # "pending" | "paid" | "failed"
    checkout_token = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="purchases")
    plan = relationship("SubscriptionPlan")
    transactions = relationship("PaymentTransaction", back_populates="purchase")

class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    purchase_id = Column(String(36), ForeignKey("purchases.id"), nullable=False)
    razorpay_payment_id = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False)  # "captured" | "failed"
    payment_method = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    purchase = relationship("Purchase", back_populates="transactions")
