from flask_bootstrap import Bootstrap
from sqlalchemy import create_engine

bootstrap = Bootstrap()
engine = None

def init_engine(url):
    global engine
    engine = create_engine(url, future=True, pool_pre_ping=True)
