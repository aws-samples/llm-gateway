# Set up the regex matches within the pattern
ANY_WORD = "([a-zA-Z]+)"
UP_TO_3_DIGITS = "([\d]{1,3})"
PUNCTUATION = ".?!,\/\(\);:~=@%'\n"
UP_TO_3_PUNCTUATION = f"([{PUNCTUATION}]{1,3}+(?=(.?.?.?)*))"
ANY_NON_ASCII_CHAR = "(\\\\x[0-9a-fA-F]{2})"

PATTERN = f"{ANY_WORD}|{UP_TO_3_DIGITS}|{ANY_NON_ASCII_CHAR}|{UP_TO_3_PUNCTUATION}"


def get_estimated_tokens(s: str) -> int:
    """
    Counts the number of tokens in the given string `s`, according to the
    following method:

    - All words (characters in [a-zA-Z] separated by whitespace or _, count as 1 token.
    - Numbers and punctuation are put into groups of 1-3 digits. Each group counts as 1 token.
    - All non ascii characters count as 1 token per byte.
    """

    s_encoded = s.encode("utf-8")

    result = re.findall(PATTERN, str(s_encoded)[2:])
    return [item for tup in result for item in tup if item]


def lambda_handler(event, context):
    # Get the input string from the event.
    s = event.get("input", "")

    # Return the JSON response.
    response = {
        "ascii_token_estimate": len(get_estimated_tokens(s)),
        "input_length": len(s)
    }
    return {
        "statusCode": 200,
        "body": json.dumps(response)
    }
