import operator
from google.genai import types

import operator
from py_expression_eval import Parser


# The new, more powerful function
def calculate(expression: str):
    """
    Safely evaluates a mathematical string expression.

    This tool is highly efficient for multi-step calculations. It supports
    basic arithmetic (+, -, *, /), parentheses for order of operations,
    and common math functions.

    Args:
        expression (str): The mathematical expression to evaluate.
                          Example: "(5 + 3) * 2 - 10 / 2"

    Returns:
        dict: A dictionary containing the result or an error message.
              - On success: {"success": True, "result": <value>}
              - On failure: {"success": False, "error": "error_message"}
    """
    try:
        # Create a parser object
        parser = Parser()
        # Evaluate the expression
        result = parser.parse(expression).evaluate({}) # empty dict for variables
        return {"success": True, "result": result}
    except ZeroDivisionError:
        return {"success": False, "error": "Division by zero occurred in the expression."}
    except Exception as e:
        # Catches parsing errors, unknown functions, etc.
        return {"success": False, "error": f"Invalid expression or calculation error: {str(e)}"}
    
    
schema_calculate = types.FunctionDeclaration(
    name="calculate",
    description="A powerful calculator that safely evaluates a complete mathematical string expression. Use this for multi-step calculations involving parentheses and standard order of operations (PEMDAS).",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "expression": types.Schema(
                type=types.Type.STRING,
                description="The mathematical expression to evaluate. For example: '(10 + 5) * 2' or '100 / 4 - 10'."
            )
        },
        required=["expression"],
    ),
)