---
taxonomy: context
variant: main
version: 1
based_on: 0
round: 0
---

# Context codebook (fixture for the agent test harness)

Synthetic repo kinds for testing agents only (#62). Not the study's context codebook (#41).
Never register this file in the real labels.db.

## kind-project: Operational project

### Definition
The repository exists to build or run something else, and its skills support that work.

### Include
- Application, library or service code with a few skills for working on it.

### Exclude
- Repositories meant to be copied as a starting point: use kind-template.

### Examples
- fx-garden/garden-app: "Garden App is a Flask web application our community garden uses to plan watering and planting."

## kind-catalog: Catalog or collection

### Definition
The skills themselves are the product: the repository collects, lists or distributes them.

### Include
- Curated lists or libraries of many skills to browse or copy.

### Exclude
- A single skill shown for teaching: use kind-demo.

### Examples
- fx-kitchen/awesome-kitchen-skills: "A curated collection of agent skills for cooking and baking."

## kind-template: Template or starter

### Definition
The repository is meant to be copied as the start of a new project.

### Include
- Repositories marked as templates, or whose README says to use them as a template or starter.

### Exclude
- Repositories that only show how something works: use kind-demo.

### Examples
- fx-starter/plant-starter: "Use this template to start a new plant-care project."

## kind-demo: Demonstration or tutorial

### Definition
The repository shows how skills work or teaches something, and is not meant for real use.

### Include
- Examples for a talk, course or tutorial.

### Exclude
- Repositories meant to be copied and filled in: use kind-template.

### Examples
- fx-demo/stamp-demo: "It is not meant for real use."
