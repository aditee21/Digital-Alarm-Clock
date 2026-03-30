# ** Digital Alarm Clock**
A lightweight desktop alarm clock built with Python and Tkinter that incorporates rule-based AI concepts such as automated scheduling and decision logic. Designed without external dependencies, relying entirely on Python’s standard library.

## ** FEATURES**

Analog + digital clock: live dial with sweeping seconds arc, blinking colon, and a day-of-week strip that highlights today.

Multiple alarms — add as many as you need, each with its own time, repeat rule, label, and sound toggle.

Repeat modes — Once, Daily, Weekdays, or Weekends

Alarm cards — colour-coded by status (active / inactive / ringing), with a toggle and delete button on each

Audio — synthesised entirely in Python; no sound files needed

Persistent — alarms are saved to alarms.json next to the script and reload automatically on next launch

## Requirements

Python 3.7 or newer

tkinter (ships with Python on Windows and macOS; on Linux: sudo apt install python3-tk)

Nothing else — no pip, no virtualenv

## run it 
 
```bash
python alarm_clock.py
```
 
 ## How audio works
 
The beep is synthesised sample-by-sample using the `wave` module and played through whatever the OS provides:
 
| Platform | Player used |
|----------|-------------|
| Windows  | `winsound` (Python stdlib) |
| macOS    | `afplay` (built into macOS) |
| Linux    | `aplay` → `paplay` → `ffplay` (first one found) |
| Fallback | terminal bell (`\a`) |
 
No sound files are bundled or downloaded.
 
 ## alarms file
 
Alarms are stored as plain JSON in `alarms.json` in the same folder as the script. You can edit it by hand if you want — the structure is straightforward:
 
```json
[
  {
    "id": 1719000000000,
    "time": "07:30",
    "label": "Morning",
    "repeat": "weekdays",
    "sound": true,
    "active": true
  }
]
```
## PROJECT STRUCTURE
 
```
alarm_clock.py   — entire application, single file
alarms.json      — created automatically on first save
README.md        — this file
```
## User Interface
<img width="749" height="1124" alt="image" src="https://github.com/user-attachments/assets/bb670345-556f-4da0-acc8-d2ae582d5f11" />


KNOWN LIMITATIONS
 
 Window size is fixed at 500 × 820 px and cannot be resized
 On Linux, audio requires at least one of `aplay`, `paplay`, or `ffplay` — most desktop distros include `aplay` via `alsa-utils` by default
 There is no snooze; the only option when an alarm rings is to dismiss it
 
