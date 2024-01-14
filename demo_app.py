# Example usage of StreamlitKani

########################
##### 0 - load libs
########################


# kani_streamlit imports
import kani_utils.kani_streamlit_server as ks
from kani_utils.streamlit_agent import StreamlitKani
from kani_utils.token_counter_agent import TokenCounterKani
from kani_utils.df_agent import DfKani
from kani_utils.file_agent import FileKani

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
        # Do so by passing a function to the render_in_ui method; it should take no paramters
        # (but you can refer to data in the outer scope, for example to use st.write() to display a pandas dataframe)
        weather_df = pd.DataFrame({"date": ["2021-01-01", "2021-01-02", "2021-01-03"], "temp": [72, 73, 74]})
        self.render_in_ui(lambda: st.write(weather_df))

        mean_temp = weather_df.temp.mean()
        return f"Weather in {location}: Sunny, {mean_temp} degrees fahrenheit."


    @ai_function()
    def entertain_user(self):
        """Entertain the user by showing a video."""

        self.render_in_ui(lambda: st.video("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))

        return "The video has just been shown to the user, but they have not begun playing it yet. Tell the user you hope it doesn't 'let them down'."


class TokenCounterFileKani(StreamlitKani, TokenCounterKani, FileKani):
    """A Kani that keeps track of tokens used over the course of the conversation."""
    def __init__(self, *args, **kwargs):
        # run the constructors of both superclasses
        super().__init__(*args, **kwargs)

        self.description = f"Agent that can read files and track the cost of the conversation."
        self.greeting = "Hello, I'm an assistant with with the ability to read the contents text and PDF files, and track the cost of our conversation."

        self.prompt_tokens_cost = 0.01
        self.completion_tokens_cost = 0.03

    @ai_function()
    def identify_gene_names(self, gene_names: Annotated[List[str], AIParam(desc="A list of gene names to identify.")]):
        """Identifies gene names of interest from the current conversation, focusing on genes of interest to the user."""

        return f"Identified {len(gene_names)} gene names of interest: {', '.join(gene_names)}."


class FileDatabaseKani(StreamlitKani, DfKani, FileKani):
    """A Kani that keeps track of tokens used over the course of the conversation."""
    def __init__(self, *args, **kwargs):
        # run the constructors of both superclasses
        super().__init__(*args, **kwargs)

        self.description = f"Agent that can read files, including reading CSV files and query them with SQL."
        self.greeting = "Hello, I'm an assistant with the ability to read CSV files and query them with SQL."



# define an engine to use (see Kani documentation for more info)
engine = OpenAIEngine(os.environ["OPENAI_API_KEY"], model="gpt-4-1106-preview")

# We also have to define a function that returns a dictionary of agents to serve
# Agents are keyed by their name, which is what the user will see in the UI
def get_agents():
    return {
            "Demo Agent": MediaKani(engine),
            "Token Counter Demo Agent": TokenCounterFileKani(engine),
            "File Database Demo Agent": FileDatabaseKani(engine),
           }


# tell the app to use that function to create agents when needed
ks.set_app_agents(get_agents)


########################
##### 3 - Serve App
########################

ks.serve_app()
