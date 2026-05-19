import uuid
from .factory import Factory
from api.billing.model_bills import DBBill
from datetime import timedelta

class BillFactory(Factory):
    @property
    def model(self):
        return DBBill

    def definition(self) -> dict:
        month_ending = self.faker.date_time_between(start_date="-1y", end_date="now")
        due_date = month_ending + timedelta(days=15)
        
        return {
            "id": uuid.uuid4(),
            "customer_id": None, # Provided during seeding
            "amount": self.faker.pyfloat(left_digits=4, right_digits=2, min_value=50.0, max_value=2000.0),
            "month_ending": month_ending,
            "due_date": due_date,
            "pay_via": self.faker.random_element(elements=("Credit Card", "UPI", "Cash", "Bank Transfer")),
            "status": self.faker.random_element(elements=("paid", "confirmed", "pending"))
        }
