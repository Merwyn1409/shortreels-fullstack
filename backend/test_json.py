import json

data = {"test": {"order_id": "order_test", "payment_id": "pay_test"}}

with open("request_mapping.json", "w") as f:
    json.dump(data, f)