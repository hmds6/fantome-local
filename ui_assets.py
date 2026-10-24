"""Local artwork: mod previews first, then a cached Data Dragon champion splash, then a placeholder."""
from pathlib import Path
import hashlib
import io
import json
import re
import unicodedata
import urllib.request
import zipfile
from PIL import Image, ImageOps, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
PORTRAITS = ROOT / 'assets/champions'
INDEX = PORTRAITS / 'champions.json'
DDRAGON = 'https://ddragon.leagueoflegends.com'

def load_index():
    try:
        return json.loads(INDEX.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}

CHAMPION_NAMES = load_index()  # Data Dragon id -> French display name

def champion_id(mod):
    """Data Dragon id taken from the WAD name (e.g. WAD/KSante.wad.client), else from the mod name."""
    known = {k.casefold(): k for k in CHAMPION_NAMES}
    for path in mod.get('wads', []):
        parts = path.replace('\\', '/').split('/')
        if len(parts) > 1 and parts[1].casefold().endswith('.wad.client'):
            stem = parts[1][:-len('.wad.client')]
            if not CHAMPION_NAMES or stem.casefold() in known:
                return known.get(stem.casefold(), stem)
    words = simplify_words(mod['name'])
    for key, name in sorted(CHAMPION_NAMES.items(), key=lambda kv: -len(kv[1])):
        if simplify_words(name) in words or simplify_words(key) in words:
            return key
    return None

def simplify_words(text):
    """' kai sa ' style form, so that short names like Vi only match whole words."""
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().casefold()
    return ' ' + ' '.join(re.findall(r'[a-z0-9]+', text)) + ' '

def champion(mod):
    key = champion_id(mod)
    return CHAMPION_NAMES.get(key, key) if key else 'Autre'

def fetch_portraits(mods, timeout=10):
    """Download the champion index and missing splashes into assets/champions. Returns True if anything changed."""
    global CHAMPION_NAMES
    PORTRAITS.mkdir(parents=True, exist_ok=True)
    changed = False
    if not CHAMPION_NAMES:
        with urllib.request.urlopen(DDRAGON + '/api/versions.json', timeout=timeout) as r:
            version = json.load(r)[0]
        with urllib.request.urlopen(f'{DDRAGON}/cdn/{version}/data/fr_FR/champion.json', timeout=timeout) as r:
            data = json.load(r)['data']
        CHAMPION_NAMES = {key: value['name'] for key, value in data.items()}
        INDEX.write_text(json.dumps(CHAMPION_NAMES, ensure_ascii=False, indent=1), encoding='utf-8')
        changed = True
    for key in sorted({champion_id(m) for m in mods} - {None}):
        target = PORTRAITS / (key + '.jpg')
        if target.exists() or key not in CHAMPION_NAMES:
            continue
        try:
            with urllib.request.urlopen(f'{DDRAGON}/cdn/img/champion/splash/{key}_0.jpg', timeout=timeout) as r:
                img = Image.open(io.BytesIO(r.read())).convert('RGB')
        except Exception:
            continue
        img.save(target, quality=90)
        changed = True
    return changed

def destination(mod):
    text = (' '.join([mod['name'], *mod.get('source_files', [])])).upper()
    if 'TRUE_DAMAGE' in text or 'TRUE DAMAGE' in text:
        return 'True Damage'
    if 'SUR_PROJECT' in text or 'SUR PROJECT' in text:
        return 'PROJECT'
    if 'SUR_BASE' in text or 'SUR BASE' in text or 'SUR CLASSIQUE' in text or 'SUR_CLASSIQUE' in text:
        return 'Classique'
    return 'Voir la description'

class Artwork:
    def __init__(self, library):
        self.library = library
        self.cache = {}

    def original(self, mod):
        key = mod['sha256']
        if key in self.cache:
            return self.cache[key]
        preview = ROOT / 'assets/previews' / (key + '.png')
        if preview.exists():
            try:
                result = (Image.open(preview).convert('RGB'), 'Visuel fourni dans le mod')
                self.cache[key] = result
                return result
            except Exception:
                pass
        try:
            path = self.library.archives / (key + '.fantome')
            with zipfile.ZipFile(path) as archive:
                candidates = [i for i in archive.infolist() if i.filename.lower().startswith('meta/')
                              and i.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))
                              and i.file_size < 20 * 1024**2]
                for entry in candidates:
                    try:
                        img = Image.open(io.BytesIO(archive.read(entry)))
                        if img.width * img.height > 30_000_000:
                            continue
                        img = img.convert('RGB')
                        img.thumbnail((1280, 1280))
                        preview.parent.mkdir(parents=True, exist_ok=True)
                        img.save(preview)
                        self.cache[key] = (img, 'Visuel fourni dans le mod')
                        return self.cache[key]
                    except Exception:
                        continue
        except (OSError, zipfile.BadZipFile):
            pass
        portrait = PORTRAITS / ((champion_id(mod) or 'Autre') + '.jpg')
        if portrait.exists():
            self.cache[key] = (Image.open(portrait).convert('RGB'), 'Portrait du champion • aperçu du mod indisponible')
            return self.cache[key]
        colour = hashlib.sha256(champion(mod).encode()).digest()
        img = Image.new('RGB', (640, 400), (20 + colour[0] // 7, 22 + colour[1] // 8, 45 + colour[2] // 5))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 100)
        except OSError:
            font = ImageFont.load_default()
        draw.text((50, 130), champion(mod)[:2].upper(), font=font, fill='#bbb0ff')
        self.cache[key] = (img, 'Illustration de remplacement • aucun aperçu fourni')
        return self.cache[key]

    def cover(self, mod, size):
        image, label = self.original(mod)
        return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(.5, .24)), label
