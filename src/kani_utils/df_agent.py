from kani import Kani
from kani import AIParam, ai_function
from typing import Annotated, Optional, List
import pandas as pd
from pandasql import sqldf

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
