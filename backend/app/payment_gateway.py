import razorpay
import logging
import sys
from .config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET,payment_log_FILE
import traceback

# Initialize Razorpay client
client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))



logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(payment_log_FILE, mode='w', encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logging.info("✅ Test log: Logging system is working.")
logging.info("🚀 Starting payment_gateway...")


def process_payment(amount, currency="INR", request_id=None):
    """Create a Razorpay order and store mapping between order_id and request_id."""
    try:
        if amount <= 0:
            logging.error("❌ Invalid payment amount. It must be greater than zero.")
            return None

        logging.debug(f"Processing payment of amount: {amount} {currency} for request_id: {request_id}")
        amount_in_paise = int(amount * 100)  # Convert to paise
        
        order = client.order.create({
            "amount": amount_in_paise,
            "currency": currency,
            "payment_capture": 0  # ❌ Do NOT auto-capture in test mode
        })

        order_id = order.get("id")
        logging.info(f"✅ Razorpay Order Created: {order_id} for request_id: {request_id}")

        return order_id
    except Exception as e:
        logging.error(f"❌ Error creating Razorpay order: {e}")
        return None

def capture_payment(payment_id):
    """Capture an authorized payment manually."""
    try:
        if not payment_id:
            logging.error("❌ Missing payment_id for capture.")
            return False

        payment = client.payment.fetch(payment_id)

        if payment["status"] != "authorized":
            logging.warning(f"⚠️ Payment {payment_id} is not in 'authorized' state. Current status: {payment['status']}")
            return False

        amount = payment["amount"]  # Amount is in paise
        response = client.payment.capture(payment_id, amount)

        logging.info(f"✅ Payment {payment_id} captured successfully: {response}")
        return True
    except razorpay.errors.BadRequestError as e:
        logging.error(f"⚠️ BadRequestError while capturing payment {payment_id}: {e}")
    except razorpay.errors.ServerError as e:
        logging.error(f"⚠️ ServerError while capturing payment {payment_id}: {e}")
    except Exception as e:
        logging.error(f"⚠️ Failed to capture payment {payment_id}: {e}")
    
    return False

def verify_payment(payment_id):
    """Verify payment after it is captured."""
    try:
        if not payment_id:
            logging.error("❌ Missing payment_id for verification.")
            return False

        payment = client.payment.fetch(payment_id)
        logging.debug(f"🔍 Razorpay Payment Fetch Response: {payment}")

        if payment["status"] == "captured":
            logging.info(f"✅ Payment {payment_id} is captured and verified.")
            return True  # ✅ Payment is verified
        
        logging.error(f"❌ Payment {payment_id} failed or was not captured. Current status: {payment['status']}")
        return False  # ❌ Payment failed
    
    except razorpay.errors.SignatureVerificationError as e:
        logging.error(f"❌ Signature verification failed for payment {payment_id}: {e}")
        return False
    except Exception as e:
        logging.error(f"❌ Payment verification failed for {payment_id}: {e}")
        return False  # ❌ Payment verification failed
