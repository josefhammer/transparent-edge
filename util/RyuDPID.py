# Josef Hammer (josef.hammer@aau.at)
#
"""
Provides a DPID class (that requires Ryu libs) for the other components.
"""

from ryu.lib.dpid import dpid_to_str, str_to_dpid


class DPID(object):
    """ 
    Provides easy access to a short DPID representation with only the last two digits
    (if the DPID starts with 02-00-00-00-00-).
    """

    def __init__(self, dpid):

        if isinstance(dpid, str):
            if dpid.isdigit():  # digits only? --> a (short) DPID
                dpid = int(dpid)
            else:
                dpid = str_to_dpid(self._fromPretty(dpid))
        if isinstance(dpid, int) and dpid < 100:
            dpid = str_to_dpid(self._fromPretty("02-00-00-00-00-{:02d}".format(dpid)))
        if isinstance(dpid, DPID):
            dpid = dpid.dpid
        self.dpid = dpid

    def _toPretty(self, dpid):
        return '-'.join(dpid[4:][i:i + 2] for i in range(0, 12, 2))

    def _fromPretty(self, dpid):
        if isinstance(dpid, str) and '-' in dpid:
            return '0000' + dpid.replace('-', '')
        return dpid

    def __repr__(self):
        return self._toPretty(dpid_to_str(self.dpid))

    # short, readable version
    #
    def __str__(self):
        dstr = self.__repr__()
        if (dstr.startswith("02-00-00-00-00-")):
            return '#' + str(int(dstr[15:]))
        return dstr

    def asShortInt(self):
        return int(self.dpid % 256)  # we are interested in the last two

    # necessary to be used as dict key
    #
    def __hash__(self):
        return hash(self.dpid)

    def __eq__(self, other):
        if (isinstance(other, DPID)):
            return self.dpid == other.dpid
        return self.dpid == other

    def __ne__(self, other):
        return not self == other
