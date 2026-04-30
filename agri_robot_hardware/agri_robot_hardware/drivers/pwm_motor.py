"""
PWM Motor Driver — GPIO PWM low-level abstraction for Raspberry Pi 3.

Drives two motors (LEFT, RIGHT) via an L298N H-bridge (or compatible).
Each motor needs:
  - 1 PWM GPIO pin  (duty cycle 0–100 %)
  - 2 direction GPIO pins (IN1/IN2) for H-bridge forward/reverse

Requires `RPi.GPIO` on the Pi.  A `MockPWMMotor` stub is provided for
simulation / desktop testing without hardware.

Typical L298N wiring (Pi 3):
  Left motor:  ENA → GPIO 12 (HW PWM), IN1 → GPIO 23, IN2 → GPIO 24
  Right motor: ENB → GPIO 13 (HW PWM), IN3 → GPIO 27, IN4 → GPIO 22

Hardware PWM pins on Pi 3: GPIO 12 (PWM0) and GPIO 13 (PWM1).
Software PWM works on any pin but may jitter at >1 kHz.
"""

from __future__ import annotations
from abc import ABC, abstractmethod


# ── Abstract base ──────────────────────────────────────────────────────────────

class PWMMotorDriver(ABC):
    """Common interface for PWM motor controllers."""

    @abstractmethod
    def setup(self) -> None:
        """Initialise GPIO / resources."""

    @abstractmethod
    def set_speeds(self, left: float, right: float) -> None:
        """
        Set motor speeds.

        left, right: float in [-1.0, +1.0]
          +1.0 = full forward, -1.0 = full reverse, 0.0 = stop
        """

    @abstractmethod
    def stop(self) -> None:
        """Immediately stop both motors (duty = 0, coasting)."""

    @abstractmethod
    def brake(self) -> None:
        """Active brake both motors (H-bridge short-circuit stop)."""

    @abstractmethod
    def cleanup(self) -> None:
        """Release GPIO resources."""


# ── L298N driver ───────────────────────────────────────────────────────────────

class L298NDriver(PWMMotorDriver):
    """
    Dual H-bridge driver for L298N (and compatible chips like L293D).

    Each side: one PWM enable pin + two direction pins.
    PWM frequency: 1000 Hz (software PWM) — suitable for DC motors.
    """

    PWM_FREQ_HZ = 1000

    def __init__(
        self,
        left_en:  int,   # GPIO BCM — PWM enable for left motor
        left_in1: int,   # GPIO BCM — direction A
        left_in2: int,   # GPIO BCM — direction B
        right_en:  int,  # GPIO BCM — PWM enable for right motor
        right_in1: int,  # GPIO BCM — direction A
        right_in2: int,  # GPIO BCM — direction B
    ):
        self._pins = {
            'left_en':  left_en,
            'left_in1': left_in1,
            'left_in2': left_in2,
            'right_en':  right_en,
            'right_in1': right_in1,
            'right_in2': right_in2,
        }
        self._pwm_left  = None
        self._pwm_right = None
        self._gpio = None

    def setup(self) -> None:
        try:
            import RPi.GPIO as GPIO
            self._gpio = GPIO
        except ImportError:
            raise RuntimeError(
                'RPi.GPIO not installed — run: pip3 install RPi.GPIO'
            )

        GPIO = self._gpio
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        for pin in self._pins.values():
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

        self._pwm_left  = GPIO.PWM(self._pins['left_en'],  self.PWM_FREQ_HZ)
        self._pwm_right = GPIO.PWM(self._pins['right_en'], self.PWM_FREQ_HZ)
        self._pwm_left.start(0)
        self._pwm_right.start(0)

    def set_speeds(self, left: float, right: float) -> None:
        self._set_one(
            left,
            self._pins['left_in1'],
            self._pins['left_in2'],
            self._pwm_left,
        )
        self._set_one(
            right,
            self._pins['right_in1'],
            self._pins['right_in2'],
            self._pwm_right,
        )

    def stop(self) -> None:
        GPIO = self._gpio
        if GPIO is None:
            return
        self._pwm_left.ChangeDutyCycle(0)
        self._pwm_right.ChangeDutyCycle(0)
        for pin in (
            self._pins['left_in1'], self._pins['left_in2'],
            self._pins['right_in1'], self._pins['right_in2'],
        ):
            GPIO.output(pin, GPIO.LOW)

    def brake(self) -> None:
        GPIO = self._gpio
        if GPIO is None:
            return
        # Short-circuit brake: both IN pins HIGH, duty 100 %
        self._pwm_left.ChangeDutyCycle(100)
        self._pwm_right.ChangeDutyCycle(100)
        GPIO.output(self._pins['left_in1'],  GPIO.HIGH)
        GPIO.output(self._pins['left_in2'],  GPIO.HIGH)
        GPIO.output(self._pins['right_in1'], GPIO.HIGH)
        GPIO.output(self._pins['right_in2'], GPIO.HIGH)

    def cleanup(self) -> None:
        if self._pwm_left is not None:
            self._pwm_left.stop()
        if self._pwm_right is not None:
            self._pwm_right.stop()
        if self._gpio is not None:
            self._gpio.cleanup()
            self._gpio = None

    # ── internal ──────────────────────────────────────────────────────────────

    def _set_one(
        self,
        speed: float,
        pin_a: int,
        pin_b: int,
        pwm,
    ) -> None:
        GPIO = self._gpio
        speed = max(-1.0, min(1.0, speed))
        duty  = abs(speed) * 100.0

        if speed > 0:
            GPIO.output(pin_a, GPIO.HIGH)
            GPIO.output(pin_b, GPIO.LOW)
        elif speed < 0:
            GPIO.output(pin_a, GPIO.LOW)
            GPIO.output(pin_b, GPIO.HIGH)
        else:
            GPIO.output(pin_a, GPIO.LOW)
            GPIO.output(pin_b, GPIO.LOW)

        pwm.ChangeDutyCycle(duty)


# ── Mock driver (simulation / desktop testing) ────────────────────────────────

class MockPWMMotor(PWMMotorDriver):
    """
    Stub driver — no GPIO, stores last commanded speeds for inspection.
    Used when running on a non-Pi machine or when hardware is absent.
    """

    def __init__(self):
        self.left_speed  = 0.0
        self.right_speed = 0.0
        self.is_braking  = False

    def setup(self) -> None:
        pass

    def set_speeds(self, left: float, right: float) -> None:
        self.left_speed  = max(-1.0, min(1.0, left))
        self.right_speed = max(-1.0, min(1.0, right))
        self.is_braking  = False

    def stop(self) -> None:
        self.left_speed  = 0.0
        self.right_speed = 0.0
        self.is_braking  = False

    def brake(self) -> None:
        self.left_speed  = 0.0
        self.right_speed = 0.0
        self.is_braking  = True

    def cleanup(self) -> None:
        self.stop()


# ── Factory ────────────────────────────────────────────────────────────────────

def create_motor_driver(config: dict) -> PWMMotorDriver:
    """
    Factory used by motor_driver_node.

    config keys (from hardware_params.yaml):
        motor.driver      'l298n' | 'mock'
        motor.left_en     int   GPIO BCM pin
        motor.left_in1    int
        motor.left_in2    int
        motor.right_en    int
        motor.right_in1   int
        motor.right_in2   int
    """
    driver_type = config.get('driver', 'mock').lower()
    if driver_type == 'l298n':
        return L298NDriver(
            left_en   = config['left_en'],
            left_in1  = config['left_in1'],
            left_in2  = config['left_in2'],
            right_en  = config['right_en'],
            right_in1 = config['right_in1'],
            right_in2 = config['right_in2'],
        )
    elif driver_type == 'mock':
        return MockPWMMotor()
    else:
        raise ValueError(
            f"Unknown motor driver '{driver_type}'. Choose from: ['l298n', 'mock']"
        )
