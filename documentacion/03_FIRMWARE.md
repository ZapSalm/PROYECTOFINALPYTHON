# 03 — Firmware Arduino y ESP32

## Software y librerías Arduino

**Arduino UNO**
- Placa: `Arduino Uno` (AVR core).
- `Wire.h` (incluida en Arduino IDE).
- `hd44780` de **Bill Perry**, en especial `hd44780ioClass/hd44780_I2Cexp.h`.
- `pulseIn`, `digitalWrite`, `pinMode`, `Serial` (core AVR).

**ESP32**
- Placa: `ESP32 Dev Module`; paquete **esp32 by Espressif Systems**.
- `WiFi.h`, `WebServer.h`, `ArduinoOTA.h`, `Preferences.h`, `driver/gpio.h` (core ESP32).
- `ESP32Servo.h` (instalación mediante Library Manager).
- Monitor Serie USB a **115200**, Arduino UNO a **9600**. El protocolo UNO→ESP32 interno es **1200 bps**.

## Procesamiento de mediciones

- Todos los sensores reciben impulso TRIG de 10 µs, lectura ECHO con `pulseIn(..., 30000)`.
- Distancia calculada inicialmente en milímetros; `-1` = eco ausente o fuera de rango 20–4000 mm.
- Las plazas pasan a **ocupado** a ≤120 mm (12 cm) y **libre** a ≥150 mm (15 cm).
- Una nueva clasificación requiere dos lecturas consecutivas; entre 120 y 150 mm se conserva la anterior (histéresis).
- La entrada se detecta tras dos lecturas consecutivas a 50 mm o menos (5 cm).
- La entrada se confirma despejada tras dos lecturas consecutivas a 70 mm o más (7 cm).
- Apertura exige UNO comunicado, cuatro lecturas suficientes, entrada detectada y al menos un lugar libre.
- Tras despejar entrada, espera ~3000 ms antes de ordenar cierre. Si la entrada deja de ser fiable o falla comunicación, evita cerrar desde ese estado.
- Si no llegan tramas válidas durante más de **3500 ms**, los estados de sensores y plazas se invalidan y los LED se apagan.

## Protocolo compartido

La línea `D12` del UNO conmuta entre 0 V y alta impedancia; el ESP32 usa `Serial2.begin(1200, SERIAL_8N1, 16, 17)` y solo conecta físicamente RX GPIO16. Es **imprescindible** la resistencia 4.7 kΩ hacia 3V3 en el receptor. Trama: `S1:87,S2:1970,S3:1973,S4:1955\n`.

## Credenciales locales del ESP32

El sketch lee tres claves del archivo local indicado en esta línea:

```cpp
#include "config_private.h"
```

En la carpeta del `.ino`, copia el archivo `config_private.example.h` a `config_private.h` y coloca tres claves independientes:

```cpp
#define SP_AP_PASSWORD "TuClaveAPlarga123"
#define SP_CONTROL_TOKEN "TuTokenDeControlPrivado123"
#define SP_OTA_PASSWORD "TuClaveOTAprivada123"
```

- `SP_AP_PASSWORD`: conexión a `SmartParking-Setup`. Debe ser de 8–63 caracteres ASCII.
- `SP_CONTROL_TOKEN`: cabecera `X-Control-Token` enviada por la app para órdenes y cambio de Wi-Fi. Recomendado largo y único.
- `SP_OTA_PASSWORD`: contraseña de carga remota por ArduinoOTA, independiente.

`config_private.h` **no se comparte**: está excluido de Git. La red doméstica/hotspot se configura después desde Python y se almacena en `Preferences` del ESP32; no se programa en el `.ino`.

## Carga inicial y OTA

1. Primera vez: cable USB, ESP32 Dev Module, subir. Si aparece `Connecting...` prolongado, pulsar BOOT hasta que empiece `Writing...`.
2. Éxito: `Hash of data verified` y `Hard resetting via RTS pin...` indican verificación y reinicio normal.
3. Abrir Monitor Serie a 115200. Debe mostrar arranque y AP `192.168.4.1`.
4. Para cargar actualizaciones después: ESP32 y PC en el mismo hotspot; elegir el puerto de red `parqueo-esp32` desde Arduino IDE y usar la contraseña OTA del firmware que **está instalado**, no necesariamente una futura.

No mezclar archivos `.ino` de UNO y ESP32 en el mismo sketch; Arduino IDE compila todos los `.ino` que están en una carpeta de sketch y puede generar `redefinition`.

## Detalles de fiabilidad

El control del servo reporta una posición **ordenada**, no comprobada mediante sensor. La conexión puede mostrar sensor de entrada detectado mientras el carro no ha cruzado la pluma. No habilitar como barrera vehicular real sin controles adicionales.
