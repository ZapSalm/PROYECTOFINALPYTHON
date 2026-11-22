"""Verificaciones estáticas de integración: no sustituyen compilar Arduino ni probar hardware."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
UNO = (ROOT / 'firmware/arduino_uno/Parqueo_UNO_4_Sensores/Parqueo_UNO_4_Sensores.ino').read_text(encoding='utf-8')
ESP = (ROOT / 'firmware/esp32/Parqueo_ESP32_WiFi_Config/Parqueo_ESP32_WiFi_Config.ino').read_text(encoding='utf-8')
EXAMPLE = (ROOT / 'firmware/esp32/Parqueo_ESP32_WiFi_Config/config_private.example.h').read_text(encoding='utf-8')
PY = (ROOT / 'aplicacion/monitor_parqueo.py').read_text(encoding='utf-8')
README = (ROOT / 'README.md').read_text(encoding='utf-8')
IGNORE = (ROOT / '.gitignore').read_text(encoding='utf-8')
assert re.search(r'UNO_TRIG\[4\]\s*=\s*\{4,\s*6,\s*8,\s*10\}', UNO)
assert re.search(r'UNO_ECHO\[4\]\s*=\s*\{5,\s*7,\s*9,\s*11\}', UNO)
assert re.search(r'UNO_TX_ABIERTO\s*=\s*12', UNO)
assert re.search(r'GPIO_RX_UNO\s*=\s*16', ESP)
assert re.search(r'GPIO_SERVO\s*=\s*18', ESP)
assert re.search(r'GPIO_LED_VERDE\[3\]\s*=\s*\{25,\s*27,\s*33\}', ESP)
assert re.search(r'GPIO_LED_ROJO\[3\]\s*=\s*\{26,\s*32,\s*23\}', ESP)
assert 'S1:%ld,S2:%ld,S3:%ld,S4:%ld' in UNO and 'S1:%ld,S2:%ld,S3:%ld,S4:%ld%c' in ESP
for endpoint in ('/api/estado','/api/logs','/api/wifi/status','/api/wifi/scan','/api/wifi/config','/api/comando'):
    assert endpoint in ESP and endpoint in PY, endpoint
for macro in ('SP_AP_PASSWORD','SP_CONTROL_TOKEN','SP_OTA_PASSWORD'):
    assert macro in EXAMPLE and macro in ESP
assert '#include "config_private.h"' in ESP
assert 'config_private.h' in IGNORE
assert not (ROOT / 'firmware/esp32/Parqueo_ESP32_WiFi_Config/config_private.h').exists(), '¡Clave privada incluida en paquete!'
assert 'SmartParking-Setup' in ESP and '192.168.4.1' in README
for png in ('01_Diagrama_General.png','02_Detalle_LEDs.png','03_Plano_Maqueta.png'):
    assert (ROOT/'diagramas'/png).exists()
print('OK: 4 sensores, UART, 6 LED, servo, endpoints, esquema y configuracion privada coherentes.')
