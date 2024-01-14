from kani import Kani
from kani import AIParam, ai_function
from typing import Annotated
import pandas as pd
import pdfplumber
import re
import streamlit as st

class FileKani(Kani):
    """A Kani that can run SQL queries on an in-memory database, stored as a dictionary of pandas dataframes."""
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

