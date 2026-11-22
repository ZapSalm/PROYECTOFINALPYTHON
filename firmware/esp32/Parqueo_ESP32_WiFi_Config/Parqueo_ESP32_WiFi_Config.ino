/*
  PARQUEO AUTOMATICO - ESP32 WROOM 32 DevKit (38 pines)
  RX desde Arduino UNO D12 en GPIO16, protocolo abierto 1200 baudios.
  Servo SG90 senal GPIO18, alimentacion EXTERNA regulada 5 V.
  LED verde/rojo: P1 25/26, P2 27/32, P3 33/23.
  CADA LED con resistencia de 330 ohmios hacia el GPIO, catodo a GND.
  GND de UNO, ESP32 y fuente del servo deben estar unidos.

  API de monitor Python: GET /api/estado (JSON) y /api/logs (texto).
  La pluma reportada es la posicion ORDENADA, no un sensor fisico.
*/
#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoOTA.h>
#include <ESP32Servo.h>
#include <driver/gpio.h>
#include <Preferences.h>

// Ajustar a tu red; NO publicar contrasenas reales.
// PERSONALIZAR ESTAS 3 CLAVES ANTES DE INSTALAR EL FIRMWARE.
// Punto de acceso de rescate: siempre accesible en 192.168.4.1.
// Archivo local excluido de Git. Ver config_private.example.h.
#include "config_private.h"

const char* AP_SSID = "SmartParking-Setup";
const char* AP_PASSWORD = SP_AP_PASSWORD; // minimo 8 caracteres
const char* CONTROL_TOKEN = SP_CONTROL_TOKEN; // se introduce en la app
const char* CLAVE_OTA = SP_OTA_PASSWORD;
const char* HOSTNAME = "parqueo-esp32";

const int GPIO_RX_UNO = 16;
const int GPIO_SERVO = 18;
const int GPIO_LED_VERDE[3] = {25, 27, 33};
const int GPIO_LED_ROJO[3]  = {26, 32, 23};

const long UMBRAL_OCUPA_MM = 120;     // vehiculo <= 12 cm
const long UMBRAL_LIBERA_MM = 150;    // libre >= 15 cm
const long UMBRAL_ENTRA_MM = 150;     // entrada detecta <= 15 cm
const long UMBRAL_SALE_MM = 180;      // entrada se libera >= 18 cm
const int SERVO_CERRADO_US = 1100;
const int SERVO_ABIERTO_US = 1900;
const unsigned long CIERRE_TRAS_LIBRE_MS = 3000UL;
const unsigned long TIMEOUT_UNO_MS = 3500UL;

WebServer web(80);
Preferences prefs;
String ssidGuardado;
String passwordGuardada;
bool cambioWifiPendiente = false;
unsigned long cambioWifiDesde = 0;
unsigned long ultimoIntentoSTA = 0;
bool ledTestActivo = false;
unsigned long ledTestHasta = 0;
int ledTestColor = 0; // 0 verde, 1 rojo
unsigned long ultimoVehiculoEntrada = 0;
String ultimoComando = "ninguno";
Servo pluma;
long mm[4] = {-1, -1, -1, -1};
// -1 desconocida, 0 libre, 1 ocupada
int8_t estadoPlaza[3] = {-1, -1, -1};
uint8_t cuentaOcupa[3] = {0, 0, 0};
uint8_t cuentaLibera[3] = {0, 0, 0};
uint8_t cuentaEntrada = 0, cuentaSalida = 0;
bool vehiculoEntrada = false;
bool entradaValida = false;
bool arduinoConectado = false;
bool servoDisponible = false;
bool plumaAbierta = false;
bool servidorListo = false;
bool wifiAnterior = false;
unsigned long ultimaTrama = 0;
unsigned long entradaLibreDesde = 0;
unsigned long ultimoIntentoWifi = 0;
unsigned long ultimoDebug = 0;
char lineaRx[80];
size_t largoRx = 0;

const size_t MAX_REGISTROS = 24;
String registros[MAX_REGISTROS];
size_t proximoRegistro = 0, numeroRegistros = 0;

void registrar(const String& texto) {
  String linea = String(millis() / 1000UL) + "s | " + texto;
  Serial.println(linea);
  registros[proximoRegistro] = linea;
  proximoRegistro = (proximoRegistro + 1) % MAX_REGISTROS;
  if (numeroRegistros < MAX_REGISTROS) numeroRegistros++;
}

bool lecturaValida(long distancia) {
  return distancia >= 20 && distancia <= 4000;
}

// Estados desconocidos SIEMPRE apagan ambos LED de la plaza.
void actualizarLED() {
  if (ledTestActivo) return;
  for (int i = 0; i < 3; i++) {
    digitalWrite(GPIO_LED_VERDE[i], estadoPlaza[i] == 0 ? HIGH : LOW);
    digitalWrite(GPIO_LED_ROJO[i], estadoPlaza[i] == 1 ? HIGH : LOW);
  }
}

void actualizarPlaza(int i, long distancia) {
  int8_t antes = estadoPlaza[i];
  if (!lecturaValida(distancia)) {
    estadoPlaza[i] = -1;
    cuentaOcupa[i] = cuentaLibera[i] = 0;
  } else if (distancia <= UMBRAL_OCUPA_MM) {
    cuentaLibera[i] = 0;
    if (cuentaOcupa[i] < 2) cuentaOcupa[i]++;
    if (cuentaOcupa[i] >= 2) estadoPlaza[i] = 1;
  } else if (distancia >= UMBRAL_LIBERA_MM) {
    cuentaOcupa[i] = 0;
    if (cuentaLibera[i] < 2) cuentaLibera[i]++;
    if (cuentaLibera[i] >= 2) estadoPlaza[i] = 0;
  } else {
    cuentaOcupa[i] = cuentaLibera[i] = 0;
  }
  if (antes != estadoPlaza[i]) {
    const char* etiqueta = estadoPlaza[i] == 1 ? "OCUPADA" :
                          estadoPlaza[i] == 0 ? "LIBRE" : "SIN LECTURA";
    registrar("Plaza " + String(i + 1) + ": " + etiqueta);
  }
}

void actualizarEntrada(long distancia) {
  // Cualquier eco invalido se trata como posible obstaculo para el cierre manual.
  if (!lecturaValida(distancia) || distancia < UMBRAL_SALE_MM) {
    ultimoVehiculoEntrada = millis();
  }
  bool antes = vehiculoEntrada;
  entradaValida = lecturaValida(distancia);
  if (!entradaValida) {
    vehiculoEntrada = false; // diagnostico; si pluma abierta, NO cerrar
    cuentaEntrada = cuentaSalida = 0;
  } else if (distancia <= UMBRAL_ENTRA_MM) {
    cuentaSalida = 0;
    if (cuentaEntrada < 2) cuentaEntrada++;
    if (cuentaEntrada >= 2) vehiculoEntrada = true;
  } else if (distancia >= UMBRAL_SALE_MM) {
    cuentaEntrada = 0;
    if (cuentaSalida < 2) cuentaSalida++;
    if (cuentaSalida >= 2) vehiculoEntrada = false;
  } else {
    cuentaEntrada = cuentaSalida = 0;
  }
  if (antes != vehiculoEntrada && entradaValida) {
    registrar(vehiculoEntrada ? "Vehiculo en entrada" : "Entrada libre");
  }
}

// Devuelve false si alguna plaza no se puede determinar.
bool obtenerConteo(int& ocupadas, int& libres) {
  ocupadas = 0;
  for (int i = 0; i < 3; i++) {
    if (estadoPlaza[i] < 0) {
      libres = -1;
      return false;
    }
    if (estadoPlaza[i] == 1) ocupadas++;
  }
  libres = 3 - ocupadas;
  return true;
}

void abrirPluma() {
  if (!servoDisponible || plumaAbierta) return;
  pluma.writeMicroseconds(SERVO_ABIERTO_US);
  plumaAbierta = true;
  entradaLibreDesde = 0;
  registrar("PLUMA ABIERTA - entrada autorizada");
}
void cerrarPluma() {
  if (!servoDisponible || !plumaAbierta) return;
  pluma.writeMicroseconds(SERVO_CERRADO_US);
  plumaAbierta = false;
  entradaLibreDesde = 0;
  registrar("PLUMA CERRADA");
}

void controlarPluma() {
  if (!servoDisponible) return;
  if (plumaAbierta) {
    // No mover la barrera hacia abajo con S1 perdido o carro detectado.
    if (!arduinoConectado || !entradaValida || vehiculoEntrada) {
      entradaLibreDesde = 0;
      return;
    }
    if (entradaLibreDesde == 0) entradaLibreDesde = millis();
    if (millis() - entradaLibreDesde >= CIERRE_TRAS_LIBRE_MS) cerrarPluma();
  } else {
    int ocupadas, libres;
    bool todasValidas = obtenerConteo(ocupadas, libres);
    if (arduinoConectado && entradaValida && vehiculoEntrada &&
        todasValidas && libres > 0) abrirPluma();
  }
}

// Acepta UNICAMENTE la trama de 4 sensores del programa UNO actual.
void procesarLinea(const char* texto) {
  long s1, s2, s3, s4;
  char extra;
  int leidos = sscanf(texto, "S1:%ld,S2:%ld,S3:%ld,S4:%ld%c",
                      &s1, &s2, &s3, &s4, &extra);
  if (leidos != 4) return;
  bool primera = !arduinoConectado;
  arduinoConectado = true;
  ultimaTrama = millis();
  const long valores[4] = {s1, s2, s3, s4};
  for (int i = 0; i < 4; i++) mm[i] = lecturaValida(valores[i]) ? valores[i] : -1;
  if (primera) registrar("UNO comunicado: 4 sensores reconocidos");
  for (int i = 0; i < 3; i++) actualizarPlaza(i, mm[i + 1]);
  actualizarEntrada(mm[0]);
  actualizarLED();
}

void recibirUNO() {
  while (Serial2.available()) {
    char c = (char)Serial2.read();
    if (c == '\n') {
      if (largoRx > 0) {
        lineaRx[largoRx] = '\0';
        procesarLinea(lineaRx);
      }
      largoRx = 0;
    } else if (c != '\r') {
      if (largoRx < sizeof(lineaRx) - 1) lineaRx[largoRx++] = c;
      else largoRx = 0; // ignorar trama truncada
    }
  }
  if (arduinoConectado && millis() - ultimaTrama > TIMEOUT_UNO_MS) {
    arduinoConectado = false;
    entradaValida = false;
    vehiculoEntrada = false;
    entradaLibreDesde = 0;
    for (int i = 0; i < 4; i++) mm[i] = -1;
    for (int i = 0; i < 3; i++) {
      estadoPlaza[i] = -1;
      cuentaOcupa[i] = cuentaLibera[i] = 0;
    }
    cuentaEntrada = cuentaSalida = 0;
    actualizarLED();
    registrar("ALERTA: perdida de comunicacion con Arduino UNO");
  }
}

String jsonBooleano(bool valor) { return valor ? "true" : "false"; }
String jsonDistancia(long distancia) {
  return lecturaValida(distancia) ? String(distancia / 10.0f, 1) : "null";
}
String jsonEstado(int8_t estado) {
  return estado < 0 ? "null" : jsonBooleano(estado == 1);
}

void responderEstado() {
  int ocupadas, libres;
  bool completo = obtenerConteo(ocupadas, libres);
  String resultado;
  resultado.reserve(1300);
  resultado += "{\"equipo\":\"parqueo-esp32\",";
  resultado += "\"conectado\":true,"; // servidor accesible via AP o STA
  resultado += "\"ip\":\"" + (WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString() : WiFi.softAPIP().toString()) + "\",";
  resultado += "\"wifi_sta_conectado\":" + jsonBooleano(WiFi.status() == WL_CONNECTED) + ",";
  resultado += "\"ip_ap\":\"" + WiFi.softAPIP().toString() + "\",";
  resultado += "\"tiempo_encendido_s\":" + String(millis() / 1000UL) + ",";
  resultado += "\"senal_wifi_dbm\":" + (WiFi.status() == WL_CONNECTED ? String(WiFi.RSSI()) : "null") + ",";
  resultado += "\"arduino_conectado\":" + jsonBooleano(arduinoConectado) + ",";
  resultado += "\"sensor1_cm\":" + jsonDistancia(mm[0]) + ",";
  resultado += "\"sensor2_cm\":" + jsonDistancia(mm[1]) + ",";
  resultado += "\"sensor3_cm\":" + jsonDistancia(mm[2]) + ",";
  resultado += "\"sensor4_cm\":" + jsonDistancia(mm[3]) + ",";
  resultado += "\"vehiculo_entrada\":" +
               (entradaValida && arduinoConectado ? jsonBooleano(vehiculoEntrada) : "null") + ",";
  resultado += "\"plaza1_ocupada\":" + jsonEstado(estadoPlaza[0]) + ",";
  resultado += "\"plaza2_ocupada\":" + jsonEstado(estadoPlaza[1]) + ",";
  resultado += "\"plaza3_ocupada\":" + jsonEstado(estadoPlaza[2]) + ",";
  resultado += "\"plazas_total\":3,";
  resultado += "\"plazas_ocupadas\":" + (completo ? String(ocupadas) : "null") + ",";
  resultado += "\"plazas_libres\":" + (completo ? String(libres) : "null") + ",";
  resultado += "\"parqueo_lleno\":" + (completo ? jsonBooleano(libres == 0) : "null") + ",";
  resultado += "\"pluma\":\"" + String(!servoDisponible ? "error" : plumaAbierta ? "abierta" : "cerrada") + "\",";
  resultado += "\"servo_disponible\":" + jsonBooleano(servoDisponible) + ",";
  resultado += "\"lcd\":\"controlada_por_arduino_uno\",";
  resultado += "\"modo\":\"automatico\",";
  resultado += "\"ultimo_comando\":\"" + ultimoComando + "\"}";
  web.send(200, "application/json; charset=utf-8", resultado);
}

void responderLogs() {
  String contenido;
  contenido.reserve(1700);
  for (size_t j = 0; j < numeroRegistros; j++) {
    size_t k = (proximoRegistro + MAX_REGISTROS - numeroRegistros + j) % MAX_REGISTROS;
    contenido += registros[k] + "\n";
  }
  web.send(200, "text/plain; charset=utf-8", contenido);
}

// Escapar SSID y texto antes de incluirlos en JSON.
String jsonEscape(const String& texto) {
  String out = "";
  for (size_t i = 0; i < texto.length(); ++i) {
    char c = texto.charAt(i);
    if (c == '\\' || c == '\"') { out += '\\'; out += c; }
    else if ((uint8_t)c < 0x20) out += ' ';
    else out += c;
  }
  return out;
}

bool autorizado() {
  if (!web.hasHeader("X-Control-Token") ||
      web.header("X-Control-Token") != CONTROL_TOKEN) {
    web.send(403, "application/json; charset=utf-8",
             "{\"aceptado\":false,\"detalle\":\"Token de control incorrecto\"}");
    return false;
  }
  return true;
}

void wifiStatus() {
  bool conectado = WiFi.status() == WL_CONNECTED;
  String out = "{\"equipo\":\"parqueo-esp32\",";
  out += "\"sta_conectado\":" + jsonBooleano(conectado) + ",";
  out += "\"ssid\":\"" + jsonEscape(conectado ? WiFi.SSID() : ssidGuardado) + "\",";
  out += "\"ip_sta\":" + (conectado ? String("\"") + WiFi.localIP().toString() + "\"" : "null") + ",";
  out += "\"ip_ap\":\"" + WiFi.softAPIP().toString() + "\",";
  out += "\"ap_ssid\":\"" + String(AP_SSID) + "\",";
  out += "\"pendiente\":" + jsonBooleano(cambioWifiPendiente) + ",";
  out += "\"rssi\":" + (conectado ? String(WiFi.RSSI()) : "null") + "}";
  web.send(200, "application/json; charset=utf-8", out);
}

// Escaneo asincrono para no bloquear el control de sensores y pluma.
void buscarRedes() {
  int n = WiFi.scanComplete();
  if (n == WIFI_SCAN_RUNNING) {
    web.send(200, "application/json", "{\"pendiente\":true,\"redes\":[]}");
    return;
  }
  if (n < 0) {
    WiFi.scanNetworks(true);
    web.send(200, "application/json", "{\"pendiente\":true,\"redes\":[]}");
    return;
  }
  String out = "{\"pendiente\":false,\"redes\":[";
  int limite = n < 20 ? n : 20;
  for (int i = 0; i < limite; ++i) {
    if (i) out += ",";
    out += "{\"ssid\":\"" + jsonEscape(WiFi.SSID(i)) + "\",";
    out += "\"rssi\":" + String(WiFi.RSSI(i)) + "}";
  }
  out += "]}";
  WiFi.scanDelete();
  web.send(200, "application/json; charset=utf-8", out);
}

void configurarWifi() {
  if (!autorizado()) return;
  String nuevoSsid = web.arg("ssid");
  String nuevaClave = web.arg("password");
  if (nuevoSsid.length() < 1 || nuevoSsid.length() > 32 ||
      nuevaClave.length() < 8 || nuevaClave.length() > 63) {
    web.send(400, "application/json", "{\"aceptado\":false,\"detalle\":\"SSID 1-32 y clave WPA2 8-63 caracteres\"}");
    return;
  }
  // Las credenciales nunca se devuelven al navegador ni a los logs.
  ssidGuardado = nuevoSsid;
  passwordGuardada = nuevaClave;
  prefs.putString("ssid", ssidGuardado);
  prefs.putString("pass", passwordGuardada);
  cambioWifiPendiente = true;
  cambioWifiDesde = millis();
  registrar("Nueva red recibida; se intentara conectar a SSID: " + ssidGuardado);
  web.send(202, "application/json; charset=utf-8",
           "{\"aceptado\":true,\"detalle\":\"Credenciales guardadas. Conectando en unos segundos.\"}");
}

// Acknowledge de orden recibida y aceptada; NO confirma movimiento fisico.
void ordenRemota() {
  if (!autorizado()) return;
  String accion = web.arg("accion");
  String identificador = web.arg("id");
  if (identificador.length() > 32) identificador = identificador.substring(0, 32);
  bool ejecutado = false;
  String detalle = "Orden desconocida";
  if (accion == "ping") {
    ejecutado = true;
    detalle = "ESP32 recibio y proceso la orden";
  } else if (accion == "led_verde" || accion == "led_rojo") {
    ledTestActivo = true;
    ledTestColor = accion == "led_rojo" ? 1 : 0;
    ledTestHasta = millis() + 2000UL;
    for (int i = 0; i < 3; ++i) {
      digitalWrite(GPIO_LED_VERDE[i], ledTestColor == 0 ? HIGH : LOW);
      digitalWrite(GPIO_LED_ROJO[i], ledTestColor == 1 ? HIGH : LOW);
    }
    ejecutado = true;
    detalle = "Prueba de LED iniciada 2 segundos; se restablece el estado real";
  } else if (accion == "abrir") {
    int ocupadas, libres;
    if (servoDisponible && arduinoConectado && entradaValida &&
        obtenerConteo(ocupadas, libres) && libres > 0) {
      if (!plumaAbierta) abrirPluma();
      ejecutado = true;
      detalle = "Pluma en estado ABIERTO ordenado; NO confirmacion fisica";
    } else detalle = "Apertura bloqueada: revisar sensores, servo y plazas disponibles";
  } else if (accion == "cerrar") {
    // Solo maqueta; nunca cerrar con posible obstaculo o sin sensor confiable.
    if (servoDisponible && arduinoConectado && entradaValida &&
        !vehiculoEntrada && (millis() - ultimoVehiculoEntrada >= 1500UL)) {
      if (plumaAbierta) cerrarPluma();
      ejecutado = true;
      detalle = "Pluma en estado CERRADO ordenado; NO confirmacion fisica";
    } else detalle = "Cierre bloqueado: sensor entrada no confirma despeje seguro";
  }
  if (ejecutado) {
    ultimoComando = accion;
    registrar("Orden de interfaz: " + accion);
  }
  String out = "{\"recibido\":true,\"ejecutado\":" + jsonBooleano(ejecutado) + ",";
  out += "\"id\":\"" + jsonEscape(identificador) + "\",";
  out += "\"accion\":\"" + jsonEscape(accion) + "\",";
  out += "\"detalle\":\"" + jsonEscape(detalle) + "\",";
  out += "\"pluma\":\"" + String(plumaAbierta ? "abierta" : "cerrada") + "\"}";
  web.send(ejecutado ? 200 : 409, "application/json; charset=utf-8", out);
}

void prepararRed() {
  web.on("/", HTTP_GET, []() {
    web.send(200, "text/plain; charset=utf-8", "Smart Parking: /api/estado, /api/logs, /api/wifi/status");
  });
  web.on("/api/estado", HTTP_GET, responderEstado);
  web.on("/api/logs", HTTP_GET, responderLogs);
  web.on("/api/wifi/status", HTTP_GET, wifiStatus);
  web.on("/api/wifi/scan", HTTP_GET, buscarRedes);
  web.on("/api/wifi/config", HTTP_POST, configurarWifi);
  web.on("/api/comando", HTTP_POST, ordenRemota);
  web.onNotFound([]() { web.send(404, "text/plain", "Ruta desconocida"); });
  const char* cabeceras[] = {"X-Control-Token"};
  web.collectHeaders(cabeceras, 1);

  ArduinoOTA.setHostname(HOSTNAME);
  ArduinoOTA.setPassword(CLAVE_OTA);
  ArduinoOTA.onStart([]() { registrar("Actualizacion OTA iniciada"); });
  ArduinoOTA.onEnd([]() { registrar("Actualizacion OTA finalizada"); });
  ArduinoOTA.onError([](ota_error_t error) {
    registrar("OTA error: " + String((int)error));
  });

  prefs.begin("smartparking", false);
  ssidGuardado = prefs.getString("ssid", "");
  passwordGuardada = prefs.getString("pass", "");
  WiFi.mode(WIFI_AP_STA);
  WiFi.softAPConfig(IPAddress(192, 168, 4, 1), IPAddress(192, 168, 4, 1), IPAddress(255, 255, 255, 0));
  WiFi.softAP(AP_SSID, AP_PASSWORD);
  web.begin(); // Se puede configurar aun sin router ni hotspot.
  servidorListo = true;
  registrar("AP de configuracion: " + WiFi.softAPIP().toString());
  WiFi.setAutoReconnect(true);
  if (ssidGuardado.length() > 0) {
    WiFi.begin(ssidGuardado.c_str(), passwordGuardada.c_str());
    ultimoIntentoSTA = millis();
  }
}

void atenderRed() {
  // La API siempre permanece disponible en el AP aunque falle el hotspot.
  web.handleClient();
  if (cambioWifiPendiente && millis() - cambioWifiDesde >= 1800UL) {
    cambioWifiPendiente = false;
    WiFi.disconnect(false, false);
    WiFi.begin(ssidGuardado.c_str(), passwordGuardada.c_str());
    ultimoIntentoSTA = millis();
  }
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiAnterior) {
      wifiAnterior = true;
      ArduinoOTA.begin();
      registrar("Hotspot conectado: " + WiFi.localIP().toString());
    }
    ArduinoOTA.handle();
  } else {
    if (wifiAnterior) {
      wifiAnterior = false;
      registrar("Hotspot desconectado; AP de configuracion sigue disponible");
    }
    if (!cambioWifiPendiente && ssidGuardado.length() > 0 &&
        millis() - ultimoIntentoSTA >= 12000UL) {
      WiFi.begin(ssidGuardado.c_str(), passwordGuardada.c_str());
      ultimoIntentoSTA = millis();
    }
  }
}

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < 3; i++) {
    pinMode(GPIO_LED_VERDE[i], OUTPUT);
    pinMode(GPIO_LED_ROJO[i], OUTPUT);
  }
  actualizarLED();

  // Serial2 RX en GPIO16; el TX GPIO17 no se conecta.
  Serial2.begin(1200, SERIAL_8N1, GPIO_RX_UNO, 17);
  gpio_pullup_en(GPIO_NUM_16); // mejora con resistencia EXTERNA 4.7k a 3V3

  pluma.setPeriodHertz(50);
  pluma.attach(GPIO_SERVO, 500, 2400);
  servoDisponible = pluma.attached();
  if (servoDisponible) pluma.writeMicroseconds(SERVO_CERRADO_US);
  registrar(servoDisponible ? "Servo PWM configurado" : "ERROR al configurar PWM del servo");
  prepararRed();
  registrar("ESP32 iniciado - 3 plazas y 6 LED");
}

void loop() {
  recibirUNO();
  controlarPluma();
  atenderRed();
  if (ledTestActivo && (long)(millis() - ledTestHasta) >= 0) {
    ledTestActivo = false;
    actualizarLED();
  }
  if (millis() - ultimoDebug >= 3500UL) {
    ultimoDebug = millis();
    Serial.printf("UNO:%s S1:%ld S2:%ld S3:%ld S4:%ld Pluma:%s\n",
                  arduinoConectado ? "OK" : "SIN DATOS",
                  mm[0], mm[1], mm[2], mm[3], plumaAbierta ? "ABIERTA" : "CERRADA");
  }
  delay(2);
}
