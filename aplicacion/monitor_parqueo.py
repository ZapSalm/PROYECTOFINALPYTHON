"""Smart Parking Monitor V5, configuración Wi-Fi y órdenes, Python 3.10+.
Ejecutar: py -3 monitor_parqueo.py | Demostración: --demo
"""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
import ipaddress
import json
import math
import os
import queue
import re
import socket
import uuid
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlsplit, urlencode
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError

IP_INICIAL = '192.168.4.1'
AP_CONFIG_IP = '192.168.4.1'
BG = '#0c1420'
PANEL = '#182536'
PANEL2 = '#111e2e'
TEXT = '#f1f5f9'
MUTED = '#9baec1'
GREEN = '#5cdda0'
RED = '#ff858b'
AMBER = '#f7c36e'
BLUE = '#7dc5ff'
FONT = 'Segoe UI'
INTERVAL = 1700
MAX_EVENTS = 350
MAX_HISTORY = 1800
HISTORY_COLUMNS = (
    "fecha_hora", "origen", "sensor1_cm", "sensor2_cm", "sensor3_cm", "sensor4_cm",
    "plaza1_ocupada", "plaza2_ocupada", "plaza3_ocupada", "vehiculo_entrada",
    "plazas_ocupadas", "plazas_libres", "pluma_ordenada", "arduino_conectado", "wifi_dbm", "estado"
)

def history_row(ts, source, state=None, status="ok"):
    state = state or {}
    return (ts.isoformat(timespec="seconds"), source, *state.get("dist", [None]*4),
            *state.get("ocup", [None]*3), state.get("entrada"), state.get("ocupadas"),
            state.get("libres"), state.get("pluma"), state.get("arduino"), state.get("rssi"), status)

def export_history(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(HISTORY_COLUMNS)
        writer.writerows(rows)



def base_url(host):
    host = host.strip()
    if not host:
        raise ValueError('Escribe la IP o el nombre del ESP32.')
    if '://' not in host:
        host = 'http://' + host
    u = urlsplit(host)
    if u.scheme != 'http' or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ('', '/'):
        raise ValueError('Usa una IP o nombre local, por ejemplo 192.168.1.18.')
    # No aceptar caracteres extraños en el nombre del equipo.
    name = u.hostname
    try:
        ipaddress.ip_address(name)
    except ValueError:
        if not re.fullmatch(r'[A-Za-z0-9.-]+', name):
            raise ValueError('Dirección no válida.')
    if u.port is not None and not 1 <= u.port <= 65535:
        raise ValueError('Puerto no válido.')
    return 'http://' + u.netloc


def get_text(url, timeout=2.5):
    # El ESP32 está en la LAN; no usar proxies configurados por Windows.
    opener = build_opener(ProxyHandler({}))
    with opener.open(Request(url, headers={'Accept': '*/*', 'Cache-Control': 'no-cache'}), timeout=timeout) as response:
        raw = response.read(131073)
        if len(raw) > 131072:
            raise ValueError('Respuesta demasiado grande.')
        return raw.decode('utf-8', errors='replace')


def consultar_esp32(host):
    base = base_url(host)
    estado = json.loads(get_text(base + '/api/estado'))
    if not isinstance(estado, dict) or not any(k in estado for k in ('equipo', 'plazas_total', 'arduino_conectado', 'sensor1_cm')):
        raise ValueError('La respuesta no parece corresponder al firmware del parqueo.')
    # La consola puede fallar por separado sin invalidar la telemetría.
    try:
        logs = get_text(base + '/api/logs')
        error_logs = None
    except Exception as exc:
        logs, error_logs = None, str(exc)
    return estado, logs, error_logs



def api_json(host, endpoint, fields=None, token=None, timeout=4):
    """Solicita estado o envía campos form; devuelve también los HTTP 4xx con JSON.

    No escribe las contraseñas ni el token en archivos o URLs.
    """
    if endpoint not in ('/api/wifi/status', '/api/wifi/scan', '/api/wifi/config', '/api/comando'):
        raise ValueError('Endpoint no permitido.')
    body = urlencode(fields, encoding='utf-8').encode('utf-8') if fields is not None else None
    headers = {'Accept': 'application/json', 'Cache-Control': 'no-cache'}
    if body is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=utf-8'
    if token is not None:
        if not token.strip() or '\r' in token or '\n' in token:
            raise ValueError('Escribe el token de control del firmware.')
        headers['X-Control-Token'] = token.strip()
    req = Request(base_url(host) + endpoint, data=body, headers=headers,
                  method='POST' if body is not None else 'GET')
    opener = build_opener(ProxyHandler({}))
    try:
        response = opener.open(req, timeout=timeout)
    except HTTPError as e:
        response = e
    with response:
        raw = response.read(131073)
        if len(raw) > 131072:
            raise ValueError('Respuesta del ESP32 demasiado grande.')
        data = json.loads(raw.decode('utf-8'))
        if not isinstance(data, dict):
            raise ValueError('El ESP32 no devolvió un objeto JSON.')
        data['_http_status'] = response.status
        return data


def validar_wifi(ssid, password):
    # El tamaño del SSID es en bytes, no en caracteres de pantalla.
    if not 1 <= len(ssid.encode('utf-8')) <= 32:
        raise ValueError('El SSID debe ocupar entre 1 y 32 bytes.')
    if not 8 <= len(password.encode('utf-8')) <= 63:
        raise ValueError('La clave del hotspot debe tener entre 8 y 63 bytes.')
    return ssid, password


def comandos_permitidos():
    return {'ping': 'Ping — verificar recepción',
            'led_verde': 'Probar los 3 LED verdes (2 s)',
            'led_rojo': 'Probar los 3 LED rojos (2 s)',
            'abrir': 'Abrir pluma (con cupo y sensores válidos)',
            'cerrar': 'Cerrar pluma (solo entrada despejada)'}


def interfaces_ipv4():
    """Solo IPv4 locales; descubrimiento limitado a la /24 actual del usuario."""
    ips = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('1.1.1.1', 80))  # UDP connect: no envía paquetes.
            ips.add(sock.getsockname()[0])
    except OSError:
        pass
    try:
        ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return sorted(ip for ip in ips if ipaddress.ip_address(ip).is_private
                  and not ipaddress.ip_address(ip).is_loopback)


def descubrir_esp32():
    """Busca exclusivamente en /24 locales; confirma la identidad del dispositivo."""
    ip_candidates = set()
    for ip in interfaces_ipv4():
        net = ipaddress.ip_network(ip + '/24', strict=False)
        ip_candidates.update(str(h) for h in net.hosts())
        ip_candidates.discard(ip)
    ip_candidates.add(AP_CONFIG_IP)

    def probe(host):
        try:
            obj = api_json(host, '/api/wifi/status', timeout=.45)
            if obj.get('equipo') == 'parqueo-esp32':
                return {'host': host, 'ssid': obj.get('ssid'), 'ip_sta': obj.get('ip_sta')}
        except Exception:
            # La V3 es visible por /api/estado, pero no se puede configurar remotamente.
            try:
                obj = json.loads(get_text(base_url(host) + '/api/estado', timeout=.45))
                if obj.get('equipo') == 'parqueo-esp32':
                    return {'host': host, 'ssid': None, 'ip_sta': None}
            except Exception:
                pass
        return None

    found = []
    with ThreadPoolExecutor(max_workers=28) as pool:
        futures = {pool.submit(probe, ip): ip for ip in ip_candidates}
        for fut in as_completed(futures):
            value = fut.result()
            if value:
                found.append(value)
    return sorted(found, key=lambda x: (x['host'] == AP_CONFIG_IP, x['host']))


def valor_distancia(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or not 2 <= value <= 400:
        return None
    return float(value)


def booleano(value):
    return value if isinstance(value, bool) else None


def entero(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def normalizar(estado):
    """No inventar ocupación ni derivar libre a partir de null."""
    arduino = booleano(estado.get('arduino_conectado'))
    dist = [valor_distancia(estado.get(f'sensor{i}_cm')) for i in range(1, 5)]
    ocup = [booleano(estado.get(f'plaza{i}_ocupada')) for i in range(1, 4)]
    entrada = booleano(estado.get('vehiculo_entrada'))
    if arduino is False:
        dist = [None] * 4
        ocup = [None] * 3
        entrada = None
    else:
        for i in range(3):
            if dist[i + 1] is None:
                ocup[i] = None
        if dist[0] is None:
            entrada = None
    total = entero(estado.get('plazas_total'))
    ocupadas = entero(estado.get('plazas_ocupadas'))
    libres = entero(estado.get('plazas_libres'))
    # No mostrar conteos definitivos si la API no tiene lecturas completas/coherentes.
    if (total != 3 or None in ocup or ocupadas is None or libres is None
            or ocupadas != sum(x is True for x in ocup) or ocupadas + libres != total):
        ocupadas = libres = None
    lleno = booleano(estado.get('parqueo_lleno')) if ocupadas is not None else None
    if lleno is not None and lleno != (ocupadas == 3):
        lleno = None
    pluma = estado.get('pluma')
    if pluma not in ('abierta', 'cerrada', 'error', 'sin_instalar', 'en_prueba'):
        pluma = None
    rssi = estado.get('senal_wifi_dbm')
    if isinstance(rssi, bool) or not isinstance(rssi, (int, float)) or not math.isfinite(rssi):
        rssi = None
    return dict(arduino=arduino, dist=dist, ocup=ocup, entrada=entrada,
                total=total, ocupadas=ocupadas, libres=libres, lleno=lleno,
                pluma=pluma, servo=booleano(estado.get('servo_disponible')),
                rssi=rssi, uptime=entero(estado.get('tiempo_encendido_s')),
                modo=estado.get('modo'), lcd=estado.get('lcd'), ip=estado.get('ip'),
                equipo=estado.get('equipo'), wifi=booleano(estado.get('conectado')))


def config_path():
    """Solo almacena la última IP/nombre, nunca contraseñas."""
    base = Path(os.environ.get('APPDATA', str(Path.home() / '.config')))
    return base / 'SmartParkingMonitor' / 'config.json'


def cargar_host_guardado():
    try:
        data = json.loads(config_path().read_text(encoding='utf-8'))
        host = data.get('host')
        if isinstance(host, str):
            base_url(host)
            return host
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return IP_INICIAL


def guardar_host(host, destino=None):
    base_url(host)
    path = Path(destino) if destino else config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'host': host}, ensure_ascii=False), encoding='utf-8')


def diagnosticar(s):
    """Devuelve severidad, título, indicaciones. Nunca confirma LEDs o pluma físicos."""
    notes = []
    sev = 'ok'
    def add(level, msg):
        nonlocal sev
        notes.append(msg)
        if level == 'error' or (level == 'warning' and sev != 'error'):
            sev = level

    if s['arduino'] is not True:
        add('error' if s['arduino'] is False else 'warning',
            'Arduino UNO sin comunicación confirmada. Verificar UNO D12 → ESP32 GPIO16, GND común y firmware de 4 sensores.')
    else:
        for i, d in enumerate(s['dist']):
            if d is None:
                add('error', f'Sensor S{i + 1} sin distancia válida; revisar alimentación, TRIG/ECHO y superficie de referencia.')
        missing = [str(i + 1) for i, x in enumerate(s['ocup']) if x is None]
        if missing:
            add('error', f'Estado no confirmado de plaza(s) {", ".join(missing)}. Sus LED lógicos quedan apagados; no se autoriza entrada.')
        if not missing and s['ocupadas'] is None:
            add('warning', 'El conteo de ocupadas/libres no coincide con los estados de las plazas o falta en la API.')
    if s['servo'] is False or s['pluma'] == 'error':
        add('error', 'Servo no disponible según el ESP32. Revisar GPIO18, 5 V regulados externos y GND común.')
    elif s['servo'] is None:
        add('warning', 'No se ha podido confirmar la inicialización PWM del servo.')
    if s['ocupadas'] == 3:
        add('warning', 'PARQUEO LLENO: las nuevas entradas están bloqueadas por la lógica del ESP32.')
    elif s['entrada'] is True and s['pluma'] == 'cerrada' and s['libres'] is not None and s['libres'] > 0 and s['servo'] is True:
        add('warning', 'Vehículo detectado y cupo disponible, pero la pluma indica CERRADA. Puede estar esperando confirmación; si persiste, revisar control del servo.')
    if s['rssi'] is not None and s['rssi'] < -78:
        add('warning', f'Señal Wi-Fi baja ({s["rssi"]:g} dBm). Acercar el ESP32 al router.')
    if not notes:
        return 'ok', 'Telemetría sin alertas', ['Los estados recibidos son coherentes. Verificar visualmente LEDs y pluma antes de la presentación.']
    return sev, f'{len(notes)} aviso(s) del sistema', notes


def texto_reporte(s, notas, eventos, logs, fecha=None):
    fecha = fecha or datetime.now()
    lines = [
        'SMART PARKING — REPORTE DE DIAGNÓSTICO',
        f'Fecha: {fecha:%Y-%m-%d %H:%M:%S}',
        'Monitor: V3 FINAL | Consulta HTTP de solo lectura',
        'NOTA: LED = estado lógico esperado; pluma = posición ordenada, NO confirmación física.',
        '', 'RESUMEN DEL SISTEMA',
    ]
    if s is None:
        lines.append('No hay telemetría actual válida.')
    else:
        lines.extend([
            f'ESP32 IP: {s["ip"] or "—"}',
            f'Arduino UNO conectado: {s["arduino"]}',
            f'Capacidad: {s["total"]} | Ocupadas: {s["ocupadas"]} | Libres: {s["libres"]}',
            f'Entrada: {s["entrada"]} | Pluma ordenada: {s["pluma"]} | Servo PWM: {s["servo"]}',
            f'Wi-Fi RSSI: {s["rssi"]} dBm | Encendido: {format_uptime(s["uptime"])}',
        ])
        for i in range(4):
            distance = s['dist'][i]
            txt = 'sin lectura' if distance is None else f'{distance:.1f} cm'
            if i == 0:
                lines.append(f'S1 Entrada: {txt}')
            else:
                lines.append(f'S{i+1} Plaza {i}: {txt}; ocupada={s["ocup"][i-1]}')
    lines.extend(['', 'DIAGNÓSTICO', *(f'- {x}' for x in notas), '', 'EVENTOS DE ESTA SESIÓN'])
    lines.extend(eventos or ['(sin eventos)'])
    lines.extend(['', 'ÚLTIMO REGISTRO DEL FIRMWARE', logs or '(sin registro)'])
    return '\n'.join(lines) + '\n'


def format_uptime(seconds):
    if seconds is None:
        return '—'
    days, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    return (f'{days}d ' if days else '') + f'{h:02d}:{m:02d}:{s:02d}'


def demo_state(t):
    phase = int(t / 5) % 5
    occup = [[False, False, False], [False, True, False], [True, True, False], [True, True, True], [False, True, False]][phase]
    entry = phase in (1, 2, 3)
    distances = [4.5 if entry else 14.0] + [8.2 + i if v else 29.4 + i for i, v in enumerate(occup)]
    d = {'equipo': 'parqueo-esp32', 'conectado': True, 'ip': '192.168.1.18',
         'arduino_conectado': True, 'wifi_sta_conectado': True,
         'senal_wifi_dbm': -59, 'tiempo_encendido_s': int(t),
         'plazas_total': 3, 'plazas_ocupadas': sum(occup), 'plazas_libres': 3-sum(occup),
         'parqueo_lleno': all(occup), 'vehiculo_entrada': entry, 'servo_disponible': True,
         'pluma': 'abierta' if entry and not all(occup) else 'cerrada',
         'lcd': 'controlada_por_arduino_uno', 'modo': 'automatico'}
    d.update({f'sensor{i+1}_cm': v for i, v in enumerate(distances)})
    d.update({f'plaza{i+1}_ocupada': v for i, v in enumerate(occup)})
    logs = f'[DEMO] Lecturas simuladas, no corresponden al hardware.\n[{int(t)}s] ' + ' | '.join(f'S{i+1}: {v:.1f} cm' for i,v in enumerate(distances)) + f'\n[{int(t)}s] OCUPADAS: {sum(occup)}/3 | LIBRES: {3-sum(occup)}\n[{int(t)}s] PLUMA {d["pluma"].upper()}'
    return d, logs, None


class MonitorParqueo:
    def __init__(self, root, demo=False, host=IP_INICIAL):
        self.root, self.demo = root, demo
        self.started = time.monotonic()
        self.root.title('Smart Parking V5')
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f'{min(1180, max(920, sw-90))}x{min(850, max(620, sh-100))}')
        self.root.minsize(830, 550)
        self.root.configure(bg=BG)
        self.ip = tk.StringVar(value=host)
        self.results = queue.Queue()
        self.action_results = queue.Queue()
        self.control_token = tk.StringVar(value='')  # Jamás guardar el token en disco.
        self.last_wifi_result = None
        self.running = False
        self.last_logs = None
        self.last_success = None
        self.active_host = host
        self.paused = False
        self.history = deque(maxlen=MAX_HISTORY)
        self.history_window = None
        self.history_canvas = None
        self.history_status = None
        self.last_history_status = None
        self.actual = None
        self.alerts = ['Esperando conexión con el ESP32.']
        self.events = deque(maxlen=MAX_EVENTS)
        self.prev_state = None
        self.online = False
        self.saved_host = cargar_host_guardado()
        self.scroll_area = None
        self._ui()
        self.root.after(100, self._drain)
        self.root.after(130, self._drain_actions)
        self.root.after(100, self._poll)

    def label(self, parent, txt='', size=11, color=TEXT, bold=False):
        return tk.Label(parent, text=txt, font=(FONT, size, 'bold' if bold else 'normal'), fg=color,
                        bg=parent.cget('bg'), anchor='w')

    def button(self, parent, txt, fn, primary=False):
        return tk.Button(parent, text=txt, command=fn, font=(FONT,10,'bold'),
                         bg='#2567b9' if primary else '#28394d', fg=TEXT,
                         activebackground='#3579c6', activeforeground='white', relief='flat',
                         padx=12, pady=6, cursor='hand2')

    def panel(self, parent, color=PANEL, px=13, py=10):
        return tk.Frame(parent, bg=color, padx=px, pady=py, highlightthickness=0)

    def stat_card(self, parent, col, title, subtitle):
        f=self.panel(parent)
        f.grid(row=0,column=col,sticky='nsew',padx=(0 if col==0 else 8,0))
        self.label(f,title,10,MUTED,True).pack(anchor='w')
        value=self.label(f,'—',25,TEXT,True); value.pack(anchor='w')
        self.label(f,subtitle,9,MUTED).pack(anchor='w')
        return value

    def _ui(self):
        container=tk.Frame(self.root,bg=BG); container.pack(fill='both',expand=True)
        canvas=tk.Canvas(container,bg=BG,highlightthickness=0)
        scrollbar=tk.Scrollbar(container,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right',fill='y'); canvas.pack(side='left',fill='both',expand=True)
        outer=tk.Frame(canvas,bg=BG,padx=24,pady=18)
        win=canvas.create_window((0,0),window=outer,anchor='nw')
        def resized(_ev): canvas.configure(scrollregion=canvas.bbox('all'))
        outer.bind('<Configure>',resized)
        canvas.bind('<Configure>',lambda ev: canvas.itemconfigure(win,width=ev.width))
        def wheel(ev):
            if isinstance(ev.widget, (tk.Text, tk.Listbox)):
                return
            if ev.num == 4: units = -3
            elif ev.num == 5: units = 3
            else: units = -int(ev.delta / 120) * 3
            canvas.yview_scroll(units,'units')
        self.root.bind_all('<MouseWheel>',wheel)
        self.root.bind_all('<Button-4>',wheel)
        self.root.bind_all('<Button-5>',wheel)
        self.scroll_area=canvas
        header=tk.Frame(outer,bg=BG); header.pack(fill='x')
        self.label(header,'SMART PARKING',24,TEXT,True).pack(side='left')
        self.connection=self.label(header,'●  SIN CONEXIÓN',11,AMBER,True); self.connection.pack(side='right')
        self.label(outer,'ESP32 + Arduino UNO  /  Tres plazas  /  Monitor V5 con configuración Wi-Fi',10,MUTED).pack(anchor='w',pady=(0,10))
        ctrl=self.panel(outer,px=12,py=8); ctrl.pack(fill='x')
        self.label(ctrl,'Dirección ESP32',10,MUTED).pack(side='left')
        ent=tk.Entry(ctrl,textvariable=self.ip,width=22,font=('Consolas',11),bg=PANEL2,fg=TEXT,insertbackground=TEXT,relief='flat')
        ent.pack(side='left',padx=10,ipady=6); ent.bind('<Return>',lambda _e:self._manual())
        self.button(ctrl,'Conectar',self._manual,True).pack(side='left')
        self.pause_btn=self.button(ctrl,'Pausar',self._toggle_pause); self.pause_btn.pack(side='left',padx=7)
        self.button(ctrl,'Diagnóstico',self._show_diagnostics).pack(side='left')
        self.refresh=self.label(ctrl,'Actualización: 1.7 s',10,MUTED); self.refresh.pack(side='right')
        netbar=self.panel(outer,px=12,py=7)
        netbar.pack(fill='x',pady=(7,0))
        self.button(netbar,'Configurar red Wi-Fi',self._show_wifi,True).pack(side='left')
        self.button(netbar,'Enviar instrucciones',self._show_commands).pack(side='left',padx=(8,0))
        self.button(netbar,'Buscar ESP32 en la red',self._discover).pack(side='left',padx=(8,0))
        self.button(netbar,'Usar IP de configuración',self._use_ap).pack(side='left',padx=(8,0))
        self.netstatus=self.label(netbar,'Red: por consultar',9,MUTED)
        self.netstatus.pack(side='right')
        self.alert_panel=self.panel(outer,color='#182d2b',px=13,py=10); self.alert_panel.pack(fill='x',pady=(9,0))
        self.alert_label=self.label(self.alert_panel,'●  Esperando telemetría...',11,GREEN,True); self.alert_label.pack(anchor='w')
        self.alert_detail=self.label(self.alert_panel,'El acceso y los LED solo se interpretan cuando los sensores tienen lecturas válidas.',9,MUTED); self.alert_detail.pack(anchor='w')
        if self.demo:
            self.label(outer,'MODO DEMOSTRACIÓN — datos simulados, no hay conexión al ESP32.',10,AMBER,True).pack(anchor='w',pady=(6,0))

        summary=tk.Frame(outer,bg=BG); summary.pack(fill='x',pady=(12,9))
        for i in range(4): summary.columnconfigure(i,weight=1,uniform='summary')
        self.total=self.stat_card(summary,0,'CAPACIDAD','Plazas del estacionamiento')
        self.occupied=self.stat_card(summary,1,'OCUPADAS','Vehículos estacionados')
        self.free=self.stat_card(summary,2,'DISPONIBLES','Espacios libres')
        self.access=self.stat_card(summary,3,'ACCESO','Estado del parqueo')

        self.label(outer,'ESTADO DE LAS PLAZAS',12,TEXT,True).pack(anchor='w',pady=(2,6))
        spaces=tk.Frame(outer,bg=BG); spaces.pack(fill='x')
        self.space_widgets=[]
        for i in range(3):
            spaces.columnconfigure(i,weight=1,uniform='spaces')
            f=self.panel(spaces,px=12,py=10); f.grid(row=0,column=i,sticky='nsew',padx=(0 if i==0 else 8,0))
            self.label(f,f'PLAZA {i+1}  ·  SENSOR {i+2}',10,MUTED,True).pack(anchor='w')
            status=self.label(f,'SIN DATOS',15,MUTED,True); status.pack(anchor='w',pady=(5,1))
            dist=self.label(f,'— cm',18,TEXT,True); dist.pack(anchor='w')
            led=tk.Canvas(f,width=130,height=27,bg=PANEL,highlightthickness=0); led.pack(anchor='w',pady=(3,0))
            g=led.create_oval(3,5,17,19,fill='#324b40',outline=''); r=led.create_oval(70,5,84,19,fill='#52383e',outline='')
            led.create_text(22,12,text='Verde',anchor='w',fill=MUTED,font=(FONT,8)); led.create_text(89,12,text='Rojo',anchor='w',fill=MUTED,font=(FONT,8))
            hint=self.label(f,'LED esperado: sin datos',9,MUTED); hint.pack(anchor='w')
            self.space_widgets.append((status,dist,led,g,r,hint))

        self.label(outer,'ENTRADA Y SISTEMA',12,TEXT,True).pack(anchor='w',pady=(11,6))
        controls=tk.Frame(outer,bg=BG); controls.pack(fill='x')
        for i in range(3): controls.columnconfigure(i,weight=1,uniform='control')
        f=self.panel(controls,px=12,py=9); f.grid(row=0,column=0,sticky='nsew')
        self.label(f,'SENSOR 1  ·  ENTRADA',10,MUTED,True).pack(anchor='w')
        self.entry_dist=self.label(f,'— cm',20,TEXT,True); self.entry_dist.pack(anchor='w')
        self.entry_state=self.label(f,'Sin datos',10,MUTED); self.entry_state.pack(anchor='w')
        f=self.panel(controls,px=12,py=9); f.grid(row=0,column=1,sticky='nsew',padx=8)
        self.label(f,'PLUMA DE ACCESO',10,MUTED,True).pack(anchor='w')
        self.gate=self.label(f,'—',20,TEXT,True); self.gate.pack(anchor='w')
        self.servo=self.label(f,'Servo: sin datos',10,MUTED); self.servo.pack(anchor='w')
        self.label(f,'Posición ordenada, no verificada',9,MUTED).pack(anchor='w')
        f=self.panel(controls,px=12,py=9); f.grid(row=0,column=2,sticky='nsew')
        self.label(f,'COMUNICACIÓN',10,MUTED,True).pack(anchor='w')
        self.arduino=self.label(f,'Arduino: —',13,MUTED,True); self.arduino.pack(anchor='w')
        self.wifi=self.label(f,'Wi-Fi: —',10,MUTED); self.wifi.pack(anchor='w')
        self.uptime=self.label(f,'Encendido: —',10,MUTED); self.uptime.pack(anchor='w')
        self.detail=self.label(outer,'LCD: —  |  Modo: —',10,MUTED); self.detail.pack(anchor='w',pady=(6,0))

        lh=tk.Frame(outer,bg=BG); lh.pack(fill='x',pady=(8,5))
        self.label(lh,'REGISTRO DE EVENTOS',12,TEXT,True).pack(side='left')
        self.button(lh,'Guardar registro',self._export).pack(side='right')
        self.button(lh,'Exportar reporte',self._export_report,True).pack(side='right',padx=7)
        self.button(lh,'Eventos locales',self._show_events).pack(side='right')
        self.button(lh,'Historial de sensores',self._show_history).pack(side='right',padx=7)
        self.logs_status=self.label(lh,'',9,MUTED); self.logs_status.pack(side='right',padx=9)
        logf=tk.Frame(outer,bg=PANEL2); logf.pack(fill='both',expand=True)
        sb=tk.Scrollbar(logf); sb.pack(side='right',fill='y')
        self.logs=tk.Text(logf,bg=PANEL2,fg='#b7e4cb',font=('Consolas',10),wrap='word',relief='flat',padx=12,pady=9,yscrollcommand=sb.set,state='disabled',height=5)
        self.logs.pack(fill='both',expand=True); sb.config(command=self.logs.yview)
        self.footer=self.label(outer,'Esperando primera respuesta…',10,MUTED); self.footer.pack(anchor='w',pady=(7,0))


    def _job(self, task, callback):
        """Trabajos de red fuera del hilo de Tkinter."""
        def worker():
            try:
                self.action_results.put((callback, task(), None))
            except Exception as error:
                self.action_results.put((callback, None, error))
        threading.Thread(target=worker, daemon=True).start()

    def _drain_actions(self):
        try:
            while True:
                callback, result, error = self.action_results.get_nowait()
                callback(result, error)
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(130, self._drain_actions)

    def _use_ap(self):
        self.ip.set(AP_CONFIG_IP)
        self._event('Seleccionada la dirección del AP de configuración 192.168.4.1')
        if not self.demo:
            self._manual()

    def _discover(self):
        if self.demo:
            messagebox.showinfo('Modo demostración', 'La búsqueda solo funciona al conectar el hardware real.')
            return
        self.netstatus.config(text='Buscando en la red local…', fg=AMBER)
        def result(data, error):
            if error:
                self.netstatus.config(text='Error al buscar', fg=RED)
                messagebox.showerror('Búsqueda de ESP32', str(error)); return
            if not data:
                self.netstatus.config(text='No se encontró ESP32', fg=AMBER)
                messagebox.showinfo('No encontrado', 'Conecta la PC al mismo hotspot que el ESP32, o a SmartParking-Setup (IP 192.168.4.1).\nSolo se inspecciona la subred local /24.')
                return
            if len(data) == 1:
                selected = data[0]['host']
            else:
                w=tk.Toplevel(self.root); w.title('ESP32 encontrados'); w.geometry('540x265'); w.configure(bg=BG)
                f=self.panel(w); f.pack(fill='both',expand=True)
                self.label(f,'Selecciona el ESP32 a utilizar',14,TEXT,True).pack(anchor='w')
                choices=[f"{d['host']}  |  Red: {d.get('ssid') or 'no informada'}" for d in data]
                box=ttk.Combobox(f,values=choices,state='readonly',width=65); box.pack(fill='x',pady=12); box.current(0)
                def apply():
                    value=data[box.current()]['host']
                    self.ip.set(value); self._manual(); w.destroy()
                self.button(f,'Usar este ESP32',apply,True).pack(anchor='w')
                self.netstatus.config(text=f'{len(data)} ESP32 encontrado(s)',fg=GREEN)
                return
            self.ip.set(selected)
            self.netstatus.config(text=f'ESP32 encontrado: {selected}',fg=GREEN)
            self._event('ESP32 encontrado en la IP: '+selected)
            self._manual()
        self._job(descubrir_esp32,result)

    def _show_wifi(self):
        if self.demo:
            messagebox.showinfo('Modo demo','Configurar red requiere un ESP32 con el firmware del proyecto.')
            return
        w=tk.Toplevel(self.root); w.title('Smart Parking | Configurar Wi-Fi del ESP32')
        w.geometry('720x570'); w.minsize(660,520); w.configure(bg=BG)
        outer=self.panel(w,px=23,py=18); outer.pack(fill='both',expand=True)
        self.label(outer,'CONFIGURAR RED DEL ESP32',17,TEXT,True).pack(anchor='w')
        instructions=('1. Conecta tu laptop a SmartParking-Setup (contraseña indicada en el firmware).\n'
                      '2. Usa la IP 192.168.4.1; escribe el token de control del firmware.\n'
                      '3. Indica el SSID y la contraseña de tu hotspot de 2.4 GHz.\n'
                      '4. Envía la configuración; después conecta la laptop a ese hotspot y pulsa Buscar ESP32.')
        tk.Label(outer,text=instructions,justify='left',wraplength=640,bg=PANEL,fg=MUTED,
                 font=(FONT,10),padx=12,pady=12).pack(fill='x',pady=(10,14))
        def field(label,var,hidden=False):
            self.label(outer,label,10,MUTED,True).pack(anchor='w',pady=(5,3))
            ent=tk.Entry(outer,textvariable=var,show='•' if hidden else '',bg=PANEL2,
                         fg=TEXT,insertbackground=TEXT,relief='flat',font=(FONT,11))
            ent.pack(fill='x',ipady=6)
            return ent
        host=tk.StringVar(value=self.ip.get())
        ssid=tk.StringVar(value='')
        pw=tk.StringVar(value='')
        field('IP actual del ESP32 (AP: 192.168.4.1)',host)
        field('Token de control (se define en el firmware ESP32)',self.control_token,True)
        networks=tk.Frame(outer,bg=PANEL); networks.pack(fill='x',pady=(9,0))
        self.label(networks,'Red / SSID del hotspot',10,MUTED,True).pack(side='left')
        self.button(networks,'Buscar redes Wi-Fi',lambda:self._wifi_scan(host.get(),combo,feedback,w)).pack(side='right')
        combo=ttk.Combobox(outer,textvariable=ssid,state='normal',width=65)
        combo.pack(fill='x',ipady=4)
        field('Contraseña del hotspot (mínimo 8 caracteres)',pw,True)
        feedback=tk.StringVar(value='Estado: todavía no consultado')
        self.label(outer,'CONFIRMACIÓN DEL ESP32',10,MUTED,True).pack(anchor='w',pady=(10,2))
        tk.Label(outer,textvariable=feedback,bg=PANEL,fg=GREEN,justify='left',anchor='w',
                 wraplength=620,padx=11,pady=7,font=(FONT,10)).pack(fill='x')
        buttons=tk.Frame(outer,bg=PANEL); buttons.pack(fill='x',pady=(12,0))
        self.button(buttons,'Consultar estado de red',lambda:self._wifi_status(host.get(),feedback,w)).pack(side='left')
        self.button(buttons,'GUARDAR Y CONECTAR HOTSPOT',lambda:self._wifi_save(host.get(),ssid.get(),pw.get(),feedback,w),True).pack(side='right')
        self._wifi_status(host.get(),feedback,w)

    def _wifi_status(self,host,feedback,window):
        feedback.set('Consultando si el ESP32 está conectado…')
        def done(data,error):
            if not window.winfo_exists(): return
            if error:
                feedback.set('Sin respuesta. Conecta la laptop al AP SmartParking-Setup o al hotspot. '+str(error)); return
            if data.get('equipo') != 'parqueo-esp32':
                feedback.set('La IP no pertenece al ESP32 del parqueo.'); return
            if data.get('sta_conectado') is True:
                feedback.set(f"CONECTADO a: {data.get('ssid')}  |  IP hotspot: {data.get('ip_sta')}  |  IP configuración: {data.get('ip_ap')}")
                self.netstatus.config(text='Hotspot: conectado',fg=GREEN)
            else:
                feedback.set(f"Sin conexión al hotspot. Red guardada: {data.get('ssid') or 'ninguna'}  |  AP: {data.get('ip_ap')}")
                self.netstatus.config(text='Solo AP de configuración',fg=AMBER)
            self.last_wifi_result=data
        self._job(lambda:api_json(host,'/api/wifi/status'),done)

    def _wifi_scan(self,host,combo,feedback,window):
        feedback.set('Solicitando escaneo de redes al ESP32…')
        def done(data,error):
            if not window.winfo_exists(): return
            if error:
                feedback.set('No fue posible buscar redes. '+str(error)); return
            if data.get('pendiente'):
                feedback.set('Escaneo en curso; vuelve a pulsar Buscar redes Wi-Fi en unos segundos.')
                return
            names=sorted({x.get('ssid') for x in data.get('redes',[]) if isinstance(x,dict) and x.get('ssid')})
            combo.configure(values=names)
            feedback.set(f'{len(names)} redes detectadas por el ESP32. Selecciona una o escribe el SSID manualmente.')
        self._job(lambda:api_json(host,'/api/wifi/scan'),done)

    def _wifi_save(self,host,ssid,password,feedback,window):
        try:
            validar_wifi(ssid,password)
            if not self.control_token.get().strip():
                raise ValueError('El token de control del ESP32 es obligatorio.')
        except ValueError as error:
            messagebox.showerror('Datos Wi-Fi',str(error),parent=window); return
        if not messagebox.askyesno('Cambiar red Wi-Fi',
             f'¿Guardar la red {ssid} en el ESP32? Podría cambiar su IP. No se guardará la contraseña en la app.',parent=window):
            return
        feedback.set('Enviando credenciales por la red local…')
        token=self.control_token.get().strip()
        def done(data,error):
            if not window.winfo_exists(): return
            if error:
                feedback.set('No se confirmó la recepción: '+str(error)); return
            if data.get('aceptado') is True:
                feedback.set('RECIBIDO: credenciales guardadas por el ESP32. Espera la conexión, vuelve a consultar estado y después busca la nueva IP.')
                self._event('ESP32 confirmó recepción de una nueva configuración Wi-Fi (sin guardar clave)')
                self.netstatus.config(text='Nueva red enviada; verificar conexión',fg=AMBER)
            else:
                feedback.set('RECHAZADO por ESP32: '+str(data.get('detalle') or data.get('_http_status')))
        self._job(lambda:api_json(host,'/api/wifi/config',{'ssid':ssid,'password':password},token),done)

    def _show_commands(self):
        if self.demo:
            messagebox.showinfo('Modo demo','Los comandos reales están desactivados en modo demostración.')
            return
        w=tk.Toplevel(self.root); w.title('Smart Parking | Enviar órdenes al ESP32')
        w.geometry('680x390'); w.configure(bg=BG)
        f=self.panel(w,px=22,py=17); f.pack(fill='both',expand=True)
        self.label(f,'CONTROL REMOTO — MAQUETA',17,TEXT,True).pack(anchor='w')
        self.label(f,'Las órdenes requieren token. La respuesta confirma el procesamiento lógico, NO el movimiento físico.',10,MUTED).pack(anchor='w',pady=(2,11))
        self.label(f,'IP del ESP32',10,MUTED,True).pack(anchor='w')
        host=tk.StringVar(value=self.ip.get())
        tk.Entry(f,textvariable=host,bg=PANEL2,fg=TEXT,insertbackground=TEXT,relief='flat').pack(fill='x',ipady=5)
        self.label(f,'Token de control del firmware',10,MUTED,True).pack(anchor='w',pady=(7,2))
        tk.Entry(f,textvariable=self.control_token,show='•',bg=PANEL2,fg=TEXT,insertbackground=TEXT,relief='flat').pack(fill='x',ipady=5)
        opts=comandos_permitidos()
        self.label(f,'Seleccionar instrucción',10,MUTED,True).pack(anchor='w',pady=(10,2))
        selected=tk.StringVar(value='ping')
        combo=ttk.Combobox(f,state='readonly',values=[f'{key} — {label}' for key,label in opts.items()],width=65)
        combo.pack(fill='x',ipady=3); combo.current(0)
        feedback=tk.StringVar(value='Selecciona una instrucción y pulsa Enviar.')
        tk.Label(f,textvariable=feedback,bg=PANEL2,fg=GREEN,wraplength=590,justify='left',padx=10,pady=8).pack(fill='x',pady=(12,9))
        self.button(f,'ENVIAR INSTRUCCIÓN',lambda:self._send_command(host.get(),list(opts)[combo.current()],feedback,w),True).pack(anchor='e')

    def _send_command(self,host,accion,feedback,window):
        if not self.control_token.get().strip():
            messagebox.showerror('Control','Escribe el token de control.',parent=window); return
        if accion in ('abrir','cerrar') and not messagebox.askyesno('Confirmación de movimiento',
             'La pluma de la maqueta puede moverse. Verifica que esté despejada y supervisa la prueba. ¿Enviar la orden?',parent=window):
            return
        ident=uuid.uuid4().hex[:12]
        token=self.control_token.get().strip()
        feedback.set(f'Enviando {accion}, ID {ident}…')
        def done(data,error):
            if not window.winfo_exists(): return
            if error:
                feedback.set('No se recibió confirmación: '+str(error)); return
            if data.get('id') != ident or data.get('recibido') is not True:
                feedback.set('Respuesta no confirmada: identificador incorrecto o firmware anterior.'); return
            status='ACEPTADA' if data.get('ejecutado') is True else 'BLOQUEADA'
            feedback.set(f"Orden {status} por ESP32. ID: {ident}\n{data.get('detalle','sin detalle')}")
            self._event(f'Orden remota {accion}: {status}; ID {ident}')
            self._manual()
        self._job(lambda:api_json(host,'/api/comando',{'accion':accion,'id':ident},token),done)

    def _manual(self):
        self.paused=False; self.pause_btn.config(text='Pausar')
        self._request()

    def _toggle_pause(self):
        self.paused=not self.paused
        self.pause_btn.config(text='Reanudar' if self.paused else 'Pausar')
        if self.paused:
            self._unknown('●  PAUSADO',AMBER,'Actualización pausada. Los valores ya no son actuales.')
        else:
            self._request()

    def _request(self):
        if self.running: return
        host=self.ip.get().strip()
        if host != self.active_host:
            self.active_host=host; self.last_success=None; self.last_logs=None
            self.history.clear(); self.last_history_status=None; self._draw_history()
            self.prev_state=None; self.actual=None
            self._event('Dirección de conexión cambiada: '+host)
            self._set_logs('')
            self._unknown('●  CONECTANDO',AMBER,'Consultando nueva dirección…')
        self.running=True
        def worker():
            try:
                values=demo_state(time.monotonic()-self.started) if self.demo else consultar_esp32(host)
                self.results.put((host,True,values))
            except Exception as exc:
                self.results.put((host,False,str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def _poll(self):
        if not self.paused: self._request()
        self.root.after(INTERVAL,self._poll)

    def _drain(self):
        try:
            while True:
                host,ok,result=self.results.get_nowait(); self.running=False
                if self.paused: continue
                if host != self.ip.get().strip():
                    self._request(); continue
                if ok:
                    try: self._display(*result)
                    except Exception as exc: self._unknown('●  ERROR DE DATOS',RED,str(exc))
                else:
                    self._unknown('●  SIN CONEXIÓN',RED,'No se pudo consultar: '+result[:150])
        except queue.Empty: pass
        self.root.after(100,self._drain)

    def _set_logs(self, content):
        at_bottom = self.logs.yview()[1] >= 0.98
        top = self.logs.yview()[0]
        self.logs.config(state='normal'); self.logs.delete('1.0','end'); self.logs.insert('end',content or '(No hay mensajes)')
        if at_bottom: self.logs.see('end')
        else: self.logs.yview_moveto(top)
        self.logs.config(state='disabled')

    def _space(self,i,state,distance,installed=True):
        status,dist,led,g,r,hint=self.space_widgets[i]
        txt,col=('OCUPADA',RED) if state is True else ('LIBRE',GREEN) if state is False else ('SIN LECTURA',AMBER) if installed else ('PENDIENTE',MUTED)
        status.config(text=txt,fg=col)
        dist.config(text=f'{distance:.1f} cm' if distance is not None else '— cm')
        led.itemconfig(g,fill=GREEN if state is False else '#324b40')
        led.itemconfig(r,fill=RED if state is True else '#52383e')
        hint.config(text='LED esperado: ROJO' if state is True else 'LED esperado: VERDE' if state is False else 'LED esperado: APAGADOS',fg=col)

    def _unknown(self,title,color,detail):
        self.connection.config(text=title,fg=color)
        self.netstatus.config(text='Sin telemetría actual',fg=AMBER)
        self.actual=None
        if self.online:
            self._event('Conexión de telemetría interrumpida: '+title.removeprefix('●  '))
        self.online=False
        self.alerts=[detail]
        self._set_diagnostic('error' if color == RED else 'warning',title.removeprefix('●  '),detail)
        self._record_history(None,title.removeprefix('●  '))
        for w in (self.total,self.occupied,self.free,self.access,self.entry_dist,self.gate): w.config(text='—',fg=MUTED)
        for i in range(3): self._space(i,None,None)
        for w,txt in ((self.entry_state,'Sin datos actuales'),(self.servo,'Servo: sin datos'),(self.arduino,'Arduino: —'),(self.wifi,'Wi-Fi: —'),(self.uptime,'Encendido: —'),(self.detail,'LCD: —  |  Modo: —')): w.config(text=txt,fg=MUTED)
        self.logs_status.config(text='Registro anterior' if self.last_logs else 'Sin registro',fg=AMBER)
        last=self.last_success.strftime('%H:%M:%S') if self.last_success else '—'
        self.footer.config(text=f'{detail}  |  Última lectura válida: {last}',fg=color)

    def _display(self,raw,logs,log_error):
        s=normalizar(raw); self.last_success=datetime.now()
        self.actual=s
        if s['wifi'] is False:
            self._unknown('●  SIN WI-FI',RED,'El equipo informa que no está conectado.'); return
        self.connection.config(text='●  DEMOSTRACIÓN' if self.demo else '●  ESP32 EN LÍNEA',fg=AMBER if self.demo else GREEN)
        # El firmware informa la conexión STA al hotspot y el estado del AP.
        sta = raw.get('wifi_sta_conectado')
        if sta is True:
            self.netstatus.config(text='Hotspot: conectado',fg=GREEN)
        elif sta is False:
            self.netstatus.config(text='Solo red de configuración',fg=AMBER)
        else:
            self.netstatus.config(text='Red: firmware anterior',fg=MUTED)
        if not self.demo and self.ip.get().strip() != self.saved_host:
            try:
                guardar_host(self.ip.get().strip())
                self.saved_host = self.ip.get().strip()
            except (OSError, ValueError):
                pass
        self._track_events(s)
        self.online=True
        severity, title, notes = diagnosticar(s)
        self.alerts=notes
        self._set_diagnostic(severity,title,notes[0])
        self._record_history(s)
        self.total.config(text=str(s['total']) if s['total'] is not None else '—',fg=TEXT)
        self.occupied.config(text=str(s['ocupadas']) if s['ocupadas'] is not None else '—',fg=RED if s['ocupadas'] else TEXT)
        self.free.config(text=str(s['libres']) if s['libres'] is not None else '—',fg=GREEN if s['libres'] else TEXT)
        # Estado de disponibilidad, no una confirmación de paso físico.
        if s['arduino'] is not True or s['ocupadas'] is None or s['entrada'] is None:
            access,ac='SIN DATOS',AMBER
        elif s['ocupadas']==3:
            access,ac='LLENO',RED
        elif s['servo'] is False or s['pluma']=='error':
            access,ac='ERROR',RED
        else: access,ac='DISPONIBLE',GREEN
        self.access.config(text=access,fg=ac,font=(FONT,15,'bold'))
        for i in range(3):
            self._space(i,s['ocup'][i],s['dist'][i+1],f'sensor{i+2}_cm' in raw)
        self.entry_dist.config(text=f"{s['dist'][0]:.1f} cm" if s['dist'][0] is not None else '— cm',fg=TEXT)
        v=s['entrada']; self.entry_state.config(text='Vehículo detectado' if v is True else 'Entrada despejada' if v is False else 'Sin lectura válida',fg=GREEN if v is True else MUTED if v is False else AMBER)
        gate=s['pluma']; gt={'abierta':'ABIERTA','cerrada':'CERRADA','error':'ERROR','sin_instalar':'PENDIENTE','en_prueba':'EN PRUEBA'}.get(gate,'—')
        self.gate.config(text=gt,fg=GREEN if gate=='abierta' else RED if gate=='error' else TEXT)
        self.servo.config(text='Servo: inicializado' if s['servo'] is True else 'Servo: no disponible' if s['servo'] is False else 'Servo: sin confirmar',fg=GREEN if s['servo'] is True else AMBER)
        a=s['arduino']; self.arduino.config(text='Arduino: conectado' if a is True else 'Arduino: desconectado' if a is False else 'Arduino: sin confirmar',fg=GREEN if a is True else RED if a is False else AMBER)
        self.wifi.config(text=f"Wi-Fi: {s['rssi']:g} dBm" if s['rssi'] is not None else 'Wi-Fi: sin dato',fg=MUTED)
        self.uptime.config(text='Encendido: '+format_uptime(s['uptime']),fg=MUTED)
        lcd={'controlada_por_arduino_uno':'controlada por UNO','conectada':'detectada','no_detectada':'no detectada'}.get(s['lcd'],'sin dato')
        self.detail.config(text=f"LCD: {lcd}  |  Modo: {str(s['modo'] or 'sin dato').replace('_',' ')}  |  Equipo: {s['equipo'] or 'ESP32'}",fg=MUTED)
        if log_error:
            self.logs_status.config(text='Error al consultar registro',fg=AMBER)
        else:
            self.logs_status.config(text='Actualizado',fg=MUTED)
            if logs != self.last_logs:
                self.last_logs=logs; self._set_logs(logs)
        self.footer.config(text=f"Última lectura: {self.last_success:%H:%M:%S}  |  ESP32: {s['ip'] or self.active_host}  |  {'SIMULADO' if self.demo else 'Red local'}",fg=MUTED)

    def _set_diagnostic(self, severity, title, detail):
        bg,fg = {'ok':('#182d2b',GREEN),'warning':('#352e21',AMBER),'error':('#392329',RED)}.get(severity,('#352e21',AMBER))
        self.alert_panel.config(bg=bg)
        self.alert_label.config(bg=bg,fg=fg,text=('●  ' + title))
        self.alert_detail.config(bg=bg,text=detail if len(detail) < 185 else detail[:182]+'…')

    def _event(self, msg):
        self.events.append(f'{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}')

    def _track_events(self, s):
        prev=self.prev_state
        if prev is None:
            self._event('ESP32 accesible; monitoreo activo' + (' (demostración)' if self.demo else ''))
        else:
            if not self.online:
                self._event('Conexión de telemetría recuperada')
            if prev['arduino'] != s['arduino']:
                self._event('Arduino UNO: ' + ('CONECTADO' if s['arduino'] is True else 'DESCONOCIDO' if s['arduino'] is None else 'DESCONECTADO'))
            for i in range(3):
                if prev['ocup'][i] != s['ocup'][i]:
                    value=s['ocup'][i]
                    self._event(f'Plaza {i+1}: ' + ('OCUPADA (LED rojo esperado)' if value is True else 'LIBRE (LED verde esperado)' if value is False else 'SIN LECTURA'))
            if prev['pluma'] != s['pluma']:
                self._event('Pluma ordenada: '+str(s['pluma']).upper())
            if prev['entrada'] != s['entrada']:
                self._event('Entrada: ' + ('VEHÍCULO DETECTADO' if s['entrada'] is True else 'DESPEJADA' if s['entrada'] is False else 'SIN LECTURA'))
            if prev['lleno'] != s['lleno'] and s['lleno'] is True:
                self._event('ALERTA: Estacionamiento lleno (3/3)')
        self.prev_state=s

    def _show_diagnostics(self):
        w=tk.Toplevel(self.root); w.title('Smart Parking | Diagnóstico'); w.geometry('800x390'); w.configure(bg=BG)
        f=tk.Frame(w,bg=BG,padx=22,pady=16); f.pack(fill='both',expand=True)
        self.label(f,'DIAGNÓSTICO DEL SISTEMA',18,TEXT,True).pack(anchor='w')
        self.label(f,'Interpretación de datos recibidos. No sustituye la revisión física del circuito.',10,MUTED).pack(anchor='w',pady=(1,12))
        txt=tk.Text(f,bg=PANEL2,fg=TEXT,font=(FONT,11),wrap='word',padx=14,pady=12,relief='flat')
        txt.pack(fill='both',expand=True)
        lines=['ESTADO ACTUAL',*(f'• {item}' for item in self.alerts),'',
               'MAPA DE CONEXIÓN DE LED',
               'Plaza 1: verde GPIO25 / rojo GPIO26',
               'Plaza 2: verde GPIO27 / rojo GPIO32',
               'Plaza 3: verde GPIO33 / rojo GPIO23',
               'Cada LED: GPIO → resistencia 330 Ω → ánodo LED → cátodo GND.',
               '', 'Los LED muestran órdenes lógicas, no confirmación del encendido físico.',
               'La posición de pluma se reporta como orden PWM, no confirmación mecánica.']
        txt.insert('1.0','\n'.join(lines)); txt.config(state='disabled')

    def _show_events(self):
        w=tk.Toplevel(self.root); w.title('Smart Parking | Eventos locales'); w.geometry('850x470'); w.configure(bg=BG)
        f=tk.Frame(w,bg=BG,padx=18,pady=16); f.pack(fill='both',expand=True)
        self.label(f,'EVENTOS DE ESTA SESIÓN',17,TEXT,True).pack(anchor='w')
        self.label(f,'Cambios observados mediante consultas HTTP; no son eventos certificados del hardware.',10,MUTED).pack(anchor='w',pady=(0,9))
        txt=tk.Text(f,bg=PANEL2,fg='#b7e4cb',font=('Consolas',10),wrap='word',padx=12,pady=12,relief='flat')
        txt.pack(fill='both',expand=True)
        txt.insert('1.0','\n'.join(self.events) or '(Todavía no hay eventos)'); txt.config(state='disabled')

    def _export_report(self):
        path=filedialog.asksaveasfilename(defaultextension='.txt',initialfile=f'SmartParking_reporte_{datetime.now():%Y%m%d_%H%M%S}.txt',filetypes=[('Texto UTF-8','*.txt')])
        if not path: return
        try:
            out=texto_reporte(self.actual,self.alerts,list(self.events),self.last_logs)
            Path(path).write_text(out,encoding='utf-8')
        except OSError as exc:
            messagebox.showerror('Error al exportar',str(exc))
        else:
            messagebox.showinfo('Smart Parking','Reporte de diagnóstico guardado correctamente.')

    def _record_history(self, state=None, status='ok'):
        # Una sola marca por episodio de desconexión; no unir trazos a través de huecos.
        if state is None and status == self.last_history_status:
            return
        self.last_history_status = status
        row = history_row(datetime.now(), 'DEMO' if self.demo else self.active_host, state, status)
        self.history.append(row)
        self._draw_history()

    def _show_history(self):
        if self.history_window is not None and self.history_window.winfo_exists():
            self.history_window.lift(); return
        w = tk.Toplevel(self.root); self.history_window = w
        w.title('Smart Parking | Historial de sensores'); w.geometry('920x500'); w.minsize(650,380); w.configure(bg=BG)
        outer = tk.Frame(w,bg=BG,padx=18,pady=15); outer.pack(fill='both',expand=True)
        head = tk.Frame(outer,bg=BG); head.pack(fill='x')
        self.label(head,'HISTORIAL DE DISTANCIAS',17,TEXT,True).pack(side='left')
        self.button(head,'Exportar CSV',self._export_history,True).pack(side='right')
        self.label(outer,'Últimos 5 minutos · centímetros · los huecos indican ausencia de lectura',10,MUTED).pack(anchor='w',pady=(3,8))
        legend = tk.Frame(outer,bg=BG); legend.pack(fill='x')
        for i,(name,color) in enumerate(zip(('S1 Entrada','S2 Plaza 1','S3 Plaza 2','S4 Plaza 3'),(BLUE,GREEN,AMBER,RED))):
            self.label(legend,'● '+name,11,color,True).pack(side='left',padx=(0,17))
        self.history_canvas = tk.Canvas(outer,bg=PANEL2,highlightthickness=0); self.history_canvas.pack(fill='both',expand=True,pady=(8,6))
        self.history_canvas.bind('<Configure>',lambda _e:self._draw_history())
        self.history_status = self.label(outer,'Sin muestras todavía',10,MUTED); self.history_status.pack(anchor='w')
        def close():
            self.history_window=None; self.history_canvas=None; self.history_status=None; w.destroy()
        w.protocol('WM_DELETE_WINDOW',close)
        self._draw_history()

    def _draw_history(self):
        c = self.history_canvas
        if c is None or not c.winfo_exists(): return
        c.delete('all')
        W,H=c.winfo_width(),c.winfo_height()
        if W<100 or H<100: return
        end=datetime.now().timestamp(); start=end-300
        rows=[(datetime.fromisoformat(r[0]).timestamp(),r) for r in self.history]
        rows=[(t,r) for t,r in rows if t>=start]
        values=[v for _,r in rows for v in r[2:6] if v is not None]
        ymax=max(40, math.ceil(max(values,default=40)/20)*20)
        left,right,top,bottom=55,W-18,18,H-32
        def x(t): return left+(right-left)*max(0,min(1,(t-start)/300))
        def y(v): return bottom-(bottom-top)*v/ymax
        for j in range(5):
            value=ymax*j/4; yy=y(value)
            c.create_line(left,yy,right,yy,fill='#2c4055')
            c.create_text(left-8,yy,text=f'{value:g}',anchor='e',fill=MUTED,font=(FONT,9))
        for j in range(6):
            xx=x(start+60*j)
            c.create_text(xx,bottom+15,text='Ahora' if j==5 else f'-{5-j}m',fill=MUTED,font=(FONT,9))
        if not values: c.create_text((left+right)/2,(top+bottom)/2,text='Sin lecturas válidas',fill=MUTED,font=(FONT,13))
        for i,color in enumerate((BLUE,GREEN,AMBER,RED)):
            prev=None
            for t,r in rows:
                v=r[2+i]
                if v is None:
                    prev=None; continue
                xx,yy=x(t),y(v)
                if prev and t-prev[0] <= 10:
                    c.create_line(prev[1],prev[2],xx,yy,fill=color,width=2)
                c.create_oval(xx-2,yy-2,xx+2,yy+2,fill=color,outline='')
                prev=(t,xx,yy)
        self.history_status.config(text=f'{len(self.history)} muestras guardadas en esta sesión (máximo {MAX_HISTORY}). Exporta CSV antes de cerrar.' + ('  |  DEMOSTRACIÓN' if self.demo else ''))

    def _export_history(self):
        if not self.history:
            messagebox.showinfo('Historial','Todavía no hay muestras.',parent=self.history_window); return
        name=filedialog.asksaveasfilename(parent=self.history_window,defaultextension='.csv',initialfile=f'parqueo_historial_{datetime.now():%Y%m%d_%H%M%S}.csv',filetypes=[('CSV','*.csv')])
        if name:
            try: export_history(name,list(self.history))
            except OSError as exc: messagebox.showerror('Error al guardar',str(exc),parent=self.history_window)
            else: messagebox.showinfo('Historial','Archivo CSV guardado.',parent=self.history_window)

    def _export(self):
        if self.last_logs is None:
            messagebox.showinfo('Registro','Todavía no hay mensajes para guardar.'); return
        name=filedialog.asksaveasfilename(defaultextension='.txt',initialfile=f'parqueo_eventos_{datetime.now():%Y%m%d_%H%M%S}.txt',filetypes=[('Texto UTF-8','*.txt')])
        if name:
            try: Path(name).write_text(self.last_logs,encoding='utf-8')
            except OSError as exc: messagebox.showerror('Error al guardar',str(exc))
            else: messagebox.showinfo('Registro','Registro guardado correctamente.')


def main():
    parser=argparse.ArgumentParser(description='Monitor Smart Parking ESP32')
    parser.add_argument('--demo',action='store_true',help='Mostrar datos simulados, sin hardware')
    parser.add_argument('--host',default=cargar_host_guardado(),help='IP o nombre del ESP32')
    args=parser.parse_args()
    root=tk.Tk(); MonitorParqueo(root,args.demo,args.host); root.mainloop()


if __name__=='__main__': main()
