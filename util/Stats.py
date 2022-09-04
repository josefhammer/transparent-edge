# Josef Hammer (josef.hammer@aau.at)
#
"""
Flow statistics.
"""


class Stats(object):
    """
    Cookie constants to obtain aggregate flow statistics from the switch.
    """

    # NOTE:
    # uint8_t table_id
    # uint64_t cookie
    #
    CATEGORY_MASK = 0xff
    CATEGORY_SHIFT = 8
    DETAIL_SHIFT = 4

    DETECT = 3  # 0011
    REDIR = 12  # 1100

    DETECT_EDGE = ((1 << 0) << DETAIL_SHIFT) + DETECT  # 0
    DETECT_DEFAULT = ((1 << 1) << DETAIL_SHIFT) + DETECT  # 1
    REDIR_EDGE = ((1 << 2) << DETAIL_SHIFT) + REDIR  # 2
    REDIR_DEFAULT = ((1 << 3) << DETAIL_SHIFT) + REDIR  # 3

    @staticmethod
    def cookie(category: int, value: int) -> int:
        """
        :returns: The cookie value combining both category and value.
        """
        return (value << Stats.CATEGORY_SHIFT) + category
