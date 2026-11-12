#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoOTA.h>
#include <ESP32Servo.h>
#include <driver/gpio.h>

// ========================================
// CONFIGURACION WIFI Y OTA
// ========================================

const char* ssid = "GS_2.4HZ";
const char* password = "Luna0892!";
const char* otaPassword = "4ng3l!+";

// ========================================
// PINES
// ========================================

#define RX_ARDUINO 16
#define TX_ARDUINO 17
#define PIN_SERVO 18

// ========================================
// CONFIGURACION DEL ESTACIONAMIENTO
// ========================================

// Distancias expresadas en milimetros
const long DISTANCIA_APERTURA = 150; // 15 cm
const long DISTANCIA_SALIDA = 180;   // 18 cm
const long LIMITE_PLAZA = 120;       // 12 cm

// Pulsos del servo
const int SERVO_CERRADO = 1100;
const int SERVO_ABIERTO = 1900;

// Tiempo de espera antes del cierre
const unsigned long TIEMPO_CIERRE = 3000;

// true: exige que la plaza de prueba este libre.
// false: prueba solamente el sensor de entrada.
const bool CONTROLAR_PLAZA = true;

// ========================================
// OBJETOS Y VARIABLES
// ========================================

Servo pluma;

WebServer servidor(80);

String historial = "";
String mensajeRecibido = "";

long distancia1 = -1;
long distancia2 = -1;

bool arduinoConectado = false;
bool serviciosIniciados = false;

bool vehiculoEntrada = false;
bool plazaOcupada = false;

bool plumaAbierta = false;
bool servoDisponible = false;

bool esperandoCierre = false;
bool actualizandoOTA = false;

bool descartarMensaje = false;

unsigned long ultimaLectura = 0;
unsigned long inicioCierre = 0;

// ========================================
// REGISTRAR MENSAJES
// ========================================

void registrar(String mensaje) {

  String linea =
    "[" + String(millis() / 1000) +
    "s] " + mensaje;

  Serial.println(linea);

  historial += linea + "\n";

  if (historial.length() > 4500) {

    historial.remove(
      0,
      historial.length() - 4000
    );
  }
}

// ========================================
// VALIDAR DISTANCIAS
// ========================================

bool distanciaValida(long distancia) {

  return distancia >= 20 &&
         distancia <= 4000;
}

// ========================================
// ABRIR PLUMA
// ========================================

void abrirPluma() {

  if (!servoDisponible || plumaAbierta) {
    return;
  }

  pluma.writeMicroseconds(SERVO_ABIERTO);

  plumaAbierta = true;

  esperandoCierre = false;

  registrar("ACCESO AUTORIZADO");
  registrar("PLUMA ABIERTA");
}

// ========================================
// CERRAR PLUMA
// ========================================

void cerrarPluma() {

  if (!servoDisponible || !plumaAbierta) {
    return;
  }

  pluma.writeMicroseconds(SERVO_CERRADO);

  plumaAbierta = false;

  esperandoCierre = false;

  registrar("PLUMA CERRADA");
}

// ========================================
// CONTROL AUTOMATICO
// ========================================

void controlarPluma() {

  if (!servoDisponible || actualizandoOTA) {
    esperandoCierre = false;
    return;
  }

  // No actuar sin datos del Arduino
  if (!arduinoConectado) {

    esperandoCierre = false;
    return;
  }

  // Validar sensor de entrada
  if (!distanciaValida(distancia1)) {

    esperandoCierre = false;
    return;
  }

  // Validar sensor de plaza si esta habilitado
  if (CONTROLAR_PLAZA &&
      !distanciaValida(distancia2)) {

    esperandoCierre = false;
    return;
  }

  // ======================================
  // SI LA PLUMA ESTA CERRADA
  // ======================================

  if (!plumaAbierta) {

    bool espacioDisponible =
      !CONTROLAR_PLAZA || !plazaOcupada;

    if (vehiculoEntrada &&
        espacioDisponible) {

      abrirPluma();
    }

    return;
  }

  // ======================================
  // SI LA PLUMA ESTA ABIERTA
  // ======================================

  // Mantener abierta mientras el
  // vehiculo se encuentre cerca.
  if (vehiculoEntrada ||
      distancia1 < DISTANCIA_SALIDA) {

    esperandoCierre = false;

    return;
  }

  // El vehiculo se ha retirado.
  // Iniciar temporizador de cierre.
  if (!esperandoCierre) {

    esperandoCierre = true;

    inicioCierre = millis();

    registrar(
      "Entrada despejada - Esperando cierre"
    );
  }

  // Cerrar si permanece despejada
  // durante tres segundos.
  if (millis() - inicioCierre >=
      TIEMPO_CIERRE) {

    cerrarPluma();
  }
}

// ========================================
// PROCESAR DATOS DEL ARDUINO
// ========================================

void procesarMensaje(String mensaje) {

  mensaje.trim();

  long s1;
  long s2;
  char extra;

  int campos = sscanf(
    mensaje.c_str(),
    "S1:%ld,S2:%ld%c",
    &s1,
    &s2,
    &extra
  );

  if (campos != 2) {
    return;
  }

  if (s1 != -1 && !distanciaValida(s1)) {
    return;
  }

  if (s2 != -1 && !distanciaValida(s2)) {
    return;
  }

  distancia1 = s1;
  distancia2 = s2;

  ultimaLectura = millis();

  arduinoConectado = true;

  // ======================================
  // SENSOR 1: ENTRADA
  // ======================================

  if (distanciaValida(distancia1)) {

    registrar(
      "Sensor 1 - Entrada: " +
      String(distancia1 / 10.0, 1) +
      " cm"
    );

    // Detectar llegada del vehiculo
    if (distancia1 <= DISTANCIA_APERTURA) {

      if (!vehiculoEntrada) {

        registrar("VEHICULO DETECTADO");
      }

      vehiculoEntrada = true;

    } else if (
      distancia1 >= DISTANCIA_SALIDA
    ) {

      if (vehiculoEntrada) {

        registrar("VEHICULO RETIRADO");
      }

      vehiculoEntrada = false;
    }

  } else {

    vehiculoEntrada = false;

    registrar("Sensor 1: Sin lectura");
  }

  // ======================================
  // SENSOR 2: PLAZA DE ESTACIONAMIENTO
  // ======================================

  if (distanciaValida(distancia2)) {

    registrar(
      "Sensor 2 - Plaza: " +
      String(distancia2 / 10.0, 1) +
      " cm"
    );

    bool nuevaOcupacion =
      distancia2 <= LIMITE_PLAZA;

    if (nuevaOcupacion != plazaOcupada) {

      plazaOcupada = nuevaOcupacion;

      if (plazaOcupada) {

        registrar("PLAZA 1 OCUPADA");

      } else {

        registrar("PLAZA 1 DISPONIBLE");
      }
    }

  } else {

    registrar("Sensor 2: Sin lectura");
  }

  // Tomar decisiones con datos nuevos
  controlarPluma();
}

// ========================================
// RECIBIR INFORMACION UART
// ========================================

void recibirArduino() {

  while (Serial2.available()) {

    char caracter = Serial2.read();

    if (caracter == '\n') {

      if (!descartarMensaje) {

        procesarMensaje(mensajeRecibido);
      }

      mensajeRecibido = "";

      descartarMensaje = false;

    } else if (caracter != '\r') {

      if (!descartarMensaje) {

        if (mensajeRecibido.length() < 60) {

          mensajeRecibido += caracter;

        } else {

          mensajeRecibido = "";

          descartarMensaje = true;
        }
      }
    }
  }
}

// ========================================
// CONVERTIR DISTANCIAS A JSON
// ========================================

String distanciaJSON(long distancia) {

  if (!arduinoConectado ||
      !distanciaValida(distancia)) {

    return "null";
  }

  return String(distancia / 10.0, 1);
}

// ========================================
// ESTADO PARA EL MONITOR PYTHON
// ========================================

String obtenerEstado() {

  String json = "{";

  json += "\"equipo\":\"parqueo-esp32\",";

  json += "\"conectado\":";

  json +=
    (WiFi.status() == WL_CONNECTED)
    ? "true" : "false";

  json += ",\"ip\":\"";

  json += WiFi.localIP().toString();

  json += "\"";

  json += ",\"tiempo_encendido_s\":";

  json += String(millis() / 1000);

  json += ",\"senal_wifi_dbm\":";

  json += String(WiFi.RSSI());

  json += ",\"arduino_conectado\":";

  json += arduinoConectado ? "true" : "false";

  // Distancias
  json += ",\"sensor1_cm\":";

  json += distanciaJSON(distancia1);

  json += ",\"sensor2_cm\":";

  json += distanciaJSON(distancia2);

  // Vehiculo en entrada
  json += ",\"vehiculo_entrada\":";

  if (arduinoConectado &&
      distanciaValida(distancia1)) {

    json += vehiculoEntrada ? "true" : "false";

  } else {

    json += "null";
  }

  // Estado de la plaza 1
  json += ",\"plaza1_ocupada\":";

  if (arduinoConectado &&
      distanciaValida(distancia2)) {

    json += plazaOcupada ? "true" : "false";

  } else {

    json += "null";
  }

  // Informacion del estacionamiento
  json += ",\"plazas_total\":3";

  // Las otras plazas todavia no
  // estan instaladas.
  json += ",\"plazas_ocupadas\":null";

  json += ",\"plazas_libres\":null";

  json += ",\"lcd\":\"controlada_por_arduino_uno\"";

  json += ",\"modo\":\"automatico_prueba\"";

  json += ",\"servo_disponible\":";

  json += servoDisponible ? "true" : "false";

  // Estado ordenado al servo
  json += ",\"pluma\":\"";

  if (!servoDisponible) {

    json += "error";

  } else {

    json += plumaAbierta
      ? "abierta" : "cerrada";
  }

  json += "\"}";

  return json;
}

// ========================================
// SERVIDOR HTTP
// ========================================

void configurarServidor() {

  servidor.on("/", HTTP_GET, []() {

    servidor.send(
      200,
      "text/plain",
      "PARQUEO AUTOMATICO ESP32"
    );
  });

  servidor.on("/api/estado", HTTP_GET, []() {

    servidor.sendHeader(
      "Cache-Control",
      "no-store"
    );

    servidor.send(
      200,
      "application/json",
      obtenerEstado()
    );
  });

  servidor.on("/api/logs", HTTP_GET, []() {

    servidor.sendHeader(
      "Cache-Control",
      "no-store"
    );

    servidor.send(
      200,
      "text/plain",
      historial
    );
  });

  servidor.begin();

  registrar("SERVIDOR HTTP INICIADO");
}

// ========================================
// CONFIGURAR OTA
// ========================================

void configurarOTA() {

  ArduinoOTA.setHostname("parqueo-esp32");

  ArduinoOTA.setPassword(otaPassword);

  ArduinoOTA.onStart([]() {

    actualizandoOTA = true;

    esperandoCierre = false;

    registrar("ACTUALIZACION OTA INICIADA");
  });

  ArduinoOTA.onEnd([]() {

    registrar("ACTUALIZACION OTA COMPLETADA");
  });

  ArduinoOTA.onError([](ota_error_t error) {

    actualizandoOTA = false;

    arduinoConectado = false;

    distancia1 = -1;
    distancia2 = -1;

    esperandoCierre = false;

    registrar(
      "ERROR OTA: " + String((int)error)
    );
  });

  ArduinoOTA.begin();

  registrar("OTA HABILITADO");
}

// ========================================
// CONFIGURACION INICIAL
// ========================================

void setup() {

  Serial.begin(115200);

  historial.reserve(4600);

  mensajeRecibido.reserve(60);

  // ======================================
  // COMUNICACION CON ARDUINO UNO
  // ======================================

  Serial2.begin(
    1200,
    SERIAL_8N1,
    RX_ARDUINO,
    TX_ARDUINO
  );

  // Pull-up interno de 3.3 V
  gpio_pulldown_dis(GPIO_NUM_16);

  gpio_pullup_en(GPIO_NUM_16);

  // ======================================
  // CONFIGURACION DEL SERVO
  // ======================================

  pluma.setPeriodHertz(50);

  pluma.attach(
    PIN_SERVO,
    500,
    2400
  );

  servoDisponible = pluma.attached();

  if (servoDisponible) {

    // Iniciar con pluma cerrada
    pluma.writeMicroseconds(
      SERVO_CERRADO
    );

    plumaAbierta = false;

    registrar("SERVO INICIALIZADO");

    registrar("PLUMA CERRADA");

  } else {

    registrar("ERROR: SERVO NO INICIALIZADO");
  }

  // ======================================
  // CONEXION WIFI
  // ======================================

  WiFi.mode(WIFI_STA);

  WiFi.setAutoReconnect(true);

  WiFi.begin(ssid, password);

  registrar("CONECTANDO AL WIFI");

  registrar("SISTEMA AUTOMATICO INICIADO");
}

// ========================================
// BUCLE PRINCIPAL
// ========================================

void loop() {

  // Recibir informacion de sensores
  recibirArduino();

  // Detectar perdida de comunicacion
  if (arduinoConectado &&
      millis() - ultimaLectura > 3500) {

    arduinoConectado = false;

    distancia1 = -1;
    distancia2 = -1;

    vehiculoEntrada = false;

    esperandoCierre = false;

    registrar(
      "ADVERTENCIA: SIN DATOS DEL ARDUINO"
    );
  }

  // ======================================
  // WIFI Y MONITOR PYTHON
  // ======================================

  if (WiFi.status() == WL_CONNECTED) {

    if (!serviciosIniciados) {

      registrar("WIFI CONECTADO");

      registrar(
        "IP: " +
        WiFi.localIP().toString()
      );

      configurarOTA();

      configurarServidor();

      serviciosIniciados = true;
    }

    ArduinoOTA.handle();

    servidor.handleClient();
  }

  delay(2);
}