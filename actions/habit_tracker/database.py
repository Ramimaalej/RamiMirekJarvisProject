import sqlite3
import os
from pathlib import Path
from .habit import Habit

_DATA_DIR = Path(__file__).resolve().parent / "data"

class Database:
    def __init__(self):
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.db_path = str(_DATA_DIR / "habits.db")
        self.create_tables()

    def create_tables(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS habits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    periodicity TEXT NOT NULL,
                    category TEXT,
                    creation_date TEXT NOT NULL
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS completions (
                    completion_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id INTEGER NOT NULL,
                    completion_date TEXT NOT NULL,
                    FOREIGN KEY(id) REFERENCES habits(id)
                )
            ''')

    def save_habit(self, habit: Habit):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if habit.id is None:
                cursor.execute('SELECT id FROM habits WHERE name = ?', (habit.name,))
                if cursor.fetchone():
                    raise ValueError(f"Habit '{habit.name}' already exists.")
                cursor.execute('''
                    INSERT INTO habits (name, periodicity, category, creation_date)
                    VALUES (?, ?, ?, ?)
                ''', (habit.name, habit.periodicity, habit.category, habit.creation_date))
                habit.id = cursor.lastrowid
            else:
                cursor.execute('''
                    UPDATE habits SET name=?, periodicity=?, category=?, creation_date=?
                    WHERE id=?
                ''', (habit.name, habit.periodicity, habit.category, habit.creation_date, habit.id))
            cursor.execute('DELETE FROM completions WHERE id=?', (habit.id,))
            for date in habit.completion_dates:
                cursor.execute('INSERT INTO completions (id, completion_date) VALUES (?,?)', (habit.id, date))
            conn.commit()

    def delete_habit(self, id: int):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM habits WHERE id = ?', (id,))
            cursor.execute('DELETE FROM completions WHERE id = ?', (id,))
            conn.commit()

    def load_habits(self) -> list[Habit]:
        habits = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM habits')
            for row in cursor.fetchall():
                habit = Habit(row[1], row[2], row[3])
                habit.id, habit.creation_date = row[0], row[4]
                cursor.execute('SELECT completion_date FROM completions WHERE id = ?', (habit.id,))
                habit.completion_dates = [r[0] for r in cursor.fetchall()]
                habits.append(habit)
        return habits
