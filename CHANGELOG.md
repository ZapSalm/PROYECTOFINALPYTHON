# Registro de cambios

## V5 — actualización del paquete

- Ejecutable de Windows y capturas de configuración Wi-Fi y control remoto para Smart Parking V5.

## V5 — segundo avance

- Ajuste de la detección de entrada a 5 cm con dos lecturas consecutivas.
- Confirmación de despeje a 7 cm con dos lecturas antes de contar el retardo de cierre de 3 segundos.
- Monitor de demostración actualizado al alcance de la maqueta.
- Informe del segundo avance, capturas, logo y versiones de dependencias en la documentación.

## Funcionalidades de la base del proyecto

- Monitor Python con tres plazas, cuatro sensores, diagnósticos, eventos, gráficas y exportaciones.
- Configuración Wi-Fi AP/STA y credenciales del hotspot enviadas desde la aplicación.
- API del ESP32 para estado, logs, búsqueda de redes y órdenes autenticadas.
- Soporte ArduinoOTA para actualizaciones desde Arduino IDE.
- Diagrama completo de pines y distribución de maqueta.
- Configuración de credenciales del ESP32 en el archivo local `config_private.h`.
- 26 pruebas automatizadas de Python con API simulada y validador de pinout y configuración.
- Documentación de los módulos de Python, su función y la generación del ejecutable con PyInstaller.
