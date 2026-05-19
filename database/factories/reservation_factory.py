import uuid
from .factory import Factory
from api.reservations.model_reservations import DBReservation
from datetime import timedelta

class ReservationFactory(Factory):
    def __init__(self, session):
        super().__init__(session)
        self.counts = {}

    @property
    def model(self):
        return DBReservation

    def definition(self) -> dict:
        start_date = self.faker.date_time_between(start_date="-1y", end_date="now")
        duration = self.faker.random_int(min=1, max=12)
        
        org = self.faker.random_element(elements=("Trisha Library", "G2 Library"))
        sub_org = self.faker.random_element(elements=("Premium Zone", "General Area", "Reading Room"))
        
        org_code = "TL" if org == "Trisha Library" else "G2"
        sub_code = "PZ" if sub_org == "Premium Zone" else "GA" if sub_org == "General Area" else "RR"
        
        key = f"{org_code}-{sub_code}"
        self.counts[key] = self.counts.get(key, 0) + 1
        seat_num = f"{key}-{self.counts[key]:03d}"
        
        return {
            "id": uuid.uuid4(),
            "customer_id": None, # Provided during seeding
            "subsection": sub_org,
            "seat_number": seat_num,
            "start_date": start_date,
            "end_date": start_date + timedelta(days=30 * duration),
            "duration_months": duration,
            "amount": self.faker.pyfloat(left_digits=4, right_digits=2, min_value=150.0, max_value=5000.0),
            "pay_via": self.faker.random_element(elements=("Credit Card", "Bank Transfer", "Cash")),
            "status": self.faker.random_element(elements=("paid", "confirmed", "pending")),
            "organization": org,
            "sub_organization": sub_org
        }
