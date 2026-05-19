from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from api.db_core import Base

# Import all models to ensure they are registered with Base.metadata
import api.auth_user.model_users
import api.customers.model_customers
import api.billing.model_bills
import api.reservations.model_reservations
import api.reservations.model_seats
import api.settings.model_settings

# Function to dump schema
with open("supabase_schema.sql", "w") as f:
    for table in Base.metadata.sorted_tables:
        create_expr = CreateTable(table).compile(dialect=postgresql.dialect())
        f.write(str(create_expr).strip() + ";\n\n")
print("Schema generated in supabase_schema.sql")
