# Product Architecture

## System overview

This prototype is a Liquid3-inspired floating microalgae biofilter for demonstration use. It adapts the idea of a land-based microalgae photobioreactor into a floating buoy for polluted water in Thailand.

Each module is divided into two controlled layers:

1. Liquid3-style sealed photobioreactor  
   The upper transparent chamber holds microalgae in a closed environment for photosynthesis and oxygen production. Oxygen is collected and routed toward the water through tubing and a diffuser. The algae itself remains contained.

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

In the updated concept, the upper photobioreactor behaves like a "Liquid3 in water" module, while the lower chamber keeps the original AI water-treatment buoy function.

## Main subsystems

- Floating body / buoy frame
- Sealed Liquid3-style microalgae photobioreactor
- Gas collector and oxygen tubing
- Check valve
- Fine bubble diffuser / air stone
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
