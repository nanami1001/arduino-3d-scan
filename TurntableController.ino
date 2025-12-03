// TurntableController.ino
// 控制 28BYJ-48 (ULN2003) via Arduino Uno
// Serial protocol: send "ROTATE_STEPS <N>\n"  -> Arduino runs N steps -> prints "DONE\n"

const int motorPin1 = 8;   // IN1
const int motorPin2 = 9;   // IN2
const int motorPin3 = 10;  // IN3
const int motorPin4 = 11;  // IN4

// 28BYJ-48 step sequence (half-step)
const int stepCount = 8;
const int stepSequence[8][4] = {
  {1,0,0,0},
  {1,1,0,0},
  {0,1,0,0},
  {0,1,1,0},
  {0,0,1,0},
  {0,0,1,1},
  {0,0,0,1},
  {1,0,0,1}
};

unsigned long stepDelay = 1000UL / 200; // default delay between steps (microseconds converted)
int direction = 1;

void setup() {
  Serial.begin(115200);
  pinMode(motorPin1, OUTPUT);
  pinMode(motorPin2, OUTPUT);
  pinMode(motorPin3, OUTPUT);
  pinMode(motorPin4, OUTPUT);
  // set low
  digitalWrite(motorPin1, LOW);
  digitalWrite(motorPin2, LOW);
  digitalWrite(motorPin3, LOW);
  digitalWrite(motorPin4, LOW);
  Serial.println("TurntableController ready");
}

void stepOnce(int stepIndex) {
  digitalWrite(motorPin1, stepSequence[stepIndex][0]);
  digitalWrite(motorPin2, stepSequence[stepIndex][1]);
  digitalWrite(motorPin3, stepSequence[stepIndex][2]);
  digitalWrite(motorPin4, stepSequence[stepIndex][3]);
}

void runSteps(long steps) {
  int curStep = 0;
  if (steps == 0) return;
  int dir = (steps > 0) ? 1 : -1;
  long s = abs(steps);
  for (long i = 0; i < s; ++i) {
    stepOnce(curStep);
    delayMicroseconds(stepDelay);
    curStep += dir;
    if (curStep >= stepCount) curStep = 0;
    if (curStep < 0) curStep = stepCount - 1;
  }
  // turn off coils to reduce heating
  digitalWrite(motorPin1, LOW);
  digitalWrite(motorPin2, LOW);
  digitalWrite(motorPin3, LOW);
  digitalWrite(motorPin4, LOW);
}

String readLine() {
  String s = "";
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') break;
    if (c != '\r') s += c;
  }
  return s;
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) return;
    // expected "ROTATE_STEPS <n>"
    if (line.startsWith("ROTATE_STEPS")) {
      int sp = line.indexOf(' ');
      if (sp > 0) {
        String num = line.substring(sp + 1);
        long steps = num.toInt();
        Serial.print("RUN ");
        Serial.println(steps);
        runSteps(steps);
        Serial.println("DONE");
      } else {
        Serial.println("ERR_BAD_CMD");
      }
    } else if (line.startsWith("SET_DELAY")) {
      // optional: set microsecond delay between steps: "SET_DELAY 800"
      int sp = line.indexOf(' ');
      if (sp > 0) {
        long d = line.substring(sp + 1).toInt();
        if (d > 0) {
          stepDelay = d;
          Serial.print("DELAY_SET ");
          Serial.println(stepDelay);
        }
      }
    } else {
      Serial.println("UNKNOWN_CMD");
    }
  }
}
