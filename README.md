# Lumina Pro - Backend

The core API for the Lumina Pro seat reservation and payment tracking system. Built with **FastAPI**, **SQLAlchemy**, and **Supabase**.

## Features
- **User Authentication**: Secure JWT-based auth with Supabase integration.
- **Seat Management**: Comprehensive CRUD for seat reservations.
- **Payment Processing**: Integration with PhonePe for seamless transactions.
- **Data Persistence**: Robust PostgreSQL database schema managed via SQLAlchemy.

## Tech Stack
- **Framework**: FastAPI
- **Database**: PostgreSQL (via Supabase)
- **ORM**: SQLAlchemy
- **Authentication**: Python-JOSE & PassLib
- **External APIs**: PhonePe, Supabase

## Setup & Running Locally

### Prerequisites
- Python 3.9+
- Pip & Virtualenv

### Installation
1. Clone the repository and navigate to the backend folder.
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # Linux/Mac
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure environment variables:
   - Copy `.env.example` to `.env`
   - Fill in your Supabase and database credentials.

### Starting the Server
Run the application using Uvicorn:
```bash
uvicorn app.main:app --reload
```
The API documentation will be available at [http://localhost:8000/docs](http://localhost:8000/docs).

## Project Structure
- `app/`: Core application logic (models, schemas, routers).
- `api/`: API endpoint definitions.
- `database/`: Database connection and session management.
- `tests/`: Automated test suite.
