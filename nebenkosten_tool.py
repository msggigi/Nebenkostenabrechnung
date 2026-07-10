
# -*- coding: utf-8 -*-
"""
Nebenkostenabrechnung Tool
===========================
Verwaltung von Immobilien, Parteien (Mietparteien) und Zählern (Gas, Öl, Wasser, Strom)
inkl. Zählerstandserfassung und automatischer Erstellung einer formal korrekten
Nebenkostenabrechnung nach deutschem Mietrecht (§556 BGB i.V.m. BetrKV) als PDF (DIN A4).

Alle Daten werden dauerhaft in einer SQLite-Datenbank im Unterordner "data" gespeichert,
der sich neben dieser Programmdatei / der erzeugten .exe befindet.
"""

import sqlite3
import os
import sys
import datetime
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                 Spacer, PageBreak, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER

# ---------------------------------------------------------------------------
# Speicherort: IMMER neben der Programmdatei / .exe, damit Daten dauerhaft
# erhalten bleiben, egal von wo das Programm gestartet wird.
# ---------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
PDF_DIR = os.path.join(BASE_DIR, "abrechnungen")
DB_PATH = os.path.join(DATA_DIR, "nebenkosten.db")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PDF_DIR, exist_ok=True)

KOSTENARTEN_BETRKV = [
    "Grundsteuer", "Wasserversorgung", "Entwässerung", "Heizung", "Warmwasser",
    "Aufzug", "Straßenreinigung/Müllbeseitigung", "Gebäudereinigung/Ungezieferbekämpfung",
    "Gartenpflege", "Beleuchtung", "Schornsteinreinigung",
    "Sach-/Haftpflichtversicherung", "Hauswart", "Gemeinschaftsantenne/Breitband",
    "Wascheinrichtung", "Sonstige Betriebskosten"
]

UMLAGESCHLUESSEL = ["Wohnfläche (m²)", "Personenzahl", "Verbrauch (Zähler)", "Wohneinheiten", "Individuell (%)"]

ZAEHLERTYPEN = ["Strom", "Gas", "Wasser", "Öl"]
EINHEITEN = {"Strom": "kWh", "Gas": "kWh / m³", "Wasser": "m³", "Öl": "Liter"}


# ---------------------------------------------------------------------------
# Datenbank
# ---------------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS immobilien (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        adresse TEXT,
        gesamtwohnflaeche REAL DEFAULT 0,
        gesamteinheiten INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS parteien (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        immobilie_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        einheit TEXT,
        wohnflaeche REAL DEFAULT 0,
        personenzahl INTEGER DEFAULT 1,
        einzug TEXT,
        auszug TEXT,
        vorauszahlung_monat REAL DEFAULT 0,
        FOREIGN KEY(immobilie_id) REFERENCES immobilien(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS zaehler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        immobilie_id INTEGER NOT NULL,
        partei_id INTEGER,
        typ TEXT NOT NULL,
        name TEXT NOT NULL,
        nummer TEXT,
        FOREIGN KEY(immobilie_id) REFERENCES immobilien(id) ON DELETE CASCADE,
        FOREIGN KEY(partei_id) REFERENCES parteien(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS zaehlerstaende (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zaehler_id INTEGER NOT NULL,
        datum TEXT NOT NULL,
        stand REAL NOT NULL,
        notiz TEXT,
        FOREIGN KEY(zaehler_id) REFERENCES zaehler(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS kostenpositionen (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        immobilie_id INTEGER NOT NULL,
        jahr INTEGER NOT NULL,
        kostenart TEXT NOT NULL,
        betrag REAL NOT NULL,
        umlageschluessel TEXT NOT NULL,
        FOREIGN KEY(immobilie_id) REFERENCES immobilien(id) ON DELETE CASCADE
    );
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Haupt-App
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Nebenkostenabrechnung Manager")
        self.geometry("1150x680")
        init_db()
        self._build_ui()
        self.refresh_immobilien()

    # -------------------- UI Aufbau --------------------
    def _build_ui(self):
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=8, pady=8)

        # Linke Spalte: Immobilien
        left = ttk.LabelFrame(main, text="Immobilien")
        left.pack(side="left", fill="y", padx=(0, 6))
        self.tree_immo = ttk.Treeview(left, columns=("adresse",), show="tree headings", height=25)
        self.tree_immo.heading("#0", text="Name")
        self.tree_immo.heading("adresse", text="Adresse")
        self.tree_immo.column("#0", width=160)
        self.tree_immo.column("adresse", width=220)
        self.tree_immo.pack(fill="y", expand=True)
        self.tree_immo.bind("<<TreeviewSelect>>", lambda e: self.on_select_immobilie())

        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill="x", pady=4)
        ttk.Button(btn_frame, text="+ Neu", command=self.add_immobilie).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Bearbeiten", command=self.edit_immobilie).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Löschen", command=self.delete_immobilie).pack(side="left", padx=2)

        # Mitte: Notebook mit Parteien / Zähler / Kosten
        mid = ttk.Frame(main)
        mid.pack(side="left", fill="both", expand=True)

        self.notebook = ttk.Notebook(mid)
        self.notebook.pack(fill="both", expand=True)

        self._build_tab_parteien()
        self._build_tab_zaehler()
        self._build_tab_kosten()
        self._build_tab_abrechnung()

    # -------------------- Immobilien --------------------
    def refresh_immobilien(self):
        self.tree_immo.delete(*self.tree_immo.get_children())
        conn = get_conn()
        for row in conn.execute("SELECT * FROM immobilien ORDER BY name"):
            self.tree_immo.insert("", "end", iid=str(row["id"]), text=row["name"], values=(row["adresse"],))
        conn.close()

    def current_immobilie_id(self):
        sel = self.tree_immo.selection()
        if not sel:
            return None
        return int(sel[0])

    def add_immobilie(self):
        name = simpledialog.askstring("Neue Immobilie", "Name der Immobilie:")
        if not name:
            return
        adresse = simpledialog.askstring("Neue Immobilie", "Adresse:")
        conn = get_conn()
        conn.execute("INSERT INTO immobilien (name, adresse) VALUES (?, ?)", (name, adresse or ""))
        conn.commit()
        conn.close()
        self.refresh_immobilien()

    def edit_immobilie(self):
        iid = self.current_immobilie_id()
        if not iid:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Immobilie auswählen.")
            return
        conn = get_conn()
        row = conn.execute("SELECT * FROM immobilien WHERE id=?", (iid,)).fetchone()
        name = simpledialog.askstring("Immobilie bearbeiten", "Name:", initialvalue=row["name"])
        if name is None:
            conn.close()
            return
        adresse = simpledialog.askstring("Immobilie bearbeiten", "Adresse:", initialvalue=row["adresse"])
        flaeche = simpledialog.askstring("Immobilie bearbeiten", "Gesamtwohnfläche (m², optional):",
                                          initialvalue=str(row["gesamtwohnflaeche"]))
        einheiten = simpledialog.askstring("Immobilie bearbeiten", "Anzahl Wohneinheiten (optional):",
                                            initialvalue=str(row["gesamteinheiten"]))
        try:
            flaeche_v = float(flaeche) if flaeche else 0
        except ValueError:
            flaeche_v = row["gesamtwohnflaeche"]
        try:
            einheiten_v = int(einheiten) if einheiten else 0
        except ValueError:
            einheiten_v = row["gesamteinheiten"]
        conn.execute("UPDATE immobilien SET name=?, adresse=?, gesamtwohnflaeche=?, gesamteinheiten=? WHERE id=?",
                     (name, adresse, flaeche_v, einheiten_v, iid))
        conn.commit()
        conn.close()
        self.refresh_immobilien()

    def delete_immobilie(self):
        iid = self.current_immobilie_id()
        if not iid:
            return
        if not messagebox.askyesno("Löschen", "Immobilie inkl. aller Parteien, Zähler und Kosten wirklich löschen?"):
            return
        conn = get_conn()
        conn.execute("DELETE FROM immobilien WHERE id=?", (iid,))
        conn.commit()
        conn.close()
        self.refresh_immobilien()
        self.refresh_parteien()
        self.refresh_zaehler()
        self.refresh_kosten()

    def on_select_immobilie(self):
        self.refresh_parteien()
        self.refresh_zaehler()
        self.refresh_kosten()

    # -------------------- Tab: Parteien --------------------
    def _build_tab_parteien(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Parteien")

        self.tree_partei = ttk.Treeview(
            tab, columns=("einheit", "flaeche", "personen", "vorauszahlung"),
            show="headings", height=18)
        for col, txt, w in [("einheit", "Einheit/Wohnung", 150), ("flaeche", "Wohnfläche m²", 100),
                             ("personen", "Personen", 80), ("vorauszahlung", "Vorauszahlung €/Monat", 150)]:
            self.tree_partei.heading(col, text=txt)
            self.tree_partei.column(col, width=w)
        self.tree_partei.heading("#0", text="Name")
        self.tree_partei.pack(fill="both", expand=True, padx=6, pady=6)

        btns = ttk.Frame(tab)
        btns.pack(fill="x", padx=6, pady=4)
        ttk.Button(btns, text="+ Neue Partei", command=self.add_partei).pack(side="left", padx=2)
        ttk.Button(btns, text="Bearbeiten", command=self.edit_partei).pack(side="left", padx=2)
        ttk.Button(btns, text="Löschen", command=self.delete_partei).pack(side="left", padx=2)

    def refresh_parteien(self):
        self.tree_partei.delete(*self.tree_partei.get_children())
        iid = self.current_immobilie_id()
        if not iid:
            return
        conn = get_conn()
        for row in conn.execute("SELECT * FROM parteien WHERE immobilie_id=? ORDER BY name", (iid,)):
            self.tree_partei.insert("", "end", iid=str(row["id"]), text=row["name"],
                                     values=(row["einheit"], row["wohnflaeche"], row["personenzahl"],
                                             row["vorauszahlung_monat"]))
        conn.close()

    def _partei_dialog(self, existing=None):
        win = tk.Toplevel(self)
        win.title("Partei" if not existing else "Partei bearbeiten")
        fields = {}
        labels = ["Name", "Einheit/Wohnung (z.B. 'EG links')", "Wohnfläche m²", "Personenzahl",
                  "Einzug (JJJJ-MM-TT)", "Auszug (JJJJ-MM-TT, optional)", "Vorauszahlung €/Monat"]
        keys = ["name", "einheit", "wohnflaeche", "personenzahl", "einzug", "auszug", "vorauszahlung_monat"]
        for i, (lbl, key) in enumerate(zip(labels, keys)):
            ttk.Label(win, text=lbl).grid(row=i, column=0, sticky="w", padx=6, pady=3)
            e = ttk.Entry(win, width=30)
            if existing:
                val = existing[key]
                e.insert(0, "" if val is None else str(val))
            e.grid(row=i, column=1, padx=6, pady=3)
            fields[key] = e

        result = {}

        def on_ok():
            for k, e in fields.items():
                result[k] = e.get()
            win.destroy()

        ttk.Button(win, text="Speichern", command=on_ok).grid(row=len(labels), column=0, columnspan=2, pady=8)
        win.grab_set()
        self.wait_window(win)
        return result if result else None

    def add_partei(self):
        iid = self.current_immobilie_id()
        if not iid:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Immobilie auswählen.")
            return
        data = self._partei_dialog()
        if not data or not data.get("name"):
            return
        conn = get_conn()
        conn.execute("""INSERT INTO parteien
            (immobilie_id, name, einheit, wohnflaeche, personenzahl, einzug, auszug, vorauszahlung_monat)
            VALUES (?,?,?,?,?,?,?,?)""",
            (iid, data["name"], data["einheit"], float(data["wohnflaeche"] or 0),
             int(data["personenzahl"] or 1), data["einzug"], data["auszug"] or None,
             float(data["vorauszahlung_monat"] or 0)))
        conn.commit()
        conn.close()
        self.refresh_parteien()

    def edit_partei(self):
        sel = self.tree_partei.selection()
        if not sel:
            return
        pid = int(sel[0])
        conn = get_conn()
        row = conn.execute("SELECT * FROM parteien WHERE id=?", (pid,)).fetchone()
        data = self._partei_dialog(existing=row)
        if not data:
            conn.close()
            return
        conn.execute("""UPDATE parteien SET name=?, einheit=?, wohnflaeche=?, personenzahl=?,
            einzug=?, auszug=?, vorauszahlung_monat=? WHERE id=?""",
            (data["name"], data["einheit"], float(data["wohnflaeche"] or 0),
             int(data["personenzahl"] or 1), data["einzug"], data["auszug"] or None,
             float(data["vorauszahlung_monat"] or 0), pid))
        conn.commit()
        conn.close()
        self.refresh_parteien()

    def delete_partei(self):
        sel = self.tree_partei.selection()
        if not sel:
            return
        if not messagebox.askyesno("Löschen", "Partei wirklich löschen?"):
            return
        conn = get_conn()
        conn.execute("DELETE FROM parteien WHERE id=?", (int(sel[0]),))
        conn.commit()
        conn.close()
        self.refresh_parteien()

    # -------------------- Tab: Zähler --------------------
    def _build_tab_zaehler(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Zähler & Zählerstände")

        top = ttk.Frame(tab)
        top.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(top)
        left.pack(side="left", fill="both", expand=True)

        self.tree_zaehler = ttk.Treeview(left, columns=("typ", "nummer", "partei"), show="headings", height=16)
        for col, txt, w in [("typ", "Typ", 80), ("nummer", "Zählernummer", 130), ("partei", "Zugeordnete Partei", 160)]:
            self.tree_zaehler.heading(col, text=txt)
            self.tree_zaehler.column(col, width=w)
        self.tree_zaehler.heading("#0", text="Name")
        self.tree_zaehler.pack(fill="both", expand=True)
        self.tree_zaehler.bind("<<TreeviewSelect>>", lambda e: self.refresh_staende())

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=4)
        ttk.Button(btns, text="+ Neuer Zähler", command=self.add_zaehler).pack(side="left", padx=2)
        ttk.Button(btns, text="Bearbeiten", command=self.edit_zaehler).pack(side="left", padx=2)
        ttk.Button(btns, text="Löschen", command=self.delete_zaehler).pack(side="left", padx=2)

        right = ttk.LabelFrame(top, text="Zählerstände")
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        self.tree_stand = ttk.Treeview(right, columns=("datum", "stand", "notiz"), show="headings", height=14)
        for col, txt, w in [("datum", "Datum", 100), ("stand", "Stand", 100), ("notiz", "Notiz", 160)]:
            self.tree_stand.heading(col, text=txt)
            self.tree_stand.column(col, width=w)
        self.tree_stand.pack(fill="both", expand=True)

        btns2 = ttk.Frame(right)
        btns2.pack(fill="x", pady=4)
        ttk.Button(btns2, text="+ Stand erfassen", command=self.add_stand).pack(side="left", padx=2)
        ttk.Button(btns2, text="Löschen", command=self.delete_stand).pack(side="left", padx=2)

    def refresh_zaehler(self):
        self.tree_zaehler.delete(*self.tree_zaehler.get_children())
        iid = self.current_immobilie_id()
        if not iid:
            return
        conn = get_conn()
        rows = conn.execute("""
            SELECT z.*, p.name as partei_name FROM zaehler z
            LEFT JOIN parteien p ON z.partei_id = p.id
            WHERE z.immobilie_id=? ORDER BY z.typ, z.name""", (iid,)).fetchall()
        for row in rows:
            partei_name = row["partei_name"] if row["partei_name"] else "Allgemein/Haus"
            self.tree_zaehler.insert("", "end", iid=str(row["id"]), text=row["name"],
                                      values=(row["typ"], row["nummer"], partei_name))
        conn.close()
        self.refresh_staende()

    def _zaehler_dialog(self, existing=None):
        iid = self.current_immobilie_id()
        conn = get_conn()
        parteien = conn.execute("SELECT id, name FROM parteien WHERE immobilie_id=? ORDER BY name", (iid,)).fetchall()
        conn.close()

        win = tk.Toplevel(self)
        win.title("Zähler")
        ttk.Label(win, text="Name (z.B. 'Zähler Küche')").grid(row=0, column=0, sticky="w", padx=6, pady=3)
        e_name = ttk.Entry(win, width=30)
        e_name.grid(row=0, column=1, padx=6, pady=3)

        ttk.Label(win, text="Typ").grid(row=1, column=0, sticky="w", padx=6, pady=3)
        cb_typ = ttk.Combobox(win, values=ZAEHLERTYPEN, state="readonly", width=27)
        cb_typ.grid(row=1, column=1, padx=6, pady=3)
        cb_typ.set(ZAEHLERTYPEN[0])

        ttk.Label(win, text="Zählernummer").grid(row=2, column=0, sticky="w", padx=6, pady=3)
        e_nummer = ttk.Entry(win, width=30)
        e_nummer.grid(row=2, column=1, padx=6, pady=3)

        ttk.Label(win, text="Zugeordnete Partei").grid(row=3, column=0, sticky="w", padx=6, pady=3)
        partei_map = {"Allgemein/Haus (kein Mieter)": None}
        for p in parteien:
            partei_map[p["name"]] = p["id"]
        cb_partei = ttk.Combobox(win, values=list(partei_map.keys()), state="readonly", width=27)
        cb_partei.grid(row=3, column=1, padx=6, pady=3)
        cb_partei.set("Allgemein/Haus (kein Mieter)")

        if existing:
            e_name.insert(0, existing["name"])
            cb_typ.set(existing["typ"])
            e_nummer.insert(0, existing["nummer"] or "")
            for name, pid in partei_map.items():
                if pid == existing["partei_id"]:
                    cb_partei.set(name)

        result = {}

        def on_ok():
            result["name"] = e_name.get()
            result["typ"] = cb_typ.get()
            result["nummer"] = e_nummer.get()
            result["partei_id"] = partei_map.get(cb_partei.get())
            win.destroy()

        ttk.Button(win, text="Speichern", command=on_ok).grid(row=4, column=0, columnspan=2, pady=8)
        win.grab_set()
        self.wait_window(win)
        return result if result else None

    def add_zaehler(self):
        iid = self.current_immobilie_id()
        if not iid:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Immobilie auswählen.")
            return
        data = self._zaehler_dialog()
        if not data or not data.get("name"):
            return
        conn = get_conn()
        conn.execute("INSERT INTO zaehler (immobilie_id, partei_id, typ, name, nummer) VALUES (?,?,?,?,?)",
                     (iid, data["partei_id"], data["typ"], data["name"], data["nummer"]))
        conn.commit()
        conn.close()
        self.refresh_zaehler()

    def edit_zaehler(self):
        sel = self.tree_zaehler.selection()
        if not sel:
            return
        zid = int(sel[0])
        conn = get_conn()
        row = conn.execute("SELECT * FROM zaehler WHERE id=?", (zid,)).fetchone()
        data = self._zaehler_dialog(existing=row)
        if not data:
            conn.close()
            return
        conn.execute("UPDATE zaehler SET partei_id=?, typ=?, name=?, nummer=? WHERE id=?",
                     (data["partei_id"], data["typ"], data["name"], data["nummer"], zid))
        conn.commit()
        conn.close()
        self.refresh_zaehler()

    def delete_zaehler(self):
        sel = self.tree_zaehler.selection()
        if not sel:
            return
        if not messagebox.askyesno("Löschen", "Zähler inkl. aller Zählerstände wirklich löschen?"):
            return
        conn = get_conn()
        conn.execute("DELETE FROM zaehler WHERE id=?", (int(sel[0]),))
        conn.commit()
        conn.close()
        self.refresh_zaehler()

    def refresh_staende(self):
        self.tree_stand.delete(*self.tree_stand.get_children())
        sel = self.tree_zaehler.selection()
        if not sel:
            return
        zid = int(sel[0])
        conn = get_conn()
        for row in conn.execute("SELECT * FROM zaehlerstaende WHERE zaehler_id=? ORDER BY datum DESC", (zid,)):
            self.tree_stand.insert("", "end", iid=str(row["id"]),
                                    values=(row["datum"], row["stand"], row["notiz"] or ""))
        conn.close()

    def add_stand(self):
        sel = self.tree_zaehler.selection()
        if not sel:
            messagebox.showinfo("Hinweis", "Bitte zuerst einen Zähler auswählen.")
            return
        zid = int(sel[0])
        datum = simpledialog.askstring("Zählerstand", "Datum (JJJJ-MM-TT):",
                                        initialvalue=datetime.date.today().isoformat())
        if not datum:
            return
        stand = simpledialog.askstring("Zählerstand", "Zählerstand:")
        if stand is None:
            return
        notiz = simpledialog.askstring("Zählerstand", "Notiz (optional):") or ""
        try:
            stand_v = float(stand.replace(",", "."))
        except ValueError:
            messagebox.showerror("Fehler", "Ungültiger Zählerstand.")
            return
        conn = get_conn()
        conn.execute("INSERT INTO zaehlerstaende (zaehler_id, datum, stand, notiz) VALUES (?,?,?,?)",
                     (zid, datum, stand_v, notiz))
        conn.commit()
        conn.close()
        self.refresh_staende()

    def delete_stand(self):
        sel = self.tree_stand.selection()
        if not sel:
            return
        conn = get_conn()
        conn.execute("DELETE FROM zaehlerstaende WHERE id=?", (int(sel[0]),))
        conn.commit()
        conn.close()
        self.refresh_staende()

    # -------------------- Tab: Kosten --------------------
    def _build_tab_kosten(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Kostenpositionen")

        top = ttk.Frame(tab)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Label(top, text="Abrechnungsjahr:").pack(side="left")
        self.jahr_kosten = ttk.Combobox(top, values=[str(y) for y in range(2020, 2031)], width=8, state="readonly")
        self.jahr_kosten.set(str(datetime.date.today().year - 1))
        self.jahr_kosten.pack(side="left", padx=6)
        self.jahr_kosten.bind("<<ComboboxSelected>>", lambda e: self.refresh_kosten())

        self.tree_kosten = ttk.Treeview(tab, columns=("betrag", "schluessel"), show="headings", height=16)
        self.tree_kosten.heading("betrag", text="Betrag (€, Jahr gesamt)")
        self.tree_kosten.heading("schluessel", text="Umlageschlüssel")
        self.tree_kosten.column("betrag", width=160)
        self.tree_kosten.column("schluessel", width=200)
        self.tree_kosten.heading("#0", text="Kostenart")
        self.tree_kosten.pack(fill="both", expand=True, padx=6, pady=6)

        btns = ttk.Frame(tab)
        btns.pack(fill="x", padx=6, pady=4)
        ttk.Button(btns, text="+ Kostenposition", command=self.add_kosten).pack(side="left", padx=2)
        ttk.Button(btns, text="Bearbeiten", command=self.edit_kosten).pack(side="left", padx=2)
        ttk.Button(btns, text="Löschen", command=self.delete_kosten).pack(side="left", padx=2)

    def refresh_kosten(self):
        self.tree_kosten.delete(*self.tree_kosten.get_children())
        iid = self.current_immobilie_id()
        if not iid:
            return
        jahr = int(self.jahr_kosten.get())
        conn = get_conn()
        for row in conn.execute("SELECT * FROM kostenpositionen WHERE immobilie_id=? AND jahr=? ORDER BY kostenart",
                                 (iid, jahr)):
            self.tree_kosten.insert("", "end", iid=str(row["id"]), text=row["kostenart"],
                                     values=(f"{row['betrag']:.2f}", row["umlageschluessel"]))
        conn.close()

    def _kosten_dialog(self, existing=None):
        win = tk.Toplevel(self)
        win.title("Kostenposition")
        ttk.Label(win, text="Kostenart").grid(row=0, column=0, sticky="w", padx=6, pady=3)
        cb_art = ttk.Combobox(win, values=KOSTENARTEN_BETRKV, width=35)
        cb_art.grid(row=0, column=1, padx=6, pady=3)

        ttk.Label(win, text="Betrag Jahr gesamt (€)").grid(row=1, column=0, sticky="w", padx=6, pady=3)
        e_betrag = ttk.Entry(win, width=37)
        e_betrag.grid(row=1, column=1, padx=6, pady=3)

        ttk.Label(win, text="Umlageschlüssel").grid(row=2, column=0, sticky="w", padx=6, pady=3)
        cb_schl = ttk.Combobox(win, values=UMLAGESCHLUESSEL, state="readonly", width=35)
        cb_schl.grid(row=2, column=1, padx=6, pady=3)
        cb_schl.set(UMLAGESCHLUESSEL[0])

        if existing:
            cb_art.set(existing["kostenart"])
            e_betrag.insert(0, str(existing["betrag"]))
            cb_schl.set(existing["umlageschluessel"])

        result = {}

        def on_ok():
            result["kostenart"] = cb_art.get()
            result["betrag"] = e_betrag.get()
            result["umlageschluessel"] = cb_schl.get()
            win.destroy()

        ttk.Button(win, text="Speichern", command=on_ok).grid(row=3, column=0, columnspan=2, pady=8)
        win.grab_set()
        self.wait_window(win)
        return result if result else None

    def add_kosten(self):
        iid = self.current_immobilie_id()
        if not iid:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Immobilie auswählen.")
            return
        data = self._kosten_dialog()
        if not data or not data.get("kostenart"):
            return
        try:
            betrag = float(data["betrag"].replace(",", "."))
        except ValueError:
            messagebox.showerror("Fehler", "Ungültiger Betrag.")
            return
        jahr = int(self.jahr_kosten.get())
        conn = get_conn()
        conn.execute("""INSERT INTO kostenpositionen (immobilie_id, jahr, kostenart, betrag, umlageschluessel)
                        VALUES (?,?,?,?,?)""", (iid, jahr, data["kostenart"], betrag, data["umlageschluessel"]))
        conn.commit()
        conn.close()
        self.refresh_kosten()

    def edit_kosten(self):
        sel = self.tree_kosten.selection()
        if not sel:
            return
        kid = int(sel[0])
        conn = get_conn()
        row = conn.execute("SELECT * FROM kostenpositionen WHERE id=?", (kid,)).fetchone()
        data = self._kosten_dialog(existing=row)
        if not data:
            conn.close()
            return
        try:
            betrag = float(data["betrag"].replace(",", "."))
        except ValueError:
            messagebox.showerror("Fehler", "Ungültiger Betrag.")
            conn.close()
            return
        conn.execute("UPDATE kostenpositionen SET kostenart=?, betrag=?, umlageschluessel=? WHERE id=?",
                     (data["kostenart"], betrag, data["umlageschluessel"], kid))
        conn.commit()
        conn.close()
        self.refresh_kosten()

    def delete_kosten(self):
        sel = self.tree_kosten.selection()
        if not sel:
            return
        conn = get_conn()
        conn.execute("DELETE FROM kostenpositionen WHERE id=?", (int(sel[0]),))
        conn.commit()
        conn.close()
        self.refresh_kosten()

    # -------------------- Tab: Abrechnung / PDF --------------------
    def _build_tab_abrechnung(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Abrechnung erstellen")

        top = ttk.Frame(tab)
        top.pack(fill="x", padx=6, pady=10)
        ttk.Label(top, text="Abrechnungsjahr:").pack(side="left")
        self.jahr_abr = ttk.Combobox(top, values=[str(y) for y in range(2020, 2031)], width=8, state="readonly")
        self.jahr_abr.set(str(datetime.date.today().year - 1))
        self.jahr_abr.pack(side="left", padx=6)

        ttk.Button(top, text="📄 Alle Parteien: PDF erstellen", command=self.export_alle_pdf).pack(side="left", padx=20)
        ttk.Button(top, text="📄 Ausgewählte Partei: PDF erstellen", command=self.export_partei_pdf).pack(side="left", padx=6)

        info = ttk.Label(tab, text=(
            "Hinweis: Wählen Sie links die Immobilie und im Tab 'Parteien' eine Partei aus,\n"
            "um gezielt für diese eine Abrechnung zu erstellen. PDFs werden im Ordner\n"
            "'abrechnungen' neben dem Programm gespeichert."), justify="left")
        info.pack(padx=6, pady=10, anchor="w")

        self.abr_log = tk.Text(tab, height=20)
        self.abr_log.pack(fill="both", expand=True, padx=6, pady=6)

    def log(self, msg):
        self.abr_log.insert("end", msg + "\n")
        self.abr_log.see("end")

    def export_alle_pdf(self):
        iid = self.current_immobilie_id()
        if not iid:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Immobilie auswählen.")
            return
        jahr = int(self.jahr_abr.get())
        conn = get_conn()
        parteien = conn.execute("SELECT * FROM parteien WHERE immobilie_id=? ORDER BY name", (iid,)).fetchall()
        conn.close()
        if not parteien:
            messagebox.showinfo("Hinweis", "Keine Parteien für diese Immobilie angelegt.")
            return
        for p in parteien:
            self._erstelle_pdf_fuer_partei(iid, p["id"], jahr)
        messagebox.showinfo("Fertig", f"{len(parteien)} PDF-Abrechnungen erstellt im Ordner 'abrechnungen'.")

    def export_partei_pdf(self):
        iid = self.current_immobilie_id()
        sel = self.tree_partei.selection()
        if not iid or not sel:
            messagebox.showinfo("Hinweis", "Bitte Immobilie und Partei auswählen (Tab 'Parteien').")
            return
        jahr = int(self.jahr_abr.get())
        pid = int(sel[0])
        path = self._erstelle_pdf_fuer_partei(iid, pid, jahr)
        if path:
            messagebox.showinfo("Fertig", f"PDF erstellt:\n{path}")

    def _erstelle_pdf_fuer_partei(self, immobilie_id, partei_id, jahr):
        conn = get_conn()
        immo = conn.execute("SELECT * FROM immobilien WHERE id=?", (immobilie_id,)).fetchone()
        partei = conn.execute("SELECT * FROM parteien WHERE id=?", (partei_id,)).fetchone()
        alle_parteien = conn.execute("SELECT * FROM parteien WHERE immobilie_id=?", (immobilie_id,)).fetchall()
        kosten = conn.execute("SELECT * FROM kostenpositionen WHERE immobilie_id=? AND jahr=?",
                               (immobilie_id, jahr)).fetchall()

        gesamt_flaeche = sum(p["wohnflaeche"] or 0 for p in alle_parteien) or (immo["gesamtwohnflaeche"] or 1)
        gesamt_personen = sum(p["personenzahl"] or 0 for p in alle_parteien) or 1
        gesamt_einheiten = len(alle_parteien) or (immo["gesamteinheiten"] or 1)

        zeilen = []
        summe_anteil = 0.0
        for k in kosten:
            schl = k["umlageschluessel"]
            if schl == "Wohnfläche (m²)":
                anteil = k["betrag"] * ((partei["wohnflaeche"] or 0) / gesamt_flaeche) if gesamt_flaeche else 0
                basis_text = f"{partei['wohnflaeche'] or 0:.1f} von {gesamt_flaeche:.1f} m²"
            elif schl == "Personenzahl":
                anteil = k["betrag"] * ((partei["personenzahl"] or 0) / gesamt_personen) if gesamt_personen else 0
                basis_text = f"{partei['personenzahl'] or 0} von {gesamt_personen} Personen"
            elif schl == "Wohneinheiten":
                anteil = k["betrag"] / gesamt_einheiten if gesamt_einheiten else 0
                basis_text = f"1 von {gesamt_einheiten} Einheiten"
            elif schl == "Verbrauch (Zähler)":
                verbrauch_partei, verbrauch_gesamt = self._verbrauch_fuer(conn, immobilie_id, partei_id, jahr)
                anteil = k["betrag"] * (verbrauch_partei / verbrauch_gesamt) if verbrauch_gesamt else 0
                basis_text = f"{verbrauch_partei:.2f} von {verbrauch_gesamt:.2f} Einheiten (Verbrauch)"
            else:
                anteil = 0
                basis_text = "individuell (bitte manuell prüfen)"
            summe_anteil += anteil
            zeilen.append((k["kostenart"], k["betrag"], schl, basis_text, anteil))

        # Zählerdaten für Anlage
        zaehler_rows = conn.execute("""
            SELECT * FROM zaehler WHERE immobilie_id=? AND (partei_id=? OR partei_id IS NULL)
            ORDER BY typ, name""", (immobilie_id, partei_id)).fetchall()

        zaehler_info = []
        for z in zaehler_rows:
            staende = conn.execute(
                "SELECT * FROM zaehlerstaende WHERE zaehler_id=? ORDER BY datum", (z["id"],)).fetchall()
            jahr_staende = [s for s in staende if s["datum"][:4] == str(jahr)]
            if len(jahr_staende) >= 1:
                start = jahr_staende[0]["stand"]
                ende = jahr_staende[-1]["stand"]
                zaehler_info.append((z["typ"], z["name"], z["nummer"], start, ende, ende - start))

        monate_vorauszahlung = 12
        vorauszahlung_gesamt = (partei["vorauszahlung_monat"] or 0) * monate_vorauszahlung
        saldo = vorauszahlung_gesamt - summe_anteil  # positiv = Guthaben, negativ = Nachzahlung

        conn.close()

        # -------- PDF Erstellung --------
        filename = f"Nebenkostenabrechnung_{immo['name']}_{partei['name']}_{jahr}.pdf"
        filename = "".join(c for c in filename if c.isalnum() or c in " ._-")
        path = os.path.join(PDF_DIR, filename)

        styles = getSampleStyleSheet()
        style_title = ParagraphStyle("title", parent=styles["Title"], fontSize=16)
        style_h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, spaceBefore=10)
        style_normal = styles["Normal"]
        style_small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8)

        doc = SimpleDocTemplate(path, pagesize=A4,
                                 leftMargin=20*mm, rightMargin=20*mm, topMargin=18*mm, bottomMargin=18*mm)
        elements = []

        elements.append(Paragraph("Nebenkostenabrechnung", style_title))
        elements.append(Spacer(1, 4*mm))
        elements.append(Paragraph(f"Abrechnungszeitraum: 01.01.{jahr} – 31.12.{jahr}", style_normal))
        elements.append(Paragraph(f"Objekt: {immo['name']}, {immo['adresse'] or ''}", style_normal))
        elements.append(Paragraph(f"Mietpartei: {partei['name']} ({partei['einheit'] or '-'})", style_normal))
        elements.append(Paragraph(f"Wohnfläche: {partei['wohnflaeche'] or 0} m² · Personen: {partei['personenzahl'] or 0}",
                                   style_normal))
        elements.append(Spacer(1, 6*mm))
        elements.append(HRFlowable(width="100%", color=colors.grey))
        elements.append(Spacer(1, 4*mm))

        elements.append(Paragraph("Kostenaufstellung", style_h2))
        table_data = [["Kostenart", "Gesamtkosten (€)", "Umlageschlüssel", "Anteil-Basis", "Ihr Anteil (€)"]]
        for kostenart, betrag, schl, basis, anteil in zeilen:
            table_data.append([kostenart, f"{betrag:.2f}", schl, basis, f"{anteil:.2f}"])
        table_data.append(["", "", "", "Summe Ihr Anteil", f"{summe_anteil:.2f}"])

        t = Table(table_data, colWidths=[38*mm, 28*mm, 30*mm, 45*mm, 28*mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("ALIGN", (4, 0), (4, -1), "RIGHT"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ecf0f1")),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 8*mm))

        if zaehler_info:
            elements.append(Paragraph("Anlage: Zählerstände", style_h2))
            zt_data = [["Typ", "Zähler", "Nummer", "Anfangsstand", "Endstand", "Verbrauch", "Einheit"]]
            for typ, name, nummer, start, ende, verbrauch in zaehler_info:
                zt_data.append([typ, name, nummer or "-", f"{start:.2f}", f"{ende:.2f}", f"{verbrauch:.2f}",
                                 EINHEITEN.get(typ, "")])
            zt = Table(zt_data, colWidths=[20*mm, 30*mm, 28*mm, 26*mm, 22*mm, 22*mm, 22*mm])
            zt.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#34495e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ]))
            elements.append(zt)
            elements.append(Spacer(1, 8*mm))

        elements.append(Paragraph("Abrechnungsergebnis", style_h2))
        erg_data = [
            ["Summe Ihr Anteil an den Betriebskosten", f"{summe_anteil:.2f} €"],
            [f"Geleistete Vorauszahlungen ({monate_vorauszahlung} Monate à {partei['vorauszahlung_monat'] or 0:.2f} €)",
             f"{vorauszahlung_gesamt:.2f} €"],
            ["Ergebnis", ("Guthaben: " if saldo >= 0 else "Nachzahlung: ") + f"{abs(saldo):.2f} €"],
        ]
        et = Table(erg_data, colWidths=[110*mm, 46*mm])
        et.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#dff0d8" if saldo >= 0 else "#f2dede")),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ]))
        elements.append(et)
        elements.append(Spacer(1, 10*mm))

        elements.append(Paragraph(
            "Hinweis: Diese Abrechnung wurde nach § 556 Abs. 3 BGB i.V.m. der Betriebskostenverordnung (BetrKV) "
            "erstellt. Sie haben das Recht, die dieser Abrechnung zugrunde liegenden Belege beim Vermieter "
            "einzusehen (§ 259 BGB). Einwendungen gegen diese Abrechnung sind spätestens innerhalb von 12 Monaten "
            "nach Zugang schriftlich mitzuteilen.", style_small))
        elements.append(Spacer(1, 6*mm))
        elements.append(Paragraph(f"Erstellt am: {datetime.date.today().strftime('%d.%m.%Y')}", style_small))

        doc.build(elements)
        self.log(f"PDF erstellt: {path}")
        return path

    def _verbrauch_fuer(self, conn, immobilie_id, partei_id, jahr):
        """Ermittelt Verbrauch der Partei und Gesamtverbrauch aller mit Verbrauchszählern
        ausgestatteten Parteien (für Umlageschlüssel 'Verbrauch')."""
        rows = conn.execute("SELECT * FROM zaehler WHERE immobilie_id=?", (immobilie_id,)).fetchall()
        verbrauch_partei = 0.0
        verbrauch_gesamt = 0.0
        for z in rows:
            staende = conn.execute(
                "SELECT * FROM zaehlerstaende WHERE zaehler_id=? AND datum LIKE ? ORDER BY datum",
                (z["id"], f"{jahr}%")).fetchall()
            if len(staende) >= 2:
                v = staende[-1]["stand"] - staende[0]["stand"]
            elif len(staende) == 1:
                v = staende[0]["stand"]
            else:
                v = 0
            if z["partei_id"] is not None:
                verbrauch_gesamt += v
                if z["partei_id"] == partei_id:
                    verbrauch_partei += v
        return verbrauch_partei, verbrauch_gesamt


if __name__ == "__main__":
    app = App()
    app.mainloop()
