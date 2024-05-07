import csv

# Set up the regex matches within the pattern
ANY_WORD = "([a-zA-Z]+)"
UP_TO_3_DIGITS = "([\d]{1,3})"
PUNCTUATION = ".?!,\/\(\);:~=@%'\n"
UP_TO_3_PUNCTUATION = f"([{PUNCTUATION}]{1,3}+(?=(.?.?.?)*))"
ANY_NON_ASCII_CHAR = "(\\\\x[0-9a-fA-F]{2})"

PATTERN = f"{ANY_WORD}|{UP_TO_3_DIGITS}|{ANY_NON_ASCII_CHAR}|{UP_TO_3_PUNCTUATION}"

COST_DB = "data/cost_db.csv"


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


def estimate_cost(
    model: str,
    region: str,
    type_: str,
    string: str,
    use_cache:bool=False,
) -> float:
    if type_ not in ["input", "output"]:
        raise Exception("`type_` must be one of [\"input\", \"output\"]")

    key = ",".join([model, region, type_])

    if use_cache:  # Skip the DDB step for better cost / time performance
        with open(COST_DB) as f:
            reader = csv.DictReader(f)
            costs_dict = {",".join([k1,k3,k2]): v for (k1, k2, k3, v) in reader}

            cost_per_k_tokens = costs_dict.get(key)

            if not cost_per_k_tokens:
                raise Exception(
                    f"Could not find ({model}, {region}, {type_}) in cost DB."
                )

            cost_per_token = cost_per_k_tokens / 1000
    else:  # Lookup in DDB
        raise NotImplemented()

    n_tokens = len(get_estimated_tokens(string))

    return cost_per_token * n_tokens


estimate_cost("anthropic.claude-haiku", "us-east-1", "input", "the quick brownfox", True)
