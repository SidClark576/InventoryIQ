# InventoryIQ - UI/UX Improvement Spec (GAN Harness)

## Objective
Elevate the "Dark Luxury" operations terminal by adding high-end polish, fluid micro-interactions, and premium UI feedback mechanisms.

## Focus Areas

### 1. Skeleton Loaders
- **Problem**: When fetching data (inventory, transactions), the screen might be blank or show a generic "Loading..." text.
- **Improvement**: Implement a premium skeleton loading state with a subtle shimmer effect that perfectly matches the dark luxury color palette (`var(--bg-surface-2)` to `var(--bg-surface-3)`).

### 2. Premium Toast Notifications
- **Problem**: Standard browser alerts or simple text insertions feel cheap.
- **Improvement**: Create a custom, slide-in toast notification system in the bottom-right corner.
- **Design**: Glassmorphism background, glowing border (`--accent-bright` for success, `--red` for errors), smooth entrance/exit animations.

### 3. Beautiful Empty States
- **Problem**: Empty tables just look broken or empty.
- **Improvement**: Design dedicated "Empty State" components featuring a faded, glowing icon and elegant typography directing the user to take action (e.g., "Add your first item").

### 4. Interactive Micro-animations
- **Problem**: Table rows are static when hovered.
- **Improvement**: Add subtle transform/scale/background-color transitions on table rows.
- **Problem**: Checkboxes are default browser styles.
- **Improvement**: Ensure custom styling for checkboxes, making them align with the dark luxury aesthetic.
