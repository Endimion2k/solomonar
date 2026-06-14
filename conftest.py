"""Pytest bootstrap: pune rădăcina repo pe sys.path ca `import pipeline` / `import connectors`
să funcționeze fără instalare. (solomonar_core e instalat editable separat.)"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
