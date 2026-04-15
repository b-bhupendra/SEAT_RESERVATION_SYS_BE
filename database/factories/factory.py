from abc import ABC, abstractmethod
from typing import List, Any
from sqlalchemy.orm import Session
from faker import Faker

class Factory(ABC):
    def __init__(self, session: Session):
        self.session = session
        self.faker = Faker()

    @abstractmethod
    def definition(self) -> dict:
        """Define the model's default state."""
        pass

    @property
    @abstractmethod
    def model(self) -> Any:
        """Target SQLAlchemy model."""
        pass

    def create(self, **attributes) -> Any:
        """Create a single model instance."""
        data = {**self.definition(), **attributes}
        instance = self.model(**data)
        self.session.add(instance)
        self.session.flush()
        return instance

    def create_many(self, count: int, **attributes) -> int:
        """Create multiple model instances using bulk insert mappings for performance."""
        objects = []
        for _ in range(count):
            objects.append({**self.definition(), **attributes})
        
        # Batch processing to avoid memory issues or transaction timeouts
        batch_size = 500
        for i in range(0, len(objects), batch_size):
            batch = objects[i:i + batch_size]
            self.session.bulk_insert_mappings(self.model, batch)
            self.session.commit()
        
        return len(objects)
