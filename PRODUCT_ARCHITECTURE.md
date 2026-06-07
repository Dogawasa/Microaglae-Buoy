# Product Architecture

## System overview

This prototype is a modular floating microalgae biofilter for demonstration use. Each module is divided into two controlled layers:

1. Sealed algae cartridge  
   The upper transparent chamber holds microalgae in a closed environment for photosynthesis and oxygen support.

2. Water treatment chamber  
   The lower chamber receives incoming water, moves it through filters and treatment surfaces, and releases cleaner water back out.

## Data and control flow

1. Water enters through an intake screen.
2. ESP32 reads sensor values from the module.
3. Sensor data is sent to the AI server and dashboard.
4. The AI decides one of four main commands:
   - `TREAT`
   - `FLUSH`
   - `HOLD`
   - `LOCKOUT`
5. ESP32 controls the pump, optional aeration, grow light, and mixer.
6. The dashboard shows reasoning, safety alerts, and module state.

## Main subsystems

- Floating body / buoy frame
- Sealed microalgae cartridge
- Intake screen and outlet path
- Filter / treatment chamber
- ESP32 controller
- Sensor cluster
- Pump and relay / driver
- Optional aerator
- Battery / power system
- AI dashboard and local server

## Prototype command meanings

- `TREAT`: circulate water through the treatment chamber
- `FLUSH`: short cleaning cycle for the intake path
- `HOLD`: monitor only, no new treatment cycle
- `LOCKOUT`: stop the system for safety

## Suggested field-safe additions

- Cable glands
- Waterproof electronics box
- Fuse
- Buck converter
- Intake mesh
- Algae-retaining membrane
- Ballast or anchor rope
- Leak sensor
- Manual emergency switch
