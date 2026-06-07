# Microalgae Project Upgrade Plan

## Safer concept direction

This project should use a **closed or controlled microalgae system** instead of releasing live algae directly into a river. The buoy acts as a modular water-treatment unit that improves water quality while keeping the algae contained.

## Core design

### 1. Upper algae production / photosynthesis section
- Located at the top of the buoy
- Uses transparent material to receive sunlight
- Contains microalgae or dense algae biofilm in a closed chamber
- Supports oxygen production and algae growth without releasing organisms into the river

### 2. Lower treatment section
- Located in the lower half of the buoy
- Water flows through this section or is pumped through it
- Improves dissolved oxygen and helps reduce excess nutrients
- Designed for modular connection with other buoys

## System workflow

1. Water enters the buoy treatment inlet.
2. Sensors measure DO, pH, turbidity, sunlight, temperature, and film density.
3. AI evaluates current water quality.
4. The system decides whether to increase flow, aerate, hold, or lock out.
5. Treated water exits the buoy with improved quality.
6. The system reduces activity when water quality is already good.

## AI role

The AI acts as a **smart control system**, not only an algae-production system.

### Example decisions

| Water condition | AI decision |
|---|---|
| DO low + enough sunlight | Increase treatment flow |
| DO low + low sunlight | Use aeration and reduce algae reliance |
| Water very turbid | Reduce flow to prevent clogging |
| pH abnormal | Temporary lockout for safety |
| Water quality good | Hold / save power |
| Biofilm too dense | Harvest / replace film warning |

## Improved architecture

- ESP32 reads sensors and controls actuators
- Flask AI server analyzes incoming data
- Web dashboard displays Thai-language status and AI reasoning
- Adaptive reporting reduces unnecessary updates
- Water image analysis adds visual evidence for the project

## Presentation message

This project is a modular floating microalgae water-treatment buoy that uses a closed algae chamber, sensor monitoring, and AI-based decision making to improve water quality in a safer and more controlled way.
