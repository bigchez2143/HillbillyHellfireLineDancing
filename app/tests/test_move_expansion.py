"""Independent timing/state expectations for the bundled manual move pack."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import move_expansion as expansion
from engine import steps, project as store
from engine.choreography import compile_choreography


GROUPS = {'Wizard / Dorothy', 'Turning sailors', 'Turning triples', 'Heel jack',
          'Vaudeville', 'Kick-ball-cross', 'Heel/toe switches', 'Forward locking triple',
          'Anchor step', 'Nightclub basic', 'Samba step', 'Volta turn', 'Diamond',
          'Hinge turn', 'Spiral turn', 'Twinkle', 'Pencil turn', 'Figure-eight turn',
          'Spiral lock', 'Spiral hitch', 'Moonwalk', 'Roger Rabbit'}


def example():
    return {'schema_version': 1,
            'sources': {'association': {'title': 'Teaching reference', 'url': 'https://example.org/glossary'}},
            'moves': [{'id': 'expansion-test', 'name': 'Right turn', 'aliases': ['Test step'],
                       'level': 'INT', 'family': 'test', 'group': 'Test group',
                       'duration_counts': '1', 'start_free_foot': 'R', 'net_rotation_deg': 90,
                       'travel': 'E', 'entry_facing_deg': 45,
                       'explanation': 'Step right; leave the left foot free.',
                       'source_ids': ['association'], 'review_status': expansion.REVIEW_STATUS,
                       'generator_eligible': False,
                       'events': [
                           {'offset_counts': '0', 'duration_counts': '1/3', 'text': 'Step R to the right',
                            'support_before': 'L', 'support_after': 'R', 'rotation_deg': 30},
                           {'offset_counts': '1/3', 'duration_counts': '1/3', 'text': 'Recover onto L',
                            'support_before': 'R', 'support_after': 'L', 'rotation_deg': 30},
                           {'offset_counts': '2/3', 'duration_counts': '1/3', 'text': 'Step R clockwise',
                            'support_before': 'L', 'support_after': 'R', 'rotation_deg': 30},
                       ]}]}


def write_pack(tmp_path, raw=None):
    target = tmp_path / 'expanded.json'
    target.write_text(json.dumps(example() if raw is None else raw), encoding='utf-8')
    return target


def choreography(move):
    return {'start': {'free_foot': move['start_free_foot'] or 'R',
                      'facing_deg': move['required_start_facing'] or '0'},
            'parts': [{'id': 'part', 'moves': [move]}], 'routine': [{'part_id': 'part'}]}


def test_original_39_and_78_concrete_variants_are_byte_equivalent():
    assert len(steps.MOVES) == 39
    variants = [move.variant(lead) for move in steps.MOVES for lead in ('R', 'L')]
    value = json.dumps(variants, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    assert hashlib.sha256(value).hexdigest() == '904a5680e80c2654cb6114f1bbb6486946acfd759f3021de57221390c90b4225'


def test_exact_thirds_and_mirrored_foot_rotation_text_facing(tmp_path):
    right, left = expansion.variants(write_pack(tmp_path))
    assert right['counts'] == 1 and right['duration_counts'] == '1'
    assert [event['offset_counts'] for event in left['events']] == ['0', '1/3', '2/3']
    assert [event['support_after'] for event in left['events']] == ['L', 'R', 'L']
    assert [event['rotation_deg'] for event in left['events']] == ['-30'] * 3
    assert [event['text'] for event in left['events']] == ['Step L to the left', 'Recover onto R', 'Step L counterclockwise']
    assert left['travel'] == 'W' and left['net_rotation_deg'] == '-90'
    assert left['required_start_facing'] == '315'
    assert left['events'][0]['facing_before_deg'] == '315'
    assert left['source_ids'] == right['source_ids'] == ['association']
    assert left['sources'] == right['sources']
    assert left['definition_hash'] != right['definition_hash']
    for move, facing, support in ((right, '135', 'R'), (left, '225', 'L')):
        compiled = compile_choreography(choreography(move))
        assert compiled['status'] == 'VALID'
        assert compiled['total_counts'] == '1'
        assert compiled['end_state']['facing_deg'] == facing
        assert compiled['end_state']['support'] == support
        assert move['mechanically_complete'] is True
        assert move['generator_eligible'] is False
        assert move['review']['status'] == 'INSTRUCTOR_REVIEW_PENDING'


def test_late_and_is_not_replaced_by_early_and(tmp_path):
    pack = example()
    move = pack['moves'][0]
    move['duration_counts'] = '2'
    for event, offset, duration in zip(move['events'], ('0', '1', '3/2'), ('1', '1/2', '1/2')):
        event.update(offset_counts=offset, duration_counts=duration)
    result = compile_choreography(choreography(expansion.variants(write_pack(tmp_path, pack))[0]))
    assert [event['start_count'] for event in result['events']] == ['0', '1', '3/2']
    assert [event['count_label'] for event in result['events']] == ['1', '2', '2&']
    assert result['total_counts'] == '2'


def test_fractional_total_stays_exact_and_never_claims_legacy_mechanics(tmp_path):
    pack = example()
    move = pack['moves'][0]
    move['events'] = move['events'][:1]
    move.update(duration_counts='1/3', net_rotation_deg=30)
    result = expansion.variants(write_pack(tmp_path, pack))[0]
    assert result['counts'] == '1/3'
    assert result['duration_counts'] == '1/3'
    assert not {'start', 'end', 'rot', 'lines'} & result.keys()
    assert compile_choreography(choreography(result))['total_counts'] == '1/3'


def test_unknown_mechanics_remain_manual_and_unverified(tmp_path):
    pack = example()
    move = pack['moves'][0]
    move.update(start_free_foot=None, net_rotation_deg=None)
    for event in move['events']:
        event.update(support_before='unknown', support_after='unknown', rotation_deg=None)
    for variant in expansion.variants(write_pack(tmp_path, pack)):
        assert variant['start_free_foot'] is None
        assert variant['net_rotation_deg'] is None
        assert variant['mechanically_complete'] is False
        compiled = compile_choreography(choreography(variant))
        assert compiled['status'] == 'UNVERIFIED'
        assert compiled['end_state']['support'] == 'unknown'
        assert compiled['end_state']['facing_deg'] is None


@pytest.mark.parametrize('problem', [
    'schema', 'extra', 'duplicate-id', 'missing-source', 'source-credential',
    'unknown-level', 'generator-claim', 'review-claim', 'gap', 'overlap',
    'wrong-duration', 'rotation-sum', 'support-conflict', 'invalid-fraction',
    'numeric-count', 'boolean-angle', 'nonfinite-angle', 'facing-conflict',
])
def test_rejects_contradictory_schema_before_use(problem):
    pack = example()
    row = pack['moves'][0]
    if problem == 'schema': pack['schema_version'] = True
    elif problem == 'extra': row['api_key'] = 'not-allowed'
    elif problem == 'duplicate-id': pack['moves'].append(deepcopy(row))
    elif problem == 'missing-source': row['source_ids'] = ['missing']
    elif problem == 'source-credential': pack['sources']['association']['url'] = 'https://user:secret@example.org/'
    elif problem == 'unknown-level': row['level'] = 'Expert'
    elif problem == 'generator-claim': row['generator_eligible'] = True
    elif problem == 'review-claim': row['review_status'] = 'VERIFIED'
    elif problem == 'gap': row['events'][1]['offset_counts'] = '1/2'
    elif problem == 'overlap': row['events'][1]['offset_counts'] = '0'
    elif problem == 'wrong-duration': row['duration_counts'] = '2'
    elif problem == 'rotation-sum': row['net_rotation_deg'] = 180
    elif problem == 'support-conflict': row['events'][1]['support_before'] = 'L'
    elif problem == 'invalid-fraction': row['duration_counts'] = '1/0'
    elif problem == 'numeric-count': row['duration_counts'] = 1
    elif problem == 'boolean-angle': row['net_rotation_deg'] = True
    elif problem == 'nonfinite-angle': row['events'][0]['rotation_deg'] = float('nan')
    elif problem == 'facing-conflict': row['events'][0]['facing_before_deg'] = 90
    with pytest.raises(expansion.ExpansionError):
        expansion.validate_pack(pack)


def test_duplicate_json_keys_and_oversized_pack_rejected(tmp_path, monkeypatch):
    target = write_pack(tmp_path)
    target.write_text('{"schema_version":1,"schema_version":1}', encoding='utf-8')
    with pytest.raises(expansion.ExpansionError, match='Duplicate'):
        expansion.load_pack(target)
    target.write_bytes(b' ' * 101)
    monkeypatch.setattr(expansion, 'MAX_BYTES', 100)
    with pytest.raises(expansion.ExpansionError, match='size limit'):
        expansion.load_pack(target)


def test_pack_and_return_values_cannot_mutate_each_other(tmp_path):
    raw = example()
    pristine = deepcopy(raw)
    validated = expansion.validate_pack(raw)
    validated['moves'][0]['events'][0]['text'] = 'Changed'
    assert raw == pristine
    path = write_pack(tmp_path, raw)
    right, left = expansion.variants(path)
    right['sources'][0]['title'] = 'Changed'
    right['events'][0]['text'] = 'Changed'
    assert left['sources'][0]['title'] == 'Teaching reference'
    assert expansion.variant('expansion-test', path=path)['events'][0]['text'] == 'Step R to the right'


def test_canonical_hash_ignores_formatting_and_load_does_not_cache_stale_data(tmp_path):
    raw = example()
    path = write_pack(tmp_path, raw)
    first = expansion.variant('expansion-test', path=path)
    path.write_text(json.dumps(raw, indent=4, sort_keys=True), encoding='utf-8')
    assert expansion.variant('expansion-test', path=path)['source_hash'] == first['source_hash']
    raw['moves'][0]['events'][0]['text'] = 'Revised reference wording'
    path.write_text(json.dumps(raw), encoding='utf-8')
    revised = expansion.variant('expansion-test', path=path)
    assert revised['source_hash'] != first['source_hash']
    assert revised['definition_hash'] != first['definition_hash']
    assert revised['snapshot_id'] != first['snapshot_id']
    assert first['events'][0]['text'] == 'Step R to the right'


def test_pending_manual_moves_never_enter_legacy_or_generator_pools(tmp_path, monkeypatch):
    monkeypatch.setattr(expansion, 'PACK_PATH', write_pack(tmp_path))
    monkeypatch.setattr(steps, 'CUSTOM_MOVES_PATH', str(tmp_path / 'no-custom.json'))
    legacy = steps.library_json()
    assert len(legacy) == 78
    assert steps.editor_moves() == legacy
    assert len(steps.editor_moves(include_expansion=True)) == 80
    assert steps.get_move('expansion-test') is None
    assert all(not move['move_id'].startswith('expansion-') for move in steps.generator_moves('A', True, True))
    coverage = expansion.coverage()
    assert coverage['count_new'] == 1 and coverage['count_variants'] == 2
    assert coverage['generator_eligible'] == 0 and coverage['instructor_review_pending'] == 1


@pytest.mark.parametrize('unknown', [False, True])
def test_saved_embedded_definition_survives_pack_edit_and_removal(tmp_path, monkeypatch, unknown):
    raw = example()
    if unknown:
        raw['moves'][0].update(start_free_foot=None, net_rotation_deg=None)
        for event in raw['moves'][0]['events']:
            event.update(support_before='unknown', support_after='unknown', rotation_deg=None)
    path = write_pack(tmp_path, raw)
    monkeypatch.setattr(store, 'PROJECTS_DIR', str(tmp_path / 'projects'))
    project = store.create_project('Synthetic expansion snapshot')
    frozen = expansion.variant('expansion-test', path=path)
    doc = choreography(frozen)
    def no_live_lookup(move_id):
        raise AssertionError('Embedded events must not query the live legacy library')
    monkeypatch.setattr(store, '_move_definition', no_live_lookup)
    first = store.save_workspace(project['id'], {'choreography': doc}, project['document_revision'])
    assert first['snapshot_issues'] == {'accepted': [], 'draft': []}
    path.unlink()
    saved = store.get_workspace(project['id'])['draft']['choreography']
    assert saved == doc
    embedded = saved['parts'][0]['moves'][0]
    assert embedded['source_hash'] == frozen['source_hash']
    assert embedded['sources'] == frozen['sources']
    assert compile_choreography(saved)['status'] == ('UNVERIFIED' if unknown else 'VALID')


def test_all_22_proposal_groups_are_present_manual_and_compile_as_declared():
    pack = expansion.load_pack()
    assert {row['group'] for row in pack['moves']} == GROUPS
    all_variants = expansion.variants()
    assert len(all_variants) == 2 * len(pack['moves'])
    assert len({row['snapshot_id'] for row in all_variants}) == len(all_variants)
    for row in all_variants:
        assert not row['generator_eligible'] and not row['in_generator']
        compiled = compile_choreography(choreography(row))
        assert compiled['status'] == ('VALID' if row['mechanically_complete'] else 'UNVERIFIED'), (row['move_id'], row['lead'], compiled['issues'])
        assert Fraction(compiled['total_counts']) == Fraction(row['duration_counts'])
    assert expansion.coverage()['count_groups'] == 22


def test_real_pack_compact_foot_sequences_and_directional_aliases_mirror():
    triple = expansion.variant('expansion-triple-right-1-4', 'L')
    assert triple['name'] == 'Triple 1/4 left turn — LRL'
    assert 'selected LRL' in triple['review_note']
    pack = expansion.load_pack()
    locking = next(row for row in pack['moves'] if row['group'] == 'Forward locking triple')
    assert expansion.variant(locking['id'], 'L')['name'].endswith('— LRL')
    assert 'Left Dorothy' in expansion.variant('expansion-wizard-right-diagonal', 'L')['aliases']
    assert expansion._mirror_text('RLR LRL RL R-R-L BRIGHT scroll') == 'LRL RLR LR L-L-R BRIGHT scroll'


def test_mirror_entry_facing_prose_and_directional_words_are_consistent():
    for row in expansion.load_pack()['moves']:
        if row['group'] == 'Diamond':
            left = expansion.variant(row['id'], 'L')
            assert left['required_start_facing'] == '45'
            assert '45 degrees' in left['explanation']
            assert '45-degree entry' in left['review_note']
            assert '315' not in left['explanation'] + left['review_note']
        if row['group'] == 'Figure-eight turn':
            left = expansion.variant(row['id'], 'L')
            assert left['net_rotation_deg'] == '-360'
            assert 'leftward rotation' in left['explanation']
            assert 'rightward' not in left['explanation']
    assert expansion._mirror_text('315 degrees; 315-degree entry; 315 counts; 90 degrees; 2026', 315) == '45 degrees; 45-degree entry; 315 counts; 90 degrees; 2026'
    assert expansion._mirror_text('clockwise counter-clockwise anticlockwise anti-clockwise rightwards RF LF') == 'counterclockwise clockwise clockwise clockwise leftwards LF RF'
