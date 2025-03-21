from typing import List, Optional, Tuple  
  
from core.backend.internal_queue_processing_base import InternalQueueProcessingBase  
  
  
class BackendInternalQueueProcessingDispatcher(InternalQueueProcessingBase):  
    """  
    Dispatcher for managing internal queue processing plugins.  
    """  
    def __init__(self, global_manager):  
        from core.global_manager import GlobalManager  
        self.global_manager: GlobalManager = global_manager  
        self.logger = self.global_manager.logger  
        self.plugins: List[InternalQueueProcessingBase] = []  
        self.default_plugin_name = None  
        self.default_plugin: Optional[InternalQueueProcessingBase] = None  
  
    def initialize(self, plugins: List[InternalQueueProcessingBase] = None):  
        if not plugins:  
            self.logger.error("No plugins provided for BackendInternalQueueProcessingDispatcher")  
            return  
  
        self.plugins = plugins  
        self.default_plugin_name = self.global_manager.bot_config.INTERNAL_QUEUE_PROCESSING_DEFAULT_PLUGIN_NAME  
        self.default_plugin = self.get_plugin(self.default_plugin_name)  
  
    def get_plugin(self, plugin_name=None):  
        if plugin_name is None:  
            if self.default_plugin is None:  
                raise ValueError("No default plugin configured")  
            return self.default_plugin  
  
        for plugin in self.plugins:  
            if plugin.plugin_name == plugin_name:  
                return plugin  
  
        self.logger.error(f"BackendInternalQueueProcessingDispatcher: Plugin '{plugin_name}' not found, returning default plugin")  
        if self.default_plugin is None:  
            raise ValueError(f"Plugin '{plugin_name}' not found and no default plugin is set")  
        return self.default_plugin  
  
    @property  
    def plugins(self) -> List[InternalQueueProcessingBase]:  
        return self._plugins  
  
    @plugins.setter  
    def plugins(self, value: List[InternalQueueProcessingBase]):  
        self._plugins = value  
  
    @property  
    def plugin_name(self) -> str:  
        """  
        This property provides the plugin name.  
        """  
        return "backend_internal_queue_processing_dispatcher"  # Implementation of the abstract method  
  
    @property  
    def messages_queue(self, plugin_name=None):  
        plugin: InternalQueueProcessingBase = self.get_plugin(plugin_name)  
        return plugin.messages_queue  
  
    @property  
    def messages_queue_ttl(self, plugin_name=None):  
        plugin: InternalQueueProcessingBase = self.get_plugin(plugin_name)  
        return plugin.messages_queue_ttl  
  
    @property  
    def internal_events_queue(self, plugin_name=None):  
        plugin: InternalQueueProcessingBase = self.get_plugin(plugin_name)  
        return plugin.internal_events_queue  
  
    @property  
    def internal_events_queue_ttl(self, plugin_name=None):  
        plugin: InternalQueueProcessingBase = self.get_plugin(plugin_name)  
        return plugin.internal_events_queue_ttl  
  
    @property  
    def external_events_queue(self, plugin_name=None):  
        plugin: InternalQueueProcessingBase = self.get_plugin(plugin_name)  
        return plugin.external_events_queue  
  
    @property  
    def external_events_queue_ttl(self, plugin_name=None):  
        plugin: InternalQueueProcessingBase = self.get_plugin(plugin_name)  
        return plugin.external_events_queue_ttl  
  
    @property  
    def wait_queue(self, plugin_name=None):  
        plugin: InternalQueueProcessingBase = self.get_plugin(plugin_name)  
        return plugin.wait_queue  
  
    @property  
    def wait_queue_ttl(self, plugin_name=None):  
        plugin: InternalQueueProcessingBase = self.get_plugin(plugin_name)  
        return plugin.wait_queue_ttl  
  
    async def enqueue_message(self, data_container: str, channel_id: str, thread_id: str, message_id: str, message: str, guid: str, plugin_name: Optional[str] = None) -> None:  
        """  
        Adds a message to the queue for a given channel and thread, including a GUID for uniqueness.  
        """  
        plugin = self.get_plugin(plugin_name)  
  
        # Logging for tracking  
        self.logger.debug(f"Enqueuing message in {channel_id}_{thread_id}_{message_id}_{guid} through {plugin.plugin_name}.")  
  
        # Adding the GUID in the call to the plugin's enqueue method  
        await plugin.enqueue_message(data_container=data_container, channel_id=channel_id, thread_id=thread_id, message_id=message_id, message=message, guid=guid)  
  
  
    async def dequeue_message(self, data_container: str, channel_id: str, thread_id: str, message_id: str, guid: str, plugin_name: Optional[str] = None) -> None:  
        """  
        Removes a message from the queue after processing, using the GUID for uniqueness.  
        """  
        plugin = self.get_plugin(plugin_name)  
  
        # Logging for tracking  
        self.logger.debug(f"Dequeuing message {message_id}_{guid} from {channel_id}_{thread_id} through {plugin.plugin_name}.")  
  
        # Calling the dequeue method with the message_id and guid  
        await plugin.dequeue_message(data_container=data_container, channel_id=channel_id, thread_id=thread_id, message_id=message_id, guid=guid)  
  
  
    async def get_next_message(self, data_container: str, channel_id: str, thread_id: str, current_message_id: str, plugin_name: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:  
        """  
        Retrieves the next (oldest) message for a `channel_id` and `thread_id` after `current_message_id`.  
        Returns a tuple (message_id, message_content). If no message is found, returns (None, None).  
        """  
        plugin = self.get_plugin(plugin_name)  
        self.logger.debug(f"Getting next message for channel '{channel_id}', thread '{thread_id}' with current message_id '{current_message_id}' through {plugin.plugin_name}.")  
        return await plugin.get_next_message(data_container=data_container, channel_id=channel_id, thread_id=thread_id, current_message_id=current_message_id)  
  
    async def has_older_messages(self, data_container: str, channel_id: str, thread_id: str, current_message_id: str, plugin_name: Optional[str] = None) -> bool:  
        """  
        Checks if there are any older messages waiting in the queue for the given channel and thread.  
        """  
        plugin = self.get_plugin(plugin_name)  
        self.logger.debug(f"Checking for older messages in {channel_id}_{thread_id} through {plugin.plugin_name}.")  
        return await plugin.has_older_messages(data_container=data_container, channel_id=channel_id, thread_id=thread_id, current_message_id=current_message_id)  
  
    async def clear_messages_queue(self, data_container: str, channel_id: str, thread_id: str, plugin_name: Optional[str] = None) -> None:  
        """  
        Clears all messages in the queue for a given channel and thread.  
        """  
        plugin = self.get_plugin(plugin_name)  
        self.logger.info(f"Clearing messages queue for channel '{channel_id}', thread '{thread_id}' through {plugin.plugin_name}.")  
        await plugin.clear_messages_queue(data_container=data_container, channel_id=channel_id, thread_id=thread_id)  
  
    async def get_all_messages(self, data_container: str, channel_id: str, thread_id: str, plugin_name: Optional[str] = None) -> List[str]:  
        """  
        Retrieves the contents of all messages for a `channel_id` and `thread_id`.  
        Returns a list of message contents.  
        """  
        plugin = self.get_plugin(plugin_name)  
        self.logger.info(f"Retrieving all messages for channel '{channel_id}', thread '{thread_id}' through {plugin.plugin_name}.")  
        return await plugin.get_all_messages(data_container=data_container, channel_id=channel_id, thread_id=thread_id)  
  
    async def cleanup_expired_messages(self, data_container: str, channel_id: str, thread_id: str, ttl_seconds: int, plugin_name: Optional[str] = None) -> None:  
        """  
        Cleans up expired messages for a given thread/channel in the queue based on TTL.  
        Removes messages whose creation time exceeds the TTL.  
        """  
        plugin = self.get_plugin(plugin_name)  
        self.logger.info(f"Cleaning up expired messages for channel '{channel_id}', thread '{thread_id}' through {plugin.plugin_name}.")  
        await plugin.cleanup_expired_messages(data_container=data_container, channel_id=channel_id, thread_id=thread_id, ttl_seconds=ttl_seconds)  
  
    async def clear_all_queues(self, plugin_name: Optional[str] = None) -> None:  
        """  
        Clears all messages across all queues for the specified plugin.  
        This removes all messages, regardless of TTL.  
        """  
        plugin = self.get_plugin(plugin_name)  
        self.logger.info(f"Clearing all queues through {plugin.plugin_name}.")  
        await plugin.clear_all_queues()  
  
    async def clean_all_queues(self, plugin_name: Optional[str] = None) -> None:  
        """  
        Cleans up expired messages across all queues at startup based on TTL.  
        This ensures no expired messages remain in the system across all channels and threads.  
        """  
        plugin = self.get_plugin(plugin_name)  
        self.logger.info(f"Cleaning all expired messages from queues through {plugin.plugin_name}.")  
        await plugin.clean_all_queues()  
  
    async def create_container(self, data_container, plugin_name: Optional[str] = None):  
        """  
        Creates a new data container for the specified plugin.  
        """  
        plugin = self.get_plugin(plugin_name)  
        self.logger.info(f"Creating data container for {plugin.plugin_name}.")  
        await plugin.create_container(data_container)  
