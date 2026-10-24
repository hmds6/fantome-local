"""Local-only artwork: mod previews first, clearly labelled champion fallback."""
from pathlib import Path
import hashlib
import io
import zipfile
from PIL import Image, ImageOps, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
CHAMPIONS = ('Yasuo', 'Yone', 'Irelia', 'Qiyana', 'Viego', 'Riven', 'Sett', 'Fiora', 'KSante', 'Nautilus', 'Renekton', 'Vayne')

def champion(mod):
    for name in CHAMPIONS:
        if name.casefold() in mod['name'].casefold():
            return name
    for path in mod.get('wads', []):
        root = path.replace('\\', '/').split('/')[1:2]
        if root:
            for name in CHAMPIONS:
                if root[0].casefold().startswith(name.casefold() + '.wad'):
                    return name
    return 'Autre'

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
        portrait = ROOT / 'assets/champions' / (champion(mod) + '.jpg')
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
