CREATE TABLE roles (
	id UUID NOT NULL, 
	name VARCHAR, 
	description VARCHAR, 
	permissions VARCHAR, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE seats (
	id UUID NOT NULL, 
	seat_number VARCHAR NOT NULL, 
	organization VARCHAR NOT NULL, 
	sub_organization VARCHAR NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE settings (
	key VARCHAR NOT NULL, 
	value VARCHAR NOT NULL, 
	PRIMARY KEY (key)
);

CREATE TABLE users (
	id UUID NOT NULL, 
	email VARCHAR, 
	hashed_password VARCHAR, 
	role VARCHAR, 
	full_name VARCHAR, 
	PRIMARY KEY (id)
);

CREATE TABLE customers (
	id UUID NOT NULL, 
	name VARCHAR, 
	email VARCHAR, 
	phone VARCHAR, 
	status VARCHAR, 
	avatar VARCHAR, 
	profile_photo VARCHAR, 
	documents JSON, 
	user_id UUID, 
	first_contact TIMESTAMP WITHOUT TIME ZONE, 
	organization VARCHAR, 
	sub_organization VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE bills (
	id UUID NOT NULL, 
	customer_id UUID, 
	amount FLOAT, 
	month_ending TIMESTAMP WITHOUT TIME ZONE, 
	due_date TIMESTAMP WITHOUT TIME ZONE, 
	pay_via VARCHAR, 
	pay_date TIMESTAMP WITHOUT TIME ZONE, 
	status VARCHAR, 
	cash_due_date TIMESTAMP WITHOUT TIME ZONE, 
	notes VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);

CREATE TABLE payment_transactions (
	transaction_id VARCHAR NOT NULL, 
	customer_id UUID, 
	amount FLOAT, 
	status VARCHAR, 
	processed BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (transaction_id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);

CREATE TABLE reservations (
	id UUID NOT NULL, 
	customer_id UUID, 
	subsection VARCHAR, 
	seat_number VARCHAR, 
	start_date TIMESTAMP WITHOUT TIME ZONE, 
	end_date TIMESTAMP WITHOUT TIME ZONE, 
	duration_months INTEGER, 
	amount FLOAT, 
	pay_via VARCHAR, 
	status VARCHAR, 
	organization VARCHAR, 
	sub_organization VARCHAR, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);

