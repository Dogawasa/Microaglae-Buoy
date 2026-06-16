# Microalgae River Oxygenation Project Upgrade Plan

## Stronger project concept

Your original idea is good: use microalgae as a living photosynthesis system, then use sensors and AI to decide when the machine should help the river. The safest upgraded version is a floating contained photobioreactor, not a device that freely releases algae.

The ball can still float on the water. The top transparent half holds the microalgae culture and catches sunlight. The lower half holds sensors, battery, pump, filters, and the water-contact system. When the AI sees low dissolved oxygen and good sunlight, it runs a pump to circulate river water through or around the sealed algae chamber so oxygen can transfer into the water. The algae stays inside the machine.

## Why not automatic algae release

Releasing living algae into a real river can create ecological problems. Too much algal growth can reduce oxygen later when the algae dies and decomposes, and some blooms can harm aquatic life or people. Government sources describe nutrient-driven algae blooms as a cause of low oxygen and harmful algal blooms, so a school prototype should show containment and permission-based testing.

Good project sentence:

> This project uses contained microalgae photosynthesis and AI-controlled oxygenation to support low-oxygen water without automatically introducing organisms into the environment.

## Physical design

Top chamber:
- Clear acrylic/polycarbonate dome for sunlight.
- Microalgae culture in a sealed cartridge.
- Internal gentle mixer so algae does not settle.
- Optional low-power grow LEDs for indoor/tank demos.
- Sampling cap for school lab measurements.

Middle barrier:
- Waterproof electronics wall.
- Gas/water exchange design that prevents algae escape.
- Service hatch with gasket.

Lower chamber:
- pH sensor.
- Turbidity sensor.
- Dissolved oxygen sensor.
- Light sensor on top-facing surface.
- Optional temperature sensor, because dissolved oxygen depends strongly on temperature.
- Pump for contained oxygenation.
- Intake screen to stop leaves/debris.
- Outlet diffuser to spread oxygenated water gently.

Power:
- ESP32.
- 12 V battery.
- 5 V buck converter for ESP32.
- Fuse and waterproof switch.
- Optional solar charging module.

## Better AI decision logic

The first version releases when all values are "good." For your real goal, the system should act when oxygen is low but safety conditions are acceptable.

Improved rules:
- If sensor values are impossible, lock out.
- If pH is far outside the safe range, lock out.
- If turbidity is too high, hold because light cannot penetrate well and the pump may clog.
- If dissolved oxygen is low and sunlight is good, run contained oxygenation.
- If dissolved oxygen is low at night, do not rely on algae because algae can respire in darkness. Use mechanical aeration or wait for sunlight.
- If oxygen is already good, hold and keep monitoring.
- Use a cooldown so the pump does not run every sensor cycle.
- Keep open release disabled unless a teacher/supervisor and local authority approve a contained test.

## Files I improved

- `improved_algae_bioreactor.ino`: ESP32 firmware with sensor smoothing, pump cooldown, JSON server response parsing, contained oxygenation mode, and open-release lockout.
- `improved_ai_server.py`: Flask server with safer decision logic, sensor lockouts, cooldown, manual lock, simulation endpoint, and a dashboard.

## Testing plan

1. Dry electronics test:
   - Power ESP32 from USB.
   - Confirm WiFi connects.
   - Confirm dashboard opens.
   - Click Simulate and check that the dashboard updates.

2. Sensor cup test:
   - Test pH in known buffer solutions.
   - Test turbidity with clear water and cloudy water.
   - Compare dissolved oxygen readings with a manual DO kit if possible.

3. Closed tank test:
   - Use a bucket or aquarium, not a river.
   - Keep algae inside the sealed chamber.
   - Record DO before, during, and after oxygenation cycles.
   - Compare sunlight vs shade.

4. Field demonstration:
   - Float the sealed device without releasing algae.
   - Log sensor data and AI decisions.
   - Use the project as a monitoring and oxygenation prototype.

## Presentation structure

Problem:
Many rivers can suffer from low dissolved oxygen, especially when pollution or excess nutrients disturb the ecosystem.

Idea:
Microalgae photosynthesis can produce oxygen using sunlight.

Engineering solution:
A floating ball-shaped photobioreactor uses sensors and AI decision rules to decide when contained oxygenation should run.

Safety improvement:
The algae is contained. The prototype helps oxygen transfer without automatically releasing organisms into the river.

Data:
The dashboard shows pH, turbidity, dissolved oxygen, sunlight, AI command, oxygen need, safety state, and history.

Future work:
Add temperature compensation, solar charging, waterproof enclosure testing, a flow sensor, and real calibration data.

## Useful references

- EPA nutrient pollution overview: https://www.epa.gov/nutrientpollution
- EPA effects of dead zones and harmful algal blooms: https://www.epa.gov/nutrientpollution/effects-dead-zones-and-harmful-algal-blooms
- EPA harmful algae, cyanobacteria, and cyanotoxins: https://www.epa.gov/habs/learn-about-harmful-algae-cyanobacteria-and-cyanotoxins
- NOAA explanation of harmful algal blooms: https://oceanservice.noaa.gov/facts/habharm.html
- U.S. Fish & Wildlife Service invasive species warning: https://www.fws.gov/story/dont-let-it-loose
