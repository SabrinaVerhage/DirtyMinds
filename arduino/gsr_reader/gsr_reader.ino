// Dirty Minds USB input: one 10-bit ADC reading per line, 20 times/second.
// Use an appropriate GSR sensor module's analog OUTPUT on A0.
// This is an input protocol demo, not a body-contact circuit design.
// A potentiometer is a useful bench-test source before connecting a sensor.
void setup() {
  Serial.begin(115200);
}

void loop() {
  Serial.println(analogRead(A0));
  delay(50);
}

