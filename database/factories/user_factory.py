import uuid
from .factory import Factory
from api.auth_user.model_users import DBUser
from api.auth_user.auth_utils import get_password_hash

class UserFactory(Factory):
    @property
    def model(self):
        return DBUser

    def definition(self) -> dict:
        return {
            "id": uuid.uuid4(),
            "email": self.faker.unique.email(),
            "hashed_password": get_password_hash("password123"),
            "role": self.faker.random_element(elements=("staff", "manager")),
            "full_name": self.faker.name()
        }

    def create_admin(self, email="admin@admin.com", password="admin"):
        """Special method to create the requested admin account."""
        return self.create(
            id=uuid.uuid4(),
            email=email,
            hashed_password=get_password_hash(password),
            role="admin",
            full_name="System Administrator"
        )
