import logging

import uvicorn

from liveline.app import create_app
from liveline.settings import Settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
uvicorn.run(create_app(Settings.load()), host="0.0.0.0", port=8000)
