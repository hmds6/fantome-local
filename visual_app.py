"""Visual Windows frontend for the existing, tested local loader."""
from pathlib import Path
import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'vendor'))
import customtkinter as ctk
from core import Library, GAME
from loader import Loader
from ui_assets import Artwork, champion, destination, fetch_portraits

BG = '#0c0d15'
PANEL = '#131521'
CARD = '#191c2c'
LINE = '#292c40'
TEXT = '#f1f0fc'
MUTED = '#9398b5'
PURPLE = '#8d6bff'
GREEN = '#56d5ab'
COLUMNS = 4

class VisualApp:
    def __init__(self, window, data=None):
        self.window = window
        self.lib = Library(data or ROOT / 'data')
        self.loader = Loader(self.lib)
        self.art = Artwork(self.lib)
        self.queue = queue.Queue()
        self.busy = False
        self.focused = self.lib.state.get('selected')
        self.images = []
        self.cards = {}
        self.view_name = 'library'
        self.library_mtime = self.lib.file.stat().st_mtime_ns if self.lib.file.exists() else 0
        self.proof = {}
        proof = ROOT / 'verification-game-success.json'
        if proof.exists():
            try:
                self.proof = json.loads(proof.read_text(encoding='utf-8'))
            except ValueError:
                pass
        ctk.set_appearance_mode('dark')
        ctk.set_default_color_theme('blue')
        window.title('Fantome Local — ta collection, en jeu')
        window.geometry('1320x880')
        window.minsize(1160, 780)
        window.configure(fg_color=BG)
        window.protocol('WM_DELETE_WINDOW', self.close)
        window.grid_columnconfigure(1, weight=1)
        window.grid_rowconfigure(0, weight=1)
        self.make_sidebar()
        self.main = ctk.CTkFrame(window, fg_color=BG, corner_radius=0)
        self.main.grid(row=0, column=1, sticky='nsew', padx=(26, 24), pady=(22, 16))
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=1)
        top = ctk.CTkFrame(self.main, fg_color='transparent')
        top.grid(row=0, column=0, sticky='ew', pady=(0, 20))
        top.grid_columnconfigure(0, weight=1)
        self.page_title = self.label(top, 'Ta bibliothèque', 29, True)
        self.page_title.grid(row=0, column=0, sticky='w')
        self.collection_count = self.label(top, '', 12, colour=MUTED)
        self.collection_count.grid(row=1, column=0, sticky='w', pady=(5, 0))
        self.add_button = self.button(top, '+  Ajouter des mods', self.add, width=180)
        self.add_button.grid(row=0, column=1, rowspan=2, sticky='e')
        self.content = ctk.CTkFrame(self.main, fg_color='transparent')
        self.content.grid(row=1, column=0, sticky='nsew')
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_columnconfigure(1, weight=0, minsize=330)
        self.content.grid_rowconfigure(0, weight=1)
        self.make_library()
        self.make_details()
        self.make_logs()
        self.make_help()
        self.make_launchbar()
        self.refresh()
        self.show_view('library')
        self.write('Interface prête. Les aperçus, la bibliothèque et les journaux restent sur ce PC.')
        self.lib.log('UI_READY', 'Interface visuelle ; moteur de chargement inchangé.')
        self.fetch_portraits()
        window.after(500, self.poll)

    def fetch_portraits(self):
        mods = list(self.lib.state['mods'])
        def work():
            try:
                changed = fetch_portraits(mods)
            except Exception as exc:
                self.lib.log('PORTRAITS_FAILED', str(exc))
                changed = False
            self.queue.put(('portraits', changed))
        threading.Thread(target=work, daemon=True).start()

    def label(self, parent, text='', size=13, bold=False, colour=TEXT, **kwargs):
        return ctk.CTkLabel(parent, text=text, text_color=colour,
                            font=ctk.CTkFont(family='Segoe UI', size=size, weight='bold' if bold else 'normal'), **kwargs)

    def button(self, parent, text, command, secondary=False, **kwargs):
        return ctk.CTkButton(parent, text=text, command=command, height=40, corner_radius=10,
                             fg_color=CARD if secondary else PURPLE,
                             hover_color='#292b45' if secondary else '#a18aff',
                             text_color=TEXT, font=ctk.CTkFont(family='Segoe UI', size=13, weight='bold'), **kwargs)

    def make_sidebar(self):
        side = ctk.CTkFrame(self.window, width=190, fg_color='#10111b', corner_radius=0)
        side.grid(row=0, column=0, sticky='ns')
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(6, weight=1)
        mark = ctk.CTkFrame(side, width=48, height=48, corner_radius=16, fg_color=PURPLE)
        mark.grid(row=0, column=0, sticky='w', padx=22, pady=(28, 10))
        mark.grid_propagate(False)
        self.label(mark, 'F', 27, True).place(relx=.5, rely=.5, anchor='center')
        self.label(side, 'FANTOME', 20, True).grid(row=1, column=0, sticky='w', padx=22)
        self.label(side, 'L O C A L', 10, colour=MUTED).grid(row=2, column=0, sticky='w', padx=24, pady=(0, 36))
        self.nav = {}
        for row, (key, text) in enumerate([('library', '▦   Bibliothèque'), ('logs', '≡   Journaux'), ('help', '?   Bien démarrer')], 3):
            button = self.button(side, text, lambda k=key: self.show_view(k), secondary=True, width=158, anchor='w')
            button.grid(row=row, column=0, padx=16, pady=5)
            self.nav[key] = button
        installed = ctk.CTkFrame(side, fg_color=PANEL, corner_radius=12)
        installed.grid(row=7, column=0, sticky='ew', padx=16, pady=(0, 14))
        self.label(installed, '●  League détecté' if (GAME / 'Game').exists() else '●  League introuvable', 11,
                   colour=GREEN if (GAME / 'Game').exists() else '#ffb175').pack(anchor='w', padx=12, pady=(13, 3))
        self.label(installed, 'Chargement local\nMoteur LTK 1.28.1', 10, colour=MUTED, justify='left').pack(anchor='w', padx=12, pady=(0, 12))
        self.label(side, 'Fantome Local  •  Desktop', 10, colour='#5f6687').grid(row=8, column=0, pady=(0, 18))

    def make_library(self):
        self.library_view = ctk.CTkFrame(self.content, fg_color='transparent')
        self.library_view.grid_columnconfigure(0, weight=1)
        self.library_view.grid_rowconfigure(1, weight=1)
        filters = ctk.CTkFrame(self.library_view, fg_color='transparent')
        filters.grid(row=0, column=0, sticky='ew', pady=(0, 14))
        filters.grid_columnconfigure(0, weight=1)
        self.search = tk.StringVar()
        self.search_entry = ctk.CTkEntry(filters, textvariable=self.search, placeholder_text='Rechercher un skin, un champion…',
                                       height=42, fg_color=PANEL, border_color=LINE, corner_radius=10)
        self.search_entry.grid(row=0, column=0, sticky='ew', padx=(0, 10))
        self.champion_filter = ctk.CTkOptionMenu(filters, values=['Tous les champions'], command=lambda _: self.refresh(),
                                               height=42, width=175, fg_color=CARD, button_color=LINE, button_hover_color='#44405f',
                                               font=ctk.CTkFont(size=12))
        self.champion_filter.grid(row=0, column=1)
        self.gallery = ctk.CTkScrollableFrame(self.library_view, fg_color='transparent', corner_radius=0,
                                             scrollbar_button_color=LINE, scrollbar_button_hover_color=PURPLE)
        self.gallery.grid(row=1, column=0, sticky='nsew')
        self.gallery.grid_columnconfigure(tuple(range(COLUMNS)), weight=1, uniform='cards')
        # CustomTkinter scrolls 1 px per unit on Windows (20 px per wheel notch); make it 80 px.
        self.gallery._parent_canvas.configure(yscrollincrement=4)
        self.card_width = 0
        # Size cards from the visible viewport: the inner frame grows with its cards and would feed back.
        self.gallery._parent_canvas.bind('<Configure>', self.gallery_resized, add='+')
        self.search.trace_add('write', lambda *_: self.refresh())

    def make_details(self):
        self.detail_panel = ctk.CTkFrame(self.content, fg_color=PANEL, corner_radius=16, width=330)
        self.detail_panel.grid_propagate(False)
        self.detail_panel.grid_columnconfigure(0, weight=1)
        self.hero = self.label(self.detail_panel, '', width=298, height=238)
        self.hero.grid(row=0, column=0, padx=16, pady=(16, 4))
        self.art_caption = self.label(self.detail_panel, '', 10, colour=MUTED, wraplength=290)
        self.art_caption.grid(row=1, column=0, padx=18, sticky='w')
        self.detail_champion = self.label(self.detail_panel, '', 11, True, colour=PURPLE)
        self.detail_champion.grid(row=2, column=0, padx=20, sticky='w', pady=(18, 4))
        self.detail_title = self.label(self.detail_panel, 'Choisis un mod', 21, True, wraplength=286, justify='left', anchor='w')
        self.detail_title.grid(row=3, column=0, padx=20, sticky='ew')
        self.detail_meta = self.label(self.detail_panel, '', 11, colour=MUTED, wraplength=286, justify='left', anchor='w')
        self.detail_meta.grid(row=4, column=0, padx=20, sticky='ew', pady=(8, 14))
        self.detail_description = ctk.CTkTextbox(self.detail_panel, height=110, fg_color='transparent', text_color=MUTED,
                                               wrap='word', font=ctk.CTkFont(size=12), border_width=0)
        self.detail_description.grid(row=5, column=0, padx=14, sticky='nsew')
        self.detail_panel.grid_rowconfigure(5, weight=1)
        self.validation = self.label(self.detail_panel, '', 11, colour=MUTED, wraplength=286, justify='left')
        self.validation.grid(row=6, column=0, padx=20, sticky='w', pady=10)
        self.activate_button = self.button(self.detail_panel, 'Activer ce mod', self.toggle)
        self.activate_button.grid(row=7, column=0, padx=18, pady=(0, 18), sticky='ew')

    def make_logs(self):
        self.logs_view = ctk.CTkFrame(self.content, fg_color=PANEL, corner_radius=16)
        self.label(self.logs_view, 'Ce qui se passe, en direct', 20, True).pack(anchor='w', padx=22, pady=(22, 6))
        self.label(self.logs_view, 'Les événements affichés concernent cette application. Le rendu doit être vérifié dans le jeu.',
                   12, colour=MUTED, wraplength=720, justify='left').pack(anchor='w', padx=22, pady=(0, 16))
        self.output = ctk.CTkTextbox(self.logs_view, fg_color='#0e1019', text_color='#bdc4dd', corner_radius=10,
                                    font=ctk.CTkFont(family='Consolas', size=12), wrap='word', state='disabled')
        self.output.pack(fill='both', expand=True, padx=20, pady=(0, 14))
        tools = ctk.CTkFrame(self.logs_view, fg_color='transparent')
        tools.pack(fill='x', padx=20, pady=(0, 18))
        self.button(tools, 'Construire sans charger', self.build, secondary=True).pack(side='left')
        self.button(tools, 'Ouvrir les journaux', self.open_sessions, secondary=True).pack(side='left', padx=10)

    def make_help(self):
        self.help_view = ctk.CTkScrollableFrame(self.content, fg_color=PANEL, corner_radius=16)
        self.label(self.help_view, 'De ta bibliothèque à la Faille.', 25, True).pack(anchor='w', padx=24, pady=(25, 8))
        self.label(self.help_view, 'Un mod à la fois. Une nouvelle partie après le démarrage du chargeur.', 13,
                   colour=MUTED, wraplength=700).pack(anchor='w', padx=24, pady=(0, 25))
        for number, title, body in [
            ('01', 'Choisis ton mod', 'Recherche ton champion, clique sur une carte, puis sur Activer ce mod. Le badge SÉLECTIONNÉ indique ton choix.'),
            ('02', 'Prépare le chargement', 'Reviens au client entre deux parties. Clique Démarrer et attends que le chargeur soit prêt. Garde cette application ouverte.'),
            ('03', 'Choisis le bon skin dans League', 'Sur BASE / Classique : utilise le skin Classique, sans chroma au premier essai. Sur PROJECT ou True Damage : utilise ce skin de destination.'),
            ('04', 'Lance une nouvelle partie', 'Commence par un entraînement. Un mod Yasuo ne change pas Irelia. Les ressources sont chargées sur ton PC ; le skin n’est pas débloqué dans ton compte Riot.'),
            ('05', 'Si quelque chose bloque', 'Consulte Journaux. Une importation réussie n’est pas une preuve de compatibilité en jeu. Yasuo Héraut de la nuit a été testé ici ; chaque autre mod reste à vérifier.'),
        ]:
            box = ctk.CTkFrame(self.help_view, fg_color=CARD, corner_radius=12)
            box.pack(fill='x', padx=24, pady=(0, 12))
            self.label(box, number, 14, True, colour=PURPLE).pack(anchor='w', padx=18, pady=(14, 3))
            self.label(box, title, 17, True).pack(anchor='w', padx=18)
            self.label(box, body, 13, colour=MUTED, wraplength=670, justify='left').pack(anchor='w', padx=18, pady=(6, 16))

    def make_launchbar(self):
        bar = ctk.CTkFrame(self.main, fg_color=PANEL, corner_radius=14, border_width=1, border_color=LINE)
        bar.grid(row=2, column=0, sticky='ew', pady=(18, 0))
        bar.grid_columnconfigure(0, weight=1)
        self.active_name = self.label(bar, '', 13, True, anchor='w', wraplength=620)
        self.active_name.grid(row=0, column=0, sticky='w', padx=18, pady=(13, 2))
        self.status = tk.StringVar(value='Choisis un mod, puis démarre avant ta partie.')
        self.status_label = self.label(bar, '', 11, colour=MUTED, anchor='w', wraplength=620)
        self.status_label.configure(textvariable=self.status)
        self.status_label.grid(row=1, column=0, sticky='w', padx=18, pady=(0, 11))
        self.start_button = self.button(bar, '▶  Démarrer', self.start, width=140)
        self.start_button.grid(row=0, column=1, rowspan=2, padx=8)
        self.stop_button = self.button(bar, 'Arrêter', self.stop, secondary=True, width=90)
        self.stop_button.grid(row=0, column=2, rowspan=2, padx=(0, 14))
        self.progress = ctk.CTkProgressBar(bar, height=3, corner_radius=0, progress_color=PURPLE, fg_color=PANEL)
        self.progress.grid(row=2, column=0, columnspan=3, sticky='ew', padx=12)
        self.progress.set(0)

    def show_view(self, name):
        self.view_name = name
        for widget in (self.library_view, self.detail_panel, self.logs_view, self.help_view):
            widget.grid_remove()
        if name == 'library':
            self.library_view.grid(row=0, column=0, sticky='nsew', padx=(0, 18))
            self.detail_panel.grid(row=0, column=1, sticky='nsew')
        else:
            view = self.logs_view if name == 'logs' else self.help_view
            view.grid(row=0, column=0, columnspan=2, sticky='nsew')
        self.page_title.configure(text={'library': 'Ta bibliothèque', 'logs': 'Journal de chargement', 'help': 'Bien démarrer'}[name])
        for key, button in self.nav.items():
            button.configure(fg_color='#25213d' if key == name else 'transparent', text_color='#c5b5ff' if key == name else MUTED)

    def confirmed(self, mod):
        return self.proof.get('visual_confirmed') is True and self.proof.get('mod_sha256') == mod['sha256']

    def refresh(self):
        for widget in self.gallery.winfo_children():
            widget.destroy()
        self.images = []
        self.cards = {}
        mods = sorted(self.lib.state['mods'], key=lambda m: (champion(m).casefold(), m['name'].casefold()))
        choices = ['Tous les champions'] + sorted({champion(m) for m in mods})
        current_filter = self.champion_filter.get()
        self.champion_filter.configure(values=choices)
        if current_filter not in choices:
            self.champion_filter.set('Tous les champions')
        query = self.search.get().strip().casefold()
        visible = []
        for mod in mods:
            haystack = ' '.join([mod['name'], champion(mod), *mod.get('source_files', [])]).casefold()
            if query and query not in haystack:
                continue
            if self.champion_filter.get() != 'Tous les champions' and champion(mod) != self.champion_filter.get():
                continue
            visible.append(mod)
        self.visible_mods = visible
        for index, mod in enumerate(visible):
            self.make_card(mod, index)
        if not visible:
            self.label(self.gallery, 'Aucun mod trouvé.\nEssaie un autre champion ou ajoute un .fantome.', 15,
                       colour=MUTED, justify='center').grid(row=0, column=0, columnspan=COLUMNS, padx=30, pady=65)
        self.collection_count.configure(text=f"{len(mods)} mods dans ta collection  •  {len(visible)} affichés")
        if not any(m['sha256'] == self.focused for m in mods):
            self.focused = visible[0]['sha256'] if visible else None
        if self.focused:
            self.select(self.focused)
        selected = next((m for m in mods if m['sha256'] == self.lib.state.get('selected')), None)
        self.active_name.configure(text='PROCHAIN CHARGEMENT  ·  ' + (selected['name'] if selected else 'Aucun mod activé'))

    def cover_size(self):
        width = max(130, (self.gallery._parent_canvas.winfo_width() - 10) // COLUMNS - 28)
        return width, width * 9 // 16

    def gallery_resized(self, _):
        if abs(self.cover_size()[0] - self.card_width) > 12:
            if getattr(self, 'resize_job', None):
                self.window.after_cancel(self.resize_job)
            self.resize_job = self.window.after(150, self.refresh)

    def make_card(self, mod, index):
        digest = mod['sha256']
        selected = digest == self.lib.state.get('selected')
        card = ctk.CTkFrame(self.gallery, fg_color=CARD, corner_radius=13, border_width=2,
                            border_color=PURPLE if digest == self.focused else LINE)
        card.grid(row=index // COLUMNS, column=index % COLUMNS, sticky='nsew', padx=4, pady=(0, 8))
        card.grid_columnconfigure(0, weight=1)
        size = self.cover_size()
        self.card_width = size[0]
        photo, kind = self.art.cover(mod, size)
        image = ctk.CTkImage(light_image=photo, dark_image=photo, size=size)
        self.images.append(image)
        cover = self.label(card, '', image=image, height=size[1])
        cover.grid(row=0, column=0, sticky='ew', padx=6, pady=(6, 2))
        meta = self.label(card, champion(mod).upper() + ('  ·  SÉLECTIONNÉ' if selected else ''), 9, True,
                          colour=GREEN if selected else '#b29bff', anchor='w')
        meta.grid(row=1, column=0, padx=10, sticky='ew', pady=(3, 0))
        title = self.label(card, mod['name'], 11, True, wraplength=size[0] - 4, justify='left', anchor='w', height=34)
        title.grid(row=2, column=0, padx=10, sticky='ew')
        badge = self.label(card, '● Testé en jeu' if self.confirmed(mod) else 'Skin cible : ' + destination(mod), 9,
                           colour=GREEN if self.confirmed(mod) else MUTED, anchor='w', height=16)
        badge.grid(row=3, column=0, sticky='ew', padx=10, pady=(0, 8))
        for widget in (card, cover, meta, title, badge):
            widget.bind('<Button-1>', lambda _, d=digest: self.select(d))
        self.cards[digest] = card

    def select(self, digest):
        mod = next((m for m in self.lib.state['mods'] if m['sha256'] == digest), None)
        if not mod:
            return
        self.focused = digest
        for key, card in self.cards.items():
            card.configure(border_color=PURPLE if key == digest else LINE)
        photo, caption = self.art.cover(mod, (298, 238))
        self.hero_image = ctk.CTkImage(light_image=photo, dark_image=photo, size=(298, 238))
        self.hero.configure(image=self.hero_image)
        self.art_caption.configure(text=caption)
        self.detail_champion.configure(text=champion(mod).upper())
        self.detail_title.configure(text=mod['name'])
        author = mod.get('author') or 'Auteur non indiqué'
        self.detail_meta.configure(text=f"{author}\nSkin de destination : {destination(mod)}")
        self.detail_description.configure(state='normal')
        self.detail_description.delete('1.0', 'end')
        self.detail_description.insert('1.0', mod.get('description') or 'Aucune description fournie. Vérifie le skin de destination avant de lancer le chargement.')
        self.detail_description.configure(state='disabled')
        self.validation.configure(text='● Rendu confirmé en jeu sur ce PC' if self.confirmed(mod) else 'Fichier importé • rendu de ce mod à vérifier en jeu',
                                  text_color=GREEN if self.confirmed(mod) else MUTED)
        self.activate_button.configure(text='Désactiver ce mod' if digest == self.lib.state.get('selected') else 'Activer ce mod')

    def write(self, message):
        self.output.configure(state='normal')
        self.output.insert('end', message + '\n')
        self.output.see('end')
        self.output.configure(state='disabled')

    def notify(self, message, error=False):
        self.status.set(message)
        self.status_label.configure(text_color='#ffad99' if error else MUTED)
        self.write(('ERREUR  ' if error else '') + message)

    def error(self, exc):
        self.lib.log('ERROR', str(exc))
        self.notify(str(exc), True)

    def guarded(self):
        if self.busy or self.loader.active:
            self.notify('Un chargement est actif. Arrête-le entre deux parties pour changer de mod.')
            return True
        return False

    def toggle(self):
        if self.guarded():
            return
        if not self.focused:
            self.notify('Choisis d’abord une carte dans la bibliothèque.')
            return
        self.lib.select(None if self.lib.state.get('selected') == self.focused else self.focused)
        self.library_mtime = self.lib.file.stat().st_mtime_ns
        self.refresh()
        self.notify('Choix enregistré. Clique Démarrer avant ta prochaine partie.')

    def add(self):
        if self.guarded():
            return
        paths = filedialog.askopenfilenames(title='Ajouter des mods', filetypes=[('Mods Fantome', '*.fantome')])
        if paths:
            self.import_paths(paths)

    def import_paths(self, paths):
        if self.guarded():
            return
        self.busy = True
        self.add_button.configure(state='disabled')
        self.notify('Import et vérification des fichiers…')
        def work():
            last = None
            errors = []
            for path in paths:
                try:
                    last = self.lib.add(path)
                except Exception as exc:
                    errors.append(Path(path).name + ' : ' + str(exc))
            self.queue.put(('import', (last, errors)))
        threading.Thread(target=work, daemon=True).start()

    def start(self):
        self.launch(False)

    def build(self):
        self.launch(True)

    def launch(self, build_only):
        if self.guarded():
            return
        try:
            session = self.loader.start(build_only=build_only)
            self.write('SESSION  ' + str(session))
            self.progress.configure(mode='indeterminate')
            self.progress.start()
        except Exception as exc:
            self.error(exc)

    def stop(self):
        self.loader.stop()
        self.notify('Arrêt demandé. Le jeu et les autres applications restent ouverts.')

    def open_sessions(self):
        path = self.lib.root / 'sessions'
        path.mkdir(exist_ok=True)
        os.startfile(path)

    def close(self):
        if self.busy:
            self.notify('L’import est en cours. Attends sa fin avant de fermer.')
            return
        self.loader.stop()
        if self.loader.active:
            self.window.after(250, self.close)
        else:
            self.window.destroy()

    def poll(self):
        try:
            mtime = self.lib.file.stat().st_mtime_ns if self.lib.file.exists() else 0
            if not self.busy and mtime != self.library_mtime:
                self.lib.state = json.loads(self.lib.file.read_text(encoding='utf-8'))
                self.library_mtime = mtime
                self.refresh()
            while True:
                event = self.loader.events.get_nowait()
                self.lib.log('LOADER_' + event['state'].upper(), event['message'])
                self.write(event['time_utc'][11:19] + '  ' + event['state'].upper() + '  ' + event['message'])
                self.status.set(event['message'])
                self.status_label.configure(text_color='#ffad99' if event['state'] == 'failed' else GREEN if event['state'] in ('verified', 'redirected', 'waiting_game') else MUTED)
                if event['state'] != 'building':
                    self.progress.stop()
                    self.progress.configure(mode='determinate')
                    self.progress.set(1 if event['state'] in ('built', 'waiting_game', 'verified', 'redirected') else 0)
        except queue.Empty:
            pass
        except (OSError, ValueError) as exc:
            self.error(exc)
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == 'portraits':
                    if payload:
                        self.art.cache.clear()
                        self.art.covers.clear()
                        self.refresh()
                    continue
                last, errors = payload
                self.busy = False
                self.add_button.configure(state='normal')
                self.library_mtime = self.lib.file.stat().st_mtime_ns
                if last:
                    self.focused = last['sha256']
                self.refresh()
                self.notify('Import terminé.' if not errors else 'Import terminé avec des erreurs ; consulte les journaux.', bool(errors))
                for error in errors:
                    self.write(error)
                self.fetch_portraits()
        except queue.Empty:
            pass
        active = self.busy or self.loader.active
        self.start_button.configure(state='disabled' if active else 'normal')
        self.activate_button.configure(state='disabled' if active else 'normal')
        self.window.after(700, self.poll)

def main():
    window = ctk.CTk()
    try:
        app = VisualApp(window)
        if '--start' in sys.argv:
            window.after(1000, app.start)
        window.mainloop()
    except Exception as exc:
        messagebox.showerror('Fantome Local', str(exc))
        raise

if __name__ == '__main__':
    main()
