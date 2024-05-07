from .lambdas.count_tokens.count_tokens import get_estimated_tokens
import csv

COST_DB = "./data/cost_db.csv"


def estimate_cost(
    model: str,
    region: str,
    type_: str,
    string: str,
    use_cache: False
) -> float:
    if type_ not in ["input", "output"]:
        raise Exception("`type_` must be one of [\"input\", \"output\"]")

    key = ",".join([model, region, type_])

    if use_cache:  # Skip the DDB step for better cost / time performance
        with open(COST_DB) as f:
            costs = csv.DictReader(f)
            cost_per_k_tokens = costs.get(key)

            if not cost_per_k_tokens:
                raise Exception(
                    f"Could not find ({model}, {region}, {type_}) in cost DB."
                )

            cost_per_token = cost_per_k_tokens / 1000
    else:  # Lookup in DDB
        raise NotImplemented()

    n_tokens = len(get_estimated_tokens(string))

    return cost_per_token * n_tokens


estimate_cost("the quick brown fox")
