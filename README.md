# BSTU-AI

A multi-agent AI system designed to help students automate academic tasks, accelerate learning, and enhance productivity at Belarusian State Technical University (BSTU).

---

## Overview

BSTU-AI is a diploma project that introduces an intelligent assistant system built on a multi-agent architecture. The system consists of specialized agents that handle different aspects of student life, all coordinated through a central orchestrator that understands user intent and routes requests appropriately.

The system is designed to work entirely through natural language interaction, with no button-based interfaces—just pure conversational interaction.

---

## Tech Stack

- **Language**: Python
- **LLM Framework**: LangChain, LangGraph
- **LLM Provider**: OpenRouter (currently)
- **Database**: Qdrant (for RAG), PostgreSQL (for structured data)
- **Interface**: Telegram Bot API, Open WebUI (planned)

---

## Architecture

The system follows a multi-agent architecture pattern where specialized agents handle distinct domains of functionality. All agents are managed by a central **orchestrator** that:

1. Extracts user intents from natural language input
2. Routes requests to the appropriate agent based on detected intents
3. Coordinates responses back to the user

---

## Agents

The system currently consists of three specialized agents, each with a clearly defined responsibility domain:

| Agent | Description |
|-------|-------------|
| **Learning Agent** | Helps students learn subjects faster using pre-loaded BSTU-specific materials (notes, lectures, etc.). Utilizes RAG (Retrieval-Augmented Generation) to provide context-aware explanations. Includes quiz generation and grading capabilities for better retention. |
| **Academic Agent** | Provides centralized access to academic information including professor profiles, course requirements, exam conditions, and evaluation criteria. |
| **Scheduler Agent** | Manages reminders and deadlines for coursework, exams, and other academic events. Fully natural-language driven with Telegram integration. | 

---

## Supported Intents

The system recognizes various intents that are routed to the appropriate agents. The intent list is continuously evolving as the project develops.

### Learning Agent Intents

| Intent | Description |
|--------|-------------|
| `learning.explain` | Explain a topic using BSTU-specific reference materials |
| `learning.summarize` | Create a summary of a topic or material |
| `learning.quiz.generate` | Generate a quiz to test the user's knowledge |
| `learning.quiz.grade` | Grade user's quiz answers and provide explanations for mistakes |
| `learning.plan.revision` | Propose a revision plan based on identified weak areas |

### Academic Agent Intents

| Intent | Description |
|--------|-------------|
| `academic.professor.profile` | Provide information about a professor and their courses |
| `academic.course.requirements` | List course requirements, exam conditions, and evaluation criteria |

### Scheduler Agent Intents

| Intent | Description |
|--------|-------------|
| `schedule.lookup` | Look up event dates or class schedules |
| `schedule.deadline.lookup` | Find deadlines for coursework or exams |
| `schedule.reminder.create` | Create a reminder for an upcoming event or deadline |
| `schedule.reminder.edit` | Edit an existing reminder |
| `schedule.reminder.delete` | Delete an existing reminder |
| `schedule.reminder.view` | View user's reminders (displays up to 5 reminders) |

---

## Project Status

This project is currently under active development. The intent list and functionality are continuously being expanded and refined.