/*
  PARQUEO AUTOMATICO - ARDUINO UNO
  S1 entrada: TRIG D4, ECHO D5
  S2 plaza 1: TRIG D6, ECHO D7
  S3 plaza 2: TRIG D8, ECHO D9
  S4 plaza 3: TRIG D10, ECHO D11
  LCD I2C: SDA A4, SCL A5, VCC 5 V, GND GND
  UART unidireccional SEGURA: UNO D12 (colector abierto por software)
  -> ESP32 GPIO16, 1200 8N1. Pull-up 4.7k a 3V3 en el receptor.

  IMPORTANTE: D12 NUNCA conduce 5 V al ESP32.
*/
#include <Wire.h>
#include <hd44780.h>
#include <hd44780ioClass/hd44780_I2Cexp.h>

const byte UNO_TRIG[4] = {4, 6, 8, 10};
const byte UNO_ECHO[4] = {5, 7, 9, 11};
const byte UNO_TX_ABIERTO = 12;
const long UNO_OCUPADA_MM = 120;  // <= 12 cm
const long UNO_LIBRE_MM   = 150;  // >= 15 cm (histeresis)
const unsigned int UNO_BIT_US = 833; // 1200 baudios

hd44780_I2Cexp pantalla;
bool lcdLista = false;
long mm[4] = {-1, -1, -1, -1};
// -1 desconocida; 0 libre; 1 ocupada
int8_t estadoPlaza[3] = {-1, -1, -1};
byte confirmaOcupada[3] = {0, 0, 0};
byte confirmaLibre[3] = {0, 0, 0};

void lineaCero() {
  digitalWrite(UNO_TX_ABIERTO, LOW);
  pinMode(UNO_TX_ABIERTO, OUTPUT);
}
void lineaLibre() {
  pinMode(UNO_TX_ABIERTO, INPUT); // alta impedancia; NO OUTPUT HIGH
  digitalWrite(UNO_TX_ABIERTO, LOW); // pull-up INTERNO del UNO desactivado
}
void enviarByteUART(byte dato) {
  noInterrupts();
  lineaCero(); // start
  delayMicroseconds(UNO_BIT_US);
  for (byte bit = 0; bit < 8; bit++) {
    if (dato & (1 << bit)) lineaLibre();
    else lineaCero();
    delayMicroseconds(UNO_BIT_US);
  }
  lineaLibre(); // stop
  delayMicroseconds(UNO_BIT_US);
  interrupts();
}
void enviarMensajeUART(const char* texto) {
  for (; *texto; texto++) enviarByteUART((byte)*texto);
  enviarByteUART('\n');
}

bool valida(long distancia) {
  return distancia >= 20 && distancia <= 4000;
}
long medirMM(byte trig, byte echo) {
  digitalWrite(trig, LOW);
  delayMicroseconds(3);
  digitalWrite(trig, HIGH);
  delayMicroseconds(10);
  digitalWrite(trig, LOW);
  unsigned long duracion = pulseIn(echo, HIGH, 30000UL);
  if (duracion == 0) return -1;
  long resultado = (duracion * 343UL + 1000UL) / 2000UL;
  return valida(resultado) ? resultado : -1;
}

// Debounce de 2 muestras e histeresis, igual que en el ESP32.
void actualizarPlaza(byte plaza, long distancia) {
  if (!valida(distancia)) {
    estadoPlaza[plaza] = -1;
    confirmaOcupada[plaza] = 0;
    confirmaLibre[plaza] = 0;
    return;
  }
  if (distancia <= UNO_OCUPADA_MM) {
    confirmaLibre[plaza] = 0;
    if (confirmaOcupada[plaza] < 2) confirmaOcupada[plaza]++;
    if (confirmaOcupada[plaza] >= 2) estadoPlaza[plaza] = 1;
  } else if (distancia >= UNO_LIBRE_MM) {
    confirmaOcupada[plaza] = 0;
    if (confirmaLibre[plaza] < 2) confirmaLibre[plaza]++;
    if (confirmaLibre[plaza] >= 2) estadoPlaza[plaza] = 0;
  } else {
    confirmaOcupada[plaza] = 0;
    confirmaLibre[plaza] = 0;
  }
}

void lcdMostrar(const char* a, const char* b) {
  if (!lcdLista) return;
  pantalla.setCursor(0, 0);
  pantalla.print(F("                "));
  pantalla.setCursor(0, 0);
  pantalla.print(a);
  pantalla.setCursor(0, 1);
  pantalla.print(F("                "));
  pantalla.setCursor(0, 1);
  pantalla.print(b);
}
void actualizarLCD() {
  if (!valida(mm[0])) {
    lcdMostrar("S1 SIN LECTURA", "REVISAR ENTRADA");
    return;
  }
  int ocupadas = 0;
  for (byte i = 0; i < 3; i++) {
    if (estadoPlaza[i] < 0) {
      lcdMostrar("PLAZA SIN DATOS", "REVISAR S2-S4");
      return;
    }
    if (estadoPlaza[i] == 1) ocupadas++;
  }
  if (ocupadas == 3) {
    lcdMostrar("PARQUEO LLENO", "SIN NUEVO ACCESO");
  } else {
    char linea1[17], linea2[17];
    snprintf(linea1, sizeof(linea1), "OCUPADAS: %d/3", ocupadas);
    snprintf(linea2, sizeof(linea2), "LIBRES: %d", 3 - ocupadas);
    lcdMostrar(linea1, linea2);
  }
}

void setup() {
  Serial.begin(9600);
  lineaLibre();
  for (byte i = 0; i < 4; i++) {
    pinMode(UNO_TRIG[i], OUTPUT);
    pinMode(UNO_ECHO[i], INPUT);
    digitalWrite(UNO_TRIG[i], LOW);
  }
  lcdLista = (pantalla.begin(16, 2) == 0);
  if (lcdLista) {
    pantalla.backlight();
    lcdMostrar("PARQUEO 3 PLAZAS", "INICIANDO...");
  }
  Serial.println(F("UNO listo: 4 sensores, LCD y TX abierto D12"));
}

void loop() {
  for (byte i = 0; i < 4; i++) {
    mm[i] = medirMM(UNO_TRIG[i], UNO_ECHO[i]);
    delay(70); // HC-SR04: evitar interferencia entre sensores
  }
  for (byte i = 0; i < 3; i++) actualizarPlaza(i, mm[i + 1]);

  // Misma trama que espera el ESP32. mm=-1 significa lectura invalida.
  char mensaje[64];
  snprintf(mensaje, sizeof(mensaje), "S1:%ld,S2:%ld,S3:%ld,S4:%ld",
           mm[0], mm[1], mm[2], mm[3]);
  enviarMensajeUART(mensaje);
  Serial.println(mensaje);
  actualizarLCD();
  delay(120);
}
