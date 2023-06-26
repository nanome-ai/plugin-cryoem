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


class SessionLoggingHandler(graypy.handler.BaseGELFHandler):
    """Forward Log messages from session to NTS stream."""

    def __init__(self, nts_writer, session_id, plugin_id, plugin_name, plugin_instance):
        super(SessionLoggingHandler, self).__init__()
        self.writer = nts_writer
        self.session_id = session_id

        # Appending random string to process name makes tracking unique sessions easier
        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        self.process_name = "Session-{}-{}".format(session_id, random_str)

        # Server Fields
        self.plugin_id = plugin_id
        self.plugin_name = plugin_name
        self.plugin_instance = plugin_instance

        # Session Fields, set by set_presenter_info
        self.org_name = None
        self.org_id = None
        self.account_id = None
        self.account_name = None

    def handle(self, record):
        # Add extra fields to the record.
        record.__dict__.update({
            'plugin_name': self.plugin_name,
            'plugin_class': self.plugin_instance.__class__.__name__,
            'plugin_id': self.plugin_id,
            'source_type': 'Plugin',
            'org_name': self.org_name,
            'org_id': self.org_id,
            'user_id': self.account_id,
            'username': self.account_name,
            # 'nts_host': self._plugin.host,
        })
        record.processName = self.process_name
        return super(SessionLoggingHandler, self).handle(record)

    def emit(self, record):
        gelf_dict = self._make_gelf_dict(record)
        packet = Packet()
        packet.set(0, Packet.packet_type_live_logs, 0)
        packet.write_string(json.dumps(gelf_dict))
        self.writer.write(packet.pack())
        self._emit_task = asyncio.create_task(self.writer.drain())

    async def set_presenter_info(self):
        """Get presenter info from plugin instance and store on handler."""
        client = self.plugin_instance.client
        presenter_info = await client.request_presenter_info()
        self.org_id = presenter_info.org_id
        self.org_name = presenter_info.org_name
        self.account_id = presenter_info.account_id
        self.account_name = presenter_info.account_name
        logger.info("Presenter info set.")


async def configure_session_logging(nts_writer, session_id, plugin_id, plugin_name, plugin_instance):
    """Configure logging handler to send logs to main process."""
    logger = logging.getLogger()
    nts_handler = SessionLoggingHandler(nts_writer, session_id, plugin_id, plugin_name, plugin_instance)
    asyncio.create_task(nts_handler.set_presenter_info())
    logger.addHandler(nts_handler)
