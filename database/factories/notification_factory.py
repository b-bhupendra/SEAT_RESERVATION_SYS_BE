import uuid
from .factory import Factory
from api.notifications.model_notifications import DBNotification

class NotificationFactory(Factory):
    @property
    def model(self):
        return DBNotification

    def definition(self) -> dict:
        return {
            "id": uuid.uuid4(),
            "customer_id": None, # Provided during seeding
            "message": self.faker.sentence(nb_words=10),
            "sent_at": self.faker.date_time_between(start_date="-1m", end_date="now"),
            "is_read": self.faker.boolean(chance_of_getting_true=70)
        }
