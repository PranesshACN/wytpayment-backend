import hmac
import hashlib
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
from app.db.session import get_db
from app.models.models import User, SubscriptionPlan, Purchase, PaymentTransaction
from app.schemas.schemas import CheckoutInitiateInput, CheckoutInitiateResponse, PurchaseResponse
from app.core import security, config
from app.services.whitenet_payment import WhiteNetPaymentService

logger = logging.getLogger("whitenet_purchases")

router = APIRouter(prefix="/api/purchases", tags=["purchases"])
payment_service = WhiteNetPaymentService()

@router.post("/checkout", response_model=CheckoutInitiateResponse)
def initiate_checkout(
    data: CheckoutInitiateInput,
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db)
):
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == data.plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Subscription plan not found")
        
    # 1. Create a local pending purchase record
    purchase = Purchase(
        user_id=current_user.id,
        plan_id=plan.id,
        amount=plan.price,
        status="pending"
    )
    db.add(purchase)
    db.commit()
    db.refresh(purchase)
    
    # 2. Invoke WhiteNet order creation service
    customer_id = current_user.sso_id if current_user.sso_id else current_user.id
    
    wn_res = payment_service.create_order(
        amount=plan.price,
        currency="INR",
        customer_id=customer_id,
        plan_id=plan.id,
        metadata={
            "user_email": current_user.email,
            "user_name": current_user.name,
            "sso_id": current_user.sso_id
        }
    )

    
    if not wn_res["success"]:
        # Mark local purchase attempt as failed
        purchase.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WhiteNet payment service error: {wn_res.get('error')}"
        )
        
    # 3. Cache WhiteNet order ID and checkout session token
    purchase.whitenet_order_id = wn_res["whitenet_order_id"]
    purchase.checkout_token = wn_res["checkout_token"]
    db.commit()
    
    logger.info(f"Initiated checkout for user {current_user.id}, plan {plan.id}, order_id {purchase.whitenet_order_id}")

    return {
        "purchase_id": purchase.id,
        "checkout_url": wn_res["payment_url"],
        "checkout_token": purchase.checkout_token,
        "whitenet_order_id": purchase.whitenet_order_id,
        "mock_checkout": wn_res["mock_checkout"]
    }

@router.get("/status/{whitenet_order_id}")
def check_order_status(
    whitenet_order_id: str,
    db: Session = Depends(get_db)
):
    """
    Read-only status check endpoint for client-side queries.
    Does NOT mutate purchase or user transaction status; status updates are driven strictly by webhooks.
    """
    purchase = db.query(Purchase).filter(Purchase.whitenet_order_id == whitenet_order_id).first()
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase record not found")
        
    logger.info(f"Polled order status for whitenet_order_id {whitenet_order_id}: current status is '{purchase.status}'")

    return {
        "whitenet_order_id": purchase.whitenet_order_id,
        "status": purchase.status,
        "amount": purchase.amount,
        "subscription_status": "active" if purchase.status in ["completed", "paid"] else "none"
    }

@router.get("/history", response_model=List[PurchaseResponse])
def get_purchase_history(
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db)
):
    purchases = db.query(Purchase).filter(Purchase.user_id == current_user.id).order_by(Purchase.created_at.desc()).all()
    return purchases

@router.post("/whitenet-webhook")
async def receive_whitenet_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("X-WytNet-Signature") or request.headers.get("X-WhiteNet-Signature", "")
    
    logger.info("Received WhiteNet webhook request.")

    # Perform HMAC verification if CLIENT_SECRET config is populated
    if config.CLIENT_SECRET:
        expected_sig = hmac.new(
            config.CLIENT_SECRET.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(expected_sig, signature):
            logger.warning("Invalid webhook signature received.")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        logger.info("Webhook HMAC signature validation succeeded.")
    else:
        logger.info("CLIENT_SECRET empty; skipping HMAC signature check.")

    try:
        payload = json.loads(body.decode())
    except Exception as e:
        logger.error(f"Failed to parse webhook body as JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    status_val = payload.get("status")
    event = payload.get("event")
    if not event and status_val:
        event = "payment_success" if str(status_val).lower() in ["paid", "completed", "captured", "success"] else "payment_failed"
        
    order_id = payload.get("order_id") or payload.get("whitenet_order_id")
    if not order_id:
        order_data = payload.get("order", {})
        order_id = order_data.get("whitenet_order_id") or order_data.get("order_id")
        
    payment_id = payload.get("payment_id")
    
    logger.info(f"Webhook parsed: event='{event}', order_id='{order_id}', payment_id='{payment_id}'")

    if not order_id:
        logger.warning("Webhook payload missing order_id.")
        raise HTTPException(status_code=400, detail="Missing order_id in webhook payload")

    purchase = db.query(Purchase).filter(Purchase.whitenet_order_id == order_id).first()
    if not purchase:
        logger.warning(f"Purchase not found in DB for whitenet_order_id '{order_id}'")
        raise HTTPException(status_code=404, detail=f"Purchase for order '{order_id}' not found")

    if event == "payment_success":
        # Idempotency Check: if already completed or paid, skip reprocessing
        if purchase.status in ["completed", "paid"]:
            logger.info(f"Order '{order_id}' is already marked as '{purchase.status}'. Duplicate webhook ignored (idempotent).")
            return {"status": "already_processed"}
            
        purchase.status = "completed"
        user = db.query(User).filter(User.id == purchase.user_id).first()
        if user:
            user.active_plan_id = purchase.plan_id
            user.subscription_status = "active"
            user.renewal_date = datetime.utcnow() + timedelta(days=30)
            logger.info(f"Activated subscription for user '{user.id}', plan '{purchase.plan_id}'")
            
        tx = PaymentTransaction(
            purchase_id=purchase.id,
            razorpay_payment_id=payment_id,
            status="captured",
            payment_method=payload.get("payment_method", "Webhook")
        )
        db.add(tx)
        db.commit()
        logger.info(f"Transaction for purchase '{purchase.id}' (order '{order_id}') updated to 'completed' via webhook.")
        
    elif event == "payment_failed":
        # Idempotency Check
        if purchase.status == "failed":
            logger.info(f"Order '{order_id}' is already marked as 'failed'. Duplicate webhook ignored (idempotent).")
            return {"status": "already_processed"}

        if purchase.status in ["completed", "paid"]:
            logger.warning(f"Received payment_failed event for already completed order '{order_id}'. Webhook ignored.")
            return {"status": "ignored_conflict"}

        purchase.status = "failed"
        
        tx = PaymentTransaction(
            purchase_id=purchase.id,
            razorpay_payment_id=payment_id,
            status="failed",
            payment_method=payload.get("payment_method", "Webhook")
        )
        db.add(tx)
        db.commit()
        logger.info(f"Transaction for purchase '{purchase.id}' (order '{order_id}') updated to 'failed' via webhook.")
        
    return {"status": "processed"}

