# Example usage of StreamlitKani

########################
##### 0 - load libs
########################


# kani_streamlit imports
import kani_utils.kani_streamlit_server as ks
from kani_utils.base_kanis import StreamlitKani

# for reading API keys from .env file
import os
import dotenv # pip install python-dotenv

# kani imports
from kani.engines.openai import OpenAIEngine

# load app-defined agents
from demo_kanis import MediaKani, MemoryKani, FileKani, TableKani


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

# define an engine to use (see Kani documentation for more info)
engine = OpenAIEngine(os.environ["OPENAI_API_KEY"], model="gpt-4o")

# We also have to define a function that returns a dictionary of agents to serve
# Agents are keyed by their name, which is what the user will see in the UI
def get_agents():
    return {
            "Media Agent": MediaKani(engine, prompt_tokens_cost = 0.005, completion_tokens_cost = 0.015),
            "Media Agent (No Costs Shown)": MediaKani(engine),
            "Memory Agent": MemoryKani(engine, prompt_tokens_cost = 0.005, completion_tokens_cost = 0.015),
            "File Agent": FileKani(engine, prompt_tokens_cost = 0.005, completion_tokens_cost = 0.015),
            "Table Agent": TableKani(engine, prompt_tokens_cost = 0.005, completion_tokens_cost = 0.015),
           }


# tell the app to use that function to create agents when needed
ks.set_app_agents(get_agents)


########################
##### 3 - Serve App
########################

ks.serve_app()
