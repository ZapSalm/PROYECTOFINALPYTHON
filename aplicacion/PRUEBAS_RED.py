"""Pruebas locales de provisión y respuestas. No requieren ESP32 real."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
from monitor_parqueo import api_json, validar_wifi, comandos_permitidos, descubrir_esp32, base_url

TOKEN = 'token-de-prueba-123'
class Handler(BaseHTTPRequestHandler):
    status = {'equipo':'parqueo-esp32', 'sta_conectado':False, 'ssid':'', 'ip_ap':'192.168.4.1', 'ip_sta':None, 'pendiente':False}
    log = []
    def do_GET(self):
        if self.path == '/api/wifi/status':
            payload=self.status; code=200
        elif self.path == '/api/wifi/scan':
            payload={'pendiente':False,'redes':[{'ssid':'Hotspot del parqueo','rssi':-55}]}; code=200
        else:
            payload={'error':'unknown'}; code=404
        self.reply(code,payload)
    def do_POST(self):
        body=self.rfile.read(int(self.headers.get('Content-Length','0')))
        fields={k:v[0] for k,v in parse_qs(body.decode('utf-8')).items()}
        if self.headers.get('X-Control-Token') != TOKEN:
            self.reply(403, {'aceptado':False,'detalle':'Token de control incorrecto'});return
        self.log.append((self.path, fields.copy()))
        if self.path == '/api/wifi/config':
            type(self).status=dict(self.status,ssid=fields.get('ssid'),sta_conectado=True,ip_sta='192.168.43.99')
            self.reply(202, {'aceptado':True,'detalle':'Guardado'});return
        if self.path == '/api/comando':
            ok = fields.get('accion') in ('ping','led_verde','led_rojo')
            self.reply(200 if ok else 409,{'recibido':True,'ejecutado':ok,'id':fields.get('id'),'accion':fields.get('accion'),'detalle':'OK' if ok else 'Bloqueada'});return
        self.reply(404,{'error':'unknown'})
    def reply(self,code,value):
        data=json.dumps(value).encode()
        self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def log_message(self,*args): pass

class TestRed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.host='127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def test_01_red_estado(self):
        v=api_json(self.host,'/api/wifi/status')
        self.assertEqual(v['equipo'],'parqueo-esp32');self.assertEqual(v['ip_ap'],'192.168.4.1')
    def test_02_lista_redes(self):
        v=api_json(self.host,'/api/wifi/scan')
        self.assertEqual(v['redes'][0]['ssid'],'Hotspot del parqueo')
    def test_03_cambio_red(self):
        v=api_json(self.host,'/api/wifi/config',{'ssid':'Mi Hotspot','password':'clave-super-segura'},TOKEN)
        self.assertEqual(v['_http_status'],202)
        self.assertTrue(v['aceptado'])
        self.assertEqual(api_json(self.host,'/api/wifi/status')['ssid'],'Mi Hotspot')
    def test_04_token_incorrecto(self):
        v=api_json(self.host,'/api/wifi/config',{'ssid':'Mala','password':'abcdefghi'},'incorrecto')
        self.assertEqual(v['_http_status'],403)
        self.assertFalse(v['aceptado'])
    def test_05_ack_identificador(self):
        v=api_json(self.host,'/api/comando',{'accion':'ping','id':'abc123'},TOKEN)
        self.assertEqual(v['id'],'abc123')
        self.assertTrue(v['ejecutado'])
    def test_06_orden_bloqueada(self):
        v=api_json(self.host,'/api/comando',{'accion':'cerrar','id':'xyz890'},TOKEN)
        self.assertEqual(v['_http_status'],409)
        self.assertTrue(v['recibido']);self.assertFalse(v['ejecutado'])
    def test_07_validacion_credenciales(self):
        self.assertEqual(validar_wifi('Mi punto','12345678'),('Mi punto','12345678'))
        for ssid,pw in [('', '12345678'),('a'*33,'12345678'),('wifi','1234'),('wifi','a'*64)]:
            with self.assertRaises(ValueError): validar_wifi(ssid,pw)
    def test_08_sin_ejecucion_arbitraria(self):
        self.assertNotIn('shell',comandos_permitidos())
        with self.assertRaises(ValueError):api_json(self.host,'/api/ejecutar',{'codigo':'rm -rf /'},TOKEN)
    def test_09_ip_segura(self):
        self.assertEqual(base_url('192.168.4.1'),'http://192.168.4.1')
        with self.assertRaises(ValueError):base_url('192.168.4.1/path')

if __name__=='__main__': unittest.main(verbosity=2)
