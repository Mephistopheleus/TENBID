"""Configuration loader for TENBID"""
import configparser

class ConfigLoader:
    def __init__(self, config_path='config.ini'):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
    
    def get(self, section, option, fallback=None):
        return self.config.get(section, option, fallback=fallback)
    
    def getint(self, section, option, fallback=None):
        return self.config.getint(section, option, fallback=fallback)
    
    def getfloat(self, section, option, fallback=None):
        return self.config.getfloat(section, option, fallback=fallback)
    
    def getboolean(self, section, option, fallback=None):
        return self.config.getboolean(section, option, fallback=fallback)
    
    def get_list(self, section, option, fallback=None):
        value = self.get(section, option, fallback='')
        return [x.strip() for x in value.split(',')] if value else (fallback or [])
