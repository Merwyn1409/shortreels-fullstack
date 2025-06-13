2025-03-09 21:39:23,539 - DEBUG - Fetching paid video for payment_id: pay_Q4kijnVZPJv23n
Verifying payment for payment_id: pay_Q4kijnVZPJv23n
2025-03-09 21:39:23,725 - DEBUG - Starting new HTTPS connection (1): api.razorpay.com:443
2025-03-09 21:39:25,031 - DEBUG - https://api.razorpay.com:443 "GET /v1/payments/pay_Q4kijnVZPJv23n HTTP/1.1" 200 None
2025-03-09 21:39:26,312 - DEBUG - https://api.razorpay.com:443 "POST /v1/payments/pay_Q4kijnVZPJv23n/capture HTTP/1.1" 200 None       
Payment pay_Q4kijnVZPJv23n captured: {'id': 'pay_Q4kijnVZPJv23n', 'entity': 'payment', 'amount': 6000, 'currency': 'INR', 'status': 'captured', 'order_id': None, 'invoice_id': None, 'international': False, 'method': 'upi', 'amount_refunded': 0, 'refund_status': None, 
'captured': True, 'description': 'Purchase Watermark-Free Video', 'card_id': None, 'bank': None, 'wallet': None, 'vpa': 'success@razorpay', 'email': 'void@razorpay.com', 'contact': '+919443422677', 'notes': [], 'fee': 142, 'tax': 22, 'error_code': None, 'error_description': None, 'error_source': None, 'error_step': None, 'error_reason': None, 'acquirer_data': {'rrn': '625684858561', 'upi_transaction_id': '264BFB93629C89CFA879BB96E1EB2097'}, 'created_at': 1741536546, 'reward': None, 'upi': {'vpa': 'success@razorpay'}}
2025-03-09 21:39:26,768 - DEBUG - https://api.razorpay.com:443 "GET /v1/payments/pay_Q4kijnVZPJv23n HTTP/1.1" 200 None
INFO:     127.0.0.1:56543 - "POST /get-paid-video HTTP/1.1" 404 Not Found