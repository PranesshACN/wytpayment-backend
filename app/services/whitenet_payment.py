import requests
import logging
import uuid
from typing import Optional
from app.core import config

logger = logging.getLogger("whitenet_payment_service")

class WhiteNetPaymentService:
    def __init__(self):
        self.client_id = config.CLIENT_ID
        self.client_secret = config.CLIENT_SECRET
        self.app_id = config.APP_ID
        self.api_url = config.PAYMENT_API_URL.rstrip("/")
        
        # Running in Mock Mode if integration variables are missing
        self.is_mock = not (self.client_id and self.client_secret and self.app_id)
        if self.is_mock:
            logger.warning("WhiteNet payment integration variables missing. Running in MOCK Mode.")

    def create_order(self, amount: float, currency: str, customer_id: str, plan_id: str, metadata: Optional[dict] = None):
        if self.is_mock:
            # Generate local simulation values
            checkout_token = f"mock_tok_{uuid.uuid4().hex}"
            whitenet_order_id = f"wn_ord_mock_{uuid.uuid4().hex[:16]}"
            # The local mock checkout URL handled by the frontend
            mock_url = f"/mock-checkout/{checkout_token}"
            return {
                "success": True,
                "whitenet_order_id": whitenet_order_id,
                "checkout_token": checkout_token,
                "payment_url": mock_url,
                "mock_checkout": True
            }
            
        try:
            url = f"{self.api_url}/api/payments/orders"
            headers = {
                "Content-Type": "application/json",
                "X-Client-ID": self.client_id,
                "X-Client-Secret": self.client_secret,
                "X-App-ID": str(self.app_id)
            }
            payload = {
                "amount": amount,
                "currency": currency,
                "customer_id": customer_id,
                "plan_id": str(plan_id),
                "app_id": int(self.app_id) if self.app_id.isdigit() else self.app_id,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "metadata": metadata
            }
            
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            if 200 <= resp.status_code < 300:
                data = resp.json()
                payment_url = data.get("payment_url")
                checkout_token = data.get("checkout_token")
                if not checkout_token and payment_url:
                    checkout_token = payment_url.rstrip("/").split("/")[-1]
                return {
                    "success": True,
                    "whitenet_order_id": data.get("order_id") or data.get("whitenet_order_id"),
                    "checkout_token": checkout_token,
                    "payment_url": payment_url,
                    "mock_checkout": False
                }
            else:
                return {
                    "success": False,
                    "error": f"WhiteNet API responded with {resp.status_code}: {resp.text}"
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to connect to WhiteNet API: {str(e)}"
            }

    def verify_payment_status(self, whitenet_order_id: str):
        if self.is_mock or whitenet_order_id.startswith("wn_ord_mock_"):
            return {
                "success": True,
                "status": "paid",
                "payment_id": f"pay_mock_{uuid.uuid4().hex[:12]}",
                "payment_method": "UPI",
                "mock_checkout": True
            }
            
        try:
            url = f"{self.api_url}/api/payments/status/{whitenet_order_id}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "success": True,
                    "status": data.get("status", "pending"),
                    "payment_id": data.get("razorpay_payment_id") or data.get("payment_id"),
                    "payment_method": data.get("payment_method"),
                    "mock_checkout": False
                }
            else:
                return {
                    "success": False,
                    "error": f"WhiteNet status check responded with {resp.status_code}: {resp.text}"
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to verify order status at WhiteNet: {str(e)}"
            }
