"""
PID Controller implementation for HVAC control.

This module provides a standalone PID controller that can be used by any
equipment that needs feedback control (VAV boxes, AHUs, chillers, etc.).

The controller includes:
- Anti-windup protection
- Output clamping
- Deadband support
- Derivative smoothing

Usage:
    from src.controls.pid import PIDController
    from src.core.constants import DEFAULT_PID_KP, DEFAULT_PID_KI, DEFAULT_PID_KD

    pid = PIDController(kp=DEFAULT_PID_KP, ki=DEFAULT_PID_KI, kd=DEFAULT_PID_KD)
    output = pid.update(setpoint=72.0, measured=74.0)
"""

from typing import Optional
from src.core.constants import DEFAULT_PID_KP, DEFAULT_PID_KI, DEFAULT_PID_KD


class PIDController:
    """
    PID controller with anti-windup and derivative filtering.

    This controller uses the standard PID formula:
        output = Kp * error + Ki * integral(error) + Kd * derivative(error)

    Features:
        - Anti-windup: Limits integral accumulation when output is saturated
        - Output clamping: Ensures output stays within min/max bounds
        - Deadband: Prevents micro-adjustments for small errors
        - Derivative smoothing: Uses moving average to reduce noise sensitivity
    """

    def __init__(
        self,
        kp: float = DEFAULT_PID_KP,
        ki: float = DEFAULT_PID_KI,
        kd: float = DEFAULT_PID_KD,
        output_min: float = 0.0,
        output_max: float = 1.0,
        deadband: float = 0.5,
        integral_limit: float = 10.0,
    ) -> None:
        """
        Initialize PID controller.

        Args:
            kp: Proportional gain (default from constants)
            ki: Integral gain (default from constants)
            kd: Derivative gain (default from constants)
            output_min: Minimum output value (default 0.0)
            output_max: Maximum output value (default 1.0)
            deadband: Error deadband - no response below this (default 0.5)
            integral_limit: Maximum absolute value for integral term (default 10.0)
        """
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_min = output_min
        self.output_max = output_max
        self.deadband = deadband
        self.integral_limit = integral_limit

        # Internal state
        self._integral: float = 0.0
        self._last_error: Optional[float] = None
        self._last_output: float = 0.0

        # Derivative smoothing (3-sample moving average)
        self._error_history: list[float] = [0.0, 0.0, 0.0]
        self._history_index: int = 0

    def update(self, setpoint: float, measured: float, dt: float = 1.0) -> float:
        """
        Calculate PID output for one time step.

        Args:
            setpoint: Desired value
            measured: Current measured value
            dt: Time step (default 1.0 for normalized calculations)

        Returns:
            Control output, clamped to [output_min, output_max]
        """
        error = setpoint - measured

        # Apply deadband
        if abs(error) < self.deadband:
            error = 0.0

        # Proportional term
        p_term = self.kp * error

        # Integral term with anti-windup
        # Only integrate if output is not saturated, or if error is reducing
        if self._is_within_limits(self._last_output) or (error * self._integral < 0):
            self._integral += error * dt
            # Clamp integral to prevent excessive windup
            self._integral = max(-self.integral_limit, min(self.integral_limit, self._integral))

        i_term = self.ki * self._integral

        # Derivative term with smoothing
        if self._last_error is not None:
            raw_derivative = (error - self._last_error) / dt if dt > 0 else 0.0

            # Update moving average history
            self._error_history[self._history_index] = raw_derivative
            self._history_index = (self._history_index + 1) % len(self._error_history)

            # Calculate smoothed derivative
            smoothed_derivative = sum(self._error_history) / len(self._error_history)
            d_term = self.kd * smoothed_derivative
        else:
            d_term = 0.0

        self._last_error = error

        # Calculate total output
        output = p_term + i_term + d_term

        # Clamp output
        output = max(self.output_min, min(self.output_max, output))
        self._last_output = output

        return output

    def _is_within_limits(self, output: float) -> bool:
        """Check if output is within limits (not saturated)."""
        return self.output_min < output < self.output_max

    def reset(self) -> None:
        """Reset controller state."""
        self._integral = 0.0
        self._last_error = None
        self._last_output = 0.0
        self._error_history = [0.0, 0.0, 0.0]
        self._history_index = 0

    def set_gains(self, kp: float, ki: float, kd: float) -> None:
        """
        Update controller gains.

        Args:
            kp: New proportional gain
            ki: New integral gain
            kd: New derivative gain
        """
        self.kp = kp
        self.ki = ki
        self.kd = kd

    def set_output_limits(self, output_min: float, output_max: float) -> None:
        """
        Update output limits.

        Args:
            output_min: New minimum output
            output_max: New maximum output
        """
        self.output_min = output_min
        self.output_max = output_max

    @property
    def integral(self) -> float:
        """Current integral term accumulator."""
        return self._integral

    @property
    def last_output(self) -> float:
        """Last calculated output."""
        return self._last_output

    def __repr__(self) -> str:
        return (
            f"PIDController(kp={self.kp}, ki={self.ki}, kd={self.kd}, "
            f"limits=[{self.output_min}, {self.output_max}])"
        )
