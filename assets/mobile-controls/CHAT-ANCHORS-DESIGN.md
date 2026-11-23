# Chat HUD — anchor/layout continuation

Status: DESIGN IN PROGRESS — NOT integrated into the APK.

This continuation is for the chat anchoring/layout pass, not a project-completion marker. It preserves the current HUD concept while relocating the chat entry/panel to the left side so the upper-right utility group can remain settings-only.

## Anchor specification (Unity RectTransform reference)

All positions are normalized to Canvas coordinates; use a Canvas Scaler with Scale With Screen Size and safe-area-aware root. These are proposed anchor values, to be tuned in preview/device testing:

| Element | Anchor min | Anchor max | Pivot | Purpose |
|---|---|---|---|---|
| Chat toggle | (0, 1) | (0, 1) | (0, 1) | Upper-left safe-area corner, below status/readout |
| Chat panel | (0, 0.5) | (0, 0.5) | (0, 0.5) | Left-side panel; height constrained to middle 55–65% |
| Chat header | (0, 1) | (1, 1) | (0.5, 1) | Stays pinned to panel top |
| Message list | (0, 0) | (1, 1) | (0.5, 0.5) | Stretch within panel, offsets reserve header and input |
| Message input | (0, 0) | (1, 0) | (0.5, 0) | Pinned to panel bottom |
| Send button | (1, 0) | (1, 0) | (1, 0) | Bottom-right of input row |
| Settings/menu | (1, 1) | (1, 1) | (1, 1) | Upper-right corner; chat no longer occupies this utility slot |
| Joystick | (0, 0) | (0, 0) | (0, 0) | Lower-left; chat panel must not overlap when open |

## Placement rules

- Chat button sits left, but below the top-left weight/status display. It is not anchored to the joystick.
- The chat panel opens inward from the left edge; it must not cover the joystick base when open. If panel height overlaps the joystick region, panel open state hides/dims joystick visually but must not disable joystick input.
- Chat panel width target: 32–38% of landscape safe width; on narrow portrait layouts, 78–88% safe width. Maximum width 420 dp.
- Panel vertical span target: 58% of safe height, centered vertically; header and input stay pinned.
- Keep chat text readable: body target 14–16 dp, line spacing ~1.15, input 14 dp minimum. Avoid text behind camera notch/status cutout.
- Chat toggle uses the existing SVG chat icon and the same circular button ring. Settings stays in the right utility area.
- Opening chat should expose keyboard/input and a close/toggle affordance; closing it returns focus to gameplay. Do not invent network/chat message handlers or bypass the existing chat runtime.
- Keyboard-open state must be tested on Android: account for keyboard resize/pan, safe area, landscape and portrait, and ensure the input row stays visible.
- These anchors are a visual proposal only. Runtime anchoring depends on the editable Unity project/source for the custom mobile-controls assembly, which is not present in the repository.

## Acceptance checks (still pending)

1. Chat toggle is reachable without moving the left joystick.
2. Panel opens on left and stays inside safe area.
3. Settings remains top-right and no longer shares the chat group.
4. Chat panel does not cover action buttons or inventory.
5. Input field stays above the keyboard; sending/closing behavior remains functional.
6. Rotate device and test portrait/landscape.
7. Verify controls remain touch-responsive while panel open/closed.

