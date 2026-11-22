# Publicar Smart Parking V4 en GitHub

El paquete reúne el firmware del ESP32 y Arduino UNO, el monitor Python, las pruebas, los diagramas y el ejecutable de Windows.

## Reemplazar el contenido actual de la rama principal

El ZIP incluye `PREPARAR_REEMPLAZO.cmd` junto a la carpeta `Repositorio`. Al ejecutarlo se crea un clon nuevo de `ZapSalm/PROYECTOFINALPYTHON`, se retiran del área de preparación los archivos de la versión anterior y se agregan los de esta carpeta. La ventana muestra la lista y los comandos para crear y subir el commit. Revisa especialmente las eliminaciones antes de crear el commit.

Un commit de reemplazo actualiza el contenido visible de `main` y conserva el historial del repositorio. Si había claves reales en un commit anterior, renuévalas aunque ese archivo desaparezca de `main`.

## Configuración privada y pruebas

Para recompilar el ESP32 copia `config_private.example.h` como `config_private.h` en la misma carpeta. Para conservar la configuración que ya usas, copia en tu equipo `AP_PASSWORD` a `SP_AP_PASSWORD`, `CONTROL_TOKEN` a `SP_CONTROL_TOKEN` y `CLAVE_OTA` a `SP_OTA_PASSWORD` desde tu firmware original. El archivo nuevo está excluido de Git.

El ejecutable incluido permite abrir el monitor en Windows. Comprueba `config_private.h` y la lista completa antes de publicar con `git diff --cached --name-status`. El flujo de GitHub Actions ejecuta las pruebas Python y no compila firmware.
