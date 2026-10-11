"""Print the API's OpenAPI schema; web/ generates its typed client from it.

    python -m tools.dump_openapi > web/openapi.json
"""

import json

from api.main import create_app

if __name__ == "__main__":
    print(json.dumps(create_app().openapi(), indent=2, sort_keys=True))
