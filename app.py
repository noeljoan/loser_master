#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Loser Master 2.0 - (c) 2026 - N. Joan - Generateur Lotto de tickets perdus
==========================================================================
Pour ceux qui n’ont toujours pas gagné… mais qui n’abandonnent pas.

Avec un moteur de calcul (voir wheel.py).

Usage : python app.py
"""

import csv
import json
import os
import random
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

from wheel import (generate_wheel, apply_numbers, guarantee_table,
                    score_grids_against_draw, single_grid_odds, system_odds)
from analysis import (parse_csv_text, frequency_table, bonus_frequency_table,
                       chi_square_uniformity_test, sort_draws_chronologically)

APP_NAME = "Loser Master 2.0"
APP_VERSION = "© 2026 - N. Joan"
DATA_DIR = os.path.join(os.path.expanduser("~"), ".Lotto_perdu")
HISTORY_FILE = os.path.join(DATA_DIR, "historique.json")

BASE_DEFAULT = 6          # taille d'une grille (Loto classique = 6 numeros)
POOL_DEFAULT = 49         # numeros de 1 a 49

PRESET_GUARANTEES = [
    (3, 3), (4, 4), (5, 5), (6, 6),
    (3, 4), (3, 5), (3, 6), (3, 7),
    (4, 5), (4, 6), (4, 7),
    (5, 6), (5, 7),
]

THEMES = {
    "clair": dict(bg="#f2f2f0", fg="#1a1a1a", panel="#ffffff", accent="#0a5d8f",
                  select="#0a5d8f", select_fg="#ffffff", entry_bg="#ffffff"),
    "sombre": dict(bg="#1e1f22", fg="#e8e8e8", panel="#2b2d31", accent="#5aa9e6",
                   select="#5aa9e6", select_fg="#101010", entry_bg="#3a3c40"),
}


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_history():
    ensure_data_dir()
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history):
    ensure_data_dir()
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


class NumberPicker(ttk.Frame):
    """Grille de boutons 1..pool pour choisir des numeros (joues ou tires)."""

    def __init__(self, master, pool=POOL_DEFAULT, on_change=None, max_select=None,
                 cols=7, btn_width=3, **kw):
        super().__init__(master, **kw)
        self.pool = pool
        self.on_change = on_change
        self.max_select = max_select
        self.selected = set()
        self.buttons = {}
        self.default_bg = "#e6e6e6"
        for i in range(1, pool + 1):
            r, c = divmod(i - 1, cols)
            b = tk.Button(self, text=f"{i:02d}", width=btn_width, relief="raised",
                          bg=self.default_bg, command=lambda n=i: self.toggle(n))
            b.grid(row=r, column=c, padx=2, pady=2)
            self.buttons[i] = b

    def toggle(self, n):
        if n in self.selected:
            self.selected.remove(n)
        else:
            if self.max_select is not None and len(self.selected) >= self.max_select:
                return  # limite atteinte : on ignore le clic (pas de popup intrusif)
            self.selected.add(n)
        self.refresh_colors()
        if self.on_change:
            self.on_change()

    def refresh_colors(self, accent="#0a5d8f", fg_sel="#ffffff", normal_bg=None):
        bg = normal_bg or self.default_bg
        for n, b in self.buttons.items():
            if n in self.selected:
                b.configure(bg=accent, fg=fg_sel)
            else:
                b.configure(bg=bg, fg="#1a1a1a")

    def clear(self):
        self.selected.clear()
        self.refresh_colors()
        if self.on_change:
            self.on_change()

    def random_pick(self, count):
        self.selected = set(random.sample(range(1, self.pool + 1), count))
        self.refresh_colors()
        if self.on_change:
            self.on_change()


class LottoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} - {APP_VERSION}")
        self.geometry("1200x800")
        self.minsize(1000, 700)

        self.theme_name = tk.StringVar(value="clair")
        self.history = load_history()
        self.last_result = None
        self.last_numbers = []

        self._build_menu()
        self._build_layout()
        self.apply_theme()

    # ------------------------------------------------------------------ UI
    def _build_menu(self):
        menubar = tk.Menu(self)

        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Exporter en TXT...", command=self.export_txt)
        filemenu.add_command(label="Exporter en CSV...", command=self.export_csv)
        filemenu.add_separator()
        filemenu.add_command(label="Quitter", command=self.destroy)
        menubar.add_cascade(label="Fichier", menu=filemenu)

        thememenu = tk.Menu(menubar, tearoff=0)
        thememenu.add_radiobutton(label="Clair", variable=self.theme_name,
                                   value="clair", command=self.apply_theme)
        thememenu.add_radiobutton(label="Sombre", variable=self.theme_name,
                                   value="sombre", command=self.apply_theme)
        menubar.add_cascade(label="Affichage", menu=thememenu)

        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="A propos", command=self.show_about)
        menubar.add_cascade(label="?", menu=helpmenu)

        self.config(menu=menubar)

    @staticmethod
    def _make_responsive(source, label, padding=16):
        """
        Adapte automatiquement le retour a la ligne (wraplength) de `label`
        a la largeur reellement disponible de `source` (qui peut etre le
        label lui-meme s'il est empaquete avec fill="x", ou son conteneur
        sinon), au lieu d'une valeur fixe qui finit par etre trop large
        (texte coupe en bord de fenetre) ou trop etroite.
        """
        def _on_resize(event):
            if event.widget is source:
                new_width = max(80, event.width - padding)
                label.configure(wraplength=new_width)
        source.bind("<Configure>", _on_resize)

    def _build_layout(self):
        self.main = ttk.Frame(self, padding=10)
        self.main.pack(fill="both", expand=True)

        # ---- Colonne gauche : choix des numeros -------------------------
        left = ttk.LabelFrame(self.main, text="1. Vos numeros joues", padding=10)
        left.pack(side="left", fill="y", padx=(0, 10))

        self.picker = NumberPicker(left, pool=POOL_DEFAULT, on_change=self.on_numbers_changed)
        self.picker.pack()

        btnrow = ttk.Frame(left)
        btnrow.pack(fill="x", pady=(8, 0))
        ttk.Button(btnrow, text="Effacer", command=self.picker.clear).pack(side="left")
        ttk.Button(btnrow, text="Tirage au hasard (10)",
                   command=lambda: self.picker.random_pick(10)).pack(side="left", padx=6)

        self.count_label = ttk.Label(left, text="0 numero(s) selectionne(s)")
        self.count_label.pack(pady=(8, 0))

        # ---- Colonne centrale : parametres de la garantie ----------------
        mid = ttk.LabelFrame(self.main, text="2. Garantie souhaitee", padding=10)
        mid.pack(side="left", fill="y", padx=(0, 10))

        ttk.Label(mid, text="Garantie predefinie X/Y :").pack(anchor="w")
        self.preset_var = tk.StringVar()
        preset_values = [f"{x}/{y}" for (x, y) in PRESET_GUARANTEES] + ["Personnalisee..."]
        self.preset_combo = ttk.Combobox(mid, textvariable=self.preset_var,
                                          values=preset_values, state="readonly", width=18)
        self.preset_combo.current(4)  # 3/4 par defaut
        self.preset_combo.pack(pady=(0, 10))
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_preset_changed)

        custom_frame = ttk.Frame(mid)
        custom_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(custom_frame, text="X (garanti) :").grid(row=0, column=0, sticky="w")
        self.x_var = tk.IntVar(value=3)
        self.x_spin = ttk.Spinbox(custom_frame, from_=2, to=6, textvariable=self.x_var, width=5)
        self.x_spin.grid(row=0, column=1, padx=6)
        ttk.Label(custom_frame, text="Y (sur combien sortis) :").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.y_var = tk.IntVar(value=4)
        self.y_spin = ttk.Spinbox(custom_frame, from_=2, to=7, textvariable=self.y_var, width=5)
        self.y_spin.grid(row=1, column=1, padx=6, pady=(4, 0))

        ttk.Label(mid, text="Taille de grille (base) :").pack(anchor="w", pady=(6, 0))
        self.base_var = tk.IntVar(value=BASE_DEFAULT)
        ttk.Spinbox(mid, from_=5, to=8, textvariable=self.base_var, width=5).pack(anchor="w")

        ttk.Label(mid, text="Qualite / temps de calcul :").pack(anchor="w", pady=(10, 0))
        self.quality_var = tk.StringVar(value="Normal (8s max)")
        ttk.Combobox(mid, textvariable=self.quality_var, state="readonly", width=22,
                     values=["Rapide (3s max)", "Normal (8s max)", "Approfondi (20s max)"]
                     ).pack()

        self.generate_btn = ttk.Button(mid, text="Generer la garantie", command=self.on_generate)
        self.generate_btn.pack(pady=(16, 4), fill="x")
        self.progress = ttk.Progressbar(mid, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 10))

        self.explain = tk.Text(mid, width=32, height=10, wrap="word", relief="flat")
        self.explain.pack(fill="both", expand=True)
        self.explain.insert("1.0", self._explain_text())
        self.explain.configure(state="disabled")

        # ---- Colonne droite : resultats + verification + historique -----
        right = ttk.Frame(self.main)
        right.pack(side="left", fill="both", expand=True)

        notebook = ttk.Notebook(right)
        self.notebook = notebook
        notebook.pack(fill="both", expand=True)

        # -- Onglet 1 : grilles generees ------------------------------------
        tab_grids = ttk.Frame(notebook, padding=10)
        notebook.add(tab_grids, text="3. Grilles a jouer")

        result_frame = ttk.Frame(tab_grids)
        result_frame.pack(fill="both", expand=True)

        cols = ("grille", "numeros")
        self.tree = ttk.Treeview(result_frame, columns=cols, show="headings", height=12)
        self.tree.heading("grille", text="Grille")
        self.tree.heading("numeros", text="Numeros")
        self.tree.column("grille", width=80, anchor="center")
        self.tree.column("numeros", width=320, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="left", fill="y")

        self.status_label = ttk.Label(tab_grids, text="", wraplength=520, justify="left")
        self.status_label.pack(fill="x", pady=(8, 4))
        self._make_responsive(self.status_label, self.status_label)

        guarantee_frame = ttk.LabelFrame(tab_grids, text="Garanties reellement obtenues", padding=8)
        guarantee_frame.pack(fill="x", pady=(0, 8))
        self.guarantee_label = ttk.Label(
            guarantee_frame, text="Generez une garantie pour voir le detail.",
            wraplength=520, justify="left")
        self.guarantee_label.pack(anchor="w", fill="x")
        self._make_responsive(guarantee_frame, self.guarantee_label)

        odds_frame = ttk.LabelFrame(tab_grids, text="Probabilites de gain (calcul exact)", padding=8)
        odds_frame.pack(fill="x", pady=(0, 8))
        self.odds_label = ttk.Label(
            odds_frame, text="Generez une garantie pour voir le detail.",
            wraplength=520, justify="left")
        self.odds_label.pack(anchor="w", fill="x")
        self._make_responsive(odds_frame, self.odds_label)

        exportrow = ttk.Frame(tab_grids)
        exportrow.pack(fill="x")
        ttk.Button(exportrow, text="Exporter TXT", command=self.export_txt).pack(side="left")
        ttk.Button(exportrow, text="Exporter CSV", command=self.export_csv).pack(side="left", padx=6)
        ttk.Button(exportrow, text="Ajouter aux favoris", command=self.add_favorite).pack(side="left", padx=6)

        # -- Onglet 2 : verification d'un tirage reel -----------------------
        tab_draw = ttk.Frame(notebook, padding=10)
        notebook.add(tab_draw, text="4. Verifier un tirage")

        mode_row = ttk.Frame(tab_draw)
        mode_row.pack(anchor="w", pady=(0, 8))
        ttk.Label(mode_row, text="Tirage :").pack(side="left", padx=(0, 8))
        self.game_mode_var = tk.StringVar(value="fr")
        ttk.Radiobutton(mode_row, text="Loto France (mercredi/samedi)",
                        variable=self.game_mode_var, value="fr",
                        command=self.on_game_mode_changed).pack(side="left")
        ttk.Radiobutton(mode_row, text="Lotto Deutschland (Mittwoch/Samstag)",
                        variable=self.game_mode_var, value="de",
                        command=self.on_game_mode_changed).pack(side="left", padx=(12, 0))

        ttk.Label(tab_draw,
                  text="Entrez les 6 numeros tires, puis le(s) numero(s) bonus :"
                  ).pack(anchor="w", pady=(0, 6))

        draw_row = ttk.Frame(tab_draw)
        draw_row.pack(anchor="w")
        self.draw_picker = NumberPicker(draw_row, pool=POOL_DEFAULT,
                                         on_change=self.on_draw_changed, max_select=6)
        self.draw_picker.pack(side="left")

        bonus_container = ttk.Frame(draw_row)
        bonus_container.pack(side="left", padx=(20, 0), anchor="n")

        # -- variante France : numero chance (1-10) --
        self.bonus_frame_fr = ttk.Frame(bonus_container)
        ttk.Label(self.bonus_frame_fr, text="Numero\nchance :").pack()
        self.chance_var = tk.StringVar(value="")
        ttk.Combobox(self.bonus_frame_fr, textvariable=self.chance_var, state="readonly",
                     width=5, values=[""] + [str(i) for i in range(1, 11)]
                     ).pack(pady=(4, 0))

        # -- variante Allemagne : Zusatzzahl (1-49) + Superzahl (0-9) --
        self.bonus_frame_de = ttk.Frame(bonus_container)
        ttk.Label(self.bonus_frame_de, text="Zusatzzahl\n(1-49) :").grid(row=0, column=0, sticky="w")
        self.zusatzzahl_var = tk.StringVar(value="")
        ttk.Combobox(self.bonus_frame_de, textvariable=self.zusatzzahl_var, state="readonly",
                     width=5, values=[""] + [str(i) for i in range(1, 50)]
                     ).grid(row=0, column=1, padx=(6, 0))
        ttk.Label(self.bonus_frame_de, text="Superzahl\ntiree (0-9) :").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.superzahl_drawn_var = tk.StringVar(value="")
        ttk.Combobox(self.bonus_frame_de, textvariable=self.superzahl_drawn_var, state="readonly",
                     width=5, values=[""] + [str(i) for i in range(0, 10)]
                     ).grid(row=1, column=1, padx=(6, 0), pady=(8, 0))
        ttk.Label(self.bonus_frame_de, text="Ma Superzahl\n(0-9) :").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.superzahl_mine_var = tk.StringVar(value="")
        ttk.Combobox(self.bonus_frame_de, textvariable=self.superzahl_mine_var, state="readonly",
                     width=5, values=[""] + [str(i) for i in range(0, 10)]
                     ).grid(row=2, column=1, padx=(6, 0), pady=(8, 0))

        self.bonus_frame_fr.pack()  # mode par defaut = France

        self.draw_count_label = ttk.Label(tab_draw, text="0/6 numero(s) du tirage")
        self.draw_count_label.pack(anchor="w", pady=(6, 0))

        drawbtnrow = ttk.Frame(tab_draw)
        drawbtnrow.pack(fill="x", pady=(8, 8))
        ttk.Button(drawbtnrow, text="Effacer le tirage", command=self.draw_picker.clear).pack(side="left")
        ttk.Button(drawbtnrow, text="Verifier mes grilles",
                   command=self.on_check_draw).pack(side="left", padx=6)

        self.draw_summary_label = ttk.Label(tab_draw, text="", wraplength=520, justify="left")
        self.draw_summary_label.pack(fill="x", pady=(0, 8))
        self._make_responsive(self.draw_summary_label, self.draw_summary_label)

        draw_result_frame = ttk.Frame(tab_draw)
        draw_result_frame.pack(fill="both", expand=True)
        draw_cols = ("grille", "numeros", "points", "bonus")
        self.draw_tree = ttk.Treeview(draw_result_frame, columns=draw_cols,
                                       show="headings", height=10)
        self.draw_tree.heading("grille", text="Grille")
        self.draw_tree.heading("numeros", text="Numeros")
        self.draw_tree.heading("points", text="Points")
        self.draw_tree.heading("bonus", text="Bonus")
        self.draw_tree.column("grille", width=70, anchor="center")
        self.draw_tree.column("numeros", width=280, anchor="center")
        self.draw_tree.column("points", width=60, anchor="center")
        self.draw_tree.column("bonus", width=90, anchor="center")
        self.draw_tree.pack(side="left", fill="both", expand=True)
        draw_scroll = ttk.Scrollbar(draw_result_frame, orient="vertical",
                                     command=self.draw_tree.yview)
        self.draw_tree.configure(yscrollcommand=draw_scroll.set)
        draw_scroll.pack(side="left", fill="y")

        # -- Onglet 3 : analyse historique (import CSV) ---------------------
        tab_analysis = ttk.Frame(notebook, padding=10)
        notebook.add(tab_analysis, text="5. Analyse historique")

        disclaimer = (
            "Analyse purement descriptive et historique.\n"
            "Chaque tirage est un evenement INDEPENDANT : la frequence passee "
            "d'un numero n'influence en rien les tirages futurs. Ce tableau "
            "ne predit rien et n'ameliore aucune chance de gain -- meme la FDJ "
            "le rappelle sur sa page d'archives officielle."
        )
        disclaimer_label = ttk.Label(tab_analysis, text=disclaimer, justify="left",
                                      foreground="#a33")
        disclaimer_label.pack(anchor="w", fill="x", pady=(0, 10))
        self._make_responsive(tab_analysis, disclaimer_label)

        importrow = ttk.Frame(tab_analysis)
        importrow.pack(fill="x", pady=(0, 8))
        ttk.Label(importrow, text="Pays :").pack(side="left")
        self.analysis_country_var = tk.StringVar(value="France (Loto FDJ)")
        ttk.Combobox(importrow, textvariable=self.analysis_country_var, state="readonly",
                     width=28, values=["France (Loto FDJ)", "Allemagne (Lotto 6aus49)"]
                     ).pack(side="left", padx=(6, 16))
        ttk.Button(importrow, text="Importer un fichier CSV...",
                   command=self.on_import_csv).pack(side="left")

        self.analysis_summary_label = ttk.Label(
            tab_analysis,
            text="Aucun fichier importe. Telechargez l'historique officiel sur "
                 "fdj.fr (Loto > Archives) ou sachsenlotto.de (Download-Archiv) "
                 "puis importez le fichier CSV ici.",
            justify="left")
        self.analysis_summary_label.pack(anchor="w", fill="x", pady=(4, 8))
        self._make_responsive(self.analysis_summary_label, self.analysis_summary_label)

        chi2_row = ttk.Frame(tab_analysis)
        chi2_row.pack(fill="x", pady=(0, 4))
        ttk.Button(chi2_row, text="Tester l'equirepartition (chi2)",
                   command=self.on_run_chi2).pack(side="left")
        self.chi2_label = ttk.Label(
            tab_analysis,
            text="Ce test verifie si la MECANIQUE de tirage passee semble "
                 "equitable (chaque numero egalement probable) -- il ne dit "
                 "rien sur le prochain tirage.",
            justify="left")
        self.chi2_label.pack(anchor="w", fill="x", pady=(2, 8))
        self._make_responsive(self.chi2_label, self.chi2_label)

        sub_nb = ttk.Notebook(tab_analysis)
        sub_nb.pack(fill="both", expand=True)

        # -- sous-onglet A : frequence sur tout l'historique importe --------
        tab_freq = ttk.Frame(sub_nb, padding=6)
        sub_nb.add(tab_freq, text="Frequence (tout l'historique)")

        analysis_result_frame = ttk.Frame(tab_freq)
        analysis_result_frame.pack(fill="both", expand=True)
        acols = ("numero", "freq", "pct", "ecart")
        self.analysis_tree = ttk.Treeview(analysis_result_frame, columns=acols,
                                           show="headings", height=14)
        self.analysis_tree.heading("numero", text="Numero")
        self.analysis_tree.heading("freq", text="Sorties")
        self.analysis_tree.heading("pct", text="% des tirages")
        self.analysis_tree.heading("ecart", text="Tirages depuis derniere sortie")
        for c, w in (("numero", 70), ("freq", 80), ("pct", 110), ("ecart", 200)):
            self.analysis_tree.column(c, width=w, anchor="center")
        self.analysis_tree.pack(side="left", fill="both", expand=True)
        analysis_scroll = ttk.Scrollbar(analysis_result_frame, orient="vertical",
                                         command=self.analysis_tree.yview)
        self.analysis_tree.configure(yscrollcommand=analysis_scroll.set)
        analysis_scroll.pack(side="left", fill="y")
        self.analysis_tree.heading("freq", command=lambda: self._sort_analysis_tree("freq"))
        self.analysis_tree.heading("ecart", command=lambda: self._sort_analysis_tree("ecart"))
        self._analysis_table_cache = None

        # -- sous-onglet B : 20 derniers tirages vs mes numeros --------------
        tab_recent = ttk.Frame(sub_nb, padding=6)
        sub_nb.add(tab_recent, text="20 derniers tirages vs mes numeros")

        recent_note = (
            "Sur seulement 20 tirages (120 numeros tires au total sur 49 "
            "possibles, ~2,4 sorties attendues par numero), les ecarts "
            "observes sont du pur bruit statistique -- ils ne predisent "
            "rien sur le prochain tirage. Vue purement descriptive."
        )
        recent_note_label = ttk.Label(tab_recent, text=recent_note, justify="left",
                                       foreground="#a33")
        recent_note_label.pack(anchor="w", fill="x", pady=(0, 8))
        self._make_responsive(tab_recent, recent_note_label)

        recent_split = ttk.Frame(tab_recent)
        recent_split.pack(fill="both", expand=True)

        recent_left = ttk.Frame(recent_split)
        recent_left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ttk.Label(recent_left, text="20 derniers tirages importes :").pack(anchor="w")
        rcols = ("date", "numeros")
        self.recent_tree = ttk.Treeview(recent_left, columns=rcols, show="headings", height=20)
        self.recent_tree.heading("date", text="Date")
        self.recent_tree.heading("numeros", text="Numeros tires")
        self.recent_tree.column("date", width=100, anchor="center")
        self.recent_tree.column("numeros", width=220, anchor="center")
        self.recent_tree.pack(fill="both", expand=True)

        recent_right = ttk.Frame(recent_split)
        recent_right.pack(side="left", fill="both", expand=True)
        ttk.Label(recent_right, text="Les 49 numeros sur ces 20 tirages "
                                      "(vos numeros de l'onglet 1 sont marques) :").pack(anchor="w")
        compare_table_frame = ttk.Frame(recent_right)
        compare_table_frame.pack(fill="both", expand=True, pady=(0, 8))
        ccols = ("numero", "sorties_sur_20", "joue")
        self.compare_tree = ttk.Treeview(compare_table_frame, columns=ccols,
                                          show="headings", height=20)
        self.compare_tree.heading("numero", text="Numero")
        self.compare_tree.heading("sorties_sur_20", text="Sorties / 20")
        self.compare_tree.heading("joue", text="Joue par vous")
        self.compare_tree.column("numero", width=70, anchor="center")
        self.compare_tree.column("sorties_sur_20", width=90, anchor="center")
        self.compare_tree.column("joue", width=100, anchor="center")
        self.compare_tree.pack(side="left", fill="both", expand=True)
        compare_scroll = ttk.Scrollbar(compare_table_frame, orient="vertical",
                                        command=self.compare_tree.yview)
        self.compare_tree.configure(yscrollcommand=compare_scroll.set)
        compare_scroll.pack(side="left", fill="y")
        self.compare_tree.heading(
            "sorties_sur_20", command=lambda: self._fill_compare_tree(sort_key="sorties"))
        self.compare_tree.heading(
            "numero", command=lambda: self._fill_compare_tree(sort_key="numero"))
        self._compare_counts_cache = None

        ttk.Button(recent_right, text="Actualiser la comparaison",
                   command=self.on_refresh_recent_comparison).pack(anchor="w")
        self.recent_summary_label = ttk.Label(recent_right, text="", justify="left")
        self.recent_summary_label.pack(anchor="w", fill="x", pady=(8, 0))
        self._make_responsive(recent_right, self.recent_summary_label)

        self._last_imported_draws = None

        # -- Onglet 4 : historique / favoris ---------------------------------
        tab_hist = ttk.Frame(notebook, padding=10)
        notebook.add(tab_hist, text="Historique")
        hist_frame = ttk.Frame(tab_hist)
        hist_frame.pack(fill="both", expand=True)
        self.hist_list = tk.Listbox(hist_frame, height=20)
        self.hist_list.pack(fill="both", expand=True, side="left")
        hist_scroll = ttk.Scrollbar(hist_frame, orient="vertical", command=self.hist_list.yview)
        self.hist_list.configure(yscrollcommand=hist_scroll.set)
        hist_scroll.pack(side="left", fill="y")
        self.refresh_history_list()
        self.hist_list.bind("<Double-Button-1>", self.load_history_item)

    def _explain_text(self):
        return (
            "Une garantie N-X/Y signifie :\n\n"
            "Si, parmi vos N numeros joues, Y sortent au tirage, alors au "
            "moins une de vos grilles contiendra au moins X de ces numeros "
            "gagnants.\n\n"
            "Exemple : garantie 3/4 avec 9 numeros joues -> si 4 de vos 9 "
            "numeros sortent, une grille au moins en contiendra 3.\n\n"
            "Plus X et Y sont eleves, plus la garantie est 'forte' mais "
            "plus il faudra de grilles."
        )

    # -------------------------------------------------------------- events
    def on_numbers_changed(self):
        self.count_label.configure(text=f"{len(self.picker.selected)} numero(s) selectionne(s)")

    def on_preset_changed(self, event=None):
        val = self.preset_var.get()
        if "/" in val:
            x, y = val.split("/")
            self.x_var.set(int(x))
            self.y_var.set(int(y))

    def _quality_seconds(self):
        v = self.quality_var.get()
        if v.startswith("Rapide"):
            return 3.0
        if v.startswith("Approfondi"):
            return 20.0
        return 8.0

    def on_generate(self):
        numbers = sorted(self.picker.selected)
        base = self.base_var.get()
        x = self.x_var.get()
        y = self.y_var.get()

        if len(numbers) < base + 1:
            messagebox.showwarning(
                APP_NAME,
                f"Choisissez au moins {base + 1} numeros pour qu'une garantie "
                f"ait un sens (vous en avez {len(numbers)}).")
            return
        if y > base:
            messagebox.showwarning(APP_NAME, "Y ne peut pas depasser la taille de grille.")
            return
        if x > y:
            messagebox.showwarning(APP_NAME, "X ne peut pas depasser Y.")
            return
        if len(numbers) > 30:
            if not messagebox.askyesno(
                    APP_NAME,
                    f"Vous avez choisi {len(numbers)} numeros : le calcul peut "
                    "prendre du temps et ne pas etre prouve a 100%. Continuer ?"):
                return

        self.generate_btn.configure(state="disabled")
        self.progress.start(12)
        self.status_label.configure(text="Calcul en cours...")
        max_seconds = self._quality_seconds()

        def worker():
            try:
                result = generate_wheel(
                    n=len(numbers), x=x, y=y, base=base,
                    max_seconds=max_seconds)
                grids_real = apply_numbers(result, numbers)
            except Exception as e:
                self.after(0, lambda: self._on_generate_error(e))
                return
            self.after(0, lambda: self._on_generate_done(result, grids_real, numbers))

        threading.Thread(target=worker, daemon=True).start()

    def _on_generate_error(self, e):
        self.progress.stop()
        self.generate_btn.configure(state="normal")
        messagebox.showerror(APP_NAME, f"Erreur lors du calcul :\n{e}")

    def _on_generate_done(self, result, grids_real, numbers):
        self.progress.stop()
        self.generate_btn.configure(state="normal")
        self.last_result = result
        self.last_numbers = numbers

        for row in self.tree.get_children():
            self.tree.delete(row)
        for i, g in enumerate(grids_real, start=1):
            self.tree.insert("", "end", values=(f"Grille {i}", "-".join(f"{n:02d}" for n in g)))

        status = (f"Garantie {len(numbers)}-{result.x}/{result.y} : "
                  f"{len(grids_real)} grille(s) generee(s). {result.verify_note}")
        self.status_label.configure(text=status)

        self.guarantee_label.configure(text="Calcul des garanties reelles en cours...")
        self.odds_label.configure(text="Calcul des probabilites en cours...")

        def worker2():
            table = guarantee_table(result, y_values=(3, 4, 5, 6), time_budget=3.0)
            self.after(0, lambda: self._show_guarantee_table(table))

        def worker3():
            so = system_odds(result, pool=POOL_DEFAULT, draw_size=6)
            sg = single_grid_odds(base=result.base, draw_size=6, pool=POOL_DEFAULT)
            self.after(0, lambda: self._show_odds(so, sg))

        threading.Thread(target=worker2, daemon=True).start()
        threading.Thread(target=worker3, daemon=True).start()

    def _show_guarantee_table(self, table):
        lines = []
        for y in (3, 4, 5, 6):
            info = table.get(y)
            if info is None or info["garanti"] is None:
                continue
            marker = "" if info["exact"] else " (estimation)"
            lines.append(f"Si {y} de vos numeros sortent -> au moins "
                         f"{info['garanti']} garanti(s) dans une grille{marker}")
        self.guarantee_label.configure(text="\n".join(lines) if lines else "Non calculable pour ce cas.")

    def _show_odds(self, system_odds_result, single_grid_odds_dict):
        probs = system_odds_result["probs"]
        lines = ["Systeme complet (au moins 1 de vos grilles) :"]
        for m in sorted(probs.keys(), reverse=True):
            p = probs[m]
            if p <= 0:
                continue
            lines.append(f"  >= {m} bons numeros : 1 chance sur {1/p:,.0f}".replace(",", " "))
        marker = "" if system_odds_result["exact"] else " (estimation par echantillonnage)"
        lines.append(f"(calcul{marker})")
        lines.append("")
        lines.append("Pour comparaison, une seule grille de 6 numeros aleatoires :")
        for m in sorted(single_grid_odds_dict.keys(), reverse=True):
            p = single_grid_odds_dict[m]
            if m >= 3 and p > 0:
                lines.append(f"  {m} bons numeros : 1 chance sur {1/p:,.0f}".replace(",", " "))
        self.odds_label.configure(text="\n".join(lines))

    def on_run_chi2(self):
        if not self._last_imported_draws:
            messagebox.showinfo(APP_NAME, "Importez d'abord un historique de tirages.")
            return
        res = chi_square_uniformity_test(self._last_imported_draws)
        if "error" in res:
            self.chi2_label.configure(text=res["error"])
            return
        verdict = ("Deviation statistiquement significative detectee (p < 0.05) -- "
                   "peu probable sous l'hypothese d'equirepartition, meriterait un "
                   "second regard sur la source des donnees."
                   if res["significant"] else
                   "Pas de deviation significative : compatible avec un tirage "
                   "equitable sur cet echantillon (ne predit rien sur l'avenir).")
        self.chi2_label.configure(
            text=f"Chi2 = {res['chi2']:.1f}  (df={res['df']}, "
                 f"{res['n_draws']} tirages, ~{res['expected_per_number']:.1f} "
                 f"sorties attendues/numero)\n"
                 f"p-value ~ {res['p_value']:.4f}\n{verdict}")

    def on_import_csv(self):
        path = filedialog.askopenfilename(
            title="Importer un historique de tirages (CSV)",
            filetypes=[("Fichier CSV", "*.csv"), ("Tous les fichiers", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                text = f.read()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Impossible de lire le fichier :\n{e}")
            return

        self.analysis_summary_label.configure(text="Analyse en cours...")

        def worker():
            result = parse_csv_text(text)
            if not result.draws:
                self.after(0, lambda: messagebox.showwarning(
                    APP_NAME,
                    "Aucun tirage valide n'a ete reconnu dans ce fichier. "
                    "Verifiez qu'il s'agit bien d'un export de tirages "
                    "(6 numeros par ligne, eventuellement avec un numero bonus)."))
                self.after(0, lambda: self.analysis_summary_label.configure(
                    text="Import echoue -- aucun tirage reconnu."))
                return
            table = frequency_table(result.draws)
            country = self.analysis_country_var.get()
            bonus_pool = 10 if country.startswith("France") else 49
            btable = bonus_frequency_table(result.draws, bonus_pool=bonus_pool)
            self.after(0, lambda: self._show_analysis(result, table, btable))

        threading.Thread(target=worker, daemon=True).start()

    def _show_analysis(self, result, table, btable):
        self._analysis_table_cache = table
        sorted_draws, chrono_ok = sort_draws_chronologically(result.draws)
        self._last_imported_draws = sorted_draws
        dates = [d.date for d in sorted_draws if d.date]
        span = f" ({dates[0]} -> {dates[-1]})" if len(dates) >= 2 else ""
        order_note = "" if chrono_ok else (
            " (dates non reconnues -- ordre du fichier conserve, "
            "'derniers tirages' peut ne pas etre exact)")
        self.analysis_summary_label.configure(
            text=f"{result.note}{span}{order_note}\n"
                 "Rappel : ceci decrit le passe, cela ne predit pas l'avenir.")
        self._fill_analysis_tree(table, sort_key="numero")
        self._fill_recent_tree()
        self.on_refresh_recent_comparison()

    def _fill_recent_tree(self):
        for row in self.recent_tree.get_children():
            self.recent_tree.delete(row)
        if not self._last_imported_draws:
            return
        last20 = self._last_imported_draws[-20:]
        for d in reversed(last20):  # le plus recent en premier
            self.recent_tree.insert("", "end", values=(
                d.date or "-", "-".join(f"{n:02d}" for n in d.numbers)))

    def on_refresh_recent_comparison(self):
        if not self._last_imported_draws:
            self._compare_counts_cache = None
            for row in self.compare_tree.get_children():
                self.compare_tree.delete(row)
            self.recent_summary_label.configure(
                text="Importez d'abord un historique (bouton ci-dessus).")
            return
        last20 = self._last_imported_draws[-20:]
        n_draws = len(last20)
        my_numbers = self.picker.selected

        counts = {}
        for n in range(1, POOL_DEFAULT + 1):
            counts[n] = sum(1 for d in last20 if n in d.numbers)
        self._compare_counts_cache = (counts, n_draws, set(my_numbers))
        self._fill_compare_tree(sort_key="numero")

        if not my_numbers:
            self.recent_summary_label.configure(
                text=f"Tableau des {n_draws} derniers tirages pour les 49 numeros. "
                     "Choisissez vos numeros dans l'onglet 1 pour voir un resume "
                     "specifique a votre selection.")
            return
        total_hits = sum(counts[n] for n in my_numbers)
        expected = n_draws * len(my_numbers) * 6 / POOL_DEFAULT
        self.recent_summary_label.configure(
            text=f"Vos numeros : {total_hits} sortie(s) au total pour "
                 f"{len(my_numbers)} numero(s) sur {n_draws} tirages "
                 f"(attendu en moyenne : {expected:.1f}). "
                 "Un ecart ici est du bruit statistique normal, pas un signal.")

    def _fill_compare_tree(self, sort_key="numero"):
        for row in self.compare_tree.get_children():
            self.compare_tree.delete(row)
        if not self._compare_counts_cache:
            return
        counts, n_draws, my_numbers = self._compare_counts_cache
        items = list(counts.items())
        if sort_key == "sorties":
            items.sort(key=lambda kv: -kv[1])
        else:
            items.sort(key=lambda kv: kv[0])
        for n, count in items:
            self.compare_tree.insert("", "end", values=(
                f"{n:02d}", f"{count} / {n_draws}", "Oui" if n in my_numbers else ""))

    def _fill_analysis_tree(self, table, sort_key="numero"):
        for row in self.analysis_tree.get_children():
            self.analysis_tree.delete(row)
        items = list(table.items())
        if sort_key == "freq":
            items.sort(key=lambda kv: -kv[1]["freq"])
        elif sort_key == "ecart":
            items.sort(key=lambda kv: (kv[1]["ecart"] is None, -(kv[1]["ecart"] or 0)))
        else:
            items.sort(key=lambda kv: kv[0])
        for n, info in items:
            ecart_txt = "-" if info["ecart"] is None else str(info["ecart"])
            self.analysis_tree.insert("", "end", values=(
                f"{n:02d}", info["freq"], f"{info['pct']:.1f} %", ecart_txt))

    def _sort_analysis_tree(self, key):
        if self._analysis_table_cache:
            self._fill_analysis_tree(self._analysis_table_cache, sort_key=key)

    def on_draw_changed(self):
        self.draw_count_label.configure(
            text=f"{len(self.draw_picker.selected)}/6 numero(s) du tirage")

    def on_game_mode_changed(self):
        if self.game_mode_var.get() == "fr":
            self.bonus_frame_de.pack_forget()
            self.bonus_frame_fr.pack()
        else:
            self.bonus_frame_fr.pack_forget()
            self.bonus_frame_de.pack()
        self.draw_tree.heading(
            "bonus", text="Chance" if self.game_mode_var.get() == "fr" else "Zusatzz.")

    def on_check_draw(self):
        grids_real = []
        for iid in self.tree.get_children():
            _, numeros = self.tree.item(iid, "values")
            grids_real.append([int(x) for x in numeros.split("-")])
        if not grids_real:
            messagebox.showinfo(APP_NAME, "Generez d'abord vos grilles (ou chargez un favori).")
            return
        drawn = sorted(self.draw_picker.selected)
        if len(drawn) != 6:
            messagebox.showwarning(APP_NAME, "Entrez exactement les 6 numeros tires.")
            return

        mode = self.game_mode_var.get()
        superzahl_note = None
        if mode == "fr":
            bonus = int(self.chance_var.get()) if self.chance_var.get() else None
            bonus_label = "chance"
        else:
            bonus = int(self.zusatzzahl_var.get()) if self.zusatzzahl_var.get() else None
            bonus_label = "Zusatzzahl"
            drawn_sz = self.superzahl_drawn_var.get()
            mine_sz = self.superzahl_mine_var.get()
            if drawn_sz and mine_sz:
                match = drawn_sz == mine_sz
                superzahl_note = (f"Superzahl : tiree {drawn_sz}, la votre {mine_sz} -> "
                                  f"{'CORRESPONDANCE !' if match else 'pas de correspondance.'}\n"
                                  f"(La Superzahl est la meme pour tous vos champs de jeu par "
                                  f"defaut ; elle n'est pas generee par les grilles ci-dessus.)")

        details, summary = score_grids_against_draw(grids_real, drawn, bonus)

        for row in self.draw_tree.get_children():
            self.draw_tree.delete(row)
        for d in details:
            self.draw_tree.insert("", "end", values=(
                f"Grille {d['grille']}",
                "-".join(f"{n:02d}" for n in d["numeros"]),
                d["points"],
                "OUI" if d["bonus_touche"] else "",
            ))

        parts = [f"Tirage : {'-'.join(f'{n:02d}' for n in drawn)}"]
        if bonus is not None:
            parts[0] += f" + {bonus_label} {bonus}"
        parts.append(
            f"3 numeros : {summary[3]} grille(s) | "
            f"4 numeros : {summary[4]} grille(s) | "
            f"5 numeros : {summary[5]} grille(s) | "
            f"6 numeros (jackpot) : {summary[6]} grille(s)")
        if bonus is not None:
            parts.append(f"{bonus_label.capitalize()} touchee sur {summary['bonus']} grille(s).")
        if superzahl_note:
            parts.append(superzahl_note)
        self.draw_summary_label.configure(text="\n".join(parts))

    def add_favorite(self):
        if not self.last_result:
            messagebox.showinfo(APP_NAME, "Generez d'abord une garantie.")
            return
        entry = {
            "date": datetime.now().isoformat(timespec="seconds"),
            "numbers": self.last_numbers,
            "x": self.last_result.x,
            "y": self.last_result.y,
            "base": self.last_result.base,
            "grids": apply_numbers(self.last_result, self.last_numbers),
        }
        self.history.insert(0, entry)
        self.history = self.history[:50]
        save_history(self.history)
        self.refresh_history_list()
        messagebox.showinfo(APP_NAME, "Ajoute a l'historique.")

    def refresh_history_list(self):
        self.hist_list.delete(0, "end")
        for h in self.history:
            label = f"{h['date']} - {len(h['numbers'])} num. - garantie {h['x']}/{h['y']} - {len(h['grids'])} grilles"
            self.hist_list.insert("end", label)

    def load_history_item(self, event=None):
        sel = self.hist_list.curselection()
        if not sel:
            return
        h = self.history[sel[0]]
        for row in self.tree.get_children():
            self.tree.delete(row)
        for i, g in enumerate(h["grids"], start=1):
            self.tree.insert("", "end", values=(f"Grille {i}", "-".join(f"{n:02d}" for n in g)))
        self.picker.selected = set(h["numbers"])
        self.picker.refresh_colors()
        self.on_numbers_changed()
        self.x_var.set(h["x"])
        self.y_var.set(h["y"])
        self.base_var.set(h["base"])
        self.status_label.configure(
            text=f"Historique du {h['date']} : garantie {len(h['numbers'])}-{h['x']}/{h['y']}, "
                 f"{len(h['grids'])} grille(s).")

    # -------------------------------------------------------------- export
    def _current_grids(self):
        rows = []
        for iid in self.tree.get_children():
            _, numeros = self.tree.item(iid, "values")
            rows.append(numeros)
        return rows

    def export_txt(self):
        rows = self._current_grids()
        if not rows:
            messagebox.showinfo(APP_NAME, "Aucune grille a exporter. Generez d'abord une garantie.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt",
                                             filetypes=[("Fichier texte", "*.txt")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{APP_NAME} - {APP_VERSION}\n\n")
            if self.last_result:
                f.write(f"Numeros joues : {'-'.join(f'{n:02d}' for n in self.last_numbers)}\n")
                f.write(f"Garantie {len(self.last_numbers)}-{self.last_result.x}/{self.last_result.y}\n\n")
            for i, r in enumerate(rows, start=1):
                f.write(f"Grille {i} : {r}\n")
            f.write(f"\n{len(rows)} grilles.\n")
        messagebox.showinfo(APP_NAME, "Export TXT termine.")

    def export_csv(self):
        rows = self._current_grids()
        if not rows:
            messagebox.showinfo(APP_NAME, "Aucune grille a exporter. Generez d'abord une garantie.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                             filetypes=[("Fichier CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Grille", "Numeros"])
            for i, r in enumerate(rows, start=1):
                writer.writerow([i, r])
        messagebox.showinfo(APP_NAME, "Export CSV termine.")

    # --------------------------------------------------------------- theme
    def apply_theme(self):
        t = THEMES[self.theme_name.get()]
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        self.configure(bg=t["bg"])
        style.configure(".", background=t["bg"], foreground=t["fg"])
        style.configure("TFrame", background=t["bg"])
        style.configure("TLabelframe", background=t["bg"], foreground=t["fg"])
        style.configure("TLabelframe.Label", background=t["bg"], foreground=t["fg"])
        style.configure("TLabel", background=t["bg"], foreground=t["fg"])
        style.configure("TButton", background=t["panel"], foreground=t["fg"])
        style.map("TButton", background=[("active", t["accent"])])
        style.configure("Treeview", background=t["panel"], fieldbackground=t["panel"],
                         foreground=t["fg"])
        style.configure("Treeview.Heading", background=t["accent"], foreground=t["select_fg"])
        self.picker.refresh_colors(accent=t["accent"], fg_sel=t["select_fg"], normal_bg=t["panel"])
        self.explain.configure(bg=t["panel"], fg=t["fg"], insertbackground=t["fg"])
        self.hist_list.configure(bg=t["panel"], fg=t["fg"])

    def show_about(self):
        messagebox.showinfo(
            APP_NAME,
            f"{APP_NAME}\nVersion {APP_VERSION}\n\n"
            "Loser Master 2.0 - (c) 2026 N. Joan "
            "Le système qui gagne… pour quelqu’un d’autre. \n"
            "Rappel : ce logiciel est un outil de combinatoire (systemes "
            "reduits). Il n'augmente pas les probabilites de gain par "
            "numero joue et ne predit aucun tirage. Jouez avec moderation."
        )


def main():
    app = LottoApp()
    app.mainloop()


if __name__ == "__main__":
    main()
