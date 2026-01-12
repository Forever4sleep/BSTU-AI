--- 
globs: 
alwaysApply: true
---

# BSTU-AI — Cursor Project Rules

## Project Overview

BSTU-AI is a diploma project that implements a **multi-agent AI system** aimed at improving student productivity, learning efficiency, and academic organization within the BSTU ecosystem.

The system is composed of several specialized agents, each responsible for a clearly defined domain, and a central **Orchestrator** that interprets user input and delegates execution to the appropriate agent based on inferred intent.

This file defines **global rules, architectural constraints, and behavioral expectations** for all AI-generated code and logic within this project.

---

## Core Architectural Principles

- The system follows a **multi-agent architecture**.
- Each agent must adhere to the **single-responsibility principle**.
- Agents must be **loosely coupled** and communicate only through the Orchestrator.
- User interaction is **intent-driven**, not flow- or UI-driven.

Do not assume the intent list is final.
---

## Orchestrator

### Role

The Orchestrator has two core responsibilities:

1. Extract user intents from raw input.
2. Decide which agents to utilize to handle the inferred intents.

### Behavioral Rules

- Prefer correctness over confidence when intent is ambiguous.
- Do not embed business logic inside the Orchestrator.
- Do not hardcode conversational flows.
- The Orchestrator must be resilient to incomplete or noisy user input.


### Current Implementation

- The intent classifier is currently implemented using a Large Language Model (LLM).
- There are plans to substitute the LLM-based intent classifier with a Deep Learning (DL) classifier in the future.

Orchestrator logic routes user input based on the classified intent.

---

## Agents

### 1. Learning Agent

**Purpose**  
Helps students learn subjects faster using BSTU-specific academic materials.

**Key Characteristics**
- Uses **Retrieval-Augmented Generation (RAG)** over preloaded BSTU resources such as:
  - Lecture notes
  - Course materials
  - Internal academic content
- Prioritizes accuracy, relevance, and alignment with BSTU curricula.
- Supports active learning through quizzes and revision planning.

**Supported Intents**
- `learning.explain` — explain a topic using BSTU reference materials.
- `learning.summarize` — produce a concise, structured summary.
- `learning.quiz.generate` — generate quizzes for knowledge retention.
- `learning.quiz.grade` — evaluate answers and explain mistakes.
- `learning.plan.revision` — propose a revision plan based on weak areas.

**Constraints**
- Do not hallucinate sources.
- Do not use general knowledge when BSTU-specific material is available.
- Explanations must be pedagogical and structured.

---

### 2. Academic Agent

**Purpose**  
Acts as a centralized academic information assistant.

**Key Characteristics**
- Provides authoritative and structured academic information.
- Focuses on professors, courses, exams, and evaluation criteria.
- Avoids speculation and unverifiable claims.

**Supported Intents**
- `academic.professor.profile` — provide information on a professor and their courses.
- `academic.course.requirements` — list course requirements, exam eligibility, and grading criteria.

**Constraints**
- Prefer structured output over narrative output.
- Do not infer requirements that are not explicitly known.
- Treat academic data as factual, not conversational.

---

### 3. Scheduler Agent

**Purpose**  
Helps students manage academic time and deadlines.

**Key Characteristics**
- Fully **natural-language driven** (no buttons, no UI flows).
- Integrates with **Telegram** for reminders and notifications.
- Focuses on schedules, deadlines, and academic events.

**Supported Intents**
- `schedule.lookup` — look up class schedules or event dates.
- `schedule.deadline.lookup` — find coursework or exam deadlines.
- `schedule.reminder.create` — create reminders via Telegram.
- `schedule.reminder.edit` — edit existing reminders using natural language.
- `schedule.reminder.delete` — delete reminders via Telegram or chat input.
- `schedule.reminder.list` — list all active reminders for the user.

**Constraints**
- Always confirm time-sensitive information when ambiguity exists.
- Do not create reminders without sufficient temporal data.
- Keep interactions concise and action-oriented.
- Reminders do not have priorities. 

---

## Intent Handling Rules

- Every user request must map to **one or multiple intents**.
- Intent extraction must be deterministic and explainable.
- Unknown intents should fail gracefully and be logged for future taxonomy expansion.

---

## Output Quality Standards

- Prefer clarity over verbosity.
- Use structured formats (lists, tables) where appropriate.
- Avoid unnecessary conversational filler.
- Optimize responses for **students**, not developers.

---

## Scope and Assumptions

- The system is **student-facing**.
- BSTU-specific context is first-class and must be preferred over general knowledge.
- New agents and intents will be added incrementally.
- This file defines **behavioral rules**, not implementation details.

---

## Explicit Non-Goals

- No UI logic or frontend assumptions.
- No hardcoded workflows.
- No speculative academic information.
- No monolithic agent behavior.

---
