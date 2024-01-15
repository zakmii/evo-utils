
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



class TokenCounterKani(Kani):
    """A Kani that keeps track of tokens used over the course of the conversation."""
    def __init__(self, 
                 *args, 
                 prompt_tokens_cost = None, 
                 completion_tokens_cost = None,                  
                 **kwargs):

        super().__init__(*args, **kwargs)

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



class FileKani(Kani):
    """A Kani that can access the contents of uploaded files."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.files = []


    @ai_function()
    def get_file_contents(self, file_name: Annotated[str, AIParam(desc="The name of the file to read.")]):
        """Return the contents of the given filename as a string. If the file is not found, or is not a PDF or text-based, return None."""

        for file in self.files:
            if file.name == file_name:
                if file.type.startswith("text"):
                    return file.read()
                elif file.type == "application/pdf":
                    with pdfplumber.open(file) as pdf:
                        return "\n\n".join([page.extract_text() for page in pdf.pages])
                elif file.type == "application/json":
                    return file.read()


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
                    self.render_in_ui(lambda: st.dataframe(sample))

                    message = f"The user has been shown the first {min(10, len(sample))} rows of the CSV. There are {len(df)} rows total, and {len(df.columns)} columns named: {', '.join(df.columns)}."

                    if hasattr(self, "dfs"):
                        self.dfs[table_name] = df
                        message = f"Created table {table_name} from the CSV. {message}"

                    return message

                else:
                    return f"Error: file is not a CSV."
                
        return f"Error: file name not found in current uploaded file set."



class DfKani(Kani):
    """A Kani that can run SQL queries on an in-memory database, stored as a dictionary of pandas dataframes."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.dfs = {}

    @ai_function()
    def list_tables(self):
        """List the tables in your in-memory database."""
        return list(self.dfs.keys())
    
    # @ai_function()
    # def create_table_from_pandas(self,
    #                              df: Annotated[pd.DataFrame, AIParam(desc="The dataframe to create the table from.")],
    #                              table_name: Annotated[str, AIParam(desc="The name of the table to create.")]):
    #     """Create a table in your in-memory database from a pandas dataframe."""
    #     self.dfs[table_name] = df
    #     return f"Created table {table_name}."
    

    def create_table_from_json(self,
                               json_str: str,
                               table_name: str):
        """Create a table in your in-memory database from a JSON string. Uses pandas.read_json."""
        df = pd.read_json(json_str)
        return self.create_table_from_pandas(df, table_name)

    @ai_function()
    def run_query(self,
                 query: Annotated[str, AIParam(desc="The query to run.")]):
        """Query your in-memory database using SQL."""
        try:
            result = sqldf(query, self.dfs)
            #self.render_in_ui(lambda: st.dataframe(result))
            return result.to_string(index=False)
        except Exception as e:
            return f"Error: {e}"
