"""Catalog preservation and the approved move-expansion data contract."""
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
GROUPS={
    'Wizard / Dorothy','Turning sailors','Turning triples','Heel jack','Vaudeville',
    'Kick-ball-cross','Heel/toe switches','Forward locking triple','Anchor step',
    'Nightclub basic','Samba step','Volta turn','Diamond','Hinge turn','Spiral turn',
    'Twinkle','Pencil turn','Figure-eight turn','Spiral lock','Spiral hitch','Moonwalk','Roger Rabbit',
}


def read(name):
    return json.loads((ROOT/'data'/name).read_text(encoding='utf-8'))


def test_original_173_identities_and_mechanics_are_preserved():
    fields=['name','aliases','category','counts','net_rotation_deg','travels','foot_start',
            'foot_end','weight_changes','level','ab_safe','mirrorable']
    prefix=read('step-database.json')['steps'][:173]
    projection=[{key:row.get(key) for key in fields} for row in prefix]
    digest=hashlib.sha256(json.dumps(projection,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    assert digest=='5bf23faface91121fff1b00cbdb139a625c70dd41e553e51e46ea313a92e3c6e'
    assert prefix[142]['name']=='Wizard'
    assert prefix[142]['count_notation']=='1-2&'
    assert prefix[122]['mechanics_review_notes'] and prefix[170]['mechanics_review_notes']


def test_all_22_approved_groups_are_review_pending_and_traceable():
    pack=read('expanded-moves.json')
    assert pack['schema_version']==1
    moves=pack['moves']
    assert {move['group'] for move in moves}==GROUPS
    assert len({move['id'] for move in moves})==len(moves)
    for move in moves:
        assert move['id'].startswith('expansion-')
        assert move['review_status']=='mechanics_draft_instructor_review_pending'
        assert move['generator_eligible'] is False
        assert move['explanation'].strip() and move['provenance_note'].strip()
        assert move['source_ids'] and set(move['source_ids'])<=set(pack['sources'])
    for source in pack['sources'].values():
        assert source['title'].strip() and source['url'].startswith('https://')


def test_event_intervals_exactly_partition_each_selected_duration():
    for move in read('expanded-moves.json')['moves']:
        elapsed=Fraction(0); support='L' if move['start_free_foot']=='R' else 'unknown'
        for event in move['events']:
            assert Fraction(event['offset_counts'])==elapsed,move['id']
            duration=Fraction(event['duration_counts'])
            assert duration>0
            elapsed+=duration
            assert event['support_before']==support,move['id']
            support=event['support_after']
        assert elapsed==Fraction(move['duration_counts']),move['id']
        if move['net_rotation_deg'] is not None:
            assert sum(Fraction(event['rotation_deg']) for event in move['events'])==Fraction(str(move['net_rotation_deg']))


def test_wizard_lock_and_samba_rhythms_remain_distinct():
    moves={move['id']:move for move in read('expanded-moves.json')['moves']}
    def onsets(mid):
        return [Fraction(e['offset_counts']) for e in moves[mid]['events']]
    assert onsets('expansion-wizard-right-diagonal')==[0,1,Fraction(3,2)]
    assert onsets('expansion-forward-locking-triple')==[0,Fraction(1,2),1]
    assert onsets('expansion-samba-forward-1a2')==[0,Fraction(3,4),1]
    assert onsets('expansion-samba-cross-1a2')==[0,Fraction(3,4),1]


def test_turn_variants_have_separate_ids_and_declared_entry_constraints():
    moves=read('expanded-moves.json')['moves']
    for group in ('Turning sailors','Turning triples','Volta turn'):
        assert {move['net_rotation_deg'] for move in moves if move['group']==group}=={90,180,270,360}
    diamonds=[move for move in moves if move['group']=='Diamond']
    assert len(diamonds)==2
    assert all(move['entry_facing_deg']==315 for move in diamonds)
    assert {move['net_rotation_deg'] for move in diamonds}=={180,360}


def test_unknown_technical_cues_do_not_invent_support_or_standard_timing():
    unknown=[move for move in read('expanded-moves.json')['moves'] if move['start_free_foot'] is None]
    assert {move['group'] for move in unknown}=={'Spiral lock','Spiral hitch','Moonwalk','Roger Rabbit'}
    for move in unknown:
        assert move['net_rotation_deg'] is None
        assert 'provisional' in move['explanation'].lower()
        assert all(e['support_before']=='unknown' and e['support_after']=='unknown' and e['rotation_deg'] is None for e in move['events'])


def test_reference_links_and_statistics_match_the_expansion():
    pack=read('expanded-moves.json')
    catalog=read('step-database.json')
    rows=catalog['steps']; ids={move['id'] for move in pack['moves']}
    assert len(rows)==173+len(pack['moves'])
    assert {row['expansion_ids'][0] for row in rows[173:]}==ids
    assert all(set(row.get('expansion_ids',[]))<=ids for row in rows)
    assert catalog['stats']['total']==len(rows)
    assert catalog['stats']['by_category']==dict(Counter(row['category'] for row in rows))
    assert catalog['stats']['by_level']==dict(Counter(row['level'] for row in rows))
    assert all(row['generator_eligible'] is False for row in rows[173:])
