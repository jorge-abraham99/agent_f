from google.genai import types

from query import fuzzy_search_rows, schema_fuzzy_search_rows
from calculator import calculate, schema_calculate
from get_file_content import get_file_content, schema_get_file_content
from get_files_info import get_files_info, schema_get_files_info
from write_file_content import write_file_content, schema_write_file

import os

available_functions = types.Tool(
    function_declarations=[
        schema_fuzzy_search_rows,
        schema_calculate,
        schema_get_file_content,
        schema_get_files_info,
        schema_write_file
    ]
)
WORKING_DIR = "./"


def call_function(function_call_part, verbose=False):
    if verbose:
        print(
            f" - Calling function: {function_call_part.name}({function_call_part.args})"
        )
    else:
        print(f" - Calling function: {function_call_part.name}")

    # Wrapper to handle parameter renaming for write_file_content
    def write_file_content_wrapper(**kwargs):
        if "filename" in kwargs:
            kwargs["file_path"] = kwargs.pop("filename")
        return write_file_content(**kwargs)

    function_map = {
        "fuzzy_search_rows": fuzzy_search_rows,
        "calculate": calculate,
        "get_file_content": get_file_content,
        "get_files_info": get_files_info,
        "write_file_content": write_file_content_wrapper,
    }
    functions_requiring_wd = [
        "get_file_content",
        "get_files_info",
        "write_file_content"
    ]
    function_name = function_call_part.name
    if function_name not in function_map:
        return types.Content(
            role="tool",
            parts=[
                types.Part.from_function_response(
                    name=function_name,
                    response={"error": f"Unknown function: {function_name}"},
                )
            ],
        )
    args = dict(function_call_part.args)
    if function_name in functions_requiring_wd:
        args["working_directory"] = WORKING_DIR
    function_result = function_map[function_name](**args)
    return types.Content(
        role="tool",
        parts=[
            types.Part.from_function_response(
                name=function_name,
                response={"result": function_result},
            )
        ],
    )


