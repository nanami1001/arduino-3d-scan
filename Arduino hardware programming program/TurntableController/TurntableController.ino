#include <Unistep2.h>

// IN1, IN2, IN3, IN4, 一圈step數, 每step延遲(us)
Unistep2 stepper(8, 9, 10, 11, 4096, 2441);

void setup()
{
  // 先給一圈
  stepper.move(4096);
}

void loop()
{
  // 必須持續執行
  stepper.run();

  // 剩餘step快跑完時補充
  if (stepper.stepsToGo() < 1000)
  {
    stepper.move(4096);
  }
}