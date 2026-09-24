"""Recording swaps preserve choreography and archive source-specific timing.

History is local project data, not a publication payload. Changing recordings
does not change an accepted dance. Explicit review binds a recording's content
to the exact saved timing map; neither analysis nor generation grants review.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
import uuid

from . import project as store
from .music_map import validate_map


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def file_signature(path):
    """Content identity, with no path or credentials in the review token."""
    digest, size = hashlib.sha256(), 0
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            size += len(block)
            digest.update(block)
    return {'sha256': digest.hexdigest(), 'bytes': size}


def recording_review_needed(project):
    marker = project.get('recording_review') or (project.get('draft') or {}).get('recording_review')
    if not marker:
        return False  # legacy projects retain their existing behavior until a swap
    if not isinstance(marker, dict) or marker.get('status') != 'REVIEWED':
        return True
    if marker.get('recording_id') != (project.get('song') or {}).get('recording_id'):
        return True
    music_map = (project.get('draft') or {}).get('music_map') or project.get('music_map') or {}
    if marker.get('music_map_hash') != _digest(music_map):
        return True
    try:
        return file_signature(project['song']['path']) != marker.get('file_signature')
    except (OSError, KeyError, TypeError):
        return True


def switch_recording(project, path, filename, signature=None):
    """Mutate a loaded project copy; caller commits once using its revision.

Same-content relinking is reversible metadata maintenance. Different content
gets a new identity and a fresh, visibly unreviewed timing map. The previous
recording, mappings and accepted definitions are retained in local history.
"""
    signature = signature or file_signature(path)
    previous_song = deepcopy(project.get('song') or {})
    previous_signature = previous_song.get('content_signature')
    same_recording = bool(previous_signature and previous_signature == signature)
    if same_recording:
        project['song'].update(path=str(path), filename=filename)
        project.setdefault('draft', {})['song'] = deepcopy(project['song'])
        return False
    old_map = deepcopy((project.get('draft') or {}).get('music_map') or project.get('music_map') or {})
    history = project.setdefault('recording_history', [])
    if not isinstance(history, list):
        raise ValueError('Recording history is invalid; restore a good project version before replacing music.')
    prior_id = previous_song.get('recording_id') or 'recording-' + uuid.uuid4().hex
    if previous_song.get('path') or old_map or project.get('dance') or project.get('accepted_choreography'):
        archive = {'id': 'recording-history-' + uuid.uuid4().hex, 'recording_id': prior_id,
                   'archived_at': time.time(), 'source_revision': project.get('document_revision'),
                   'song': previous_song, 'music_map': old_map,
                   'recording_review': deepcopy(project.get('recording_review'))}
        for key in ('analysis', 'sections', 'alignment', 'phrase', 'lyric_move_draft', 'tutorial',
                    'repair', 'lyrics_raw', 'lyric_sections', 'dance', 'accepted_choreography',
                    'accepted_choreography_source', 'accepted_choreography_hash', 'movement_snapshots'):
            if key in project:
                archive[key] = deepcopy(project[key])
        history.append(archive)
    recording_id = 'recording-' + uuid.uuid4().hex
    new_song = {**previous_song, 'path': str(path), 'filename': filename,
                'recording_id': recording_id, 'content_signature': signature}
    # New bytes invalidate any old media-identity fields, even when the filename
    # is reused. Keep human title/artist metadata for the author to edit.
    new_song.pop('sha256', None)
    new_song.pop('fingerprint', None)
    project['song'] = new_song
    fresh_map = {'bpm': 120, 'first_count': 0, 'meter': old_map.get('meter', 4), 'anchors': [],
                 'reviewed': False, 'timing_confirmed': False, 'status': 'REVIEW_REQUIRED',
                 'source_recording_id': recording_id, 'bpm_source': 'PROVISIONAL_DEFAULT'}
    marker = {'status': 'REVIEW_REQUIRED', 'recording_id': recording_id,
              'previous_recording_id': prior_id if history else None, 'changed_at': time.time(),
              'reason': 'The recording changed. Review BPM, first count, beat anchors and choreography before exporting a timed or accepted version.'}
    project['recording_review'] = marker
    project['music_map'] = fresh_map
    draft = project.setdefault('draft', {})
    draft['song'] = deepcopy(new_song)
    draft['music_map'] = deepcopy(fresh_map)
    draft['recording_review'] = deepcopy(marker)
    # These are derived from audio time, not the independent choreography graph.
    project['sections'] = []
    draft['sections'] = []
    for key in ('analysis', 'alignment', 'phrase', 'lyric_move_draft', 'tutorial'):
        project[key] = None
        if key in draft:
            draft[key] = None
    return True


def review_recording(pid, expected_revision, confirmed):
    if confirmed is not True:
        raise ValueError('Confirm that you reviewed this recording and its saved timing map.')
    project = store.load_project(pid)
    if type(expected_revision) is not int or expected_revision != project['document_revision']:
        raise store.RevisionConflict(expected_revision, project['document_revision'])
    path = (project.get('song') or {}).get('path')
    if not path or not Path(path).is_file():
        raise ValueError('Attach or relink the recording before reviewing its timing.')
    signature = file_signature(path)
    recording_id = project['song'].get('recording_id') or 'recording-' + uuid.uuid4().hex
    music_map = deepcopy(project.get('draft', {}).get('music_map') or project.get('music_map') or {})
    validate_map(music_map)
    music_map.update(reviewed=True, timing_confirmed=True, status='REVIEWED', source_recording_id=recording_id)
    marker = {'status': 'REVIEWED', 'recording_id': recording_id, 'reviewed_at': time.time(),
              'file_signature': signature, 'music_map_hash': _digest(music_map)}
    project['song'].update(recording_id=recording_id, content_signature=signature)
    project['music_map'] = deepcopy(music_map)
    project['draft']['music_map'] = deepcopy(music_map)
    project['recording_review'] = deepcopy(marker)
    project['draft']['recording_review'] = deepcopy(marker)
    store.save_project(pid, project, expected_revision=expected_revision)
    result = store.get_workspace(pid)
    result['recording_review'] = deepcopy(marker)
    return result
