# Mobile touch-control SVG set

Original vector control assets prepared against the visual direction of the Google Play reference for **Mortal Company: Co-op Horror**.

## Visual language
- Lightweight white line icons, rounded caps and joins.
- Circular, translucent touch targets with thin white outlines.
- Left-side floating joystick: separate base and movable knob.
- Right-side action buttons: sprint, crouch, jump, flashlight, scan and interact.
- Chat and settings sit in the upper-right utility column.
- Build/move icon is a contextual action for ship-placeable objects.

## Files
- `button-ring.svg`: reusable circular hit-target skin.
- `joystick-base.svg` and `joystick-knob.svg`: layered, movable virtual stick.
- `sprint.svg`, `crouch.svg`, `jump.svg`, `flashlight.svg`, `scan.svg`, `interact.svg`, `chat.svg`, `settings.svg`, `build-move.svg`: action glyphs.

## Integration status
These are source vector assets only. They are **not yet wired into the APK runtime**. The current repository contains the packaged Android APK, Unity asset inspection scripts, and IL2CPP metadata dumps, but not the editable Unity project or source files for the custom `LethalOffline.MobileControls` assembly. Integrating the SVGs requires rebuilding that runtime assembly and packaging it with Unity's Vector Graphics support (or converting the vectors into Unity sprites and wiring those sprites into the generated controls).

No game textures, 3D meshes, or audio are modified by these design assets.
