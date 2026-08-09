"""
Configuració del projecte Agenda Fonera.

Les credencials es llegeixen de dues maneres:
  1. De variables d'entorn (és com funciona a GitHub Actions, amb els "secrets").
  2. Si no n'hi ha, dels valors escrits aquí sota (per treballar al teu ordinador).

IMPORTANT: si escrius les credencials aquí, aquest fitxer NO s'ha de pujar mai
a GitHub. El .gitignore ja el bloqueja, però val més saber-ho.
"""

import os

API_KEY = os.environ.get("GOOGLE_API_KEY", "ENGANXA_AQUI_LA_TEVA_API_KEY")
CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "ENGANXA_AQUI_L_ID_DEL_CALENDARI")
