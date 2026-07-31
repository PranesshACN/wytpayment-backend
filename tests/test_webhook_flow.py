import unittest
import asyncio
import hmac
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import User, SubscriptionPlan, Purchase, PaymentTransaction
from app.routes.purchases import check_order_status, receive_whitenet_webhook
from app.core import security, config

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class MockRequest:
    def __init__(self, body_bytes: bytes, headers: dict = None):
        self._body = body_bytes
        self.headers = headers or {}

    async def body(self):
        return self._body

class TestWebhookFlowDirect(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        
        # Seed plan
        plan = SubscriptionPlan(id=1, name="Starter", price=100.0)
        self.db.add(plan)
        
        # Seed user
        user = User(
            id="test_user_id",
            email="test@example.com",
            name="Test User",
            hashed_password=security.get_password_hash("password123"),
            subscription_status="none"
        )
        self.db.add(user)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def test_status_endpoint_is_readonly(self):
        purchase = Purchase(
            id="purch_1",
            user_id="test_user_id",
            plan_id=1,
            whitenet_order_id="wn_ord_100",
            amount=100.0,
            status="pending"
        )
        self.db.add(purchase)
        self.db.commit()

        # Query status endpoint function directly
        res = check_order_status("wn_ord_100", db=self.db)
        self.assertEqual(res["status"], "pending")
        self.assertEqual(res["subscription_status"], "none")

        # Verify database status remains unchanged ("pending")
        p = self.db.query(Purchase).filter(Purchase.id == "purch_1").first()
        self.assertEqual(p.status, "pending")
        
        # Verify no PaymentTransaction record was created
        tx_count = self.db.query(PaymentTransaction).filter(PaymentTransaction.purchase_id == "purch_1").count()
        self.assertEqual(tx_count, 0)

    def test_webhook_success_flow(self):
        purchase = Purchase(
            id="purch_2",
            user_id="test_user_id",
            plan_id=1,
            whitenet_order_id="wn_ord_200",
            amount=100.0,
            status="pending"
        )
        self.db.add(purchase)
        self.db.commit()

        payload = {
            "event": "payment_success",
            "whitenet_order_id": "wn_ord_200",
            "payment_id": "pay_999",
            "payment_method": "UPI"
        }
        body = json.dumps(payload).encode()
        headers = {}
        if config.CLIENT_SECRET:
            headers["X-WhiteNet-Signature"] = hmac.new(config.CLIENT_SECRET.encode(), body, hashlib.sha256).hexdigest()
        req = MockRequest(body, headers=headers)

        res = asyncio.run(receive_whitenet_webhook(req, db=self.db))
        self.assertEqual(res, {"status": "processed"})

        # Verify DB state updated to completed
        self.db.expire_all()
        p = self.db.query(Purchase).filter(Purchase.id == "purch_2").first()
        self.assertEqual(p.status, "completed")

        user = self.db.query(User).filter(User.id == "test_user_id").first()
        self.assertEqual(user.subscription_status, "active")
        self.assertEqual(user.active_plan_id, 1)

        txs = self.db.query(PaymentTransaction).filter(PaymentTransaction.purchase_id == "purch_2").all()
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0].status, "captured")
        self.assertEqual(txs[0].razorpay_payment_id, "pay_999")

    def test_webhook_idempotency(self):
        purchase = Purchase(
            id="purch_3",
            user_id="test_user_id",
            plan_id=1,
            whitenet_order_id="wn_ord_300",
            amount=100.0,
            status="pending"
        )
        self.db.add(purchase)
        self.db.commit()

        payload = {
            "event": "payment_success",
            "whitenet_order_id": "wn_ord_300",
            "payment_id": "pay_888",
            "payment_method": "Card"
        }
        body = json.dumps(payload).encode()
        headers = {}
        if config.CLIENT_SECRET:
            headers["X-WhiteNet-Signature"] = hmac.new(config.CLIENT_SECRET.encode(), body, hashlib.sha256).hexdigest()
        req1 = MockRequest(body, headers=headers)
        req2 = MockRequest(body, headers=headers)

        # First webhook call
        res1 = asyncio.run(receive_whitenet_webhook(req1, db=self.db))
        self.assertEqual(res1, {"status": "processed"})

        # Duplicate webhook call
        res2 = asyncio.run(receive_whitenet_webhook(req2, db=self.db))
        self.assertEqual(res2, {"status": "already_processed"})

        # Verify only ONE transaction record created
        self.db.expire_all()
        tx_count = self.db.query(PaymentTransaction).filter(PaymentTransaction.purchase_id == "purch_3").count()
        self.assertEqual(tx_count, 1)

    def test_webhook_failed_flow(self):
        purchase = Purchase(
            id="purch_4",
            user_id="test_user_id",
            plan_id=1,
            whitenet_order_id="wn_ord_400",
            amount=100.0,
            status="pending"
        )
        self.db.add(purchase)
        self.db.commit()

        payload = {
            "event": "payment_failed",
            "whitenet_order_id": "wn_ord_400",
            "payment_id": "pay_777"
        }
        body = json.dumps(payload).encode()
        headers = {}
        if config.CLIENT_SECRET:
            headers["X-WhiteNet-Signature"] = hmac.new(config.CLIENT_SECRET.encode(), body, hashlib.sha256).hexdigest()
        req = MockRequest(body, headers=headers)

        res = asyncio.run(receive_whitenet_webhook(req, db=self.db))
        self.assertEqual(res, {"status": "processed"})

        # Verify DB state
        self.db.expire_all()
        p = self.db.query(Purchase).filter(Purchase.id == "purch_4").first()
        self.assertEqual(p.status, "failed")

        txs = self.db.query(PaymentTransaction).filter(PaymentTransaction.purchase_id == "purch_4").all()
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0].status, "failed")

    def test_webhook_signature_verification(self):
        old_secret = config.CLIENT_SECRET
        try:
            config.CLIENT_SECRET = "supersecretkey"

            purchase = Purchase(
                id="purch_5",
                user_id="test_user_id",
                plan_id=1,
                whitenet_order_id="wn_ord_500",
                amount=100.0,
                status="pending"
            )
            self.db.add(purchase)
            self.db.commit()

            body = json.dumps({
                "event": "payment_success",
                "whitenet_order_id": "wn_ord_500",
                "payment_id": "pay_666"
            }).encode()

            # Invalid signature -> Expect HTTPException 401
            bad_req = MockRequest(body, headers={"X-WhiteNet-Signature": "invalid_sig"})
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(receive_whitenet_webhook(bad_req, db=self.db))
            self.assertEqual(ctx.exception.status_code, 401)

            # Valid signature -> Expect success
            valid_sig = hmac.new("supersecretkey".encode(), body, hashlib.sha256).hexdigest()
            good_req = MockRequest(body, headers={"X-WhiteNet-Signature": valid_sig})
            res = asyncio.run(receive_whitenet_webhook(good_req, db=self.db))
            self.assertEqual(res, {"status": "processed"})
        finally:
            config.CLIENT_SECRET = old_secret

if __name__ == "__main__":
    unittest.main()
