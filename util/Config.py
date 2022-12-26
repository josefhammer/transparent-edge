# Josef Hammer (josef.hammer@aau.at)
#
"""
Configuration container. Loads config values from ENV (primary) and a JSON file (secondary).
"""

from json import load as json_load
from os import getenv as os_getenv


class Config(object):
    """ 
    (Dict): key -> value

    Attach all config variables to this class (Config.name = defaultValue).
    All these values will be updated when calling loadConfig().
    """

    def __init__(self, filename: str):
        self.cfgFilename = filename

    def __str__(self):
        return str(vars(self))

    def loadConfig(self):

        cfg = vars(self)

        with open(self.cfgFilename) as file:

            json = json_load(file)

            for key in cfg:
                """
                Gets the given config value. 
                Order: ENV variable first, then config file, then defaultValue.
                """
                cfg[key] = os_getenv(key, json.get(key, cfg[key]))
