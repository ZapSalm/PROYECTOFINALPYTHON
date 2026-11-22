# 06 — Pruebas y diagnóstico

## Comprobaciones de software realizadas

En el entorno de preparación de este paquete se ejecutan `PRUEBAS.py` (**17 tests**) y `PRUEBAS_RED.py` (**9 tests**), total **26**. Estas pruebas validan respuestas simuladas de HTTP, normalización de sensores, ocupación, estado lleno, desconexión UNO, informes, CSV, detección de IP, token y aceptación/rechazo de órdenes. También se verifica sintaxis Python con `py_compile`.

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

## Evidencias observadas en la maqueta (usuario, noviembre de 2026)

- El IDE informó `Hash of data verified` y `Hard resetting via RTS pin...` al cargar firmware V4 por USB.
- Monitor Serie del ESP32: punto de acceso iniciado en **192.168.4.1**, `UNO comunicado: 4 sensores reconocidos`, tres plazas libres, S1 cercano y apertura ordenada.
- El endpoint `/api/estado` respondió por Wi-Fi, y Smart Parking V4 mostró **ESP32 en línea**, Arduino conectado, tres plazas libres, distancias de los cuatro sensores y pluma informada como abierta.
- **No se afirma** que el firmware de este pack, ya reorganizado para claves privadas, se haya recompilado o subido. Las pruebas físicas de todas las combinaciones ocupadas, el cambio efectivo de hotspot y OTA completo están por documentar.

## Matriz de pruebas físicas recomendadas antes de exposición

| Caso | Acción | Resultado esperado | Estado |
|---|---|---|---|
| Arranque | Encender UNO y ESP32 | LCD inicializa; cuatro sensores visibles | Parcialmente observado |
| Plaza 1 | Carrito frente a S2 a <12 cm | LED rojo P1; verde P1 apagado; Python ocupada | Pendiente repetir en maqueta final |
| Plaza 2 | Carrito frente a S3 a <12 cm | LED rojo P2; Python ocupada | Pendiente |
| Plaza 3 | Carrito frente a S4 a <12 cm | LED rojo P3; Python ocupada | Pendiente |
| Liberación | Retirar carrito y dejar referencia ≥15 cm | Verde vuelve tras dos lecturas | Pendiente |
| Entrada | Acercar objeto a S1 ≤15 cm con plazas libres | Solicitud apertura, estado abierta | Observado a nivel lógico |
| Lleno | Ocupar las 3 plazas | 0 libres, mensaje lleno, nueva entrada bloqueada | Pendiente |
| Sensor perdido | Retirar eco de S3 | P2 desconocida y ambos LED P2 apagados | Pendiente |
| UNO apagado | Interrumpir comunicación | API indica UNO desconectado y plaza desconocida | Pendiente |
| Hotspot nuevo | Cambiar red desde Python | `sta_conectado=true`, `ip_sta` asignada | Pendiente |
| Orden `ping` | Enviar token + id | Acuse con el mismo id y `ejecutado=true` | Pendiente en hardware |
| OTA | Subir firmware por Wi-Fi | Arduino IDE verifica y reinicia | Pendiente en V4 |

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
