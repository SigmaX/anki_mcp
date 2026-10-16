import sqlite3
from contextlib import closing

import pytest

from anki_review.review import create_demo


@pytest.fixture
def collection(tmp_path):
    """Each test gets an isolated synthetic Anki collection, never user data."""
    path = tmp_path / "collection.anki2"
    info = create_demo(path)
    return path, info["deck_id"]


def read_rows(path, query, parameters=()):
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as db:
        return db.execute(query, parameters).fetchall()


def review_count(path):
    return read_rows(path, "select count(*) from revlog")[0][0]
