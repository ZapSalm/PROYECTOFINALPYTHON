# Registro de cambios

## V4 — versión documentada para GitHub (noviembre de 2026)

- Monitor Python con tres plazas, cuatro sensores, diagnósticos, eventos, gráficas y exportaciones.
- Configuración Wi-Fi AP/STA y credenciales del hotspot enviadas desde la aplicación.
- API del ESP32 para estado, logs, búsqueda de redes y órdenes autenticadas.
- Soporte ArduinoOTA para actualizaciones desde Arduino IDE.
- Diagrama completo de pines y distribución de maqueta.
- **Preparación para repositorio:** credenciales separadas en `config_private.h`, plantilla pública y exclusión mediante `.gitignore`; aviso de inicialización fallida del AP.
- 26 pruebas automatizadas de Python revisadas (API simulada), más validador estático del paquete.

## V3

- Diagnóstico de fallos, historial de sensores, exportación CSV y eventos.

## V2

- Adaptación de la aplicación de escritorio a tres plazas y cuatro sensores.

## Prototipo inicial

- Comunicación unidireccional UNO→ESP32 a 1200 baudios y control automático del servo.
