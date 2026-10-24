"""Local WAD v3.4 overlay writer; preserves Riot header provenance and stored data.

Format references: LeagueToolkit cslol-manager toc.hpp; league-mod wad_builder.rs.
No source code from those projects is copied here. Runtime stays in LTK host/DLL.
"""
from pathlib import Path
import io
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
import xxhash
import zstandard as zstd

ENTRY = struct.Struct('<QIIIB3sQ')
HEADER = 268
COUNT_END = 272
MAX_CHUNK = 512 * 1024**2

class Wad:
    def __init__(self, path):
        self.path = Path(path)
        self.size = self.path.stat().st_size
        with self.path.open('rb') as f:
            self.header = f.read(HEADER)
            if self.header[:4] != b'RW\x03\x04':
                raise ValueError('WAD v3.4 requis : ' + str(path))
            n = struct.unpack('<I', f.read(4))[0]
            if n > 2000000 or COUNT_END + n * ENTRY.size > self.size:
                raise ValueError('Table WAD invalide : ' + str(path))
            toc = f.read(n * ENTRY.size)
        self.start = COUNT_END + n * ENTRY.size
        self.entries = {}
        previous = -1
        for e in ENTRY.iter_unpack(toc):
            h, off, size, usize, flags, sub, checksum = e
            if h <= previous or off < self.start or off + size > self.size:
                raise ValueError('Entrée WAD invalide : ' + hex(h) + ' dans ' + str(path))
            self.entries[h] = e
            previous = h

    def raw(self, e):
        if e[2] > MAX_CHUNK:
            raise ValueError('Chunk trop volumineux pour la validation locale : ' + hex(e[0]))
        with self.path.open('rb') as f:
            f.seek(e[1])
            data = f.read(e[2])
        if len(data) != e[2] or xxhash.xxh3_64_intdigest(data) != e[6]:
            raise ValueError('Checksum de chunk invalide : ' + hex(e[0]) + ' dans ' + str(self.path))
        return data

    def decode(self, e):
        data = self.raw(e)
        codec = e[4] & 15
        if codec == 0:
            decoded = data
        elif codec in (3, 4):
            # Multi chunks made of zstd frames can be decoded without rewriting
            # their subchunk TOC. Mixed raw subchunks fail here and are rejected.
            with zstd.ZstdDecompressor().stream_reader(io.BytesIO(data), read_across_frames=True) as stream:
                decoded = stream.read(MAX_CHUNK + 1)
        else:
            raise ValueError('Codec de remplacement non pris en charge : ' + str(codec))
        if len(decoded) > MAX_CHUNK or len(decoded) != e[3]:
            raise ValueError('Taille décompressée invalide : ' + hex(e[0]))
        return decoded

def validate(path):
    wad = Wad(path)
    with wad.path.open('rb') as f:
        for e in wad.entries.values():
            f.seek(e[1])
            data = f.read(e[2])
            if len(data) != e[2] or xxhash.xxh3_64_intdigest(data) != e[6]:
                raise ValueError('WAD généré invalide, chunk ' + hex(e[0]))
    return len(wad.entries)

def build_one(source, target, overrides, cancel):
    combined = sorted(set(source.entries) | set(overrides))
    new_start = COUNT_END + len(combined) * ENTRY.size
    delta = new_start - source.start
    target.parent.mkdir(parents=True, exist_ok=True)
    records = []
    with source.path.open('rb') as src, target.open('w+b') as out:
        out.write(source.header)
        out.write(struct.pack('<I', len(combined)))
        out.write(bytes(len(combined) * ENTRY.size))
        src.seek(source.start)
        while chunk := src.read(8 * 1024**2):
            if cancel.is_set():
                raise InterruptedError('Construction annulée.')
            out.write(chunk)
        for h in combined:
            if h in overrides:
                data, usize, codec = overrides[h]
                offset = out.tell()
                e = (h, offset, len(data), usize, codec, b'\0\0\0', xxhash.xxh3_64_intdigest(data))
                out.write(data)
            else:
                old = source.entries[h]
                e = (h, old[1] + delta, *old[2:])
            if e[1] + e[2] > 0xffffffff:
                raise ValueError('WAD supérieur à la limite d’adressage 32 bits.')
            records.append(e)
        out.seek(COUNT_END)
        for e in records:
            out.write(ENTRY.pack(*e))
    count = validate(target)
    result = Wad(target)
    if result.header != source.header:
        raise ValueError('En-tête original non préservé.')
    return dict(chunks=count, overrides=len(overrides), original_header_preserved=True,
                all_chunk_checksums_valid=True)

def build_overlay(folder, game, overlay, cancel, progress):
    folder, game, overlay = Path(folder), Path(game), Path(overlay)
    files = list((game / 'DATA/FINAL').rglob('*.wad.client'))
    names = {}
    for path in files:
        names.setdefault(path.name.lower(), []).append(path)
    changes = {}
    destinations = {}
    filtered = 0
    requested = list((folder / 'WAD').rglob('*.wad.client'))
    for modfile in requested:
        matches = names.get(modfile.name.lower(), [])
        if len(matches) != 1:
            raise ValueError('WAD cible absent ou ambigu : ' + modfile.name)
        original = Wad(matches[0])
        mod = Wad(modfile)
        for h, entry in mod.entries.items():
            if cancel.is_set():
                raise InterruptedError('Construction annulée.')
            decoded = mod.decode(entry)
            if h in original.entries and decoded == original.decode(original.entries[h]):
                filtered += 1
                continue
            if entry[4] & 15 in (0, 3):
                encoded = (mod.raw(entry), len(decoded), entry[4] & 15)
            else:
                encoded = (zstd.ZstdCompressor(level=3).compress(decoded), len(decoded), 3)
            if h in changes and changes[h] != encoded:
                raise ValueError('Deux WAD du mod modifient différemment le même hash : ' + hex(h))
            changes[h] = encoded
            destinations.setdefault(matches[0], set()).add(h)
    if not changes:
        raise ValueError('Le mod ne contient aucun changement réel pour cette installation.')
    progress(f'{filtered} entrées identiques ignorées ; {len(changes)} changements réels. Recherche des archives partagées.')
    # Every original archive holding an overridden path gets the same stored
    # bytes, so cross-WAD compressed checksums remain consistent.
    readers = {}
    for path in files:
        if cancel.is_set():
            raise InterruptedError('Construction annulée.')
        source = Wad(path)
        affected = set(source.entries) & set(changes)
        affected |= destinations.get(path, set())
        if affected:
            readers[path] = (source, affected)
    import shutil
    needed = sum(source.size for source, _ in readers.values()) + sum(len(x[0]) for x in changes.values()) * len(readers) + 512 * 1024**2
    overlay.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(overlay).free < needed:
        raise ValueError('Espace libre insuffisant pour cet overlay.')
    from core import sha256
    identities = {str(path): sha256(path) for path in readers}
    reports = {}
    for path, (source, affected) in readers.items():
        rel = path.relative_to(game)
        progress('Écriture et validation : ' + str(rel))
        reports[str(rel)] = build_one(source, overlay / rel, {h: changes[h] for h in affected}, cancel)
    for path in readers:
        if sha256(path) != identities[str(path)]:
            raise ValueError('Archive originale changée pendant la construction : ' + str(path))
    return dict(originals_unchanged=True, originals_sha256=identities, wads=reports,
                identical_entries_filtered=filtered, real_overrides=len(changes))
