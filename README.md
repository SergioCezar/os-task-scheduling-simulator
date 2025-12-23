# Task Scheduling Simulator

This project implements a **task scheduling simulator** that models how an
operating system schedules tasks in a batch environment.

The simulator was developed as part of an academic assignment for the
**Operating Systems** course and focuses on both scheduling algorithms and
inter-process communication using sockets.

---

## Project Overview

The simulation is composed of three independent processes:

- **Clock** — simulates the CPU clock and controls the progression of time
- **Task Emitter** — reads tasks from an input file and emits them at the correct arrival time
- **Scheduler** — applies a selected scheduling algorithm and manages task execution

All components communicate through **TCP sockets**, simulating realistic
process interaction in an operating system.

---

## Implemented Scheduling Algorithms

The following CPU scheduling algorithms are implemented:

- **FCFS** — First-Come, First-Served
- **RR** — Round-Robin (quantum = 3)
- **SJF** — Shortest Job First
- **SRTF** — Shortest Remaining Time First
- **PRIOc** — Cooperative Priority Scheduling
- **PRIOp** — Preemptive Priority Scheduling
- **PRIOd** — Dynamic Priority Scheduling (with aging)

---

## Input Format

The input file describes the tasks to be scheduled.
Each line follows the format:

ID;arrival_time;duration;priority

Example:

t0;0;5;1
t1;2;3;2

---

## How to Run

### Requirements
- Python 3.x
- matplotlib

### Execution
```bash
python trab-so.py <input_file> <algorithm>
```
Example:

python trab-so.py entrada.txt fcfs

Available algorithms:

fcfs | rr | sjf | srtf | prioc | priop | priod

## Output

After the simulation finishes, the scheduler generates:

A text output file containing:

- The execution timeline

- Turnaround time and waiting time for each task

- Average turnaround and waiting times

- A Gantt chart image illustrating task execution over time

---

## Technical Report

A detailed technical report describing design decisions,
algorithm analysis, and performance evaluation is available
in the `report/` directory.
