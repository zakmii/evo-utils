
from kani import Kani
from .kani_streamlit_server import UIOnlyMessage
from kani import Kani
from kani.engines.base import BaseCompletion, Completion
from kani import Kani
from kani import AIParam, ai_function
from typing import Annotated
import pandas as pd
import pdfplumber
import re
import streamlit as st
from kani import Kani
from kani import AIParam, ai_function
from typing import Annotated
import pandas as pd
from pandasql import sqldf


class EnhancedKani(Kani):
    def __init__(self,
                 *args,
                 name = "Agent Name",
                 greeting = "Greetings! This greeting is shown to the user before the interaction, to provide instructions or other information. The LLM does not see it.",
                 description = "A brief description of the agent, shown in the user interface.",
                 avatar = "🤖",
                 user_avatar = "👤",
                 prompt_tokens_cost = None,
                 completion_tokens_cost = None,
                 **kwargs):
        
        super().__init__(*args, **kwargs)

        self.name = name
        self.greeting = greeting
        self.description = description
        self.avatar = avatar
        self.user_avatar = user_avatar

        self.prompt_tokens_cost = prompt_tokens_cost
        self.completion_tokens_cost = completion_tokens_cost
        self.tokens_used_prompt = 0
        self.tokens_used_completion = 0

            
    def get_convo_cost(self):
        """Get the total cost of the conversation so far."""
        if self.prompt_tokens_cost is None or self.completion_tokens_cost is None:
            return None
        
        return (self.tokens_used_prompt / 1000.0) * self.prompt_tokens_cost + (self.tokens_used_completion / 1000.0) * self.completion_tokens_cost


    async def get_model_completion(self, include_functions: bool = True, **kwargs) -> BaseCompletion:
        """Overrides the default get_model_completion to track tokens used.
        See https://github.com/zhudotexe/kanpai/blob/cc603705d353e4e9b9aa3cf9fbb12e3a46652c55/kanpai/base_kani.py#L48
        """
        completion = await super().get_model_completion(include_functions, **kwargs)
        self.tokens_used_prompt += completion.prompt_tokens
        self.tokens_used_completion += completion.completion_tokens

        message = completion.message
        # HACK: sometimes openai's function calls are borked; we fix them here
        if (function_call := message.function_call) and function_call.name.startswith("functions."):
            fixed_name = function_call.name.removeprefix("functions.")
            message = message.copy_with(function_call=function_call.copy_with(name=fixed_name))
            return Completion(
                message, prompt_tokens=completion.prompt_tokens, completion_tokens=completion.completion_tokens
            )
        return completion
    
    async def estimate_next_tokens_cost(self):
        """Estimate the cost of the next message (not including the response)."""
        # includes all previous messages, plus the current
        return sum(self.message_token_len(m) for m in await self.get_prompt()) + self.engine.token_reserve + self.engine.function_token_reserve(list(self.functions.values()))


class StreamlitKani(EnhancedKani):
    def __init__(self,
                 *args,
                 **kwargs):

        super().__init__(*args, **kwargs)

        self.display_messages = []

    def render_in_streamlit_chat(self, func):
        """Renders UI components in the chat. Takes a function that takes no parameters that should render the elements."""
        self.display_messages.append(UIOnlyMessage(func))

    def render_streamlit_ui(self):
        st.markdown(f"""
                     ## {self.name}
                     {self.description}
                     """)

        cost = self.get_convo_cost()
        if cost is not None:
            st.markdown(f"""
                        ### Conversation Cost: {cost:.2f}
                        Prompt tokens: {self.tokens_used_prompt}, Completion tokens: {self.tokens_used_completion}
                        """)

# let's pull the memory functionality out into a separate class
class StreamlitMemoryKani(StreamlitKani):
    """A Kani that can store and retrieve values from memory."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.memory = {}

    def render_streamlit_ui(self):
        StreamlitKani.render_streamlit_ui(self)
        st.markdown("### Memory")
        st.caption("This model can store and retrieve values in memory. Memory is cleared when the model is reloaded.")
        memory_keys = self.list_memory_keys()
        if len(memory_keys) == 0:
            memory_keys = ["*None*"]
        sep = "\n- "
        st.markdown("- " + sep.join(memory_keys))

    @ai_function()
    def save_to_memory(self,
                       key: Annotated[str, AIParam(desc="The key to save the value under.")],
                       value: Annotated[str, AIParam(desc="The value to save.")]):
        """Save a value to memory."""
        self.memory[key] = value

    @ai_function()
    def get_from_memory(self,
                        key: Annotated[str, AIParam(desc="The key to retrieve the value for.")]):
        """Retrieve a value from memory."""
        return self.memory.get(key, None)

    @ai_function()
    def list_memory_keys(self):
        """List the keys currently stored in memory."""
        return list(self.memory.keys())


class StreamlitFileKani(StreamlitMemoryKani):
    """A Kani that can access the contents of uploaded files."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.files = []

    def render_streamlit_ui(self):
        StreamlitKani.render_streamlit_ui(self)
        st.markdown("### Files")
        st.caption("This model can read the files listed below. When referenced in conversation, text-like file contents (txt, pdf, json) will be supplied in full to the model. CSV files will be read as data frames and summarized.")
        uploaded_files = st.file_uploader("Upload a document", 
                                          type= None, 
                                          accept_multiple_files = True,
                                          )
        
        # replace the agents files with the returned list (which will contain
        # the current file set shown in the UI)
        self.files = uploaded_files

    @ai_function()
    def get_file_contents(self, file_name: Annotated[str, AIParam(desc="The name of the file to read.")]):
        """Return the contents of the given filename as a string. If the file is not found, or is not a PDF or text-based, return None."""

        contents = None
        for file in self.files:
            if file.name == file_name:
                if file.type.startswith("text"):
                    contents = file.read()
                elif file.type == "application/pdf":
                    with pdfplumber.open(file) as pdf:
                        contents = "\n\n".join([page.extract_text() for page in pdf.pages])
                elif file.type == "application/json":
                    contents = file.read()

        if contents is None:
            return f"Error: file name not found in current uploaded file set."
        
        # save the contents in memory for later use
        self.memory[file_name] = contents
        message = f"Here are the contents of the file, which have also been saved in memory key '{file_name}' for further use:\n\n"
        return message + contents


    @ai_function()
    def list_current_files(self):
        """List the files currently uploaded by the user."""
        return self.files
    

    @ai_function()
    # todo: convert to something like "load_csv_files" that takes a list of files,
    # don't display to user (make seperate visualization function)
    def read_csv_file(self, file_name: Annotated[str, AIParam(desc="The name of the file to read.")]):
        """Read a CSV file uploaded by the user."""
        for file in self.files:
            if file.name == file_name:

                # assume the file is a csv, use pandas to read it
                if file.type == "text/csv":
                    df = pd.read_csv(file)

                    # create an SQL-compatible table name based on the filename, keeping only alphanumeric characters, dots to underscores, and uppercasing
                    table_name = re.sub(r"[^a-zA-Z0-9_]", "_", file_name).upper()

                    sample = df.head(10)

                    message = f"Here is a sample of the data: {sample.to_markdown()}.\n\nThere are {len(df)} rows total, and {len(df.columns)} columns named: {', '.join(df.columns)}."
                    self.memory[table_name] = df
                    message += f"\n\nThe data has been saved in memory key '{table_name}' for further use."

                    return message

                else:
                    return f"Error: file is not a CSV."
                
        return f"Error: file name not found in current uploaded file set."


class StreamlitFileTableKani(StreamlitFileKani):
    """A Kani that can run SQL queries on pandas dataframes stored in memory."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    def render_streamlit_ui(self):
        StreamlitFileKani.render_streamlit_ui(self)
        table_names = self.list_tables()
        if len(table_names) == 0:
            table_names = ["*None*"]
        sep = "\n- "
        st.markdown("### Current Tables")
        st.caption("This model can querying the following in-memory tables. Tables may be created by uploading a CSV file or other operations.")
        st.markdown("- " + sep.join(table_names))


    @ai_function()
    def list_tables(self):
        """List pandas dataframes stored in memory, which can be queried and joined with SQL."""
        pandas_tables = [k for k, v in self.memory.items() if isinstance(v, pd.DataFrame)]
        return pandas_tables
   
    @ai_function()
    def run_query(self,
                 query: Annotated[str, AIParam(desc="The query to run.")],
                 save_result_to_memory_key: Annotated[str, AIParam(desc="Optional: the key to save the result to. If not provided, the result will not be saved.")] = None
                 ):
        """Query the pandas dataframes store in memory as an SQL database. Use memory key names as table names. Results are returned as text."""
        try:
            memory_dfs = {k: v for k, v in self.memory.items() if isinstance(v, pd.DataFrame)}
            result = sqldf(query, memory_dfs)

            if save_result_to_memory_key is not None:
                self.memory[save_result_to_memory_key] = result

            return result.to_string(index=False)
        except Exception as e:
            return f"Error: {e}"
