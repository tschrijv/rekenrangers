import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    DATABASE_URL = os.getenv("DATABASE_URL")

    # Language for this deployment. Fixed at startup, no runtime switching.
    # Supported: "nl" (Dutch), "es" (Spanish).
    LANGUAGE = os.getenv("LANGUAGE", "nl")
    BABEL_DEFAULT_LOCALE = LANGUAGE
    BABEL_TRANSLATION_DIRECTORIES = "translations"
