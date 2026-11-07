from app.database import engine, Base
from app.models import *  # noqa

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("Database tables created.")
