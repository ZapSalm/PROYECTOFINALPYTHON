"""Pruebas locales sin conectar un ESP32 real."""
import unittest
import json
import threading
import tempfile
import csv
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from monitor_parqueo import consultar_esp32, normalizar, demo_state, base_url, format_uptime, history_row, export_history, HISTORY_COLUMNS, diagnosticar, texto_reporte, guardar_host, cargar_host_guardado

class Api(BaseHTTPRequestHandler):
    def do_GET(self):
        estado, logs, _ = demo_state(6)
        if self.path == '/api/estado':
            data = json.dumps(estado).encode(); kind='application/json'
        elif self.path == '/api/logs':
            data = logs.encode(); kind='text/plain'
        else:
            self.send_error(404); return
        self.send_response(200); self.send_header('Content-Type',kind); self.end_headers(); self.wfile.write(data)
    def log_message(self,*args): pass

class TestMonitor(unittest.TestCase):
    def test_mock_http(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Api)
        t=threading.Thread(target=server.serve_forever,daemon=True); t.start()
        try:
            raw, logs, error=consultar_esp32(f'127.0.0.1:{server.server_port}')
            data=normalizar(raw)
            self.assertEqual(data['ocup'],[False,True,False]); self.assertEqual(data['libres'],2)
            self.assertEqual(data['dist'][0],4.5); self.assertTrue(data['entrada']); self.assertEqual(data['pluma'],'abierta')
            self.assertIn('DEMO',logs); self.assertIsNone(error)
        finally: server.shutdown(); server.server_close(); t.join()
    def test_full(self):
        raw,_,_=demo_state(16); s=normalizar(raw)
        self.assertEqual(s['ocupadas'],3); self.assertEqual(s['libres'],0); self.assertTrue(s['lleno']); self.assertEqual(s['pluma'],'cerrada')
    def test_missing_sensor(self):
        raw,_,_=demo_state(6); raw['sensor3_cm']=None
        s=normalizar(raw); self.assertIsNone(s['ocup'][1]); self.assertIsNone(s['libres']); self.assertIsNone(s['ocupadas'])
    def test_old_firmware(self):
        raw,_,_=demo_state(6)
        for k in ['sensor3_cm','sensor4_cm','plaza2_ocupada','plaza3_ocupada']: raw.pop(k)
        s=normalizar(raw); self.assertEqual(s['ocup'],[False,None,None]); self.assertIsNone(s['libres'])
    def test_disconnected_arduino(self):
        raw,_,_=demo_state(6); raw['arduino_conectado']=False
        s=normalizar(raw); self.assertEqual(s['dist'],[None]*4); self.assertEqual(s['ocup'],[None]*3); self.assertIsNone(s['libres'])
    def test_inconsistent(self):
        raw,_,_=demo_state(6); raw['plazas_libres']=3
        self.assertIsNone(normalizar(raw)['libres'])
    def test_url(self):
        self.assertEqual(base_url('192.168.1.18'),'http://192.168.1.18'); self.assertEqual(base_url('http://parqueo-esp32.local/'),'http://parqueo-esp32.local')
        for bad in ('', 'https://example.com','http://a@b','http://a/path'):
            with self.assertRaises(ValueError): base_url(bad)
    def test_history_csv(self):
        raw,_,_=demo_state(6)
        row=history_row(datetime(2026,11,13,17,37),'DEMO',normalizar(raw))
        gap=history_row(datetime(2026,11,13,17,38),'DEMO',None,'SIN CONEXIÓN')
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'datos.csv'; export_history(path,[row,gap])
            with path.open(encoding='utf-8-sig',newline='') as f: data=list(csv.reader(f))
        self.assertEqual(tuple(data[0]),HISTORY_COLUMNS)
        self.assertEqual(data[1][2],'4.5'); self.assertEqual(data[2][2],''); self.assertEqual(data[2][-1],'SIN CONEXIÓN')
    def test_uptime(self): self.assertEqual(format_uptime(90061),'1d 01:01:01')


    def test_diagnostico_correcto(self):
        s=normalizar(demo_state(0)[0]); severity, title, notes=diagnosticar(s)
        self.assertEqual(severity, 'ok')
        self.assertIn('sin alertas',title)

    def test_diagnostico_errores_sensores(self):
        raw,_,_=demo_state(0)
        raw['sensor4_cm']=None
        s=normalizar(raw)
        level,_,notes=diagnosticar(s)
        self.assertEqual(level,'error')
        self.assertTrue(any('S4' in x for x in notes))
        self.assertTrue(any('LED' in x for x in notes))

    def test_diagnostico_lleno(self):
        s=normalizar(demo_state(16)[0]); level,_,notes=diagnosticar(s)
        self.assertEqual(level,'warning')
        self.assertTrue(any('LLENO' in x for x in notes))

    def test_diagnostico_servo(self):
        raw,_,_=demo_state(0); raw['servo_disponible']=False; raw['pluma']='error'
        level,_,notes=diagnosticar(normalizar(raw))
        self.assertEqual(level,'error')
        self.assertTrue(any('GPIO18' in x for x in notes))

    def test_reporte_completo(self):
        s=normalizar(demo_state(6)[0])
        out=texto_reporte(s,['Sin avisos'],['Plaza 2: ocupada'],'EVENTO',datetime(2026,11,21,18,25))
        for text in ('2026-11-21 18:25','S4 Plaza 3','Plaza 2: ocupada','EVENTO','NO confirmación física'):
            self.assertIn(text,out)

    def test_guardar_config(self):
        import json
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'config.json'; guardar_host('192.168.1.18',p)
            self.assertEqual(json.loads(p.read_text())['host'],'192.168.1.18')
            with self.assertRaises(ValueError): guardar_host('https://ejemplo.com',p)
            self.assertEqual(json.loads(p.read_text())['host'],'192.168.1.18')

    def test_error_rssi(self):
        raw,_,_=demo_state(0); raw['senal_wifi_dbm']=-88
        severity,_,notes=diagnosticar(normalizar(raw))
        self.assertEqual(severity,'warning')
        self.assertTrue(any('Wi-Fi' in x for x in notes))

    def test_sensor_falso_no_libre(self):
        raw,_,_=demo_state(0); raw['plaza1_ocupada']=False; raw['sensor2_cm']=-1
        state=normalizar(raw)
        self.assertIsNone(state['ocup'][0]); self.assertIsNone(state['libres'])

if __name__=='__main__': unittest.main(verbosity=2)

