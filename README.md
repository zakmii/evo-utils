# Kani-Utils

Utilities for deploying one or more tool-using LLM agents
using the [Kani](https://kani.readthedocs.io/en/latest/index.html) and [Streamlit](https://streamlit.io/) libraries.

Features

- Define multiple agents (for different engines and/or functionality)
- Agents can display streamlit objects from custom functions (e.g. dataframes, images)
- Agent-associated UI elements (e.g., file uploads)
- Streaming responses
- Optional full context for 
- Token and cost accounting

See [demo_app.py](demo_app.py) and [demo_agents.py](demo_agents.py).

## Installation and Use

#### 0. Install

With `pip`, `poetry`, etc.

```
pip install git+https://github.com/oneilsh/kani-utils.git
```

#### 1. Define Agents

The `StreamlitKani` class extends [Kani](https://kani.readthedocs.io/en/latest/index.html), with additional
functionality to intregate with the Streamlit server and UI elements. We'll need this and a few other imports
from the `kani` and `streamlit` libraries in an `agents.py` or similar: 

```python
# agents.py

from kani_utils.base_kanis import StreamlitKani
from kani import AIParam, ai_function
import streamlit as st
```

Let's define a `WeatherKani`, starting with the constructor, which should call the parent constructor
and define some expected agent properties. This agent will use `pandas` later.

```python
# agents.py continued

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
# agents.py continued

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
# agents.py continued

    def render_sidebar(self):
        # Call the superclass method to render the default sidebar elements
        super().render_sidebar()
        st.divider()

        st.markdown("### Search History")
        st.caption("Previous searches:")

        # format as markdown-formatted list
        st.markdown("- " + "\n- ".join(self.search_history))
```



#### 2. App Configuration

Here's where we initialize settings for the page. This MUST be called. Parameters here are
passed to `streamlit.set_page_config()`, see more at https://docs.streamlit.io/library/api-reference/utilities/st.set_page_config. 

```python
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
```

Finally, we start the app:

```python
ks.serve_app()
```

#### 3. Run Locally

Run the streamlit app:

```
streamlit run demo_app.py
```

# Changelog
 - 1.1: Added streaming output
 - 1.0: Moved memory functionality out of base class