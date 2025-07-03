import pandas as pd
from fuzzywuzzy import process, fuzz
from google.genai import types

df = pd.read_csv("food.csv")

def fuzzy_search_rows(query,df=df, column_name="Food Name", threshold=85):
    
    matches = process.extract(query, df[column_name], scorer=fuzz.token_set_ratio, limit=len(df))

    matched_indices = [idx for (name, score, idx) in matches if score >= threshold]
    
    matched_df =  df.iloc[matched_indices][['Food Name','Protein (g)','Fat (g)','Carbohydrate (g)','Energy (kcal) (kcal)']]

    return matched_df.reset_index(drop=True).to_json(orient='records')



schema_fuzzy_search_rows = types.FunctionDeclaration(
    name="fuzzy_search_rows",
    description="Performs a fuzzy search on food items and returns matching rows with nutritional information, the value of the nutrtional information is based on the food item name, for example: 'grilled chicken' it represents value per 100g",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "query": types.Schema(
                type=types.Type.STRING,
                description="The search term to match against food names (e.g., 'grilled chicken')",
            )
        },
        required=["query"],
    ),
)

