"""Monitor de escritorio para ESP32: Python estandar, sin paquetes pip.

Ejecutar en Windows: py -3 monitor_parqueo.py
El ESP32 debe tener el sketch firmware_parqueo_ota.ino y estar en la misma LAN.
"""

import json
import queue
import threading
import tkinter as tk
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


IP_INICIAL = "192.168.1.18"  # Cambiar si el router asigna otra IP.
COLOR_FONDO = "#0d1422"
COLOR_PANEL = "#1b2940"
COLOR_TEXTO = "#edf3fb"
COLOR_MUTED = "#9cb0ca"
COLOR_VERDE = "#60d99b"
COLOR_ROJO = "#ff8585"


def consultar_esp32(host: str) -> tuple[dict, str]:
    """Solicita estado JSON y mensajes de la API del ESP32."""
    host = host.strip().removeprefix("http://").removeprefix("https://").rstrip("/")
    if not host:
        raise ValueError("Escribe la IP del ESP32")
    url_base = f"http://{host}"

    with urlopen(f"{url_base}/api/estado", timeout=3) as respuesta:
        estado = json.loads(respuesta.read().decode("utf-8"))
    with urlopen(f"{url_base}/api/logs", timeout=3) as respuesta:
        logs = respuesta.read().decode("utf-8", errors="replace")
    return estado, logs


class MonitorParqueo:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Parking Monitor - ESP32")
        self.root.geometry("880x630")
        self.root.minsize(720, 540)
        self.root.configure(bg=COLOR_FONDO)
        self.ip = tk.StringVar(value=IP_INICIAL)
        self.resultados: queue.Queue = queue.Queue()
        self.consulta_en_curso = False
        self.ultimos_logs = None
        self._construir_ui()
        self.root.after(100, self._procesar_resultados)
        self.root.after(100, self._actualizacion_periodica)

    def _etiqueta(self, padre, texto, tam=12, color=COLOR_TEXTO, negrita=False):
        return tk.Label(
            padre, text=texto, font=("Segoe UI", tam, "bold" if negrita else "normal"),
            fg=color, bg=padre.cget("bg"),
        )

    def _tarjeta(self, padre, titulo, columna):
        marco = tk.Frame(padre, bg=COLOR_PANEL, padx=17, pady=14)
        marco.grid(row=0, column=columna, sticky="nsew", padx=5)
        self._etiqueta(marco, titulo, 10, COLOR_MUTED).pack(anchor="w")
        valor = self._etiqueta(marco, "--", 27, COLOR_TEXTO, True)
        valor.pack(anchor="w", pady=(6, 0))
        return valor

    def _construir_ui(self):
        exterior = tk.Frame(self.root, bg=COLOR_FONDO, padx=25, pady=20)
        exterior.pack(fill="both", expand=True)

        encabezado = tk.Frame(exterior, bg=COLOR_FONDO)
        encabezado.pack(fill="x")
        self._etiqueta(encabezado, "Parking Monitor", 23, negrita=True).pack(side="left")
        self.lbl_conexion = self._etiqueta(
            encabezado, "● Sin conectar", 12, COLOR_ROJO, True
        )
        self.lbl_conexion.pack(side="right")

        self._etiqueta(
            exterior, "Estacionamiento automatico de 3 plazas · Conexion local por Wi-Fi",
            10, COLOR_MUTED,
        ).pack(anchor="w", pady=(3, 17))

        control = tk.Frame(exterior, bg=COLOR_PANEL, padx=13, pady=12)
        control.pack(fill="x")
        self._etiqueta(control, "IP del ESP32", 11, COLOR_MUTED).pack(side="left")
        tk.Entry(
            control, textvariable=self.ip, width=23, font=("Consolas", 12),
            bg="#111d30", fg=COLOR_TEXTO, insertbackground=COLOR_TEXTO,
            relief="flat", highlightthickness=0,
        ).pack(side="left", padx=12, ipady=7)
        tk.Button(
            control, text="Conectar / actualizar", command=self._solicitar_consulta,
            bg="#3170d2", fg="white", activebackground="#2457aa",
            activeforeground="white", relief="flat", cursor="hand2",
            font=("Segoe UI", 10, "bold"), padx=12, pady=7,
        ).pack(side="left")

        tarjetas = tk.Frame(exterior, bg=COLOR_FONDO)
        tarjetas.pack(fill="x", pady=(17, 14))
        for columna in range(3):
            tarjetas.grid_columnconfigure(columna, weight=1)
        self.val_total = self._tarjeta(tarjetas, "Capacidad", 0)
        self.val_ocupadas = self._tarjeta(tarjetas, "Ocupadas", 1)
        self.val_libres = self._tarjeta(tarjetas, "Disponibles", 2)

        detalles = tk.Frame(exterior, bg=COLOR_PANEL, padx=14, pady=11)
        detalles.pack(fill="x", pady=(0, 14))
        self.lbl_pluma = self._etiqueta(detalles, "Pluma: pendiente", 11, COLOR_MUTED)
        self.lbl_pluma.pack(side="left")
        self.lbl_senal = self._etiqueta(detalles, "Wi-Fi: -- dBm", 11, COLOR_MUTED)
        self.lbl_senal.pack(side="right")

        self._etiqueta(exterior, "Mensajes recibidos del ESP32", 13, negrita=True).pack(
            anchor="w", pady=(0, 8)
        )
        log_marco = tk.Frame(exterior, bg="#07101d")
        log_marco.pack(fill="both", expand=True)
        barra = tk.Scrollbar(log_marco)
        barra.pack(side="right", fill="y")
        self.texto_logs = tk.Text(
            log_marco, wrap="word", bg="#07101d", fg="#9be4b5",
            font=("Consolas", 10), relief="flat", padx=14, pady=14,
            yscrollcommand=barra.set, state="disabled", height=11,
        )
        self.texto_logs.pack(fill="both", expand=True)
        barra.config(command=self.texto_logs.yview)

        self.lbl_pie = self._etiqueta(
            exterior, "Esperando datos del ESP32...", 10, COLOR_MUTED
        )
        self.lbl_pie.pack(anchor="w", pady=(12, 0))

    def _solicitar_consulta(self):
        if self.consulta_en_curso:
            return
        self.consulta_en_curso = True
        host = self.ip.get().strip()
        threading.Thread(target=self._trabajador, args=(host,), daemon=True).start()

    def _trabajador(self, host):
        try:
            estado, logs = consultar_esp32(host)
            self.resultados.put(("ok", estado, logs))
        except (HTTPError, URLError, ValueError, TimeoutError, OSError) as error:
            self.resultados.put(("error", str(error), None))
        except Exception as error:
            self.resultados.put(("error", f"Respuesta inesperada: {error}", None))

    def _actualizacion_periodica(self):
        self._solicitar_consulta()
        self.root.after(1700, self._actualizacion_periodica)

    def _procesar_resultados(self):
        try:
            while True:
                tipo, dato, logs = self.resultados.get_nowait()
                self.consulta_en_curso = False
                if tipo == "ok":
                    self._mostrar_estado(dato, logs)
                else:
                    self.lbl_conexion.config(text="● Desconectado", fg=COLOR_ROJO)
                    self.lbl_pie.config(text=f"No se pudo consultar el ESP32: {dato}")
        except queue.Empty:
            pass
        self.root.after(100, self._procesar_resultados)

    def _mostrar_estado(self, estado, logs):
        self.lbl_conexion.config(text="● Conectado", fg=COLOR_VERDE)

        def numero_o_guion(valor):
            return "--" if valor is None else str(valor)

        self.val_total.config(text=numero_o_guion(estado.get("plazas_total")))
        self.val_ocupadas.config(text=numero_o_guion(estado.get("plazas_ocupadas")))
        self.val_libres.config(text=numero_o_guion(estado.get("plazas_libres")))

        pluma = estado.get("pluma", "sin_instalar")
        self.lbl_pluma.config(text=f"Pluma: {pluma.replace('_', ' ')}")
        self.lbl_senal.config(text=f"Wi-Fi: {estado.get('senal_wifi_dbm', '--')} dBm")
        hora = datetime.now().strftime("%H:%M:%S")
        ip = estado.get("ip", self.ip.get())
        self.lbl_pie.config(text=f"Ultima lectura: {hora}   |   ESP32: {ip}")

        if logs != self.ultimos_logs:
            self.ultimos_logs = logs
            self.texto_logs.config(state="normal")
            self.texto_logs.delete("1.0", "end")
            self.texto_logs.insert("end", logs or "(Aun no hay mensajes)")
            self.texto_logs.see("end")
            self.texto_logs.config(state="disabled")


def main():
    root = tk.Tk()
    MonitorParqueo(root)
    root.mainloop()


if __name__ == "__main__":
    main()
