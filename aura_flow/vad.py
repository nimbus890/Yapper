from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class VadDecision:
    accepted: bool
    speech_seconds: float
    speech_ratio: float
    threshold: float
    reason: str


class EnergyVad:
    """Cheap first-pass VAD used to reject silence before model inference."""

    def __init__(self, sample_rate: int, rms_threshold: float, min_speech_seconds: float):
        self.sample_rate = sample_rate
        self.rms_threshold = rms_threshold
        self.min_speech_seconds = min_speech_seconds

    def analyze(self, audio: np.ndarray) -> VadDecision:
        frame_size = max(1, int(self.sample_rate * 0.03))
        usable = audio[: audio.size - (audio.size % frame_size)]
        if usable.size == 0:
            return VadDecision(False, 0.0, 0.0, self.rms_threshold, "recording is too short")
        frames = usable.reshape(-1, frame_size).astype(np.float64, copy=False)
        energies = np.sqrt(np.mean(np.square(frames), axis=1))
        noise_floor = float(np.percentile(energies, 20))
        speech_reference = float(np.percentile(energies, 80))
        # A recording can begin with continuous speech and contain no usable
        # silence sample. Cap the adaptive threshold below the likely speech
        # energy so a steady voice is not mistaken for steady background noise.
        threshold = max(self.rms_threshold, min(noise_floor * 2.75, speech_reference * 0.65))
        active = energies >= threshold
        speech_seconds = float(active.sum() * frame_size / self.sample_rate)
        ratio = float(active.mean())
        accepted = speech_seconds >= self.min_speech_seconds
        reason = "speech detected" if accepted else "not enough speech above the noise floor"
        return VadDecision(accepted, speech_seconds, ratio, threshold, reason)
