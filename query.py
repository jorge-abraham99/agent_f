import pandas as pd
from fuzzywuzzy import process, fuzz
from google.genai import types

df = pd.read_csv("recipes.csv")

def fuzzy_search_rows(query,df=df, column_name="Recipe Name", threshold=85):
    
    matches = process.extract(query, df[column_name], scorer=fuzz.token_set_ratio, limit=len(df))

    matched_indices = [idx for (name, score, idx) in matches if score >= threshold]
    
    matched_df =  df.iloc[matched_indices][['Recipe Name','protein','fat','carbohydrates','calories','sodium']]

    return matched_df.reset_index(drop=True).to_json(orient='records')



schema_fuzzy_search_rows = types.FunctionDeclaration(
    name="fuzzy_search_rows",
    description="Performs a fuzzy search on recipe names and returns matching rows with nutritional information per serving, including calories, protein, fat, carbohydrates, and sodium",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "query": types.Schema(
                type=types.Type.STRING,
                description="The search term to match against recipe names (e.g., 'chicken curry', 'salmon bowl')",
            )
        },
        required=["query"],
    ),
)

