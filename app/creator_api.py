"""Local creator tools. No owner-funded service or automatic external requests."""
import copy
import importlib.util
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StrictInt
from engine import database, project as store
from engine.choreography import compile_choreography, exact_count
from engine.assembler import assemble, assemble_anchored, AssemblyError
from engine.steps import get_move
from engine.music_map import estimate_key, validate_map

router = APIRouter(prefix='/api/creator')


class DocumentBody(BaseModel):
    document: dict | list


class GenerateBody(BaseModel):
    counts: int = Field(default=32, ge=4, le=256)
    wall: str = '2'
    turn_dir: str = 'L'
    level: str = 'AB'
    seed: int = 0
    bpm: float | None = None
    allow_sync: bool = False
    start_foot: str = 'R'
    part: dict | None = None


class AcceptBody(BaseModel):
    expected_revision: StrictInt = Field(ge=0)


@router.post('/compile')
def compile_document(body: DocumentBody):
    if len(json.dumps(body.document)) > 4000000:
        raise HTTPException(413, 'Choreography is too large.')
    try:
        return compile_choreography(body.document)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise HTTPException(422, f'Choreography could not be read: {exc}') from exc


@router.get('/catalog')
def catalog():
    with open(database.SOURCE_PATH, encoding='utf-8') as source:
        return json.load(source)


@router.get('/moves')
def creator_moves():
    """Creator snapshots include exact events; the legacy /api/steps stays flat."""
    from engine.steps import library_json
    from engine.move_expansion import variants
    legacy = library_json()
    expansion = variants()
    return {'moves': legacy + expansion, 'coverage': {
        'legacy_patterns': len({m['move_id'] for m in legacy}),
        'expansion_patterns': len({m['move_id'] for m in expansion}),
        'expansion_variants': len(expansion),
        'mechanically_complete_variants': sum(bool(m.get('mechanically_complete')) for m in expansion),
        'instructor_review_pending': True,
    }}


@router.post('/generate')
def generate(body: GenerateBody):
    try:
        slots=[]
        count=exact_count(0)
        for item in (body.part or {}).get('moves', []):
            duration=exact_count(item.get('duration_counts',item.get('counts',0)))
            if item.get('locked'):
                if any(key in item for key in ('events', 'snapshot_id', 'definition')):
                    raise ValueError('This locked move uses an explicit event or snapshot definition. Keep it in the manual editor; automatic generation cannot substitute its legacy summary.')
                move=get_move(item.get('move_id'))
                if not move or item.get('lead') not in ('L','R') or count.denominator != 1:
                    raise ValueError('This locked move cannot be regenerated around automatically. Keep it in the manual editor or use reviewed built-in moves.')
                concrete=move.variant(item['lead'])
                if duration != exact_count(concrete['counts']):
                    raise ValueError('The locked move has conflicting count durations. Correct its timing before generating around it.')
                if any(item.get(key)!=concrete.get(key) for key in ('counts','start','end','rot','lines')):
                    raise ValueError('The locked definition differs from the current generator definition. The existing draft has been preserved.')
                slots.append({'start_count':int(count)+1,'move_id':item['move_id'],'lead':item['lead'],'source_text':item.get('name')})
            count+=duration
        method=assemble_anchored if slots else assemble
        kwargs={'required_slots':slots} if slots else {}
        result=method(total_counts=body.counts, wall=body.wall, turn_dir=body.turn_dir,
                        level=body.level, seed=body.seed, bpm=body.bpm, k=3,
                        allow_sync=body.allow_sync, start_foot=body.start_foot, **kwargs)
        # Preserve each locked occurrence's exact authored payload, ID and metadata.
        locked={};count=0
        for item in (body.part or {}).get('moves',[]):
            if item.get('locked'):locked[count]=item
            count+=exact_count(item.get('duration_counts',item.get('counts',0)))
        for candidate in result['candidates']:
            count=0
            for i,item in enumerate(candidate['moves']):
                if count in locked:candidate['moves'][i]=copy.deepcopy(locked[count])
                count+=item['counts']
        return result
    except (AssemblyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post('/projects/{pid}/key')
def key(pid: str):
    try:
        p = store.load_project(pid)
        path = (p.get('song') or {}).get('path')
        if not path:
            raise HTTPException(422, 'Attach music first; manual key entry is also available.')
        return estimate_key(path)
    except FileNotFoundError as exc:
        raise HTTPException(404, 'Project or music file not found; relink it in Music.') from exc


@router.post('/music-map/validate')
def check_music_map(body: dict):
    try:
        return validate_map(body)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('/addons')
def addons():
    available={name:importlib.util.find_spec(name) is not None for name in ('whisperx','demucs')}
    return {'installed':available, 'summary':'Core editing, music timing and export work locally. Speech alignment and stem separation are optional installations. AI assistance uses your own provider and credentials.'}


@router.post('/projects/{pid}/accept')
def accept(pid: str, body: AcceptBody):
    p=store.load_project(pid)
    if p['document_revision'] != body.expected_revision:
        raise store.RevisionConflict(body.expected_revision, p['document_revision'])
    # Read and compile the same revision that will be committed by store CAS.
    draft=copy.deepcopy(p['draft'])
    document=draft.get('choreography')
    if document is None:
        document=store.resolve_move_variants(p, (draft.get('editor') or {}).get('moves', []), draft=True)
    snapshots=draft.get('movement_snapshots') or p.get('movement_snapshots') or {}
    result=compile_choreography(document, snapshots)
    if not result['valid']:
        raise HTTPException(422, 'Resolve choreography errors before accepting this dance.')
    # Preserve the complete graph independently of the optional legacy view.
    p['accepted_choreography']=copy.deepcopy(result['normalized_document'])
    p['accepted_choreography_hash']=result['source_hash']
    p['accepted_choreography_source']=copy.deepcopy(document)
    p['dance']={'source':'structured', 'counts':result['total_counts'],
                'compiler':copy.deepcopy(result), 'tempo':{'bpm':draft.get('music_map',{}).get('bpm')}}

    def legacy_view():
        from engine.assembler import validate_sequence
        normalized=result['normalized_document']
        parts, runs=normalized['parts'], normalized['routine']
        if (result['status'] != 'VALID' or len(parts) != 1 or len(runs) != 1
                or parts[0]['kind'] != 'part' or runs[0]['repeat'] != 1
                or any(key in runs[0] for key in ('end_after_counts','reason','overrides'))
                or exact_count(normalized['pickup_counts']) != 0
                or normalized['meter'] != {'beats':'4','unit':'4','group_counts':'8'}
                or result['start_state']['facing_deg'] != '0'
                or result['start_state']['free_foot'] not in ('L','R')):
            return None
        raw_moves=document if isinstance(document,list) else document['parts'][0]['moves']
        moves=[]
        for item in raw_moves:
            if item.get('snapshot_id') is not None:
                item={**snapshots.get(str(item['snapshot_id']),{}), **item}
            elif isinstance(item.get('definition'),dict):
                item={**item['definition'], **{key:value for key,value in item.items() if key!='definition'}}
            # An explicit event graph is authoritative and must never be
            # replaced with aggregate mechanics that may disagree with it.
            if ('events' in item or not all(key in item for key in ('counts','start','end','rot','lines'))
                    or type(item['counts']) is not int or item['counts'] <= 0
                    or type(item['rot']) is not int or item['rot'] % 90
                    or item['start'] not in ('L','R','F') or item['end'] not in ('L','R','SAME')
                    or not isinstance(item['lines'],list) or not item['lines']):
                return None
            if any(not isinstance(line,dict) or type(line.get('beats')) is not int
                   or line['beats'] <= 0 or not isinstance(line.get('text'),str)
                   or not line['text'].strip() for line in item['lines']):
                return None
            if sum(line['beats'] for line in item['lines']) != item['counts']:
                return None
            move=copy.deepcopy(item)
            move.setdefault('name', str(item.get('move_id') or item.get('id') or 'Authored move'))
            move.setdefault('header', move['name'])
            move.setdefault('move_id', str(item.get('id') or f'accepted-{len(moves)+1}'))
            moves.append(move)
        counts=exact_count(result['total_counts'])
        rotation=exact_count(result['net_rotation_deg'])
        if counts.denominator != 1 or rotation not in (0,90,180,270):
            return None
        wall={0:'1',90:'4',180:'2',270:'4'}[rotation]
        turn_dir='R' if rotation == 90 or (rotation == 180 and sum(move['rot'] for move in moves) > 0) else 'L'
        start_foot=result['start_state']['free_foot']
        report=validate_sequence(moves,int(counts),wall,turn_dir,start_foot=start_foot)
        if not report['valid']:
            return None
        return {'source':'creator', 'counts':int(counts), 'wall':wall, 'walls':report['walls'],
                'turn_dir':turn_dir, 'start_foot':start_foot, 'chosen':0,
                'candidates':[{'moves':moves, 'net_rot':report['net_rot'], 'walls':report['walls']}],
                'compiler':copy.deepcopy(result), 'tempo':{'bpm':draft.get('music_map',{}).get('bpm')}}

    compatible=legacy_view()
    if compatible is not None:
        p['dance']=compatible
    store.save_project(pid,p,expected_revision=body.expected_revision)
    return {'status':'accepted', 'document_revision':p['document_revision'], 'validation':result['status'],
            'legacy_compatible':compatible is not None}
