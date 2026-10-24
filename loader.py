"""Actual local overlay build + installed LTK host adapter. No patcher modification."""
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import queue
import struct
import subprocess
import threading
import time
import uuid
import zipfile
from core import GAME, inspect, sha256, save_json
from wad_builder import build_overlay
from storage import session_root, cleanup_finished_sessions

ROOT = Path(__file__).resolve().parent
HOST = ROOT / 'third_party/ltk-v1.28.1/ltk_patcher_host.exe'
NO_WINDOW = subprocess.CREATE_NO_WINDOW
TEST_GAME_BUILD = 1792188909

def game_build():
    with (GAME / 'Game/League of Legends.exe').open('rb') as f:
        header = f.read(4096)
    pe = struct.unpack_from('<I', header, 60)[0]
    if header[:2] != b'MZ' or header[pe:pe + 4] != b'PE\0\0':
        raise RuntimeError('Exécutable League invalide.')
    return struct.unpack_from('<I', header, pe + 8)[0]

def opted_out_warning(line):
    lower = line.lower()
    return (' warn ' in lower and 'wad scan failed' in lower
            and '(opted out)' in lower)

def host_failure(line):
    lower = line.lower()
    if opted_out_warning(line):
        return False
    return ('wad scan failed' in lower or 'overlay verification failed' in lower
            or 'host verification failed' in lower or 'refusing overlay' in lower
            or line.startswith('error ') or (line.startswith('status ') and ' failed' in lower))

def recent_game_error(since):
    root = GAME / 'Logs/GameLogs'
    paths = sorted(root.glob('*/*r3dlog.txt'), key=lambda p: p.parent.name, reverse=True)
    for path in paths[:2]:
        if path.stat().st_mtime < since:
            continue
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
        selected = [line for line in lines if ('FATAL ERROR' in line or 'WadFile mount failed' in line
                    or line.startswith(' - WadFile:') or line.startswith(' - Problem:'))]
        if selected:
            return path.name + '\n' + '\n'.join(selected)
    return None

class Loader:
    def __init__(self, library):
        self.lib = library
        self.events = queue.Queue()
        self.thread = None
        self.process = None
        self.cancel = threading.Event()
        self.started_at = time.time()
        self.lock = threading.Lock()
        self.state = 'idle'
        self.session = None
        self.verified = False
        self.redirected = []

    @property
    def active(self):
        return self.thread is not None and self.thread.is_alive()

    def emit(self, state, message):
        with self.lock:
            self.state = state
            item = dict(time_utc=datetime.now(timezone.utc).isoformat(), state=state, message=message)
            if self.session:
                confirmation = self.session / 'visual-confirmation.json'
                visual_confirmed = False
                if confirmation.exists():
                    visual_confirmed = json.loads(confirmation.read_text(encoding='utf-8')).get('confirmed') is True
                with (self.session / 'events.jsonl').open('a', encoding='utf-8') as f:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')
                save_json(self.session / 'status.json', dict(**item, verified=self.verified,
                          redirected=self.redirected, visual_confirmed=visual_confirmed))
            self.events.put(item)

    def conflicts(self):
        p = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True,
                           creationflags=NO_WINDOW, timeout=15)
        if p.returncode:
            raise RuntimeError('Impossible de vérifier les processus actifs ; démarrage annulé.')
        names = [r[0].lower() for r in csv.reader(io.StringIO(p.stdout.decode(errors='replace'))) if r]
        return [n for n in names if n in ('ltk_patcher_host.exe', 'cslol-manager.exe', 'rose.exe', 'league of legends.exe')]

    def start(self, build_only=False):
        if self.active:
            raise RuntimeError('Un chargement est déjà actif.')
        archive = self.lib.selected_archive()
        digest = self.lib.state['selected']
        inspect(archive)
        for p in (HOST, HOST.with_name('ltk_patcher_dll.dll')):
            if not p.is_file():
                raise RuntimeError('Dépendance absente : ' + str(p))
        if not build_only and game_build() != TEST_GAME_BUILD:
            raise RuntimeError('League a changé depuis le test du moteur v1.28.1. Chargement suspendu : '
                               'une nouvelle validation du moteur est nécessaire. La construction reste disponible.')
        compat = ROOT / 'compatibility.json'
        if not build_only and compat.exists():
            known = json.loads(compat.read_text(encoding='utf-8'))
            if known.get('rejected_dll_sha256') == sha256(HOST.with_name('ltk_patcher_dll.dll')):
                raise RuntimeError('Chargement bloqué : cette DLL a refusé notre application en jeu (VRF00000008). '
                                   'La construction d’overlay reste disponible. Voir README.md et verification-game.json.')
        self.build_only = build_only
        self.cancel = threading.Event()
        self.started_at = time.time()
        self.verified = False
        self.redirected = []
        self.session = session_root(self.lib.root) / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
        self.session.mkdir(parents=True)
        save_json(self.session / 'input.json', dict(mod_sha256=digest, game=str(GAME),
                  build_only=build_only,
                  builder='native-python-wad-v3.4', builder_sha256=sha256(ROOT / 'wad_builder.py'), host=str(HOST), host_sha256=sha256(HOST),
                  dll_sha256=sha256(HOST.with_name('ltk_patcher_dll.dll')), flags=4))
        self.emit('building', 'Construction d’un overlay privé. League reste en lecture seule.')
        self.thread = threading.Thread(target=self.run, args=(archive,), daemon=True)
        self.thread.start()
        return self.session

    def command(self, line):
        with self.lock:
            if self.process and self.process.poll() is None and self.process.stdin:
                self.process.stdin.write(line + '\n')
                self.process.stdin.flush()

    def stop(self):
        self.cancel.set()
        try:
            self.command('stop')
        except (OSError, ValueError):
            pass

    def run(self, archive):
        try:
            conflicts = [] if self.build_only else self.conflicts()
            if conflicts:
                raise RuntimeError('Fermez le patcher concurrent ou la partie avant de démarrer : ' + ', '.join(conflicts))
            if not self.build_only:
                roots = {self.session.parent.resolve(), (self.lib.root / 'sessions').resolve()}
                reclaimed = 0
                for cache in roots:
                    result = cleanup_finished_sessions(cache)
                    reclaimed += result['freed_bytes']
                if reclaimed:
                    self.emit('building', f'Ancien cache temporaire nettoyé : {reclaimed / 1024**2:.0f} Mio libérés. Archives et journaux conservés.')
            # Stream only recognized payloads. No archive executables, symlinks,
            # thumbnails or arbitrary metadata files are used as runtime code.
            mods = self.session / 'mods'
            folder = mods / 'selected'
            folder.mkdir(parents=True)
            with zipfile.ZipFile(archive) as z:
                if any(i.filename.startswith('RAW/') and not i.is_dir() for i in z.infolist()):
                    raise RuntimeError('Ce moteur accepte actuellement les mods WAD/. Conversion RAW/ non implémentée.')
                for entry in z.infolist():
                    name = entry.filename
                    if entry.is_dir() or not (name == 'META/info.json' or name.startswith('WAD/')):
                        continue
                    target = folder / name
                    if not target.resolve().is_relative_to(folder.resolve()):
                        raise ValueError('Chemin d’archive interdit.')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(entry) as src, target.open('wb') as dst:
                        while chunk := src.read(1024**2):
                            dst.write(chunk)
            if self.cancel.is_set():
                self.emit('stopped', 'Construction annulée avant lancement.')
                return
            overlay = self.session / 'overlay'
            targets = list((folder / 'WAD').rglob('*'))
            if any(p.is_file() and not p.name.lower().endswith('.wad.client') for p in targets):
                raise RuntimeError('WAD décompressés non pris en charge : fournissez des fichiers .wad.client dans WAD/.')
            with (self.session / 'builder.log').open('w', encoding='utf-8') as out:
                def progress(message):
                    out.write(message + '\n')
                    out.flush()
                    self.emit('building', message)
                report = build_overlay(folder, GAME / 'Game', overlay, self.cancel, progress)
            save_json(self.session / 'originals.json', report['originals_sha256'])
            built = list(overlay.rglob('*.wad.client'))
            if not built:
                raise RuntimeError('Le constructeur n’a produit aucun WAD.')
            save_json(self.session / 'build.json', report)
            if self.build_only:
                self.emit('built', 'Overlay construit : ' + str(overlay) + '. Aucun chargement en jeu demandé.')
                return
            self.emit('built', str(len(built)) + ' WAD construit(s). Démarrage du host officiel LTK v1.28.1 isolé ; ce n’est pas un moteur indépendant.')
            if self.cancel.is_set():
                self.emit('stopped', 'Arrêt demandé avant injection.')
                return
            conflicts = self.conflicts()
            if conflicts:
                raise RuntimeError('Processus concurrent apparu pendant la construction : ' + ', '.join(conflicts))
            p = subprocess.Popen([str(HOST)], cwd=HOST.parent, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding='utf-8', errors='replace', bufsize=1,
                                 creationflags=NO_WINDOW)
            self.process = p
            threading.Thread(target=self.cancel_monitor, args=(p, self.cancel), daemon=True).start()
            expected = {'config loglevel', 'config flags', 'config prefix'}
            self.command('config loglevel 16')
            self.command('config flags 4')
            self.command('config prefix ' + str(overlay.resolve()) + '\\')
            sent = False
            failed = False
            with (self.session / 'host.log').open('w', encoding='utf-8') as out:
                for raw in p.stdout:
                    out.write(raw)
                    out.flush()
                    line = raw.rstrip()
                    lower = line.lower()
                    if line.startswith('ok '):
                        expected = {x for x in expected if x not in lower}
                        if not expected and not sent and not self.cancel.is_set():
                            self.command('start scan')
                            sent = True
                    if 'scanning for game' in lower and sent and not self.verified:
                        self.emit('waiting_game', 'Host démarré, configuration acceptée. Lancez une partie d’entraînement ; aucun skin encore vérifié.')
                    elif opted_out_warning(line):
                        self.emit('warning', 'Avertissement non bloquant du moteur : ' + line)
                    elif host_failure(line):
                        failed = True
                        self.emit('failed', line)
                        self.stop()
                    elif 'overlay verified' in lower and not failed:
                        self.verified = True
                        self.emit('verified', 'Overlay accepté par la DLL. Attente de la redirection effective.')
                    elif 'redirected wad:' in lower and not failed:
                        wad = line.split('redirected wad:', 1)[-1].strip()
                        self.redirected.append(wad)
                        self.emit('redirected', 'Archive redirigée : ' + wad + '. Rendu visuel à confirmer en jeu.')
                    elif line.startswith('status ') and ' exited' in lower:
                        game_error = recent_game_error(self.started_at)
                        if game_error:
                            failed = True
                            (self.session / 'game-errors.log').write_text(game_error, encoding='utf-8')
                            self.emit('failed', 'Le jeu a signalé une erreur : ' + game_error)
                        else:
                            self.emit('game_ended', 'Processus du jeu terminé ; cela ne confirme pas le rendu. Redémarrez pour une nouvelle partie.')
                        self.stop()
            p.wait(timeout=10)
            if not failed:
                if self.cancel.is_set():
                    self.emit('stopped', 'Session arrêtée.')
                else:
                    self.emit('failed', 'Host terminé sans arrêt demandé, code ' + str(p.returncode))
        except Exception as exc:
            self.emit('failed', str(exc))
        finally:
            p = self.process
            if p and p.poll() is None:
                try:
                    p.terminate()
                    p.wait(timeout=5)
                except OSError:
                    pass
            self.process = None

    def cancel_monitor(self, process, cancel):
        deadline = time.monotonic() + 3600
        while not cancel.wait(.25):
            if process.poll() is not None:
                return
            if time.monotonic() >= deadline:
                self.emit('failed', 'Durée maximale de session atteinte (1 heure).')
                cancel.set()
        if process.poll() is None:
            try:
                with self.lock:
                    process.stdin.write('stop\n')
                    process.stdin.flush()
                process.stdin.close()
                process.wait(timeout=5)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    process.terminate()
