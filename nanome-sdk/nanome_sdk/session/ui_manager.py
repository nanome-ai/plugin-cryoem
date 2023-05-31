
import functools
import inspect
import logging
import enum

from nanome.api import ui
from collections import defaultdict
from nanome._internal.enums import Commands

logger = logging.getLogger(__name__)


class UIManager:

    def __init__(self):
        self.callbacks = defaultdict(dict)
        self._menus = []

    def __new__(cls):
        # Create Singleton object
        if not hasattr(cls, 'instance'):
            cls.instance = super(UIManager, cls).__new__(cls)
        return cls.instance

    def create_new_menu(self, json_path):
        menu = ui.Menu.io.from_json(json_path)
        self._menus.append(menu)
        return menu

    def register_btn_pressed_callback(self, btn: ui.Button, callback_fn):
        # hook_ui_callback = Messages.hook_ui_callback
        ui_hook = Commands.button_press
        content_id = btn._content_id
        self.callbacks[content_id][ui_hook] = callback_fn

    def register_slider_change_callback(self, sld: ui.Slider, callback_fn):
        ui_hook = Commands.slider_change
        content_id = sld._content_id
        self.callbacks[content_id][ui_hook] = callback_fn

    def register_slider_released_callback(self, sld: ui.Slider, callback_fn):
        ui_hook = Commands.slider_release
        content_id = sld._content_id
        self.callbacks[content_id][ui_hook] = callback_fn

    async def handle_ui_command(self, command, received_obj_list):
        content_id, val = received_obj_list
        menu_content = self.__find_content(content_id)
        if not menu_content:
            logger.warning(f"No callback registered for button {content_id}")
            return
        if command == Commands.button_press:
            pass
        elif command in [Commands.slider_change, Commands.slider_release]:
            menu_content.current_value = val
        else:
            logger.debug('huh?')

        callback_fn = self.callbacks[content_id].get(command)
        is_async_fn = inspect.iscoroutinefunction(callback_fn)
        is_async_partial = isinstance(callback_fn, functools.partial) and \
            inspect.iscoroutinefunction(callback_fn.func)

        if is_async_fn or is_async_partial:
            await callback_fn(menu_content)
        elif callback_fn:
            callback_fn(menu_content)
        else:
            # no callback registered
            logger.warning(f"No callback registered for button {content_id}")

    def __find_content(self, content_id):
        content = None
        for menu in self._menus:
            content = menu.find_content(content_id)
            if content:
                break
        return content

    @staticmethod
    def find_command(command_hash):
        from nanome.api._hashes import Hashes
        from nanome.api.ui import registered_commands
        cmds = [tup[0] for tup in registered_commands]
        command = None
        for cmd in cmds:
            if Hashes.hash_command(cmd.name) == command_hash:
                command = cmd
                break
        return command
    # def __find_content(self, content_id):
    #     all_content = itertools.chain(*[menu.get_all_content() for menu in self._menus])
    #     content = next((
    #         cntnt for cntnt in all_content
    #         if cntnt._content_id == content_id), None)
    #     return content
