# Kani-Utils

Utilities for deploying one or more tool-using LLM agents
using the [Kani](https://kani.readthedocs.io/en/latest/index.html) and [Streamlit](https://streamlit.io/) libraries.

Features

- Define multiple agents (for different engines and/or functionality)
- Agents can render Streamlit elements to the chat stream (e.g. dataframes, images)
- Agent-defined UI elements in the sidebar (e.g., file uploads)
- Streaming responses
- Token and cost accounting

Screenshot:

![screenshot](screenshot.png)


See [demo_app.py](demo_app.py) and [demo_agents.py](demo_agents.py).

## Installation and Use

### 0. Install

With `pip`, `poetry`, etc.

```
pip install git+https://github.com/oneilsh/kani-utils.git
```

### 1. Define Agents ([demo_agents.py](demo_agents.py))

The `StreamlitKani` class extends [Kani](https://kani.readthedocs.io/en/latest/index.html), with additional
functionality to intregate with the Streamlit server and UI elements. We'll need this and a few other imports
from the `kani` and `streamlit` libraries in a `demo_agents.py` or similar:

```python
# from demo_agents.py

from kani_utils.base_kanis import StreamlitKani
from kani import AIParam, ai_function
import streamlit as st
```

Let's define a `WeatherKani`, starting with the constructor, which should call the parent constructor
and define some expected agent properties. This agent will use `pandas` later.

```python
# demo_agents.py continued

import pandas as pd

class WeatherKani(StreamlitKani):
    # Be sure to override the __init__ method to pass any parameters to the superclass
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Define avatars for the agent and user
        # Can be URLs or emojis
        self.avatar = "🎬"
        self.user_avatar = "👤"

        # The name and greeting are shown at the start of the chat
        # The greeting is not known to the LLM, it serves as a prompt for the user
        self.name = "Media Agent"
        self.greeting = "Hello, I'm a demo assistant. You can ask me the weather, or to play a random video on youtube."

        # The description is shown in the sidebar and provides more information about the agent
        self.description = "An agent that demonstrates the basic capabilities of Streamlit+Kani."

        # We'll keep track of user weather queries here
        self.search_history = []
```

And let's define an AI-callable function that retrieves some mock weather data for a given city.
The use of `@ai_function()`, `Annotated`, and `AIParam` are described in the [Kani](https://kani.readthedocs.io/en/latest/index.html)
documentation. The function returns data to the Agent - by default results of functions are only shown to
the LLM, but the user can optionally see the full context of called functions and results.

This function additionally renders the `pandas` dataframe directly in the chat UI using Streamlit's
type-inferring `st.write()` function. Streamlit provides a [variety](https://docs.streamlit.io/develop/api-reference)
of UI elements, and most are allowed, including a sequence or nesting of them. The rendering code *must* be provided as
a callable function.

Rendered UI elements are by default displayed after the resulting answer from the Agent in the chat, even though
`@ai_function()`s are typically called before the agent begins its answer (an artifact of the rendering and streaming
process).

```python
# demo_agents.py continued

    @ai_function()
    def get_weather(self, location: Annotated[str, AIParam(desc="The city and state, e.g. San Francisco, CA")]):
        """Get the current weather in a given location."""

        self.search_history.append(location)

        # generate mock data
        weather_df = pd.DataFrame({"date": ["2021-01-01", "2021-01-02", "2021-01-03"], "temp": [72, 73, 74]})
        mean_temp = weather_df.temp.mean()

        # call for the dataframe to 
        self.render_in_streamlit_chat(lambda: st.write(weather_df))

        return f"Weather: Sunny, {mean_temp}F. A table with recent data will be shown after your response in the chat."
```

Agents can also optionally define UI elements in the sidebar by implementing a `render_sidebar()` method. It is a good
idea to call `super().render_sidebar()` to render the sidebar for the parent class. If you want to be consisent with the
defaults, add a divider and use level 3 headings and caption-sized font. 

```python
# demo_agents.py continued

    def render_sidebar(self):
        # Call the superclass method to render the default sidebar elements
        super().render_sidebar()
        st.divider()

        st.markdown("### Search History")
        st.caption("Previous searches:")

        # format as markdown-formatted list
        st.markdown("- " + "\n- ".join(self.search_history))
```

The [demo_agents.py](demo_agents.py) defines several other examples: a `MemoryKani` with an integrated
key/value store, a `FileKani` that can read the contents of uploaded files, and a `TableKani` that
can query uploaded CSV files as a relational database.


### 2. App Configuration ([demo_app.py](demo_app.py))

First, we defined needed imports, and use `dotenv.load_dotenv()` to load the OpenAI API Key 
from a `.env` file (which you will need to create, containing a line like `OPENAI_API_KEY=sk-...`)


```python
# kani_streamlit imports
import kani_utils.kani_streamlit_server as ks

# for reading API keys from .env file
import os
import dotenv # pip install python-dotenv

# kani imports
from kani.engines.openai import OpenAIEngine

# load app-defined agents
from demo_agents import WeatherKani, MemoryKani, FileKani, TableKani

# read API keys .env file (e.g. set OPENAI_API_KEY=.... in .env and gitignore .env)
dotenv.load_dotenv() 
```

Next we initialize settings for the page. This MUST be called. Parameters here are
passed to `streamlit.set_page_config()`, see more at https://docs.streamlit.io/library/api-reference/utilities/st.set_page_config. 

```python
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
```

Then, we define one more more engines (Kani supports popular [cloud and local models](https://kani.readthedocs.io/en/latest/engines.html)), and define a function that returns a dictionary mapping agent names
to Kani agents. If `prompt_tokens_cost` and `completion_tokens_cost` (in dollars per 1k tokens), then
conversation cost tracking will be enabled. This function is passed to `ks.set_app_agents()` to be used
for initialization.

```python
# define an engine to use (see Kani documentation for more info)
engine = OpenAIEngine(os.environ["OPENAI_API_KEY"], model="gpt-4o")

# We also have to define a function that returns a dictionary of agents to serve
# Agents are keyed by their name, which is what the user will see in the UI
def get_agents():
    return {
            "Weather Agent": WeatherKani(engine, prompt_tokens_cost = 0.005, completion_tokens_cost = 0.015),
            "Weather Agent (No Costs Shown)": WeatherKani(engine),
            "Memory Agent": MemoryKani(engine, prompt_tokens_cost = 0.005, completion_tokens_cost = 0.015),
            "File Agent": FileKani(engine, prompt_tokens_cost = 0.005, completion_tokens_cost = 0.015),
            "Table Agent": TableKani(engine, prompt_tokens_cost = 0.005, completion_tokens_cost = 0.015),
           }


# tell the app to use that function to create agents when needed
ks.set_app_agents(get_agents)
```

Finally, `ks.serve_app()` will start the streamlit server.

```python
ks.serve_app()
```

### 3. Run Locally

Run the streamlit app:

```
streamlit run demo_app.py
```

### 4. Publish

Use Streamlit's [publishing functionality](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app) to deploy publicly, using secrets to store API keys.


# Changelog
 - 1.1: Added streaming output
 - 1.0: Moved memory functionality out of base class