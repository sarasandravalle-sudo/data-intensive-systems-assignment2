"""Assignment 2: three SQLite databases and a Tkinter front end.

"""
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox

BASE_DIR = Path(__file__).resolve().parent
DATABASES = {"Suomi": "finland.db", "Ruotsi": "sweden.db", "Saksa": "germany.db"}
STATUSES = ("Avoin", "Työn alla", "Ratkaistu", "Suljettu")
PRIORITIES = ("Matala", "Normaali", "Korkea")


class IncidentStore:
    """Read and write incidents in the selected country's separate database."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, country):
        """Return an allowlisted country database path; reject other selections."""
        if country not in DATABASES:
            raise ValueError("Tuntematon tietokanta.")
        return self.directory / DATABASES[country]

    def connect(self, country):
        """Open one database connection; callers close it with closing()."""
        connection = sqlite3.connect(str(self.path(country)), timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self):
        """Create all three databases and add 30 dummy rows to each empty table."""
        examples = [
            ("Tietokone ei käynnisty", "Virtapainike ei reagoi. Laturi on kytketty."),
            ("VPN-yhteys katkeilee", "Etäyhteys katkeaa useita kertoja päivässä."),
            ("Tulostus ei onnistu", "Tulostustyö jää jonoon eikä tulostin reagoi."),
            ("Sähköposti ei päivity", "Uudet viestit eivät näy työaseman sovelluksessa."),
            ("Näyttö välkkyy", "Ulkoinen näyttö välkkyy telakointiasemassa."),
            ("Mikrofoni ei toimi", "Videopalaverin osallistujat eivät kuule ääntä."),
        ]
        for country, prefix in zip(DATABASES, ("FI", "SE", "DE")):
            with closing(self.connect(country)) as con, con:
                con.execute("""CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL CHECK(length(trim(title)) > 0),
                    reporter TEXT NOT NULL CHECK(length(trim(reporter)) > 0),
                    serial TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL CHECK(length(trim(description)) > 0),
                    status TEXT NOT NULL CHECK(status IN
                        ('Avoin','Työn alla','Ratkaistu','Suljettu')),
                    priority TEXT NOT NULL CHECK(priority IN ('Matala','Normaali','Korkea')),
                    updated_at TEXT NOT NULL
                )""")
                if con.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] == 0:
                    for i in range(30):
                        title, description = examples[i % len(examples)]
                        stamp = (datetime(2026, 10, 1, 9) + timedelta(hours=i)).isoformat(timespec="seconds")
                        con.execute("""INSERT INTO incidents
                            (title, reporter, serial, description, status, priority, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (title, "Demo-käyttäjä %02d" % (i % 10 + 1),
                             "%s-LAP-%03d" % (prefix, i + 1), description,
                             STATUSES[i % len(STATUSES)], PRIORITIES[i % len(PRIORITIES)], stamp))

    def list_incidents(self, country):
        """Return all rows from the chosen database, newest IDs first."""
        with closing(self.connect(country)) as con:
            return con.execute("SELECT * FROM incidents ORDER BY id DESC").fetchall()

    def get(self, country, incident_id):
        """Return one row, or None if the selected ID no longer exists."""
        with closing(self.connect(country)) as con:
            return con.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()

    def save(self, country, incident_id, values):
        """Insert (ID None) or update a row; validate fields and return its ID.

        values contains title, reporter, serial, description, status and priority.
        SQL parameters keep user input separate from SQL statements.
        """
        cleaned = {name: values[name].strip() for name in
                   ("title", "reporter", "serial", "description", "status", "priority")}
        if not all(cleaned[name] for name in ("title", "reporter", "description")):
            raise ValueError("Täytä otsikko, ilmoittaja ja ongelman kuvaus.")
        if cleaned["status"] not in STATUSES or cleaned["priority"] not in PRIORITIES:
            raise ValueError("Valitse tila ja kiireellisyys valintalistoista.")
        args = tuple(cleaned[name] for name in
                     ("title", "reporter", "serial", "description", "status", "priority"))
        args += (datetime.now().isoformat(timespec="seconds"),)
        with closing(self.connect(country)) as con, con:
            if incident_id is None:
                cursor = con.execute("""INSERT INTO incidents
                    (title, reporter, serial, description, status, priority, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""", args)
                return cursor.lastrowid
            cursor = con.execute("""UPDATE incidents SET title=?, reporter=?, serial=?,
                description=?, status=?, priority=?, updated_at=? WHERE id=?""",
                args + (incident_id,))
            if cursor.rowcount != 1:
                raise ValueError("Pyyntöä ei enää löydy. Päivitä lista.")
            return incident_id


class IncidentApp(ttk.Frame):
    """A database selector, a readable table and an editable incident form."""

    def __init__(self, root, store):
        super().__init__(root, padding=16)
        self.pack(fill="both", expand=True)
        self.store = store
        self.selected_id = None
        self.country = tk.StringVar(value="Suomi")
        self.info = tk.StringVar()
        self.form_title = tk.StringVar(value="Uusi tukipyyntö")
        self.fields = {name: tk.StringVar() for name in
                       ("title", "reporter", "serial", "status", "priority")}
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        ttk.Label(self, text="IT-tuki: kolme tietokantaa", font=("Arial", 19, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 14))
        toolbar = ttk.Frame(self)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(toolbar, text="Valitse tietokanta:").pack(side="left")
        selector = ttk.Combobox(toolbar, textvariable=self.country,
                                values=list(DATABASES), state="readonly", width=15)
        selector.pack(side="left", padx=10)
        selector.bind("<<ComboboxSelected>>", self.change_database)
        ttk.Button(toolbar, text="Päivitä lista", command=self.refresh).pack(side="left")
        ttk.Label(toolbar, text="Kaikki tiedot ovat kuvitteellista harjoitusdataa.").pack(side="right")

        columns = ("id", "title", "reporter", "status", "priority")
        listing = ttk.Frame(self)
        listing.grid(row=2, column=0, sticky="nsew")
        listing.rowconfigure(0, weight=1)
        listing.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(listing, columns=columns, show="headings", height=10,
                                 selectmode="browse")
        for key, label, width in zip(columns, ("ID", "Ongelma", "Ilmoittaja", "Tila", "Kiireellisyys"),
                                     (55, 330, 180, 130, 115)):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=50, stretch=(key == "title"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(listing, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self.select_incident)

        form = ttk.LabelFrame(self, text="Valitun pyynnön tiedot", padding=12)
        form.grid(row=3, column=0, sticky="ew", pady=12)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)
        ttk.Label(form, textvariable=self.form_title, font=("Arial", 11, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        for label, key, row, column in (("Otsikko *", "title", 1, 0),
                                       ("Ilmoittaja *", "reporter", 1, 2),
                                       ("Sarjanumero", "serial", 2, 0)):
            ttk.Label(form, text=label).grid(row=row, column=column, sticky="w", padx=(0, 8), pady=4)
            ttk.Entry(form, textvariable=self.fields[key]).grid(
                row=row, column=column + 1, sticky="ew", padx=(0, 16), pady=4)
        ttk.Label(form, text="Tila").grid(row=2, column=2, sticky="w")
        ttk.Combobox(form, textvariable=self.fields["status"], values=STATUSES,
                     state="readonly").grid(row=2, column=3, sticky="ew", padx=(0, 16))
        ttk.Label(form, text="Kiireellisyys").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Combobox(form, textvariable=self.fields["priority"], values=PRIORITIES,
                     state="readonly").grid(row=3, column=1, sticky="ew", padx=(0, 16))
        ttk.Label(form, text="Kuvaus *").grid(row=4, column=0, sticky="nw", pady=6)
        self.description = tk.Text(form, height=3, wrap="word", font=("Arial", 10))
        self.description.grid(row=4, column=1, columnspan=3, sticky="ew", padx=(0, 16), pady=6)
        actions = ttk.Frame(form)
        actions.grid(row=5, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Button(actions, text="Uusi tukipyyntö", command=self.new_incident).pack(side="left")
        ttk.Button(actions, text="Tallenna", command=self.save_incident).pack(side="left", padx=10)
        ttk.Label(self, textvariable=self.info, wraplength=900).grid(row=4, column=0, sticky="w")
        self.change_database()

    def change_database(self, _event=None):
        """Clear the form so a row ID cannot accidentally target another country."""
        self.new_incident()
        self.refresh()

    def refresh(self, select_id=None):
        """Read the active database and replace the visible list."""
        try:
            rows = self.store.list_incidents(self.country.get())
            self.tree.delete(*self.tree.get_children())
            for row in rows:
                self.tree.insert("", "end", iid=str(row["id"]), values=tuple(
                    row[key] for key in ("id", "title", "reporter", "status", "priority")))
            self.info.set("Tietokanta: %s | %d tukipyyntöä | %s" %
                          (self.country.get(), len(rows), self.store.path(self.country.get())))
            if select_id is not None and self.tree.exists(str(select_id)):
                self.tree.selection_set(str(select_id))
                self.tree.see(str(select_id))
        except sqlite3.Error as error:
            messagebox.showerror("Tietokantavirhe", str(error))

    def new_incident(self):
        """Start an empty form for insertion into the active database."""
        self.selected_id = None
        self.tree.selection_remove(*self.tree.selection())
        self.form_title.set("Uusi tukipyyntö — " + self.country.get())
        for value in self.fields.values():
            value.set("")
        self.fields["status"].set("Avoin")
        self.fields["priority"].set("Normaali")
        self.description.delete("1.0", "end")

    def select_incident(self, _event=None):
        """Load the selected row from the currently selected database."""
        selection = self.tree.selection()
        if not selection:
            return
        try:
            row = self.store.get(self.country.get(), int(selection[0]))
            if row is None:
                return
            self.selected_id = row["id"]
            self.form_title.set("Muokkaa pyyntöä #%s — %s" % (row["id"], self.country.get()))
            for key, value in self.fields.items():
                value.set(row[key])
            self.description.delete("1.0", "end")
            self.description.insert("1.0", row["description"])
        except sqlite3.Error as error:
            messagebox.showerror("Tietokantavirhe", str(error))

    def save_incident(self):
        """Save form changes and refresh the active country's table."""
        values = {key: value.get() for key, value in self.fields.items()}
        values["description"] = self.description.get("1.0", "end-1c")
        try:
            incident_id = self.store.save(self.country.get(), self.selected_id, values)
            self.selected_id = incident_id
            self.refresh(select_id=incident_id)
            self.form_title.set("Muokkaa pyyntöä #%s — %s" % (incident_id, self.country.get()))
            self.info.set("Tallennettu pyyntö #%s tietokantaan %s. Muutos säilyy uudelleenkäynnistyksessä." %
                          (incident_id, DATABASES[self.country.get()]))
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Tallennus ei onnistunut", str(error))


def main():
    """Initialize the files and start the desktop application."""
    root = tk.Tk()
    root.title("Assignment 2 — IT-tuki")
    root.geometry("1040x780")
    root.minsize(930, 700)
    store = IncidentStore(BASE_DIR / "databases")
    try:
        store.initialize()
    except (OSError, sqlite3.Error) as error:
        messagebox.showerror("Käynnistys ei onnistunut", "Pura ZIP ensin tavalliseen kansioon.\n\n" + str(error))
        root.destroy()
        return
    IncidentApp(root, store)
    root.mainloop()


if __name__ == "__main__":
    main()
