from datetime import datetime

class Habit:
    def __init__(self, name: str, periodicity: str, category: str):
        self.id = None
        self.name = name
        self.periodicity = periodicity
        self.category = category
        self.creation_date = datetime.now().isoformat()
        self.completion_dates = []

    def complete_habit(self):
        self.completion_dates.append(datetime.now().isoformat())
