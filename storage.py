"""Storage for generated session payloads; user archives and logs are retained."""
from pathlib import Path
import json
import os
import re
import shutil

ROOT = Path(__file__).resolve().parent
SESSION_NAME = re.compile(r'^\d{8}T\d{6}Z-[0-9a-f]{6}$')
PAYLOAD_DIRS = ('overlay', 'mods', 'game_view')

def session_root(library_root, settings_path=None):
    settings_path = Path(settings_path) if settings_path else ROOT / 'settings.json'
    settings = json.loads(settings_path.read_text(encoding='utf-8-sig')) if settings_path.exists() else {}
    configured = os.environ.get('FANTOME_CACHE_DIR') or settings.get('cache_dir')
    path = Path(configured) / 'sessions' if configured else Path(library_root) / 'sessions'
    if not path.is_absolute():
        path = path.resolve() if not configured else None
    if path is None:
        raise ValueError('Le chemin du cache doit être absolu.')
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError('Dossier de cache indisponible : ' + str(path)) from exc
    return path

def file_bytes(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file() and not p.is_symlink())

def cleanup_finished_sessions(root, protected_pids=()):
    root = Path(root).resolve()
    if not root.exists():
        return {'freed_bytes': 0, 'directories_removed': 0, 'sessions_protected': [], 'errors': []}
    protected_pids = {int(pid) for pid in protected_pids}
    report = {'freed_bytes': 0, 'directories_removed': 0, 'sessions_protected': [], 'errors': []}
    for session in root.iterdir():
        if not session.is_dir() or not SESSION_NAME.fullmatch(session.name) or session.is_symlink() or session.is_junction():
            continue
        try:
            state = json.loads((session / 'status.json').read_text(encoding='utf-8')).get('state')
            if state not in ('stopped', 'failed', 'game_ended'):
                info = session / 'input.json'
                build_finished = (state == 'built' and info.exists()
                                  and json.loads(info.read_text(encoding='utf-8')).get('build_only') is True)
                if not build_finished:
                    continue
            log = session / 'host.log'
            pids = set(map(int, re.findall(r'^dll\s+\S+\s+(\d+)\s+', log.read_text(encoding='utf-8', errors='replace'), re.M))) if log.exists() else set()
            if pids & protected_pids:
                report['sessions_protected'].append(session.name)
                continue
            for name in PAYLOAD_DIRS:
                target = session / name
                if not target.exists():
                    continue
                resolved = target.resolve()
                if (not resolved.is_relative_to(root) or resolved.parent != session.resolve()
                        or target.is_symlink() or target.is_junction()):
                    raise ValueError('Chemin de nettoyage refusé : ' + str(target))
                if any(p.is_symlink() or p.is_junction() for p in target.rglob('*')):
                    raise ValueError('Lien détecté dans le cache ; dossier conservé.')
                amount = file_bytes(target)
                shutil.rmtree(target)
                report['freed_bytes'] += amount
                report['directories_removed'] += 1
        except (OSError, ValueError) as exc:
            report['errors'].append(session.name + ': ' + str(exc))
    return report
