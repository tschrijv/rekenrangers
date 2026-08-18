from flask import current_app, url_for
from flask_bootstrap import Bootstrap
from flask_babel import Babel
from sqlalchemy import create_engine

bootstrap = Bootstrap()
babel = Babel()
engine = None

def init_engine(url):
    global engine
    engine = create_engine(url, future=True, pool_pre_ping=True)


def select_locale():
    # Language is fixed per deployment via the LANGUAGE config/env var —
    # there is no runtime language switching.
    return current_app.config["LANGUAGE"]


def audio_url(filename):
    """Build the static URL for a voiceover clip in the deployment's language."""
    lang = current_app.config["LANGUAGE"]
    return url_for("static", filename=f"audio/{lang}/{filename}")


def image_url(filename):
    """Build the static URL for a themed illustration in the deployment's language."""
    lang = current_app.config["LANGUAGE"]
    return url_for("static", filename=f"images/{lang}/{filename}")
