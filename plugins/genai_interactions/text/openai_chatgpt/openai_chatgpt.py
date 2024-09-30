import json
import traceback
from datetime import datetime
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel

from core.action_interactions.action_input import ActionInput
from core.genai_interactions.genai_cost_base import GenAICostBase
from core.genai_interactions.genai_interactions_text_plugin_base import (
    GenAIInteractionsTextPluginBase,
)
from core.global_manager import GlobalManager
from core.user_interactions.incoming_notification_data_base import (
    IncomingNotificationDataBase,
)
from core.user_interactions.message_type import MessageType
from plugins.genai_interactions.text.chat_input_handler import ChatInputHandler
from utils.config_manager.config_manager import ConfigManager
from utils.plugin_manager.plugin_manager import PluginManager


class OpenAIChatGptConfig(BaseModel):
    PLUGIN_NAME: str
    OPENAI_CHATGPT_API_KEY: str
    OPENAI_CHATGPT_MODEL_NAME: str
    OPENAI_CHATGPT_VISION_MODEL_NAME: str
    OPENAI_CHATGPT_INPUT_TOKEN_PRICE: float
    OPENAI_CHATGPT_OUTPUT_TOKEN_PRICE: float
    OPENAI_CHATGPT_IS_ASSISTANT: bool = False
    OPENAI_CHATGPT_ASSISTANT_ID: str = None

class OpenaiChatgptPlugin(GenAIInteractionsTextPluginBase):
    def __init__(self, global_manager: GlobalManager):
        super().__init__(global_manager)
        self.global_manager = global_manager
        self.logger = self.global_manager.logger
        self.plugin_manager: PluginManager = global_manager.plugin_manager
        self.config_manager: ConfigManager = global_manager.config_manager
        openai_chatgpt_config_dict = global_manager.config_manager.config_model.PLUGINS.GENAI_INTERACTIONS.TEXT["OPENAI_CHATGPT"]
        self.openai_chatgpt_config = OpenAIChatGptConfig(**openai_chatgpt_config_dict)
        self.plugin_name = None
        self._genai_cost_base = None
        self.session_manager = self.global_manager.session_manager

        # Dispatchers
        self.user_interaction_dispatcher = None
        self.genai_interactions_text_dispatcher = None
        self.backend_internal_data_processing_dispatcher = None

    @property
    def plugin_name(self):
        return "openai_chatgpt"

    @plugin_name.setter
    def plugin_name(self, value):
        self._plugin_name = value

    @property
    def genai_cost_base(self) -> GenAICostBase:
        if self._genai_cost_base is None:
            raise ValueError("GenAI cost base is not set")
        return self._genai_cost_base

    @genai_cost_base.setter
    def genai_cost_base(self, value: GenAICostBase):
        self._genai_cost_base = value

    def initialize(self):
        # Client settings
        self.openai_api_key = self.openai_chatgpt_config.OPENAI_CHATGPT_API_KEY
        self.model_name = self.openai_chatgpt_config.OPENAI_CHATGPT_MODEL_NAME
        self.input_token_price = self.openai_chatgpt_config.OPENAI_CHATGPT_INPUT_TOKEN_PRICE
        self.output_token_price = self.openai_chatgpt_config.OPENAI_CHATGPT_OUTPUT_TOKEN_PRICE
        self.is_assistant = self.openai_chatgpt_config.OPENAI_CHATGPT_IS_ASSISTANT
        self.assistant_id = self.openai_chatgpt_config.OPENAI_CHATGPT_ASSISTANT_ID

        # Set OpenAI API key
        AsyncOpenAI.api_key = self.openai_api_key
        self.input_handler = ChatInputHandler(self.global_manager, self)
        self.input_handler.initialize()

        # Dispatchers
        self.user_interaction_dispatcher = self.global_manager.user_interactions_dispatcher
        self.genai_interactions_text_dispatcher = self.global_manager.genai_interactions_text_dispatcher
        self.backend_internal_data_processing_dispatcher = self.global_manager.backend_internal_data_processing_dispatcher

    def validate_request(self, event: IncomingNotificationDataBase):
        """Determines whether the plugin can handle the given request."""
        return True

    async def handle_request(self, event: IncomingNotificationDataBase):
        """Handles the request."""
        try:
            validate_request = self.validate_request(event)

            if not validate_request:
                self.logger.error(f"Invalid request: {event}")
                await self.dispatcher.send_message(
                    event.user_id,
                    "Something went wrong. Please try again or contact the bot owner.",
                    message_type=MessageType.COMMENT
                )
                return None

            response = await self.input_handler.handle_event_data(event)
            return response

        except Exception as e:
            error_trace = traceback.format_exc()
            self.logger.error(f"An error occurred: {e}\n{error_trace}")

            await self.user_interaction_dispatcher.send_message(
                event.user_id,
                "Something went wrong. Please try again or contact the bot owner.",
                message_type=MessageType.COMMENT
            )

            await self.user_interaction_dispatcher.send_message(
                "genai interaction issue",
                f"An error occurred in the openai_chatgpt module: {e}\n{error_trace}",
                message_type=MessageType.TEXT, is_internal=True
            )
            return None

    async def handle_action(self, action_input: ActionInput, event: IncomingNotificationDataBase):
        try:
            # Extract parameters from the action input
            parameters = action_input.parameters
            input_param: str = parameters.get('input', '')
            main_prompt = parameters.get('main_prompt', '')
            context = parameters.get('context', '')
            conversation_data = parameters.get('conversation_data', '')

            # Always retrieve the session for this thread (since we're in a thread context)
            session = await self.session_manager.get_or_create_session(
                event.origin_plugin_name,
                event.channel_id,
                event.thread_id,
                "",  # core_prompt not needed since the session already exists
                "",  # main_prompt not needed since the session already exists
                datetime.now().isoformat(),
                enriched=True  # Ensure we're working with an enriched session
            )

            # Capture the action invocation time
            action_start_time = datetime.now()

            # Add action input details to the session
            action_event_data = {
                'action_name': action_input.action_name,
                'parameters': parameters,
                'input': input_param,
                'context': context,
                'conversation_data': conversation_data,
                'timestamp': action_start_time.isoformat()  # Add the timestamp when the action started
            }
            await self.session_manager.add_event_to_session(session, 'action_invocation', action_event_data)

            # Build the messages for the model call
            messages = [{"role": "system", "content": main_prompt or "No specific instruction provided."}]

            if context:
                messages.append({"role": "user", "content": f"Context: {context}"})

            if conversation_data:
                messages.append({"role": "user", "content": f"Conversation: {conversation_data}"})

            messages.append({"role": "user", "content": input_param})

            # Call the model to generate the completion
            self.logger.info(f"Calling OpenAI API for model {self.plugin_name}..")

            # Record the time before completion generation
            generation_start_time = datetime.now()

            # Generate the completion
            completion, genai_cost_base = await self.generate_completion(messages, event)

            # Calculate the generation time
            generation_end_time = datetime.now()
            generation_duration = (generation_end_time - generation_start_time).total_seconds()

            # Update the costs
            costs = self.backend_internal_data_processing_dispatcher.costs
            original_msg_ts = event.thread_id if event.thread_id else event.timestamp
            blob_name = f"{event.channel_id}-{original_msg_ts}.txt"
            await self.input_handler.calculate_and_update_costs(genai_cost_base, costs, blob_name, event)

            # Update the session with the model's completion and costs
            assistant_response_event = {
                'role': 'assistant',
                'content': completion,
                'generation_time': generation_duration,  # Add the generation time
                'cost': {
                    'total_tokens': genai_cost_base.total_tk,
                    'prompt_tokens': genai_cost_base.prompt_tk,
                    'completion_tokens': genai_cost_base.completion_tk,
                    'input_cost': genai_cost_base.input_token_price,
                    'output_cost': genai_cost_base.output_token_price
                }
            }
            await self.session_manager.add_event_to_session(session, 'assistant_completion', assistant_response_event)

            # Save the enriched session after the action and model invocation
            await self.session_manager.save_session(session)

            # Update session with the completion (keeping the original OpenAI implementation)
            sessions = self.backend_internal_data_processing_dispatcher.sessions
            messages = json.loads(await self.backend_internal_data_processing_dispatcher.read_data_content(sessions, blob_name) or "[]")
            messages.append({"role": "assistant", "content": completion})
            await self.backend_internal_data_processing_dispatcher.write_data_content(sessions, blob_name, json.dumps(messages))

            return completion

        except Exception as e:
            self.logger.error(f"An error occurred: {e}\n{traceback.format_exc()}")
            raise

    async def generate_completion(self, messages, event_data: IncomingNotificationDataBase):
        try:
            self.logger.info("Generate completion triggered...")

            # If not using an assistant, proceed with the standard completion
            model_name = self.openai_chatgpt_config.OPENAI_CHATGPT_MODEL_NAME
            client = AsyncOpenAI(api_key=self.openai_api_key)
            # Standard text-based completion
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.1,
                max_tokens=4096
            )

            result = response.choices[0].message.content

            # Track usage and costs
            self.genai_cost_base = GenAICostBase()
            usage = response.usage
            self.genai_cost_base.total_tk = usage.total_tokens
            self.genai_cost_base.prompt_tk = usage.prompt_tokens
            self.genai_cost_base.completion_tk = usage.completion_tokens
            self.genai_cost_base.input_token_price = self.input_token_price
            self.genai_cost_base.output_token_price = self.output_token_price

            return result, self.genai_cost_base

        except Exception as e:
            self.logger.error(f"An error occurred during completion: {str(e)}\n{traceback.format_exc()}")
            await self.user_interaction_dispatcher.send_message(event=event_data, message="An unexpected error occurred", message_type=MessageType.ERROR, is_internal=True)
            raise

    async def trigger_genai(self, event: IncomingNotificationDataBase):
        AUTOMATED_RESPONSE_TRIGGER = "Automated response"
        event_copy = event

        if event.thread_id == '':
            response_id = event_copy.timestamp
        else:
            response_id = event_copy.thread_id

        event_copy.user_id = "AUTOMATED_RESPONSE"
        event_copy.user_name = AUTOMATED_RESPONSE_TRIGGER
        event_copy.user_email = AUTOMATED_RESPONSE_TRIGGER
        event_copy.event_label = "thread_message"
        user_message = self.user_interaction_dispatcher.format_trigger_genai_message(event=event, message=event_copy.text)
        event_copy.text = user_message
        event_copy.is_mention = True
        event_copy.thread_id = response_id

        self.logger.debug(f"Triggered automated response on behalf of the user: {event_copy.text}")
        await self.user_interaction_dispatcher.send_message(event=event_copy, message="Processing incoming data, please wait...", message_type=MessageType.COMMENT)

        word_count = len(event_copy.text.split())

        if word_count > 300:
            await self.user_interaction_dispatcher.upload_file(event=event_copy, file_content=event_copy.text, filename="Bot reply.txt", title="Automated User Input", is_internal=True)
        else:
            await self.user_interaction_dispatcher.send_message(event=event_copy, message=f"AutomatedUserInput: {event_copy.text}", message_type=MessageType.TEXT, is_internal=True)

        await self.global_manager.user_interactions_behavior_dispatcher.process_incoming_notification_data(event_copy)

    async def trigger_feedback(self, event: IncomingNotificationDataBase) -> Any:
        """
        This method is used to trigger feedback based on a user's interaction.
        You can customize this based on how you want to handle feedback.

        :param event: The event data containing user interaction details
        :return: A response or action based on the feedback
        """
        try:
            # Extract relevant data from the event
            user_id = event.user_id
            user_feedback = event.text  # Assuming the feedback is in the 'text' field

            # Log the feedback received
            self.logger.info(f"Received feedback from user {user_id}: {user_feedback}")

            # Here you can send a message acknowledging feedback or process it further
            response_message = "Thank you for your feedback!"
            await self.user_interaction_dispatcher.send_message(
                event=event,
                message=response_message,
                message_type=MessageType.TEXT
            )

            # Process the feedback or log it for future analysis
            # You can also integrate it with analytics or other systems
            self.logger.debug("Processing feedback for further action")

            return {"status": "feedback_received", "feedback": user_feedback}

        except Exception as e:
            self.logger.error(f"Error in processing feedback: {e}")
            raise

