"""Local archive importer. Runtime adapter lives in loader.py."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone

def find_game():
    """FANTOME_GAME override, then Riot Client metadata, then the default install folder."""
    candidates = [os.environ.get('FANTOME_GAME')]
    riot = Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData')) / 'Riot Games'
    settings = riot / 'Metadata/league_of_legends.live/league_of_legends.live.product_settings.yaml'
    try:
        for line in settings.read_text(encoding='utf-8').splitlines():
            if line.startswith('product_install_full_path:'):
                candidates.append(line.split(':', 1)[1].strip().strip('"'))
    except OSError:
        pass
    try:
        installs = json.loads((riot / 'RiotClientInstalls.json').read_text(encoding='utf-8'))
        candidates += [p for p in installs.get('associated_client', {}) if 'league of legends' in p.lower()]
    except (OSError, ValueError):
        pass
    candidates += [r'C:\Riot Games\League of Legends', r'D:\Riot Games\League of Legends', r'E:\Riot Games\League of Legends']
    for c in candidates:
        if c and (Path(c) / 'Game/League of Legends.exe').is_file():
            return Path(c)
    return Path(r'C:\Riot Games\League of Legends')

GAME = find_game()
LOGS = Path(os.environ['APPDATA']) / 'dev.leaguetoolkit.manager' / 'logs'

def sha256(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def save_json(path, value):
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def inspect(path):
    if Path(path).stat().st_size > 2 * 1024**3:
        raise ValueError('Limite de 2 Gio dépassée.')
    with zipfile.ZipFile(path) as z:
        entries = z.infolist()
        if len(entries) > 50000 or sum(x.file_size for x in entries) > 4 * 1024**3:
            raise ValueError('Limite de 50 000 entrées ou de 4 Gio décompressés dépassée.')
        names = set()
        for entry in entries:
            name = entry.filename
            if (name.startswith('/') or '\\' in name or ':' in name
                    or '..' in PurePosixPath(name).parts):
                raise ValueError('Chemin ZIP non sûr : ' + repr(name))
            if name.casefold() in names or entry.flag_bits & 1:
                raise ValueError('Entrée ZIP en double ou chiffrée.')
            names.add(name.casefold())
        meta = z.getinfo('META/info.json')
        if meta.file_size > 1024**2:
            raise ValueError('Métadonnées trop volumineuses.')
        info = json.loads(z.read(meta).decode('utf-8-sig'))
        if not isinstance(info, dict) or not isinstance(info.get('Name'), str) or not info['Name'].strip():
            raise ValueError('Nom du mod absent.')
        wads = [x.filename for x in entries if x.filename.startswith('WAD/') and not x.is_dir()]
        raw = [x.filename for x in entries if x.filename.startswith('RAW/') and not x.is_dir()]
        if not wads and not raw:
            raise ValueError('Aucun contenu WAD/ ou RAW/.')
        bad = z.testzip()
        if bad:
            raise ValueError('CRC ZIP incorrect : ' + bad)
        return dict(name=info['Name'], author=str(info.get('Author', '')),
                    description=str(info.get('Description', '')), version=str(info.get('Version', '')),
                    wads=wads, raw_count=len(raw), entries=len(entries))

class Library:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.archives = self.root / 'archives'
        self.archives.mkdir(exist_ok=True)
        self.file = self.root / 'library.json'
        self.state = json.loads(self.file.read_text(encoding='utf-8')) if self.file.exists() else dict(mods=[], selected=None)

    def log(self, event, message):
        with (self.root / 'events.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(dict(time_utc=datetime.now(timezone.utc).isoformat(), event=event,
                                   message=message), ensure_ascii=False) + '\n')

    def add(self, path):
        if Path(path).suffix.lower() != '.fantome':
            raise ValueError('Sélectionnez un fichier .fantome.')
        fd, tmp = tempfile.mkstemp(suffix='.fantome', dir=self.archives)
        os.close(fd)
        try:
            shutil.copyfile(path, tmp)
            mod = inspect(tmp)
            digest = sha256(tmp)
            for existing in self.state['mods']:
                if existing['sha256'] == digest:
                    self.log('IMPORT_DUPLICATE', digest)
                    return existing
            os.replace(tmp, self.archives / (digest + '.fantome'))
            mod['sha256'] = digest
            self.state['mods'].append(mod)
            save_json(self.file, self.state)
            self.log('IMPORTED', mod['name'] + ' | ' + digest)
            return mod
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def select(self, digest):
        if digest is not None and not any(m['sha256'] == digest for m in self.state['mods']):
            raise ValueError('Mod inconnu.')
        self.state['selected'] = digest
        save_json(self.file, self.state)
        self.log('PROFILE_SELECTED', digest)

    def selected_archive(self):
        digest = self.state['selected']
        if not digest:
            raise ValueError('Sélectionnez un mod dans le profil local.')
        if sha256(self.archives / (digest + '.fantome')) != digest:
            raise ValueError('Archive locale modifiée ; réimportation nécessaire.')
        return self.archives / (digest + '.fantome')

class LogWatch:
    MARKERS = ('c0000229', 'wad scan failed', 'overlay verified', 'redirected wad:',
               'skin database', 'skeleton is', 'overlay disabled', 'config flags')
    def __init__(self, directory=LOGS):
        self.directory = Path(directory)
        self.offsets = {str(p): p.stat().st_size for p in self.directory.glob('ltk-manager*.log')}
        self.pending = {}

    def poll(self):
        result = []
        for p in sorted(self.directory.glob('ltk-manager*.log')):
            key = str(p)
            offset = self.offsets.get(key, 0)
            if p.stat().st_size < offset:
                offset = 0
                self.pending.pop(key, None)
            with p.open('rb') as f:
                f.seek(offset)
                chunk = f.read(1024**2)
                self.offsets[key] = f.tell()
            lines = (self.pending.get(key, b'') + chunk).split(b'\n')
            self.pending[key] = lines.pop()
            for line in lines:
                text = line.decode('utf-8', errors='replace').strip()
                if any(m in text.lower() for m in self.MARKERS):
                    result.append(p.name + ' | ' + text)
        return result
