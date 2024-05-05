# Example usage of StreamlitKani

########################
##### 0 - load libs
########################


# kani_streamlit imports
import kani_utils.kani_streamlit_server as ks
from kani_utils.kanis import StreamlitKani, StreamlitFileKani, StreamlitFileTableKani

# for reading API keys from .env file
import os
import dotenv # pip install python-dotenv

# kani imports
from typing import Annotated, List, Dict, Optional
from kani import AIParam, ai_function
from kani.engines.openai import OpenAIEngine

# streamlit and pandas for extra functionality
import streamlit as st
import pandas as pd


########################
##### 1 - Configuration
########################

# read API keys .env file (e.g. set OPENAI_API_KEY=.... in .env and gitignore .env)
import dotenv
dotenv.load_dotenv() 

# initialize the application and set some page settings
# parameters here are passed to streamlit.set_page_config, 
# see more at https://docs.streamlit.io/library/api-reference/utilities/st.set_page_config
# this function MUST be run first
ks.initialize_app_config(
    show_function_calls = True,
    page_title = "StreamlitKani Demo",
    page_icon = "🦀", # can also be a URL
    initial_sidebar_state = "expanded", # or "expanded"
    menu_items = {
            "Get Help": "https://github.com/.../issues",
            "Report a Bug": "https://github.com/.../issues",
            "About": "StreamlitKani is a Streamlit-based UI for Kani agents.",
        }
)


########################
##### 2 - Define Agents
########################

# StreamlitKani agents are Kani agents and work the same
# We must subclass StreamlitKani instead of Kani to get the Streamlit UI
class MediaKani(StreamlitKani):
    # Be sure to override the __init__ method to pass any parameters to the superclass
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.greeting = "Hello, I'm a demo assistant. You can ask me the weather, or to play a random video on youtube."
        self.description = "An agent that demonstrates the basic capabilities of Streamlit+Kani."
        self.avatar = "🎬"
        self.user_avatar = "👤"

    @ai_function()
    def get_weather(
        self,
        location: Annotated[str, AIParam(desc="The city and state, e.g. San Francisco, CA")],
    ):
        """Get the current weather in a given location."""

        # You can use the Streamlit API to render things in the UI in the chat
        # Do so by passing a function to the render_in_streamlit_chat method; it should take no paramters
        # (but you can refer to data in the outer scope, for example to use st.write() to display a pandas dataframe)
        weather_df = pd.DataFrame({"date": ["2021-01-01", "2021-01-02", "2021-01-03"], "temp": [72, 73, 74]})
        self.render_in_streamlit_chat(lambda: st.write(weather_df))

        mean_temp = weather_df.temp.mean()
        return f"Weather in {location}: Sunny, {mean_temp} degrees fahrenheit."

    @ai_function()
    def entertain_user(self):
        """Entertain the user by showing a video."""

        self.render_in_streamlit_chat(lambda: st.video("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))

        return "The video has just been shown to the user, but they have not begun playing it yet. Tell the user you hope it doesn't 'let them down'."


class RedlineKani(StreamlitKani):
    """A Kani that can use the redline library to compute diffs between text inputs."""

    def __init__(self, *args, **kwargs):
        kwargs['system_prompt'] = 'You are a professional editor. You may be asked to review or improve text. Provide the user feedback, and make suggested edits, displaying them to the user.'

        super().__init__(*args, **kwargs)

        self.greeting = "Hello, I'm an editing assistant. You can ask me to review or improve text."
        self.description = "A professional editor."
        self.avatar = "🖍️"
        self.user_avatar = "👤"


    @ai_function()
    def display_diff(self,
                     text1: Annotated[str, AIParam(desc="Original text.")],
                     text2: Annotated[str, AIParam(desc="Edited text.")]):
        """Display changes between two versions of text."""
        from redlines import Redlines
        
        result = Redlines(text1, text2).output_markdown
        self.render_in_streamlit_chat(lambda: st.markdown(result, unsafe_allow_html=True))

        return "<!-- the result has been displayed in the chat -->"


# define an engine to use (see Kani documentation for more info)
engine = OpenAIEngine(os.environ["OPENAI_API_KEY"], model="gpt-4-turbo-2024-04-09")

# We also have to define a function that returns a dictionary of agents to serve
# Agents are keyed by their name, which is what the user will see in the UI
def get_agents():
    return {
            "Editor Agent": RedlineKani(engine, prompt_tokens_cost = 0.01, completion_tokens_cost = 0.03),
            "Basic Agent": StreamlitKani(engine, prompt_tokens_cost = 0.01, completion_tokens_cost = 0.03),
            "Basic Agent, No Costs": StreamlitKani(engine),
            "File Agent": StreamlitFileKani(engine, prompt_tokens_cost = 0.01, completion_tokens_cost = 0.03),
            "Table Agent": StreamlitFileTableKani(engine, prompt_tokens_cost = 0.01, completion_tokens_cost = 0.03),
            "Media Agent": MediaKani(engine, prompt_tokens_cost = 0.01, completion_tokens_cost = 0.03),
           }


# tell the app to use that function to create agents when needed
ks.set_app_agents(get_agents)


########################
##### 3 - Serve App
########################

ks.serve_app()
