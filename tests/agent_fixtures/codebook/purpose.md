---
taxonomy: purpose
variant: main
version: 1
based_on: 0
round: 0
---

# Purpose codebook (fixture for the agent test harness)

Synthetic categories for testing agents only (#62). Deliberately about non-software topics, so
nothing here hints at a real purpose category. Never register this file in the real labels.db.

## cat-a: Gardening

### Definition
Skills whose main purpose is caring for plants: watering, planting, pruning or harvesting.

### Include
- Watering schedules and amounts for beds or pots.
- Pruning and cutting back plants.

### Exclude
- Cooking with harvested produce: use cat-b.

### Examples
- 2be41365be68fc979e51e33ca5e5214fae816aed: "Water seedlings every day and established beds every three days."

## cat-b: Cooking

### Definition
Skills whose main purpose is preparing food or drink.

### Include
- Recipes and baking procedures.
- Making sauces and spreads.

### Exclude
- Responding to kitchen emergencies such as fires: use cat-d.

### Examples
- 1bb3a72cc2c59812f32167d396e4cff1435d6d7d: "Bake at 220 C for 30 minutes, until the loaf sounds hollow when tapped."

## cat-c: Collecting

### Definition
Skills whose main purpose is organising or caring for a collection of objects.

### Include
- Sorting, cataloguing and storing collected items.

### Exclude
- Organising food storage: use cat-b.

### Examples
- 3ef4c76ebba10a3ca8185ae17254b1f7c4db3417: "Sort the stamps first by country, then by year of issue, oldest first."

## cat-d: Emergency response

### Definition
Skills whose main purpose is responding to an emergency such as a fire, flood or injury.

### Include
- What to do when an alarm goes off; evacuation and safety steps.

### Exclude
- Routine care or cooking that only mentions safety in passing: use the category of the routine.

### Examples
- 2a0f2c58258cb4529a4e23b076135116612eb749: "Never pour water on a grease fire: cover the pan with a lid."
