import asyncio
import logging
import sys
from nanome.api import ui
from nanome.api.serializers import CommandMessageSerializer
from nanome.util import enums
from nanome._internal.network.packet import Packet
from nanome._internal.enums import Messages
from server import utils


class SessionClient:
    """Provides API for connecting to a Nanome session."""
    callbacks = dict()  # {content_id: {hook_type: callback_fn}}
    _menus = dict()  # {menu_index: menu}

    def __init__(self, plugin_id, session_id, version_table):
        self.version_table = version_table
        self.plugin_id = plugin_id
        self.session_id = session_id
        self.logger = logging.getLogger(name=f"SessionClient {session_id}")
        self.request_futs = {}
        self.reader = self.writer = None

    async def connect_stdin_stdout(self):
        self.reader, self.writer = await connect_stdin_stdout()

    def update_menu(self, menu, shallow=False):
        self.logger.debug("Sending Update Menu.")
        SessionClient._menus[menu.index] = menu
        message_type = Messages.menu_update
        expects_response = False
        args = [menu, shallow]
        self._send_message(message_type, args, expects_response)

    async def request_complex_list(self):
        message_type = Messages.complex_list_request
        expects_response = True
        args = None
        request_id = self._send_message(message_type, args, expects_response)
        fut = self.request_futs[request_id]
        await fut
        result = fut.result()
        del self.request_futs[request_id]
        return result

    async def send_connect(self, plugin_id, session_id, version_table):
        self.reader, self.writer = await connect_stdin_stdout()
        self.logger.debug("Sending Connect")
        serializer = CommandMessageSerializer()
        message_type = Messages.connect
        request_id = utils.random_request_id()
        args = [Packet._compression_type(), version_table]
        expects_response = False
        message = serializer.serialize_message(request_id, message_type, args, version_table, expects_response)

        packet = Packet()
        packet.set(session_id, Packet.packet_type_message_to_client, plugin_id)
        packet.write(message)
        pack = packet.pack()
        self.writer.write(pack)
        self.logger.debug(f'Connect Size: {len(pack)} bytes')

    async def request_workspace(self):
        message_type = Messages.workspace_request
        expects_response = True
        args = None
        request_id = self._send_message(message_type, args, expects_response)
        fut = self.request_futs[request_id]
        await fut
        result = fut.result()
        del self.request_futs[request_id]
        return result

    async def request_complexes(self, id_list):
        message_type = Messages.complexes_request
        expects_response = True
        args = id_list
        request_id = self._send_message(message_type, args, expects_response)
        fut = self.request_futs[request_id]
        await fut
        result = fut.result()
        del self.request_futs[request_id]
        return result

    def update_workspace(self, workspace):
        message_type = Messages.workspace_update
        expects_response = False
        args = [workspace]
        self._send_message(message_type, args, expects_response)

    async def send_notification(self, notification_type, message):
        message_type = Messages.notification_send
        expects_response = False
        args = [notification_type, message]
        self._send_message(message_type, args, expects_response)

    async def update_structures_deep(self, structures):
        message_type = Messages.structures_deep_update
        expects_response = True
        args = structures
        request_id = self._send_message(message_type, args, expects_response)
        fut = self.request_futs[request_id]
        await fut
        result = fut.result()
        del self.request_futs[request_id]
        return result

    def update_structures_shallow(self, structures):
        message_type = Messages.structures_shallow_update
        expects_response = False
        args = structures
        self._send_message(message_type, args, expects_response)

    def zoom_on_structures(self, structures):
        message_type = Messages.structures_zoom
        expects_response = False
        args = structures
        self._send_message(message_type, args, expects_response)

    def center_on_structures(self, structures):
        message_type = Messages.structures_center
        expects_response = False
        args = structures
        self._send_message(message_type, args, expects_response)

    async def add_to_workspace(self, complex_list):
        message_type = Messages.add_to_workspace
        expects_response = True
        args = complex_list
        request_id = self._send_message(message_type, args, expects_response)
        fut = self.request_futs[request_id]
        await fut
        result = fut.result()
        del self.request_futs[request_id]
        return result

    async def remove_from_workspace(self, complex_list):
        """By removing all atoms from complexes, we can remove them from the workspace."""
        from nanome.api.structure import Complex
        message_type = Messages.structures_deep_update
        expects_response = True
        empty_complexes = []
        for complex in complex_list:
            empty = Complex()
            empty.index = complex.index
            empty_complexes.append(empty)
        args = empty_complexes
        request_id = self._send_message(message_type, args, expects_response)
        fut = self.request_futs[request_id]
        await fut
        result = fut.result()
        del self.request_futs[request_id]
        return result

    def update_content(self, *content):
        message_type = Messages.content_update
        expects_response = False
        args = list(content)
        self._send_message(message_type, args, expects_response)

    def update_node(self, *nodes):
        message_type = Messages.node_update
        expects_response = False
        args = nodes
        self._send_message(message_type, args, expects_response)

    def set_menu_transform(self, index, position, rotation, scale):
        message_type = Messages.menu_transform_set
        expects_response = False
        args = [index, position, rotation, scale]
        self._send_message(message_type, args, expects_response)

    async def request_menu_transform(self, index):
        message_type = Messages.menu_transform_request
        expects_response = True
        args = [index]
        request_id = self._send_message(message_type, args, expects_response)
        fut = self.request_futs[request_id]
        await fut
        result = fut.result()
        del self.request_futs[request_id]
        return result

    async def save_files(self, file_list):
        message_type = Messages.file_save
        expects_response = True
        args = file_list
        request_id = self._send_message(message_type, args, expects_response)
        fut = self.request_futs[request_id]
        await fut
        result = fut.result()
        del self.request_futs[request_id]
        return result

    async def create_writing_stream(self, indices_list, stream_type):
        message_type = Messages.stream_create
        expects_response = True
        args = (stream_type, indices_list, enums.StreamDirection.writing)
        request_id = self._send_message(message_type, args, expects_response)
        fut = self.request_futs[request_id]
        await fut
        result = fut.result()
        del self.request_futs[request_id]
        return result

    async def create_reading_stream(self, indices_list, stream_type):
        message_type = Messages.stream_create
        expects_response = True
        args = (stream_type, indices_list, enums.StreamDirection.reading)
        request_id = self._send_message(message_type, args, expects_response)
        fut = self.request_futs[request_id]
        await fut
        result = fut.result()
        del self.request_futs[request_id]
        return result

    async def add_volume(self, comp, volume, properties, complex_to_align_index=-1):
        message_type = Messages.add_volume
        expects_response = True
        args = (comp, complex_to_align_index, volume, properties)
        request_id = self._send_message(message_type, args, expects_response)
        fut = self.request_futs[request_id]
        await fut
        result = fut.result()
        del self.request_futs[request_id]
        return result

    def open_url(self, url, desktop_browser=False):
        message_type = Messages.open_url
        expects_response = False
        args = (url, desktop_browser)
        self._send_message(message_type, args, expects_response)

    async def request_presenter_info(self):
        message_type = Messages.presenter_info_request
        expects_response = True
        args = None
        request_id = self._send_message(message_type, args, expects_response)
        fut = self.request_futs[request_id]
        await fut
        result = fut.result()
        del self.request_futs[request_id]
        return result

    async def request_controller_transforms(self):
        message_type = Messages.controller_transforms_request
        expects_response = True
        args = None
        request_id = self._send_message(message_type, args, expects_response)
        fut = self.request_futs[request_id]
        await fut
        result = fut.result()
        del self.request_futs[request_id]
        return result

    def set_plugin_list_button(self, button: ui.Button, text: str = None, usable: bool = None):
        message_type = Messages.plugin_list_button_set
        expects_response = False
        args = (button, text, usable)
        self._send_message(message_type, args, expects_response)

    async def send_files_to_load(self, files_list):
        message_type = Messages.load_file
        expects_response = True
        args = (files_list, True, True)
        request_id = self._send_message(message_type, args, expects_response)
        fut = self.request_futs[request_id]
        await fut
        result = fut.result()
        del self.request_futs[request_id]
        return result

    async def request_export(self, format, entities=None):
        message_type = Messages.export_files
        expects_response = True
        args = (format, entities)
        request_id = self._send_message(message_type, args, expects_response)
        fut = self.request_futs[request_id]
        await fut
        result = fut.result()
        del self.request_futs[request_id]
        return result

    def apply_color_scheme(self, color_scheme, target, only_carbons):
        message_type = Messages.apply_color_scheme
        expects_response = False
        args = (color_scheme, target, only_carbons)
        self._send_message(message_type, args, expects_response)

    def _send_message(self, message_type, args, expects_response=False):
        request_id = utils.random_request_id()
        serializer = CommandMessageSerializer()
        message = serializer.serialize_message(request_id, message_type, args, self.version_table, expects_response)
        packet = Packet()
        packet.set(self.session_id, Packet.packet_type_message_to_client, self.plugin_id)
        packet.write(message)
        pack = packet.pack()
        if expects_response:
            # Store future to receive any response required
            fut = asyncio.Future()
            self.request_futs[request_id] = fut
        self.writer.write(pack)
        return request_id

    @classmethod
    def register_btn_pressed_callback(cls, btn: ui.Button, callback_fn):
        # hook_ui_callback = Messages.hook_ui_callback
        ui_hook = 'button_press'  # Not acutally enumerated anywhere
        if btn not in cls.callbacks:
            cls.callbacks[btn] = dict()
        cls.callbacks[btn][ui_hook] = callback_fn
        btn._pressed_callback = callback_fn


async def connect_stdin_stdout():
    """Wrap stdin and stdout in StreamReader and StreamWriter interface.

    allows async reading and writing.
    """
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader(limit=2**32)
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    w_transport, w_protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout)
    writer = asyncio.StreamWriter(w_transport, w_protocol, reader, loop)
    return reader, writer
