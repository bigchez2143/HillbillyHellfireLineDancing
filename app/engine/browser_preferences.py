"""Small per-profile move favorites store; no connection or project data."""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import sqlite3

PREFERENCES_DIR = None
KEY = re.compile(r'^(core|expansion|user|reference):[A-Za-z0-9_-]{1,140}$')

def directory():
    if PREFERENCES_DIR is not None:
        return Path(PREFERENCES_DIR)
    root = os.environ.get('LINE_DANCE_DATA_DIR')
    if root:
        return Path(root) / 'preferences'
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'LineDanceCreator/preferences'

@contextmanager
def _db():
    root = directory(); root.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(root / 'browser.sqlite3', timeout=15) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS favorites(key TEXT PRIMARY KEY)')
        yield conn

def get_preferences():
    with _db() as conn:
        return {'schema_version': 1, 'favorites': [r[0] for r in conn.execute('SELECT key FROM favorites ORDER BY key')]}

def set_favorite(key, favorite):
    if not isinstance(key, str) or not KEY.fullmatch(key) or type(favorite) is not bool:
        raise ValueError('Choose a move and whether to keep it in favorites.')
    with _db() as conn:
        if favorite:
            if conn.execute('SELECT count(*) FROM favorites').fetchone()[0] >= 5000:
                raise ValueError('The favorites limit has been reached.')
            conn.execute('INSERT OR IGNORE INTO favorites VALUES(?)', (key,))
        else:
            conn.execute('DELETE FROM favorites WHERE key=?', (key,))
        return {'schema_version': 1, 'favorites': [r[0] for r in conn.execute('SELECT key FROM favorites ORDER BY key')]}
