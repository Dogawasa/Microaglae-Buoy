# Liquid3-Inspired Water Buoy Concept

## Short idea

This update combines the old microalgae buoy project with the new Liquid3-inspired idea.

The old project already had:

- ESP32 sensor reporting
- AI/backend decision logic
- GitHub Pages dashboard
- Water quality simulation buttons
- Safety commands: `HOLD`, `TREAT`, `FLUSH`, `LOCKOUT`
- Lower water treatment path with intake, filter, pump, sensors, and diffuser

The new idea adds:

- A Liquid3-style sealed microalgae photobioreactor on top of the buoy
- A clear chamber that lets sunlight reach the microalgae
- Oxygen transfer from the chamber to water using tubing, check valve, and diffuser
- A clearer project identity: **Liquid3 in water for Thailand**

## Main design rule

The algae must stay inside the sealed chamber.

The system should transfer oxygen support into water, but it should not release live microalgae directly into rivers, canals, or ponds.

## Updated system structure

1. Upper photobioreactor
   - Inspired by Liquid3
   - Holds microalgae in a closed clear chamber
   - Receives sunlight
   - Produces oxygen

2. Oxygen transfer path
   - Gas collector at the top of the chamber
   - Tubing
   - Check valve to prevent water backflow
   - Fine bubble diffuser or air stone under the buoy

3. Lower water treatment path
   - Intake screen
   - Filter / treatment chamber
   - Water flow path
   - Pump or controlled circulation

4. AI and sensor system
   - ESP32
   - DO, pH, turbidity, sunlight, and temperature sensors
   - Backend API
   - Dashboard
   - AI decision logic

## Updated pitch

This project adapts the Liquid3 microalgae photobioreactor idea into a floating water-treatment buoy for Thailand. Instead of cleaning air on land, the buoy uses a sealed microalgae chamber to produce oxygen support while the lower module monitors and treats polluted water using sensors, ESP32 control, and AI decision logic.

## Interactive model

Open:

```text
docs/liquid3-water-buoy-3d.html
```

This file shows the updated engineering-style 3D model and can be opened directly in a browser.
