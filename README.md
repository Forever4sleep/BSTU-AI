# BSTU-AI

## Purpose 

BSTU-AI is a diploma project which introduces a multi-agent system that helps students automate certain activities, learn stuff quicker and be overall more productive. 

## Functionality

Currently, I am planning on building three separate agents with their own responsibility domain.

| Agent | What it does |
| ----- | ------------ |
| <b>Learning Agent</b> | Helps students learn a subject faster using pre-loaded materials: notes, lectures and so on.   Uses the RAG concept as the underlying mechanism of using materials unique to BSTU. I am also planning on adding quizes for better retention. |
| <b>Academic Agent</b> | Used as the go-to helper to retrieve useful information about the professors, exam requirements, passing criterion – all in one place.|  
| <b>Scheduler Agent</b> | Buddy that helps you set a reminder for an upcoming coursework deadline, exam – all via Telegram and zero buttons, just raw text! |

Agents are managed by the <b>orchestator</b>.
An orchestator, in the content of BSTU-AI, is a mechanism that helps understand the end user, what they're asking right now. It extracts the intents of a user's request and then decides which agent to utilize.

Right now there's an undefined number of intents, though there are draft ones. As I make progress in building this project, I am going to fill up this list more and more and make it more accurate. 

### Learning Agent

| Intent | Description | 
| ------ | ----------- | 
| learning.explain | explain a topic using reference material specific to BSTU. | 
| learning.summarize | create a summary of a topic. | 
| learning.quiz.generate | come up with a quiz to test the user's knowledge. | 
| learning.quiz.grade | check the user's answers and provide explanations to the mistakes made. | 
| learning.plan.revision | propose a revision plan in accordance with the user's weak links. | 


### Academic Agent 

| Intent | Description | 
| ------ | ----------- | 
| academic.professor.profile | provide info on a professor and their courses. |
| academic.course.requirements | list course requirements to sit for the exam, evaluation criterion |

### Scheduler Agent

| Intent | Description | 
| ------ | ----------- | 
| schedule.lookup | look up the certain event's date, class schedule. |
| schedule.deadline.lookup | find deadline (if there's one) |
| schedule.reminder.create | create a reminder (implemented via Telegram)| 

TO BE CONTINUED...