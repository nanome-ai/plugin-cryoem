import json
import asyncio
import graypy
import logging
import random
import string

from nanome._internal.network.packet import Packet

# from tblib import pickling_support
# pickling_support.install()

logger = logging.getLogger(__name__)


class NTSLoggingHandler(graypy.handler.BaseGELFHandler):
    """Forward Log messages to NTS."""

    def __init__(self, nts_writer, session_id):
        super(NTSLoggingHandler, self).__init__()
        self.writer = nts_writer
        self.session_id = session_id

        # Appending random string to process name makes tracking unique sessions easier
        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        self.process_name = "Session-{}-{}".format(session_id, random_str)
        
        # Server Fields
        # self.plugin_id = plugin_id
        # self.plugin_name = plugin_name
        # self.plugin_class = plugin_class
        # # Session Fields
        # self.org_name = None
        # self.org_id = None
        # self.account_id = None
        # self.account_name = None
        # self._presenter_task = asyncio.create_task(self.set_presenter_info())

    def handle(self, record):
        # Add extra fields to the record.
        record.__dict__.update({
            'process_name': self.process_name,
            # 'plugin_name': self.plugin_name,
            # 'plugin_class': self.plugin_name,
            # 'plugin_id': self.plugin_id,
            # 'nts_host': self._plugin.host,
            # 'source_type': 'Plugin',
            # 'version': self._plugin.version
        })
        return super(NTSLoggingHandler, self).handle(record)

    def emit(self, record):
        gelf_dict = self._make_gelf_dict(record)
        packet = Packet()
        packet.set(0, Packet.packet_type_live_logs, 0)
        packet.write_string(json.dumps(gelf_dict))
        self.writer.write(packet.pack())
        self._emit_task = asyncio.create_task(self.writer.drain())

    async def set_presenter_info(self):
        """Get presenter info from plugin instance and store on handler."""
        presenter_info = await self.session_client.request_presenter_info(self._presenter_info_callback)
        self.org_id = presenter_info.org_id
        self.org_name = presenter_info.org_name
        self.account_id = presenter_info.account_id
        self.account_name = presenter_info.account_name
        logger.info("Presenter info set.")


def configure_session_logging(nts_writer, session_id):
    """Configure logging handler to send logs to main process."""
    logger = logging.getLogger()
    nts_handler = NTSLoggingHandler(nts_writer, session_id)
    # fmt_string = '%(asctime)s : %(processName)s : %(levelname)s : %(module)s : %(message)s'
    # nts_handler.setFormatter(logging.Formatter(fmt_string))
    logger.addHandler(nts_handler)
