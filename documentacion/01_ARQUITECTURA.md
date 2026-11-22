# 01 — Arquitectura y flujo de información

## Objetivo

Demostrar un parqueo de **tres plazas** que observe presencia, informe disponibilidad local y remota, y autorice apertura de una barrera cuando una nueva entrada es posible. Es un **prototipo de laboratorio**, no una barrera de seguridad vehicular comercial.

## Tres capas

**Adquisición local — Arduino UNO (5 V).** Controla las líneas TRIG/ECHO de cuatro sensores HC-SR04, obtiene distancia en milímetros, marca `-1` ante eco ausente o distancia fuera de 20–4000 mm, calcula el estado para mostrar en LCD I2C de 16×2 y envía una trama por D12 a 1200 baudios.

**Automatización y conectividad — ESP32-WROOM-32 (3.3 V).** Recibe tramas por GPIO16, aplica histéresis y confirmación de dos lecturas, gestiona seis LED y un SG90, ofrece un servidor HTTP, crea el punto de acceso de configuración, se conecta opcionalmente al hotspot mediante STA y acepta órdenes controladas con token. Guarda las credenciales de hotspot en `Preferences` (memoria NVS).

**Supervisión — Aplicación Python para Windows.** Usa Tkinter para mostrar plazas, distancias, estado lógico de LED, señal de entrada, orden al servo, conexión UNO, logs, historial, diagnóstico, exportaciones y cambio de red. Consulta `/api/estado` aproximadamente cada 1.7 s; el trabajo de red se ejecuta en hilos para no congelar la ventana.

## Protocolo interno UNO→ESP32

- **Unidireccional**, 1200 baudios, 8N1.
- Mensaje ASCII terminado en `\n`, por ejemplo `S1:87,S2:1970,S3:1973,S4:1955`.
- Todas las distancias dentro del mensaje son **milímetros**. `S1` = entrada; `S2`–`S4` = plazas 1–3.
- D12 **no genera nivel HIGH de 5 V**. Funciona en bajo forzado (`OUTPUT LOW`) o alta impedancia (`INPUT` sin pull-up del UNO); GPIO16 tiene pull-up externo de 4.7 kΩ conectado a **3V3**.
- Tierra común imprescindible. Nunca conectar un UART de 5 V configurado en push-pull al ESP32.

## Hipótesis de montaje

Sensor apuntando a una superficie de referencia estable incluso con la plaza vacía; un vehículo acorta la distancia. La posición y ángulo se calibran sobre la maqueta. Los umbrales de firmware no son una escala de estacionamiento real.

## Ejemplo de operación

1. S1 detecta carrito a ~8 cm.
2. S2–S4 reportan mediciones válidas; el ESP32 determina si existe al menos una libre.
3. Si hay libre, se ordena apertura del SG90. Cuando S1 se despeja, el firmware espera 3 s antes de cerrar.
4. El estado de S2–S4 cambia a ocupado/libre, modifica LED y LCD y se publica por HTTP.
5. Python actualiza la UI, eventos e historial.

Consulta también [cableado](02_HARDWARE_Y_CABLEADO.md) y [API](05_RED_WIFI_API_OTA.md).
