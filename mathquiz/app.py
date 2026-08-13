# app.py

from dotenv import load_dotenv
load_dotenv()  # load .env BEFORE anything else

from flask import Flask
from config import Config
import extensions
from extensions import bootstrap, babel, init_engine, select_locale, audio_url
from models.db import init_db
from blueprints.auth.routes import auth_bp
from blueprints.student.routes import student_bp
from blueprints.teacher.routes import teacher_bp
import generate_exercises_all


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    bootstrap.init_app(app)
    babel.init_app(app, locale_selector=select_locale)
    app.jinja_env.globals["audio_url"] = audio_url
    app.jinja_env.globals["LANGUAGE"] = Config.LANGUAGE
    init_engine(Config.DATABASE_URL)
    init_db()
    generate_exercises_all.main()

    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(teacher_bp)

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=False)
