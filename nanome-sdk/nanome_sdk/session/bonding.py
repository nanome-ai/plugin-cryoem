from distutils.spawn import find_executable
import logging

logger = logging.getLogger(__name__)


NANOBABEL_PATH = find_executable('nanobabel')
OBABEL_PATH = find_executable('obabel')


class Bonding:

    @staticmethod
    def has_executable():
        """Ensure that nanobabel or openbabel is installed."""
        if not NANOBABEL_PATH and not OBABEL_PATH:
            logger.error("No bonding executable found. Please install openbabel or nanobabel to use Bonding feature.")
            return False
        return True