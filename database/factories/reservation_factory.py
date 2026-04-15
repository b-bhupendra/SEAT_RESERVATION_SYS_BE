import uuid
from .factory import Factory
from api.reservations.model_reservations import DBReservation
from datetime import timedelta

class ReservationFactory(Factory):
    @property
    def model(self):
        return DBReservation

    def definition(self) -> dict:
        start_date = self.faker.date_time_between(start_date="-1y", end_date="now")
        duration = self.faker.random_int(min=1, max=12)
        
        return {
            "id": uuid.uuid4(),
            "customer_id": None, # Provided during seeding
            "subsection": self.faker.random_element(elements=("Main Floor", "Premium", "Window View")),
            "seat_number": f"{self.faker.random_letter().upper()}-{self.faker.random_int(min=1, max=100)}",
            "start_date": start_date,
            "end_date": start_date + timedelta(days=30 * duration),
            "duration_months": duration,
            "amount": self.faker.pyfloat(left_digits=4, right_digits=2, min_value=150.0, max_value=5000.0),
            "pay_via": self.faker.random_element(elements=("Credit Card", "Bank Transfer", "Cash")),
            "status": self.faker.random_element(elements=("paid", "confirmed", "pending"))
        }
