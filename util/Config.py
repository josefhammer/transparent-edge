# Josef Hammer (josef.hammer@aau.at)
#
"""
Configuration container. Loads config values from ENV (primary) and a JSON file (secondary).
"""

from json import load as json_load
from os import getenv as os_getenv
from distutils.util import strtobool


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

            for key, value in cfg.items():
                """
                Gets the given config value. 
                Order: ENV variable first, then config file, then defaultValue.
                """
                temp = os_getenv(key)
                if temp is None:
                    cfg[key] = json.get(key, cfg[key])
                else:
                    # extract wanted type from default value
                    #
                    if isinstance(value, bool):
                        temp = bool(strtobool(temp))  # convert str(0/False/1/True) to bool
                    elif isinstance(value, int):
                        temp = int(temp)
                    elif isinstance(value, float):
                        temp = float(temp)
                    cfg[key] = temp
