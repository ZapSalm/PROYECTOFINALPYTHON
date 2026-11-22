# 05 — Wi-Fi, endpoints HTTP y ArduinoOTA

## Dos interfaces de red

**Modo AP**: `SmartParking-Setup`, IP fija `192.168.4.1` del ESP32. La PC debe conectarse a este SSID para aprovisionarlo, salvo que ya tenga acceso por la red STA. No proporciona Internet; Windows puede marcarlo «Sin Internet» y eso es normal.

**Modo STA**: el ESP32 se asocia al Wi-Fi o hotspot configurado desde Python, en banda **2.4 GHz**, obtiene IP por DHCP y la reporta mediante `/api/wifi/status`. La PC debe estar en la misma LAN sin aislamiento entre clientes. Las credenciales se conservan en NVS de `Preferences` para siguientes arranques.

**No confundir IPs:** 192.168.4.1 es la AP interna del ESP32; la IP STA será asignada por el hotspot y puede cambiar. `192.168.1.18` fue una dirección de pruebas anterior, no una constante del proyecto.

## Secuencia de cambio de red

1. Encender UNO y ESP32.
2. Conectar Windows al SSID de configuración del ESP32; introducir `SP_AP_PASSWORD`.
3. En la app, **Usar IP de configuración** → `192.168.4.1` → **Conectar**.
4. **Configurar red Wi-Fi** → token privado → SSID y contraseña del hotspot → **Guardar y conectar hotspot**.
5. Esperar y consultar **estado de red**. `aceptado: true` al guardar no significa asociación completada; es necesaria `sta_conectado: true` y `ip_sta` no nula.
6. Conectar Windows al mismo hotspot y usar **Buscar ESP32 en la red** o introducir `ip_sta` manualmente.
7. Probar `ping` autenticado y luego verificar las cuatro distancias.

Si se equivoca en la clave, reconectar al AP y repetir. Si un AP quedó **abierto**, es posible que la contraseña del AP usada en el firmware tuviera menos de 8 caracteres: fijar y volver a instalar; no presentar así en público.

## API utilizada por Python

La API devuelve JSON salvo `/api/logs` (texto). En el ESP32 `WebServer` escucha puerto TCP **80**. Ejemplos:

| Método | Endpoint | Acción | Autenticación |
|---|---|---|---|
| GET | `/api/estado` | Lecturas, plazas, servo, conexión | No |
| GET | `/api/logs` | Registro reciente | No |
| GET | `/api/wifi/status` | SSID, AP, STA, IP y RSSI | No |
| GET | `/api/wifi/scan` | Escaneo de redes 2.4 GHz (puede estar pendiente) | No |
| POST | `/api/wifi/config` | Guardar SSID/contraseña hotspot e iniciar conexión | `X-Control-Token` |
| POST | `/api/comando` | Orden controlada con acuse | `X-Control-Token` |

### GET /api/estado

Ejemplo de respuesta saneada en [api_estado_ejemplo.json](api_estado_ejemplo.json). Campos especialmente importantes: `sensor1_cm`…`sensor4_cm`, `plaza1_ocupada`…`plaza3_ocupada`, `plazas_total`, `plazas_ocupadas`, `plazas_libres`, `parqueo_lleno`, `vehiculo_entrada`, `servo_disponible`, `pluma`, `arduino_conectado`, `wifi_sta_conectado`, `ip` y `ip_ap`. `null` representa medición o estado no conocido.

### POST /api/wifi/config

- Header: `X-Control-Token: <token de control privado>`.
- Cuerpo tipo `application/x-www-form-urlencoded`, con `ssid` y `password`.
- Respuesta **202** cuando se guarda la petición y se inicia el proceso. Consultar después `/api/wifi/status` para confirmar el resultado.
- No publicar capturas, credenciales ni solicitudes con password real.

### POST /api/comando

- Header: `X-Control-Token: <token de control privado>`.
- Cuerpo tipo `application/x-www-form-urlencoded`, con `accion` e `id`.
- Acciones: `ping`, `led_verde`, `led_rojo`, `abrir`, `cerrar`.
- Si se acepta: `recibido: true`, `ejecutado: true` y se devuelve el `id`. Si se bloquea por estado inseguro: `HTTP 409`, `ejecutado: false`.
- El acuse significa **procesamiento en software**, no prueba de movimiento físico.

## OTA

El firmware inicial de V4 debe estar instalado. Con PC y ESP32 en la misma red, Arduino IDE puede detectar el puerto de red `parqueo-esp32`; se usa la **clave OTA del firmware instalado**. La aplicación Python V4 **no compila ni sube** código C++/`.ino`. No hacer OTA mientras se demuestra movimiento de la barrera.

## Seguridad

- API sin TLS/HTTPS: para maqueta solo en Wi-Fi local protegido y bajo control.
- El AP permanece activo como mecanismo de recuperación. Utilizar AP password fuerte.
- Tokens y credenciales en `config_private.h` excluido de GitHub.
- GET de telemetría es público para dispositivos de la misma red, y la seguridad física no depende de autenticación.
- Para una producción real harían falta autenticación integral, TLS, rotación de secretos, red aislada y límites de peticiones.
