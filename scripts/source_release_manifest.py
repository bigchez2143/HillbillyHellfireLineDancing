"""Read-only candidate source manifest. Never stages, copies, commits or uploads.

This is an allowlist, not a rights/security certification. Review Git history
and the S09 gates separately. Output contains relative paths and hashes only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {'.gitignore','README.md','STEERING.md','LICENSE','LICENSE.md','LICENSE.txt',
              'LICENSE-DRAFT.md','PRIVACY.md','THIRD_PARTY_NOTICES.md','CONTRIBUTING.md'}
PRUNED = {'.git','.venv','venv','env','.uv-cache','.pytest_cache','.test-cache','.test-tmp',
          'build','work','exports','references','private-audit','private-backups','backup-work','restored-profiles','__pycache__','node_modules'}
NOTICE_FILES = {'openpyxl-3.1.5-LICENSE.txt','et_xmlfile-2.0.0-LICENSE.txt','provenance.json'}
STATIC = {'.html','.css','.js','.svg','.png','.jpg','.jpeg','.ico','.woff2'}
TOKEN = re.compile(r'\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16})\b')


def allowed(relative):
    parts = relative.parts
    if len(parts) == 1:
        return relative.name in ROOT_FILES
    if parts[0] == 'app':
        if len(parts) == 2:
            return relative.suffix == '.py' or relative.name == 'run.bat' or (
                relative.name.startswith('requirements') and relative.suffix == '.txt')
        if parts[1] in {'engine','tests'}:
            return relative.suffix == '.py' or (parts[1] == 'tests' and relative.suffix == '.cjs')
        if parts[1] == 'static':
            return relative.suffix.lower() in STATIC
    if parts[0] == 'data':
        return len(parts) == 2 and relative.name in {'step-database.json','step-database.seed.json','common-move-explanations.json','expanded-moves.json'}
    if parts[0] == 'requirements':
        return len(parts) == 2 and (relative.suffix == '.txt' or relative.name == 'README.md')
    if parts[0] == 'scripts':
        return len(parts) == 2 and relative.suffix == '.py'
    if parts[:2] == ('docs','steering'):
        return (len(parts) == 3 and relative.suffix == '.md') or (
            len(parts) == 5 and parts[2:4] == ('evidence','dependency-notices') and relative.name in NOTICE_FILES)
    return False


def manifest():
    entries, flags, excluded = [], [], {}
    personal_root = str(Path.home()).lower()
    personal_forward = personal_root.replace('\\','/')
    for directory, folders, names in os.walk(ROOT, followlinks=False):
        parent = Path(directory)
        kept = []
        for name in folders:
            path = parent / name
            relative = path.relative_to(ROOT)
            if name in PRUNED or path.is_symlink() or relative.parts[:3] == ('docs','steering','legacy'):
                excluded[relative.as_posix() + '/'] = 'directory not traversed'
            else:
                kept.append(name)
        folders[:] = kept
        for name in names:
            path = parent / name
            relative = path.relative_to(ROOT)
            if not allowed(relative):
                group = relative.parts[0] if len(relative.parts) > 1 else '(other root files)'
                excluded[group] = excluded.get(group, 0) + 1
                continue
            if not path.resolve().is_relative_to(ROOT) or path.is_symlink():
                flags.append({'file':relative.as_posix(),'issue':'source resolves outside tree or is a symlink'})
                continue
            data = path.read_bytes()
            entries.append({'path':relative.as_posix(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
            if relative.suffix.lower() in STATIC - {'.html','.css','.js','.svg'}:
                flags.append({'file':relative.as_posix(),'issue':'static binary asset needs explicit provenance/rights review'})
            try:
                text = data.decode('utf-8-sig')
            except UnicodeDecodeError:
                continue
            lower = text.lower()
            if personal_root in lower or personal_forward in lower:
                flags.append({'file':relative.as_posix(),'issue':'contains a personal home path; review/redact for public source'})
            if TOKEN.search(text):
                flags.append({'file':relative.as_posix(),'issue':'possible credential-shaped value; inspect locally without publishing its value'})
    final_license = any((ROOT / name).is_file() for name in ('LICENSE','LICENSE.md','LICENSE.txt'))
    return {'mode':'dry-run only; no files staged/copied/committed/uploaded',
            'ready_to_publish':False,
            'reason':'Owner/license/content/history and release gates require separate review; this tool cannot approve them.',
            'final_license_present':final_license,
            'candidate_count':len(entries), 'candidate_bytes':sum(item['bytes'] for item in entries),
            'candidates':sorted(entries,key=lambda item:item['path']),
            'review_flags':flags,'excluded_summary':excluded,
            'git_history_checked':False,
            'exclusion_policy':'Runtime/environment/project/reference trees are not allowlisted; candidate file contents still require review.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary',action='store_true',help='Omit the full per-file hash list')
    result = manifest()
    if parser.parse_args().summary:
        result.pop('candidates')
    print(json.dumps(result,indent=2))
