# --- 1. Unused import (F401) ---

# --- 2. Multiple statements on one line (E702) ---
a = 1
b = 2

# --- 3. Shadowing builtins (N or PLW shadow rules) ---
list = [1, 2, 3]
dict = {"a": 1, "b": 2}

# --- 4. Unused variable (F841) ---
for i in range(5):
    pass

# --- 5. Unnecessary list index lookup (PLR1736) ---
letters = ["a", "b", "c"]
for i, letter in enumerate(letters):
    print(letter)  # unnecessary list index lookup

# --- 6. Non-idiomatic membership check (UP015 or PLR1714 style) ---
if "a" == letter:
    print("found a")

# --- 7. Unnecessary comparison to True (PLR0123) ---
flag = True
if flag == True:
    print("flag is true")

# --- 8. Unnecessary lambda (PLR5501) ---
nums = [1, 2, 3]
mapped = map(lambda x: x + 1, nums)

# --- 9. Bad import sorting (I001) ---

# --- 10. Long line (E501) ---
very_long_string = "x" * 200  # This line should exceed your configured line length


# --- 11. Mutable default argument (B006) ---
def append_item(value, container=None):
    """Append a value to a container.

    If no container is provided, a new list is created.

    Args:
        value: The value to append.
        container: The list to which the value will be appended. If None, a new list is created.

    Returns:
        The container with the appended value.

    """
    if container is None:
        container = []
    container.append(value)
    return container


# --- 12. Simplifiable if statement (PLR1701 or similar) ---
x = [1, 2, 3]
if len(x) != 0:
    print("not empty")


def risky():
    """Raise a ValueError to demonstrate exception handling."""
    raise ValueError("Something went wrong")


# --- 13. Exception that should specify type (B001) ---
try:
    risky()
except ValueError as e:
    print(f"error: {e}")
