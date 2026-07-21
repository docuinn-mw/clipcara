import json
import os

from PyQt6.QtCore import QStandardPaths


class LoopStore:
    """Named A-B regions persisted per audio file, as JSON keyed by
    absolute file path in the platform application-data directory."""

    def __init__(self, path=None):
        if path is None:
            d = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppDataLocation)
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, "loops.json")
        self.path = path
        self._data = {}
        try:
            with open(self.path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._data = data
        except (OSError, ValueError):
            pass

    def loops_for(self, filepath):
        return list(self._data.get(os.path.abspath(filepath), []))

    def add(self, filepath, name, a, b):
        key = os.path.abspath(filepath)
        loops = [l for l in self._data.get(key, []) if l["name"] != name]
        loops.append({"name": name, "a": int(a), "b": int(b)})
        self._data[key] = loops
        self._save()

    def remove(self, filepath, name):
        key = os.path.abspath(filepath)
        loops = [l for l in self._data.get(key, []) if l["name"] != name]
        if loops:
            self._data[key] = loops
        else:
            self._data.pop(key, None)
        self._save()

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._data, f, indent=2)
        os.replace(tmp, self.path)
