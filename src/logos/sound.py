# src/logos/sound.py

"""
My auditory synthesis and sound production module. 🔊

This module allows me to generate mathematical wave shapes (sine, square,
triangle, sawtooth, noise), shape them using ADSR envelopes, parse scientific
music notation, play gapless melodies, and trigger prebuilt dynamic chimes.
"""

import time
import threading
from typing import List, Dict, Any, Optional, Union, Tuple

from .core import api_call, Verbosity, check_for_interrupt

# Gated imports to prevent startup crashes when running offline or linting
try:
    import numpy as np
    import sounddevice as sd
    _HAS_SOUND = True
except ImportError:
    _HAS_SOUND = False

__all__ = [
    "beep",
    "play_melody",
    "play_waveform",
    "chime",
    "SoundTask",
    "note_to_freq",
    "sine",
    "square",
    "triangle",
    "sawtooth",
    "noise",
    "apply_adsr",
]

# Standard note name mapping to semitones from C0
_NOTE_SEMITONES = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4,
    'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8, 'Ab': 8, 'A': 9,
    'A#': 10, 'Bb': 10, 'B': 11
}

def note_to_freq(note_name: str) -> float:
    """Convert scientific pitch notation (e.g., 'A4', 'C#5', 'Eb3') to frequency in Hz.
    
    I use this to parse music notes written in text format into exact frequencies.
    It supports sharps (#), flats (b), and octaves. Rest notes ('R' or 'rest') return 0.0.
    
    Args:
        note_name: The note string (e.g. 'A4', 'C#5', 'Eb3', 'R').
        
    Returns:
        The frequency in Hertz, or 0.0 for a rest.
        
    Note to self:
        Reference pitch is A4 = 440.0Hz. Octave numbers start at C.
    """
    cleaned = note_name.strip().upper()
    if cleaned in ('R', 'REST'):
        return 0.0
        
    if not cleaned:
        return 0.0
        
    if cleaned[-1].isdigit():
        octave = int(cleaned[-1])
        pitch = cleaned[:-1]
    else:
        octave = 4  # Default octave
        pitch = cleaned
        
    if pitch not in _NOTE_SEMITONES:
        raise ValueError(f"Unknown note pitch name: {pitch}")
        
    # Calculate semitones relative to C0
    # C0 is 12 * 0 = 0 semitones. A4 is 9 semitones above C4.
    # Semitones from C0 = (octave * 12) + note_semitone
    # Standard formula: freq = 440.0 * 2^((semitones - 57) / 12)
    # A4 is 57 semitones from C0 (9 + 4 * 12 = 57)
    semitones = (octave * 12) + _NOTE_SEMITONES[pitch]
    freq = 440.0 * (2.0 ** ((semitones - 57) / 12.0))
    return freq


def sine(frequency: float, duration: float, sample_rate: int = 44100) -> 'np.ndarray':
    """Generate a sine wave array.
    
    Creates a pure tone wave. Extremely smooth and useful for clear chimes or pads.
    
    Args:
        frequency: Pitch frequency in Hz.
        duration: Duration of the wave in seconds.
        sample_rate: Audio sampling rate.
        
    Returns:
        A 1D float32 numpy array representing the waveform.
    """
    if not _HAS_SOUND:
        return np.array([], dtype=np.float32)
    if frequency <= 0.0 or duration <= 0.0:
        return np.zeros(int(sample_rate * duration), dtype=np.float32)
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    return np.sin(2 * np.pi * frequency * t).astype(np.float32)


def square(frequency: float, duration: float, sample_rate: int = 44100) -> 'np.ndarray':
    """Generate a square wave array.
    
    Creates a retro, hollow, or buzzy tone wave. Great for arcade sounds or warning alerts.
    
    Args:
        frequency: Pitch frequency in Hz.
        duration: Duration of the wave in seconds.
        sample_rate: Audio sampling rate.
        
    Returns:
        A 1D float32 numpy array representing the waveform.
    """
    if not _HAS_SOUND:
        return np.array([], dtype=np.float32)
    if frequency <= 0.0 or duration <= 0.0:
        return np.zeros(int(sample_rate * duration), dtype=np.float32)
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    return np.sign(np.sin(2 * np.pi * frequency * t)).astype(np.float32)


def triangle(frequency: float, duration: float, sample_rate: int = 44100) -> 'np.ndarray':
    """Generate a triangle wave array.
    
    Creates a mellow, soft buzz that contains only odd harmonics. Good for woodwind-like notes.
    
    Args:
        frequency: Pitch frequency in Hz.
        duration: Duration of the wave in seconds.
        sample_rate: Audio sampling rate.
        
    Returns:
        A 1D float32 numpy array representing the waveform.
    """
    if not _HAS_SOUND:
        return np.array([], dtype=np.float32)
    if frequency <= 0.0 or duration <= 0.0:
        return np.zeros(int(sample_rate * duration), dtype=np.float32)
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    return (2.0 * np.abs(2.0 * (t * frequency - np.floor(t * frequency + 0.5))) - 1.0).astype(np.float32)


def sawtooth(frequency: float, duration: float, sample_rate: int = 44100) -> 'np.ndarray':
    """Generate a sawtooth wave array.
    
    Creates a bright, rich wave containing all harmonics. Excellent for brassy sounds or sweeps.
    
    Args:
        frequency: Pitch frequency in Hz.
        duration: Duration of the wave in seconds.
        sample_rate: Audio sampling rate.
        
    Returns:
        A 1D float32 numpy array representing the waveform.
    """
    if not _HAS_SOUND:
        return np.array([], dtype=np.float32)
    if frequency <= 0.0 or duration <= 0.0:
        return np.zeros(int(sample_rate * duration), dtype=np.float32)
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    return (2.0 * (t * frequency - np.floor(t * frequency + 0.5))).astype(np.float32)


def noise(duration: float, sample_rate: int = 44100) -> 'np.ndarray':
    """Generate a white noise array.
    
    Creates uniform random noise. Perfect for pings, clicks, static, or wind sounds.
    
    Args:
        duration: Duration in seconds.
        sample_rate: Audio sampling rate.
        
    Returns:
        A 1D float32 numpy array representing the waveform.
    """
    if not _HAS_SOUND:
        return np.array([], dtype=np.float32)
    if duration <= 0.0:
        return np.array([], dtype=np.float32)
    return np.random.uniform(-1.0, 1.0, int(sample_rate * duration)).astype(np.float32)


def apply_adsr(
    waveform: 'np.ndarray',
    attack: float,
    decay: float,
    sustain: float,
    release: float,
    duration: float,
    sample_rate: int = 44100
) -> 'np.ndarray':
    """Apply an Attack-Decay-Sustain-Release envelope to a waveform.
    
    Shapes the volume of the sound over time to mimic organic instruments and avoid popping.
    
    Args:
        waveform: The input 1D float32 numpy array.
        attack: Time in seconds to ramp volume from 0 to 1.
        decay: Time in seconds to decay volume from 1 to sustain level.
        sustain: Volume level (0.0 to 1.0) to hold during key hold phase.
        release: Time in seconds to ramp volume from sustain level to 0 at the end.
        duration: Total duration of the sound.
        sample_rate: Audio sampling rate.
        
    Returns:
        The envelope-shaped float32 array.
        
    Note to self:
        If total envelope segments exceed the duration, we scale them proportionally.
    """
    if not _HAS_SOUND or len(waveform) == 0:
        return waveform
        
    n_total = len(waveform)
    
    # Scale envelope phases if they exceed the duration
    total_env_time = attack + decay + release
    if total_env_time > duration:
        scale = duration / (total_env_time + 1e-6)
        attack *= scale
        decay *= scale
        release *= scale
        
    n_attack = int(attack * sample_rate)
    n_decay = int(decay * sample_rate)
    n_release = int(release * sample_rate)
    n_sustain = n_total - (n_attack + n_decay + n_release)
    
    if n_sustain < 0:
        n_sustain = 0
        # Re-adjust phases to fit exactly
        total_phases = attack + decay + release + 1e-6
        n_attack = int(n_total * (attack / total_phases))
        n_decay = int(n_total * (decay / total_phases))
        n_release = n_total - n_attack - n_decay
        
    # Attack ramp (0 -> 1)
    env_attack = np.linspace(0.0, 1.0, n_attack, dtype=np.float32) if n_attack > 0 else np.array([], dtype=np.float32)
    # Decay ramp (1 -> sustain)
    env_decay = np.linspace(1.0, sustain, n_decay, dtype=np.float32) if n_decay > 0 else np.array([], dtype=np.float32)
    # Sustain flat line
    env_sustain = np.full(n_sustain, sustain, dtype=np.float32) if n_sustain > 0 else np.array([], dtype=np.float32)
    # Release ramp (sustain -> 0)
    env_release = np.linspace(sustain, 0.0, n_release, dtype=np.float32) if n_release > 0 else np.array([], dtype=np.float32)
    
    envelope = np.concatenate([env_attack, env_decay, env_sustain, env_release])
    
    # Pad or trim to match waveform length exactly
    if len(envelope) < n_total:
        envelope = np.pad(envelope, (0, n_total - len(envelope)), 'constant')
    elif len(envelope) > n_total:
        envelope = envelope[:n_total]
        
    return waveform * envelope


class SoundTask:
    """A handle for monitoring and controlling an active playback.
    
    I use this to check if a sound is still playing, inspect its progress,
    cancel it midway, or wait for it to complete.
    """
    def __init__(self, stream: Optional['sd.OutputStream'], duration: float):
        self._stream = stream
        self._duration = duration
        self._start_time = time.time()
        self._canceled = False
        
    def is_active(self) -> bool:
        """Check if the sound is currently playing from the physical speakers.
        
        Returns:
            True if playing, False if completed or stopped.
        """
        if not _HAS_SOUND or self._stream is None or self._canceled:
            return False
        try:
            return self._stream.active
        except Exception:
            return False
            
    def progress(self) -> float:
        """Estimate the playback progress as a fraction from 0.0 to 1.0.
        
        Returns:
            The progress ratio.
        """
        if self._duration <= 0.0:
            return 1.0
        elapsed = time.time() - self._start_time
        return max(0.0, min(1.0, elapsed / self._duration))
        
    def cancel(self) -> None:
        """Cancel this playback immediately.
        
        Note to self:
            This stops all global playbacks managed by sounddevice.
        """
        if not _HAS_SOUND:
            return
        if self.is_active():
            self._canceled = True
            sd.stop()
            
    def wait(self) -> None:
        """Block execution until the playback completes or is cancelled.
        
        Note to self:
            This is cooperative and yields to global robot interrupts.
        """
        if not _HAS_SOUND or self._stream is None:
            return
        while self.is_active():
            check_for_interrupt()
            time.sleep(0.01)


def _get_default_volume() -> float:
    import logos
    try:
        return logos.config.merged.sound.default_volume
    except AttributeError:
        return 0.5


def _get_sample_rate() -> int:
    import logos
    try:
        return logos.config.merged.sound.sample_rate
    except AttributeError:
        return 44100


@api_call(default_verbosity=Verbosity.ACK)
def play_waveform(
    waveform_data: 'np.ndarray',
    sample_rate: Optional[int] = None,
    volume: Optional[float] = None,
    wait: bool = True
) -> SoundTask:
    """Play back a raw NumPy array containing audio data.
    
    This is my low-level entrypoint for playing arbitrary synthesized sound arrays.
    It normalizes input data, applies volume scaling, starts the PortAudio stream,
    and returns a SoundTask.
    
    Args:
        waveform_data: The 1D float32 array of sample values (-1.0 to 1.0).
        sample_rate: Samples per second. If None, inherits from config (default 44100).
        volume: Volume multiplier override (0.0 to 1.0). If None, inherits default.
        wait: If True, blocks until playback finishes.
        
    Returns:
        A SoundTask handle to manage playback.
    """
    if not _HAS_SOUND:
        print("Sound Device Error: sounddevice or numpy is unavailable.")
        return SoundTask(None, 0.0)
        
    if sample_rate is None:
        sample_rate = _get_sample_rate()
    if volume is None:
        volume = _get_default_volume()
        
    if len(waveform_data) == 0:
        return SoundTask(None, 0.0)
        
    # Scale volume and convert to float32
    audio_data = waveform_data.astype(np.float32) * float(volume)
    
    # Clip to prevent digital clipping/distortion
    audio_data = np.clip(audio_data, -1.0, 1.0)
    
    duration = len(audio_data) / sample_rate
    
    # sd.play stops any currently running playbacks
    sd.play(audio_data, sample_rate)
    
    # Capture the active output stream
    try:
        stream = sd.get_stream()
    except RuntimeError:
        stream = None
        
    task = SoundTask(stream, duration)
    
    if wait:
        task.wait()
        
    return task


@api_call(default_verbosity=Verbosity.BRIEF)
def beep(
    frequency: float = 440.0,
    duration: float = 0.5,
    waveform: str = 'sine',
    volume: Optional[float] = None,
    wait: bool = True
) -> SoundTask:
    """Play a single pitch tone with a soft envelope to prevent clicks.
    
    Creates a simple tone using one of the primary wave shapes. Useful for
    sonifying UI actions, clicks, or pings.
    
    Args:
        frequency: Pitch frequency in Hz.
        duration: Playback duration in seconds.
        waveform: Oscillator type ('sine', 'square', 'triangle', 'sawtooth', 'noise').
        volume: Volume level override (0.0 to 1.0).
        wait: If True, blocks until finished.
        
    Returns:
        A SoundTask handle.
    """
    if not _HAS_SOUND:
        print(f"Sound Device Error: Cannot beep {frequency}Hz (sounddevice missing).")
        return SoundTask(None, 0.0)
        
    sample_rate = _get_sample_rate()
    
    w_type = waveform.lower()
    if w_type == 'sine':
        wave_arr = sine(frequency, duration, sample_rate)
    elif w_type == 'square':
        wave_arr = square(frequency, duration, sample_rate)
    elif w_type == 'triangle':
        wave_arr = triangle(frequency, duration, sample_rate)
    elif w_type == 'sawtooth':
        wave_arr = sawtooth(frequency, duration, sample_rate)
    elif w_type == 'noise':
        wave_arr = noise(duration, sample_rate)
    else:
        raise ValueError(f"Unknown waveform type: {waveform}")
        
    # Apply a quick 10ms ADSR/fade to prevent pops
    fade_time = min(0.01, duration * 0.1)
    wave_arr = apply_adsr(
        wave_arr,
        attack=fade_time,
        decay=0.0,
        sustain=1.0,
        release=fade_time,
        duration=duration,
        sample_rate=sample_rate
    )
    
    return play_waveform(wave_arr, sample_rate, volume, wait=wait)


@api_call(default_verbosity=Verbosity.ACK)
def play_melody(
    melody: Union[str, List[Tuple[str, float]]],
    tempo: float = 120,
    waveform: str = 'sine',
    volume: Optional[float] = None,
    wait: bool = True
) -> SoundTask:
    """Play a sequence of notes gaplessly with tempo mapping.
    
    Accepts note sequences in scientific notation. Renders them to a single
    continuous array with fast crossfades between note boundaries to avoid clicks.
    
    Args:
        melody: Space-separated note strings ('C4:1 D4:1' where :beats is optional)
                or a list of (note, beats) tuples. R/REST specifies a rest.
        tempo: Beats per minute (defines duration of 1 beat).
        waveform: Oscillator type ('sine', 'square', 'triangle', 'sawtooth', 'noise').
        volume: Volume override (0.0 to 1.0).
        wait: If True, blocks until melody finishes.
        
    Returns:
        A SoundTask handle.
    """
    if not _HAS_SOUND:
        print("Sound Device Error: Cannot play melody (sounddevice missing).")
        return SoundTask(None, 0.0)
        
    note_list = []
    if isinstance(melody, str):
        tokens = melody.split()
        for token in tokens:
            if not token:
                continue
            if ":" in token:
                note_part, dur_part = token.split(":", 1)
                try:
                    dur = float(dur_part)
                except ValueError:
                    dur = 1.0
            else:
                note_part = token
                dur = 1.0
            note_list.append((note_part, dur))
    elif isinstance(melody, list):
        note_list = melody
    else:
        raise TypeError("Melody must be a space-separated string or a list of (note, beats) tuples.")
        
    sample_rate = _get_sample_rate()
    beat_duration = 60.0 / tempo
    wave_list = []
    
    for note, beats in note_list:
        note_seconds = beats * beat_duration
        if note_seconds <= 0.0:
            continue
            
        freq = note_to_freq(note)
        
        if freq == 0.0:
            # Rest note is absolute silence
            note_wave = np.zeros(int(sample_rate * note_seconds), dtype=np.float32)
        else:
            w_type = waveform.lower()
            if w_type == 'sine':
                note_wave = sine(freq, note_seconds, sample_rate)
            elif w_type == 'square':
                note_wave = square(freq, note_seconds, sample_rate)
            elif w_type == 'triangle':
                note_wave = triangle(freq, note_seconds, sample_rate)
            elif w_type == 'sawtooth':
                note_wave = sawtooth(freq, note_seconds, sample_rate)
            elif w_type == 'noise':
                note_wave = noise(note_seconds, sample_rate)
            else:
                raise ValueError(f"Unknown waveform type: {waveform}")
                
            # Apply a quick 5ms fade-in/out to prevent clicks between adjacent notes
            fade_time = min(0.005, note_seconds * 0.1)
            note_wave = apply_adsr(
                note_wave,
                attack=fade_time,
                decay=0.0,
                sustain=1.0,
                release=fade_time,
                duration=note_seconds,
                sample_rate=sample_rate
            )
            
        wave_list.append(note_wave)
        
    if not wave_list:
        return SoundTask(None, 0.0)
        
    melody_wave = np.concatenate(wave_list)
    return play_waveform(melody_wave, sample_rate, volume, wait=wait)


@api_call(default_verbosity=Verbosity.ACK)
def chime(
    name: str,
    volume: Optional[float] = None,
    wait: bool = True
) -> SoundTask:
    """Play a premium, prebuilt algorithmic chime sound effect.
    
    Generates complex sound effects dynamically using layered chords, detuned
    oscillators, or frequency sweeps. No audio asset files required.
    
    Supported chime names:
      - 'startup': Ascending major triad arpeggio building into a sustained chord.
      - 'success': Cheerful ascending major 7th chord arpeggio with high decay.
      - 'error': Detuned low buzz beating (90Hz + 93Hz) mimicking warning buzzer.
      - 'warning': Two rapid 800Hz warning alert beeps.
      - 'alert': High-pitched modular frequency sweep siren.
      - 'thinking': Soft, warm, pentatonic bubble ping texture.
      - 'scan': Sonic chirp sweeping downward rapidly.
      - 'click': Short, sharp click pop.
      
    Args:
        name: The chime identifier string.
        volume: Volume level override (0.0 to 1.0).
        wait: If True, blocks until the chime finishes.
        
    Returns:
        A SoundTask handle.
    """
    if not _HAS_SOUND:
        print(f"Sound Device Error: Cannot play chime '{name}' (sounddevice missing).")
        return SoundTask(None, 0.0)
        
    sample_rate = _get_sample_rate()
    c_name = name.lower().strip()
    
    if c_name == 'startup':
        # C major arpeggio sustained build-up
        duration = 1.6
        total_samples = int(sample_rate * duration)
        y = np.zeros(total_samples, dtype=np.float32)
        
        # Note, start delay, frequency, volume weight
        voices = [
            (1.2, 0.0, 261.63, 0.3),  # C4
            (1.05, 0.15, 329.63, 0.3), # E4
            (0.9, 0.30, 392.00, 0.3),  # G4
            (1.05, 0.45, 523.25, 0.4), # C5
        ]
        for note_dur, start_t, freq, weight in voices:
            start_sample = int(sample_rate * start_t)
            t = np.linspace(0, note_dur, int(sample_rate * note_dur), endpoint=False)
            w = np.sin(2 * np.pi * freq * t)
            w = apply_adsr(w, 0.05, 0.3, 0.3, 0.5, note_dur, sample_rate)
            y[start_sample:start_sample+len(w)] += w * weight
            
    elif c_name == 'success':
        # Ascending major 7th arpeggio
        duration = 1.0
        total_samples = int(sample_rate * duration)
        y = np.zeros(total_samples, dtype=np.float32)
        voices = [
            (duration - 0.0, 0.0, 523.25, 0.25),  # C5
            (duration - 0.08, 0.08, 659.25, 0.25), # E5
            (duration - 0.16, 0.16, 783.99, 0.25), # G5
            (duration - 0.24, 0.24, 987.77, 0.25), # B5
            (duration - 0.32, 0.32, 1046.50, 0.3), # C6
        ]
        for note_dur, start_t, freq, weight in voices:
            start_sample = int(sample_rate * start_t)
            t = np.linspace(0, note_dur, int(sample_rate * note_dur), endpoint=False)
            w = np.sin(2 * np.pi * freq * t)
            w = apply_adsr(w, 0.02, 0.1, 0.4, 0.3, note_dur, sample_rate)
            y[start_sample:start_sample+len(w)] += w * weight
            
    elif c_name == 'error':
        # Detuned warning buzz beating
        duration = 0.8
        total_samples = int(sample_rate * duration)
        t = np.linspace(0, duration, total_samples, endpoint=False)
        w1 = np.sign(np.sin(2 * np.pi * 90.0 * t))
        w2 = np.sign(np.sin(2 * np.pi * 93.0 * t))
        w = (w1 + w2) * 0.5
        w = apply_adsr(w, 0.01, 0.2, 0.2, 0.4, duration, sample_rate)
        y = w * 0.5
        
    elif c_name == 'warning':
        # Double warning beep pings
        duration = 0.4
        total_samples = int(sample_rate * duration)
        y = np.zeros(total_samples, dtype=np.float32)
        
        # Pulse 1
        t1 = np.linspace(0, 0.12, int(sample_rate * 0.12), endpoint=False)
        w1 = np.sign(np.sin(2 * np.pi * 800.0 * t1))
        w1 = apply_adsr(w1, 0.01, 0.02, 0.8, 0.03, 0.12, sample_rate)
        y[0:len(w1)] += w1 * 0.4
        
        # Pulse 2
        start_2 = int(sample_rate * 0.18)
        t2 = np.linspace(0, 0.12, int(sample_rate * 0.12), endpoint=False)
        w2 = np.sign(np.sin(2 * np.pi * 800.0 * t2))
        w2 = apply_adsr(w2, 0.01, 0.02, 0.8, 0.03, 0.12, sample_rate)
        y[start_2:start_2+len(w2)] += w2 * 0.4
        
    elif c_name == 'alert':
        # High pitched FM sweep siren
        duration = 1.2
        total_samples = int(sample_rate * duration)
        t = np.linspace(0, duration, total_samples, endpoint=False)
        mod_freq = 3.0
        phase = 2.0 * np.pi * (1000.0 * t - (300.0 / (2.0 * np.pi * mod_freq)) * np.cos(2.0 * np.pi * mod_freq * t))
        w = np.sin(phase)
        y = apply_adsr(w, 0.05, 0.1, 0.8, 0.15, duration, sample_rate) * 0.4
        
    elif c_name == 'thinking':
        # Soft pentatonic ambient bubbles
        duration = 1.5
        total_samples = int(sample_rate * duration)
        y = np.zeros(total_samples, dtype=np.float32)
        voices = [
            (duration - 0.0, 0.0, 659.25, 0.12),  # E5
            (duration - 0.2, 0.2, 880.00, 0.12),  # A5
            (duration - 0.4, 0.4, 987.77, 0.12),  # B5
            (duration - 0.6, 0.6, 1318.51, 0.12), # E6
        ]
        for note_dur, start_t, freq, weight in voices:
            start_sample = int(sample_rate * start_t)
            t = np.linspace(0, note_dur, int(sample_rate * note_dur), endpoint=False)
            w = np.sin(2 * np.pi * freq * t)
            w = apply_adsr(w, 0.15, 0.3, 0.2, 0.5, note_dur, sample_rate)
            y[start_sample:start_sample+len(w)] += w * weight
            
    elif c_name == 'scan':
        # Sonar sweep (linear chirp)
        duration = 0.6
        total_samples = int(sample_rate * duration)
        t = np.linspace(0, duration, total_samples, endpoint=False)
        f0, f1 = 2000.0, 400.0
        phase = 2.0 * np.pi * (f0 * t + 0.5 * (f1 - f0) * (t**2) / duration)
        w = np.sin(phase)
        y = apply_adsr(w, 0.01, 0.1, 0.2, 0.45, duration, sample_rate) * 0.35
        
    elif c_name == 'click':
        # Tactile short click (fast decaying sine)
        duration = 0.03
        total_samples = int(sample_rate * duration)
        t = np.linspace(0, duration, total_samples, endpoint=False)
        w = np.sin(2.0 * np.pi * 1200.0 * t) * np.exp(-300.0 * t)
        y = apply_adsr(w, 0.001, 0.005, 0.0, 0.01, duration, sample_rate) * 0.5
        
    else:
        raise ValueError(f"Unknown chime name: {name}. Supported chimes: startup, success, error, warning, alert, thinking, scan, click")
        
    return play_waveform(y, sample_rate, volume, wait=wait)
