from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from engine import browser_preferences as prefs

def test_favorites_are_profile_scoped_persistent_and_independent(tmp_path,monkeypatch):
    monkeypatch.setattr(prefs,'PREFERENCES_DIR',tmp_path/'first')
    prefs.set_favorite('core:vine',True)
    prefs.set_favorite('expansion:expansion-test',True)
    prefs.set_favorite('core:vine',False)
    assert prefs.get_preferences()['favorites']==['expansion:expansion-test']
    monkeypatch.setattr(prefs,'PREFERENCES_DIR',tmp_path/'second')
    assert prefs.get_preferences()['favorites']==[]
    monkeypatch.setattr(prefs,'PREFERENCES_DIR',tmp_path/'first')
    assert prefs.get_preferences()['favorites']==['expansion:expansion-test']

def test_favorite_keys_cannot_be_paths_or_credentials(tmp_path,monkeypatch):
    monkeypatch.setattr(prefs,'PREFERENCES_DIR',tmp_path)
    for key in ('../../settings.json','api_key:secret','core:bad/path','core:bad?token=x'):
        with pytest.raises(ValueError):prefs.set_favorite(key,True)
    assert prefs.get_preferences()['favorites']==[]
