from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from app.config import DATABASE_URL


@contextmanager
def get_connection():
    with psycopg.connect(DATABASE_URL, connect_timeout=10, row_factory=dict_row) as connection:
        yield connection
