/*
 * DMXcat clean-room test bridge firmware
 * ---------------------------------------
 * Bit-bangs DMX512 (250 kbaud, 8N2) on software pins so the hardware UART
 * stays free for the USB command link to the PC.
 *
 * Wiring (Arduino Nano, ATmega168 @16 MHz) to a CD40698M auto-direction
 * RS485 module (module pins named from the serial side):
 *   D12 (PB4) -> module RXD  (module DATA INPUT  = our DMX transmit)
 *   D11 (PB3) <- module TXD  (module DATA OUTPUT = our DMX receive)
 *   5V/GND    -> module VCC/GND ; module A/B -> DMXcat DMX pair
 *   The module auto-switches direction from data activity (no DE/RE pin).
 *
 * USB serial command protocol (115200 8N1, newline-terminated):
 *   PING            -> PONG
 *   ID              -> banner
 *   SET <ch> <val>   set one slot (ch 1..512, val 0..255)
 *   FILL <val>       set all 512 slots to val
 *   COUNT <n>        number of slots to transmit (1..512)
 *   FRAME <hex...>   set slots 1..N from hex bytes (also sets COUNT)
 *   ON / OFF         enable/disable continuous DMX transmit
 *   CAP <n>          receive up to n frames; prints "RX <len> <hex>"
 *   IDLE             stop TX, transceiver to receive, release bus
 *   PAD <s> <d>      set per-bit pad loop counts (TX timing calibration)
 */
#include <util/delay.h>
#include <avr/interrupt.h>

#define TXBIT   4   // PB4 / D12  -> module RXD (DMX transmit out onto RS485)
#define RXBIT   3   // PB3 / D11  <- module TXD (DMX receive from RS485)
#define DIRBIT  2   // PD2 / D2   (unused: CD40698M auto-direction)

#define DMX_MAX 256
static uint8_t  dmx[DMX_MAX];
static uint16_t dmxCount = 24;
static bool     txEnabled = false;

// One DMX bit = 4us = 64 cycles @16MHz. The delayCycles loop is ~3 cycles per
// count; padStart/padData pad each bit to 64 cycles. Tunable via "PAD s d".
static volatile uint8_t padStart = 18;
static volatile uint8_t padData  = 16;
static volatile uint8_t rxInvert = 0;   // flip received bits (A/B swapped bus)

static inline void dirTransmit() { PORTD |= (1 << DIRBIT); }
static inline void dirReceive()  { PORTD &= ~(1 << DIRBIT); }

static inline void delayCycles(uint8_t n) {
  __asm__ __volatile__(
    "1: dec %0 \n\t"
    "   brne 1b \n\t"
    : "+r"(n));
}

static inline void txByte(uint8_t b) {
  PORTB &= ~(1 << TXBIT);          // start bit
  delayCycles(padStart);
  for (uint8_t i = 0; i < 8; i++) {
    uint8_t p = (PORTB & ~(1 << TXBIT)) | ((b & 1) << TXBIT);
    PORTB = p;
    b >>= 1;
    delayCycles(padData);
  }
  PORTB |= (1 << TXBIT);           // stop bits (2)
  delayCycles(padData);
  delayCycles(padData);
}

static void sendFrame() {
  cli();
  dirTransmit();
  PORTB |= (1 << TXBIT);
  _delay_us(12);
  PORTB &= ~(1 << TXBIT);          // BREAK
  _delay_us(120);
  PORTB |= (1 << TXBIT);           // MARK AFTER BREAK
  _delay_us(16);
  txByte(0x00);                    // start code
  for (uint16_t i = 0; i < dmxCount; i++) txByte(dmx[i]);
  PORTB |= (1 << TXBIT);
  sei();
}

// ---- DMX receive (bit-bang, best effort) ----
static inline uint8_t rxHigh() { return (((PINB >> RXBIT) & 1) ^ rxInvert); }

static uint16_t captureFrame(uint8_t *buf, uint16_t maxLen) {
  uint32_t guard;
  for (;;) {                       // find a BREAK (long low)
    guard = 200000UL;
    while (rxHigh()) { if (--guard == 0) return 0; }
    uint16_t lowCount = 0;
    while (!rxHigh()) { lowCount++; _delay_us(1); if (lowCount > 600) break; }
    if (lowCount >= 80) break;     // qualified BREAK; line now high (MAB)
  }
  uint16_t n = 0;
  while (n < maxLen) {
    guard = 40000UL;               // wait for next start bit (falling)
    while (rxHigh()) { if (--guard == 0) return n; }
    __builtin_avr_delay_cycles(96 - 8);   // to centre of data bit 0
    uint8_t b = 0;
    for (uint8_t i = 0; i < 8; i++) {
      b = (b >> 1) | (rxHigh() << 7);
      __builtin_avr_delay_cycles(64 - 8);
    }
    buf[n++] = b;
    __builtin_avr_delay_cycles(40);       // ride out stop bits
  }
  return n;
}

static void doCapture(uint16_t frames) {
  uint8_t *buf = dmx;            // reuse TX buffer (unused during capture)
  dirReceive();
  _delay_ms(2);
  for (uint16_t f = 0; f < frames; f++) {
    cli();
    uint16_t n = captureFrame(buf, DMX_MAX);
    sei();
    if (n == 0) { Serial.println(F("RX timeout")); continue; }
    Serial.print(F("RX ")); Serial.print(n); Serial.print(' ');
    for (uint16_t i = 0; i < n; i++) {
      if (buf[i] < 16) Serial.print('0');
      Serial.print(buf[i], HEX);
    }
    Serial.println();
  }
}

// ---- command parsing ----
static char line[120];
static uint16_t lineLen = 0;

static uint8_t hexNibble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return 0;
}

static void handleLine() {
  if (lineLen == 0) return;
  line[lineLen] = 0;
  if      (!strncmp(line, "PING", 4)) Serial.println(F("PONG"));
  else if (!strncmp(line, "ID", 2))   Serial.println(F("DMXCAT-BRIDGE v1"));
  else if (!strncmp(line, "ON", 2))   { txEnabled = true;  Serial.println(F("OK ON")); }
  else if (!strncmp(line, "OFF", 3))  { txEnabled = false; dirReceive(); Serial.println(F("OK OFF")); }
  else if (!strncmp(line, "IDLE", 4)) { txEnabled = false; dirReceive(); Serial.println(F("OK IDLE")); }
  else if (!strncmp(line, "INV", 3)) {
    rxInvert = atoi(line + 3) ? 1 : 0;
    Serial.print(F("OK INV ")); Serial.println(rxInvert);
  }
  else if (!strncmp(line, "PAD", 3)) {
    int a, b; if (sscanf(line + 3, "%d %d", &a, &b) == 2) { padStart = a; padData = b; }
    Serial.print(F("OK PAD ")); Serial.print(padStart); Serial.print(' '); Serial.println(padData);
  }
  else if (!strncmp(line, "COUNT", 5)) {
    int n = atoi(line + 5); if (n < 1) n = 1; if (n > DMX_MAX) n = DMX_MAX; dmxCount = n;
    Serial.print(F("OK COUNT ")); Serial.println(dmxCount);
  }
  else if (!strncmp(line, "FILL", 4)) {
    int v = atoi(line + 4); for (uint16_t i = 0; i < DMX_MAX; i++) dmx[i] = v;
    Serial.print(F("OK FILL ")); Serial.println(v);
  }
  else if (!strncmp(line, "SET", 3)) {
    int ch, v;
    if (sscanf(line + 3, "%d %d", &ch, &v) == 2 && ch >= 1 && ch <= DMX_MAX) {
      dmx[ch - 1] = v; Serial.print(F("OK SET ")); Serial.print(ch); Serial.print('='); Serial.println(v);
    } else Serial.println(F("ERR SET"));
  }
  else if (!strncmp(line, "FRAME", 5)) {
    char *p = line + 5; while (*p == ' ') p++;
    uint16_t n = 0;
    while (p[0] && p[1] && n < DMX_MAX) { dmx[n++] = (hexNibble(p[0]) << 4) | hexNibble(p[1]); p += 2; }
    if (n) dmxCount = n;
    Serial.print(F("OK FRAME ")); Serial.println(n);
  }
  else if (!strncmp(line, "CAP", 3)) {
    int n = atoi(line + 3); if (n < 1) n = 1; if (n > 50) n = 50;
    bool wasTx = txEnabled; txEnabled = false;
    doCapture(n);
    txEnabled = wasTx;
  }
  else Serial.println(F("ERR ?"));
  lineLen = 0;
}

void setup() {
  DDRB |= (1 << TXBIT);
  DDRB &= ~(1 << RXBIT);
  DDRD |= (1 << DIRBIT);
  PORTB |= (1 << TXBIT);
  dirReceive();
  Serial.begin(115200);
  delay(50);
  Serial.println(F("DMXCAT-BRIDGE v1 ready"));
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') handleLine();
    else if (lineLen < sizeof(line) - 1) line[lineLen++] = c;
  }
  if (txEnabled) { sendFrame(); delay(5); }
}
