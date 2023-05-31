
import functools
import inspect
import logging
import enum

from nanome.api import ui
from collections import defaultdict

logger = logging.getLogger(__name__)


class UICommands(enum.Enum):
    button_press = enum.auto()
    sld_changed = enum.auto()


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
        ui_hook = UICommands.button_press.name
        content_id = btn._content_id
        self.callbacks[content_id][ui_hook] = callback_fn
        btn._pressed_callback = callback_fn

    def register_sld_changed_callback(self, sld: ui.Slider, callback_fn):
        ui_hook = UICommands.sld_changed.name
        content_id = sld._content_id
        self.callbacks[content_id][ui_hook] = callback_fn
        sld._changed_callback = callback_fn

    async def handle_ui_command(self, command, received_obj_list):
        content_id, val = received_obj_list
        menu_content = self.__find_content(content_id)
        if not menu_content:
            logger.warning(f"No callback registered for button {content_id}")
            return
        if type(command) == ui.messages.ButtonCallback:
            cmd_type = UICommands.button_press.name
        elif type(command) == ui.messages.SliderCallback:
            cmd_type = UICommands.sld_changed.name
            menu_content.current_value = val

        callback_fn = self.callbacks[content_id].get(cmd_type)
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

    # def __find_content(self, content_id):
    #     all_content = itertools.chain(*[menu.get_all_content() for menu in self._menus])
    #     content = next((
    #         cntnt for cntnt in all_content
    #         if cntnt._content_id == content_id), None)
    #     return content
