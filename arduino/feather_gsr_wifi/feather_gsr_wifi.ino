// Original Adafruit HUZZAH32 (ESP32): local Wi-Fi GSR stream + NeoPixel bar.
// Copy wifi_secrets.example.h to wifi_secrets.h and add your own Wi-Fi details.
// This sketch reads a suitable sensor output; it is NOT a body-contact circuit.
#include <WiFi.h>
#include <Adafruit_NeoPixel.h>
#include "wifi_secrets.h"

constexpr int SENSOR_PIN = 34; // GPIO34 (A2 on original HUZZAH32), ADC1
constexpr int PIXEL_PIN = 32;  // NeoPixel FeatherWing default jumper on original HUZZAH32
constexpr int TCP_PORT = 8765;
Adafruit_NeoPixel pixels(32, PIXEL_PIN, NEO_GRB + NEO_KHZ800);
WiFiServer server(TCP_PORT);
WiFiClient client;
unsigned long lastSample = 0, lastConnect = 0;
bool serverStarted = false;

void setup() {
  Serial.begin(115200);
  analogReadResolution(10);
  pixels.begin(); pixels.setBrightness(16); pixels.clear(); pixels.show();
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void loop() {
  unsigned long now = millis();
  if (WiFi.status() != WL_CONNECTED) {
    if (serverStarted) { client.stop(); server.stop(); serverStarted = false; }
    if (now - lastConnect >= 10000) {
      lastConnect = now; WiFi.disconnect(); WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      Serial.println("Connecting to Wi-Fi...");
    }
  } else {
    if (!serverStarted) {
      server.begin(); serverStarted = true;
      Serial.print("Feather IP: "); Serial.println(WiFi.localIP());
    }
    if (!client || !client.connected()) {
      client.stop(); client = server.available();
    }
  }
  if (now - lastSample >= 50) {
    lastSample = now;
    int value = analogRead(SENSOR_PIN);
    // Light count shows raw ADC voltage, not emotion or GSR quality.
    int count = map(value, 0, 1023, 0, 32);
    pixels.clear();
    for (int i = 0; i < count; ++i) pixels.setPixelColor(i, pixels.Color(80, 8, 28));
    pixels.show();
    if (client && client.connected()) {
      client.print("GSR:"); client.println(value);
    }
  }
  delay(1);
}
