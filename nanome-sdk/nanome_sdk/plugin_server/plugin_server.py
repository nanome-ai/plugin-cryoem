import asyncio
import json
import logging
import logging.config
import os
import ssl
import sys

from nanome._internal.network.packet import Packet, PacketTypes
from nanome._internal.serializer_fields import TypeSerializer
from nanome.api.serializers import CommandMessageSerializer
from nanome_sdk import default_logging_config_ini
from nanome_sdk.utils import convert_bytes_to_packet
from nanome_sdk.session import run_session_loop_py


__all__ = ["PluginServer"]


logging.config.fileConfig(default_logging_config_ini)
# root_logger = logging.getLogger()
# root_logger.setLevel(logging.DEBUG)
# handler = logging.StreamHandler()


logger = logging.getLogger(__name__)

KEEP_ALIVE_TIME_INTERVAL = 60.0


class PluginServer:

    def __init__(self):
        self.plugin_id = None
        self.logger = logging.getLogger(name="PluginServer")
        self._sessions = {}
        self.plugin_class = None
        self.polling_tasks = {}

    async def run(self, nts_host, nts_port, plugin_name, description, plugin_class):
        self.plugin_class = plugin_class
        try:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS)
            self.nts_reader, self.nts_writer = await asyncio.open_connection(nts_host, nts_port, ssl=ssl_context)
            await self.connect_plugin(plugin_name, description)

            # Start keep-alive task
            self.keep_alive_task = asyncio.create_task(self.keep_alive(self.plugin_id))
            self.poll_nts_task = asyncio.create_task(self.poll_nts())
            await self.poll_nts_task
        except Exception as e:
            logger.error(e)
            raise e
        finally:
            self.nts_writer.close()

    async def poll_nts(self):
        """Poll NTS for packets, and forward them to the plugin server."""
        while True:
            self.logger.debug("Waiting for NTS Data...")
            received_bytes = await self.nts_reader.readexactly(Packet.packet_header_length)
            unpacked = Packet.header_unpack(received_bytes)
            payload_length = unpacked[4]
            received_bytes += await self.nts_reader.readexactly(payload_length)
            self.logger.debug(f"Received Data from NTS. Size {len(received_bytes)}")
            await self.route_bytes(received_bytes)
            await self.nts_writer.drain()

    async def connect_plugin(self, name, description):
        """Send a packet to NTS to register plugin."""
        environ = os.environ
        key = environ["NTS_KEY"]
        name = environ['PLUGIN_NAME']
        category = ""
        tags = []
        has_advanced = False
        permissions = []
        integrations = []
        description = {
            'name': name,
            'description': description,
            'category': category,
            'tags': tags,
            'hasAdvanced': has_advanced,
            'auth': key,
            'permissions': permissions,
            'integrations': integrations
        }
        packet = Packet()
        plugin_id = 0
        packet.set(0, Packet.packet_type_plugin_connection, plugin_id)
        packet.write_string(json.dumps(description))
        pack = packet.pack()
        self.nts_writer.write(pack)
        await self.nts_writer.drain()
        # Wait for response containing plugin_id
        header = await self.nts_reader.read(Packet.packet_header_length)
        unpacked = Packet.header_unpack(header)
        self.plugin_id = unpacked[3]
        logger.info(f"Plugin id: {self.plugin_id}")

    async def keep_alive(self, plugin_id):
        """Long running task to send keep alive packets to NTS."""
        sleep_time = KEEP_ALIVE_TIME_INTERVAL
        while True:
            await asyncio.sleep(sleep_time)
            logger.debug("Sending keep alive packet.")
            packet = Packet()
            packet.set(plugin_id, PacketTypes.keep_alive, 0)
            pack = packet.pack()
            self.nts_writer.write(pack)
            await self.nts_writer.drain()

    async def route_bytes(self, received_bytes):
        """Route bytes from NTS to the appropriate session."""
        serializer = CommandMessageSerializer()
        packet = convert_bytes_to_packet(received_bytes)
        session_id = packet.session_id
        packet_type = packet.packet_type
        if packet_type == PacketTypes.message_to_plugin:
            self.logger.info("Received message to plugin")
            # If session id does not exist, start a new session process
            if session_id not in self._sessions:
                received_version_table, _, _ = serializer.deserialize_command(packet.payload, None)
                version_table = TypeSerializer.get_best_version_table(received_version_table)
                await self.start_session_process(version_table, packet, self.plugin_class)
            else:
                process = self._sessions[session_id]
                self.logger.debug(f"Writing line to session {session_id}: {len(received_bytes)} bytes")
                process.stdin.write(received_bytes)
                await process.stdin.drain()

        elif packet_type == PacketTypes.client_disconnection:
            self.logger.info(f"Disconnecting Session {session_id}.")
            popen = self._sessions[session_id]
            popen.kill()
            del self._sessions[session_id]

        elif packet_type == PacketTypes.keep_alive:
            # Why is the plugin id returned as the session id?
            session_id = packet.session_id
            msg = f"Keep Alive Packet received. Plugin id: {session_id}"
            self.logger.debug(msg)
        elif packet_type == PacketTypes.plugin_list:
            self.logger.info("Plugin list happening?")

    async def start_session_process(self, version_table, packet, plugin_class):
        plugin_id = packet.plugin_id
        session_id = packet.session_id
        self.logger.info(f"Starting process for Session {session_id}")
        env = {
            'NANOME_VERSION_TABLE': json.dumps(version_table),
            'PATH': os.environ.get('PATH', ''),
        }
        plugin_class_filepath = os.path.abspath(sys.modules[plugin_class.__module__].__file__)
        session_process = await asyncio.create_subprocess_exec(
            sys.executable, run_session_loop_py, str(plugin_id), str(session_id), plugin_class_filepath,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            cwd=os.getcwd(),
            env=env)
        connect_data = await session_process.stdout.read(Packet.packet_header_length)
        try:
            unpacked = Packet.header_unpack(connect_data)
        except Exception:
            self.logger.error("Failed to unpack header")
            return
        payload_length = unpacked[4]
        self.logger.debug(f"Packet payload length: {payload_length}")

        connect_data += await session_process.stdout.read(payload_length)

        self.logger.debug(f"Writing line to NTS: {len(connect_data)} bytes")
        self.nts_writer.write(connect_data)
        self._sessions[session_id] = session_process
        self.polling_tasks[session_id] = asyncio.create_task(self.poll_session(session_process))

    async def poll_session(self, process):
        """Poll a session process for packets, and forward them to NTS."""
        while True:
            # Load header, and then payload
            self.logger.debug("Waiting for session data...")
            outgoing_bytes = await process.stdout.readexactly(Packet.packet_header_length)
            if not outgoing_bytes:
                logger.debug("No outgoing bytes. Ending polling task.")
                break
            _, _, _, _, payload_length = Packet.header_unpack(outgoing_bytes)
            outgoing_bytes += await process.stdout.readexactly(payload_length)
            logger.debug(f"Writing line to NTS: {len(outgoing_bytes)} bytes")
            self.nts_writer.write(outgoing_bytes)
            await self.nts_writer.drain()
