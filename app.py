
from postgres import postgres_user, postgres_pass
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    app.config['SQLALCHEMY_DATABASE_URI'] = (
        f"postgresql://{postgres_user}:{postgres_pass}"
        f"@climate-db.croamw4iqxpi.us-east-2.rds.amazonaws.com:5432/postgres"
    )

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    return app

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        # Use a connection context
        with db.engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            print(result.fetchone())

