"""Reviewed musical timing, independently usable without optional AI models."""
import math
from bisect import bisect_right


def validate_map(raw):
    result = dict(raw or {})
    for key, default, low, high in [('bpm', 120, 10, 400), ('first_count', 0, 0, 86400)]:
        value = float(result.get(key, default))
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'{key} must be between {low} and {high}.')
        result[key] = value
    meter_number = float(result.get('meter', 4))
    if not math.isfinite(meter_number) or not meter_number.is_integer():
        raise ValueError('Meter must be a whole number of beats per bar.')
    meter = int(meter_number)
    if meter not in (2, 3, 4, 6, 8, 9, 12):
        raise ValueError('Choose a supported meter.')
    result['meter'] = meter
    anchors = result.get('anchors') or []
    if len(anchors) > 20000:
        raise ValueError('Too many timing anchors.')
    points = []
    for anchor in anchors:
        count, time = float(anchor['count']), float(anchor['time'])
        if not all(math.isfinite(x) for x in (count, time)) or count < 0 or time < 0:
            raise ValueError('Timing anchors need finite nonnegative counts and seconds.')
        if points and (count <= points[-1]['count'] or time <= points[-1]['time']):
            raise ValueError('Timing anchors must advance in both counts and seconds.')
        points.append({'count': count, 'time': time})
    result['anchors'] = points
    return result


def _interpolate(value, points, source, target, fallback):
    if not points:
        return fallback(value)
    if len(points) == 1:
        return points[0][target] + fallback(value) - fallback(points[0][source])
    index = max(0, min(len(points)-2, bisect_right([p[source] for p in points], value)-1))
    left, right = points[index:index+2]
    return left[target] + (value-left[source]) * (right[target]-left[target]) / (right[source]-left[source])


def count_to_seconds(count, raw):
    m = validate_map(raw)
    return _interpolate(float(count), m['anchors'], 'count', 'time', lambda x:m['first_count']+x*60/m['bpm'])


def seconds_to_count(seconds, raw):
    m = validate_map(raw)
    return _interpolate(float(seconds), m['anchors'], 'time', 'count', lambda x:(x-m['first_count'])*m['bpm']/60)


def estimate_key(path):
    """Heuristic chroma correlation; confidence describes separation, not certainty."""
    import librosa
    import numpy as np
    y, sr = librosa.load(path, sr=22050, mono=True, duration=180)
    if len(y) < sr or np.sqrt(np.mean(y*y)) < 1e-5:
        return {'key': '', 'confidence': 'insufficient', 'method':'chroma profile correlation', 'alternatives': []}
    chroma = librosa.feature.chroma_stft(y=y, sr=sr).mean(axis=1)
    profiles = {'major':[6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88],
                'minor':[6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17]}
    notes = ['C','C♯','D','E♭','E','F','F♯','G','A♭','A','B♭','B']
    ranked=[]
    for mode, profile in profiles.items():
        for shift, note in enumerate(notes):
            score = float(np.corrcoef(chroma, np.roll(profile, shift))[0,1])
            ranked.append({'key':note+' '+mode, 'score':round(score if math.isfinite(score) else 0,4)})
    ranked.sort(key=lambda row:row['score'], reverse=True)
    gap=ranked[0]['score']-ranked[1]['score']
    return {'key':ranked[0]['key'], 'confidence':'moderate' if gap>.08 else 'low',
            'method':'chroma profile correlation; first 180 seconds', 'alternatives':ranked[:3],
            'note':'Estimate only. Review by ear; key may change within the recording.'}
