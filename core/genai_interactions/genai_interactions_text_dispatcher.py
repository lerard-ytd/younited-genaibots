from typing import List, Optional

from core.action_interactions.action_input import ActionInput
from core.genai_interactions.genai_interactions_text_plugin_base import (
    GenAIInteractionsTextPluginBase,
)
from core.user_interactions.incoming_notification_data_base import (
    IncomingNotificationDataBase,
)
from core.user_interactions.message_type import MessageType
from utils.config_manager.config_model import BotConfig


class GenaiInteractionsTextDispatcher(GenAIInteractionsTextPluginBase):
    def __init__(self, global_manager):
        from core.global_manager import GlobalManager
        self.global_manager : GlobalManager = global_manager
        self.logger = self.global_manager.logger
        self.plugins : List[GenAIInteractionsTextPluginBase] = []
        self.default_plugin_name = None
        self.default_plugin : Optional[GenAIInteractionsTextPluginBase] = None

    def initialize(self, plugins: List[GenAIInteractionsTextPluginBase] = None):
        self.bot_config : BotConfig = self.global_manager.bot_config
        if not plugins:
            self.logger.error("No plugins provided for GenaiInteractionsTextDispatcher")
            return

        self.plugins = plugins
        if self.bot_config.GENAI_TEXT_DEFAULT_PLUGIN_NAME is not None:
            self.logger.info(f"Setting Genai Text default plugin to <{self.bot_config.GENAI_TEXT_DEFAULT_PLUGIN_NAME}>")
            self.default_plugin : GenAIInteractionsTextPluginBase = self.get_plugin(self.bot_config.GENAI_TEXT_DEFAULT_PLUGIN_NAME)
            self.default_plugin_name = self.default_plugin.plugin_name
        else:
            self.default_plugin = plugins[0]
            self.default_plugin_name = self.default_plugin.plugin_name
            self.logger.info(f"Setting Genai Text default plugin to first plugin in list <{self.default_plugin_name}>")

    def get_plugin(self, plugin_name = None):
        if plugin_name is None:
            plugin_name = self.default_plugin_name

        for plugin in self.plugins:
            if plugin.plugin_name == plugin_name:
                return plugin

        self.logger.error(f"GenaiInteractionsTextDispatcher: Plugin '{plugin_name}' not found, returning default plugin")
        return self.default_plugin

    @property
    def plugins(self) -> List[GenAIInteractionsTextPluginBase]:
        return self._plugins

    @plugins.setter
    def plugins(self, value: List[GenAIInteractionsTextPluginBase]):
        self._plugins = value

    @property
    def plugin_name(self, plugin_name = None):
        plugin : GenAIInteractionsTextPluginBase = self.get_plugin(plugin_name)
        return plugin.plugin_name

    @plugin_name.setter
    def plugin_name(self, value):
        plugin : GenAIInteractionsTextPluginBase = self.get_plugin()
        plugin.plugin_name = value

    def validate_request(self, event: IncomingNotificationDataBase, plugin_name = None):
        plugin : GenAIInteractionsTextPluginBase = self.get_plugin(plugin_name)
        return plugin.validate_request(event)

    async def handle_request(self, event: IncomingNotificationDataBase, plugin_name = None):
        plugin : GenAIInteractionsTextPluginBase = self.get_plugin(plugin_name)
        return await plugin.handle_request(event)

    async def trigger_genai(self, event: IncomingNotificationDataBase, plugin_name = None):
        plugin : GenAIInteractionsTextPluginBase = self.get_plugin(plugin_name)
        ts = event.thread_id
        channel_id = str(event.channel_id)
        session_name = f"{channel_id.replace(':','_')}-{ts}.txt"
        abort_container = self.global_manager.backend_internal_data_processing_dispatcher.abort
        aborted = await self.global_manager.backend_internal_data_processing_dispatcher.read_data_content(abort_container, session_name)
        if aborted:
            self.logger.info(f"Aborted session found for {session_name}")
            await self.global_manager.user_interactions_dispatcher.send_message(message=f"Session aborted, discarded autogenerated content (Trigger: {event.text})", event=event, message_type=MessageType.COMMENT, is_internal=True)
            await self.global_manager.user_interactions_dispatcher.send_message(message=f"Session aborted, discarded autogenerated content (Trigger: {event.text})", event=event, message_type=MessageType.COMMENT, is_internal=False)
            return
        await plugin.trigger_genai(event=event)

    async def handle_action(self, action_input: ActionInput, event: IncomingNotificationDataBase, plugin_name = None):
        plugin : GenAIInteractionsTextPluginBase = self.get_plugin(plugin_name)
        return await plugin.handle_action(action_input, event)

    async def load_client(self, plugin_name = None):
        plugin : GenAIInteractionsTextPluginBase = self.get_plugin(plugin_name)
        return await plugin.load_client()

    async def trigger_feedback(self, event: IncomingNotificationDataBase, plugin_name = None):
        plugin : GenAIInteractionsTextPluginBase = self.get_plugin(plugin_name)
        return await plugin.trigger_feedback(event=event)

    async def generate_completion(self, messages, event_data: IncomingNotificationDataBase, plugin_name = None):
        plugin : GenAIInteractionsTextPluginBase = self.get_plugin(plugin_name)
        return await plugin.generate_completion(messages, event_data)
