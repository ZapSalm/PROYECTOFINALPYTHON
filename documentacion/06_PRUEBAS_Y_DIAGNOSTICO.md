# 06 — Pruebas y diagnóstico

## Comprobaciones de software realizadas

Las suites `PRUEBAS.py` (**17 casos**) y `PRUEBAS_RED.py` (**9 casos**) validan respuestas HTTP simuladas, normalización de sensores, ocupación, desconexión del UNO, informes, exportación CSV, detección de IP, token y procesamiento de órdenes. El flujo automatizado también comprueba la sintaxis de Python con `py_compile`.

**Alcance limitado:** son pruebas de software y API simulada. No equivalen a compilar firmware UNO/ESP32 con Arduino IDE ni prueban tensiones, cableado o movimiento real. Los ensayos físicos siguen siendo necesarios.

### En computadora

```powershell
cd aplicacion
py -3 PRUEBAS.py
py -3 PRUEBAS_RED.py
cd ..
py -3 herramientas/validar_repositorio.py
```

GitHub Actions ejecuta los tests de Python y el validador de archivos al hacer push/PR.

## Matriz de comprobación de la maqueta

| Caso | Acción | Resultado esperado |
|---|---|---|
| Arranque | Encender UNO y ESP32 | Se inicializa la LCD y el monitor muestra cuatro sensores. |
| Plaza 1 | Colocar un carrito a ≤12 cm de S2 | Se enciende el LED rojo de la plaza 1 y el monitor la muestra ocupada. |
| Plaza 2 | Colocar un carrito a ≤12 cm de S3 | Se enciende el LED rojo de la plaza 2 y el monitor la muestra ocupada. |
| Plaza 3 | Colocar un carrito a ≤12 cm de S4 | Se enciende el LED rojo de la plaza 3 y el monitor la muestra ocupada. |
| Liberación | Retirar el carrito y dejar una referencia a ≥15 cm | El LED verde vuelve tras dos lecturas. |
| Entrada | Acercar un objeto a ≤15 cm de S1 con cupo | El firmware ordena abrir la pluma. |
| Parqueo lleno | Ocupar las tres plazas | El monitor muestra cero plazas libres y se bloquea una nueva entrada. |
| Eco ausente | Interrumpir el eco de S3 | El estado de la plaza 2 pasa a desconocido y se apagan ambos LED. |
| UNO apagado | Interrumpir la comunicación | La API indica UNO desconectado y las plazas pasan a desconocidas. |
| Cambio de red | Configurar otro hotspot desde Python | La API devuelve `sta_conectado=true` y una IP STA asignada. |
| Orden `ping` | Enviar un token válido y un identificador | El acuse devuelve el mismo identificador y `ejecutado=true`. |
| OTA | Cargar el firmware por Wi-Fi | Arduino IDE verifica la carga y el ESP32 reinicia. |

## Guía rápida de fallos

| Síntoma | Causa frecuente | Verificación |
|---|---|---|
| Verde enciende pero rojo no | Polaridad, GND, GPIO incorrecto, resistor o no cambia estado | Prueba `led_rojo` de 2 s y comprueba GPIO26/32/23 |
| `S1:-1...` | Sin eco, alimentación o cable sensor, falta reflector | Monitor Serie UNO, 5 V, TRIG/ECHO, superficie de referencia |
| `UNO:SIN DATOS` | D12↔GPIO16 desconectado, GND sin unir o trama incorrecta | Pull-up de 4.7k a 3V3 y Serial2 1200 bps |
| App no encuentra ESP32 | IP obsoleta / red diferente | `192.168.4.1/api/estado` en AP o buscar IP STA |
| `ESP_...` como red abierta | AP de firmware distinto o contraseña AP menor a 8 | Ver SSID en firmware y reforzar clave AP |
| Servo tiembla o reinicia ESP32 | Alimentación inestable | 5 V regulados para servo y GND común |
| `WiFi.h No such file` | Placa Arduino Uno seleccionada para código ESP32 | Seleccionar `ESP32 Dev Module` |
| `redefinition` | Dos `.ino` o declaraciones duplicadas en carpeta | Abrir carpetas independientes para UNO y ESP32 |
| `Hard resetting via RTS pin...` | Final normal de la carga | Presionar EN y abrir Monitor Serie 115200 |

## Seguridad del mecanismo de entrada

S1 no confirma que un vehículo haya pasado completamente debajo de la barrera. No probar apertura/cierre con vehículos reales ni personas; supervisar el SG90 y retirar su brazo durante calibración.
