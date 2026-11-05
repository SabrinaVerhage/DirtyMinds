// TEST 1: original HUZZAH32 + 4x8 / 32-LED NeoPixel FeatherWing.
// Keep the 6V motor supply disconnected. Only USB power is needed.
// Library: Adafruit NeoPixel. Board: Adafruit ESP32 Feather.
#include <Arduino.h>
#include <Adafruit_NeoPixel.h>

#if !defined(ARDUINO_FEATHER_ESP32)
#error Select the original "Adafruit ESP32 Feather" board.
#endif

constexpr uint8_t PIXEL_PIN = 32;  // Default Wing jumper on ORIGINAL HUZZAH32.
constexpr uint16_t PIXEL_COUNT = 32;
constexpr uint8_t BRIGHTNESS = 24; // 0..255; start dim on USB power.
constexpr uint8_t MOTOR_ENABLE_PINS[] = {27, 33, 25, 26};
Adafruit_NeoPixel pixels(PIXEL_COUNT, PIXEL_PIN, NEO_GRB + NEO_KHZ800);

bool automatic = true;
uint8_t frame = 0;
uint32_t lastFrame = 0;
uint32_t frameTime = 0;

uint32_t bankColor(uint8_t bank) {
  const uint32_t colors[] = {
    pixels.Color(255, 35, 120), pixels.Color(255, 150, 0),
    pixels.Color(50, 255, 35), pixels.Color(20, 130, 255)
  };
  return colors[bank];
}

void showBank(uint8_t bank) {
  pixels.clear();
  pixels.fill(bankColor(bank), bank * 8, 8);
  pixels.show();
}

void printHelp() {
  Serial.println("NEOPIXEL TEST: red, green, blue, pixel chase, then banks 1-4.");
  Serial.println("1/2/3/4 = hold that bank; a = automatic; 0 = off; ? = help.");
}

void setup() {
  // These match the combined sketch. Keep all motor enables low if attached.
  for (uint8_t pin : MOTOR_ENABLE_PINS) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
  }
  Serial.begin(115200);
  pixels.begin();
  pixels.setBrightness(BRIGHTNESS);
  pixels.clear();
  pixels.show();
  printHelp();
}

void loop() {
  // Single-character commands; Serial Monitor's newline setting does not matter.
  for (uint8_t budget = 0; budget < 32 && Serial.available(); ++budget) {
    char command = Serial.read();
    if (command >= '1' && command <= '4') {
      automatic = false;
      showBank(command - '1');
    } else if (command == '0') {
      automatic = false;
      pixels.clear();
      pixels.show();
    } else if (command == 'a' || command == 'A') {
      automatic = true;
      frame = 0;
      frameTime = 0;
    } else if (command == '?') printHelp();
  }
  uint32_t now = millis();
  if (automatic && uint32_t(now - lastFrame) >= frameTime) {
    pixels.clear();
    frameTime = 900;
    if (frame < 3) {
      const uint32_t colors[] = {pixels.Color(255, 0, 0),
                                pixels.Color(0, 255, 0), pixels.Color(0, 0, 255)};
      pixels.fill(colors[frame]);
    } else if (frame < 35) {
      uint8_t index = frame - 3;
      pixels.setPixelColor(index, bankColor(index / 8));
      frameTime = 100;
    } else if (frame < 39) {
      uint8_t bank = frame - 35;
      pixels.fill(bankColor(bank), bank * 8, 8);
      Serial.print("Bank "); Serial.println(bank + 1);
    } // Frame 39 is a short all-off pause.
    pixels.show();
    frame = (frame + 1) % 40;
    lastFrame = now;
  }
  delay(1);
}
