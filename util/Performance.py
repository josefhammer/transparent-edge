from dis import dis
from time import perf_counter


# Use the @disassemble decorator to print the bytecode for a function.
#
def disassemble(func):
    """
    A decorator to print the disassembled code of a function.
    """
    dis(func)
    return func


class PerfCounter:
    """
    Wrapper for perf_counter.
    """

    def __init__(self):
        self._laps = [0]
        self.start = perf_counter()

    def ms(self):
        return int((perf_counter() - self.start) * 1000000) / 1000

    def ns(self):
        return int((perf_counter() - self.start) * 1000000)

    def lap(self):
        self._laps.append(self.ns())

    def laps(self):

        sum = self._laps[-1]
        for i in range(len(self._laps) - 1, 0, -1):
            self._laps[i] -= self._laps[i - 1]

        return '/'.join(str(x / 1000) for x in self._laps[1:]) + " = " + str(sum / 1000)
