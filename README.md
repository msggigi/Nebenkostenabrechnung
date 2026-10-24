# Nebenkostenabrechnung

Ein lokales Desktop-Tool (Windows/Mac/Linux) zur Verwaltung von Immobilien,
Mietparteien und Zählern (Strom, Gas, Wasser, Öl) inkl. automatischer
Erstellung rechtssicherer Nebenkostenabrechnungen als PDF (DIN A4, Druckansicht).

## Installation (einmalig auf deinem PC)

1. Python 3.10+ installieren (falls noch nicht vorhanden): https://www.python.org/downloads/
   Beim Installer unter Windows unbedingt "Add Python to PATH" aktivieren.
2. Diesen Ordner (alle Dateien) an einen festen Ort speichern, z. B.:
   C:\Nebenkostenabrechnung\
3. Terminal/Eingabeaufforderung in diesem Ordner öffnen und ausführen:

   pip install -r requirements.txt

## Ausführbares Programm 

Die Versionen als ausführbares Programm findest du unter Releases. Diese werden erzeugt, wenn ein neuer Git-Tag erstellt wird. Manuell kann man dieses Executable erzeugen wie im nächsten Abschnitt beschrieben. 

### EXE-Datei erzeugen

Im selben Ordner ausführen:

   pyinstaller --onefile --noconsole --name "Nebenkostenabrechnung" nebenkosten_tool.py

Danach liegt die fertige Datei unter:

   dist/Nebenkostenabrechnung.exe

Diese .exe kannst du an einen beliebigen Ort verschieben und per Doppelklick
starten - eine Python-Installation ist dann für die Nutzung selbst nicht mehr
nötig (nur für den einmaligen Build-Vorgang).

## Wichtig: Datenspeicherung

Bei jedem Start legt das Programm automatisch neben der .exe (bzw. neben dem
.py-Skript) folgende Ordner an, falls sie nicht existieren:

- data/nebenkosten.db      -> Datenbank mit allen Immobilien, Parteien, Zählern,
                               Zählerständen und Kostenpositionen
- abrechnungen/            -> alle erzeugten PDF-Abrechnungen

Verschiebe niemals nur die .exe allein - verschiebe immer den GESAMTEN Ordner
(exe + data + abrechnungen zusammen), damit alle Daten erhalten bleiben.
Ein Backup dieses gesamten Ordners (z. B. Kopie auf externe Festplatte oder
Cloud-Speicher) ist die beste Absicherung für die nächsten Jahre.

## Nutzung

1. Links: Immobilie anlegen (Name + Adresse), optional Gesamtwohnfläche/-einheiten.
2. Tab "Parteien": Mietparteien mit Wohnfläche, Personenzahl, Einzug/Auszug und
   monatlicher Vorauszahlung anlegen.
3. Tab "Zähler & Zählerstände": Zähler anlegen (Typ Strom/Gas/Wasser/Öl,
   Name, Nummer) und einer Partei zuordnen (oder "Allgemein/Haus" für
   Gemeinschaftszähler). Zählerstände mit Datum erfassen.
4. Tab "Kostenpositionen": Jahreskosten je Kostenart (nach BetrKV) eintragen
   und Umlageschlüssel wählen (Wohnfläche, Personenzahl, Verbrauch, Einheiten
   oder Miteigentumsanteil). Für den individuellen Umlageschlüssel werden die
   Anteile je Kostenposition und Partei als Prozentwert (z. B. `12,5 %`) oder
   Verhältnis (z. B. `125/1000`) eingegeben; zusammen müssen sie 100 % ergeben.
5. Tab "Abrechnung erstellen": Jahr wählen und mit einem Klick PDF für alle
   Parteien oder eine einzelne Partei erzeugen.

## Rechtliche Hinweise / zusätzliche Funktionen (wichtig!)

Damit eine Nebenkostenabrechnung nach deutschem Recht (§ 556 Abs. 3 BGB i.V.m.
der Betriebskostenverordnung, BetrKV) formal korrekt und rechtssicher ist,
enthält das Tool bereits folgende Pflichtelemente automatisch im PDF:

- Abrechnungszeitraum (max. 12 Monate)
- Zusammenstellung der Gesamtkosten je Kostenart (17 BetrKV-Kostenarten
  als Auswahl vorbelegt)
- verwendeter Umlageschlüssel je Kostenart
- konkret berechneter Anteil der jeweiligen Partei
- geleistete Vorauszahlungen und Saldo (Nachzahlung/Guthaben)
- Zählerstände als Anlage bei verbrauchsabhängiger Abrechnung
- Hinweis auf das Recht zur Belegeinsicht (§ 259 BGB) und die 12-Monats-
  Einwendungsfrist

Zusätzlich empfehlenswert, aber (noch) nicht automatisiert - bitte selbst
im Blick behalten:

- Fristen: Die Abrechnung muss dem Mieter spätestens 12 Monate nach Ende
  des Abrechnungszeitraums zugehen, sonst verfällt eine Nachforderung.
- Heizkostenverordnung: Bei Heizung/Warmwasser sind mindestens 50-70% nach
  tatsächlichem Verbrauch abzurechnen, der Rest nach Wohnfläche - das Tool
  bildet einen Verbrauchsschlüssel ab, prüfe aber die gesetzlichen Anteile.
- Belege aufbewahren: Rechnungen zu jeder Kostenart sollten (auch digital)
  mindestens für die Einwendungsfrist griffbereit sein.
- Bei Verkauf/Vermieterwechsel innerhalb des Jahres ggf. anteilige
  Abrechnung zwischen altem und neuem Eigentümer beachten.
- Für gewerbliche Mietverhältnisse können abweichende Regeln gelten.

Diese Punkte sind rechtlich relevant, aber individuell (z. B. vertragliche
Vereinbarungen), daher bewusst nicht automatisch im Tool vorbelegt - im
Zweifel empfiehlt sich eine kurze Prüfung durch einen Mieterverein/Anwalt,
insbesondere bei der ersten Abrechnung für eine neue Immobilie.

## Datensicherung

Da die gesamte Datenbank in einer einzigen Datei (data/nebenkosten.db) liegt,
reicht es, diese Datei regelmäßig zu kopieren (z. B. wöchentlich), um alle
Immobilien, Zähler und Abrechnungen dauerhaft zu sichern.
