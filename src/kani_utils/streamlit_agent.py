
from kani import Kani
from .kani_streamlit_server import UIOnlyMessage


class StreamlitKani(Kani):
    def __init__(self,
                 *args,
                 greeting = "Greetings! This greeting is shown to the user before the interaction, to provide instructions or other information. The LLM does not see it.",
                 description = "A brief description of the agent, shown in the sidebar.",
                 avatar = "🤖",
                 user_avatar = "👤",
                 **kwargs):

        super().__init__(*args, **kwargs)

        self.greeting = greeting
        self.description = description
        self.avatar = avatar
        self.user_avatar = user_avatar

        self.display_messages = []
        self.conversation_started = False

    def render_in_ui(self, data):
        """Render a dataframe in the chat window."""
        self.display_messages.append(UIOnlyMessage(data))
