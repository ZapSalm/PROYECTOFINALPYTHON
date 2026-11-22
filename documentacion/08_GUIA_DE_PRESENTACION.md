# 08 — Guion técnico de demostración presencial

## Antes de llegar

- Llevar UNO, ESP32, cableado, fuente estable del servo, protoboard, laptop con EXE y cargadores.
- Instalar el firmware V4 y comprobar Wi-Fi con anticipación.
- Probar hotspot de 2.4 GHz; desactivar aislamiento entre clientes si el teléfono/router lo permite.
- Tener copia de ZIP, IDE, código fuente y el ejecutable ya creado en Windows.
- No exhibir las contraseñas ni el token en pantalla.

## Secuencia de 5–7 minutos

1. **Arquitectura (45 s):** explicar por qué hay dos microcontroladores: UNO adquiere sensores 5 V, ESP32 realiza lógica, conectividad y actuadores.
2. **Conexiones (45 s):** señalar S1 entrada, S2–S4 plazas, seis LED, LCD y SG90, además del cable D12→GPIO16 con GND común.
3. **Plazas (1–2 min):** mostrar tres libres, colocar un carrito en S2, comprobar LED rojo P1 y actualización en Python; repetir con otra plaza.
4. **Entrada (1 min):** acercar objeto a S1 con cupo; describir condición de autorización y verificar orden al servo. No poner dedos bajo la barrera.
5. **Parqueo lleno (45 s):** ocupar las tres plazas y enseñar que no autoriza una nueva entrada.
6. **Red (1 min):** mostrar AP `192.168.4.1`, consultar estado, enviar `ping` con token en campo oculto y explicar cómo puede vincularse a un hotspot diferente sin reprogramar.
7. **Diagnóstico y cierre (30 s):** enseñar histórico, exportación CSV y límites de seguridad.

## Plan de contingencia

- Si el hotspot falla, conecta PC a `SmartParking-Setup` y usa IP `192.168.4.1`.
- Si la app no encuentra el ESP32, consultar `/api/estado` desde el navegador.
- Si no hay energía de servo, presenta la lógica y los indicadores sin operar la pluma.
- Si no hay electrónica, abrir `ABRIR_DEMO.cmd`, **aclarando explícitamente que son datos simulados**.
