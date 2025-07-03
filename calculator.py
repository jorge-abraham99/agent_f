import operator
from google.genai import types

def calculate(operation: str, num1: float, num2: float):
    """
    Performs a specified arithmetic operation on two numbers.

    This function is designed to be a robust tool for an LLM. It accepts
    common names for operations (e.g., "add", "plus", "+") and returns a
    structured dictionary indicating success or failure.

    Args:
        operation (str): The arithmetic operation to perform.
            Valid operations include: "add", "plus", "+",
                                   "subtract", "minus", "-",
                                   "multiply", "times", "*",
                                   "divide", "div", "/"
        num1 (float): The first number.
        num2 (float): The second number.

    Returns:
        dict: A dictionary containing the result or an error message.
              - On success: {"success": True, "result": <value>}
              - On failure: {"success": False, "error": "error_message"}

    Examples:
        calculate("add", 10, 5)      # -> {"success": True, "result": 15}
        calculate("*", 3, 4)         # -> {"success": True, "result": 12}
        calculate("divide", 10, 0)   # -> {"success": False, "error": "Division by zero is not allowed."}
        calculate("power", 2, 3)     # -> {"success": False, "error": "Invalid operation: 'power'. ..."}
    """
    # Map friendly names and symbols to standard Python operator functions
    # This makes the function more flexible to user/LLM input.
    op_map = {
        # Addition
        "add": operator.add,
        "plus": operator.add,
        "+": operator.add,
        # Subtraction
        "subtract": operator.sub,
        "minus": operator.sub,
        "-": operator.sub,
        # Multiplication
        "multiply": operator.mul,
        "times": operator.mul,
        "*": operator.mul,
        # Division
        "divide": operator.truediv,
        "div": operator.truediv,
        "/": operator.truediv,
    }

    # Normalize operation string to lowercase
    op_func = op_map.get(operation.lower())

    if not op_func:
        valid_ops = sorted(list(set(op_map.keys())))
        return {
            "success": False,
            "error": f"Invalid operation: '{operation}'. Valid operations are: {', '.join(valid_ops)}."
        }

    # Handle division by zero specifically before the general try-except
    if op_func == operator.truediv and num2 == 0:
        return {"success": False, "error": "Division by zero is not allowed."}

    try:
        result = op_func(num1, num2)
        return {"success": True, "result": result}
    except Exception as e:
        # This catch-all is for truly unexpected errors.
        return {"success": False, "error": f"An unexpected error occurred during calculation: {str(e)}"}
    
schema_calculate = types.FunctionDeclaration(
    name="calculate",
    description="A simple calculator for basic arithmetic. Use this to perform addition, subtraction, multiplication, or division on two numbers.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "operation": types.Schema(
                type=types.Type.STRING,
                description="The mathematical operation to perform. Supported values are: '+', 'add', 'plus', '-', 'subtract', 'minus', '*', 'multiply', 'times', '/', 'divide'."
            ),
            "num1": types.Schema(
                type=types.Type.NUMBER,
                description="The first number in the calculation (e.g., the dividend in division, the minuend in subtraction)."
            ),
            "num2": types.Schema(
                type=types.Type.NUMBER,
                description="The second number in the calculation (e.g., the divisor in division, the subtrahend in subtraction)."
            )
        },
        required=["operation", "num1", "num2"],
    ),
)