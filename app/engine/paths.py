"""Portable builds keep mutable data outside application files.

Existing source checkouts retain their original locations unless explicitly
configured, so upgrading never silently moves or deletes private projects.
"""
import os


def runtime_path(name, legacy_path):
    root = os.environ.get('LINE_DANCE_DATA_DIR')
    return os.path.join(os.path.abspath(root), name) if root else legacy_path
