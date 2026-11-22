# 07 — Seguridad, privacidad y limitaciones

## Lo que SÍ garantiza la lógica del prototipo

- No abre para una nueva entrada si todas las plazas figuran ocupadas, si faltan lecturas válidas o no se recibe información reciente del UNO.
- LED de estado desconocido apagados; nunca se representa automáticamente como libre.
- Cierre lógico no se ordena durante detección de objeto en la entrada ni si se pierde la lectura o comunicación mientras la pluma está abierta.
- Las órdenes remotas autorizadas se limitan a cinco acciones predefinidas; no existe ejecución remota de código arbitrario desde la app.

## Lo que NO garantiza

- La posición **física** de la pluma (solo se conoce la orden PWM).
- Que no haya persona/vehículo bajo la barrera, pues solo existe un sensor de presencia en la entrada y no hay sensor de paso redundante.
- Que la medición ultrasónica sea válida para todas las formas/ángulos/superficies.
- Seguridad criptográfica sobre HTTP: tanto comandos como credenciales del hotspot cruzan una red local sin cifrado de capa aplicación.
- Telemetría privada frente a cualquier cliente de la misma red; las rutas GET no están autenticadas.
- Funcionamiento industrial o continuo sin pruebas de estrés.

## Protección de secretos para GitHub

- NO versionar SSID privado, contraseñas domésticas, `SP_AP_PASSWORD`, `SP_CONTROL_TOKEN`, `SP_OTA_PASSWORD` reales ni tokens enviados al dispositivo.
- Usar `config_private.example.h` como plantilla y crear `config_private.h` en local. Este último está en `.gitignore`.
- Nunca publicar capturas de configuración con contraseñas visibles. Las imágenes de este paquete son de demostración.
- Si un secreto ya se publicó en algún lugar, cambiarlo/rotarlo; borrar el archivo de un commit posterior **no lo elimina del historial de Git**.
- No publicar reportes TXT o CSV exportados de presentaciones si contienen información sensible de red/personas.

## AP abierto por clave corta

En la versión del firmware de origen, una contraseña de AP con menos de 8 caracteres podía provocar un punto de acceso sin seguridad WPA2. El repositorio exige mediante `static_assert` que la clave AP tenga 8–63 caracteres. Esto no sustituye probar que Windows lo muestra como red **Segura**. Comprueba también el éxito de inicialización en el Monitor Serie.

## Para mejorar una versión posterior

Usar sensor óptico de seguridad bajo pluma, dos sensores de paso/vehículo, fin de carrera para confirmar posición, watchdog, protección de fuente, carcasa, credenciales con acceso limitado, HTTPS o protocolo de enlace autenticado. Esas mejoras **no están implementadas en la V4 documentada**.
