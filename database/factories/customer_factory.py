import uuid
from .factory import Factory
from api.customers.model_customers import DBCustomer

class CustomerFactory(Factory):
    @property
    def model(self):
        return DBCustomer

    def definition(self) -> dict:
        return {
            "id": uuid.uuid4(),
            "name": self.faker.name(),
            "email": self.faker.unique.email(),
            "phone": self.faker.phone_number(),
            "status": self.faker.random_element(elements=("active", "inactive")),
            "avatar": self.faker.image_url() if self.faker.boolean() else None,
            "first_contact": self.faker.date_time_between(start_date="-1y", end_date="now")
        }
