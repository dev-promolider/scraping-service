import sys
import os

# Asegurarnos de que src/ esté en el path para que encuentre scrapegraph_api
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from scrapegraph_api.api import app as application
