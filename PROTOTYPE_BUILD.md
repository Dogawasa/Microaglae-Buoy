# Prototype Build

## Prototype target

This version is a `Prototype Demo` for school presentation and controlled testing, not a long-term river deployment.

## Recommended build order

1. Build the floating frame
2. Install the sealed algae cartridge on the top layer
3. Build the lower treatment chamber and water path
4. Add intake screen, tubing, and outlet
5. Install pump and relay / driver
6. Mount ESP32 and waterproof the electronics box
7. Connect sensors
8. Upload Arduino code
9. Run the AI dashboard
10. Test with clear water, low oxygen simulation, turbid water, and unsafe pH

## Required core hardware

- ESP32 dev board
- pH sensor
- turbidity sensor
- DO sensor
- light sensor
- waterproof temperature sensor
- DC water pump
- relay or MOSFET driver
- floating body or foam pontoons
- clear acrylic algae chamber
- tubing and fittings
- battery pack

## Strongly recommended extra hardware

- Waterproof enclosure
- Cable glands
- Fuse
- 12V to 5V buck converter
- Intake screen / debris guard
- Fine filter media
- Algae-retaining membrane
- Ballast weight
- Anchor rope
- Leak sensor
- Manual power switch

## Demo test sequence

1. Start the dashboard
2. Open the simulation controls
3. Show `Clear` -> system stays in `HOLD`
4. Show `Treat` -> pump runs treatment cycle
5. Show `Dark` -> treatment still runs with aeration support
6. Show `Clog` -> system runs `FLUSH`
7. Show `pH` -> system enters `LOCKOUT`
8. Show `Service` -> maintenance alert for the algae cartridge
