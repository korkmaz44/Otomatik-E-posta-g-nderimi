import json
import os

class ConfigManager:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.config = {}

    def load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            self.config = {}
        return self.config

    def save_config(self, config):
        """Tüm config'i kaydet"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        self.config = config

    def save_settings(self, settings):
        config = self.load_config()
        config["settings"] = settings
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        self.config = config

    def save_database(self, database):
        config = self.load_config()
        config["database"] = database
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        self.config = config

    def save_schedule(self, schedule):
        """Zamanlama ayarlarını kaydet"""
        config = self.load_config()
        config["schedule"] = schedule
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        self.config = config

    def load_schedule(self):
        """Zamanlama ayarlarını yükle"""
        config = self.load_config()
        return config.get("schedule", {}) 