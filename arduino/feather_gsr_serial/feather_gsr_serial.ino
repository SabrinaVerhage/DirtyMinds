// Original Adafruit HUZZAH32: USB serial GSR stream + NeoPixel Wing level.
// Bench-check the sensor output first, with nobody wearing the glove.
#include <Adafruit_NeoPixel.h>

constexpr int SENSOR_PIN = 34; // A2 on the original HUZZAH32
constexpr int PIXEL_PIN = 32;  // Same FeatherWing jumper as the Wi-Fi sketch
constexpr int PIXEL_COUNT = 32;
constexpr int ADC_MAX = 1023;
constexpr unsigned long SAMPLE_INTERVAL_MS = 50;

Adafruit_NeoPixel pixels(PIXEL_COUNT, PIXEL_PIN, NEO_GRB + NEO_KHZ800);
unsigned long lastSample = 0;

void setup() {
  Serial.begin(115200);
  analogReadResolution(10);
  pixels.begin();
  pixels.setBrightness(16);
  pixels.clear();
  pixels.show();
}

void loop() {
  const unsigned long now = millis();
  if (now - lastSample < SAMPLE_INTERVAL_MS) {
    delay(1);
    return;
  }
  lastSample = now;

  const int value = analogRead(SENSOR_PIN);
  Serial.print("GSR:");
  Serial.println(value);

  const int lit = map(value, 0, ADC_MAX, 0, PIXEL_COUNT);
  pixels.clear();
  for (int i = 0; i < lit; ++i) {
    pixels.setPixelColor(i, pixels.Color(80, 8, 28));
  }
  pixels.show();
}
