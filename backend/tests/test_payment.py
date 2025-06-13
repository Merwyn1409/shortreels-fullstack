from payment_gateway import capture_payment, client

payment_id = "pay_Q5UopClV9yYAod"  # Replace with actual payment_id

# Fetch payment details to get the correct amount
payment = client.payment.fetch(payment_id)
amount = payment["amount"]  # Amount is in paise

# Capture the payment
if capture_payment(payment_id):
    print("✅ Payment captured successfully!")
else:
    print("❌ Failed to capture payment.")

    
